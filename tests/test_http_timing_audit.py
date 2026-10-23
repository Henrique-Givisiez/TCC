"""Deterministic audit of existing timing contracts; no runtime changes/network."""
import csv
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import requests
from requests.adapters import BaseAdapter

from simulator import normal_traffic, traffic_injectorV0
from simulator.experiment_config import NormalTrafficConfig, AttackConfig
from simulator.ground_truth import GroundTruth
from simulator.request_logger import RequestLogger
from simulator.source_journal import Journal, JournalGroundTruth
from simulator.source_aggregate import aggregate


class Clock:
    epoch_initial = 1700000000
    monotonic_initial = 100

    def __init__(self):
        self.now = 0

    def advance(self, value):
        self.now += value

    def sample(self):
        return self.epoch_initial + self.now, self.now

    def elapsed(self):
        return self.now

    def monotonic(self):
        return self.monotonic_initial + self.now


def read_rows(path):
    with Path(path).open(newline='') as stream:
        return list(csv.DictReader(stream))


class Body(BytesIO):
    def __init__(self, clock, delay):
        super().__init__(b'host=victim body complete\n')
        self.clock, self.delay, self.consumed = clock, delay, False

    def read(self, *args, **kwargs):
        if not self.consumed:
            self.clock.advance(self.delay)
            self.consumed = True
        return super().read(*args, **kwargs)


class Adapter(BaseAdapter):
    """Headers and body have separate, controlled completion instants."""
    def __init__(self, clock, status=200, error=None):
        self.clock, self.status, self.error = clock, status, error
        self.body = None
        self.called_at = None

    def send(self, request, **kwargs):
        self.called_at = self.clock.now
        self.clock.advance(.125)
        if self.error:
            raise self.error
        response = requests.Response()
        response.status_code = self.status
        response.url = request.url
        response.request = request
        response.raw = self.body = Body(self.clock, .375)
        response.headers['Content-Type'] = 'text/plain'
        return response

    def close(self):
        pass


class TimingAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.clock = Clock()
        self.addCleanup(self.shutdown)

    def shutdown(self):
        for module in (normal_traffic, traffic_injectorV0):
            if module._send_pool is not None:
                module._send_pool.shutdown(wait=True)

    def setup_source(self, module=normal_traffic, begin_delay=.75, finish_delay=1.25):
        source = 'normal_1' if module is normal_traffic else 'attack_1'
        output = self.root/source/'output'
        output.mkdir(parents=True)
        journal = Journal(output/'journal.jsonl', source, 'audit-run')
        def delayed_journal(kind, payload):
            if kind == 'request_begin':
                self.clock.advance(begin_delay)
            elif kind == 'request_finish':
                self.clock.advance(finish_delay)
            journal(kind, payload)
        gt = JournalGroundTruth('audit', output/'events.csv', clock=self.clock,
                                run_id='audit-run', journal=delayed_journal)
        logger = RequestLogger(gt, output/'requests.csv', source_id=source, journal=delayed_journal)
        observer = lambda duration, elapsed: journal('latency_sample', dict(
            generator='normal' if module is normal_traffic else 'attack', duration_ms=duration,
            elapsed_seconds=elapsed, audit_publication_elapsed_seconds=self.clock.now))
        settings = NormalTrafficConfig() if module is normal_traffic else AttackConfig()
        module.configure(settings, 42, gt, logger, 'http://edos_service:80', observer)
        if module is traffic_injectorV0:
            gt.plan_event('A', 'E', 'continuous', 1, 10)
            gt.activate('E')
            module._event_id = 'E'
        return source, output, gt, logger

    def send(self, module, adapter):
        with requests.Session() as session:
            session.trust_env = False
            session.mount('http://', adapter)
            with patch('time.monotonic', self.clock.monotonic):
                if module is normal_traffic:
                    module._send_one_normal(session, 'http://edos_service:80/light',
                                            {'ok':0,'err':0}, threading.Lock())
                else:
                    module._send_one(session, 'http://edos_service:80/light',
                                     {'ok':0,'err':0}, threading.Lock(), event_id='E')

    def test_begin_disk_delay_included_finish_disk_delay_excluded_and_body_read(self):
        source, output, gt, logger = self.setup_source()
        self.clock.now = 2
        adapter = Adapter(self.clock)
        self.send(normal_traffic, adapter)
        row = read_rows(output/'requests.csv')[0]
        self.assertTrue(adapter.body.consumed)
        self.assertEqual(adapter.called_at, 2.75)
        self.assertEqual(float(row['elapsed_seconds']), 2)
        self.assertEqual(float(row['end_elapsed_seconds']), 3.25)
        self.assertEqual(float(row['duration_ms']), 1250)  # .75 begin + .5 HTTP
        self.assertEqual(self.clock.now, 4.5)  # finish persistence is outside duration
        items = [json.loads(l) for l in (output/'journal.jsonl').read_text().splitlines()]
        latency = next(i['payload'] for i in items if i['kind']=='latency_sample')
        self.assertEqual(latency['duration_ms'], 500)
        self.assertEqual(latency['elapsed_seconds'], 3.25)
        self.assertEqual(latency['audit_publication_elapsed_seconds'], 4.5)
        logger.save_rtt(output/'rtt.csv')
        self.assertEqual(float(read_rows(output/'rtt.csv')[0]['rtt']), 1250)
        self.assertEqual(normal_traffic.get_average_rtt_ms(), 500)
        self.assertEqual(normal_traffic.get_average_rtt_ms(), 0)  # empty buffer sentinel

    def test_http_error_and_transport_exception_have_different_populations(self):
        for module in (normal_traffic, traffic_injectorV0):
            with self.subTest(module=module.__name__):
                source, output, gt, logger = self.setup_source(module)
                for status, error in [(503, None),(200, requests.exceptions.ConnectionError('network'))]:
                    self.clock.now += 2
                    if module is traffic_injectorV0:
                        self.assertTrue(gt.admit('E'))
                    self.send(module, Adapter(self.clock, status, error))
                rows = read_rows(output/'requests.csv')
                self.assertEqual([r['outcome'] for r in rows], ['http_error','transport_error'])
                self.assertEqual([float(r['duration_ms']) for r in rows], [1250,875])
                logger.save_rtt(output/'rtt.csv')
                self.assertEqual(read_rows(output/'rtt.csv'), [])
                items = [json.loads(l) for l in (output/'journal.jsonl').read_text().splitlines()]
                samples = [i['payload'] for i in items if i['kind']=='latency_sample']
                self.assertEqual(len(samples), 1)  # HTTP 503 counts, transport failure does not
                self.assertEqual(samples[0]['duration_ms'], 500)
                self.clock.now += 1
                gt.finalize()
                if module is traffic_injectorV0:
                    self.assertEqual(gt.event('E')['status'], 'completed')

    def test_executor_queue_does_not_become_request_begin_or_duration(self):
        source, output, gt, logger = self.setup_source(begin_delay=0, finish_delay=0)
        occupied, release = threading.Event(), threading.Event()
        def blocker():
            occupied.set()
            if not release.wait(5):
                raise AssertionError('test synchronization timed out')
        with ThreadPoolExecutor(max_workers=1) as executor:
            busy = executor.submit(blocker)
            try:
                self.assertTrue(occupied.wait(5))
                self.clock.now = 1
                adapter = Adapter(self.clock)
                queued = executor.submit(self.send, normal_traffic, adapter)
                self.clock.now = 6
                self.assertFalse(queued.done())
                self.assertEqual(logger._next_id, 0)
                self.assertIsNone(adapter.called_at)
            finally:
                release.set()
            busy.result(timeout=5)
            queued.result(timeout=5)
        row = read_rows(output/'requests.csv')[0]
        self.assertEqual(float(row['elapsed_seconds']), 6)
        self.assertEqual(float(row['duration_ms']), 500)  # excludes 5 s queued

    def test_continuous_queued_start_after_stop_then_closure_before_drain(self):
        source, output, gt, logger = self.setup_source(traffic_injectorV0, 0, 0)
        occupied, release = threading.Event(), threading.Event()
        in_http, finish_http = threading.Event(), threading.Event()
        def blocker():
            occupied.set()
            if not release.wait(5):
                raise AssertionError('test synchronization timed out')
        def http(*args, **kwargs):
            in_http.set()
            if not finish_http.wait(5):
                raise AssertionError('test synchronization timed out')
            response = requests.Response()
            response.status_code, response._content = 200, b'body'
            return response
        with ThreadPoolExecutor(max_workers=1) as executor:
            busy = executor.submit(blocker)
            try:
                self.assertTrue(occupied.wait(5))
                self.clock.now = 9
                self.assertTrue(gt.admit('E'))
                session = type('Session', (), {'get': staticmethod(http)})()
                with patch('time.monotonic', self.clock.monotonic):
                    queued = executor.submit(traffic_injectorV0._send_one, session,
                        'http://edos_service:80/light', {'ok':0,'err':0}, threading.Lock(), 0, 'E')
                    self.clock.now = 10
                    with patch.object(traffic_injectorV0, 'attack_active', True), \
                         patch.object(traffic_injectorV0, 'attacker_threads', []):
                        traffic_injectorV0.stop_http_flood('scheduled_end')
                    self.assertFalse(gt.admit('E'))
                    self.assertIsNone(gt.event('E')['actual_end_seconds'])
                    self.clock.now = 12
                    release.set()
                    self.assertTrue(in_http.wait(5))
                    self.assertEqual(gt.event('E')['actual_start_seconds'], 12)
                    self.clock.now = 12.25
                    gt.stop('E')  # a strictly later clock observation certifies closure
                    self.assertEqual(gt.event('E')['actual_end_seconds'], 12.25)
                    self.assertIsNone(gt.event('E')['drained_end_seconds'])
                    self.clock.now = 14
                    finish_http.set()
                    queued.result(timeout=5)
            finally:
                release.set()
                finish_http.set()
            busy.result(timeout=5)
        row = read_rows(output/'requests.csv')[0]
        self.assertEqual(float(row['elapsed_seconds']), 12)
        self.assertEqual(float(row['duration_ms']), 2000)
        self.assertEqual(row['attack_active'], '1')
        self.assertEqual(gt.event('E')['drained_end_seconds'], 14)
        self.assertEqual(gt.event('E')['status'], 'completed')

    def test_finalized_pending_attempt_has_no_invented_duration(self):
        source, output, gt, logger = self.setup_source()
        self.clock.now = 1
        attempt = logger.begin('normal', 0, 'http://edos_service:80/light')
        self.assertFalse(logger.finalize())
        row = read_rows(output/'requests.csv')[0]
        self.assertEqual(row['outcome'], 'incomplete')
        self.assertEqual(row['duration_ms'], '')
        self.clock.now = 5
        self.assertIsNone(logger.finish(attempt, requests.Response()))
        self.assertEqual(len(read_rows(output/'requests.csv')), 1)

    def test_source_aggregation_preserves_timings_and_response_subset(self):
        source, output, gt, logger = self.setup_source()
        self.clock.now = 2
        for status,error in [(200,None),(503,None),(200,requests.exceptions.Timeout('read'))]:
            self.send(normal_traffic, Adapter(self.clock,status,error))
        self.assertTrue(logger.finalize())
        entries = [dict(source_id=source,source_type='normal',run_id='audit-run')]
        global_gt = GroundTruth('audit',self.root/'global_events.csv',self.clock,run_id='audit-run')
        complete, rows = aggregate(global_gt,entries,self.root,self.root/'request_log.csv',
                        self.root/'rtt_log.csv',self.root/'routing.jsonl',self.root/'absent_metrics.csv')
        self.assertTrue(complete)
        self.assertEqual([r['duration_ms'] for r in rows],[1250,1250,875])
        self.assertEqual(len(read_rows(self.root/'rtt_log.csv')),1)
        rtt = read_rows(self.root/'rtt_log.csv')[0]
        self.assertEqual(float(rtt['rtt']),1250)
        self.assertEqual(float(rtt['elapsed_seconds']),3.25)

    def test_features_count_starts_and_bin_all_failure_durations_by_completion(self):
        from tests import test_feature_extraction as feature_fixtures
        fixture = feature_fixtures.FeatureExtractionTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        def add_failures(rows):
            base = rows[1]  # benign n1, duration 200 ms, completion 2.7
            rows.append(dict(base, request_id='audit_http', elapsed_seconds='2.8',
                end_elapsed_seconds='3', outcome='http_error', http_status='503', error_type=''))
            rows.append(dict(base, request_id='audit_transport', elapsed_seconds='2.75',
                end_elapsed_seconds='3', outcome='transport_error', http_status='', error_type='ConnectionError'))
        fixture.change_requests(add_failures)
        fixture.extract()
        windows = fixture.rows('service')
        self.assertEqual(windows[2]['request_starts'], '4')
        self.assertEqual(windows[2]['request_completions'], '1')
        self.assertEqual(windows[3]['request_starts'], '0')
        self.assertEqual(windows[3]['request_completions'], '3')
        self.assertEqual(windows[3]['http_failures'], '1')
        self.assertEqual(windows[3]['transport_failures'], '1')
        # a1=1000 ms, HTTP failure=200 ms, transport failure=250 ms
        self.assertAlmostEqual(float(windows[3]['mean_duration_ms']), 1450/3)


if __name__ == '__main__':
    unittest.main()
