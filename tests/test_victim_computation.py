import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, Future
from unittest.mock import MagicMock, patch
from simulator.app import simple_server as server
from simulator.diagnostics import DiagnosticWriter, computational_state
from simulator.ground_truth import GroundTruth
from simulator.request_logger import RequestLogger

class ComputationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'events.jsonl'
        self.writer=DiagnosticWriter(self.path)
        self.observer=server.ComputationObservation(self.writer)
        self.addCleanup(self.writer.close)
    def identity(self, key='a', cls='attack'):
        return dict(operation_id=key,run_id='run',request_id='req_'+key,source_id='src',
                    event_id='event' if cls=='attack' else None,traffic_class=cls,endpoint='/medium')
    def rows(self):
        self.writer.close()
        return [json.loads(x) for x in self.path.read_text().splitlines()]
    def wait_events(self, n):
        deadline=time.monotonic()+2
        while len(self.observer.seen)<n and time.monotonic()<deadline: time.sleep(.005)
        self.assertEqual(len(self.observer.seen),n)
    def event(self, kind, key):
        server._worker_instrumentation(*self.observer.initializer_args())
        server._worker_event(kind,key)
    def test_real_pool_lifecycle_and_two_operations(self):
        with ProcessPoolExecutor(2,initializer=server._worker_instrumentation,
                                 initargs=self.observer.initializer_args()) as pool:
            futures=[self.observer.submit(pool,1000,self.identity(k,c)) for k,c in [('a','attack'),('b','benign')]]
            for f in futures: self.assertGreaterEqual(f.result(3)['work_cpu_seconds'],0)
        rows=self.rows()
        self.assertEqual(len([e for e in rows if e['kind']=='work_completed']),2)
        self.assertTrue(rows[-1]['observation_complete'])
        self.assertFalse(rows[-1]['pending'])
        self.assertEqual([e['sequence'] for e in rows],list(range(1,len(rows)+1)))
    def test_waiting_running_and_unobserved_drain(self):
        pool=MagicMock(); pool.submit.return_value=Future()
        self.observer.submit(pool,1,self.identity())
        self.observer.submit(pool,1,self.identity('b','benign'))
        self.event('work_started','a'); self.wait_events(1)
        rows=self.rows(); cut=rows[-1]
        self.assertTrue(cut['observation_complete'])
        self.assertEqual(cut['counts']['attack']['running'],1)
        self.assertEqual(cut['counts']['benign']['waiting'],1)
        state=computational_state(rows,float('inf'),observation_complete=True,ingress_closed=True)
        self.assertEqual(state['drainage'],'not_observed')
    def test_residual_at_E_and_legitimate_continues(self):
        pool=MagicMock(); pool.submit.return_value=Future()
        self.observer.submit(pool,1,self.identity())
        self.observer.submit(pool,1,self.identity('b','benign'))
        self.event('work_started','a'); self.wait_events(1)
        E=time.monotonic()
        self.event('work_completed','a'); self.wait_events(2)
        rows=self.rows()
        before=computational_state(rows,E,observation_complete=True,ingress_closed=True)
        after=computational_state(rows,float('inf'),observation_complete=True,ingress_closed=True)
        self.assertEqual(before['counts']['attack']['running'],1)
        self.assertEqual(after['drainage'],'drained_observed')
        self.assertEqual(after['counts']['benign']['pending'],1)
        self.assertEqual(computational_state(rows,float('inf'),observation_complete=True)['drainage'],'not_observed')
    def test_submission_failure(self):
        pool=MagicMock(); pool.submit.side_effect=RuntimeError('closed')
        with self.assertRaises(RuntimeError): self.observer.submit(pool,1,self.identity())
        rows=self.rows()
        self.assertEqual(rows[-1]['counts']['attack']['submission_failed'],1)
        self.assertFalse(rows[-1]['pending'])
    def test_execution_failure(self):
        # Real wrapper preserves failure event independent of future/HTTP result.
        pool=MagicMock(); pool.submit.return_value=Future()
        self.observer.submit(pool,1,self.identity())
        server._worker_instrumentation(*self.observer.initializer_args())
        with patch.object(server,'_burn_cpu',side_effect=ValueError('work')):
            with self.assertRaises(ValueError): server._observed_work(1,'a')
        rows=self.rows()
        self.assertEqual(rows[-1]['counts']['attack']['failed'],1)
    def test_missing_event_and_duplicate_invalidate_observation(self):
        self.observer.sequence.value=1
        rows=self.rows()
        self.assertFalse(rows[-1]['observation_complete'])
        self.assertEqual(computational_state(rows,1,observation_complete=False)['drainage'],'observation_incomplete')
        e=dict(kind='work_submitted',at=0,operation_id='a',traffic_class='attack')
        self.assertTrue(computational_state([e,e],1,observation_complete=True)['errors'])
    def test_identity_transport_same_endpoint_and_unknown(self):
        gt=GroundTruth('test',Path(self.tmp.name)/'gt.csv')
        logger=RequestLogger(gt,Path(self.tmp.name)/'req.csv',source_id='normal_1')
        for cls in ('benign','attack','unknown'):
            attempt=dict(run_id='run',request_id='request',event_id='event' if cls=='attack' else None,traffic_class=cls)
            headers=logger.instrumentation_headers(attempt)
            handler=server.SimpleAppHandler.__new__(server.SimpleAppHandler)
            handler.headers=headers; handler.path='/medium'; handler.wfile=io.BytesIO()
            handler.send_response=MagicMock(); handler.send_header=MagicMock(); handler.end_headers=MagicMock()
            with patch.object(server,'_diagnostics',self.writer), patch.object(server,'_computation',None),patch.object(server,'_pool') as pool:
                pool.submit.return_value.result.return_value={}
                handler.do_GET()
        rows=self.rows(); starts=[r for r in rows if r['kind']=='handler_started']
        self.assertEqual([r['traffic_class'] for r in starts],['benign','attack','unknown'])
        self.assertTrue(all(r['request_id']=='request' and r['source_id']=='normal_1' for r in starts))
    def test_disconnect_after_computation_still_records_completion(self):
        handler=server.SimpleAppHandler.__new__(server.SimpleAppHandler)
        handler.path='/medium'; handler.headers={}; handler.wfile=MagicMock()
        handler.wfile.write.side_effect=BrokenPipeError('client timed out')
        handler.send_response=MagicMock(); handler.send_header=MagicMock(); handler.end_headers=MagicMock()
        with ProcessPoolExecutor(1,initializer=server._worker_instrumentation,initargs=self.observer.initializer_args()) as pool:
            with patch.object(server,'_pool',pool),patch.object(server,'_diagnostics',self.writer),patch.object(server,'_computation',self.observer):
                with self.assertRaises(BrokenPipeError): handler.do_GET()
        rows=self.rows()
        self.assertTrue(any(e['kind']=='work_completed' for e in rows))
        self.assertEqual(next(e for e in rows if e['kind']=='handler_finished')['error_type'],'BrokenPipeError')

    def test_drain_before_E_and_ipc_loss(self):
        events=[dict(kind=k,operation_id='a',traffic_class='attack',at=t)
                for k,t in [('work_submitted',1),('work_started',2),('work_completed',3)]]
        state=computational_state(events,4,observation_complete=True,ingress_closed=True)
        self.assertEqual(state['drainage'],'drained_observed')
        self.observer.losses.value=1
        rows=self.rows()
        self.assertFalse(rows[-1]['observation_complete'])
        summary=json.loads(self.path.with_suffix('.summary.json').read_text())
        self.assertFalse(summary['complete'])

    def test_declared_mechanism_and_absent_identity(self):
        gt=GroundTruth('test',Path(self.tmp.name)/'gt.csv')
        log=RequestLogger(gt,Path(self.tmp.name)/'req.csv',source_id='attack_1')
        for endpoint,mechanism in [('/medium','http_request_flooding'),('/expensive','computational_asymmetry')]:
            headers=log.instrumentation_headers(dict(run_id='run',request_id='r',event_id='e',traffic_class='attack',target_url='http://edos_service:80'+endpoint))
            self.assertEqual(headers['X-Edos-Attack-Mechanism'],mechanism)
        handler=server.SimpleAppHandler.__new__(server.SimpleAppHandler)
        handler.headers={}; handler.path='/medium'; handler.wfile=io.BytesIO()
        handler.send_response=MagicMock();handler.send_header=MagicMock();handler.end_headers=MagicMock()
        with patch.object(server,'_diagnostics',self.writer),patch.object(server,'_computation',None),patch.object(server,'_pool') as pool:
            pool.submit.return_value.result.return_value={}
            handler.do_GET()
        row=next(e for e in self.rows() if e['kind']=='handler_started')
        self.assertEqual(row['traffic_class'],'unknown')
        self.assertIsNone(row['request_id'])

    def test_client_timeout_while_worker_still_runs(self):
        import requests
        from concurrent.futures import ThreadPoolExecutor
        entered,release=threading.Event(),threading.Event()
        class QuietServer(server.ThreadingHTTPServer):
            def handle_error(self,*args): pass
        http=QuietServer(('127.0.0.1',0),server.SimpleAppHandler)
        thread=threading.Thread(target=http.serve_forever,daemon=True)
        def burn(units): entered.set(); release.wait(2)
        pool=ThreadPoolExecutor(1,initializer=server._worker_instrumentation,initargs=self.observer.initializer_args())
        try:
            with patch.object(server,'_pool',pool),patch.object(server,'_computation',self.observer),patch.object(server,'_diagnostics',self.writer),patch.object(server,'_burn_cpu',side_effect=burn):
                thread.start()
                with self.assertRaises(requests.exceptions.Timeout):
                    requests.get('http://127.0.0.1:'+str(http.server_port)+'/medium',timeout=.05,
                        headers={'X-Edos-Run-Id':'run','X-Edos-Request-Id':'r','X-Edos-Traffic-Class':'attack','X-Edos-Event-Id':'e'})
                self.assertTrue(entered.is_set())
                self.wait_events(1)
                self.assertTrue(any(op['state']=='running' for op in self.observer.operations.values()))
                release.set(); pool.shutdown(wait=True)
                self.wait_events(2)
                http.shutdown(); http.server_close()
        finally:
            release.set(); pool.shutdown(wait=True)
            http.server_close()
        rows=self.rows()
        self.assertTrue(any(e['kind']=='work_completed' and e['request_id']=='r' for e in rows))

    def test_export_preserves_lifecycle_and_hashes(self):
        from tests.test_dataset_export import DatasetExportTests
        from experiments.dataset_provenance import sha256_file
        fixture=DatasetExportTests(); fixture.setUp()
        self.addCleanup(fixture.temporary.cleanup)
        rows=self.rows()
        root=fixture.source/'diagnostics/victim'; root.mkdir(parents=True)
        original=self.path.read_bytes(); (root/'events.jsonl').write_bytes(original)
        (root/'events.summary.json').write_bytes(self.path.with_suffix('.summary.json').read_bytes())
        manifest=fixture.export()
        relative='evidence/other/diagnostics/victim/events.jsonl'
        entry=next(e for e in manifest['files'] if e['path']==relative)
        self.assertEqual((fixture.destination/relative).read_bytes(),original)
        self.assertEqual(entry['sha256'],sha256_file(root/'events.jsonl'))
