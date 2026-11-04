import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch,MagicMock

from simulator.diagnostics import DiagnosticWriter,DiagnosticExecutor
from simulator.experiment_config import ExperimentConfig
from simulator.ground_truth import GroundTruth
from simulator.request_logger import RequestLogger,REQUEST_FIELDS
from simulator.app import simple_server as server
from experiments.summarize_diagnostics import stats,count_windows,summarize


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def writer(self,**kwargs):
        writer=DiagnosticWriter(self.root/'events.jsonl',**kwargs)
        self.addCleanup(writer.close)
        return writer

    def read(self):
        return [json.loads(s) for s in (self.root/'events.jsonl').read_text().splitlines()]

    def test_writer_drains_and_reports_clock(self):
        writer=self.writer();writer.emit('one',request_id='r');self.assertTrue(writer.close())
        summary=json.loads((self.root/'events.summary.json').read_text())
        self.assertTrue(summary['complete']);self.assertEqual(summary['written'],1)
        self.assertEqual(summary['clock']['unit'],'seconds')

    def test_bounded_writer_reports_drops_without_blocking(self):
        gate=threading.Event()
        class Paused(DiagnosticWriter):
            def _write(self):
                gate.wait(2);super()._write()
        writer=Paused(self.root/'events.jsonl',capacity=1)
        try:
            writer.emit('one');writer.emit('two');gate.set();writer.close()
            summary=json.loads((self.root/'events.summary.json').read_text())
            self.assertEqual(summary['dropped'],1);self.assertFalse(summary['complete'])
        finally:gate.set();writer.close()

    def test_output_failure_does_not_break_producer(self):
        (self.root/'events.jsonl').mkdir()
        writer=self.writer();writer.emit('one');writer.close()
        summary=json.loads((self.root/'events.summary.json').read_text())
        self.assertGreater(summary['write_errors'],0);self.assertFalse(summary['complete'])

    def test_executor_queue_cancellation_and_unique_ids(self):
        writer=self.writer();gate=threading.Event();entered=threading.Event()
        pool=ThreadPoolExecutor(1);executor=DiagnosticExecutor(pool,writer)
        def wait():entered.set();gate.wait(2)
        first=executor.submit(wait)
        try:
            self.assertTrue(entered.wait(1))
            second=executor.submit(lambda:None);self.assertTrue(second.cancel())
            third=executor.submit(lambda:3);gate.set()
            first.result(2);self.assertEqual(third.result(2),3)
            executor.shutdown(wait=True);writer.close()
            self.assertEqual(executor.counts,dict(submitted=3,task_started=2,task_finished=2,cancelled=1,rejected=0))
            events=self.read();ids=[e['attempt_id'] for e in events if e['kind']=='submitted']
            self.assertEqual(len(set(ids)),3)
            for ident in ids:
                own={e['kind']:e for e in events if e['attempt_id']==ident}
                if 'task_started' in own:
                    self.assertLessEqual(own['submitted']['at'],own['task_started']['at'])
                    self.assertLessEqual(own['task_started']['at'],own['task_finished']['at'])
        finally:gate.set();pool.shutdown(wait=True)

    def test_executor_rejection_and_exception_preserve_behavior(self):
        writer=self.writer();pool=ThreadPoolExecutor(1);executor=DiagnosticExecutor(pool,writer)
        def fail():raise ValueError('observed')
        with self.assertRaises(ValueError):executor.submit(fail).result(2)
        executor.shutdown(wait=True)
        with self.assertRaises(RuntimeError):executor.submit(lambda:None)
        writer.close()
        self.assertEqual(executor.counts['rejected'],1)
        self.assertTrue(any(e.get('error_type')=='ValueError' for e in self.read()))

    def test_planned_wait_is_real_relative_deadline(self):
        writer=self.writer();pool=ThreadPoolExecutor(1);executor=DiagnosticExecutor(pool,writer)
        began=time.monotonic()-.2;executor.plan_wait(began,.1)
        executor.submit(lambda:None).result(2);executor.shutdown();writer.close()
        events=self.read();planned=next(e for e in events if e['kind']=='planned')
        submitted=next(e for e in events if e['kind']=='submitted')
        self.assertEqual(planned['planned_at'],began+.1)
        self.assertEqual(planned['attempt_id'],submitted['attempt_id'])

    def test_http_times_and_scientific_schema_preserved(self):
        writer=self.writer();pool=ThreadPoolExecutor(1);executor=DiagnosticExecutor(pool,writer)
        gt=GroundTruth('test',self.root/'events.csv')
        logger=RequestLogger(gt,self.root/'requests.csv',source_id='normal_1');logger.diagnostics=executor
        def request():
            row=logger.begin('normal',0,'http://edos_service:80/light')
            logger.finish(row,error=TimeoutError())
        executor.submit(request).result(2);executor.shutdown();writer.close()
        with (self.root/'requests.csv').open() as stream:
            reader=csv.DictReader(stream);self.assertEqual(reader.fieldnames,REQUEST_FIELDS);row=next(reader)
        events={e['kind']:e for e in self.read()}
        self.assertEqual(events['http_started']['elapsed_seconds'],float(row['elapsed_seconds']))
        self.assertEqual(events['http_finished']['elapsed_seconds'],float(row['end_elapsed_seconds']))
        self.assertEqual(events['http_finished']['error_type'],'TimeoutError')
        self.assertEqual(events['http_started']['attempt_id'],events['submitted']['attempt_id'])

    def handler(self):
        h=server.SimpleAppHandler.__new__(server.SimpleAppHandler)
        h.path='/light';h.headers={'X-Edos-Request-Id':'existing'};h.wfile=io.BytesIO()
        h.send_response=MagicMock();h.send_header=MagicMock();h.end_headers=MagicMock()
        return h

    def test_handler_enabled_records_actual_worker_and_existing_id(self):
        writer=self.writer();h=self.handler();future=Future()
        future.set_result(server._timed_burn_cpu(0))
        # Worker timing generated during actual submit, rather than before handler.
        def submit(fn,work):
            f=Future();f.set_result(fn(0));return f
        with patch.object(server,'_diagnostics',writer),patch.object(server,'_pool') as pool:
            pool.submit.side_effect=submit;h.do_GET()
            pool.submit.assert_called_once_with(server._timed_burn_cpu,10000)
        writer.close();event=next(e for e in self.read() if e['kind']=='handler_finished')
        self.assertEqual(event['request_id'],'existing');self.assertEqual(event['http_status'],200)
        self.assertEqual(event['active_handlers_at_finish'],0)
        order=['handler_started_at','work_submitted_at','work_started_at','work_finished_at','work_result_observed_at','handler_finished_at']
        self.assertEqual([event[k] for k in order],sorted(event[k] for k in order))
        self.assertGreaterEqual(event['work_cpu_seconds'],0)

    def test_handler_failure_is_recorded_and_reraised(self):
        writer=self.writer();h=self.handler()
        with patch.object(server,'_diagnostics',writer),patch.object(server,'_pool') as pool:
            pool.submit.side_effect=RuntimeError('broken')
            with self.assertRaises(RuntimeError):h.do_GET()
        writer.close();end=next(e for e in self.read() if e['kind']=='handler_finished')
        self.assertEqual(end['error_type'],'RuntimeError');self.assertNotIn('work_started_at',end)
        self.assertEqual(end['active_handlers_at_finish'],0)

    def test_disabled_handler_uses_original_work_and_no_header(self):
        h=self.handler();del h.headers
        with patch.object(server,'_diagnostics',None),patch.object(server,'_pool') as pool:
            h.do_GET();pool.submit.assert_called_once_with(server._burn_cpu,10000)

    def test_diagnostics_config_is_optional_and_both_topologies_supported(self):
        import json
        self.assertNotIn('diagnostics',json.loads(ExperimentConfig().to_json()))
        for mode in ('direct','proxy'):
            c=ExperimentConfig.from_dict(dict(topology={'mode':mode},traffic_sources={'execution':'containers'},
                autoscaler={'enabled':False},infrastructure={'initial_instances':1,'min_instances':1,'max_instances':1},
                load_balancer={'enabled':mode=='proxy'},diagnostics={'enabled':True,'queue_capacity':8}))
            self.assertTrue(c.diagnostics.enabled)
        for data in [dict(diagnostics={'queue_capacity':0}),dict(diagnostics={'enabled':True})]:
            with self.assertRaises(ValueError):ExperimentConfig.from_dict(data)

    def test_offline_boundaries_nulls_and_tail(self):
        result=count_windows([99,100,100.9,101,102],100,2)
        self.assertEqual(result['counts'],[2,1]);self.assertIsNone(stats([])['mean'])

    def test_instrumentation_preserves_exponential_draw_and_immediate_dispatch(self):
        import random
        from simulator import normal_traffic
        from simulator.experiment_config import NormalTrafficConfig,worker_seed
        observed=[]
        for enabled in (False,True):
            pool=ThreadPoolExecutor(1)
            writer=self.writer() if enabled else None
            executor=DiagnosticExecutor(pool,writer) if enabled else pool
            intervals=[]
            def sleep(interval):
                intervals.append(interval);normal_traffic.traffic_active=False
            try:
                with patch.multiple(normal_traffic,_send_pool=executor,_seed=42,_ground_truth=None,
                    _service_endpoint='http://edos_service:80',traffic_active=True,_settings=NormalTrafficConfig(rate=3)), \
                    patch.object(normal_traffic,'_send_one_normal') as send, \
                    patch.object(normal_traffic.time,'sleep',side_effect=sleep), \
                    patch.object(normal_traffic,'normal_traffic_summary_logger'),patch('builtins.print'):
                    normal_traffic.normal_http_request_worker(3,0)
                    self.assertEqual(send.call_count,1)
                observed.append(intervals)
            finally:
                pool.shutdown()
                if writer:writer.close()
        self.assertEqual(observed[0],observed[1])
        self.assertEqual(observed[0],[random.Random(worker_seed(42,'normal',0)).expovariate(3)])

    def test_handler_concurrency_counts_two_blocked_handlers(self):
        writer=self.writer();gate=threading.Event();entered=threading.Event();lock=threading.Lock()
        workers=ThreadPoolExecutor(2);count=[0]
        def work(units):
            with lock:
                count[0]+=1
                if count[0]==2:entered.set()
            gate.wait(2)
            return dict(work_started_at=time.monotonic(),work_finished_at=time.monotonic())
        handlers=[self.handler(),self.handler()]
        with patch.object(server,'_diagnostics',writer),patch.object(server,'_pool',workers), \
             patch.object(server,'_timed_burn_cpu',work),patch.object(server,'_active_handlers',0):
            threads=[threading.Thread(target=h.do_GET) for h in handlers]
            try:
                for t in threads:t.start()
                self.assertTrue(entered.wait(1));self.assertEqual(server._active_handlers,2)
            finally:
                gate.set()
                for t in threads:t.join(2)
                workers.shutdown()
            self.assertEqual(server._active_handlers,0)
        writer.close()
        self.assertEqual(max(e['active_handlers_at_start'] for e in self.read() if e['kind']=='handler_started'),2)


class DiagnosticSummaryTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        def put(path,value):
            p=self.root/path;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(json.dumps(value) if not isinstance(value,str) else value)
        self.put=put
        put('effective_config.json',dict(duration_seconds=2,diagnostics={'enabled':True},normal_traffic={'rate':1,'clients':1}))
        put('run_status.json',dict(run_id='run',experiment_start_monotonic=100))
        request='request_id,elapsed_seconds,end_elapsed_seconds,duration_ms,outcome\nr1,0.2,0.4,200,response\n'
        put('request_log.csv',request)
        put('simulation_metrics.csv','active_containers_names,average_cpu_percent\nvictim,0\n')
        put('source_inventory.json',[dict(source_id='normal_1')])
        put('source_artifacts/normal_1/output/local_requests.csv',request)
        put('diagnostics/metadata.json',{})
        self.events=[dict(kind=kind,at=at,attempt_id='1') for kind,at in
            [('submitted',100.1),('task_started',100.15),('http_started',100.2),('http_finished',100.4),('task_finished',100.5)]]
        self.events[0]['planned_at']=None
        self.events[2].update(request_id='r1',elapsed_seconds=.2)
        self.events[3].update(request_id='r1',elapsed_seconds=.4)
        self.events.append(dict(kind='planned',at=101.5,attempt_id='2',planned_at=103,sampled_interval=1.5))
        self.events.append(dict(kind='source_closed',at=102.1,drained=True,logger_complete=True,
            counts=dict(submitted=1,task_started=1,task_finished=1,cancelled=0,rejected=0)))
        self.save_source()
        put('source_artifacts/normal_1/output/diagnostics/events.summary.json',dict(complete=True,written=7))
        victim=[dict(kind='handler_started',at=100.25,request_id='r1',active_handlers_at_start=1),
            dict(kind='handler_finished',at=100.35,request_id='r1',handler_started_at=100.25,handler_finished_at=100.35,
                 work_submitted_at=100.26,work_started_at=100.27,work_finished_at=100.33,work_result_observed_at=100.34,
                 worker_clock={'time_namespace':'same'},error_type=None)]
        put('diagnostics/victim/events.jsonl',''.join(json.dumps(e)+'\n' for e in victim))
        put('diagnostics/victim/events.summary.json',dict(complete=True,written=2,clock={'time_namespace':'same'}))

    def save_source(self):
        self.put('source_artifacts/normal_1/output/diagnostics/events.jsonl',''.join(json.dumps(e)+'\n' for e in self.events))

    def test_aligned_horizon_future_plan_and_correlation(self):
        r=summarize(self.root);self.assertEqual(r['reliability_errors'],[])
        s=r['sources'][0]
        self.assertEqual(s['planned_after_plan'],1);self.assertEqual(s['planned_not_submitted_in_plan'],0)
        self.assertEqual(s['unresolved_tasks'],0);self.assertEqual(r['victim']['matched_request_ids'],1)

    def test_counter_disagreement_and_diagnostic_loss_are_visible(self):
        self.events[-1]['counts']['submitted']=2;self.save_source()
        self.put('diagnostics/victim/events.summary.json',dict(complete=False,written=2,clock={'time_namespace':'same'}))
        errors=summarize(self.root)['reliability_errors']
        self.assertIn('source counter mismatch',errors)
        self.assertIn('victim diagnostic log incomplete',errors)

    def test_scientific_timestamp_divergence_is_rejected(self):
        self.events[2]['elapsed_seconds']=.3;self.save_source()
        self.assertIn('diagnostic/scientific start time differs',summarize(self.root)['reliability_errors'])

    def test_incomplete_source_is_not_approved_by_balanced_counts(self):
        self.events[-1]['drained']=False;self.save_source()
        r=summarize(self.root)
        self.assertIn('source closure incomplete',r['reliability_errors'])
        self.assertFalse(r['sources'][0]['closure']['drained'])

    def test_incomparable_worker_clocks_do_not_form_durations(self):
        p=self.root/'diagnostics/victim/events.jsonl'
        events=[json.loads(s) for s in p.read_text().splitlines()]
        events[-1]['worker_clock']['time_namespace']='different'
        events[-1]['work_started_at']=10
        p.write_text(''.join(json.dumps(e)+'\n' for e in events))
        r=summarize(self.root)
        self.assertIn('worker/handler clock namespace differs',r['reliability_errors'])
        self.assertNotIn('work_wait',r['victim']['durations_seconds'])

    def test_negative_delay_in_comparable_source_clock_is_flagged(self):
        self.events[2]['at']=100;self.save_source()
        self.assertIn('negative submit_to_http',summarize(self.root)['reliability_errors'])
