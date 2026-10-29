"""Offline two-origin fixtures; no containers or load are started."""
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from experiments import development_d3 as d3
from simulator.experiment_config import ExperimentConfig
from simulator.request_logger import REQUEST_FIELDS
from simulator.ground_truth import EVENT_FIELDS
from experiments.dataset_schema import schema
from tests.test_development_d3 import fixture,put,csvwrite

import io
import sys
import tempfile
import unittest
from experiments import development_d3_origins as c
from experiments import development_d3_origins_ops as ops
from experiments.export_dataset import export_run

def origins_fixture(raw, entry):
    condition='E8';recover=True;opened=False;control_bad=False
    cfg = ExperimentConfig.from_dict(entry['effective_configuration'])
    raw.mkdir()
    run = 'synthetic_' + cfg.id
    put(raw / 'effective_config.json', json.loads(cfg.to_json()))
    allrows, inventory = [], []
    groups = [(f'normal_{i+1}','normal','benign',i,4) for i in range(4)]
    if condition != 'C':
        groups.extend((f'attack_{i+1}','attack','attack',i,cfg.attack.rate) for i in range(cfg.attack.attackers))
    event = None;events=[]
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
                actual_start_seconds=rows[0]['elapsed_seconds'],stop_requested_seconds=270,actual_end_seconds=270.01+.02*worker,
                last_request_start_seconds=rows[-1]['elapsed_seconds'],drained_end_seconds=max(r['end_elapsed_seconds'] for r in rows),
                status='completed',end_reason='scheduled_end')
            events.append(event)
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
            send_workers=64//cfg.attack.attackers if cls=='attack' else 16,status_final=dict(state='exited',exit_code=2 if not closed['drained'] else 0,forced=False,**final)))
        allrows.extend(rows)
    event=dict(events[0])
    for key in ('actual_start_seconds','activation_requested_seconds','stop_requested_seconds'):event[key]=min(e[key] for e in events)
    for key in ('actual_end_seconds','last_request_start_seconds','drained_end_seconds'):event[key]=max(e[key] for e in events)
    for row in allrows:
        active=event['actual_start_seconds']<=row['elapsed_seconds']<event['actual_end_seconds']
        row.update(attack_active=int(active),active_event_ids='["event_001"]' if active else '[]')
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


class OriginsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.control_raw=cls.root/'synthetic_control';cfg=fixture(cls.control_raw,'C')
        cls.control=c.base.old.build_review(cls.control_raw,cfg)
        cls.control['preserved_raw_hashes']={str(p):c.base.sha(p) for p in cls.control_raw.rglob('*') if p.is_file()}
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_real_authority_pairing_order_rates_budget_and_tamper(self):
        v=c.validate_plan();self.assertEqual(v['entry_count'],4);self.assertEqual(v['blocks'],2)
        p=c.read(c.DEFAULT_MANIFEST);self.assertNotEqual(p['block_seeds']['A'],p['block_seeds']['B'])
        self.assertEqual(p['budget']['envelope_seconds'],4320)
        for block in ('A','B'):
            pair=[e for e in p['entries'] if e['block']==block]
            self.assertEqual({e['effective_configuration']['seed'] for e in pair},{p['block_seeds'][block]})
            a,b=[e['effective_configuration'] for e in pair]
            self.assertEqual({k:v for k,v in a.items() if k not in ('id','attack')},{k:v for k,v in b.items() if k not in ('id','attack')})
            self.assertEqual({k:v for k,v in a['attack'].items() if k not in ('rate','attackers')},{k:v for k,v in b['attack'].items() if k not in ('rate','attackers')})
        bad=deepcopy(p);bad['entries'][0],bad['entries'][1]=bad['entries'][1],bad['entries'][0]
        path=self.root/'bad-order.json';put(path,bad)
        with self.assertRaises(ValueError):c.validate_plan(path)
        bad=deepcopy(p);bad['rule']['success_fraction_min']='0.98';put(path,bad)
        with self.assertRaises(ValueError):c.validate_plan(path)

    def test_contexts_restore_and_old_authorities_are_not_overridden(self):
        before=(c.base.read,c.base.put,c.base.validate_plan,ops.operations.BASE,ops.operations.get_plan)
        with self.assertRaisesRegex(RuntimeError,'sentinel'):
            with c.review_context(c.ENTRY_IDS[2],c.DEFAULT_MANIFEST),ops.operations_context():
                view=c.base.read(c.DEFAULT_MANIFEST)
                self.assertEqual(len(view['entries']),1);self.assertEqual(view['entries'][0]['id'],c.ENTRY_IDS[2])
                raise RuntimeError('sentinel')
        self.assertEqual(before,(c.base.read,c.base.put,c.base.validate_plan,ops.operations.BASE,ops.operations.get_plan))

    def test_review_hash_terminal_gate_and_idle_required_active_failure_allowed(self):
        p=c.read(c.DEFAULT_MANIFEST);entry=p['entries'][0]
        r=dict(classification=dict(technical_integrity=True,service_observation_valid=True),lifecycle=dict(controlled_closure=True),
            dataset_validation=dict(dataset_valid=True,analysis_eligible=True),operations=dict(cleanup_verified=True,execution=dict(returncode=0),cleanup=dict(observed_epoch=0)),
            service=dict(reference_compatibility=dict(compatible=True),last_two_post_windows_qualified=True,active_degradation_observed=True),technical_checks=[dict(passed=True)])
        self.assertTrue(c.gate_passes(r))
        self.assertEqual(ops.check_predecessors(p,0)[0]['entry'],'d3_cost_B_medium')
        with patch.object(c,'reviewed_entry',return_value=r),patch.object(c.base,'sha',return_value='approved'),patch.object(ops,'REVIEWED_SHA256','wrong'):
            with self.assertRaisesRegex(ValueError,'reviewed-sha256'):ops.check_predecessors(p,1)
        with patch.object(c,'reviewed_entry',return_value=r),patch.object(c.base,'sha',return_value='approved'),patch.object(ops,'REVIEWED_SHA256','approved'):
            self.assertEqual(len(ops.check_predecessors(p,1)),1)
            bad=deepcopy(r);bad['service']['last_two_post_windows_qualified']=False
            with patch.object(c,'reviewed_entry',return_value=bad):
                with self.assertRaisesRegex(ValueError,'blocks progression'):ops.check_predecessors(p,1)
            recent=deepcopy(r);recent['operations']['cleanup']['observed_epoch']=10**12
            with patch.object(c,'reviewed_entry',return_value=recent):
                with self.assertRaisesRegex(ValueError,'idle'):ops.check_predecessors(p,1)

    def test_historical_pilot_review_cannot_replace_planned_entry(self):
        plan=deepcopy(c.read(c.DEFAULT_MANIFEST));entry=plan['entries'][0]
        entry['outputs']['review']='review.json'
        root=self.root/'wrong-pilot';root.mkdir();manifest=root/'manifest.json';put(manifest,plan)
        review=dict(entry_id='d3_pilot_E8_R2',authority=dict(manifest_sha256=c.base.sha(manifest),config_sha256=entry['config_sha256']),
            campaign_identity=dict(block=entry['block'],offensive_endpoint=entry['endpoint'],condition=entry['condition'],attackers=entry['effective_configuration']['attack']['attackers'],seed=entry['effective_configuration']['seed']),preserved_raw_hashes={})
        put(root/'review.json',review)
        with patch.object(c,'ROOT',root):
            with self.assertRaisesRegex(ValueError,'binding mismatch'):c.reviewed_entry(plan,entry,manifest)

    def test_four_run_fixture_pipeline_and_seed_paired_comparison(self):
        root=self.root/'pipeline';root.mkdir();p=deepcopy(c.read(c.DEFAULT_MANIFEST))
        cref=root/'C-review.json';put(cref,self.control)
        p['secondary_reference'].update(review_path='C-review.json',review_sha256=c.base.sha(cref),raw=str(self.control_raw),
            files=[dict(path='C-review.json',sha256=c.base.sha(cref))]);p['runtime_source_hashes']={}
        manifest=root/'manifest.json';put(manifest,p)
        for index,entry in enumerate(p['entries']):
            cfgpath=root/entry['config'];cfgpath.parent.mkdir(parents=True,exist_ok=True);cfgpath.write_bytes((c.ROOT/entry['config']).read_bytes())
            raw=root/entry['outputs']['raw'];raw.parent.mkdir(parents=True,exist_ok=True)
            cfg=origins_fixture(raw,entry)
            baseline=c.assess_raw(raw,cfg,self.control_raw,self.control)
            if cfg.attack.attackers==1:
                self.assertEqual(baseline['service'],c.e8.assess_raw(raw,cfg,self.control_raw,self.control)['service'])
            export_run(raw,root/entry['outputs']['dataset'])
            op=root/p['results_root']/'operations'/entry['id'];pf=op/'pf-0001/report.json'
            put(pf,dict(ready=True,preflight_id='pf-0001',manifest_sha256=c.base.sha(manifest),approved_entry=entry['id'],checks=dict(operational_code_sha256={},containers_before=[])))
            put(op/'attempt.json',dict(authorization_scope=entry['id'],manifest_sha256=c.base.sha(manifest),preflight_path=str(pf.relative_to(root)),preflight_sha256=c.base.sha(pf),preflight_id='pf-0001',approved_source_hashes={}))
            put(op/'execution_result.json',dict(returncode=0))
            put(op/'cleanup_observation.json',dict(containers=[],no_active_containers=True,no_scientific_processes=True,
                port_check_returncode=0,port_8080='State Recv-Q Send-Q Local Address:Port Peer Address:Port\n',observed_epoch=1))
            with patch.object(c,'ROOT',root),patch.object(c,'validate_plan',return_value={'fixture_authority':True}),patch.object(c.base.old,'ROOT',root):
                r=c.review_entry(entry['id'],manifest)
                self.assertTrue(r['classification']['technical_integrity'],r['technical_checks'])
                self.assertEqual(r['service'],baseline['service'])
                offense=next(x for x in r['generator']['nominal_start_adherence'] if x['traffic_class']=='attack')
                self.assertEqual(offense['nominal_expected'],960)
                self.assertEqual(offense['starts'],960)
                count=cfg.attack.attackers
                self.assertEqual(len(offense['per_origin']),count)
                self.assertEqual([x['nominal_expected'] for x in offense['per_origin']],[960//count]*count)
                self.assertEqual([x['observed_start_rps'] for x in offense['per_origin']],[8//count]*count)
                self.assertEqual([x['send_workers'] for x in r['generator']['attack_admission']['per_origin']],[64//count]*count)
                self.assertAlmostEqual(float(r['ground_truth']['actual_emission_intervals'][0][1]),270.01+.02*(count-1))
                self.assertTrue(c.gate_passes(r))
                self.assertEqual(r['timing']['cleanup_observation']['epoch'],1)
                self.assertEqual(r['campaign_identity']['seed'],entry['effective_configuration']['seed'])
                with self.assertRaises(FileExistsError):c.review_entry(entry['id'],manifest)
                with patch.object(c,'ROOT',root):
                    self.assertEqual(c.reviewed_entry(p,entry,manifest)['entry_id'],entry['id'])
                    altered=deepcopy(r);altered['campaign_identity']['attackers']=99
                    reviewpath=root/entry['outputs']['review'];put(reviewpath,altered)
                    with self.assertRaisesRegex(ValueError,'binding mismatch'):c.reviewed_entry(p,entry,manifest)
                    put(reviewpath,r)
                if count==2:
                    inventorypath=raw/'source_inventory.json';inventory=c.read(inventorypath)
                    put(inventorypath,inventory[:-1])
                    self.assertFalse(c.assess_raw(raw,cfg,self.control_raw,self.control)['classification']['technical_integrity'])
                    put(inventorypath,inventory)
                    eventpath=raw/'attack_events.csv';events=c.base.old.csv_rows(eventpath)
                    altered=deepcopy(events);altered[0]['actual_end_seconds']='270.01';csvwrite(eventpath,EVENT_FIELDS,altered)
                    self.assertFalse(c.assess_raw(raw,cfg,self.control_raw,self.control)['classification']['technical_integrity'])
                    csvwrite(eventpath,EVENT_FIELDS,events)
                    journal=raw/'source_artifacts/attack_2/output/journal.jsonl';saved=journal.read_bytes()
                    journal.write_bytes(b'\n'.join(saved.splitlines()[:-1])+b'\n')
                    self.assertFalse(c.assess_raw(raw,cfg,self.control_raw,self.control)['classification']['technical_integrity'])
                    journal.write_bytes(saved)
                    local=raw/'source_artifacts/attack_2/output/local_requests.csv';saved_csv=local.read_bytes()
                    local.write_bytes(b'\n'.join(saved_csv.splitlines()[:-1])+b'\n')
                    self.assertFalse(c.assess_raw(raw,cfg,self.control_raw,self.control)['classification']['technical_integrity'])
                    local.write_bytes(saved_csv)
                    # The production aggregator must wait for every emission certificate.
                    from types import SimpleNamespace
                    from simulator.source_aggregate import reconcile,records
                    allrecords=records(raw/'source_artifacts',inventory)
                    aggregate=c.base.old.csv_rows(eventpath)[0]
                    obj=SimpleNamespace(row=dict(aggregate),accepting=True)
                    truth=SimpleNamespace(_events={'event_001':obj},persist=lambda:None)
                    reconcile(truth,inventory,[x for x in allrecords if x['source_id']!='attack_2'])
                    self.assertIsNone(obj.row['actual_end_seconds'])
                    self.assertTrue(obj.accepting)
                    reconcile(truth,inventory,allrecords,final=True)
                    self.assertAlmostEqual(float(obj.row['actual_end_seconds']),270.03)
                    self.assertFalse(obj.accepting)
                    self.assertEqual(obj.row['status'],'completed')
                    wrong=deepcopy(inventory);wrong[-1]['send_workers']=64;put(inventorypath,wrong)
                    self.assertFalse(c.assess_raw(raw,cfg,self.control_raw,self.control)['classification']['technical_integrity'])
                    put(inventorypath,inventory)
        with patch.object(c,'ROOT',root),patch.object(c,'validate_plan',return_value={'fixture_authority':True}):
            result=c.compare(manifest)
            self.assertEqual(len(result['runs']),4);self.assertEqual(result['pilot_runs_in_comparison'],0)
            self.assertIn('attack_2',(root/p['comparison_outputs']['markdown']).read_text())
            self.assertIn('ΔRPS',(root/p['comparison_outputs']['markdown']).read_text())
            for block in ('A','B'):
                pair=result['within_block_N2_minus_N1'][block]['contrast']
                self.assertTrue(pair['same_seed']);self.assertFalse(pair['realized_offensive_starts_differ'])
                self.assertEqual(pair['observed_offensive_rps']['left_minus_right'],0)
                self.assertEqual(pair['left_minus_right']['ACTIVE']['p95_ms'],0)
            left=deepcopy(result['runs']['d3_origins_A_N2']);right=result['runs']['d3_origins_A_N1']
            left['offense']['observed_start_rps']=c.base.number('7.5')
            unequal=c.contrast(left,right,same_seed=True)
            self.assertTrue(unequal['realized_offensive_starts_differ'])
            self.assertEqual(unequal['observed_offensive_rps']['left_minus_right'],c.base.number('-.5'))
            self.assertTrue(all(not x['same_seed'] for x in result['between_block_B_minus_A_by_condition'].values()))
            with self.assertRaises(FileExistsError):c.compare(manifest)
        # Concise actual CLI path, with full review already tested above.
        with patch.object(sys,'argv',['origins','review','--entry',p['entries'][-1]['id']]),patch.object(c,'review_entry',return_value=r),patch('sys.stdout',new_callable=io.StringIO) as out:
            c.main();self.assertLess(len(out.getvalue()),450);self.assertNotIn('post_windows',out.getvalue())


if __name__=='__main__':unittest.main()
