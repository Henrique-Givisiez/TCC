import csv
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
from concurrent.futures import Future

from simulator.attack_patterns import ContinuousFlood, PeriodicBurst, attack_pattern
from simulator.experiment_config import ExperimentConfig, AttackConfig, BurstConfig
from simulator.ground_truth import GroundTruth
from simulator.request_logger import RequestLogger
from simulator.source_journal import Journal, JournalGroundTruth
from simulator.source_manager import worker_quotas
from simulator import traffic_injectorV0 as injector, config


class Clock:
    epoch_initial = 1000
    monotonic_initial = 100
    now = 0

    def sample(self):
        return self.epoch_initial + self.now, self.now

    def elapsed(self):
        return self.now


class PatternTests(unittest.TestCase):
    def test_continuous_and_historical_configs(self):
        for path in Path('experiments/configs').glob('*.json'):
            c = ExperimentConfig.load(path)
            self.assertEqual(ExperimentConfig.from_dict(json.loads(c.to_json())), c)
        self.assertEqual(AttackConfig().rate, 10)
        self.assertIs(type(attack_pattern(AttackConfig())), ContinuousFlood)
        pattern = ContinuousFlood(2, 12)
        for t, allowed in ((0, False), (1.999, False), (2, True), (5, True), (11.999, True), (12, False)):
            self.assertEqual(pattern.allows(t), allowed)

    def test_periodic_boundaries_start_to_start_and_global_clipping(self):
        pattern = PeriodicBurst(2, 12.5, 3, 1)
        for t, allowed in ((0, False), (1.999, False), (2, True), (2.999, True), (3, False),
                           (4.999, False), (5, True), (6, False), (8, True), (9, False),
                           (11, True), (12, False), (12.5, False), (20, False)):
            with self.subTest(t=t):
                self.assertEqual(pattern.allows(t), allowed)
        self.assertEqual(pattern.next_window(3), (5, 6))
        self.assertIsNone(pattern.next_window(12))
        clipped = PeriodicBurst(2, 5.5, 3, 1)
        self.assertEqual(clipped.next_window(5), (5, 5.5))
        self.assertTrue(clipped.allows(5.499))
        self.assertFalse(clipped.allows(5.5))

    def test_full_duty_cycle_has_no_silence(self):
        periodic, continuous = PeriodicBurst(2, 12.5, 3, 3), ContinuousFlood(2, 12.5)
        for i in range(150):
            t = i / 10
            self.assertEqual(periodic.allows(t), continuous.allows(t))

    def test_invalid_pattern_configuration(self):
        base = dict(profile='periodic_burst', start_seconds=2, duration_seconds=10)
        invalid = [None, {}, {'period_seconds': 3}, {'duration_seconds': 1},
                   {'period_seconds': 0, 'duration_seconds': 1},
                   {'period_seconds': -1, 'duration_seconds': 1},
                   {'period_seconds': 3, 'duration_seconds': 0},
                   {'period_seconds': 3, 'duration_seconds': -1},
                   {'period_seconds': 1, 'duration_seconds': 2},
                   {'period_seconds': float('inf'), 'duration_seconds': 1},
                   {'period_seconds': 3, 'duration_seconds': float('nan')},
                   {'period_seconds': True, 'duration_seconds': 1},
                   {'period_seconds': 3, 'duration_seconds': 1, 'jitter_seconds': 0}]
        for burst in invalid:
            with self.subTest(burst=burst), self.assertRaises(ValueError):
                ExperimentConfig.from_dict({'attack': dict(base, burst=burst)})
        for profile in ('random_burst', 'custom_pattern', 'PeriodicBurst'):
            with self.assertRaises(ValueError):
                ExperimentConfig.from_dict({'attack': dict(base, profile=profile)})

    def test_operations_are_independent_and_planning_is_deterministic(self):
        base = AttackConfig(profile='periodic_burst', start_seconds=2, duration_seconds=10,
                            burst=BurstConfig(period_seconds=3, duration_seconds=1))
        for operation in ('/light', '/medium', '/expensive'):
            c = ExperimentConfig(attack=replace(base, endpoint=operation), seed=42).validate()
            pattern = attack_pattern(c.attack)
            self.assertEqual(pattern, attack_pattern(c.resolve_seed().attack))
            self.assertEqual([pattern.next_window(t) for t in (0, 3, 6, 9)], [(2, 3), (5, 6), (8, 9), (11, 12)])

    def test_worker_budget_and_rate_remain_per_attacker(self):
        settings = AttackConfig(rate=10, attackers=4, profile='periodic_burst',
                                burst=BurstConfig(period_seconds=3, duration_seconds=1))
        self.assertEqual(worker_quotas(settings.max_concurrent_sends, settings.attackers), [16]*4)
        # SourceManager preserves settings.rate; only send worker quotas split.
        from simulator.source_manager import SourceManager
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            experiment = ExperimentConfig(attack=settings, normal_traffic=replace(ExperimentConfig().normal_traffic, clients=0))
            client, network = MagicMock(), MagicMock()
            client.images.get.return_value.id = 'image'
            client.images.get.return_value.attrs = {'RepoDigests': []}
            client.containers.run.return_value.id = 'container'
            client.containers.run.return_value.name = 'source'
            network.name = 'edos_sources'
            client.containers.run.return_value.attrs = {'Config': {'Hostname': 'source'},
                'NetworkSettings': {'Networks': {'edos_sources': {'IPAddress': '172.20.0.3'}}}}
            manager = SourceManager(client, network, root/'sources', root/'inventory.json', experiment)
            # Stop after all manifests are written, before readiness/clock audit.
            with patch.object(manager, 'verify', side_effect=RuntimeError('stop before readiness')):
                with self.assertRaisesRegex(RuntimeError, 'stop before readiness'):
                    manager.start()
            self.assertEqual([p['settings']['rate'] for p in manager.plan], [10]*4)
            self.assertEqual(sum(p['settings']['max_concurrent_sends'] for p in manager.plan), 64)


class PeriodicAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.clock = Clock()
        self.journal = Journal(self.root/'journal.jsonl', 'attack_1', 'run')
        self.gt = JournalGroundTruth('periodic', self.root/'events.csv', self.clock,
                                    run_id='run', journal=self.journal)
        self.gt.plan_event('attack_001', 'event_001', 'periodic_burst', 2, 12.5)
        self.clock.now = 2
        self.gt.activate('event_001')
        self.logger = RequestLogger(self.gt, self.root/'requests.csv', journal=self.journal)
        settings = AttackConfig(profile='periodic_burst', start_seconds=2, duration_seconds=10.5,
                                endpoint='/expensive', max_concurrent_sends=1,
                                burst=BurstConfig(period_seconds=3, duration_seconds=1))
        injector.configure(settings, 42, self.gt, self.logger, config.SOURCE_SERVICE_ENDPOINT)
        injector._event_id = 'event_001'
        self.session = MagicMock()
        self.session.get.return_value = MagicMock(status_code=200, text='host=victim')
        self.counters, self.lock = {'ok': 0, 'err': 0}, threading.Lock()

    def tearDown(self):
        injector.attack_active = False
        injector._send_pool.shutdown(wait=True)
        injector.configure(AttackConfig(), 42)
        injector._send_pool.shutdown()

    def send(self, deadline=3):
        injector._send_periodic(self.session, config.SOURCE_SERVICE_ENDPOINT+'/expensive',
                                self.counters, self.lock, 0, deadline)

    def admission_rows(self):
        return [r for r in map(json.loads, (self.root/'journal.jsonl').read_text().splitlines()) if r['kind']=='admission']

    def test_expiration_before_admission_and_no_rollover(self):
        for time in (1.999, 3, 4, 5.2, 12.5, 20):
            self.clock.now = time
            self.send()  # Original deadline=3: never resurrect in burst 5–6.
        self.session.get.assert_not_called()
        self.assertFalse(self.admission_rows())
        self.assertEqual(self.counters, {'ok': 0, 'err': 0})
        self.assertEqual(self.logger._next_id, 0)
        self.assertEqual(self.gt._events['event_001'].pending, 0)
        self.assertIsNone(self.gt.event('event_001')['actual_start_seconds'])
        self.clock.now = 5.2
        self.send(6)
        self.session.get.assert_called_once()
        self.assertEqual(len(self.admission_rows()), 1)

    def test_capacity_exhaustion_does_not_admit_or_queue_and_failure_releases_slot(self):
        injector._send_slots.acquire()
        with patch.object(injector._send_pool, 'submit') as submit:
            self.assertIsNone(injector._submit_periodic(self.session, 'url', self.counters, self.lock, 0, 3))
            submit.assert_not_called()
        self.assertFalse(self.admission_rows())
        injector._send_slots.release()
        with patch.object(injector._send_pool, 'submit', side_effect=RuntimeError('shutdown')):
            with self.assertRaises(RuntimeError):
                injector._submit_periodic(self.session, 'url', self.counters, self.lock, 0, 3)
        self.assertTrue(injector._send_slots.acquire(blocking=False))
        injector._send_slots.release()

    def test_executor_delay_expires_without_request_or_admission(self):
        saved = []
        done = Future()
        with patch.object(injector._send_pool, 'submit', side_effect=lambda *args: saved.append(args) or done):
            self.clock.now = 2.9
            future = injector._submit_periodic(self.session, 'url', self.counters, self.lock, 0, 3)
        self.assertFalse(self.admission_rows())
        self.clock.now = 5.1  # Delayed task wakes in NEXT burst.
        saved[0][0](*saved[0][1:])
        done.set_result(None)
        self.assertTrue(future.done())
        self.session.get.assert_not_called()
        self.assertFalse(self.admission_rows())
        self.assertTrue(injector._send_slots.acquire(blocking=False))
        injector._send_slots.release()

    def test_gate_uses_observed_start_sample_not_earlier_elapsed_check(self):
        self.clock.now = 3
        with patch.object(self.clock, 'elapsed', return_value=2.9):
            self.send()
        self.session.get.assert_not_called()
        self.assertFalse(self.admission_rows())

    def test_valid_beginning_and_completion_in_silence_preserve_global_event(self):
        self.clock.now = 2.95
        def finish_in_silence(*args, **kwargs):
            self.clock.now = 3.4
            return MagicMock(status_code=200)
        self.session.get.side_effect = finish_in_silence
        self.send()
        with (self.root/'requests.csv').open() as stream:
            row = next(csv.DictReader(stream))
        self.assertEqual((float(row['elapsed_seconds']), float(row['end_elapsed_seconds'])), (2.95, 3.4))
        self.assertEqual((row['traffic_class'], row['attack_active']), ('attack', '1'))
        self.assertEqual(self.gt.is_attack_active(4), 1)
        self.assertIsNone(self.gt.event('event_001')['actual_end_seconds'])
        self.assertEqual(self.gt._events['event_001'].pending, 0)
        self.assertEqual(self.admission_rows()[0]['payload']['elapsed_seconds'], 2.95)

    def test_completion_after_global_end_keeps_end_separate_from_drain(self):
        self.clock.now = 11.9
        def finish_after_end(*args, **kwargs):
            self.clock.now = 12.5
            self.gt.stop('event_001')
            self.assertEqual(self.gt.event('event_001')['actual_end_seconds'], 12.5)
            self.assertIsNone(self.gt.event('event_001')['drained_end_seconds'])
            self.clock.now = 14
            return MagicMock(status_code=200)
        self.session.get.side_effect = finish_after_end
        self.send(12)
        event = self.gt.event('event_001')
        self.assertEqual((event['actual_start_seconds'], event['actual_end_seconds'], event['drained_end_seconds']), (11.9, 12.5, 14))
        self.assertEqual(event['status'], 'completed')

    def test_scheduler_with_fake_clock_never_submits_in_silence(self):
        self.clock.now = 0
        class Stop:
            def is_set(self):
                return False
            def wait(_, seconds):
                self.clock.now += seconds
        submissions = []
        def submit(session, url, counters, lock, index, deadline):
            submissions.append((self.clock.now, deadline, url))
            return None
        injector.attack_active = True
        with patch.object(injector, '_stop_event', Stop()), \
             patch.object(injector, '_submit_periodic', side_effect=submit), \
             patch.object(injector, '_finish_worker'):
            injector.http_request_worker(10, 0)
        self.assertTrue(submissions)
        self.assertEqual({int((time-2)//3) for time, _, _ in submissions}, {0, 1, 2, 3})
        self.assertTrue(all(injector._pattern.allows(time) and time < deadline for time, deadline, _ in submissions))
        self.assertTrue(all(url == config.SOURCE_SERVICE_ENDPOINT+'/expensive' for _, _, url in submissions))


if __name__ == '__main__':
    unittest.main()
