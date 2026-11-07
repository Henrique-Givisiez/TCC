"""Simulated I1.1 lifecycle; no live Docker, signals, HTTP or workloads."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from experiments.diagnostic_run import complete_procedure
from simulator.exploratory_operations import Operations
from tests.test_exploratory_operations import policy, IMAGE


class CertificationTests(unittest.TestCase):
    def fixture(self, root):
        op=Operations(policy(),{},root)
        op.report.update(cleanup_verified=True, post_cleanup_readiness={'verified':True})
        root.mkdir(exist_ok=True)
        (root/'run_status.json').write_text(json.dumps(dict(status='completed',end_reason='simulation_end',run_id='r',producers_drained=True,errors=[],capture_results={'pcap':{'accepted':True},'csv':{'accepted':True}})))
        for n in ['effective_config.json','run_provenance.json','source_inventory.json','request_log.csv','traffic_capture.csv','simulation_metrics.csv']:
            (root/n).write_text('[]' if n=='source_inventory.json' else '{}')
        dest=root/'dataset';dest.mkdir()
        return op,dest

    def test_success_then_previous_export_failure_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            op,d=self.fixture(Path(t))
            def export(): (d/'dataset_manifest.json').write_text('{"run_id":"r"}')
            complete_procedure(lambda:None,export,op,Path(t),d)
            self.assertTrue(op.report['progression_allowed'])
            self.assertEqual(op.report['execution']['status'],'completed')
            # A separate attempt, not editing a previous certificate.
            op2=Operations(policy(),{},t);op2.report.update(cleanup_verified=True,post_cleanup_readiness={'verified':True})
            with self.assertRaisesRegex(OSError,'export failed'):
                complete_procedure(lambda:None,MagicMock(side_effect=OSError('export failed')),op2,Path(t),d)
            self.assertFalse(op2.report['progression_allowed'])

    def test_execution_failure_preserved_when_export_also_fails(self):
        with tempfile.TemporaryDirectory() as t:
            op,d=self.fixture(Path(t))
            with self.assertRaisesRegex(RuntimeError,'original'):
                complete_procedure(MagicMock(side_effect=RuntimeError('original')),
                    MagicMock(side_effect=OSError('export')),op,Path(t),d)
            self.assertGreaterEqual(len(op.report['failures']),2)
            self.assertFalse(op.report['procedure_completed'])

    def test_missing_status_and_persistence_failure_fail_closed(self):
        with tempfile.TemporaryDirectory() as t:
            op,d=self.fixture(Path(t));(Path(t)/'run_status.json').unlink()
            with self.assertRaises(RuntimeError): complete_procedure(lambda:None,lambda:None,op,t,d)
            self.assertEqual(op.report['certification'],'blocked')
        with tempfile.TemporaryDirectory() as t:
            op,d=self.fixture(Path(t));(d/'dataset_manifest.json').write_text('{"run_id":"r"}')
            with patch.object(op,'persist',side_effect=OSError('disk')):
                with self.assertRaises(OSError):op.certify(d,[])
            self.assertFalse(op.report['progression_allowed'])

    def test_incomplete_runtime_but_physically_clean(self):
        with tempfile.TemporaryDirectory() as t:
            op,d=self.fixture(Path(t));(d/'dataset_manifest.json').write_text('{"run_id":"r"}')
            (Path(t)/'run_status.json').write_text('{"status":"incomplete","end_reason":"interrupted","run_id":"r"}')
            op.certify(d,[])
            self.assertTrue(op.report['cleanup_verified'])
            self.assertFalse(op.report['progression_allowed'])
            self.assertFalse(op.report['procedure_completed'])

    def test_cleanup_blocks_otherwise_completed(self):
        with tempfile.TemporaryDirectory() as t:
            op,d=self.fixture(Path(t));op.report['cleanup_verified']=False
            (d/'dataset_manifest.json').write_text('{"run_id":"r"}')
            op.certify(d,[]);self.assertFalse(op.report['progression_allowed'])

    def test_partial_arm_and_disarm_attempt_both_restorations(self):
        with tempfile.TemporaryDirectory() as t:
            op=Operations(policy(),{},t)
            with patch('signal.getitimer',return_value=(0.,0.)),patch('signal.getsignal',return_value='old'),patch('signal.signal') as sig,patch('signal.setitimer',side_effect=OSError('arm')):
                with self.assertRaises(OSError):op.arm()
                with self.assertRaises(RuntimeError):op.disarm()
                sig.assert_called_with(__import__('signal').SIGALRM,'old')
            with patch('signal.setitimer'),patch('signal.signal') as sig:
                op.disarm()
            self.assertFalse(op.timer_changed)

    def test_prearm_failure_does_not_touch_existing_timer(self):
        with tempfile.TemporaryDirectory() as t:
            op=Operations(policy(),{},t)
            with patch('signal.getitimer',return_value=(10.,0.)),patch('signal.signal') as sig,patch('signal.setitimer') as timer:
                with self.assertRaises(RuntimeError):op.arm()
                op.disarm();sig.assert_not_called();timer.assert_not_called()

    def test_historical_procedure_has_no_certificate(self):
        with tempfile.TemporaryDirectory() as t:
            run=MagicMock();export=MagicMock()
            complete_procedure(run,export,None,t,Path(t)/'data')
            run.assert_called_once();export.assert_not_called()

    def test_real_source_manager_registers_partial_sources_immediately(self):
        from simulator.source_manager import SourceManager
        from tests.test_exploratory_operations import cfg
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);client=MagicMock();network=MagicMock();network.name='n'
            client.images.get.return_value.id=IMAGE
            client.images.get.return_value.attrs={'RepoDigests':[]}
            containers=[]
            for i in range(2):
                c=MagicMock();c.id=str(i);c.name='source'+str(i)
                c.attrs={'Image':IMAGE,'Config':{'Hostname':'s'},'NetworkSettings':{'Networks':{'n':{'IPAddress':'1'}}}}
                containers.append(c)
            client.containers.run.side_effect=[*containers,RuntimeError('third source failed')]
            manager=SourceManager(client,network,root/'sources',root/'inventory.json',cfg(4,64,150))
            op=Operations(policy(),{'source':IMAGE},root/'op');manager.on_created=lambda c:op.own(c,'source')
            with self.assertRaisesRegex(RuntimeError,'third'):manager.start()
            self.assertEqual(set(op.owned),{'0','1'})
            self.assertEqual(manager.containers,containers)
            manager.remove()
            for c in containers:c.remove.assert_called_once_with(force=True)
            self.assertFalse(op.report['progression_allowed'])

    def test_runtime_setup_timer_failure_still_finishes_and_restores_docker(self):
        import sys
        import simulator
        from simulator import source_experiment as runtime, config
        from tests.test_exploratory_operations import cfg
        fake=MagicMock();fake.client.api.timeout=17
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);op=Operations(policy(),{},root)
            def setup_failure(_):
                (root/'diagnostics/victim/events.summary.json').write_text('{"complete":true}')
                raise RuntimeError('original setup')
            with patch.dict(sys.modules,{'simulator.docker_manager':fake}),patch.object(simulator,'docker_manager',fake,create=True),\
                 patch.object(config,'RUN_STATUS_FILE',str(root/'run_status.json')),\
                 patch.object(op,'ready',side_effect=setup_failure),patch.object(op,'arm'),\
                 patch.object(op,'disarm',side_effect=RuntimeError('secondary timer')),patch.object(op,'finish') as finish:
                with self.assertRaisesRegex(RuntimeError,'original setup'):
                    runtime.run(cfg(),operational=op)
            finish.assert_called_once()
            self.assertEqual(fake.client.api.timeout,17)
            status=json.loads((root/'run_status.json').read_text())
            self.assertEqual(status['status'],'incomplete')
            self.assertTrue(any('secondary timer' in e for e in status['errors']))
            self.assertFalse(op.report['progression_allowed'])

    def test_external_containers_categorized_never_removed(self):
        with tempfile.TemporaryDirectory() as t:
            op=Operations(policy(),{},t);client=MagicMock()
            client.containers.list.side_effect=[[MagicMock(id='external')],[],[],[]]
            client.networks.get.return_value.attrs={'Containers':{}}
            with patch('experiments.development_d1_ops.process_rows',return_value=[]),patch.object(op,'observe'):
                with self.assertRaises(RuntimeError):op.ready(client)
            self.assertEqual(op.report['readiness']['reasons'],['external_active_containers'])
            self.assertEqual(op.report['readiness']['active_external'],['external'])
            client.containers.get.assert_not_called()

    def test_runtime_arm_and_docker_restore_failures_are_retained(self):
        import sys
        import simulator
        from simulator import source_experiment as runtime, config
        from tests.test_exploratory_operations import cfg
        class API:
            def __init__(self):self.value=17;self.restoration_attempted=False
            @property
            def timeout(self):return self.value
            @timeout.setter
            def timeout(self,v):
                if v==17:
                    self.restoration_attempted=True
                    raise RuntimeError('restore refused')
                self.value=v
        fake=MagicMock();fake.client.api=API()
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);op=Operations(policy(),{},root)
            def arm_failure():
                (root/'diagnostics/victim/events.summary.json').write_text('{"complete":true}')
                raise RuntimeError('arm failed')
            with patch.dict(sys.modules,{'simulator.docker_manager':fake}),patch.object(simulator,'docker_manager',fake,create=True),\
                 patch.object(config,'RUN_STATUS_FILE',str(root/'run_status.json')),\
                 patch.object(op,'arm',side_effect=arm_failure),patch.object(op,'disarm') as disarm,patch.object(op,'finish') as finish:
                with self.assertRaisesRegex(RuntimeError,'arm failed'):runtime.run(cfg(),op)
            disarm.assert_called_once();finish.assert_called_once()
            self.assertTrue(fake.client.api.restoration_attempted)
            self.assertTrue(any('restore refused' in e for e in json.loads((root/'run_status.json').read_text())['errors']))

    def test_continuation_requires_final_certificate_and_status_binding(self):
        from simulator.exploratory_operations import verify_previous
        with tempfile.TemporaryDirectory() as t:
            op,d=self.fixture(Path(t));(d/'dataset_manifest.json').write_text('{"run_id":"r"}')
            op.persist()
            with self.assertRaises(RuntimeError):verify_previous(t)
            op.certify(d,[]);verify_previous(t)
            (Path(t)/'run_status.json').write_text('{}')
            with self.assertRaises(RuntimeError):verify_previous(t)

    def test_completed_with_unexpected_end_reason_is_blocked(self):
        with tempfile.TemporaryDirectory() as t:
            op,d=self.fixture(Path(t));(d/'dataset_manifest.json').write_text('{"run_id":"r"}')
            p=Path(t)/'run_status.json';status=json.loads(p.read_text());status['end_reason']='interrupted';p.write_text(json.dumps(status))
            op.certify(d,[])
            self.assertFalse(op.report['progression_allowed'])
