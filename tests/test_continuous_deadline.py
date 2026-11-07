"""No network: shared-clock admission and queued-task lifecycle."""
import csv
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from concurrent.futures import ThreadPoolExecutor
import requests
from simulator import traffic_injectorV0 as injector
from simulator.experiment_config import AttackConfig
from simulator.source_journal import Journal, JournalGroundTruth
from simulator.request_logger import RequestLogger
from simulator.source_aggregate import identified_admission_errors
from simulator.diagnostics import DiagnosticExecutor, DiagnosticWriter

class Clock:
    monotonic_initial = 0
    epoch_initial = 1000
    now = 2
    def elapsed(self): return self.now
    def sample(self): return 1000 + self.now, self.now

class DeadlineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.clock = Clock()
        self.gt = JournalGroundTruth('test', self.root/'events.csv', self.clock,
            run_id='run', journal=Journal(self.root/'journal.jsonl', 'attack_1', 'run'))
        self.gt.plan_event('A', 'E', 'continuous', 2, 4); self.gt.activate('E')
        self.logger = RequestLogger(self.gt, self.root/'requests.csv', journal=self.gt.journal)
        injector.configure(AttackConfig(start_seconds=2, duration_seconds=2), 42,
                           self.gt, self.logger, 'http://edos_service:80')
        injector._event_id = 'E'
        self.addCleanup(lambda: injector._send_pool.shutdown(wait=True))
        self.session = MagicMock(); self.session.get.return_value = MagicMock(status_code=200, text='ok')
    def records(self): return [json.loads(x) for x in (self.root/'journal.jsonl').read_text().splitlines()]
    def send(self, token):
        injector._send_one(self.session, 'http://edos_service:80/medium', {'ok':0,'err':0},
                           threading.Lock(), 0, 'E', admission_id=token)
    def test_boundaries_and_duplicate_resolution(self):
        for t in (1, 4, 5):
            self.clock.now=t; self.assertIsNone(self.gt.admit_continuous('E'))
        self.clock.now=2; token=self.gt.admit_continuous('E')
        self.clock.now=4; self.send(token)
        self.session.get.assert_not_called()
        self.assertEqual(self.logger._next_id,0)
        self.assertEqual(self.gt._events['E'].pending,0)
        with self.assertRaises(RuntimeError): self.send(token)
        self.assertFalse(identified_admission_errors(self.records()))
    def test_before_start_guard(self):
        token=self.gt.admit_continuous('E'); self.clock.now=1
        self.send(token); self.session.get.assert_not_called()
        self.assertEqual(self.gt._events['E'].in_flight,0)
    def test_completion_and_timeout_after_end(self):
        for timeout in (False, True):
            self.clock.now=3; token=self.gt.admit_continuous('E')
            def get(*args, **kwargs):
                self.clock.now=5
                if timeout: raise requests.exceptions.Timeout('late')
                return MagicMock(status_code=200, text='ok')
            self.session.get.side_effect=get; self.send(token)
        with (self.root/'requests.csv').open() as f: rows=list(csv.DictReader(f))
        self.assertEqual([r['outcome'] for r in rows],['response','transport_error'])
        self.assertTrue(all(float(r['end_elapsed_seconds'])==5 for r in rows))
        self.assertFalse(identified_admission_errors(self.records()))
    def test_simultaneous_expiration_and_incomplete(self):
        tokens=[self.gt.admit_continuous('E') for _ in range(30)]
        self.assertTrue(identified_admission_errors(self.records()))
        self.clock.now=4
        with ThreadPoolExecutor(8) as pool: list(pool.map(self.send,tokens))
        self.assertEqual(self.gt._events['E'].pending,0)
        self.assertFalse(identified_admission_errors(self.records()))
        self.session.get.assert_not_called()
    def test_stop_start_race(self):
        token=self.gt.admit_continuous('E'); barrier=threading.Barrier(2)
        def stop(): barrier.wait(); self.gt.stop('E')
        def send(): barrier.wait(); self.send(token)
        with ThreadPoolExecutor(2) as pool:
            a=pool.submit(stop); b=pool.submit(send); a.result(); b.result()
        self.assertEqual(self.gt._events['E'].pending,0)
        self.assertEqual(self.gt._events['E'].in_flight,0)
        self.assertLessEqual(self.session.get.call_count,1)
        self.assertFalse(identified_admission_errors(self.records()))
    def test_rejected_submit_and_absolute_producer_end(self):
        injector.attack_active=True
        try:
            with patch.object(injector._send_pool,'submit',side_effect=RuntimeError('closed')):
                injector.http_request_worker(8)
            self.assertEqual(self.gt._events['E'].pending,0)
            self.assertFalse(identified_admission_errors(self.records()))
            self.clock.now=4
            with patch.object(injector._send_pool,'submit') as submit:
                injector.http_request_worker(8); submit.assert_not_called()
        finally: injector.attack_active=False
    def test_producer_waits_until_start_without_catchup(self):
        self.clock.now=1
        injector.attack_active=True
        def wait(seconds):
            self.assertEqual(seconds,1)
            self.clock.now=4
        try:
            with patch.object(injector._stop_event,'wait',side_effect=wait), patch.object(injector._send_pool,'submit') as submit:
                injector.http_request_worker(8)
                submit.assert_not_called()
            self.assertFalse([e for e in self.records() if e['kind']=='admission'])
        finally: injector.attack_active=False

    def test_real_executor_queue_and_diagnostic_identity(self):
        writer=DiagnosticWriter(self.root/'diagnostic.jsonl')
        entered=threading.Event(); release=threading.Event()
        with ThreadPoolExecutor(1) as pool:
            executor=DiagnosticExecutor(pool,writer)
            blocked=pool.submit(lambda: (entered.set(),release.wait(2)))
            self.assertTrue(entered.wait(1))
            token=self.gt.admit_continuous('E')
            f=executor.submit(injector._send_one,self.session,'http://edos_service:80/medium',
                              {'ok':0,'err':0},threading.Lock(),0,'E',admission_id=token)
            self.clock.now=4; release.set(); f.result(2); blocked.result(2)
        writer.close(); self.session.get.assert_not_called()
        events=[json.loads(x) for x in (self.root/'diagnostic.jsonl').read_text().splitlines()]
        self.assertEqual({e['attempt_id'] for e in events},{token})
        self.assertFalse(identified_admission_errors(self.records()))
