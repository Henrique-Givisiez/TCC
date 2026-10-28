"""Synthetic full IO and causal-horizon tests; no Docker or traffic execution."""
from copy import deepcopy
from decimal import Decimal as D
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from experiments import development_d3_minimal as m
from experiments.export_dataset import export_run
from tests.test_development_d3 import fixture, put, csvwrite
from simulator.ground_truth import EVENT_FIELDS
from simulator.request_logger import REQUEST_FIELDS


def records(a,b,n,duration='.05',failure=False):
    rows=[]
    for i in range(n):
        start=D(a)+D('.1')+(D(b)-D(a)-D('.2'))*(D(i)+D('.5'))/n
        end=start+D(duration)
        rows.append(dict(start=start,end=end,duration=(end-start)*1000,
            category='transport_error' if failure else 'success_2xx',traffic_class='benign',request_id=str(i)))
    return rows


def fresh_fixture(raw,*,healthy_active=False,recover=True,opened=False):
    fixture(raw,'E4',recover=recover,opened=opened)
    cfg=m.ExperimentConfig.load(m.ROOT/'experiments/configs/development_d3_minimal_20261028/d3_minimal_E4_R2.json')
    put(raw/'effective_config.json',json.loads(cfg.to_json()))
    status=m.read(raw/'run_status.json');status['experiment_id']=cfg.id;put(raw/'run_status.json',status)
    for path in [raw/'attack_events.csv',raw/'source_artifacts/attack_1/output/local_events.csv']:
        rows=m.old.csv_rows(path)
        for r in rows:r['experiment_id']=cfg.id
        csvwrite(path,EVENT_FIELDS,rows)
    for journal in (raw/'source_artifacts').glob('*/output/journal.jsonl'):
        items=[json.loads(x) for x in journal.read_text().splitlines()]
        for item in items:
            if item['kind'] in ('event_snapshot','emission_closed'):item['payload']['experiment_id']=cfg.id
        journal.write_text(''.join(json.dumps(x)+'\n' for x in items))
    if healthy_active:
        def heal(row):
            if row['traffic_class']=='benign' and 150<=float(row['elapsed_seconds'])<270:
                start=float(row['elapsed_seconds']);end=start+.05
                row.update(end_elapsed_seconds=end,end_timestamp=1000+end,duration_ms=(end-start)*1000,
                           outcome='response',http_status=200,error_type=None)
        for path in [raw/'request_log.csv',*(raw/'source_artifacts').glob('*/output/local_requests.csv')]:
            rows=m.old.csv_rows(path)
            for row in rows:heal(row)
            csvwrite(path,REQUEST_FIELDS,rows)
        for journal in (raw/'source_artifacts').glob('*/output/journal.jsonl'):
            items=[json.loads(x) for x in journal.read_text().splitlines()]
            for item in items:
                if item['kind']=='request_finish':heal(item['payload'])
            journal.write_text(''.join(json.dumps(x)+'\n' for x in items))
        rows=m.old.csv_rows(raw/'request_log.csv')
        from simulator.request_logger import RTT_FIELDS
        csvwrite(raw/'rtt_log.csv',RTT_FIELDS,[dict(timestamp=r['end_timestamp'],rtt=r['duration_ms'],run_id=r['run_id'],
            request_id=r['request_id'],traffic_class=r['traffic_class'],elapsed_seconds=r['end_elapsed_seconds']) for r in rows if r['outcome']=='response'])
    return cfg


class MinimalD3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.control_raw=cls.root/'historical_C';ccfg=fixture(cls.control_raw,'C')
        cls.control=m.old.build_review(cls.control_raw,ccfg)
        cls.control['preserved_raw_hashes']={str(p):m.sha(p) for p in cls.control_raw.rglob('*') if p.is_file()}
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_deadline_does_not_borrow_future_success(self):
        r=records(270,300,480);r[-1].update(end=D(305),duration=(D(305)-r[-1]['start'])*1000)
        a=m.measure(r,270,300,D('300.1'))
        self.assertFalse(a['cohort_mature']);self.assertIsNone(a['success_fraction'])
        self.assertEqual(a['snapshot_at_bin_end']['pending_from_cohort'],1)
        a=m.measure(r,270,300,303)
        self.assertTrue(a['cohort_mature']);self.assertEqual(a['timely_2xx'],479)
        later=m.measure(r,270,300,420)
        self.assertEqual(a['success_fraction'],later['success_fraction'])
        self.assertEqual(later['evidence_horizon_seconds'],303)

    def test_early_complete_cohort_is_explicit_not_invented_horizon(self):
        a=m.measure(records(360,390,480),360,390,D('390.1'))
        self.assertTrue(a['cohort_mature']);self.assertTrue(a['cohort_finalized_early'])
        self.assertFalse(a['horizon_observed']);self.assertLess(a['decision_not_before_seconds'],393)

    def test_missing_window_observation_cannot_qualify(self):
        a=m.measure(records(360,390,480),360,390,389)
        self.assertFalse(a['window_fully_observed']);self.assertFalse(a['cohort_mature'])
        self.assertIsNone(a['success_fraction']);self.assertIsNone(a['pending_at_end'])

    def test_exposure_arrival_variation_and_no_false_recovery(self):
        pre=records(30,150,1920);control=records(30,390,6000)
        rows=pre+records(150,270,1920)
        for i,n in enumerate((440,520,450,510)):rows+=records(max(D(270+30*i),D('270.0015')),300+30*i,n)
        result=m.service_assessment(rows,[],cutoff=420,emission_end=D('270.0015'),secondary=m.reference(control,30,390,420))
        self.assertEqual(result['state'],'post_compatible_no_prior_impairment')
        self.assertIsNone(result['recovery_event'])
        self.assertTrue(all(w['qualified'] for w in result['post_windows']))
        self.assertEqual(result['post_windows'][0]['metrics']['exposure_seconds'],D('29.9985'))
        self.assertEqual(result['first_post_compatibility']['window_end_seconds'],330)
        self.assertEqual(result['first_post_compatibility']['required_evidence_horizon_seconds'],333)

    def test_persistent_degradation_and_pending_are_service_results(self):
        pre=records(30,150,1920);ref=m.reference(pre,30,150,420)
        rows=pre+records(150,270,1920,duration='.5')+records(270,390,1920,duration='.5')
        r=m.service_assessment(rows,[],cutoff=420,emission_end=270,secondary=ref)
        self.assertTrue(r['active_degradation_observed']);self.assertTrue(r['right_censored'])
        self.assertIsNone(r['first_post_compatibility'])
        rows=pre+records(150,390,3840)+[dict(start=D(260),end=None,duration=None,category='incomplete',traffic_class='benign',request_id='open')]
        r=m.service_assessment(rows,[],cutoff=420,emission_end=270,secondary=ref)
        self.assertTrue(all(w['service_checks']['pending_age'] is False for w in r['post_windows']))

    def test_secondary_disagreement_does_not_invent_primary_degradation(self):
        pre=records(30,150,1920,duration='.06');ref=m.reference(records(30,390,5760),30,390,420)
        rows=pre+records(150,390,3840,duration='.07')
        r=m.service_assessment(rows,[],cutoff=420,emission_end=270,secondary=ref)
        self.assertFalse(r['active_degradation_observed'])
        self.assertTrue(all(w['secondary_disagreement'] for w in r['post_windows']))
        self.assertIsNone(r['recovery_event'])
        self.assertTrue(r['right_censored'])

    def test_raw_fixture_persistent_degradation_is_valid_and_censored(self):
        raw=self.root/'persistent';cfg=fresh_fixture(raw,recover=False)
        r=m.assess_raw(raw,cfg,self.control_raw,self.control)
        self.assertTrue(r['classification']['technical_integrity'],r['technical_checks'])
        self.assertTrue(r['service']['right_censored'])
        self.assertEqual(r['service']['censor_at_seconds'],390)
        self.assertTrue(all(w['service_impairment_observed'] for w in r['service']['post_windows']))

    def test_raw_fixture_no_active_impairment_service_valid_generator_unknown(self):
        raw=self.root/'no_active';cfg=fresh_fixture(raw,healthy_active=True)
        with patch('subprocess.Popen',side_effect=AssertionError('No external process')):
            r=m.assess_raw(raw,cfg,self.control_raw,self.control)
        self.assertTrue(r['classification']['technical_integrity'],r['technical_checks'])
        self.assertEqual(r['service']['state'],'post_compatible_no_prior_impairment')
        self.assertIsNone(r['service']['recovery_event'])
        self.assertFalse(r['generator']['full_scheduled_load_verified'])
        self.assertTrue(r['classification']['service_observation_valid'])

    def test_collection_failure_invalidates_inference_not_recovery_censoring(self):
        raw=self.root/'bad_capture';cfg=fresh_fixture(raw)
        path=raw/'traffic_capture.csv.capture.json';d=m.read(path);d['capture_counters']['packets_dropped_by_kernel']=1;put(path,d)
        r=m.assess_raw(raw,cfg,self.control_raw,self.control)
        self.assertFalse(r['classification']['technical_integrity'])
        self.assertIsNone(r['service']['recovery_event']);self.assertFalse(r['service']['right_censored'])

    def test_open_persisted_attempt_is_not_lost_record(self):
        raw=self.root/'opened';cfg=fresh_fixture(raw,opened=True)
        r=m.assess_raw(raw,cfg,self.control_raw,self.control)
        self.assertTrue(r['classification']['technical_integrity'],r['technical_checks'])
        self.assertEqual(r['lifecycle']['records_lost'],0)
        self.assertEqual(r['lifecycle']['open_without_end'],1)
        self.assertFalse(r['lifecycle']['controlled_closure'])

    def test_full_pipeline_export_binding_publication_and_compact_cli(self):
        root=self.root/'pipeline';root.mkdir()
        plan=deepcopy(m.read(m.DEFAULT_MANIFEST));e=plan['entries'][0]
        cfgpath=root/e['config'];cfgpath.parent.mkdir(parents=True);cfgpath.write_bytes((m.ROOT/e['config']).read_bytes())
        raw=root/e['outputs']['raw'];raw.parent.mkdir(parents=True);fresh_fixture(raw)
        export_run(raw,root/e['outputs']['dataset'])
        cpath=root/'control-review.json';put(cpath,self.control)
        plan['secondary_reference'].update(review_path='control-review.json',review_sha256=m.sha(cpath),raw=str(self.control_raw),
            files=[dict(path='control-review.json',sha256=m.sha(cpath))])
        plan['runtime_source_hashes']={}
        manifest=root/'manifest.json';put(manifest,plan)
        ops=root/plan['results_root']/'operations'/m.ENTRY_ID
        pf=ops/'pf-0001/report.json';put(pf,dict(ready=True,preflight_id='pf-0001',manifest_sha256=m.sha(manifest),approved_entry=m.ENTRY_ID,
            checks=dict(operational_code_sha256={},containers_before=[])))
        put(ops/'attempt.json',dict(authorization_scope=m.ENTRY_ID,manifest_sha256=m.sha(manifest),preflight_path=str(pf.relative_to(root)),
            preflight_sha256=m.sha(pf),preflight_id='pf-0001',approved_source_hashes={}))
        put(ops/'execution_result.json',dict(returncode=0))
        put(ops/'cleanup_observation.json',dict(containers=[],no_active_containers=True,no_scientific_processes=True,
            port_check_returncode=0,port_8080='State Recv-Q Send-Q Local Address:Port Peer Address:Port\n',observed_epoch=1))
        with patch.object(m,'ROOT',root),patch.object(m.old,'ROOT',root),patch.object(m,'validate_plan',return_value={'fixture_authority':True}):
            r=m.review_entry(manifest)
            self.assertTrue(r['classification']['technical_integrity'],r['technical_checks'])
            self.assertEqual(r['service']['state'],'recovery_observed')
            event=r['service']['recovery_event']
            self.assertEqual(event['window_end_seconds'],330)
            self.assertEqual(event['required_evidence_horizon_seconds'],333)
            self.assertGreaterEqual(event['decision_not_before_seconds'],r['lifecycle']['cutoff'])
            self.assertTrue(r['publication']['evaluation_published_at_utc'])
            self.assertFalse(r['generator']['full_scheduled_load_verified'])
            self.assertLess(len(json.dumps(m.compact(r))),400)
            with self.assertRaises(FileExistsError):m.review_entry(manifest)
        # CLI with a synthetic authority reader exercises the actual main branch,
        # without bypassing processing via a hand-written output formatter.
        with patch.object(sys,'argv',['minimal','review']),patch.object(m,'review_entry',return_value=r),patch('sys.stdout',new_callable=io.StringIO) as out:
            m.main();self.assertLess(len(out.getvalue()),400);self.assertNotIn('post_windows',out.getvalue())

    def test_real_authority_and_config_reject_tampering(self):
        r=m.validate_plan()
        self.assertEqual(r['configurations'],1);self.assertEqual(r['seed_collisions'],[])
        plan=m.read(m.DEFAULT_MANIFEST)
        original=m.read(m.ROOT/plan['configuration_template']['path'])
        effective=plan['entries'][0]['effective_configuration']
        self.assertEqual({k:v for k,v in effective.items() if k not in ('id','seed')},
                         {k:v for k,v in original.items() if k not in ('id','seed')})
        bad=deepcopy(plan);bad['entries'].append(deepcopy(bad['entries'][0]))
        path=self.root/'bad-authority.json';put(path,bad)
        with self.assertRaisesRegex(ValueError,'authority'):m.validate_plan(path)
        bad=deepcopy(plan);bad['secondary_reference']['review_sha256']='0'*64;put(path,bad)
        with self.assertRaisesRegex(ValueError,'review hash mismatch'):m.validate_plan(path)

    def test_e8_and_second_attempt_are_rejected_before_docker(self):
        from experiments import development_d3_minimal_ops as ops
        with self.assertRaises(ValueError):ops.check_predecessors({'entries':[{'id':'d3_pilot_E8'}]},0)
        p=self.root/'already_attempted';p.mkdir();put(p/'attempt.json',{'attempt_number':1})
        with self.assertRaises(RuntimeError):ops.ensure_single_experimental_attempt(p)
        r=subprocess.run([sys.executable,'-B','-m','experiments.development_d3_minimal_ops','preflight','--entry','d3_pilot_E8'],capture_output=True,text=True)
        self.assertNotEqual(r.returncode,0);self.assertIn('invalid choice',r.stderr)


if __name__=='__main__':unittest.main()
