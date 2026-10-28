"""Four paired synthetic runs through frozen E8 pipeline; no Docker/load execution."""
from copy import deepcopy
from decimal import Decimal as D
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from experiments import development_d3_cost as c
from experiments import development_d3_cost_ops as ops
from experiments.export_dataset import export_run
from tests.test_development_d3 import fixture,put,csvwrite
from simulator.ground_truth import EVENT_FIELDS


def cost_fixture(raw,entry,*,remove_attack=0):
    fixture(raw,'E8')
    cfg=c.base.ExperimentConfig.from_dict(entry['effective_configuration'])
    run='synthetic_'+entry['id'];endpoint=cfg.attack.endpoint
    rows=c.base.old.csv_rows(raw/'request_log.csv')
    attack=[r for r in rows if r['traffic_class']=='attack']
    removed={r['request_id'] for r in attack[-remove_attack:]} if remove_attack else set()
    removed_admissions={float(r['elapsed_seconds'])-.001 for r in attack if r['request_id'] in removed}
    def mutate(row,finish=True):
        if 'run_id' in row:row['run_id']=run
        if 'experiment_id' in row:row['experiment_id']=cfg.id
        if row.get('traffic_class')=='attack' and 'target_url' in row:
            row['target_url']='http://edos_service:80'+endpoint
        if finish and 'outcome' in row and endpoint=='/medium' and row.get('traffic_class')=='benign' and 'elapsed_seconds' in row and 150<=float(row['elapsed_seconds'])<270:
            start=float(row['elapsed_seconds']);end=start+.05
            row.update(end_elapsed_seconds=end,end_timestamp=1000+end,duration_ms=(end-start)*1000,outcome='response',http_status=200,error_type=None)
    for path in raw.rglob('*.csv'):
        with path.open(newline='') as stream:
            import csv
            reader=csv.DictReader(stream);fields=reader.fieldnames;items=list(reader)
        if fields is None:continue
        items=[r for r in items if r.get('request_id') not in removed]
        for r in items:
            mutate(r)
            if path.name=='simulation_metrics.csv' and 150<=float(r['elapsed_seconds'])<270:
                r['average_cpu_percent']=30 if endpoint=='/medium' else 90
        csvwrite(path,fields,items)
    put(raw/'effective_config.json',json.loads(cfg.to_json()))
    status=c.read(raw/'run_status.json');status.update(run_id=run,experiment_id=cfg.id);put(raw/'run_status.json',status)
    inventory=c.read(raw/'source_inventory.json')
    for source in inventory:
        source['run_id']=run;source['status_final']['run_id']=run
        path=raw/'source_artifacts'/source['source_id']/'output/final_status.json'
        final=c.read(path);final['run_id']=run;put(path,final)
    put(raw/'source_inventory.json',inventory)
    rows=c.base.old.csv_rows(raw/'request_log.csv');attack=[r for r in rows if r['traffic_class']=='attack']
    event=c.base.old.csv_rows(raw/'attack_events.csv')[0]
    event.update(last_request_start_seconds=max(float(r['elapsed_seconds']) for r in attack),drained_end_seconds=max(float(r['end_elapsed_seconds']) for r in attack))
    for path in (raw/'attack_events.csv',raw/'source_artifacts/attack_1/output/local_events.csv'):csvwrite(path,EVENT_FIELDS,[event])
    for path in (raw/'source_artifacts').glob('*/output/journal.jsonl'):
        records=[]
        for line in path.read_text().splitlines():
            item=json.loads(line);kind=item['kind'];p=item['payload']
            if p.get('request_id') in removed or (kind=='admission' and p['elapsed_seconds'] in removed_admissions):continue
            item['run_id']=run;mutate(p,finish=kind=='request_finish')
            if kind in ('event_snapshot','emission_closed'):item['payload']=event
            item['sequence']=len(records)+1;records.append(item)
        path.write_text(''.join(json.dumps(x)+'\n' for x in records))
    # RTT is an exact subset of successful response rows; rebuild after healing.
    from simulator.request_logger import RTT_FIELDS
    csvwrite(raw/'rtt_log.csv',RTT_FIELDS,[dict(timestamp=r['end_timestamp'],rtt=r['duration_ms'],run_id=run,request_id=r['request_id'],
        traffic_class=r['traffic_class'],elapsed_seconds=r['end_elapsed_seconds']) for r in rows if r['outcome']=='response'])
    path=raw/'proxy_artifacts/monitor_samples.jsonl';samples=[json.loads(x) for x in path.read_text().splitlines()]
    for sample in samples:
        sample['run_id']=run
        sample['docker']['data']=dict(cpu_percent=2 if endpoint=='/medium' else 3,memory_usage_bytes=8000000)
        sample['status']['data']=dict(active_connections=12,reading_connections=0,writing_connections=1,waiting_connections=11)
    path.write_text(''.join(json.dumps(x)+'\n' for x in samples))
    for name in ('monitor_summary.json','capture_metadata.json'):
        path=raw/'proxy_artifacts'/name;value=c.read(path);value['run_id']=run;put(path,value)
    return cfg


class CostTests(unittest.TestCase):
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
            self.assertEqual({k:v for k,v in a['attack'].items() if k!='endpoint'},{k:v for k,v in b['attack'].items() if k!='endpoint'})
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
            campaign_identity=dict(block=entry['block'],offensive_endpoint=entry['endpoint'],seed=entry['effective_configuration']['seed']),preserved_raw_hashes={})
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
            cfg=cost_fixture(raw,entry,remove_attack=8 if index==1 else 16 if index==2 else 0)
            baseline=c.e8.assess_raw(raw,cfg,self.control_raw,self.control)
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
                self.assertTrue(c.gate_passes(r));self.assertEqual(r['timing']['cleanup_observation']['epoch'],1)
                self.assertEqual(r['campaign_identity']['seed'],entry['effective_configuration']['seed'])
                with self.assertRaises(FileExistsError):c.review_entry(entry['id'],manifest)
        with patch.object(c,'ROOT',root),patch.object(c,'validate_plan',return_value={'fixture_authority':True}):
            result=c.compare(manifest)
            self.assertEqual(len(result['runs']),4);self.assertEqual(result['pilot_runs_in_comparison'],0)
            self.assertIn('ΔRPS',(root/p['comparison_outputs']['markdown']).read_text())
            for block in ('A','B'):
                pair=result['within_block_expensive_minus_medium'][block]['contrast']
                self.assertTrue(pair['same_seed']);self.assertTrue(pair['realized_offensive_starts_differ'])
                self.assertLess(pair['observed_offensive_rps']['left_minus_right'],0)
                self.assertGreater(pair['left_minus_right']['ACTIVE']['p95_ms'],0)
            self.assertTrue(all(not x['same_seed'] for x in result['between_block_B_minus_A_by_endpoint'].values()))
            with self.assertRaises(FileExistsError):c.compare(manifest)
        # Concise actual CLI path, with full review already tested above.
        with patch.object(sys,'argv',['cost','review','--entry',p['entries'][-1]['id']]),patch.object(c,'review_entry',return_value=r),patch('sys.stdout',new_callable=io.StringIO) as out:
            c.main();self.assertLess(len(out.getvalue()),450);self.assertNotIn('post_windows',out.getvalue())


if __name__=='__main__':unittest.main()
