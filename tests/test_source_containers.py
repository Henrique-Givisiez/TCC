import csv
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from simulator.experiment_config import ExperimentConfig, TrafficSourcesConfig
from simulator.ground_truth import GroundTruth
from simulator.request_logger import RequestLogger
from simulator.source_journal import Journal, JournalGroundTruth
from simulator.source_manager import worker_quotas, validate_clocks
from simulator.source_aggregate import aggregate, records, reconcile


class Clock:
    epoch_initial = 1000
    monotonic_initial = 100
    value = 0
    def sample(self):
        return self.epoch_initial+self.value,self.value
    def elapsed(self):
        return self.value+.001
    def from_epoch(self,timestamp):
        return timestamp-self.epoch_initial


class SourceTests(unittest.TestCase):
    def test_budget_and_configuration_fail_closed(self):
        self.assertEqual(worker_quotas(64,4),[16]*4)
        self.assertEqual(worker_quotas(64,3),[22,21,21])
        self.assertEqual(sum(worker_quotas(64,7)),64)
        with self.assertRaises(ValueError):
            worker_quotas(64,65)
        base = ExperimentConfig(traffic_sources=TrafficSourcesConfig('containers'))
        with self.assertRaises(ValueError):
            base.validate()
        valid = replace(base,load_balancer=replace(base.load_balancer,enabled=True),autoscaler=replace(base.autoscaler,enabled=False))
        valid.validate()
        with self.assertRaises(ValueError):
            replace(valid,normal_traffic=replace(valid.normal_traffic,clients=65)).validate()

    def test_premature_clean_source_exit_is_not_success(self):
        from simulator.source_manager import SourceManager
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root/'normal_1/output'
            output.mkdir(parents=True)
            manager = SourceManager.__new__(SourceManager)
            manager.directory = root
            manager.experiment = ExperimentConfig(duration_seconds=30)
            manager.entries = [dict(source_id='normal_1',source_type='normal',container_id='container',run_id='run')]
            manager.client = MagicMock()
            manager.client.containers.get.return_value = MagicMock(id='container',status='exited',attrs={'State':{'ExitCode':0}})
            (output/'final_status.json').write_text(json.dumps(dict(source_id='normal_1',run_id='run',drained=True,logger_complete=True)))
            for elapsed in (4,30):
                (output/'journal.jsonl').write_text(json.dumps(dict(source_id='normal_1',run_id='run',kind='source_closed',payload=dict(elapsed_seconds=elapsed)))+'\n')
                if elapsed==4:
                    with self.assertRaisesRegex(RuntimeError,'unexpectedly'):
                        manager.verify()
                else:
                    manager.verify()

    def test_noncomparable_clock_rejects_before_release(self):
        container = MagicMock()
        container.exec_run.return_value = MagicMock(exit_code=0,output=json.dumps(dict(monotonic=20,epoch=1000,namespace='different')).encode())
        with tempfile.TemporaryDirectory() as root, patch('simulator.source_manager.time.monotonic',side_effect=[10,30]):
            with self.assertRaisesRegex(RuntimeError,'not demonstrably comparable'):
                validate_clocks([container],Path(root)/'clock.json')

    def test_global_emission_end_does_not_become_drain_end(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            official = GroundTruth('test',root/'events.csv',clock=Clock(),run_id='run')
            official.plan_event('attack_001','event_001','continuous',1,6)
            entries = []
            for index,begin,stop,completion in [(1,2,3,50),(2,4,6,100)]:
                source_id = f'attack_{index}'
                output = root/source_id/'output'
                output.mkdir(parents=True)
                entry = dict(source_id=source_id,source_type='attack',run_id='run')
                entries.append(entry)
                journal = Journal(output/'journal.jsonl',source_id,'run')
                clock = Clock()
                local = JournalGroundTruth('test',output/'events.csv',clock=clock,run_id='run',journal=journal)
                local.plan_event('attack_001','event_001','continuous',1,6)
                local.activate('event_001')
                local.admit('event_001')
                if index==1:
                    local.admit('event_001')
                logger = RequestLogger(local,output/'requests.csv',source_id=source_id,journal=journal)
                clock.value = begin
                first = logger.begin('attack',index-1,'http://edos_service:80/','event_001')
                clock.value = stop
                local.stop('event_001')
                if index==1:
                    self.assertIsNone(local.event('event_001')['actual_end_seconds'])
                    clock.value = 8
                    queued = logger.begin('attack',0,'http://edos_service:80/','event_001')
                    clock.value = 40
                    logger.finish(queued,response=MagicMock(status_code=200))
                clock.value = completion
                logger.finish(first,response=MagicMock(status_code=200))
                local.finalize()
                journal('source_closed',dict(drained=True,logger_complete=True))
            complete,requests = aggregate(official,entries,root,root/'requests.csv',root/'rtt.csv',root/'routing.jsonl',root/'metrics.csv')
            event = official.event('event_001')
            self.assertTrue(complete)
            self.assertEqual(event['actual_start_seconds'],2)
            self.assertEqual(event['actual_end_seconds'],8.001)
            self.assertEqual(event['last_request_start_seconds'],8)
            self.assertEqual(event['drained_end_seconds'],100)
            self.assertEqual(len({r['request_id'] for r in requests}),3)
            self.assertTrue(all(r['attack_active']==1 for r in requests))

    def test_missing_source_does_not_fabricate_global_closure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gt = GroundTruth('test',root/'events.csv',clock=Clock(),run_id='run')
            gt.plan_event('attack_001','event_001','continuous',1,6)
            row = gt.event('event_001')
            row.update(actual_start_seconds=2,last_request_start_seconds=3,actual_end_seconds=4,
                       activation_requested_seconds=1,stop_requested_seconds=4,status='completed',drained_end_seconds=5)
            entries = [dict(source_id='attack_1',source_type='attack'),dict(source_id='attack_2',source_type='attack')]
            reconcile(gt,entries,[dict(kind='event_snapshot',source_id='attack_1',payload=row)],final=True)
            self.assertIsNone(gt.event('event_001')['actual_end_seconds'])
            self.assertIsNone(gt.context(5)[0])

    def test_partial_capture_reconciles_timeline_before_reporting_failure(self):
        from simulator.tcpdump_sniffer import TcpdumpSniffer
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            clock = Clock()
            gt = GroundTruth('test',root/'events.csv',clock=clock,run_id='run')
            gt.plan_event('attack_001','event_001','continuous',1,6)
            capture = TcpdumpSniffer('bridge',root/'packets.csv',gt)
            capture._write_row(dict(time='1002.5',src_ip='172.20.0.3',src_port='40000',dst_ip='172.20.0.2',dst_port='80',length='10'))
            gt.activate('event_001')
            gt.admit('event_001')
            clock.value = 2
            gt.begin_request('event_001')
            clock.value = 3
            gt.stop('event_001')
            capture.process = MagicMock(returncode=1)
            with self.assertRaisesRegex(RuntimeError,'exited with status'):
                capture.stop()
            with (root/'packets.csv').open() as stream:
                self.assertEqual(next(csv.DictReader(stream))['attack_active'],'1')

    def test_archive_keeps_sources_associated_and_rejects_wrong_run(self):
        from experiments.result_archive import move_result
        for inventory_run in ('run','other'):
            with self.subTest(inventory_run=inventory_run), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root/'work'
                source.mkdir()
                (source/'simulation_metrics.csv').write_text('run_id\nrun\n')
                for name in ('attack_events.csv','request_log.csv'):
                    (source/name).write_text('run_id\nrun\n')
                (source/'run_status.json').write_text(json.dumps(dict(run_id='run')))
                (source/'source_artifacts').mkdir()
                (source/'source_artifacts/evidence.json').write_text('{}')
                (source/'source_inventory.json').write_text(json.dumps([dict(run_id=inventory_run,source_id='normal_1')]))
                if inventory_run=='other':
                    with self.assertRaisesRegex(ValueError,'inventory run_id mismatch'):
                        move_result(source/'simulation_metrics.csv',root/'metrics_case.csv')
                else:
                    move_result(source/'simulation_metrics.csv',root/'metrics_case.csv')
                    self.assertTrue((root/'source_artifacts_case/evidence.json').exists())
                    self.assertEqual(json.loads((root/'source_inventory_case.json').read_text())[0]['source_id'],'normal_1')

    def test_journal_identity_and_sequence_are_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root/'normal_1/output'
            output.mkdir(parents=True)
            (output/'journal.jsonl').write_text(json.dumps(dict(sequence=2,source_id='normal_1',run_id='run',kind='x',payload={}))+'\n')
            with self.assertRaises(ValueError):
                records(root,[dict(source_id='normal_1',run_id='run')])


if __name__=='__main__':
    unittest.main()
