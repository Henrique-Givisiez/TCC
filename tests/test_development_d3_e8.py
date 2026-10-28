"""E8 adapter/authority and synthetic full IO; no Docker or experiment execution."""
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from experiments import development_d3_e8 as e
from experiments import development_d3_e8_ops as bridge
from experiments.export_dataset import export_run
from tests.test_development_d3 import fixture,put,csvwrite
from simulator.ground_truth import EVENT_FIELDS


def e8_fixture(path):
    fixture(path,'E8')
    plan=e.base.read(e.DEFAULT_MANIFEST)
    cfg=e.base.ExperimentConfig.load(e.ROOT/plan['entries'][0]['config'])
    put(path/'effective_config.json',json.loads(cfg.to_json()))
    status=e.base.read(path/'run_status.json');status['experiment_id']=cfg.id;put(path/'run_status.json',status)
    for p in (path/'attack_events.csv',path/'source_artifacts/attack_1/output/local_events.csv'):
        rows=e.base.old.csv_rows(p)
        for row in rows:row['experiment_id']=cfg.id
        csvwrite(p,EVENT_FIELDS,rows)
    p=path/'source_artifacts/attack_1/output/journal.jsonl'
    items=[json.loads(x) for x in p.read_text().splitlines()]
    for item in items:
        if item['kind'] in ('event_snapshot','emission_closed'):item['payload']['experiment_id']=cfg.id
    p.write_text(''.join(json.dumps(x)+'\n' for x in items))
    return cfg


class E8Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.control_raw=cls.root/'synthetic_C';cfg=fixture(cls.control_raw,'C')
        cls.control=e.base.old.build_review(cls.control_raw,cfg)
        cls.control['preserved_raw_hashes']={str(p):e.base.sha(p) for p in cls.control_raw.rglob('*') if p.is_file()}
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_real_authority_exact_rule_seed_rate_and_parent_binding(self):
        result=e.validate_plan()
        self.assertEqual(result['configurations'],1)
        p=e.base.read(e.DEFAULT_MANIFEST);parent=e.base.read(e.ROOT/p['predecessor']['manifest_path'])
        self.assertEqual(p['rule'],parent['rule']);self.assertEqual(p['budget'],parent['budget'])
        self.assertNotEqual(p['pilot_seed'],parent['pilot_seed'])
        before=e.base.read(e.ROOT/p['configuration_template']['path'])
        after=p['entries'][0]['effective_configuration']
        expected={**before,'id':e.ENTRY_ID,'seed':p['pilot_seed'],'attack':{**before['attack'],'rate':8}}
        self.assertEqual(after,expected)
        for key,value in parent['runtime_source_hashes'].items():self.assertEqual(e.base.sha(e.ROOT/key),value)
        bad=deepcopy(p);bad['rule']['success_fraction_min']='0.98'
        f=self.root/'bad-rule.json';put(f,bad)
        with self.assertRaises(ValueError):e.validate_plan(f)
        bad=deepcopy(p);bad['predecessor']['review_sha256']='0'*64;put(f,bad)
        with self.assertRaisesRegex(ValueError,'review changed'):e.validate_plan(f)

    def test_service_uses_unchanged_engine_and_attack_denominator_is_960(self):
        raw=self.root/'engine';cfg=e8_fixture(raw)
        a=e._ORIGINAL_ASSESS(raw,cfg,self.control_raw,self.control)
        b=e.assess_raw(raw,cfg,self.control_raw,self.control)
        self.assertEqual(a['service'],b['service'])
        self.assertEqual(a['classification'],b['classification'])
        self.assertTrue(b['classification']['technical_integrity'],b['technical_checks'])
        rate=next(x for x in b['generator']['nominal_start_adherence'] if x['traffic_class']=='attack')
        self.assertEqual(rate['starts'],960);self.assertEqual(rate['nominal_expected'],960)
        self.assertEqual(rate['starts_over_nominal_expectation'],1)
        self.assertFalse(b['generator']['full_scheduled_load_verified'])

    def test_adapter_bindings_restore_on_success_and_failure(self):
        original=(e.base.ROOT,e.base.validate_plan,e.base.assess_raw,bridge.operations.ENTRY_ID,bridge.operations.ACTIVE_MANIFEST)
        with self.assertRaisesRegex(RuntimeError,'sentinel'):
            with e.review_context(),bridge.operations_context():
                self.assertEqual(bridge.operations.ENTRY_ID,e.ENTRY_ID)
                self.assertIs(e.base.validate_plan,e.validate_plan)
                raise RuntimeError('sentinel')
        self.assertEqual(original,(e.base.ROOT,e.base.validate_plan,e.base.assess_raw,bridge.operations.ENTRY_ID,bridge.operations.ACTIVE_MANIFEST))

    def test_rejects_other_entries_and_consumed_attempt_before_docker(self):
        with self.assertRaises(ValueError):bridge.check_predecessors({'entries':[{'id':'d3_minimal_E4_R2'}]},0)
        p=self.root/'attempted';p.mkdir();put(p/'attempt.json',{'attempt_number':1})
        with self.assertRaises(RuntimeError):bridge.operations.ensure_single_experimental_attempt(p)
        r=subprocess.run([sys.executable,'-B','-m','experiments.development_d3_e8_ops','preflight','--entry','d3_pilot_E8'],capture_output=True,text=True)
        self.assertNotEqual(r.returncode,0);self.assertIn('invalid choice',r.stderr)

    def test_full_fixture_export_review_publication_short_output_no_overwrite(self):
        root=self.root/'pipeline';root.mkdir()
        p=deepcopy(e.base.read(e.DEFAULT_MANIFEST));entry=p['entries'][0]
        path=root/entry['config'];path.parent.mkdir(parents=True);path.write_bytes((e.ROOT/entry['config']).read_bytes())
        raw=root/entry['outputs']['raw'];raw.parent.mkdir(parents=True);e8_fixture(raw)
        export_run(raw,root/entry['outputs']['dataset'])
        cref=root/'C-review.json';put(cref,self.control)
        p['secondary_reference'].update(review_path='C-review.json',review_sha256=e.base.sha(cref),raw=str(self.control_raw),
            files=[dict(path='C-review.json',sha256=e.base.sha(cref))]);p['runtime_source_hashes']={}
        manifest=root/'manifest.json';put(manifest,p)
        ops=root/p['results_root']/'operations'/e.ENTRY_ID;pf=ops/'pf-0001/report.json'
        put(pf,dict(ready=True,preflight_id='pf-0001',manifest_sha256=e.base.sha(manifest),approved_entry=e.ENTRY_ID,
            checks=dict(operational_code_sha256={},containers_before=[])))
        put(ops/'attempt.json',dict(authorization_scope=e.ENTRY_ID,manifest_sha256=e.base.sha(manifest),preflight_path=str(pf.relative_to(root)),
            preflight_sha256=e.base.sha(pf),preflight_id='pf-0001',approved_source_hashes={}))
        put(ops/'execution_result.json',dict(returncode=0))
        put(ops/'cleanup_observation.json',dict(containers=[],no_active_containers=True,no_scientific_processes=True,
            port_check_returncode=0,port_8080='State Recv-Q Send-Q Local Address:Port Peer Address:Port\n',observed_epoch=1))
        previous_validator=e.base.validate_plan
        with patch.object(e,'ROOT',root),patch.object(e,'validate_plan',return_value={'synthetic_io_authority':True}),patch.object(e.base.old,'ROOT',root):
            report=e.review_entry(manifest)
            self.assertTrue(report['classification']['technical_integrity'],report['technical_checks'])
            self.assertEqual(report['service']['state'],'recovery_observed')
            self.assertFalse(report['classification']['continued_execution_authorized'])
            self.assertEqual(next(x for x in report['generator']['nominal_start_adherence'] if x['traffic_class']=='attack')['nominal_expected'],960)
            self.assertTrue(report['publication']['evaluation_published_at_utc'])
            self.assertLess(len(json.dumps(e.base.compact(report))),400)
            with self.assertRaises(FileExistsError):e.review_entry(manifest)
        self.assertIs(e.base.validate_plan,previous_validator)
        with patch.object(sys,'argv',['e8','review']),patch.object(e,'review_entry',return_value=report),patch('sys.stdout',new_callable=io.StringIO) as out:
            e.main();self.assertLess(len(out.getvalue()),400);self.assertIn(e.ENTRY_ID,out.getvalue())


if __name__=='__main__':unittest.main()
