"""Stage 10 contract tests using temporary Stage 8/9 synthetic datasets."""
import csv
from decimal import Decimal, localcontext, ROUND_UP
import json
from pathlib import Path
import unittest

from experiments.dataset_provenance import sha256_file
from experiments.extract_features import extract_features
from experiments.feature_schema import FEATURES, KEYS
from experiments.validate_dataset import DatasetValidator, validate_dataset, write_report
from tests import test_dataset_validation as fixtures


class FeatureExtractionTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.ScientificValidationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root;self.dataset=self.fixture.dataset
        self.report_path=self.root/'stage9.json'
        self.output=self.root/'features'
        self.report()

    def report(self):
        result=validate_dataset(self.dataset)
        self.assertTrue(result['analysis_eligible'],result)
        self.fixture.put_json(self.report_path,result)

    def extract(self,width='1',output=None):
        return extract_features(self.dataset,self.report_path,output or self.output,width)

    def rows(self,family,output=None):
        with ((output or self.output)/f'timeseries/{family}.csv').open() as stream:
            return list(csv.DictReader(stream))

    def source_rows(self,relative):
        with (self.dataset/relative).open() as stream:return list(csv.DictReader(stream))

    def events(self):
        rows=self.source_rows('raw/attacks/attack_events.csv')
        for r in rows:
            for k in ['actual_start_seconds','actual_end_seconds','activation_requested_seconds','last_request_start_seconds']:
                r[k]=float(r[k]) if r[k] else None
        return rows

    def change_requests(self,callback):
        rows=self.source_rows('raw/service/request_log.csv');callback(rows)
        for row in rows:
            start=float(row['elapsed_seconds'])
            row['timestamp']=100+start
            active,ids=DatasetValidator.event_context(self.events(),start)
            row['attack_active']=active;row['active_event_ids']=json.dumps(ids)
            if row['end_elapsed_seconds']!='':
                end=float(row['end_elapsed_seconds']);row['end_timestamp']=100+end;row['duration_ms']=(end-start)*1000
        self.fixture.put_csv(self.dataset/'raw/service/request_log.csv','requests',rows);self.fixture.refresh('raw/service/request_log.csv')
        rtts=[dict(timestamp=r['end_timestamp'],rtt=r['duration_ms'],run_id=r['run_id'],request_id=r['request_id'],traffic_class=r['traffic_class'],elapsed_seconds=r['end_elapsed_seconds']) for r in rows if r['outcome']=='response']
        self.fixture.put_csv(self.dataset/'raw/service/rtt_log.csv','rtt',rtts);self.fixture.refresh('raw/service/rtt_log.csv');self.report()

    def change_metrics(self,callback):
        rows=self.source_rows('raw/infrastructure/simulation_metrics.csv');callback(rows)
        for r in rows:
            t=float(r['elapsed_seconds']);r['timestamp']=100+t;r['elapsed_time_s']=round(t,2)
            r['attack_active'],ids=DatasetValidator.event_context(self.events(),t);r['active_event_ids']=json.dumps(ids)
        rows.sort(key=lambda r:float(r['elapsed_seconds']))
        self.fixture.put_csv(self.dataset/'raw/infrastructure/simulation_metrics.csv','metrics',rows);self.fixture.refresh('raw/infrastructure/simulation_metrics.csv');self.report()

    def test_decimal_border_point_three_belongs_to_window_three(self):
        self.change_requests(lambda r:r[1].update(elapsed_seconds='0.3',end_elapsed_seconds='0.4'))
        self.extract('0.1');rows=self.rows('service')
        self.assertEqual(rows[2]['request_starts'],'0')
        self.assertEqual(rows[3]['request_starts'],'1')
        self.assertEqual(rows[3]['request_completions'],'0')
        self.assertEqual(rows[4]['request_completions'],'1')
        self.assertEqual((rows[3]['window_start_seconds'],rows[3]['window_end_seconds']),('0.3','0.4'))

    def test_empty_window_zero_counts_null_means(self):
        self.extract()
        service=self.rows('service')[1];network=self.rows('network')[1];infra=self.rows('infrastructure')[1]
        self.assertEqual(service['request_starts'],'0');self.assertEqual(service['request_completions'],'0')
        self.assertEqual(service['mean_duration_ms'],'')
        self.assertTrue(all(network[n]=='0' for n in FEATURES['network']))
        self.assertTrue(all(infra[n]=='' for n in FEATURES['infrastructure']))

    def test_start_and_completion_use_separate_windows(self):
        self.extract();r=self.rows('service')
        self.assertEqual(r[2]['request_starts'],'2');self.assertEqual(r[2]['request_completions'],'1')
        self.assertEqual(r[3]['request_starts'],'0');self.assertEqual(r[3]['request_completions'],'1')
        self.assertEqual(Decimal(r[3]['mean_duration_ms']),Decimal(1000))

    def test_completion_exactly_at_integer_border(self):
        self.change_requests(lambda r:r[1].update(elapsed_seconds='0.25',end_elapsed_seconds='1'))
        self.extract();r=self.rows('service')
        self.assertEqual(r[0]['request_completions'],'0');self.assertEqual(r[1]['request_completions'],'1')

    def test_periodic_silence_has_global_overlap_and_no_attack_starts(self):
        self.extract();labels=self.rows('labels')
        self.assertEqual(labels[3]['attack_request_starts'],'0')
        self.assertEqual(labels[3]['attack_event_overlap_seconds'],'1')
        self.assertEqual(labels[3]['attack_event_overlap_fraction'],'1')
        self.assertEqual(self.rows('service')[3]['request_completions'],'1')

    def test_partial_integral_and_zero_overlap(self):
        self.extract();labels=self.rows('labels')
        self.assertEqual(labels[2]['attack_event_overlap_seconds'],'0.8')
        self.assertEqual(labels[6]['attack_event_overlap_seconds'],'0.3')
        self.assertEqual(labels[3]['attack_event_overlap_fraction'],'1')
        self.assertEqual(labels[1]['attack_event_overlap_fraction'],'0')

    def test_event_exact_border_semiopen(self):
        self.fixture.csv_change('raw/attacks/attack_events.csv','attacks',lambda r:r[0].update(actual_end_seconds=6,stop_requested_seconds=6))
        # Update already-observed contexts at t=7 remain zero; starts are before end.
        self.report();self.extract();labels=self.rows('labels')
        self.assertEqual(labels[5]['attack_event_overlap_seconds'],'1')
        self.assertEqual(labels[6]['attack_event_overlap_seconds'],'0')

    def test_absent_cpu_sample_is_null(self):
        self.extract();self.assertEqual(self.rows('infrastructure')[1]['mean_cpu_percent'],'')

    def test_initial_placeholder_zero_excluded_and_diagnosed(self):
        self.change_metrics(lambda r:r[0].update(mem_usage='0',average_cpu_percent='0'))
        manifest=self.extract()
        self.assertEqual(self.rows('infrastructure')[0]['mean_cpu_percent'],'')
        self.assertEqual(self.rows('infrastructure')[0]['mean_memory_mib'],'')
        self.assertEqual(manifest['diagnostics']['infrastructure_without_support'][0]['window_index'],0)
        self.assertEqual(manifest['diagnostics']['infrastructure_without_support'][0]['reported_cpu_percent'],'0')

    def test_supported_zero_is_not_null(self):
        self.change_metrics(lambda r:r[0].update(active_containers_names='victim',mem_usage='0',average_cpu_percent='0'))
        self.extract();r=self.rows('infrastructure')[0]
        self.assertEqual(r['mean_cpu_percent'],'0');self.assertEqual(r['mean_memory_mib'],'0')

    def test_multiple_supported_samples_equal_weight_mean(self):
        def change(rows):
            rows[1].update(active_containers_names='victim',average_cpu_percent='10',mem_usage='3')
            rows.append(dict(rows[1],elapsed_seconds='2.75',average_cpu_percent='30',mem_usage='5'))
        self.change_metrics(change);self.extract();r=self.rows('infrastructure')[2]
        self.assertEqual(r['mean_cpu_percent'],'20');self.assertEqual(r['mean_memory_mib'],'4')

    def test_packet_directions_proxy_not_counted_as_client_no_dedup(self):
        def change(rows):
            rows[1]['packet_length']='100';rows.append(rows[1].copy())
            rows.append(dict(rows[1],src_ip='172.20.0.2',src_port='80',dst_ip='172.20.0.4',dst_port='42000',packet_length='150'))
            rows.sort(key=lambda p:float(p['elapsed_seconds']))
        self.fixture.csv_change('raw/traffic/traffic_capture.csv','packets',change);self.report();self.extract()
        r=self.rows('network')[2]
        self.assertEqual(r['ingress_packet_count'],'2');self.assertEqual(r['egress_packet_count'],'1')
        self.assertEqual(r['ingress_tcp_payload_length_sum_bytes'],'200');self.assertEqual(r['egress_tcp_payload_length_sum_bytes'],'150')
        self.assertEqual(r['unique_client_src_ips'],'1')

    def test_direct_segment_preserves_packets_payload_and_repeated_records(self):
        self.fixture.json_change('metadata/effective_config.json',lambda c:c.update(topology={'mode':'direct'},load_balancer={'enabled':False}))
        old=self.dataset/'metadata/topology/proxy'
        new=old.with_name('direct');old.rename(new)
        path=new/'capture_metadata.json'
        self.fixture.put_json(path,dict(run_id='run1',segment='source_victim',topology='direct',
            victim_ip='172.20.0.2',target_ip='172.20.0.2',target_id='victim',target_port=80))
        manifest_path=self.dataset/'dataset_manifest.json'
        manifest=json.loads(manifest_path.read_text())
        for entry in manifest['files']:
            if entry['path'].startswith('metadata/topology/proxy/'):
                entry['path']=entry['path'].replace('/proxy/','/direct/')
                p=self.dataset/entry['path'];entry.update(sha256=sha256_file(p),bytes=p.stat().st_size)
        self.fixture.put_json(manifest_path,manifest)
        def packets(rows):
            rows[1]['packet_length']='12';rows.append(rows[1].copy())
            rows.sort(key=lambda p:float(p['elapsed_seconds']))
        self.fixture.csv_change('raw/traffic/traffic_capture.csv','packets',packets)
        self.report();m=self.extract()
        self.assertEqual(m['network_direction']['segment'],'source_victim')
        self.assertEqual(self.rows('network')[0]['ingress_packet_count'],'1')
        self.assertEqual(self.rows('network')[0]['ingress_tcp_payload_length_sum_bytes'],'0')
        self.assertEqual(self.rows('network')[2]['ingress_packet_count'],'2')
        self.assertEqual(self.rows('network')[2]['ingress_tcp_payload_length_sum_bytes'],'24')

    def test_unknown_capture_segment_rejected_by_validator(self):
        self.fixture.json_change('metadata/topology/proxy/capture_metadata.json',lambda c:c.update(segment='unknown'))
        report=validate_dataset(self.dataset)
        self.assertFalse(report['dataset_valid'])
        self.assertTrue(any(c['check_id']=='CAPTURE_TOPOLOGY_VALID' and not c['passed'] for c in report['checks']))

    def test_source_causal_class_not_used_by_network(self):
        self.extract();network=(self.output/'timeseries/network.csv').read_bytes()
        # Stage 9 is the eligibility authority. Change only irrelevant inventory class
        # in this controlled copy and rebind a synthetic report to test non-use.
        self.fixture.json_change('metadata/source_inventory.json',lambda s:[x.update(traffic_class='ignored_by_network') for x in s])
        report=json.loads(self.report_path.read_text());report['dataset_manifest_sha256']=sha256_file(self.dataset/'dataset_manifest.json')
        self.fixture.put_json(self.report_path,report)
        output=self.root/'second';self.extract(output=output)
        self.assertEqual(network,(output/'timeseries/network.csv').read_bytes())

    def test_all_completed_failure_kinds_counted_and_included_in_mean(self):
        def change(rows):
            original=rows[1]
            for name,outcome,status,error in [('http','http_error','503',''),('transport','transport_error','','ConnectionError'),('client','client_error','','ValueError')]:
                rows.append(dict(original,request_id=name,outcome=outcome,http_status=status,error_type=error))
        self.change_requests(change);self.extract();r=self.rows('service')[2]
        self.assertEqual(r['request_completions'],'4');self.assertEqual(r['request_failures'],'3')
        self.assertEqual((r['http_failures'],r['transport_failures'],r['client_failures']),('1','1','1'))
        raw=self.source_rows('raw/service/request_log.csv')
        self.assertEqual(Decimal(r['mean_duration_ms']),Decimal(raw[1]['duration_ms']))

    def test_tail_after_plan_preserved_with_full_last_window(self):
        self.change_requests(lambda r:r[1].update(elapsed_seconds='7.5',end_elapsed_seconds='8.25'))
        m=self.extract();r=self.rows('service')
        self.assertEqual(m['window']['windows'],9);self.assertEqual(r[8]['request_completions'],'1')
        self.assertEqual(m['window']['grid_end_seconds'],'9')
        self.assertEqual(m['window']['padding_after_observations_and_plan_seconds'],'0.75')
        self.assertFalse(m['window']['padding_is_observed_coverage'])

    def test_observation_exactly_at_planned_end_gets_next_window(self):
        self.change_requests(lambda r:r[1].update(elapsed_seconds='7.5',end_elapsed_seconds='8'))
        m=self.extract();self.assertEqual(m['window']['windows'],9)
        self.assertEqual(self.rows('service')[8]['request_completions'],'1')

    def test_ineligible_report_rejected(self):
        report=json.loads(self.report_path.read_text());report['analysis_eligible']=False;self.fixture.put_json(self.report_path,report)
        with self.assertRaisesRegex(ValueError,'not analysis_eligible'):self.extract()
        self.assertFalse(self.output.exists())

    def test_report_from_different_manifest_rejected(self):
        report=json.loads(self.report_path.read_text());report['dataset_manifest_sha256']='a'*64;self.fixture.put_json(self.report_path,report)
        with self.assertRaisesRegex(ValueError,'does not correspond'):self.extract()

    def test_report_from_different_run_rejected(self):
        report=json.loads(self.report_path.read_text());report['run_id']='other';self.fixture.put_json(self.report_path,report)
        with self.assertRaisesRegex(ValueError,'does not correspond'):self.extract()

    def test_input_changed_after_validation_rejected(self):
        with (self.dataset/'raw/service/request_log.csv').open('a') as f:f.write('\n')
        with self.assertRaisesRegex(ValueError,'hash/size mismatch'):self.extract()

    def test_topology_changed_after_validation_rejected(self):
        (self.dataset/'metadata/source_inventory.json').write_text('[]')
        with self.assertRaisesRegex(ValueError,'hash/size mismatch'):self.extract()

    def test_deterministic_all_output_bytes(self):
        self.extract();second=self.root/'second';self.extract(output=second)
        first={p.relative_to(self.output):p.read_bytes() for p in self.output.rglob('*') if p.is_file()}
        other={p.relative_to(second):p.read_bytes() for p in second.rglob('*') if p.is_file()}
        self.assertEqual(first,other)

    def test_readonly_dataset_and_report(self):
        paths=[p for p in self.dataset.rglob('*') if p.is_file()]+[self.report_path]
        before={p:(sha256_file(p),p.stat().st_mtime_ns) for p in paths}
        self.extract();self.assertEqual(before,{p:(sha256_file(p),p.stat().st_mtime_ns) for p in paths})

    def test_no_labels_or_causal_fields_in_feature_tables(self):
        self.extract()
        for family,names in FEATURES.items():
            rows=self.rows(family)
            self.assertEqual(list(rows[0]),KEYS+names)
            self.assertFalse(any(k in rows[0] for k in ('traffic_class','attack_active','event_id','profile','attack_request_starts','attack_event_overlap_fraction')))
        s=json.loads((self.output/'feature_schema.json').read_text())
        self.assertEqual(s['tables']['labels']['detector_columns'],[])

    def test_coverage_metadata_family_spans_and_output_hashes(self):
        m=self.extract()
        self.assertEqual(m['observed_coverage']['service_completions']['last_seconds'],'6.2')
        self.assertIsNone(m['observed_coverage']['infrastructure_supported']['first_seconds'])
        self.assertEqual(m['observed_coverage']['network']['completeness'],'not_proven')
        for entry in m['outputs']:self.assertEqual(entry['sha256'],sha256_file(self.output/entry['path']))
        self.assertEqual(m['stage9_validation_report']['sha256'],sha256_file(self.report_path))

    def test_invalid_window_sizes_rejected(self):
        for width in ['0','-1','nan','Infinity','invalid']:
            with self.subTest(width=width),self.assertRaises(ValueError):self.extract(width)

    def test_no_overwrite_or_output_inside_dataset(self):
        with self.assertRaisesRegex(ValueError,'separate'):self.extract(output=self.dataset/'features')
        self.extract()
        with self.assertRaisesRegex(ValueError,'already exists'):self.extract()

    def test_legacy_without_source_proxy_network_is_null_not_zero(self):
        self.fixture.json_change('metadata/source_inventory.json',lambda s:s.clear())
        manifest=json.loads((self.dataset/'dataset_manifest.json').read_text());manifest['source_inventory']=None
        self.fixture.put_json(self.dataset/'dataset_manifest.json',manifest)
        report=json.loads(self.report_path.read_text());report['dataset_manifest_sha256']=sha256_file(self.dataset/'dataset_manifest.json')
        self.fixture.put_json(self.report_path,report)
        m=self.extract();self.assertFalse(m['network_direction']['supported'])
        self.assertTrue(all(r[n]=='' for r in self.rows('network') for n in FEATURES['network']))

    def test_unfinished_attempt_has_no_invented_completion_failure(self):
        self.change_requests(lambda r:r[1].update(outcome='incomplete',end_elapsed_seconds='',end_timestamp='',duration_ms='',http_status=''))
        m=self.extract();r=self.rows('service')[2]
        self.assertEqual(r['request_starts'],'2');self.assertEqual(r['request_completions'],'0')
        self.assertEqual(r['request_failures'],'0');self.assertEqual(r['mean_duration_ms'],'')
        self.assertEqual(m['diagnostics']['unfinished_request_ids'],['n1'])

    def test_decimal_rounding_context_does_not_change_outputs(self):
        self.extract('0.3');other=self.root/'other-context'
        with localcontext() as context:
            context.prec=6;context.rounding=ROUND_UP
            self.extract('0.3',output=other)
        self.assertEqual((self.output/'timeseries/labels.csv').read_bytes(),(other/'timeseries/labels.csv').read_bytes())
        self.assertEqual((self.output/'timeseries/service.csv').read_bytes(),(other/'timeseries/service.csv').read_bytes())

    def test_negative_elapsed_refused_not_dropped(self):
        self.fixture.csv_change('raw/traffic/traffic_capture.csv','packets',lambda r:r[0].update(timestamp='99.5',elapsed_seconds='-0.5'))
        self.report()
        with self.assertRaisesRegex(ValueError,'Negative elapsed'):self.extract()
        self.assertFalse(self.output.exists())

    def test_malformed_stage9_report_rejected_clearly(self):
        self.fixture.put_json(self.report_path,[])
        with self.assertRaisesRegex(ValueError,'JSON objects'):self.extract()

    def test_unsupported_report_schema_rejected(self):
        report=json.loads(self.report_path.read_text());report['validation_schema_version']=2
        self.fixture.put_json(self.report_path,report)
        with self.assertRaisesRegex(ValueError,'Unsupported'):self.extract()


if __name__=='__main__':unittest.main()
