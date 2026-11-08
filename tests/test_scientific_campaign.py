"""Synthetic scientific partitions, no Docker and no actual load execution."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import csv
import json
import tempfile
import unittest
import time

from analysis.detection.scientific import protocol as p,engine,evaluation,statistics,data
from analysis.detection.inputs import ContractError,digest,read_json
from analysis.detection.artifacts import encoded,open_artifact
from experiments.scientific_campaign import Campaign,Halt
from experiments.scientific_collection import CollectionFailure,save,DockerBackend
from tests import test_detection_framework as fixtures

REAL_ROOT=p.ROOT
TEMPLATE=read_json(REAL_ROOT/'experiments/configs/development_d3_origins_20261029/d3_origins_A_N1.json')


def read_csv(path):
    with Path(path).open(newline='') as stream:return list(csv.DictReader(stream))


class FixtureBackend:
    def __init__(self,root,*,bad_b=False,fail_once=None,crash_after_receipt=None):
        self.root=root;self.bad_b=bad_b;self.fail_once=fail_once;self.crash=crash_after_receipt
        self.calls=[];self.preflights=0;self.secondary_constant=False;self.tail=False
    def preflight(self,entry,directory):
        self.preflights+=1;r=dict(ready=True,started_epoch=time.time(),finished_epoch=time.time(),backend='fixture')
        save(directory/'preflight.json',r);return r
    def collect(self,entry,directory,timeout):
        self.calls.append((entry['id'],str(directory)))
        if (self.fail_once==entry['id'] or isinstance(self.fail_once,set) and entry['id'] in self.fail_once) and directory.name=='attempt-1':
            raise CollectionFailure('CAPTURE_LOSS','Synthetic capture kernel loss')
        result=self.fixture(entry,directory)
        save(directory/'fixture-result.json',result)
        if self.crash==entry['id']:
            self.crash=None;raise RuntimeError('Synthetic controller crash after completed collection')
        return result
    def recover(self,entry,directory):
        path=directory/'fixture-result.json'
        if not path.exists():raise CollectionFailure('INDETERMINATE_ATTEMPT','Unknown consumed attempt')
        return read_json(path)
    def fixture(self,entry,directory):
        values=[14+2*(i%3) for i in range(390)]
        if self.bad_b and entry['partition']=='CAL_B':values=[40+2*(i%3) for i in range(390)]
        event_end=216 if entry['scenario']=='E16' else 270
        if entry['partition']=='TEST' and entry['scenario'] in ('E16',):
            values=[v+8 if 150<=i<event_end else v for i,v in enumerate(values)]
        if self.tail:values.append(0)
        helper=fixtures.DetectionFrameworkTests();helper.root=directory
        rid='fixture_'+entry['id']+'_'+directory.name
        feature=helper.fixture('features',rid,values)
        if self.secondary_constant and entry['partition']=='BASELINE':
            path=feature/'timeseries/service.csv'
            with path.open(newline='') as stream:reader=csv.DictReader(stream);fields=reader.fieldnames;rows=list(reader)
            for row in rows:row['mean_duration_ms']='16'
            with path.open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
        dataset=directory/'dataset';dataset.mkdir()
        status=dict(run_id=rid,status='completed',experiment_start_timestamp=1000,experiment_start_monotonic=500)
        save(dataset/'metadata/run_status.json',status);save(dataset/'metadata/effective_config.json',read_json(entry['config']))
        path=dataset/'raw/attacks/attack_events.csv';path.parent.mkdir(parents=True)
        columns=['run_id','experiment_id','profile','experiment_start_timestamp','experiment_start_monotonic',
                 'scheduled_start_seconds','scheduled_end_seconds','actual_start_seconds','actual_end_seconds']
        with path.open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader()
            if entry['scenario']!='C16':writer.writerow(dict(zip(columns,[rid,entry['id'],'continuous',1000,500,150,270,150,event_end])))
        dm=dict(run_id=rid,run_status='metadata/run_status.json',files=[])
        for file in sorted(dataset.rglob('*')):
            if file.is_file():dm['files'].append(dict(path=str(file.relative_to(dataset)),sha256=digest(file),bytes=file.stat().st_size))
        save(dataset/'dataset_manifest.json',dm)
        mp=feature/'feature_manifest.json';m=read_json(mp);m['dataset_manifest_sha256']=digest(dataset/'dataset_manifest.json')
        for item in m['outputs']:
            if item['path']=='timeseries/service.csv':
                path=feature/item['path'];item.update(sha256=digest(path),bytes=path.stat().st_size)
        report_path=feature/'evidence/stage9_validation_report.json';report=read_json(report_path)
        report['dataset_manifest_sha256']=m['dataset_manifest_sha256'];report_path.write_text(encoded(report))
        m['stage9_validation_report']['sha256']=digest(report_path)
        for item in m['outputs']:
            if item['path']=='evidence/stage9_validation_report.json':item.update(sha256=digest(report_path),bytes=report_path.stat().st_size)
        mp.write_text(encoded(m))
        return dict(entry_id=entry['id'],run_id=rid,features=str(feature.resolve()),dataset=str(dataset.resolve()),
            feature_manifest_sha256=digest(mp),dataset_manifest_sha256=digest(dataset/'dataset_manifest.json'),
            technical_valid=True,cleanup_verified=True,cleanup_epoch=0,backend='fixture',
            operational=dict(exposure_seconds=None if entry['scenario']=='C16' else event_end-150,early_stop=None if entry['scenario']=='C16' else event_end<270,recovery_confirmed=True,scalars={'exposure_seconds':None if entry['scenario']=='C16' else event_end-150,'ACTIVE/success_fraction':1.0},phases={}),
            files={str(f.resolve()):digest(f) for folder in (feature,dataset) for f in folder.rglob('*') if f.is_file()})


class ScientificCampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.frozen=p.runtime_hashes();self.stack=ExitStack();self.addCleanup(self.stack.close)
        protocol_path=self.root/'experiments/protocols/scientific_protocol_20261029.json'
        save(protocol_path,read_json(p.PROTOCOL_PATH))
        template_path=self.root/'experiments/configs/development_d3_origins_20261029/d3_origins_A_N1.json'
        template_path.parent.mkdir(parents=True,exist_ok=True)
        template_path.write_bytes((REAL_ROOT/'experiments/configs/development_d3_origins_20261029/d3_origins_A_N1.json').read_bytes())
        save(self.root/'experiments/protocols/historical.json',dict(seed=42))
        for module in (p,engine,evaluation):self.stack.enter_context(patch.object(module,'runtime_hashes',return_value=self.frozen))
        self.stack.enter_context(patch.object(p,'ROOT',self.root));self.stack.enter_context(patch.object(p,'PROTOCOL_PATH',protocol_path))
        entries=[];groups={}
        for i,slot in enumerate(p.expected_slots()):
            group=('TEST',slot['block']) if slot['partition']=='TEST' else (slot['partition'],slot['ordinal'])
            groups.setdefault(group,1000+len(groups));seed=groups[group];eid=f"sci_{i+1:03d}_{slot['scenario']}"
            cfg=deepcopy(TEMPLATE);cfg.update(id=eid,seed=seed)
            scenario=slot['scenario'];cfg['attack'].update(enabled=scenario!='C16',attackers=0 if scenario=='C16' else 1,
                rate=0 if scenario=='C16' else 16,endpoint='/medium' if scenario=='M16' else '/expensive')
            path=self.root/'configs'/f'{eid}.json';save(path,cfg)
            entries.append(dict(**slot,id=eid,seed=seed,config=str(path),config_sha256=digest(path)))
        from experiments.development_d1 import collect_seeds
        sources=[]
        for file in sorted((self.root/'experiments').rglob('*.json')):
            seeds=sorted(collect_seeds(read_json(file)))
            if seeds:sources.append(dict(path=str(file),sha256=digest(file),seeds=seeds))
        audit=self.root/'audit.json';save(audit,dict(sources=sources))
        env=self.root/'environment.json';import sys,importlib.metadata
        save(env,dict(daemon_id='fixture',kernel='fixture',python=sys.version.split()[0],images={str(i):'fixture' for i in range(3)},
            packages={name:importlib.metadata.version(name) for name in ('docker','requests','numpy','pandas','scipy','matplotlib','openpyxl')}))
        self.plan=dict(protocol=dict(path=str(protocol_path),sha256=digest(protocol_path)),runtime_hashes=self.frozen,
            environment=dict(path=str(env),sha256=digest(env)),seed_audit=dict(path=str(audit),sha256=digest(audit)),
            entries=entries,results_root=str(self.root/'result'))
        self.plan_path=self.root/'plan.json';save(self.plan_path,self.plan)
        self.backend=FixtureBackend(self.root);self.campaign=Campaign(self.plan_path,digest(self.plan_path),self.backend)

    def run_phase(self,phase):
        index=p.PARTITIONS.index(phase);cps=self.campaign.checkpoints()
        token=None if not index else cps[p.PARTITIONS[index-1]]['manifest_sha256']
        return self.campaign.run_partition(phase,phase,token)

    def test_readiness_creates_directory_before_observation(self):
        from experiments.scientific_operations import readiness
        from simulator.exploratory_operations import Policy
        directory=self.root/'missing/readiness'
        def ready(op, client):
            import shutil
            self.assertGreater(shutil.disk_usage(op.directory).total,0)
            op.report['readiness']={'verified':True}
        with patch('experiments.scientific_operations.policy',return_value=Policy()), patch('simulator.exploratory_operations.Operations.ready',ready):
            self.assertTrue(readiness(None,directory,{})['verified'])

    def test_preflight_restart_preserves_old_and_orphan_evidence(self):
        entry=self.plan['entries'][0]
        with self.campaign.locked():pass
        directory=self.campaign.root/'collection'/entry['id']/'attempt-1'
        old=directory/'preflights/pf-0001/preparation.json'
        save(old,dict(started_epoch=time.time()-3600))
        orphan=directory/'preflights/pf-0002';orphan.mkdir()
        before=old.read_bytes()
        with self.campaign.locked(), patch.object(self.backend,'preflight',return_value={'ready':False}) as preflight:
            with self.assertRaisesRegex(Halt,'no attempt consumed'):self.campaign.collect_slot(entry)
        self.assertEqual(preflight.call_args.args[1].name,'pf-0003')
        self.assertEqual(old.read_bytes(),before)
        self.assertTrue(orphan.exists())
        self.assertFalse((directory/'attempt.json').exists())
        self.assertEqual(self.campaign.status()['consumed_attempts'],0)
        self.assertEqual(self.backend.calls,[])
        with self.campaign.locked(), patch.object(self.backend,'collect',side_effect=RuntimeError('offline stop before collection')):
            with self.assertRaisesRegex(RuntimeError,'offline stop'):self.campaign.collect_slot(entry)
        self.assertEqual(old.read_bytes(),before)
        self.assertEqual(self.campaign.status()['consumed_attempts'],1)
        claim=read_json(directory/'attempt.json')
        self.assertIn('pf-0004',claim['preflight_path'])

    def test_preflight_current_window_still_bounded(self):
        entry=self.plan['entries'][0]
        def slow(entry,directory):
            clock.return_value+=601
            return {'ready':True}
        with self.campaign.locked(), patch('experiments.scientific_campaign.time.time',return_value=1000) as clock, patch.object(self.backend,'preflight',side_effect=slow):
            with self.assertRaisesRegex(Halt,'allowance exhausted'):self.campaign.collect_slot(entry)
        self.assertEqual(self.backend.calls,[])
        self.assertEqual(self.campaign.status()['consumed_attempts'],0)

    def test_full_partition_pipeline_replay_misses_ICs_and_idempotent_resume(self):
        self.backend.tail=True
        for phase in p.PARTITIONS[:3]:
            with patch.object(evaluation,'load_truth',side_effect=AssertionError('No truth before TEST')):self.run_phase(phase)
        cal=open_artifact(self.campaign.checkpoints()['CAL_A']).read()['artifacts']['request_starts']
        self.assertEqual(engine.load_calibration(cal).reference,cal)
        candidate=open_artifact(cal).read()['candidates'][0]['trajectory']
        csv_path=Path(candidate['path'])/'transitions.csv';original=csv_path.read_bytes()
        csv_path.write_bytes(original+b'corrupt\n')
        with self.assertRaises(ContractError):engine.load_calibration(cal,replay=False)
        csv_path.write_bytes(original)
        self.run_phase('TEST')
        self.assertEqual(len(self.backend.calls),56)
        cp=self.run_phase('TEST');self.assertEqual(len(self.backend.calls),56)
        summary=open_artifact(cp.read()['artifacts']['summary']).read('scientific-summary')
        self.assertEqual(len(summary['results']),60)
        # Compare numerical results and output keys against the pre-parameterization evaluator.
        import subprocess
        namespace=dict(evaluation.__dict__)
        previous=subprocess.check_output(['git','show','HEAD:analysis/detection/scientific/evaluation.py'],text=True)
        exec(compile(previous,'previous-evaluation','exec'),namespace)
        old=namespace['aggregate']([open_artifact(ref) for ref in summary['evaluations']],self.root/'equivalence-summary',self.campaign.authority).read()
        for key in ('results','paired','scenario_detection_contrasts','operational','missing_runs','ci'):
            self.assertEqual(summary[key],old[key],key)
        self.assertIn('paired_E16_minus_M16',summary['operational'])

        self.assertIn('request_starts/E16/cusum-freeze-ewma',summary['paired'])
        result=summary['results']['request_starts/M16/zscore']
        self.assertEqual(result['misses'],12);self.assertIsNone(result['delay']['mean_seconds'])
        self.assertGreater(result['detection']['interval'][1],0)
        self.assertEqual(summary['results']['request_starts/E16/zscore']['detection']['n'],12)
        self.assertEqual(summary['operational']['by_scenario']['E16']['means']['exposure_seconds']['estimate'],66)
        self.assertEqual(summary['operational']['by_scenario']['E16']['early_stop']['successes'],12)
        # Explicit technical attrition retains other conditions and aligns by block.
        all_evals=[open_artifact(ref) for ref in summary['evaluations']]
        omitted=next(e for e in self.plan['entries'] if e['scenario']=='E16')
        remaining=[a for a in all_evals if a.read()['entry']['id']!=omitted['id']]
        failure_path=self.root/'diagnosed-failure.json';cleanup_path=self.root/'diagnosed-cleanup.json'
        save(failure_path,dict(entry_id=omitted['id'],code='CAPTURE_LOSS',authority=self.campaign.authority))
        save(cleanup_path,dict(verified=True))
        attr={omitted['id']:dict(failure_path=str(failure_path),failure_sha256=digest(failure_path),cleanup_path=str(cleanup_path),cleanup_sha256=digest(cleanup_path))}
        with self.assertRaisesRegex(ContractError,'explicit technical attrition'):
            evaluation.aggregate(remaining,self.root/'unexplained-partial',self.campaign.authority)
        partial=evaluation.aggregate(remaining,self.root/'partial-summary',self.campaign.authority,attr).read()
        self.assertEqual(partial['scenario_detection_contrasts']['request_starts/zscore/E16-M16']['n'],11)
        self.assertEqual(len(partial['operational']['paired_blocks']),11)
        self.assertEqual(partial['results']['request_starts/M16/zscore']['n_runs'],12)
        self.assertEqual(partial['missing_runs'],[omitted['id']])
        self.assertEqual(self.campaign.checkpoints()['TEST'],cp.reference)
        run_ref=cp.read()['artifacts']['request_starts'][1]
        doc=engine.validate_run(open_artifact(run_ref));self.assertEqual(doc['source']['partition'],'TEST')
        self.assertEqual(len(doc['methods']['zscore']),391)
        entry=next(e for e in self.plan['entries'] if e['id']==doc['source']['entry_id'])
        receipt=self.campaign.receipt_document(self.campaign.accepted()[entry['id']]);wrong_receipt={**receipt,'run_id':'other-run'}
        with self.assertRaisesRegex(ContractError,'Evaluation source differs'):
            evaluation.evaluate(entry,wrong_receipt,open_artifact(run_ref),self.root/'bad-evaluation',self.campaign.authority)
        changed=deepcopy(doc);changed['methods']['cusum-freeze'][150]['posterior_state']='100'
        bad=engine.artifact(self.root/'bad-run','scientific-run',{k:v for k,v in changed.items() if k not in ('kind','schema_version','outputs')})
        with self.assertRaisesRegex(ContractError,'trajectory'):engine.validate_run(bad)

    def test_CAL_B_rejection_blocks_TEST_and_does_not_retune(self):
        self.backend.bad_b=True
        self.run_phase('BASELINE');self.run_phase('CAL_A')
        calibration=self.root/'result/analysis/request_starts/calibration/manifest.json';before=digest(calibration)
        with self.assertRaisesRegex(Halt,'CAL-B'):self.run_phase('CAL_B')
        self.assertEqual(digest(calibration),before)
        with self.assertRaises(Halt):self.campaign.run_partition('TEST','TEST','wrong')
        self.assertFalse(any(self.plan['entries'][i]['partition']=='TEST' for i in range(len(self.backend.calls))))
        with self.assertRaises(Halt):self.campaign.authorize_replacement(digest(calibration))

    def test_technical_replacement_consumed_once_and_same_seed(self):
        entry=self.plan['entries'][0];self.backend.fail_once=entry['id']
        with self.assertRaisesRegex(Halt,'Collection stopped'):self.run_phase('BASELINE')
        with self.assertRaises(Halt):self.run_phase('BASELINE')
        self.assertEqual(len(self.backend.calls),1)
        failure=self.root/'result/collection'/entry['id']/'attempt-1/failure.json'
        token=digest(failure);self.campaign.authorize_replacement(token)
        with self.assertRaises(Halt):self.campaign.authorize_replacement(token)
        self.run_phase('BASELINE');self.assertEqual(len(self.backend.calls),5)
        claims=[read_json(path) for path in (self.root/'result/collection'/entry['id']).glob('*/attempt.json')]
        self.assertEqual(len(claims),2);self.assertEqual(claims[0]['entry'],claims[1]['entry'])
        self.assertEqual(digest(failure),token)

    def test_resume_recovers_completed_collection_without_repeating_experiment(self):
        entry=self.plan['entries'][0];self.backend.crash=entry['id']
        with self.assertRaisesRegex(RuntimeError,'controller crash'):self.run_phase('BASELINE')
        self.assertEqual(len(self.backend.calls),1)
        self.run_phase('BASELINE');self.assertEqual(len(self.backend.calls),4)

    def test_no_eligible_candidate_is_persisted_and_stops_chain(self):
        self.run_phase('BASELINE')
        with patch.object(engine,'eligible',return_value=False):
            with self.assertRaisesRegex(Halt,'no eligible'):self.run_phase('CAL_A')
        doc=read_json(self.root/'result/analysis/request_starts/calibration/manifest.json')
        self.assertFalse(doc['eligible']);self.assertIsNone(doc['thresholds']['cusum-freeze'])
        self.assertEqual(len(doc['candidates']),11)
        calls=len(self.backend.calls)
        with self.assertRaisesRegex(Halt,'already rejected'):self.run_phase('CAL_A')
        self.assertEqual(len(self.backend.calls),calls)
        with self.assertRaises(Halt):self.campaign.run_partition('CAL_B','CAL_B','absent')

    def test_global_two_technical_replacements_and_indeterminate_guard(self):
        entries=self.plan['entries'][:3];self.backend.fail_once={e['id'] for e in entries}
        for i,entry in enumerate(entries):
            with self.assertRaises(Halt):self.run_phase('BASELINE')
            path=self.root/'result/collection'/entry['id']/'attempt-1/failure.json'
            if i<2:self.campaign.authorize_replacement(digest(path))
            else:
                with self.assertRaisesRegex(Halt,'budget'):self.campaign.authorize_replacement(digest(path))
        self.assertEqual(len([e for e,h in self.campaign.events() if e['kind']=='REPLACEMENT_APPROVED']),2)
        self.assertFalse((self.root/'result/collection'/entries[-1]['id']/'attempt-2').exists())

    def test_diagnosed_TEST_attrition_is_explicit_and_not_a_replacement(self):
        entry=next(e for e in self.plan['entries'] if e['partition']=='TEST')
        self.backend.fail_once=entry['id']
        with self.assertRaises(Halt):
            with self.campaign.locked():self.campaign.collect_slot(entry)
        directory=self.root/'result/collection'/entry['id']/'attempt-1'
        failure=directory/'failure.json';h=digest(failure)
        with self.assertRaisesRegex(Halt,'Cleanup'):self.campaign.record_attrition(h)
        save(directory/'cleanup.json',dict(verified=True))
        self.campaign.record_attrition(h)
        self.assertIn(entry['id'],self.campaign.technical_attrition())
        with self.assertRaises(Halt):self.campaign.authorize_replacement(h)
        self.assertEqual(len(self.backend.calls),1)

    def test_other_rate_spec_is_hash_bound_and_control_real_format(self):
        other=deepcopy(read_json(p.PROTOCOL_PATH));other['specification']['scenario_parameters']['E16']['rate']=7
        path=self.root/'other-spec.json';save(path,other)
        self.assertEqual(p.load_spec(path,digest(path))['scenario_parameters']['E16']['rate'],7)
        import os,subprocess,sys
        selected=subprocess.check_output([sys.executable,'-B','-c',"from analysis.detection.scientific.protocol import SPEC,expected_slots; print(SPEC['scenario_parameters']['E16']['rate'],len(expected_slots()))"],text=True,env={**os.environ,'SCIENTIFIC_SPEC_PATH':str(path),'SCIENTIFIC_SPEC_SHA256':digest(path)})
        self.assertEqual(selected.strip(),'7 56')

        with self.assertRaises(ContractError):p.load_spec(path,'0'*64)
        self.assertEqual(p.SPEC['scenario_parameters']['E16']['rate'],16)
        with patch.dict(p.SPEC,dict(scenarios=['B','M7','E7'],control_scenario='B',scenario_contrasts=[['E7','M7']])):
            docs=[dict(feature=['service','request_starts'],entry=dict(id=name,scenario=name,block=1),operational=dict(early_stop=False,scalars={'exposure_seconds':value})) for name,value in [('E7',7),('M7',9)]]
            result=evaluation.impact_aggregate(docs)
            self.assertIn('paired_E7_minus_M7',result);self.assertNotIn('paired_E16_minus_M16',result)
            self.assertEqual(result['paired_E7_minus_M7']['exposure_seconds']['estimate'],-2)

        # A second explicit authority accepts7 RPS; the current authority still rejects it.
        alternate=deepcopy(self.plan)
        for e in alternate['entries']:
            if e['scenario']=='E16':
                cfg=read_json(e['config']);cfg['attack']['rate']=7
                Path(e['config']).write_text(encoded(cfg));e['config_sha256']=digest(e['config'])
        alt_path=self.root/'alternate-plan.json';save(alt_path,alternate)
        with self.assertRaises(ContractError):p.load_plan(alt_path,digest(alt_path))
        protocol_path=Path(self.plan['protocol']['path']);before=protocol_path.read_text()
        protocol_path.write_text(encoded(other));alternate['protocol']['sha256']=digest(protocol_path)
        audit_path=Path(alternate['seed_audit']['path']);audit=read_json(audit_path);old_audit=audit_path.read_text()
        for item in audit['sources']:item['sha256']=digest(item['path'])
        audit_path.write_text(encoded(audit));alternate['seed_audit']['sha256']=digest(audit_path)
        alt_path.write_text(encoded(alternate))
        with patch.dict(p.SPEC,other['specification'],clear=True):
            self.assertEqual(len(p.load_plan(alt_path,digest(alt_path))['entries']),56)
        protocol_path.write_text(before);audit_path.write_text(old_audit)
        for e in self.plan['entries']:
            if e['scenario']=='E16':
                cfg=read_json(e['config']);cfg['attack']['rate']=16;Path(e['config']).write_text(encoded(cfg))
        entry=next(e for e in self.plan['entries'] if e['partition']=='TEST' and e['scenario']=='C16')
        from tests.test_development_d3 import fixture
        from simulator.experiment_config import ExperimentConfig
        from experiments.export_dataset import export_run
        directory=self.root/'real-control';directory.mkdir();raw=directory/'raw'
        cfg=ExperimentConfig.load(entry['config'])
        with patch('tests.test_development_d3.ExperimentConfig.load',return_value=cfg):fixture(raw,'C')
        inventory=read_json(raw/'source_inventory.json')
        tick=dict(run_id=inventory[0]['run_id'],journal_sequences={e['source_id']:0 for e in inventory},collection_samples={'v':dict(read='fixture',received_seconds=1)},actionable=True)
        from experiments.stress_observer import Observer
        tick.update(Observer().evaluate([],1,1))
        (raw/'source_artifacts/stress_observer.jsonl').write_text(json.dumps(tick)+'\n')
        export_run(raw,directory/'dataset')
        save(directory/'execution.json',dict(returncode=0));save(directory/'cleanup.json',dict(verified=True,observed_epoch=0))
        receipt=DockerBackend(self.plan).recover(entry,directory)
        truth=data.load_truth(entry,receipt);self.assertEqual(truth['events'],[])
        metrics=evaluation.metrics([dict(window_start_seconds=30,window_end_seconds=31,available_at_seconds=31,decision=False)],truth)
        self.assertIsNone(metrics['event_detected']);self.assertEqual(metrics['fpr'],0)
        self.assertIsNone(receipt['operational']['exposure_seconds'])
        self.assertEqual(DockerBackend(self.plan).recover(entry,directory),receipt)
        for part in p.PARTITIONS[:3]:self.run_phase(part)
        cps=self.campaign.checkpoints()
        refs={part:open_artifact(cps[part]).read()['artifacts']['request_starts'] for part in p.PARTITIONS[:3]}
        source=data.load_source(entry,receipt,'service','request_starts',authority=self.campaign.authority,test_release=cps['CAL_B'])
        run=engine.process(source,open_artifact(refs['BASELINE']),open_artifact(refs['CAL_A']),self.root/'real-control-score',self.campaign.authority,open_artifact(refs['CAL_B']))
        evaluated=evaluation.evaluate(entry,receipt,run,self.root/'real-control-evaluation',self.campaign.authority).read()
        for result in evaluated['results'].values():
            self.assertIsNone(result['event_detected']);self.assertIsNone(result['observed_delay_seconds'])
        self.assertEqual(evaluated['operational']['run_id'],receipt['run_id'])


    def test_clock_handoff_specific_replacement_and_resume(self):
        entry=self.plan['entries'][0];self.backend.fail_once=entry['id']
        with self.assertRaises(Halt):
            with self.campaign.locked():self.campaign.collect_slot(entry)
        oldroot=self.root/'result';directory=oldroot/'collection'/entry['id']/'attempt-1'
        failure_path=directory/'failure.json';failure=read_json(failure_path);failure['code']='IDENTITY_JOURNAL_MISMATCH';failure_path.write_text(encoded(failure))
        journal=oldroot/'journal/000002.json';event=read_json(journal);event['payload']['failure_sha256']=digest(failure_path);journal.write_text(encoded(event))
        save(directory/'cleanup.json',dict(verified=True));save(directory/'execution.json',dict(returncode=1))
        save(directory/'raw/run_status.json',dict(status='incomplete',errors=['source monotonic clock is not demonstrably comparable']))
        save(directory/'raw/source_inventory.json',[dict(run_id=None)])
        diagnosis=self.root/'diagnosis.json';save(diagnosis,dict(diagnostic_reclassification='PRE_RELEASE_CLOCK_FAILURE',original_failure_sha256=digest(failure_path)))
        h=dict(old_plan=dict(path=str(self.plan_path),sha256=digest(self.plan_path)),old_root=str(oldroot),entry_id=entry['id'],original_consumed_attempts=1,original_approved_replacements=0,corrected_code='PRE_RELEASE_CLOCK_FAILURE',diagnosis=dict(path=str(diagnosis),sha256=digest(diagnosis)),evidence_hashes={str(x.resolve()):digest(x) for x in oldroot.rglob('*') if x.is_file()})
        for key,name in [('attempt_path','attempt.json'),('failure_path','failure.json'),('cleanup_path','cleanup.json'),('execution_path','execution.json'),('status_path','raw/run_status.json'),('inventory_path','raw/source_inventory.json')]:h[key]=str(directory/name)
        hp=self.root/'handoff.json';save(hp,h)
        successor={**self.plan,'handoff':dict(path=str(hp),sha256=digest(hp)),'results_root':str(self.root/'successor')}
        sp=self.root/'successor-plan.json';save(sp,successor)
        backend=FixtureBackend(self.root);campaign=Campaign(sp,digest(sp),backend)
        with self.assertRaisesRegex(Halt,'explicit approval'):campaign.run_partition('BASELINE','BASELINE')
        self.assertEqual(backend.calls,[])
        original=failure_path.read_bytes();failure_path.write_bytes(original+b' ')
        with self.assertRaises(ContractError):p.validate_handoff(successor)
        with self.assertRaises(ContractError):campaign.authorize_replacement(h['evidence_hashes'][str(failure_path)])
        self.assertFalse(any(e['kind']=='REPLACEMENT_APPROVED' for e,h in campaign.events()))
        failure_path.write_bytes(original)
        campaign.authorize_replacement(digest(failure_path))
        campaign.run_partition('BASELINE','BASELINE');self.assertEqual(len(backend.calls),4)
        self.assertTrue((self.root/'successor/collection'/entry['id']/'attempt-2/attempt.json').exists())
        self.assertFalse((self.root/'successor/collection'/entry['id']/'attempt-1').exists())
        campaign.run_partition('BASELINE','BASELINE');self.assertEqual(len(backend.calls),4)
        self.assertEqual(sum(e['kind']=='REPLACEMENT_APPROVED' for e,h in campaign.events()),1)

    def test_real_backend_offline_recovery_and_export_features(self):
        from tests.test_development_d3_origins import origins_fixture
        from experiments.export_dataset import export_run
        entry=deepcopy(next(e for e in self.plan['entries'] if e['scenario']=='E16'))
        cfg=read_json(entry['config']);directory=self.root/'real-format-fixture';directory.mkdir()
        origins_fixture(directory/'raw',dict(effective_configuration=cfg))
        raw=directory/'raw'
        # At16 RPS the final offensive response is still in flight at emission closure.
        attack_journal=raw/'source_artifacts/attack_1/output/journal.jsonl'
        attack_items=[json.loads(x) for x in attack_journal.read_text().splitlines()]
        for item in attack_items:
            if item['kind']=='emission_closed':item['payload'].update(status='emission_ended',drained_end_seconds=None)
        attack_journal.write_text(''.join(json.dumps(x)+'\n' for x in attack_items))
        local=raw/'source_artifacts/normal_1/output/local_requests.csv'
        last=read_csv(local)[-1];rid=last['request_id'];end=390.02
        updated=dict(end_elapsed_seconds=end,end_timestamp=1000+end,duration_ms=(end-float(last['elapsed_seconds']))*1000)
        for path in raw.rglob('*.csv'):
            if path.name not in ('request_log.csv','local_requests.csv','rtt_log.csv','local_rtt.csv'):continue
            with path.open(newline='') as stream:reader=csv.DictReader(stream);fields=reader.fieldnames;rows=list(reader)
            for row in rows:
                if row.get('request_id')!=rid:continue
                if 'duration_ms' in row:row.update(updated)
                else:row.update(timestamp=updated['end_timestamp'],elapsed_seconds=end,rtt=updated['duration_ms'])
            with path.open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
        journal=raw/'source_artifacts/normal_1/output/journal.jsonl';items=[json.loads(x) for x in journal.read_text().splitlines()]
        for item in items:
            if item['kind']=='request_finish' and item['payload']['request_id']==rid:item['payload'].update(updated)
        journal.write_text(''.join(json.dumps(x)+'\n' for x in items))
        inventory=read_json(raw/'source_inventory.json')
        tick=dict(run_id=inventory[0]['run_id'],journal_sequences={e['source_id']:0 for e in inventory},collection_samples={'v':dict(read='fixture',received_seconds=1)},actionable=True)
        from experiments.stress_observer import Observer
        tick.update(Observer().evaluate([],1,1))
        (raw/'source_artifacts/stress_observer.jsonl').write_text(json.dumps(tick)+'\n')
        export_run(directory/'raw',directory/'dataset')
        save(directory/'execution.json',dict(returncode=0));save(directory/'cleanup.json',dict(verified=True,observed_epoch=0))
        backend=DockerBackend(self.plan)
        receipt=backend.recover(entry,directory)
        self.assertTrue(receipt['technical_valid']);data.verify_receipt(receipt)
        self.assertEqual(read_json(Path(receipt['features'])/'feature_manifest.json')['window']['windows'],391)
        self.assertEqual(backend.recover(entry,directory),receipt)

    def test_secondary_rejection_is_unassessed_without_feature_selection(self):
        self.backend.secondary_constant=True
        for partition in p.PARTITIONS[:3]:self.run_phase(partition)
        cps=self.campaign.checkpoints();baseline_cp=open_artifact(cps['BASELINE']).read()
        cal_cp=open_artifact(cps['CAL_A']).read();ver_cp=open_artifact(cps['CAL_B']).read()
        self.assertFalse(open_artifact(ver_cp['artifacts']['mean_duration_ms']).read()['approved'])
        self.assertTrue(open_artifact(ver_cp['artifacts']['request_starts']).read()['approved'])
        entry=self.plan['entries'][20];directory=self.root/'secondary-test-fixture';directory.mkdir()
        receipt=self.backend.fixture(entry,directory)
        source=data.load_source(entry,receipt,'service','mean_duration_ms',authority=self.campaign.authority,test_release=cps['CAL_B'])
        run=engine.process(source,open_artifact(baseline_cp['artifacts']['mean_duration_ms']),
            open_artifact(cal_cp['artifacts']['mean_duration_ms']),self.root/'secondary-run',self.campaign.authority,
            open_artifact(ver_cp['artifacts']['mean_duration_ms']))
        result=evaluation.evaluate(entry,receipt,run,self.root/'secondary-evaluation',self.campaign.authority).read()
        for row in result['results'].values():
            self.assertFalse(row['scientifically_evaluated']);self.assertIsNone(row['event_detected'])

    def test_unknown_consumed_attempt_never_repeats_or_gets_replacement(self):
        entry=self.plan['entries'][0]
        def crash(*args,**kwargs):
            self.backend.calls.append((entry['id'],'crash'));raise RuntimeError('unknown execution state')
        with patch.object(self.backend,'collect',side_effect=crash):
            with self.assertRaises(RuntimeError):self.run_phase('BASELINE')
        with self.assertRaisesRegex(Halt,'Collection stopped'):self.run_phase('BASELINE')
        self.assertEqual(len(self.backend.calls),1)
        failure=self.root/'result/collection'/entry['id']/'attempt-1/failure.json'
        self.assertEqual(read_json(failure)['code'],'INDETERMINATE_ATTEMPT')
        with self.assertRaisesRegex(Halt,'eligible'):self.campaign.authorize_replacement(digest(failure))

    def test_order_roles_seed_overlap_and_TEST_source_lock(self):
        self.assertEqual([row for row in p.SPEC['test_order']],self.plan_order())
        with self.assertRaises(Halt):self.campaign.run_partition('CAL_A','CAL_A')
        with self.assertRaises(Halt):self.campaign.run_partition('BASELINE','TEST')
        entry=self.plan['entries'][-1];directory=self.root/'external-fixture';directory.mkdir()
        receipt=self.backend.fixture(entry,directory)
        with self.assertRaisesRegex(ContractError,'TEST source locked'):
            data.load_source(entry,receipt,'service','request_starts',authority=self.campaign.authority)
        bad=deepcopy(self.plan);bad['entries'][-1]['seed']=bad['entries'][0]['seed']
        path=self.root/'badplan.json';save(path,bad)
        with self.assertRaises(ContractError):Campaign(path,digest(path),self.backend)

    def plan_order(self):
        return [[e['scenario'] for e in self.plan['entries'] if e['partition']=='TEST' and e['block']==i] for i in range(1,13)]

    def test_closed_numerical_edges_balanced_order_and_CI_reproducibility(self):
        from collections import Counter
        support=[dict(fpr='0.01',available_fraction='0.95') for i in range(12)]
        self.assertTrue(engine.eligible(support,'0.01','0.05'))
        bad=deepcopy(support);bad[0]['available_fraction']='0.949999'
        self.assertFalse(engine.eligible(bad,'0.01','0.05'))
        self.assertFalse(engine.eligible([dict(fpr='0.010001',available_fraction='1')]*12,'0.01','0.05'))
        self.assertTrue(engine.eligible([dict(fpr='0.02',available_fraction='0.95')]*16,'0.02','0.05'))
        self.assertFalse(engine.eligible([dict(fpr='0.020001',available_fraction='1')]*16,'0.02','0.05'))
        bad=[dict(fpr='0',available_fraction='1') for i in range(16)];bad[0]['fpr']='0.050001'
        self.assertFalse(engine.eligible(bad,'0.02','0.05'))
        pairs=Counter(pair for row in p.TEST_ORDER for pair in zip(row,row[1:]))
        self.assertEqual(len(pairs),6);self.assertEqual(set(pairs.values()),{4})
        for position in range(3):self.assertEqual(set(Counter(row[position] for row in p.TEST_ORDER).values()),{4})
        values=[i/16 for i in range(16)]
        self.assertEqual(statistics.mean_ci(values),statistics.mean_ci(values))
        self.assertAlmostEqual(statistics.proportion_ci(16,16)['interval'][0],.7940927857921772)

    def test_controller_lock_and_immutable_consumed_attempt(self):
        with self.campaign.locked():
            other=Campaign(self.plan_path,digest(self.plan_path),self.backend)
            with self.assertRaisesRegex(Halt,'lock'):
                with other.locked():pass
        self.run_phase('BASELINE')
        intent=next((self.root/'result/collection').glob('*/attempt-1/attempt.json'))
        value=read_json(intent)
        with self.assertRaises(FileExistsError):save(intent,value)
        value['attempt_number']=99;intent.write_text(encoded(value))
        with self.assertRaisesRegex(ContractError,'attempt changed'):self.campaign.checkpoints()

    def test_deadline_and_degenerate_CIs(self):
        truth=dict(events=[dict(actual_start_seconds='150',actual_end_seconds='270')])
        rows=[dict(window_start_seconds='269',window_end_seconds='270',available_at_seconds='270.001',decision=True)]
        late=evaluation.metrics(rows,truth);self.assertFalse(late['event_detected']);self.assertIsNone(late['observed_delay_seconds'])
        rows[0]['available_at_seconds']='270';on_time=evaluation.metrics(rows,truth)
        self.assertTrue(on_time['event_detected']);self.assertEqual(on_time['observed_delay_seconds'],120)
        self.assertEqual(late['tp'],1)  # window TP can coexist with an event deadline miss
        rows[0]['available_at_seconds']='269.9'
        with self.assertRaises(ContractError):evaluation.metrics(rows,truth)
        early=dict(events=[dict(actual_start_seconds='150',actual_end_seconds='150.5')])
        late=[dict(window_start_seconds='150',window_end_seconds='151',available_at_seconds='151',decision=True)]
        missed=evaluation.metrics(late,early)
        self.assertFalse(missed['event_detected']);self.assertIsNone(missed['observed_delay_seconds'])
        self.assertEqual(missed['restricted_undetected_fraction'],1)
        self.assertIsNone(statistics.unbounded_mean_ci([2,2,2])['interval'])
        ci=statistics.mean_ci([0]*16);self.assertEqual(ci['method'],'Hoeffding_degenerate');self.assertGreater(ci['interval'][1],0)
        self.assertIsNone(statistics.delay_summary([])['mean_seconds'])
        paired=statistics.paired_detection_ci([True]*16,[True]*16)
        self.assertLess(paired['interval'][0],0);self.assertGreater(paired['interval'][1],0)


if __name__=='__main__':unittest.main()
