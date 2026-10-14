"""Synthetic exported runs and controlled corruption, never real datasets."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from experiments.dataset_provenance import sha256_file
from experiments.dataset_schema import schema
from experiments.export_dataset import export_run
from experiments.validate_dataset import validate_dataset, write_report
from simulator.experiment_config import ExperimentConfig


class ScientificValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.run = self.root / 'run'
        self.run.mkdir()
        self.dataset = self.root / 'dataset'
        self.config = json.loads(ExperimentConfig.from_dict(dict(id='fixture', seed=42, duration_seconds=8,
            infrastructure=dict(initial_instances=1,min_instances=1,max_instances=1),
            load_balancer=dict(enabled=True), traffic_sources=dict(execution='containers'), autoscaler=dict(enabled=False),
            normal_traffic=dict(clients=1,rate=2,endpoint='/light'),
            attack=dict(attackers=1,rate=10,endpoint='/expensive',start_seconds=2,duration_seconds=4,
                        profile='periodic_burst',burst=dict(duration_seconds=1,period_seconds=3)))).to_json())
        self.put_json(self.run/'effective_config.json', self.config)
        self.put_json(self.run/'run_status.json', dict(schema_version=1,experiment_id='fixture',run_id='run1',
            status='completed',errors=[],producers_drained=True,experiment_start_timestamp=100,experiment_start_monotonic=50))
        sources = [dict(source_id=name,source_type=component,traffic_class=cls,worker_index=0,run_id='run1',
                        container_id=name+'_id',container_name=name+'_container',ip=ip,service_endpoint='http://edos_service:80')
                   for name,component,cls,ip in [('normal_1','normal','benign','172.20.0.3'),('attack_1','attack','attack','172.20.0.4')]]
        self.put_json(self.run/'source_inventory.json', sources)
        requests = []
        for name,component,start,end in [('a1','attack',2.2,3.2),('n1','normal',2.5,2.7),('a2','attack',5.2,6.2)]:
            requests.append(dict(run_id='run1',request_id=name,generator=component,worker_id=0,
                target_url='http://edos_service:80'+('/expensive' if component=='attack' else '/light'),
                timestamp=100+start,elapsed_seconds=start,end_timestamp=100+end,end_elapsed_seconds=end,
                duration_ms=(end-start)*1000,traffic_class='attack' if component=='attack' else 'benign',attack_active=1,
                attack_id='attack1' if component=='attack' else None,event_id='event1' if component=='attack' else None,
                active_event_ids='["event1"]',http_status=200,outcome='response',error_type=None))
        self.put_csv(self.run/'request_log.csv','requests',requests)
        self.put_csv(self.run/'rtt_log.csv','rtt',[dict(timestamp=r['end_timestamp'],rtt=r['duration_ms'],run_id='run1',request_id=r['request_id'],
            traffic_class=r['traffic_class'],elapsed_seconds=r['end_elapsed_seconds']) for r in requests])
        self.put_csv(self.run/'attack_events.csv','attacks',[dict(schema_version=1,experiment_id='fixture',run_id='run1',
            experiment_start_timestamp=100,experiment_start_monotonic=50,attack_id='attack1',event_id='event1',profile='periodic_burst',
            scheduled_start_seconds=2,scheduled_end_seconds=6,activation_requested_seconds=2,actual_start_seconds=2.2,
            stop_requested_seconds=6.3,actual_end_seconds=6.3,last_request_start_seconds=5.2,drained_end_seconds=6.2,
            status='completed',end_reason='scheduled_end')])
        self.put_csv(self.run/'simulation_metrics.csv','metrics',[dict(run_id='run1',timestamp=100+t,elapsed_seconds=t,elapsed_time_s=t,
            num_instances=1,average_cpu_percent=0,mem_usage=1,avg_rtt_ms=0,decision='NO_ACTION',active_containers_names='',
            attack_active=int(2.2 <= t < 6.3),active_event_ids='["event1"]' if 2.2 <= t < 6.3 else '[]',host_cpu_percent=0)
            for t in [0.5,2.5,7]])
        self.put_csv(self.run/'traffic_capture.csv','packets',[dict(run_id='run1',timestamp=100+t,elapsed_seconds=t,
            src_ip=ip,src_port=42000,dst_ip='172.20.0.2',dst_port=80,packet_length=0,traffic_class='unknown',
            attack_active=int(2.2 <= t < 6.3),active_event_ids='["event1"]' if 2.2 <= t < 6.3 else '[]')
            for t,ip in [(0.5,'172.20.0.3'),(2.5,'172.20.0.4'),(7,'172.20.0.3')]])
        self.put_json(self.run/'proxy_artifacts/capture_metadata.json',dict(run_id='run1',segment='source_proxy',proxy_ip='172.20.0.2'))
        export_run(self.run,self.dataset)

    @staticmethod
    def put_json(path, value):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value),encoding='utf-8')

    @staticmethod
    def put_csv(path, table, rows):
        with path.open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=[f['name'] for f in schema()['tables'][table]['fields']])
            writer.writeheader();writer.writerows(rows)

    def refresh(self, relative):
        path=self.dataset/relative
        manifest=json.loads((self.dataset/'dataset_manifest.json').read_text())
        for entry in manifest['files']:
            if entry['path']==relative:
                entry.update(sha256=sha256_file(path),bytes=path.stat().st_size)
        self.put_json(self.dataset/'dataset_manifest.json',manifest)

    def json_change(self, relative, callback):
        path=self.dataset/relative
        value=json.loads(path.read_text());callback(value);self.put_json(path,value);self.refresh(relative)

    def csv_change(self, relative, table, callback):
        path=self.dataset/relative
        with path.open() as f:rows=list(csv.DictReader(f))
        callback(rows);self.put_csv(path,table,rows);self.refresh(relative)

    def report(self):
        return validate_dataset(self.dataset)

    def fails(self, identifier):
        report=self.report()
        self.assertFalse(report['dataset_valid'], report)
        self.assertTrue(any(c['check_id']==identifier and c['passed'] is False for c in report['checks']),report)

    def test_valid_periodic_and_independent_drain_before_end(self):
        report=self.report()
        self.assertTrue(report['dataset_valid'],report)
        self.assertTrue(report['analysis_eligible'],report)

    def test_valid_continuous(self):
        self.json_change('metadata/effective_config.json',lambda c:c['attack'].update(profile='continuous',burst=None))
        self.csv_change('raw/attacks/attack_events.csv','attacks',lambda r:r[0].update(profile='continuous'))
        self.assertTrue(self.report()['analysis_eligible'])

    def test_continuous_queued_start_after_planned_end_allowed(self):
        self.json_change('metadata/effective_config.json',lambda c:c['attack'].update(profile='continuous',burst=None))
        start,end=6.1,6.2
        self.csv_change('raw/service/request_log.csv','requests',lambda r:r[2].update(elapsed_seconds=start,timestamp=100+start,duration_ms=(end-start)*1000))
        self.csv_change('raw/service/rtt_log.csv','rtt',lambda r:r[2].update(rtt=(end-start)*1000))
        self.csv_change('raw/attacks/attack_events.csv','attacks',lambda r:r[0].update(profile='continuous',last_request_start_seconds=start))
        self.assertTrue(self.report()['analysis_eligible'],self.report())

    def test_incomplete_intact_but_ineligible(self):
        self.json_change('metadata/run_status.json',lambda s:s.update(status='incomplete',errors=['proxy exited']))
        path=self.dataset/'dataset_manifest.json';m=json.loads(path.read_text());m['status']='incomplete';self.put_json(path,m)
        report=self.report()
        self.assertTrue(report['dataset_valid']);self.assertFalse(report['analysis_eligible'])

    def test_incomplete_explicitly_missing_scientific_data(self):
        self.test_incomplete_intact_but_ineligible()
        path=self.dataset/'dataset_manifest.json';m=json.loads(path.read_text())
        m['files']=[e for e in m['files'] if e['path']!='raw/traffic/traffic_capture.csv'];self.put_json(path,m)
        (self.dataset/'raw/traffic/traffic_capture.csv').unlink()
        self.assertTrue(self.report()['dataset_valid']);self.assertFalse(self.report()['analysis_eligible'])

    def test_invalid_manifest(self):
        (self.dataset/'dataset_manifest.json').write_text('{bad')
        self.fails('JSON_PARSEABLE')

    def test_unsupported_version(self):
        path=self.dataset/'dataset_manifest.json';m=json.loads(path.read_text());m['schema_version']=99;self.put_json(path,m)
        self.fails('MANIFEST_SCHEMA_SUPPORTED')

    def test_hash_corruption(self):
        with (self.dataset/'raw/service/request_log.csv').open('a') as f:f.write('\n')
        self.fails('FILE_HASH_MATCH')

    def test_size_corruption(self):
        path=self.dataset/'dataset_manifest.json';m=json.loads(path.read_text());m['files'][0]['bytes']+=1;self.put_json(path,m)
        self.fails('FILE_SIZE_MATCH')

    def test_missing_essential_file(self):
        (self.dataset/'raw/service/request_log.csv').unlink()
        self.fails('SCIENTIFIC_ARTIFACT_PRESENT')

    def test_run_id_mismatch(self):
        self.csv_change('raw/service/request_log.csv','requests',lambda r:r[0].update(run_id='other'))
        self.fails('RUN_ID_CONSISTENT')

    def test_nonexistent_source(self):
        self.csv_change('raw/service/request_log.csv','requests',lambda r:r[0].update(worker_id=99))
        self.fails('SOURCE_REFERENCE_VALID')

    def test_nonexistent_event(self):
        self.csv_change('raw/service/request_log.csv','requests',lambda r:r[0].update(event_id='missing'))
        self.fails('EVENT_REFERENCE_VALID')

    def test_duplicate_request_id(self):
        self.csv_change('raw/service/request_log.csv','requests',lambda r:r.append(r[0].copy()))
        self.fails('REQUEST_ID_UNIQUE')

    def test_duplicate_source_id(self):
        self.json_change('metadata/source_inventory.json',lambda s:s.append(s[0].copy()))
        self.fails('SOURCE_IDENTITY_UNIQUE')

    def test_invalid_event_end_before_start(self):
        self.csv_change('raw/attacks/attack_events.csv','attacks',lambda r:r[0].update(actual_end_seconds=1))
        self.fails('EVENT_TEMPORAL_ORDER')

    def test_invalid_event_drain_before_start(self):
        self.csv_change('raw/attacks/attack_events.csv','attacks',lambda r:r[0].update(drained_end_seconds=1))
        self.fails('EVENT_TEMPORAL_ORDER')

    def test_invalid_request_order(self):
        self.csv_change('raw/service/request_log.csv','requests',lambda r:r[0].update(end_elapsed_seconds=1))
        self.fails('REQUEST_TEMPORAL_ORDER')

    def test_periodic_start_in_silence(self):
        self.csv_change('raw/service/request_log.csv','requests',lambda r:r[0].update(elapsed_seconds=3.1,timestamp=103.1,duration_ms=(3.2-3.1)*1000))
        self.fails('ATTACK_START_WINDOW_VALID')

    def test_periodic_start_after_global_end(self):
        self.csv_change('raw/service/request_log.csv','requests',lambda r:r[2].update(elapsed_seconds=6.1,timestamp=106.1,duration_ms=(6.2-6.1)*1000))
        self.fails('ATTACK_START_WINDOW_VALID')

    def test_periodic_start_before_global_start(self):
        self.csv_change('raw/service/request_log.csv','requests',lambda r:r[0].update(elapsed_seconds=1.9,timestamp=101.9,duration_ms=(3.2-1.9)*1000))
        self.fails('ATTACK_START_WINDOW_VALID')

    def test_completion_in_silence_and_benign_in_event_accepted(self):
        report=self.report()
        self.assertTrue(report['dataset_valid'])
        self.assertTrue(next(c for c in report['checks'] if c['check_id']=='GLOBAL_ATTACK_CONTEXT_CONSISTENT')['passed'])

    def test_http_error_is_valid_observation(self):
        self.csv_change('raw/service/request_log.csv','requests',lambda r:r[1].update(outcome='http_error',http_status=503))
        self.csv_change('raw/service/rtt_log.csv','rtt',lambda r:r.pop(1))
        report=self.report()
        self.assertTrue(report['dataset_valid']);self.assertTrue(report['analysis_eligible'])
        self.assertTrue(any(c['check_id']=='REQUEST_FAILURES_OBSERVED' and c['passed'] is False for c in report['checks']))

    def test_transport_error_is_valid_observation(self):
        self.csv_change('raw/service/request_log.csv','requests',lambda r:r[1].update(outcome='transport_error',http_status='',error_type='ConnectionError'))
        self.csv_change('raw/service/rtt_log.csv','rtt',lambda r:r.pop(1))
        self.assertTrue(self.report()['dataset_valid'])

    def test_old_provenance_unknown_is_warning(self):
        report=self.report()
        self.assertTrue(report['dataset_valid'])
        self.assertTrue(any(c['check_id']=='EXECUTION_PROVENANCE_AVAILABLE' and c['severity']=='WARNING' for c in report['checks']))

    def test_readonly_and_deterministic(self):
        before={p:(sha256_file(p),p.stat().st_mtime_ns) for p in self.dataset.rglob('*') if p.is_file()}
        first,second=self.report(),self.report()
        self.assertEqual(first,second)
        self.assertEqual(json.dumps(first,sort_keys=True),json.dumps(second,sort_keys=True))
        write_report(first,self.root/'validation_report.json',self.dataset)
        self.assertEqual(before,{p:(sha256_file(p),p.stat().st_mtime_ns) for p in before})

    def test_report_cannot_be_written_in_dataset(self):
        with self.assertRaisesRegex(ValueError,'outside'):
            write_report(self.report(),self.dataset/'report.json',self.dataset)

    def test_csv_malformed(self):
        path=self.dataset/'raw/service/request_log.csv';path.write_text(path.read_text()+'"unterminated')
        self.refresh('raw/service/request_log.csv');self.fails('CSV_PARSEABLE')

    def test_json_malformed(self):
        (self.dataset/'metadata/source_inventory.json').write_text('{bad')
        self.refresh('metadata/source_inventory.json');self.fails('JSON_PARSEABLE')

    def test_path_escape(self):
        path=self.dataset/'dataset_manifest.json';m=json.loads(path.read_text());m['files'][0]['path']='../outside';self.put_json(path,m)
        self.fails('DATASET_PATH_SAFE')

    def test_symlink_escape(self):
        path=self.dataset/'raw/service/request_log.csv';path.unlink();path.symlink_to(self.run/'request_log.csv')
        self.fails('DATASET_PATH_SAFE')

    def test_nonfinite_numeric_value(self):
        self.csv_change('raw/service/request_log.csv','requests',lambda r:r[0].update(duration_ms='nan'))
        self.fails('CSV_FIELD_VALID')

    def test_incorrect_causal_class(self):
        self.csv_change('raw/service/request_log.csv','requests',lambda r:r[1].update(traffic_class='attack'))
        self.fails('REQUEST_CAUSAL_CLASS_VALID')

    def test_burst_silence_does_not_redefine_attack_active(self):
        self.csv_change('raw/service/request_log.csv','requests',lambda r:r[1].update(elapsed_seconds=3.5,timestamp=103.5,end_elapsed_seconds=3.7,end_timestamp=103.7,duration_ms=(3.7-3.5)*1000))
        self.csv_change('raw/service/rtt_log.csv','rtt',lambda r:r[1].update(elapsed_seconds=3.7,timestamp=103.7,rtt=(3.7-3.5)*1000))
        self.assertTrue(self.report()['dataset_valid'])

    def test_missing_capture_observations_blocks_eligibility(self):
        self.csv_change('raw/traffic/traffic_capture.csv','packets',lambda r:r.clear())
        report=self.report();self.assertTrue(report['dataset_valid']);self.assertFalse(report['analysis_eligible'])

    def test_capture_segment_contradiction(self):
        self.csv_change('raw/traffic/traffic_capture.csv','packets',lambda r:r[0].update(dst_ip='192.0.2.1'))
        self.fails('CAPTURE_SEGMENT_CONSISTENT')

    def test_schema_tampering_cannot_disable_fields(self):
        self.json_change('schema.json',lambda s:s['tables']['requests']['fields'].clear())
        self.fails('TABLE_SCHEMA_SUPPORTED')

    def test_missing_effective_configuration_fields(self):
        self.json_change('metadata/effective_config.json',lambda c:c.pop('normal_traffic'))
        self.fails('CONFIGURATION_VALID')

    def test_malformed_nested_schema_is_reported(self):
        self.json_change('schema.json',lambda s:s.update(tables=[]))
        self.fails('TABLE_SCHEMA_SUPPORTED')

    def add_execution_provenance(self):
        files={'simulator/example.py':'a'*64}
        value=dict(schema_version=1,scope='execution_before_invocation',run_id='run1',
            code=dict(git=dict(status='recorded',commit='a'*40,dirty=False),runtime_files_sha256=files,
                      runtime_tree_sha256=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()),
            host_environment=dict(python='3.12',platform='fixture'))
        relative='metadata/run_provenance.json';path=self.dataset/relative;self.put_json(path,value)
        m=json.loads((self.dataset/'dataset_manifest.json').read_text())
        m['execution_provenance']=dict(status='recorded',path=relative)
        m['files'].append(dict(path=relative,bytes=path.stat().st_size,sha256=sha256_file(path),group='metadata',role='canonical'))
        self.put_json(self.dataset/'dataset_manifest.json',m)

    def test_recorded_provenance_consistent(self):
        self.add_execution_provenance()
        self.assertTrue(self.report()['analysis_eligible'])

    def test_recorded_fingerprint_mismatch(self):
        self.add_execution_provenance()
        self.json_change('metadata/run_provenance.json',lambda p:p['code'].update(runtime_tree_sha256='b'*64))
        self.fails('EXECUTION_PROVENANCE_CONSISTENT')

    def test_recorded_dirty_type_invalid(self):
        self.add_execution_provenance()
        self.json_change('metadata/run_provenance.json',lambda p:p['code']['git'].update(dirty='yes'))
        self.fails('EXECUTION_PROVENANCE_CONSISTENT')

    def test_dirty_execution_is_warning_not_corruption(self):
        self.add_execution_provenance()
        self.json_change('metadata/run_provenance.json',lambda p:p['code']['git'].update(dirty=True))
        report=self.report();self.assertTrue(report['dataset_valid']);self.assertTrue(report['analysis_eligible'])

    def add_attack_journal(self, admission_time=None):
        with (self.dataset/'raw/service/request_log.csv').open() as stream:
            rows=list(csv.DictReader(stream))
        records=[]
        for row in [rows[0],rows[2]]:
            for kind,payload in [('admission',dict(event_id=row['event_id'],elapsed_seconds=float(row['elapsed_seconds']))),
                                 ('request_begin',dict(request_id=row['request_id'],generator='attack',worker_id=0,event_id=row['event_id'],elapsed_seconds=float(row['elapsed_seconds']),target_url=row['target_url']))]:
                records.append(dict(source_id='attack_1',run_id='run1',sequence=len(records)+1,kind=kind,payload=payload))
        if admission_time is not None:
            records[0]['payload']['elapsed_seconds']=admission_time
        relative='evidence/sources/attack_1/output/journal.jsonl';path=self.dataset/relative;path.parent.mkdir(parents=True)
        path.write_text(''.join(json.dumps(r)+'\n' for r in records))
        m=json.loads((self.dataset/'dataset_manifest.json').read_text())
        m['files'].append(dict(path=relative,bytes=path.stat().st_size,sha256=sha256_file(path),group='evidence',role='operational'))
        self.put_json(self.dataset/'dataset_manifest.json',m)

    def test_periodic_journal_no_backlog(self):
        self.add_attack_journal()
        self.assertTrue(self.report()['analysis_eligible'])

    def test_periodic_admission_in_silence_rejected(self):
        self.add_attack_journal(admission_time=4)
        self.fails('PERIODIC_ADMISSION_NO_BACKLOG')

    def test_periodic_backlog_even_between_valid_burst_samples_rejected(self):
        self.add_attack_journal(admission_time=2.1)
        self.fails('PERIODIC_ADMISSION_NO_BACKLOG')

    def test_wrong_global_label_rejected(self):
        self.csv_change('raw/service/request_log.csv','requests',lambda r:r[1].update(attack_active=0))
        self.fails('GLOBAL_ATTACK_CONTEXT_CONSISTENT')

    def test_old_rtt_is_not_silently_interpreted_as_tcp_rtt(self):
        self.csv_change('raw/service/rtt_log.csv','rtt',lambda r:r[0].update(elapsed_seconds=2.2))
        self.fails('HTTP_DURATION_REFERENCE_VALID')

    def test_optional_evidence_absent_only_warns(self):
        self.add_attack_journal()
        (self.dataset/'evidence/sources/attack_1/output/journal.jsonl').unlink()
        report=self.report();self.assertTrue(report['dataset_valid']);self.assertTrue(report['analysis_eligible'])

    def test_epoch_backwards_warns_without_changing_monotonic_time(self):
        self.csv_change('raw/service/request_log.csv','requests',lambda r:r[1].update(end_timestamp=99))
        self.csv_change('raw/service/rtt_log.csv','rtt',lambda r:r[1].update(timestamp=99))
        report=self.report();self.assertTrue(report['dataset_valid']);self.assertTrue(report['analysis_eligible'])

    def test_request_row_order_is_not_start_order(self):
        self.csv_change('raw/service/request_log.csv','requests',lambda r:r.reverse())
        self.assertTrue(self.report()['dataset_valid'])

    def test_malformed_manifest_reference_reported_without_exception(self):
        path=self.dataset/'dataset_manifest.json';m=json.loads(path.read_text());m['export_provenance']=[];self.put_json(path,m)
        self.fails('CANONICAL_REFERENCE_VALID')

    def test_run_inventory_mismatch(self):
        self.json_change('metadata/source_inventory.json',lambda s:s[0].update(run_id='other'))
        self.fails('SOURCE_RUN_ID_CONSISTENT')

    def test_planned_source_count_mismatch(self):
        self.json_change('metadata/source_inventory.json',lambda s:s.pop())
        self.fails('SOURCE_COUNT_CONFIG_CONSISTENT')

    def test_metric_negative_memory_rejected_without_cpu_expectation(self):
        self.csv_change('raw/infrastructure/simulation_metrics.csv','metrics',lambda r:r[0].update(mem_usage=-1))
        self.fails('METRIC_VALUES_PLAUSIBLE')

    def test_metric_elapsed_order_corruption(self):
        self.csv_change('raw/infrastructure/simulation_metrics.csv','metrics',lambda r:r.reverse())
        self.fails('METRIC_MONOTONIC_ORDER')

    def test_event_last_completion_mismatch(self):
        self.csv_change('raw/attacks/attack_events.csv','attacks',lambda r:r[0].update(drained_end_seconds=6.4))
        self.fails('EVENT_REQUEST_MILESTONES_MATCH')

    def test_operation_mismatch(self):
        self.csv_change('raw/service/request_log.csv','requests',lambda r:r[0].update(target_url='http://edos_service:80/light'))
        self.fails('REQUEST_OPERATION_VALID')

    def test_no_observed_benign_blocks_campaign_not_dataset_integrity(self):
        self.csv_change('raw/service/request_log.csv','requests',lambda r:r.pop(1))
        self.csv_change('raw/service/rtt_log.csv','rtt',lambda r:r.pop(1))
        report=self.report();self.assertTrue(report['dataset_valid']);self.assertFalse(report['analysis_eligible'])

    def test_no_epoch_monotonic_offset_tolerance_required(self):
        self.csv_change('raw/service/request_log.csv','requests',lambda r:r[1].update(timestamp=140,end_timestamp=140.2))
        self.csv_change('raw/service/rtt_log.csv','rtt',lambda r:r[1].update(timestamp=140.2))
        self.assertTrue(self.report()['analysis_eligible'])

    def test_unindexed_container_inventory_not_trusted(self):
        path=self.dataset/'dataset_manifest.json';m=json.loads(path.read_text());m['source_inventory']=None
        m['files']=[e for e in m['files'] if e['path']!='metadata/source_inventory.json'];self.put_json(path,m)
        self.fails('SOURCE_INVENTORY_REFERENCE_VALID')


if __name__=='__main__':
    unittest.main()
