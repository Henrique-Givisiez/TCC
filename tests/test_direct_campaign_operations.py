"""C1.3.3: deterministic operational tests; all collection is in-memory/files."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import json
import tempfile
import unittest

from analysis.detection.scientific import protocol as p,engine
from analysis.detection.inputs import ContractError,read_json,digest
from experiments.scientific_campaign import Campaign,Halt
from experiments.scientific_collection import save,CollectionFailure,DockerBackend
from experiments import scientific_operations as ops
from experiments.stress_observer import DIRECT_POLICY,requires_stop,Watcher

ROOT=p.ROOT
SPEC=read_json(ROOT/'docs/scientific_protocol_direct_20261108.json')['specification']

class Backend:
    def __init__(self):self.calls=[];self.fail={};self.crash=None;self.clean=True
    def preflight(self,entry,directory):
        result=dict(ready=True);save(directory/'preflight.json',result);return result
    continuation_ready=preflight
    def collect(self,entry,directory,timeout):
        self.calls.append(entry['id'])
        save(directory/'cleanup.json',dict(verified=self.clean,observed_epoch=100))
        if entry['id'] in self.fail:raise CollectionFailure(self.fail[entry['id']],'diagnosed fixture failure')
        receipt=dict(entry_id=entry['id'],run_id=entry['id'],cleanup_epoch=100,operational=dict(recovery_confirmed=False))
        save(directory/'completed.json',receipt)
        if self.crash==entry['id']:
            self.crash=None;raise RuntimeError('controller interrupted')
        return receipt
    def recover(self,entry,directory):
        path=directory/'completed.json'
        if not path.exists():raise CollectionFailure('INDETERMINATE_ATTEMPT','unknown')
        return read_json(path)

class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.stack=ExitStack();self.addCleanup(self.stack.close)
        spec=deepcopy(SPEC);spec['execution_release']['allowed']=True  # Synthetic branch only; disk authority stays false.
        self.stack.enter_context(patch.object(p,'SPEC',spec))
        self.stack.enter_context(patch.object(engine,'SPEC',spec))
        self.stack.enter_context(patch.object(p,'runtime_hashes',return_value={}))
        self.stack.enter_context(patch.object(engine,'runtime_hashes',return_value={}))
        self.stack.enter_context(patch('experiments.scientific_campaign.verify_receipt'))
        self.stack.enter_context(patch('experiments.scientific_campaign.time.time',return_value=160))
        self.stack.enter_context(patch('experiments.scientific_campaign.time.sleep'))
        self.stack.enter_context(patch.object(p,'FEATURES',()))
        self.backend=Backend();entries=[]
        for i in range(4):
            path=self.root/f'cfg{i}.json';save(path,dict(id=str(i)))
            entries.append(dict(id=str(i),partition='BASELINE',config=str(path),config_sha256=digest(path)))
        for name in ('spec','environment'):save(self.root/(name+'.json'),{})
        ref=lambda name:dict(path=str(self.root/(name+'.json')),sha256=digest(self.root/(name+'.json')))
        self.plan=dict(entries=entries,protocol=ref('spec'),environment=ref('environment'),runtime_hashes={},results_root=str(self.root/'result'))
        self.path=self.root/'plan.json';save(self.path,self.plan)
        self.stack.enter_context(patch.object(p,'load_plan',return_value=self.plan))
        self.stack.enter_context(patch.object(p,'validate_handoff',return_value=None))
        self.c=Campaign(self.path,digest(self.path),self.backend)

    def test_complete_partition_and_scientific_nonrecovery_does_not_stop(self):
        checkpoint=self.c.run_partition('BASELINE','BASELINE')
        self.assertEqual(len(checkpoint.read()['receipts']),4)
        self.assertEqual(self.backend.calls,['0','1','2','3'])
        self.assertEqual(self.c.status()['accepted_slots'],4)

    def test_recoverable_failure_collects_remaining_without_checkpoint_or_retry(self):
        self.backend.fail['0']='CAPTURE_LOSS'
        with self.assertRaisesRegex(Halt,'unresolved technical'):self.c.run_partition('BASELINE','BASELINE')
        self.assertEqual(self.backend.calls,['0','1','2','3'])
        self.assertFalse(self.c.checkpoints())
        self.assertEqual(self.c.status()['pending_count'],1)
        with self.assertRaises(Halt):self.c.run_partition('CAL_A','CAL_A')
        with self.assertRaises(Halt):self.c.run_partition('BASELINE','BASELINE')
        self.assertEqual(self.backend.calls,['0','1','2','3'])
        self.assertFalse(any(e['kind']=='REPLACEMENT_APPROVED' for e,h in self.c.events()))

    def test_failed_cleanup_halts(self):
        self.backend.fail['0']='CAPTURE_LOSS';self.backend.clean=False
        with self.assertRaisesRegex(Halt,'Cleanup unconfirmed'):self.c.run_partition('BASELINE','BASELINE')
        self.assertEqual(self.backend.calls,['0'])

    def test_identity_and_unknown_failures_halt(self):
        self.backend.fail['0']='IDENTITY_JOURNAL_MISMATCH'
        with self.assertRaisesRegex(Halt,'diagnosis'):self.c.run_partition('BASELINE','BASELINE')
        self.assertEqual(self.backend.calls,['0'])

    def test_resume_completed_attempt_without_new_collection(self):
        self.backend.crash='0'
        with self.assertRaisesRegex(RuntimeError,'interrupted'):self.c.run_partition('BASELINE','BASELINE')
        self.c.run_partition('BASELINE','BASELINE')
        self.assertEqual(self.backend.calls,['0','1','2','3'])
        self.assertEqual(self.c.status()['consumed_attempts'],4)

    def test_unknown_consumed_attempt_is_never_repeated(self):
        entry=self.plan['entries'][0];directory=self.c.root/'collection/0/attempt-1'
        with self.c.locked():pass
        save(directory/'attempt.json',dict(authority=self.c.authority,entry=entry,attempt_number=1))
        with self.assertRaises(Halt):self.c.run_partition('BASELINE','BASELINE')
        self.assertEqual(self.backend.calls,[])
        self.assertEqual(self.c.status()['consumed_attempts'],1)

    def test_idle_after_failure_and_success(self):
        self.backend.fail['0']='CAPTURE_LOSS'
        with patch('experiments.scientific_campaign.time.time',return_value=110),patch('experiments.scientific_campaign.time.sleep') as sleep:
            with self.assertRaises(Halt):self.c.run_partition('BASELINE','BASELINE')
            self.assertTrue(sleep.called)
            self.assertTrue(all(call.args==(50,) for call in sleep.call_args_list))

    def test_pending_test_does_not_consolidate(self):
        for e in self.plan['entries']:e['partition']='TEST'
        self.backend.fail['0']='MONITOR_SUPPORT'
        fake={part:dict(manifest_sha256=part) for part in ('BASELINE','CAL_A','CAL_B')}
        with patch.object(self.c,'checkpoints',return_value=fake),patch('experiments.scientific_campaign.evaluation.aggregate') as aggregate:
            with self.assertRaisesRegex(Halt,'unresolved technical'):self.c.run_partition('TEST','TEST','CAL_B')
            aggregate.assert_not_called()
        self.assertEqual(self.backend.calls,['0','1','2','3'])

    def test_sequence_requires_explicit_authorization_and_release(self):
        with self.assertRaisesRegex(Halt,'authorization'):self.c.run_sequence('yes')
        with patch.object(p,'SPEC',SPEC),self.assertRaisesRegex(Halt,'Structural'):self.c.run_sequence('ALL_PARTITIONS')
        self.assertEqual(self.backend.calls,[])

    def test_sequence_resumes_at_partition_boundary_with_checkpoint_hash(self):
        checkpoints={'BASELINE':dict(manifest_sha256='baseline')};calls=[]
        def run(partition,authorization,previous):
            calls.append((partition,authorization,previous))
            checkpoints[partition]=dict(manifest_sha256=partition)
        with patch.object(self.c,'checkpoints',side_effect=lambda:dict(checkpoints)),patch.object(self.c,'run_partition',side_effect=run),patch.object(self.c,'status',return_value={'complete':True}):
            self.assertEqual(self.c.run_sequence('ALL_PARTITIONS'),{'complete':True})
        self.assertEqual(calls,[('CAL_A','CAL_A','baseline'),('CAL_B','CAL_B','CAL_A'),('TEST','TEST','CAL_B')])
        self.assertEqual([e['kind'] for e,h in self.c.events()],['SEQUENCE_AUTHORIZED'])

    def test_subprocess_and_idle_reserve_is_not_reduced_by_preparation(self):
        with patch.object(self.backend,'collect',wraps=self.backend.collect) as collect:
            self.c.run_partition('BASELINE','BASELINE')
            self.assertTrue(all(call.args[2]==480 for call in collect.call_args_list))

    def test_replacement_explicit_same_slot(self):
        self.backend.fail['0']='CAPTURE_LOSS'
        with self.assertRaises(Halt):self.c.run_partition('BASELINE','BASELINE')
        failure=self.c.root/'collection/0/attempt-1/failure.json'
        self.c.authorize_replacement(digest(failure));self.backend.fail.clear()
        self.c.run_partition('BASELINE','BASELINE')
        self.assertEqual(self.backend.calls,['0','1','2','3','0'])
        self.assertEqual(self.c.status()['authorized_substitutions'],1)

    def test_journal_evidence_tampering_stops(self):
        self.backend.fail['0']='CAPTURE_LOSS'
        with self.assertRaises(Halt):self.c.run_partition('BASELINE','BASELINE')
        failure=self.c.root/'collection/0/attempt-1/failure.json'
        failure.write_text('{}')
        with self.assertRaises(ContractError):self.c.status()

class DirectIntegrationTests(unittest.TestCase):
    def test_full_direct_preflight_without_docker_or_capture(self):
        import sys,socket
        images=dict(victim='sha256:'+'a'*64,source='sha256:'+'b'*64)
        client=Mock();client.info.return_value=dict(ID='daemon',KernelVersion='kernel')
        client.containers.list.return_value=[]
        client.images.get.side_effect=lambda identity:SimpleNamespace(id=identity)
        process=Mock();process.poll.return_value=None;process.wait.return_value=0
        def capture(*a,**kw):kw['stderr'].write('listening on lo\n');kw['stderr'].flush();return process
        with tempfile.TemporaryDirectory() as folder,ExitStack() as stack:
            root=Path(folder);lock=root/'environment.json'
            save(lock,dict(daemon_id='daemon',kernel='kernel',python=sys.version.split()[0],images=images,packages={}))
            plan=dict(environment=dict(path=str(lock),sha256=digest(lock)),runtime_hashes={})
            stack.enter_context(patch.object(p,'SPEC',SPEC))
            stack.enter_context(patch.object(p,'runtime_hashes',return_value={}))
            factory=stack.enter_context(patch('docker.DockerClient',return_value=client))
            stack.enter_context(patch('experiments.development_d1_ops.process_rows',return_value=[]))
            stack.enter_context(patch.object(ops,'readiness',return_value=dict(verified=True)))
            code=stack.enter_context(patch.object(ops,'image_bindings',return_value={'image-code':'verified'}))
            stack.enter_context(patch('experiments.stress_runtime.resources',return_value={'limits':'fixture'}))
            stack.enter_context(patch('experiments.scientific_collection.subprocess.Popen',side_effect=capture))
            stack.enter_context(patch('experiments.scientific_collection.time.sleep'))
            stack.enter_context(patch.object(socket,'socket'))
            result=DockerBackend(plan).preflight({},root)
            self.assertTrue(result['ready']);code.assert_called_once_with(client,images)
            self.assertEqual(client.containers.run.call_args.args[0],images['source'])
            self.assertEqual(factory.call_args.kwargs['timeout'],3)

    def test_two_image_ids_and_full_code_verification(self):
        images=dict(victim='sha256:'+'a'*64,source='sha256:'+'b'*64);client=Mock()
        client.images.get.side_effect=lambda identity:SimpleNamespace(id=identity)
        with patch('experiments.image_code_evidence.verify_image_code',return_value={'verified':True}) as verify:
            self.assertEqual(ops.image_bindings(client,images),{'verified':True})
            verify.assert_called_once_with(client,images)
        client.images.get.side_effect=None;client.images.get.return_value.id='other'
        with self.assertRaises(ContractError):ops.image_bindings(client,images)
        with self.assertRaises(ContractError):ops.image_bindings(client,dict(images,proxy='nginx'))

    def test_direct_degradation_vs_technical_failure(self):
        for reason in ('service_compromise','generator_queue'):
            self.assertFalse(requires_stop(reason,DIRECT_POLICY));self.assertTrue(requires_stop(reason))
        for reason in ('collection_stale','observer_failure'):
            self.assertTrue(requires_stop(reason,DIRECT_POLICY))

    def test_real_watcher_action_with_mocked_journals(self):
        for reason in ('service_compromise','generator_queue','collection_stale'):
            with self.subTest(reason=reason),tempfile.TemporaryDirectory() as folder:
                manager=SimpleNamespace(directory=Path(folder),entries=[],observer_policy=DIRECT_POLICY,stop_attack=Mock())
                gt=SimpleNamespace(run_id='r',clock=SimpleNamespace(elapsed=lambda:160,monotonic_initial=500))
                collector=SimpleNamespace(fresh={'v':660},_container_ids=['v'])
                w=Watcher(manager,gt,collector)
                with patch('experiments.stress_observer.records',return_value=[]),patch.object(w.engine,'evaluate',return_value=dict(reason=reason)),patch.object(w.done,'wait',side_effect=lambda _:w.done.set()):w.run()
                self.assertIsNone(w.failure)
                self.assertEqual(manager.stop_attack.called,reason=='collection_stale')
                self.assertEqual(json.loads(w.path.read_text())['policy'],DIRECT_POLICY)

    def test_observer_exception_stops_safely(self):
        with tempfile.TemporaryDirectory() as folder:
            manager=SimpleNamespace(directory=Path(folder),entries=[],observer_policy=DIRECT_POLICY,stop_attack=Mock())
            gt=SimpleNamespace(run_id='r',clock=SimpleNamespace(elapsed=lambda:160))
            w=Watcher(manager,gt,SimpleNamespace())
            with patch('experiments.stress_observer.records',side_effect=ValueError('broken observation')):w.run()
            self.assertIsNotNone(w.failure)
            self.assertEqual(manager.stop_attack.call_args.args[0]['reason'],'observer_failure')

    def test_budget_reuses_limits_and_cpu_unchanged(self):
        with patch.object(p,'SPEC',SPEC):
            policy=ops.policy()
            from simulator.experiment_config import ExperimentConfig
            for cfg in SPEC['scenario_configurations'].values():
                policy.validate(ExperimentConfig.from_dict(dict(cfg,id='fixture',seed=1)))
        self.assertEqual(policy.global_timeout_seconds,480)
        self.assertEqual(policy.min_available_bytes,2*1024**3)
        self.assertEqual(SPEC['cpu_contract']['scheduling_lead_seconds'],'0.025')
        self.assertEqual(SPEC['drain_seconds'],30)
        self.assertEqual(SPEC['idle_seconds'],60)

    def test_direct_checks_reuse_capture_and_require_clean_cpu_worker(self):
        with tempfile.TemporaryDirectory() as folder:
            raw=Path(folder)
            save(raw/'victim_stats.summary.json',dict(run_id='r',worker_finished=True,fatal_error=None))
            save(raw/'run_status.json',dict(cpu_observation_contract='victim-cpu-snapshots-v1'))
            save(raw/'operational_policy.json',dict(cleanup_verified=True,post_cleanup_readiness=dict(verified=True),actions=[],failures=[]))
            with patch('experiments.development_d3.collection_checks',return_value=[dict(name='capture_csv',passed=True)]) as capture:
                checks=ops.collection_checks(raw,'r')
                capture.assert_called_once_with(raw,'r',capture_only=True)
                self.assertTrue(all(c['passed'] for c in checks))
            summary=read_json(raw/'victim_stats.summary.json');summary['fatal_error']='persistence failed'
            (raw/'victim_stats.summary.json').write_text(json.dumps(summary))
            with patch('experiments.development_d3.collection_checks',return_value=[]):
                self.assertFalse(ops.collection_checks(raw,'r')[0]['passed'])

    def test_pilot_requires_complete_direct_configuration_and_exact_policy(self):
        from analysis.detection.scientific.direct_contract import configuration
        from simulator.experiment_config import ExperimentConfig
        from dataclasses import replace
        with patch.object(p,'SPEC',SPEC):
            operational=SimpleNamespace(policy=ops.policy())
            cfg=ExperimentConfig.from_dict(configuration(SPEC,'A3','diagnostic-only',7))
            ops.validate_pilot(cfg,'A3',operational)
            with self.assertRaises(ContractError):ops.validate_pilot(cfg,'F96',operational)
            with self.assertRaises(ContractError):ops.validate_pilot(cfg,'A3',None)
            operational.policy=replace(operational.policy,global_timeout_seconds=240)
            with self.assertRaises(ContractError):ops.validate_pilot(cfg,'A3',operational)

    def test_shared_runtime_adapter_preserves_genuine_sample_freshness(self):
        from simulator import source_experiment,stats_collector
        from experiments.stress_runtime import StressManager
        with patch.object(source_experiment,'SourceManager'),patch.object(stats_collector,'StatsCollector',stats_collector.StatsCollector),patch.object(StressManager,'expected_resources'),patch.object(StressManager,'collector'),patch.object(StressManager,'observer_policy',None,create=True):
            ops.install_observer({'limits':'fixture'},DIRECT_POLICY)
            collector=stats_collector.StatsCollector(Mock())
            self.assertIs(StressManager.collector,collector)
            self.assertIs(source_experiment.SourceManager,StressManager)
            collector._on_acquisition(SimpleNamespace(id='v'),{'read':'2026-11-08T00:00:00Z'},1)
            collector._on_acquisition(SimpleNamespace(id='v'),{'read':'2026-11-08T00:00:00Z'},2)
            self.assertEqual(collector.samples.snapshot()[0],{'v':1})

    def test_randomized_balance_deterministic(self):
        from analysis.detection.scientific.direct_contract import randomized_test_order
        self.assertEqual(SPEC['test_order'],randomized_test_order(SPEC['test_randomization']['seed']))
        self.assertNotEqual(SPEC['test_order'][:6],SPEC['test_order'][6:12])

class ReconciliationTests(unittest.TestCase):
    def fixture(self,raw,attack):
        from tests.test_development_d3_origins import origins_fixture
        from tests.test_development_d3 import put,csvwrite
        from simulator.request_logger import REQUEST_FIELDS
        from simulator.ground_truth import EVENT_FIELDS
        from simulator.experiment_config import ExperimentConfig
        from experiments import stress_processing as processing
        from analysis.detection.scientific.direct_contract import configuration
        cfg=origins_fixture(raw,dict(effective_configuration=configuration(SPEC,'A3','fixture',123)))
        inventory=read_json(raw/'source_inventory.json')
        inventory=[e for e in inventory if e['source_id'] in ('normal_1','normal_2') or attack and e['source_type']=='attack']
        for e in inventory:
            if e['source_type']=='normal':e['send_workers']=32
        put(raw/'source_inventory.json',inventory)
        rows=processing.csv_rows(raw/'request_log.csv',REQUEST_FIELDS)
        ids={e['source_id'] for e in inventory}
        rows=[r for r in rows if any(r['request_id'].startswith('request_'+sid+'_') for sid in ids)]
        if not attack:
            c=configuration(SPEC,'L2','fixture',123);cfg=ExperimentConfig.from_dict(c)
            for r in rows:r.update(attack_active=0,active_event_ids='[]')
            csvwrite(raw/'attack_events.csv',EVENT_FIELDS,[])
        csvwrite(raw/'request_log.csv',REQUEST_FIELDS,rows)
        return cfg

    def test_two_legitimate_and_two_offensive_full_journal_and_ground_truth(self):
        from experiments import stress_processing as processing
        from analysis.detection.scientific.evaluation import impact
        from tests.test_development_d3 import put
        for attack in (False,True):
            with self.subTest(attack=attack),tempfile.TemporaryDirectory() as folder:
                raw=Path(folder)/'raw';cfg=self.fixture(raw,attack)
                put(raw/'effective_config.json',json.loads(cfg.to_json()))
                life,rows,_=processing.reconcile(raw,cfg)
                self.assertTrue(life['controlled_closure']);self.assertEqual(life['records_lost'],0)
                self.assertEqual(len(life['closures']),4 if attack else 2)
                gt=processing.validate_ground_truth(raw,cfg,rows,life['run_id'])
                self.assertEqual(len(gt['events']),int(attack))
                self.assertIn('recovery_confirmed',impact(raw))

    def test_missing_or_duplicate_source_rejected(self):
        from experiments import stress_processing as processing
        from tests.test_development_d3 import put
        with tempfile.TemporaryDirectory() as folder:
            raw=Path(folder)/'raw';cfg=self.fixture(raw,True)
            inventory=read_json(raw/'source_inventory.json')
            for bad in (inventory[:-1],inventory+[inventory[0]],inventory[:-1]+[inventory[0]]):
                put(raw/'source_inventory.json',bad)
                with self.assertRaisesRegex(ValueError,'Inventory'):processing.reconcile(raw,cfg)

if __name__=='__main__':unittest.main()
