"""Offline D3 pilot processing with synthetic observations; never sends traffic."""
import csv
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments import development_d3 as d3
from experiments.dataset_schema import schema
from experiments.export_dataset import export_run
from experiments.validate_dataset import validate_dataset
from simulator.experiment_config import ExperimentConfig
from simulator.request_logger import REQUEST_FIELDS
from simulator.ground_truth import EVENT_FIELDS


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, default=d3.json_default))


def csvwrite(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def fixture(raw, condition='C', *, recover=True, opened=False, control_bad=False):
    cfg = ExperimentConfig.load(d3.ROOT / f'experiments/configs/development_d3_pilots_20261028/d3_pilot_{condition}.json')
    raw.mkdir()
    run = 'synthetic_' + condition
    put(raw / 'effective_config.json', json.loads(cfg.to_json()))
    allrows, inventory = [], []
    groups = [(f'normal_{i+1}','normal','benign',i,4) for i in range(4)]
    if condition != 'C':
        groups.append(('attack_1','attack','attack',0,cfg.attack.rate))
    event = None
    for sid, generator, cls, worker, rate in groups:
        output = raw / 'source_artifacts' / sid / 'output'
        output.mkdir(parents=True)
        rows, records = [], []
        def log(kind, payload):
            records.append(dict(source_id=sid, run_id=run, sequence=len(records)+1, kind=kind, payload=deepcopy(payload)))
        a,b = (150,270) if cls == 'attack' else (0,390)
        for i in range((b-a)*rate):
            start = a + (i+.25)/rate
            degraded = cls == 'benign' and (condition != 'C' or control_bad) and (150 <= start < 270 or (not recover and start >= 270))
            failure = degraded and i % 5 == 0
            duration = 2 if failure else .5 if degraded else .1 if cls == 'attack' else .05
            end = start + duration
            row = dict.fromkeys(REQUEST_FIELDS, None)
            # Actual first offensive start is 150 + .25/rate.
            active = condition != 'C' and 150+.25/cfg.attack.rate <= start < 270.01
            row.update(run_id=run, request_id=f'request_{sid}_{i+1:09d}', generator=generator, worker_id=worker,
                target_url='http://edos_service:80'+('/expensive' if cls=='attack' else '/medium'),
                timestamp=1000+start, elapsed_seconds=start, traffic_class=cls, attack_active=int(active),
                active_event_ids='["event_001"]' if active else '[]',
                attack_id='attack_001' if cls=='attack' else None, event_id='event_001' if cls=='attack' else None)
            if cls == 'attack':
                log('admission', dict(event_id='event_001', elapsed_seconds=start-.001))
            log('request_begin', row)
            isopen = opened and sid == 'normal_1' and i == (b-a)*rate-1
            if isopen:
                row.update(outcome='incomplete')
            else:
                row.update(end_timestamp=1000+end, end_elapsed_seconds=end, duration_ms=(end-start)*1000,
                           outcome='transport_error' if failure else 'response', error_type='ReadTimeout' if failure else None,
                           http_status=None if failure else 200)
                log('request_finish', row)
            rows.append(row)
        if cls == 'attack':
            event = dict.fromkeys(EVENT_FIELDS, None)
            event.update(schema_version=1, experiment_id=cfg.id, run_id=run,experiment_start_timestamp=1000,
                experiment_start_monotonic=500, attack_id='attack_001',event_id='event_001',profile='continuous',
                scheduled_start_seconds=150,scheduled_end_seconds=270, activation_requested_seconds=150,
                actual_start_seconds=rows[0]['elapsed_seconds'],stop_requested_seconds=270,actual_end_seconds=270.01,
                last_request_start_seconds=rows[-1]['elapsed_seconds'],drained_end_seconds=max(r['end_elapsed_seconds'] for r in rows),
                status='completed',end_reason='scheduled_end')
            log('emission_closed', event)
            log('event_snapshot', event)
            csvwrite(output/'local_events.csv', EVENT_FIELDS, [event])
        else:
            csvwrite(output/'local_events.csv', EVENT_FIELDS, [])
        closed = dict(drained=not(opened and sid=='normal_1'),logger_complete=not(opened and sid=='normal_1'),elapsed_seconds=max([b+.1]+[r['end_elapsed_seconds']+.001 for r in rows if r['end_elapsed_seconds'] is not None]))
        log('source_closed', closed)
        final=dict(source_id=sid,run_id=run,drained=closed['drained'],logger_complete=closed['logger_complete'],reason='simulation_end')
        put(output/'final_status.json',final)
        (output/'journal.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
        csvwrite(output/'local_requests.csv', REQUEST_FIELDS, rows)
        inventory.append(dict(source_id=sid,source_type=generator,traffic_class=cls,worker_index=worker,run_id=run,
            container_id=sid,container_name=sid,ip=f'172.20.0.{len(inventory)+3}',service_endpoint='http://edos_service:80',
            send_workers=64 if cls=='attack' else 16,status_final=dict(state='exited',exit_code=2 if not closed['drained'] else 0,forced=False,**final)))
        allrows.extend(rows)
    csvwrite(raw/'request_log.csv',REQUEST_FIELDS,sorted(allrows,key=lambda r:r['elapsed_seconds']))
    csvwrite(raw/'attack_events.csv',EVENT_FIELDS,[event] if event else [])
    put(raw/'source_inventory.json',inventory)
    status=dict(schema_version=1, experiment_id=cfg.id, run_id=run,status='incomplete' if opened else 'completed',
                errors=[],producers_drained=not opened,end_reason='simulation_end',experiment_start_timestamp=1000,
                experiment_start_monotonic=500,capture_results={})
    for name,artifact,stderr in [('csv',raw/'traffic_capture.csv',raw/'traffic_capture.stderr'),
            ('pcap',raw/'source_artifacts/traffic_capture.pcap',raw/'source_artifacts/traffic_capture.pcap.stderr')]:
        artifact.parent.mkdir(parents=True,exist_ok=True)
        artifact.write_bytes(b'')
        stderr.write_text('0 packets captured\n0 packets received by filter\n0 packets dropped by kernel\n')
        report=dict(accepted=True,returncode=0,capture_diagnostic_sha256=d3.digest(stderr),
            capture_counters=dict(statistics_complete=True,packets_captured=0,packets_received_by_filter=0,packets_dropped_by_kernel=0,
                statistics_occurrences=dict(packets_captured=1,packets_received_by_filter=1,packets_dropped_by_kernel=1)))
        put(Path(str(artifact)+'.capture.json'),report)
        status['capture_results'][name]=report
    put(raw/'run_status.json',status)
    def table(name, kind, rows):
        csvwrite(raw/name,[f['name'] for f in schema()['tables'][kind]['fields']],rows)
    table('rtt_log.csv','rtt',[dict(timestamp=r['end_timestamp'],rtt=r['duration_ms'],run_id=run,request_id=r['request_id'],
        traffic_class=r['traffic_class'],elapsed_seconds=r['end_elapsed_seconds']) for r in allrows if r['outcome']=='response'])
    table('traffic_capture.csv','packets',[dict(run_id=run,timestamp=1000+t,elapsed_seconds=t,
        src_ip='172.20.0.3',src_port=42000,dst_ip='172.20.0.2',dst_port=80,packet_length=0,traffic_class='unknown',
        attack_active=0,active_event_ids='[]') for t in (1,389)])
    metrics=[]
    for t in range(390):
        active = event and event['actual_start_seconds'] <= t < event['actual_end_seconds']
        metrics.append(dict(run_id=run,timestamp=1000+t,elapsed_seconds=t,elapsed_time_s=t,num_instances=1,
            average_cpu_percent=25,mem_usage=23,avg_rtt_ms=50,decision='NO_ACTION',active_containers_names='victim',
            attack_active=int(bool(active)),active_event_ids='["event_001"]' if active else '[]',host_cpu_percent=0))
    table('simulation_metrics.csv','metrics',metrics)
    samples=[dict(run_id=run,container_id='proxy',status=dict(elapsed_seconds=t,success=True,data={}),
                  docker=dict(elapsed_seconds=t,success=True,data={})) for t in range(390)]
    proxy=raw/'proxy_artifacts';proxy.mkdir()
    (proxy/'monitor_samples.jsonl').write_text(''.join(json.dumps(s)+'\n' for s in samples))
    put(proxy/'monitor_summary.json',dict(run_id=run,container_id='proxy',thread_alive=False))
    put(proxy/'capture_metadata.json',dict(run_id=run,segment='source_proxy',proxy_ip='172.20.0.2'))
    return cfg


class D3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory()
        cls.root=Path(cls.temporary.name)
        cls.control_raw=cls.root/'control'
        cls.control_config=fixture(cls.control_raw)
        cls.control=d3.build_review(cls.control_raw,cls.control_config)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def make(self, label, **kwargs):
        raw=self.root/label
        return raw,fixture(raw,'E4',**kwargs)

    def test_real_authority_configs_and_exclusive_seed_reservations(self):
        result=d3.validate_plan()
        self.assertEqual(result['configurations'],3)
        self.assertEqual(len(set(result['pilot_seeds']+result['matrix_seeds_reserved_only'])),5)
        self.assertFalse(set(result['pilot_seeds']) & set(result['matrix_seeds_reserved_only']))
        self.assertFalse(result['docker_accessed'])
        self.assertFalse(result['experiments_executed'])
        plan=d3.read(d3.DEFAULT_MANIFEST)
        plan['entries'][2]['config_sha256']='0'*64
        bad=self.root/'tampered_manifest.json';put(bad,plan)
        with self.assertRaisesRegex(ValueError,'mismatched pilot config'):
            d3.validate_plan(bad)

    def test_control_and_valid_degradation_recovered(self):
        self.assertTrue(self.control['classification']['control_accepted'],self.control['technical_checks'])
        raw,cfg=self.make('valid_degradation')
        report=d3.build_review(raw,cfg,control=self.control)
        self.assertTrue(report['classification']['technical_integrity'],report['technical_checks'])
        self.assertTrue(report['classification']['generator_adherence'])
        self.assertTrue(report['classification']['service_degradation_observed'])
        self.assertTrue(report['progression']['eligible_for_manual_gate'])
        self.assertEqual(report['recovery']['status'],'observed')
        self.assertEqual(report['recovery']['recovered_by_seconds'],360)
        self.assertFalse(report['recovery']['right_censored'])
        dataset=self.root/'valid_degradation_dataset'
        export_run(raw,dataset)
        validation=validate_dataset(dataset)
        self.assertTrue(validation['dataset_valid'],[c for c in validation['checks'] if not c['passed']])
        self.assertTrue(validation['analysis_eligible'],validation['summary'])
        self.assertTrue(any(c['check_id']=='REQUEST_FAILURES_OBSERVED' and not c['passed'] for c in validation['checks']))

    def test_recovery_not_observed_is_censored_not_corrupt(self):
        raw,cfg=self.make('censored',recover=False)
        r=d3.build_review(raw,cfg,control=self.control)
        self.assertTrue(r['classification']['technical_integrity'],r['technical_checks'])
        self.assertEqual(r['recovery']['status'],'not_observed')
        self.assertTrue(r['recovery']['right_censored'])
        self.assertEqual(r['recovery']['censor_at_seconds'],390)
        self.assertFalse(r['progression']['eligible_for_manual_gate'])

    def test_capture_failure_separate_from_degradation(self):
        raw,cfg=self.make('collection_failure')
        p=raw/'traffic_capture.csv.capture.json';r=d3.read(p)
        r['capture_counters']['packets_dropped_by_kernel']=1;put(p,r)
        r=d3.build_review(raw,cfg,control=self.control)
        self.assertFalse(r['classification']['technical_integrity'])
        self.assertTrue(r['classification']['service_degradation_observed'])
        self.assertEqual(r['recovery']['status'],'unassessable_collection')
        self.assertFalse(r['progression']['eligible_for_manual_gate'])

    def test_persisted_open_request_is_not_record_loss(self):
        raw,cfg=self.make('opened',opened=True)
        r=d3.build_review(raw,cfg,control=self.control)
        self.assertTrue(r['classification']['technical_integrity'],r['technical_checks'])
        self.assertEqual(r['lifecycle']['open_without_end'],1)
        self.assertEqual(r['lifecycle']['records_lost'],0)
        self.assertFalse(r['classification']['controlled_closure'])
        self.assertFalse(r['progression']['eligible_for_manual_gate'])

    def test_missing_aggregate_record_is_collection_failure(self):
        raw,cfg=self.make('missing_record')
        rows=d3.csv_rows(raw/'request_log.csv');rows.pop()
        csvwrite(raw/'request_log.csv',REQUEST_FIELDS,rows)
        r=d3.build_review(raw,cfg,control=self.control)
        self.assertFalse(r['classification']['technical_integrity'])
        self.assertIn('Missing/extra',r['technical_checks'][0]['evidence'])

    def test_tampered_ground_truth_and_truncated_journal(self):
        raw,cfg=self.make('bad_gt')
        rows=d3.csv_rows(raw/'attack_events.csv');rows[0]['actual_end_seconds']='269'
        csvwrite(raw/'attack_events.csv',EVENT_FIELDS,rows)
        r=d3.build_review(raw,cfg,control=self.control)
        self.assertFalse(r['classification']['technical_integrity'])
        raw,cfg=self.make('truncated')
        p=raw/'source_artifacts/attack_1/output/journal.jsonl';p.write_text(p.read_text().rstrip())
        r=d3.build_review(raw,cfg,control=self.control)
        self.assertFalse(r['classification']['technical_integrity'])

    def test_continuous_queued_start_after_nominal_end_is_not_corruption(self):
        raw,cfg=self.make('queued_start')
        sid='attack_1'; output=raw/'source_artifacts'/sid/'output'
        local=d3.csv_rows(output/'local_requests.csv');last=local[-1]
        rid=last['request_id'];start,end=270.05,270.15
        updates=dict(elapsed_seconds=start,timestamp=1000+start,end_elapsed_seconds=end,
                     end_timestamp=1000+end,duration_ms=(end-start)*1000)
        for file in (raw/'request_log.csv',output/'local_requests.csv'):
            rows=d3.csv_rows(file)
            for r in rows:
                if r['request_id']==rid:r.update(updates)
            csvwrite(file,REQUEST_FIELDS,rows)
        events=d3.csv_rows(raw/'attack_events.csv')
        events[0].update(last_request_start_seconds=start,actual_end_seconds=270.06,drained_end_seconds=end)
        for file in (raw/'attack_events.csv',output/'local_events.csv'):
            csvwrite(file,EVENT_FIELDS,events)
        records=[json.loads(x) for x in (output/'journal.jsonl').read_text().splitlines()]
        for record in records:
            if record['kind'] in ('event_snapshot','emission_closed'):
                record['payload']=events[0]
            elif record['kind']=='source_closed':
                record['payload']['elapsed_seconds']=270.2
            elif record['kind'] in ('request_begin','request_finish') and record['payload']['request_id']==rid:
                keys=updates if record['kind']=='request_finish' else {k:v for k,v in updates.items() if k in ('elapsed_seconds','timestamp')}
                record['payload'].update(keys)
        (output/'journal.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
        r=d3.build_review(raw,cfg,control=self.control)
        self.assertTrue(r['classification']['technical_integrity'],r['technical_checks'])
        self.assertEqual(r['ground_truth']['starts_after_nominal_attack_end'],1)
        self.assertEqual(r['lifecycle']['records_lost'],0)

    def test_low_support_cannot_establish_recovery(self):
        raw,cfg=self.make('low_support')
        r=d3.build_review(raw,cfg,control=self.control)
        bins=deepcopy(r['bins'])
        for row in bins['rows']:
            if row['phase'].startswith('POST'):
                row['duration_success_2xx_ms']['n']=10
        recovery=d3.recovery(r['service'],bins,self.control,r['ground_truth'])
        self.assertEqual(recovery['status'],'not_observed')
        self.assertTrue(recovery['right_censored'])

    def test_control_rejects_service_failure(self):
        raw=self.root/'control_bad_service'
        cfg=fixture(raw,'C',control_bad=True)
        report=d3.build_review(raw,cfg)
        self.assertTrue(report['classification']['technical_integrity'])
        self.assertTrue(report['classification']['generator_adherence'])
        self.assertFalse(report['classification']['control_accepted'])
        self.assertFalse(report['progression']['eligible_for_manual_gate'])
        self.assertEqual(report['classification']['service_criteria_role'],'control_acceptance_gate')

    def test_recovery_needs_both_control_and_pre_reference(self):
        raw,cfg=self.make('dual_reference')
        r=d3.build_review(raw,cfg,control=self.control)
        # Healthy against PRE alone but too slow against the control.
        c=deepcopy(self.control)
        for row in c['bins']['rows']:
            if row['phase'].startswith('POST'):
                row['duration_success_2xx_ms']['p95']=d3.number(10)
        outcome=d3.recovery(r['service'],r['bins'],c,r['ground_truth'])
        self.assertEqual(outcome['status'],'not_observed')
        self.assertTrue(outcome['right_censored'])

    def test_end_to_end_export_processing_review_and_no_overwrite(self):
        root=self.root/'pipeline'
        root.mkdir()
        original=d3.read(d3.DEFAULT_MANIFEST)
        plan=deepcopy(original)
        # This synthetic authority tests IO/binding and raw/export correspondence;
        # the real authority/seed/hash validator is checked separately offline.
        plan['runtime_source_hashes']={}
        manifest=root/'manifest.json'
        put(manifest,plan)
        reports=[]
        for e in plan['entries']:
            target=root/e['config']
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((d3.ROOT/e['config']).read_bytes())
            raw=root/e['outputs']['raw']
            raw.parent.mkdir(parents=True,exist_ok=True)
            fixture(raw,e['condition'],recover=e['condition']!='E8')
            export_run(raw,root/e['outputs']['dataset'])
            base=root/plan['results_root']/'operations'/e['id']
            pf=base/'pf-0001/report.json'
            put(pf,dict(ready=True,preflight_id='pf-0001',manifest_sha256=d3.digest(manifest),approved_entry=e['id'],
                checks=dict(operational_code_sha256={},containers_before=[])))
            put(base/'attempt.json',dict(authorization_scope=e['id'],manifest_sha256=d3.digest(manifest),
                preflight_path=str(pf.relative_to(root)),preflight_sha256=d3.digest(pf),preflight_id='pf-0001',approved_source_hashes={}))
            put(base/'execution_result.json',dict(returncode=0))
            put(base/'cleanup_observation.json',dict(containers=[],no_active_containers=True,no_scientific_processes=True,
                port_check_returncode=0,port_8080='State Recv-Q Send-Q Local Address:Port Peer Address:Port\n',observed_epoch=1))
            with patch.object(d3,'ROOT',root),patch.object(d3,'validate_plan',return_value={'synthetic_authority':True}):
                reports.append(d3.process_entry(manifest,e['id']))
                prior=d3.digest(root/e['outputs']['review'])
                with self.assertRaises(FileExistsError):
                    d3.process_entry(manifest,e['id'])
                self.assertEqual(prior,d3.digest(root/e['outputs']['review']))
        self.assertTrue(reports[0]['classification']['control_accepted'])
        self.assertTrue(reports[1]['classification']['technical_integrity'])
        self.assertTrue(reports[1]['classification']['service_degradation_observed'])
        self.assertEqual(reports[1]['recovery']['status'],'observed')
        self.assertTrue(reports[2]['classification']['technical_integrity'])
        self.assertTrue(reports[2]['recovery']['right_censored'])
        self.assertFalse(reports[2]['progression']['eligible_for_manual_gate'])

    def test_operations_binding_and_e8_gate(self):
        from experiments import development_d3_ops as ops
        root=self.root/'binding';entry=dict(id='d3_pilot_E4',outputs=dict(review='review.json'))
        base=root/'results/operations/d3_pilot_E4';base.mkdir(parents=True)
        manifest=root/'manifest.json';put(manifest,{'synthetic':True})
        path=base/'pf-0001/report.json'
        plan=dict(results_root='results',runtime_source_hashes={})
        pf=dict(ready=True,preflight_id='pf-0001',manifest_sha256=d3.digest(manifest),approved_entry=entry['id'],
                checks=dict(operational_code_sha256={},containers_before=[]))
        put(path,pf)
        attempt=dict(authorization_scope=entry['id'],manifest_sha256=d3.digest(manifest),
            preflight_path=str(path.relative_to(root)),preflight_sha256=d3.digest(path),preflight_id='pf-0001',approved_source_hashes={})
        put(base/'attempt.json',attempt)
        put(base/'execution_result.json',dict(returncode=0))
        put(base/'cleanup_observation.json',dict(containers=[],no_active_containers=True,no_scientific_processes=True,
            port_check_returncode=0,port_8080='State Recv-Q Send-Q Local Address:Port Peer Address:Port\n',observed_epoch=1))
        with patch.object(d3,'ROOT',root):
            self.assertTrue(d3.operation_checks(plan,entry,manifest)['cleanup_verified'])
            attempt['preflight_sha256']='0'*64;put(base/'attempt.json',attempt)
            with self.assertRaisesRegex(ValueError,'authority'):
                d3.operation_checks(plan,entry,manifest)
        review=deepcopy(self.control)
        review.update(entry_id='d3_pilot_E4',authority=dict(manifest_sha256=d3.digest(manifest)))
        review['progression']['eligible_for_manual_gate']=False
        put(root/'review.json',review)
        with patch.object(ops,'ROOT',root),patch.object(ops,'ACTIVE_MANIFEST',manifest),patch.object(ops,'REVIEWED_PREDECESSOR',d3.digest(root/'review.json')):
            with self.assertRaisesRegex(ValueError,'blocks progression'):
                ops.check_predecessors(dict(entries=[entry,dict(id='d3_pilot_E8')]),1)

    def test_no_docker_or_experiment_during_offline_processing(self):
        with patch('subprocess.Popen',side_effect=AssertionError('external process forbidden')):
            report=d3.build_review(self.control_raw,self.control_config)
        self.assertTrue(report['classification']['control_accepted'])


if __name__=='__main__':
    unittest.main()
