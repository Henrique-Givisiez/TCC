import csv
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

import requests

from simulator.ground_truth import GroundTruth
from simulator.request_logger import RequestLogger
from simulator.tcpdump_sniffer import TcpdumpSniffer, TCPDUMP_REGEX


class Clock:
    epoch_initial = 1700000000.0
    monotonic_initial = 100.0
    now = 0.0

    def elapsed(self):
        return self.now

    def sample(self):
        return self.epoch_initial + self.now, self.now

    def from_epoch(self, timestamp):
        return timestamp - self.epoch_initial


def rows(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f))


class GroundTruthTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.clock = Clock()
        self.gt = GroundTruth('test', self.root / 'attack_events.csv', self.clock)
        self.logger = RequestLogger(self.gt, self.root / 'request_log.csv')
        self.gt.plan_event('attack_001', 'event_001', 'continuous', 20, 30)

    def begin_attack(self, start=21):
        self.clock.now = 20.5
        self.gt.activate('event_001')
        self.gt.admit('event_001')
        self.clock.now = start
        return self.logger.begin('attack', 0, 'http://localhost:8080', 'event_001')

    def test_a_b_c_d_and_origin_ids(self):
        self.clock.now = 1
        a = self.logger.begin('normal', 0, 'http://localhost:8080')
        self.logger.finish(a, MagicMock(status_code=200))
        c = self.begin_attack()
        self.clock.now = 22
        b = self.logger.begin('normal', 0, 'http://localhost:8080')
        self.logger.finish(b, MagicMock(status_code=200))
        self.clock.now = 31
        self.gt.stop('event_001')
        self.clock.now = 32
        d = self.logger.begin('normal', 0, 'http://localhost:8080')
        self.logger.finish(d, MagicMock(status_code=200))
        self.logger.finish(c, MagicMock(status_code=200))
        self.assertTrue(self.logger.finalize())
        self.gt.finalize()
        records = {r['request_id']: r for r in rows(self.root / 'request_log.csv')}
        for attempt, cls, active in [(a,'benign','0'), (b,'benign','1'),
                                    (c,'attack','1'), (d,'benign','0')]:
            row = records[attempt['request_id']]
            self.assertEqual((row['traffic_class'], row['attack_active']), (cls,active))
            self.assertEqual(int(active), self.gt.is_attack_active(float(row['elapsed_seconds'])))
        self.assertEqual(b['event_id'], None)
        self.assertEqual(json.loads(b['active_event_ids']), ['event_001'])
        self.assertEqual(c['attack_id'], 'attack_001')
        self.assertEqual(len(set(records)), 4)
        event = rows(self.root / 'attack_events.csv')[0]
        self.assertEqual(event['actual_start_seconds'], '21')
        self.assertEqual(event['actual_end_seconds'], '31')
        self.assertEqual(event['drained_end_seconds'], '32')
        self.assertEqual(event['status'], 'completed')

    def test_boundaries_scheduled_actual_and_inflight_completion(self):
        c = self.begin_attack()
        self.assertEqual(self.gt.is_attack_active(20), 0)
        self.assertEqual(self.gt.is_attack_active(21), 1)
        self.clock.now = 30.5
        self.gt.stop('event_001')
        self.assertEqual(self.gt.is_attack_active(30.499), 1)
        self.assertEqual(self.gt.is_attack_active(30.5), 0)
        self.clock.now = 35
        self.logger.finish(c, MagicMock(status_code=200))
        row = rows(self.root / 'request_log.csv')[0]
        self.assertEqual(row['attack_active'], '1')
        self.assertEqual(row['end_elapsed_seconds'], '35')
        self.assertEqual(self.gt.event('event_001')['drained_end_seconds'], 35)

    def test_queued_attempt_starts_after_stop_and_keeps_event_active(self):
        first = self.begin_attack()
        self.gt.admit('event_001')
        self.clock.now = 30
        self.gt.stop('event_001')
        self.assertFalse(self.gt.admit('event_001'))
        self.assertIsNone(self.gt.event('event_001')['actual_end_seconds'])
        self.clock.now = 33
        last = self.logger.begin('attack', 0, 'http://localhost:8080', 'event_001')
        self.assertEqual(last['attack_active'], 1)
        self.clock.now = 34
        self.gt.stop('event_001')  # observable distinct clock time certifies closure
        self.assertEqual(self.gt.event('event_001')['actual_end_seconds'], 34)
        self.assertEqual(self.gt.event('event_001')['last_request_start_seconds'], 33)
        self.clock.now = 36
        self.logger.finish(first, MagicMock(status_code=200))
        self.logger.finish(last, MagicMock(status_code=200))
        self.assertEqual(self.gt.event('event_001')['drained_end_seconds'], 36)

    def test_e_tcpdump_timestamp_unknown_and_final_timeline(self):
        sniffer = TcpdumpSniffer('any', self.root / 'traffic_capture.csv', self.gt)
        # Process before first attempt is recorded; finalization re-queries timeline.
        epoch = self.clock.epoch_initial + 22
        line = f'{epoch:.6f} IP 127.0.0.1.40000 > 127.0.0.1.8080: tcp 25'
        self.clock.now = 100  # processing time must not determine packet timestamp
        sniffer._write_row(TCPDUMP_REGEX.search(line).groupdict())
        attack = self.begin_attack()
        self.clock.now = 30
        self.gt.stop('event_001')
        self.clock.now = 31
        self.logger.finish(attack, MagicMock(status_code=200))
        sniffer.stop()
        packet = rows(self.root / 'traffic_capture.csv')[0]
        self.assertEqual(float(packet['timestamp']), epoch)
        self.assertEqual(float(packet['elapsed_seconds']), 22)
        self.assertEqual((packet['traffic_class'], packet['attack_active']), ('unknown', '1'))
        self.assertNotIn('attack_id', packet)
        self.assertFalse(hasattr(sniffer, 'set_label'))

    def test_f_zero_rate_and_zero_attackers(self):
        from simulator import traffic_injectorV0 as attack
        from simulator.experiment_config import AttackConfig
        for rate, attackers in [(0,4),(5,0)]:
            with self.subTest(rate=rate, attackers=attackers):
                gt = GroundTruth('zero', self.root / 'zero_events.csv', self.clock)
                gt.plan_event('A', 'E', 'continuous', 20,30)
                logger = RequestLogger(gt, self.root / 'zero_requests.csv')
                with patch.object(attack,'attack_active',False), patch.object(attack,'_send_pool') as pool:
                    attack.configure(AttackConfig(rate=rate, attackers=attackers), 42, gt, logger)
                    with patch.object(attack,'_send_pool') as pool:
                        self.assertFalse(attack.start_http_flood(['http://localhost:8080'],rate,attackers,'E'))
                        pool.submit.assert_not_called()
                    gt.finalize()
                    self.assertEqual(gt.is_attack_active(25),0)
                    self.assertEqual(gt.event('E')['status'],'not_executed')
                    self.assertIsNone(gt.event('E')['actual_start_seconds'])
                    self.assertIsNone(gt.event('E')['actual_end_seconds'])
                    self.assertEqual(rows(self.root / 'zero_requests.csv'), [])
                    attack._send_pool.shutdown()

    def test_failures_logged_and_rtt_origin_and_common_clock(self):
        from simulator import normal_traffic as normal
        from simulator.experiment_config import NormalTrafficConfig
        session = MagicMock()
        def response(*args, **kwargs):
            self.clock.now += .1
            return MagicMock(status_code=200)
        session.get.side_effect = response
        with patch.object(normal,'traffic_active',False):
            normal.configure(NormalTrafficConfig(),42,self.gt,self.logger)
            self.clock.now = 2
            normal._send_one_normal(session,'http://localhost:8080',{'ok':0,'err':0},threading.Lock(),7)
            self.clock.now = 3
            session.get.side_effect = requests.exceptions.Timeout('timeout')
            normal._send_one_normal(session,'http://localhost:8080',{'ok':0,'err':0},threading.Lock(),7)
            self.clock.now = 4
            session.get.side_effect = None
            session.get.return_value = MagicMock(status_code=503)
            normal._send_one_normal(session,'http://localhost:8080',{'ok':0,'err':0},threading.Lock(),7)
            self.assertTrue(normal.drain())
        self.logger.save_rtt(self.root / 'rtt_log.csv')
        reqs = rows(self.root / 'request_log.csv')
        self.assertEqual([r['outcome'] for r in reqs],['response','transport_error','http_error'])
        self.assertEqual(reqs[1]['error_type'],'Timeout')
        self.assertEqual(reqs[2]['http_status'],'503')
        rtts = rows(self.root / 'rtt_log.csv')
        self.assertEqual(len(rtts),1)
        self.assertEqual(rtts[0]['request_id'],reqs[0]['request_id'])
        self.assertEqual(rtts[0]['traffic_class'],'benign')
        self.assertAlmostEqual(float(reqs[0]['duration_ms']),100)
        for r in reqs:
            self.assertAlmostEqual(float(r['timestamp'])-self.clock.epoch_initial,float(r['elapsed_seconds']))
        self.assertAlmostEqual(float(rtts[0]['elapsed_seconds']),2.1)

    def test_incomplete_does_not_invent_end_or_inactivity(self):
        attack = self.begin_attack()
        self.gt.admit('event_001')  # queue not drained
        self.clock.now = 30
        self.gt.stop('event_001')
        self.assertFalse(self.logger.finalize())
        self.gt.finalize(complete=False)
        event = rows(self.root / 'attack_events.csv')[0]
        self.assertEqual(event['status'],'incomplete')
        self.assertEqual(event['actual_end_seconds'],'')
        self.assertEqual(event['drained_end_seconds'],'')
        self.assertEqual(self.gt.is_attack_active(21),1)
        self.assertIsNone(self.gt.is_attack_active(31))
        request = rows(self.root / 'request_log.csv')[0]
        self.assertEqual(request['outcome'],'incomplete')
        self.assertEqual(request['end_timestamp'],'')
        self.clock.now = 35
        self.assertIsNone(self.logger.finish(attack,MagicMock(status_code=200)))
        self.assertEqual(len(rows(self.root / 'request_log.csv')),1)

    def test_multiple_events_and_overlap_supported_without_burst_generator(self):
        self.begin_attack()
        self.gt.plan_event('attack_001','event_002','continuous',22,30)
        self.clock.now = 22
        self.gt.activate('event_002')
        self.gt.admit('event_002')
        self.logger.begin('attack',1,'url','event_002')
        self.assertEqual(self.gt.active_event_ids(22),['event_001','event_002'])
        self.clock.now = 23
        self.gt.stop('event_001')
        self.assertEqual(self.gt.active_event_ids(24),['event_002'])

    def test_metrics_are_temporal_not_traffic_class(self):
        from simulator import main_orchestrator as main
        self.begin_attack()
        self.clock.now = 22
        with patch.object(main.config,'METRICS_LOG_FILE',str(self.root/'metrics.csv')):
            with open(main.config.METRICS_LOG_FILE,'w',newline='') as f:
                csv.DictWriter(f,fieldnames=main.METRICS_FIELDS).writeheader()
            main.log_metrics_to_csv(self.gt,1,0,1,0,'NO_ACTION',['target'],0)
        row = rows(self.root/'metrics.csv')[0]
        self.assertEqual(row['attack_active'],'1')
        self.assertNotIn('label',row)
        self.assertNotIn('traffic_class',row)
        self.assertEqual(float(row['elapsed_seconds']),22)

    def test_real_executor_queued_after_stop_and_bounded_drain(self):
        from simulator import traffic_injectorV0 as attack
        from simulator.experiment_config import AttackConfig
        gt = GroundTruth('executor', self.root/'executor_events.csv')
        gt.plan_event('A','E','continuous',0,1)
        logger = RequestLogger(gt,self.root/'executor_requests.csv')
        entered, release = threading.Event(), threading.Event()
        session = MagicMock()
        calls = []
        def get(*args, **kwargs):
            calls.append(len(calls))
            if len(calls) == 1:
                entered.set()
                self.assertTrue(release.wait(2))
            return MagicMock(status_code=200)
        session.get.side_effect = get
        with patch.object(attack,'attack_active',False):
            attack.configure(AttackConfig(max_concurrent_sends=1),42,gt,logger)
            gt.activate('E')
            counters, lock = {'ok':0,'err':0}, threading.Lock()
            futures = []
            for i in range(2):
                self.assertTrue(gt.admit('E'))
                future = attack._send_pool.submit(attack._send_one,session,'url',counters,lock,0,'E')
                attack._track_future(future)
                futures.append(future)
                if i == 0:
                    self.assertTrue(entered.wait(2))
            gt.stop('E')
            self.assertIsNone(gt.event('E')['actual_end_seconds'])
            self.assertFalse(attack.drain(timeout=0))
            release.set()
            for f in futures:
                f.result(timeout=2)
            self.assertTrue(attack.drain(timeout=2))
        self.assertTrue(logger.finalize())
        gt.finalize()
        data=rows(self.root/'executor_requests.csv')
        event=gt.event('E')
        self.assertEqual(len(data),2)
        self.assertGreater(float(data[1]['elapsed_seconds']),event['stop_requested_seconds'])
        self.assertLess(float(data[1]['elapsed_seconds']),event['actual_end_seconds'])
        self.assertGreater(float(data[1]['end_elapsed_seconds']),event['actual_end_seconds'])
        self.assertTrue(all(r['traffic_class']=='attack' and r['attack_active']=='1' for r in data))
        self.assertEqual(event['status'],'completed')

    def test_positive_poisson_draw_unchanged_with_ground_truth(self):
        import random
        from concurrent.futures import Future
        from simulator import normal_traffic, traffic_injectorV0
        from simulator.experiment_config import NormalTrafficConfig, AttackConfig, worker_seed
        for module, settings, flag, worker, component in [
            (normal_traffic,NormalTrafficConfig(rate=3),'traffic_active',normal_traffic.normal_http_request_worker,'normal'),
            (traffic_injectorV0,AttackConfig(rate=7),'attack_active',traffic_injectorV0.http_request_worker,'attack')]:
            with self.subTest(generator=component), patch.object(module,flag,False):
                gt=GroundTruth('poisson',self.root/'poisson_events.csv')
                gt.plan_event('A','event_001','continuous',0,1)
                gt.activate('event_001')
                module.configure(settings,42,gt,None)
                module.update_targets(['http://localhost:8080'])
                done=Future(); done.set_result(None)
                def submit(*args):
                    setattr(module,flag,False)
                    return done
                setattr(module,flag,True)
                with patch.object(module._send_pool,'submit',side_effect=submit), \
                     patch.object(module,'_event_id','event_001',create=True), \
                     patch.object(module._stop_event,'wait') as wait, \
                     patch('builtins.print'), \
                     patch.object(module,'normal_traffic_summary_logger' if component=='normal' else 'attack_summary_logger'):
                    worker(settings.rate,2)
                    expected=random.Random(worker_seed(42,component,2)).expovariate(settings.rate)
                    wait.assert_called_once_with(expected)
                module._send_pool.shutdown()

    def test_shutdown_records_incomplete_and_persists_before_stopping_capture(self):
        from simulator import main_orchestrator as main
        self.begin_attack()
        self.gt.admit('event_001')
        self.clock.now = 30
        modules=[MagicMock(),MagicMock()]
        modules[0].__name__='attack'; modules[1].__name__='normal'
        modules[0].drain.return_value=False
        modules[1].drain.return_value=True
        sniffer, manager = MagicMock(),MagicMock()
        def stopped():
            self.assertTrue(self.logger._closed)
            self.assertEqual(rows(self.root/'request_log.csv')[0]['outcome'],'incomplete')
            self.assertEqual(rows(self.root/'attack_events.csv')[0]['status'],'incomplete')
        sniffer.stop.side_effect=stopped
        with patch.multiple(main, ground_truth=self.gt, request_logger=self.logger,
                            sniffer=sniffer, stats_collector=None,
                            traffic_injectorV0=modules[0], normal_traffic=modules[1],
                            docker_manager=manager, create=True), \
             patch.object(main.config,'RUN_STATUS_FILE',str(self.root/'run_status.json')), \
             patch.object(main.config,'RTT_LOG_FILE',str(self.root/'rtt_log.csv')), \
             patch('builtins.print'):
            main._shutdown('error')
        status=json.loads((self.root/'run_status.json').read_text())
        self.assertEqual(status['status'],'incomplete')
        self.assertFalse(status['producers_drained'])
        self.assertTrue(status['errors'])
        manager.cleanup_all_simulation_instances.assert_not_called()

    def test_archive_preserves_new_logs_and_does_not_relabel_history(self):
        from experiments.result_archive import move_result
        self.logger.finalize()
        status=self.root/'run_status.json'
        status.write_text(json.dumps({'run_id':self.gt.run_id}))
        metrics=self.root/'simulation_metrics.csv'
        metrics.write_text('run_id,attack_active\n'+self.gt.run_id+',0\n')
        destination=self.root/'archive'; destination.mkdir()
        move_result(metrics,destination/'metrics_example.csv')
        for name in ['attack_events_example.csv','request_log_example.csv','run_status_example.json']:
            self.assertTrue((destination/name).exists())
        metrics.write_text('label\nnormal\n')
        move_result(metrics,destination/'metrics_historical.csv')
        self.assertEqual((destination/'metrics_historical.csv').read_text(),'label\nnormal\n')


if __name__ == '__main__':
    unittest.main()
