"""Direct-80 structural tests; no Docker, network or traffic."""
from copy import deepcopy
from collections import Counter
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from analysis.detection.scientific import protocol as p
from analysis.detection.scientific.direct_contract import configuration,validate_configuration,validate_spec,draft_entries
from analysis.detection.inputs import ContractError,digest,read_json

PATH=p.ROOT/'docs/scientific_protocol_direct_20261108.json'

class DirectProtocolTests(unittest.TestCase):
    def setUp(self):
        self.spec=p.load_spec(PATH,PATH.with_suffix('.sha256').read_text().strip())

    def test_counts_blocks_balance_and_cpu(self):
        slots=p.expected_slots(self.spec)
        self.assertEqual(len(slots),80)
        self.assertEqual(Counter(s['partition'] for s in slots),dict(BASELINE=4,CAL_A=8,CAL_B=8,TEST=60))
        test=[s for s in slots if s['partition']=='TEST']
        self.assertEqual(Counter(s['scenario'] for s in test),dict(L2=20,A3=20,F96=20))
        for block in range(1,21):self.assertEqual({s['scenario'] for s in test if s['block']==block},{'L2','A3','F96'})
        for i in range(3):self.assertEqual(sorted(Counter(row[i] for row in self.spec['test_order']).values()),[6,7,7])
        self.assertEqual(self.spec['drain_seconds'],30)
        self.assertEqual(self.spec['feature_schema_version'],2)
        self.assertEqual(self.spec['cpu_contract']['boundary_tolerance_seconds'],'0.05')
        self.assertFalse(self.spec['execution_release']['allowed'])

    def test_complete_configurations_and_reject_changes(self):
        for scenario in self.spec['scenarios']:
            c=configuration(self.spec,scenario,'fixture',123)
            validate_configuration(self.spec,scenario,'fixture',123,c)
            self.assertEqual(c['normal_traffic']['clients'],2)
            self.assertEqual(c['normal_traffic']['rate'],8)
            self.assertEqual(c['server']['process_pool_workers'],2)
            self.assertEqual(c['topology']['mode'],'direct')
            self.assertFalse(c['load_balancer']['enabled'])
            self.assertEqual(c['duration_seconds'],390)
            self.assertEqual(c['attack']['start_seconds'],150)
            self.assertEqual(c['attack']['duration_seconds'],120)
            self.assertEqual(c['attack']['attackers'],0 if scenario=='L2' else 2)
            if scenario!='L2':
                self.assertEqual(c['attack']['max_concurrent_sends'],96 if scenario=='F96' else 64)
                self.assertEqual(c['attack']['rate'],32 if scenario=='F96' else 4)
            for path,value in [(('id',),'other'),(('seed',),124),(('duration_seconds',),120),
                               (('attack','endpoint'),'/light'),(('attack','max_concurrent_sends'),65),
                               (('attack','attackers'),1),(('server','process_pool_workers'),3),
                               (('topology','mode'),'proxy')]:
                bad=deepcopy(c);target=bad
                for key in path[:-1]:target=target[key]
                target[path[-1]]=value
                with self.assertRaises(ContractError):validate_configuration(self.spec,scenario,'fixture',123,bad)

    def test_seeds_are_deterministic_grouped_and_disjoint(self):
        historical={20261107,42,4481859911000311360}
        entries=draft_entries(self.spec,historical,'fixture-only-not-campaign')
        self.assertEqual(entries,draft_entries(self.spec,historical,'fixture-only-not-campaign'))
        groups={}
        for e in entries:
            group=('TEST',e['block']) if e['partition']=='TEST' else (e['partition'],e['ordinal'])
            groups.setdefault(group,e['seed']);self.assertEqual(groups[group],e['seed'])
        self.assertEqual(len(set(groups.values())),40)
        self.assertFalse(set(groups.values()) & historical)
        collision=entries[0]['seed']
        other=draft_entries(self.spec,historical|{collision},'fixture-only-not-campaign')
        self.assertNotIn(collision,[e['seed'] for e in other])
        with self.assertRaises(ContractError):draft_entries(self.spec,set(),'namespace')

    def test_hash_source_and_historical_preservation(self):
        self.assertEqual(digest(p.DEFAULT_PROTOCOL_PATH),p.DEFAULT_PROTOCOL_SHA256)
        self.assertEqual(p.SPEC['control_scenario'],'C16')
        with self.assertRaises(ContractError):p.load_spec(PATH,'0'*64)
        bad=deepcopy(self.spec);bad['scenario_configurations']['F96']['attack']['rate']=31
        with self.assertRaises(ContractError):validate_spec(bad,p.ROOT)
        bad=deepcopy(self.spec);bad['cpu_contract']['boundary_tolerance_seconds']='0.1'
        with self.assertRaises(ContractError):validate_spec(bad,p.ROOT)
        bad=deepcopy(self.spec);bad['test_order']=[['L2','A3','F96']]*20
        with self.assertRaises(ContractError):validate_spec(bad,p.ROOT)

    def test_structural_contract_cannot_collect(self):
        from experiments.scientific_campaign import Campaign,Halt
        with patch.object(p,'SPEC',self.spec),self.assertRaisesRegex(Halt,'Structural specification'):
            Campaign.__new__(Campaign).run_partition('BASELINE','BASELINE')

    def test_direct_image_roles_and_explicit_contract_selection(self):
        from analysis.detection.scientific.direct_contract import validate_image_lock
        images=dict(victim='sha256:'+'a'*64,source='sha256:'+'b'*64)
        validate_image_lock(images)
        for bad in [dict(images,proxy='nginx'),{'victim':images['victim']},dict(images,source='tag:latest')]:
            with self.assertRaises(ContractError):validate_image_lock(bad)
        import subprocess,os,sys,json
        env=dict(os.environ,SCIENTIFIC_SPEC_PATH=str(PATH),SCIENTIFIC_SPEC_SHA256=digest(PATH))
        result=subprocess.run([sys.executable,'-B','-c','import json; from analysis.detection.scientific.protocol import SPEC,expected_slots; print(json.dumps([SPEC["protocol_id"],len(expected_slots())]))'],
                              env=env,capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(result.stdout),['single-victim-direct-80-20261108',80])

    def test_complete_temporary_plan_and_rebound_tampering(self):
        import json,sys,importlib.metadata
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            def save(path,value):
                path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
                return dict(path=str(path),sha256=digest(path))
            specpath=root/'spec.json';specpath.write_bytes(PATH.read_bytes())
            history=root/'experiments/protocols/history.json';save(history,dict(seed=20261107))
            audit=save(root/'audit.json',dict(sources=[dict(path=str(history),sha256=digest(history),seeds=[20261107])]))
            images=dict(victim='sha256:'+'a'*64,source='sha256:'+'b'*64)
            environment=save(root/'environment.json',dict(daemon_id='fixture-only',kernel='fixture-only',
                python=sys.version.split()[0],images=images,
                packages={n:importlib.metadata.version(n) for n in ('docker','requests','numpy','pandas','scipy','matplotlib','openpyxl')}))
            entries=[]
            for row in draft_entries(self.spec,{20261107},'temporary-validation-only'):
                path=root/'experiments/configs'/(row['id']+'.json')
                ref=save(path,configuration(self.spec,row['scenario'],row['id'],row['seed']))
                entries.append(dict(row,config=ref['path'],config_sha256=ref['sha256']))
            plan=dict(protocol=dict(path=str(specpath),sha256=digest(specpath)),runtime_hashes={},
                      environment=environment,seed_audit=audit,entries=entries,results_root=str(root/'result'))
            planpath=root/'plan.json'
            with patch.object(p,'ROOT',root),patch.object(p,'SPEC',self.spec),patch.object(p,'PROTOCOL_PATH',specpath),patch.object(p,'runtime_hashes',return_value={}):
                save(planpath,plan);self.assertEqual(p.load_plan(planpath,digest(planpath)),plan)
                bad=deepcopy(plan);bad['entries'][0]['seed']=20261107
                save(planpath,bad)
                with self.assertRaisesRegex(ContractError,'Historical seed'):p.load_plan(planpath,digest(planpath))
                bad=deepcopy(plan);path=Path(bad['entries'][-1]['config'])
                c=read_json(path);c['server']['process_pool_workers']=3
                save(path,c);bad['entries'][-1]['config_sha256']=digest(path);save(planpath,bad)
                with self.assertRaisesRegex(ContractError,'Configuration differs'):p.load_plan(planpath,digest(planpath))

if __name__=='__main__':unittest.main()
