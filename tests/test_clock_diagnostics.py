import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from simulator.source_manager import clock_checks,validate_clocks,clock_metadata
from experiments.scientific_collection import DockerBackend,CollectionFailure

class ClockDiagnosticsTests(unittest.TestCase):
    def test_cross_namespace_requires_complete_zero_offset_proof(self):
        host=dict(namespace='host',thread_namespace='host',children_namespace='host',kernel='native',clock_source='clock_gettime(CLOCK_MONOTONIC)',timens_offsets='monotonic 0 0\nboottime 0 0\n')
        remote={**host,'namespace':'source','thread_namespace':'source','children_namespace':'source','init_namespace':'source','monotonic':20}
        self.assertTrue(clock_checks(host,remote,10,30)['comparable'])
        for change in [dict(timens_offsets='monotonic 1 0\nboottime 0 0'),dict(init_namespace='other'),dict(kernel='other'),dict(clock_source='unknown'),dict(timens_offsets=None),dict(monotonic=31)]:
            self.assertFalse(clock_checks(host,{**remote,**change},10,30)['comparable'],change)
        self.assertFalse(clock_checks(host,dict(namespace='different',monotonic=20),10,30)['comparable'])
    def test_failed_bracket_and_conditions_are_persisted(self):
        c=MagicMock();c.id='owned';c.exec_run.return_value=MagicMock(exit_code=0,output=json.dumps(dict(namespace=os.readlink('/proc/self/ns/time'),monotonic=40,epoch=1000)).encode())
        with tempfile.TemporaryDirectory() as t,patch('simulator.source_manager.time.monotonic',side_effect=[10,30]):
            path=Path(t)/'clock.json'
            with self.assertRaisesRegex(RuntimeError,'not demonstrably comparable'):validate_clocks([c],path)
            r=json.loads(path.read_text());s=r['sources'][0]['samples'][0]
            self.assertEqual((s['host_before'],s['host_after'],s['monotonic']),(10,30,40))
            self.assertFalse(s['checks']['remote_within_host_bracket']);self.assertIn('error',s);self.assertFalse(r['comparable'])
    def test_success_keeps_all_four_samples(self):
        host=clock_metadata();remote={**host,'monotonic':20,'epoch':1000}
        c=MagicMock();c.id='owned';c.exec_run.return_value=MagicMock(exit_code=0,output=json.dumps(remote).encode())
        with tempfile.TemporaryDirectory() as t,patch('simulator.source_manager.time.monotonic',side_effect=[10,30]*4):
            r=validate_clocks([c],Path(t)/'clock.json');self.assertTrue(r['comparable']);self.assertEqual(len(r['sources'][0]['samples']),4)
    def test_pre_release_classification_without_rewriting_history(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);(d/'raw/source_artifacts').mkdir(parents=True)
            for name,value in [('execution.json',dict(returncode=1)),('cleanup.json',dict(verified=True)),('raw/run_status.json',dict(status='incomplete',errors=['source monotonic clock is not demonstrably comparable'])),('raw/source_inventory.json',[dict(run_id=None)])]:
                (d/name).write_text(json.dumps(value))
            before={str(p):p.read_bytes() for p in d.rglob('*') if p.is_file()}
            with self.assertRaises(CollectionFailure) as cm:DockerBackend({}).recover({},d)
            self.assertEqual(cm.exception.code,'PRE_RELEASE_CLOCK_FAILURE')
            self.assertEqual(before,{str(p):p.read_bytes() for p in d.rglob('*') if p.is_file()})
            out=d/'raw/source_artifacts/normal_1/output';out.mkdir(parents=True);(out/'journal.jsonl').write_text('{}\n')
            with self.assertRaises(CollectionFailure) as cm:DockerBackend({}).recover({},d)
            self.assertNotEqual(cm.exception.code,'PRE_RELEASE_CLOCK_FAILURE')
if __name__=='__main__':unittest.main()
