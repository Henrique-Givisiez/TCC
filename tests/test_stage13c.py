"""Technical freeze tests; synthetic data and dummy decisions, no experiments."""
from dataclasses import replace
from decimal import Decimal
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from analysis.detection import fit_baseline
from analysis.detection.artifacts import encoded
from analysis.detection.detectors.zscore import ZScore, zscore_spec
from analysis.detection.inputs import ContractError, digest
from analysis.detection.fitting import select_interval
from analysis.detection.protocol import (FROZEN, UNRESOLVED, bind_source, guard_reference,
    load_campaign_series, load_protocol, materialize_seeds, validate_protocol, write_protocol)
from analysis.detection.evaluation.events import load_event_truth, evaluate_events
from analysis.detection.contracts import PolicyScore, DecisionRecord
from tests import test_detection_framework as framework
from tests import test_feature_extraction as extraction

PROTOCOL = Path('experiments/protocols/stage14_protocol.json')


class FitIntervalTests(unittest.TestCase):
    def setUp(self):
        self.f = framework.DetectionFrameworkTests(); self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root = self.f.root

    def source(self, name='normal', rid='n', values=(999,1,2,3,999)):
        return self.f.load(self.f.fixture(name,rid,values),'baseline',family='service',feature='mean_duration_ms')

    def model(self, sources, start=1, end=4, name='model', **kw):
        return fit_baseline(sources,ZScore(),zscore_spec(),self.root/name,
                            fit_start_seconds=start,fit_end_seconds=end,**kw).read('baseline')

    def test_boundaries_exclude_before_and_after(self):
        s=self.source(); selected, record=select_interval(s,1,4)
        self.assertEqual([o.window_index for o in selected.observations],[1,2,3])
        self.assertEqual([o.value for o in selected.observations],list(map(Decimal,[1,2,3])))
        self.assertEqual((record['candidate_windows'],record['valid_observations'],record['nulls_excluded']),(3,3,0))
        m=self.model([s]);self.assertEqual((m['parameters']['mu'],m['parameters']['sigma']),('2','1'))
        self.assertEqual(m['fit_selections'][0]['selected_window_indices'],[1,2,3])
        self.assertEqual(m['sources'][0]['feature_manifest_sha256'],digest(s.root/'feature_manifest.json'))

    def test_exact_campaign_boundaries_48_240(self):
        source=self.source(values=tuple(range(242)))
        model=self.model([source],48,240)
        selection=model['fit_selections'][0]
        self.assertEqual(selection['selected_window_indices'],list(range(48,240)))
        self.assertEqual(selection['candidate_windows'],192)
        self.assertEqual(model['parameters']['mu'],'143.5')
        self.assertAlmostEqual(float(model['parameters']['sigma']),3088**.5)

    def test_tail_does_not_change_moments(self):
        a=self.source();b=self.source('other','other',(0,1,2,3,99999999))
        p=self.model([a])['parameters']; q=self.model([b],name='model2')['parameters']
        for key in ['mu','sigma','mean_exact','variance_exact','n_valid','n_missing']:
            self.assertEqual(p[key],q[key])

    def test_null_excluded_and_contributions_pooled(self):
        a=self.source(values=(999,1,None,3,999))
        b=self.source('second','second',(999,5,7,9,999))
        m=self.model([a,b]);p=m['parameters']
        # pooled observations 1,3,5,7,9 -> mean5, sample variance10.
        self.assertEqual((p['mu'],p['n_valid'],p['n_missing']),('5',5,1))
        self.assertAlmostEqual(float(p['sigma']),10**.5)
        self.assertEqual([r['valid_observations'] for r in m['fit_selections']],[2,3])
        self.assertEqual(m['fit_selections'][0]['nulls_excluded'],1)

    def test_per_run_intervals(self):
        a=self.source();b=self.source('second','second',(0,10,20,30,40))
        m=fit_baseline([a,b],ZScore(),zscore_spec(),self.root/'perrun',fit_intervals={'n':(1,3),'second':(2,4)}).read()
        self.assertEqual(m['parameters']['mu'],'13.25')
        self.assertEqual([x['candidate_windows'] for x in m['fit_selections']],[2,2])

    def test_invalid_empty_unaligned_outside_intervals(self):
        s=self.source()
        for a,b in [(1,1),(2,1),(-1,3),(0,6),('0.5',3),(0,'NaN')]:
            with self.subTest(a=a,b=b),self.assertRaises(ContractError):select_interval(s,a,b)

    def test_explicit_bounds_required(self):
        with self.assertRaisesRegex(ContractError,'Explicit'):
            fit_baseline([self.source()],ZScore(),zscore_spec(),self.root/'bad')

    def test_insufficient_support_rejected(self):
        with self.assertRaises(ContractError):self.model([self.source(values=(0,None,2,None,0))])

    def test_determinism_and_source_unchanged(self):
        s=self.source();before={p:digest(p) for p in s.root.rglob('*') if p.is_file()}
        self.assertEqual(self.model([s]),self.model([s],name='again'))
        self.assertEqual(before,{p:digest(p) for p in before})

    def test_source_mutation_detected(self):
        s=self.source();(s.root/'timeseries/service.csv').write_text('changed')
        with self.assertRaises(ContractError):self.model([s])

    def test_no_events_or_labels_reach_fitter(self):
        s=self.source();original=Path.open
        def guard(path,*a,**kw):
            if path.name in ('labels.csv','attack_events.csv'):raise AssertionError('Truth IO in fitting')
            return original(path,*a,**kw)
        with patch.object(Path,'open',guard):self.model([s])


class OriginalEventTests(unittest.TestCase):
    def setUp(self):
        self.f=extraction.FeatureExtractionTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.extract()
        self.source=framework.load_series(self.f.output,run_id='run1',family='service',feature='request_starts',window_size_seconds=1,feature_schema_version=1,role='development')

    def truth(self):
        return load_event_truth(self.f.output,self.source.reference,stage8_dataset=self.f.dataset)

    def test_original_truth_and_independent_end_drained(self):
        truth=self.truth();e=truth.events[0]
        self.assertEqual((e.event_id,e.actual_start_seconds,e.actual_end_seconds,e.drained_end_seconds),('event1',Decimal('2.2'),Decimal('6.3'),Decimal('6.2')))
        self.assertEqual((e.planned_start_seconds,e.planned_end_seconds),(Decimal(2),Decimal(6)))
        truth.verify()

    def test_other_dataset_refused(self):
        from shutil import copytree
        other=self.f.root/'other';copytree(self.f.dataset,other)
        p=other/'dataset_manifest.json';m=json.loads(p.read_text());m['run_id']='other';p.write_text(json.dumps(m))
        with self.assertRaises(ContractError):load_event_truth(self.f.output,self.source.reference,stage8_dataset=other)

    def test_tampered_events_refused(self):
        p=self.f.dataset/'raw/attacks/attack_events.csv';p.write_text(p.read_text()+'\n')
        with self.assertRaisesRegex(ContractError,'hash'):self.truth()

    def test_changed_feature_manifest_refused(self):
        p=self.f.output/'feature_manifest.json';p.write_text(p.read_text()+'\n')
        with self.assertRaises(ContractError):self.truth()

    def run_event(self,start,end,windows):
        # Exact loader/record verified above. Synthetic decisions isolate attribution
        # arithmetic; validation is mocked ONLY here, never in production.
        truth=self.truth();e=replace(truth.events[0],actual_start_seconds=Decimal(str(start)),actual_end_seconds=Decimal(str(end)))
        truth=replace(truth,events=(e,))
        records=[]
        for i,(a,b,available,positive) in enumerate(windows):
            score=PolicyScore('run1',i,Decimal(str(a)),Decimal(str(b)),Decimal(1),True,None,Decimal(str(b)))
            records.append(DecisionRecord(score,positive,None,Decimal(str(available))))
        from analysis.detection.pipeline import DecisionRun
        run=DecisionRun(tuple(records),None)
        with patch('analysis.detection.pipeline.validate_decision_run',return_value={'source':self.source.reference}),patch.object(type(truth),'verify'):
            return evaluate_events(run,truth,policy='global_overlap_and_availability_within_event_v1')[0]

    def test_mid_window_delay(self):
        r=self.run_event(10.4,15,[(10,11,11,True)])
        self.assertTrue(r.detected);self.assertEqual(r.detection_delay_seconds,Decimal('.6'))

    def test_exact_boundary_delay(self):
        r=self.run_event(10,15,[(10,11,11,True)])
        self.assertEqual(r.detection_delay_seconds,Decimal(1))

    def test_preceding_false_alarm_ignored(self):
        r=self.run_event(10,15,[(8,9,9,True),(10,11,11,False),(11,12,12,True)])
        self.assertEqual(r.detection_delay_seconds,Decimal(2))

    def test_delayed_pre_attack_evidence_ignored(self):
        self.assertFalse(self.run_event(10,15,[(8,9,11,True)]).detected)

    def test_never_detected_nulls(self):
        r=self.run_event(10,15,[(10,11,11,False),(15,16,16,True)])
        self.assertEqual((r.detected,r.first_detection_available_at_seconds,r.detection_delay_seconds),(False,None,None))

    def test_global_periodic_silence_counts(self):
        # Fixture's global event [2.2,6.3) includes silence [3,5).
        r=self.run_event(2.2,6.3,[(3,4,4,True)])
        self.assertTrue(r.detected);self.assertEqual(r.detection_delay_seconds,Decimal('1.8'))

    def test_requires_explicit_event_policy(self):
        with self.assertRaises(ContractError):evaluate_events(None,self.truth(),policy=None)


    def test_window_closing_exactly_at_end_can_detect(self):
        r=self.run_event(10,15,[(14,15,15,True)])
        self.assertTrue(r.detected);self.assertEqual(r.detection_delay_seconds,Decimal(5))

    def test_compute_after_event_does_not_gain_unmeasured_grace(self):
        self.assertFalse(self.run_event(10,15,[(14,15,Decimal('15.1'),True)]).detected)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.f=framework.DetectionFrameworkTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.doc,self.ref=load_protocol(PROTOCOL)

    def test_schema_frozen_unresolved(self):
        self.assertEqual(validate_protocol(self.doc),self.doc)
        self.assertEqual(self.doc['frozen'],FROZEN)
        self.assertEqual(set(self.doc['unresolved']),set(UNRESOLVED))
        self.assertEqual(sum(FROZEN['seed_counts'].values()),34)
        self.assertEqual(self.doc['provenance']['run_count'],66)

    def test_missing_frozen_or_unresolved_rejected(self):
        for area,key in [('frozen','features'),('unresolved','numerical_thresholds')]:
            d=copy.deepcopy(self.doc);del d[area][key]
            with self.assertRaises(ContractError):validate_protocol(d)

    def test_approved_values_cannot_change_silently(self):
        for key,value in [('window_size_seconds',2),('operation','/light'),('calibration_strategy','attack_tuned')]:
            d=copy.deepcopy(self.doc);d['frozen'][key]=value
            with self.assertRaises(ContractError):validate_protocol(d)
        self.assertEqual(FROZEN['cov']['primary_lookback'],6)
        self.assertEqual(FROZEN['cov']['sensitivity_lookbacks'],[3,12])
        self.assertEqual(FROZEN['periodic']['burst_seconds'],2)
        self.assertEqual(FROZEN['periodic']['period_seconds'],6)
        self.assertEqual([FROZEN['durations'][k] for k in ['pre','attack','post']],[48,36,60])
        self.assertEqual(len(FROZEN['features']),5)
        self.assertEqual(FROZEN['window_truth']['primary'],'pure_windows_only')

    def test_deterministic_disjoint_seed_generation(self):
        a=materialize_seeds(self.doc['seeds']['namespace']);b=materialize_seeds(self.doc['seeds']['namespace'])
        self.assertEqual(a,b);values=[s for p in a.values() for s in p]
        self.assertEqual([len(a[p]) for p in ('baseline','calibration','test')],[6,12,16])
        self.assertEqual(len(set(values)),34);self.assertFalse(set(values)&{101,211,307,401,503})
        d=copy.deepcopy(self.doc);d['seeds'].update(status='MATERIALIZED',partitions=a);validate_protocol(d)
        d['seeds']['partitions']['test'][0]=a['baseline'][0]
        with self.assertRaises(ContractError):validate_protocol(d)

    def test_hash_bytes_and_no_overwrite(self):
        self.assertEqual(load_protocol(PROTOCOL)[1],self.ref)
        path=self.f.root/'protocol.json';write_protocol(path,self.doc)
        self.assertEqual(digest(path),self.ref['protocol_hash'])
        with self.assertRaises(FileExistsError):write_protocol(path,self.doc)
        path.write_text(path.read_text()+'\n')
        with self.assertRaises(ContractError):load_protocol(path,expected_hash=self.ref['protocol_hash'])

    def test_revision_requires_version_and_predecessor(self):
        d=copy.deepcopy(self.doc);d['limitations'].append('Additional declared limitation')
        with self.assertRaises(ContractError):write_protocol(self.f.root/'invalid.json',d,previous=self.ref)
        d.update(protocol_version=2,previous_protocol_hash=self.ref['protocol_hash'])
        ref=write_protocol(self.f.root/'v2.json',d,previous=self.ref)
        self.assertNotEqual(ref['protocol_hash'],self.ref['protocol_hash'])

    def test_test_locked_before_loading(self):
        with patch('analysis.detection.inputs.load_series',side_effect=AssertionError('TEST accessed')):
            with self.assertRaisesRegex(ContractError,'TEST locked'):
                load_campaign_series('/does/not/exist',protocol_reference=self.ref,partition='test',seed=123,scenario='B')

    def test_test_refused_for_fit_calibration_selection_evaluation(self):
        # Tampered/replayed envelope is rejected too, regardless of method callback.
        r={'role':'test','campaign':{'protocol':self.ref,'partition':'test','seed':123,'scenario':'B'}}
        for operation in ['fit','calibration','parameter_selection','scoring','evaluation']:
            with self.subTest(operation=operation),self.assertRaisesRegex(ContractError,'TEST locked'):
                guard_reference(r,operation)

    def test_binding_and_frozen_fit_interval(self):
        d=copy.deepcopy(self.doc);d['seeds'].update(status='MATERIALIZED',partitions=materialize_seeds(d['seeds']['namespace']))
        d.update(protocol_version=2,previous_protocol_hash=self.ref['protocol_hash'])
        ref=write_protocol(self.f.root/'materialized.json',d,previous=self.ref)
        source=self.f.load(self.f.baseline,'baseline')
        bound=bind_source(source,ref,partition='baseline',seed=d['seeds']['partitions']['baseline'][0],scenario='B')
        guard_reference(bound.reference,'fit')
        with self.assertRaisesRegex(ContractError,'frozen fit_interval'):
            fit_baseline([bound],framework.FakeFitter(),self.f.spec,self.f.root/'bad',fit_start_seconds=0,fit_end_seconds=5)
        with self.assertRaises(ContractError):bind_source(source,ref,partition='calibration',seed=d['seeds']['partitions']['calibration'][0],scenario='B')

    def test_existing_role_test_refused_fitting(self):
        with self.assertRaises(ContractError):
            fit_baseline([self.f.load(self.f.test,'test')],framework.FakeFitter(),self.f.spec,self.f.root/'bad',fit_start_seconds=0,fit_end_seconds=5)


class DummyEventEvaluator:
    """Test-only truth consumer; no threshold or efficacy calculation."""
    def evaluate(self, inputs, plan):
        assert inputs.events is not None
        return {'test_only_original_event_count':len(inputs.events)}


class EventPipelineIntegrationTests(unittest.TestCase):
    def test_verified_events_persist_in_evaluation_artifact(self):
        f=extraction.FeatureExtractionTests();f.setUp();self.addCleanup(f.doCleanups);f.extract()
        g=framework.DetectionFrameworkTests();g.setUp();self.addCleanup(g.doCleanups)
        from analysis.detection import score_run,calibrate,decide
        from analysis.detection.evaluation import evaluate,EvaluationPlan
        model=g.fit()
        c=score_run(g.load(g.calibration,'calibration'),framework.FakeDetector(),g.spec,g.root/'cal-score',baseline=model)
        policy=calibrate([c],framework.FakeCalibrator(),g.policy_spec,g.root/'cal-policy')
        source=framework.load_series(f.output,run_id='run1',family='service',feature='request_starts',window_size_seconds=1,feature_schema_version=1,role='development')
        # Guard both truth files throughout fitting/scoring/calibration/decision.
        original=Path.open
        def guard(path,*args,**kw):
            if path.name in ('labels.csv','attack_events.csv'):raise AssertionError('Truth leakage')
            return original(path,*args,**kw)
        with patch.object(Path,'open',guard):
            scores=score_run(source,framework.FakeDetector(),g.spec,g.root/'scores',baseline=model)
            decisions=decide(scores,framework.FakePolicy(),g.policy_spec,policy,g.root/'decisions')
        truth=load_event_truth(f.output,source.reference,stage8_dataset=f.dataset)
        result=evaluate(scores,decisions,f.output,DummyEventEvaluator(),g.spec,
                        EvaluationPlan('pure_windows_only',{},'closure'),g.root/'event-evaluation',
                        event_truth=truth,event_policy='global_overlap_and_availability_within_event_v1').read()
        self.assertEqual(result['event_truth']['dataset_manifest_sha256'],source.reference['dataset_manifest_sha256'])
        self.assertEqual(result['event_results'][0]['detection_delay_seconds'],'0.8')
        self.assertTrue(result['event_results'][0]['event_detected'])
        self.assertEqual(result['results']['test_only_original_event_count'],1)


class AdditionalIsolationTests(unittest.TestCase):
    def test_generic_test_input_locked_before_io(self):
        from analysis.detection.inputs import load_series
        with patch.object(Path,'open',side_effect=AssertionError('Unexpected input IO')):
            with self.assertRaisesRegex(ContractError,'TEST locked'):
                load_series('/absent',run_id='test',family='service',feature='request_starts',
                            window_size_seconds=1,feature_schema_version=1,role='test')

    def test_test_reference_cannot_calibrate(self):
        f=framework.DetectionFrameworkTests();f.setUp();self.addCleanup(f.doCleanups)
        from analysis.detection import score_run,calibrate
        scores=score_run(f.load(),framework.FakeDetector(),f.spec,f.root/'score')
        manifest=scores.artifact.read();manifest['source']['role']='test'
        with patch('analysis.detection.pipeline.validate_score_run',return_value=manifest):
            with self.assertRaisesRegex(ContractError,'TEST locked'):
                calibrate([scores],framework.FakeCalibrator(),f.policy_spec,f.root/'bad')

    def test_callbacks_never_read_events_in_all_pre_evaluation_phases(self):
        f=framework.DetectionFrameworkTests();f.setUp();self.addCleanup(f.doCleanups)
        original=Path.open
        def guard(path,*args,**kw):
            if path.name in ('labels.csv','attack_events.csv'):raise AssertionError('Truth leakage')
            return original(path,*args,**kw)
        with patch.object(Path,'open',guard):f.pipeline()

    def test_protocol_run_reference_includes_test_without_opening_test(self):
        from analysis.detection.protocol import run_protocol_reference
        import tempfile
        document,reference=load_protocol(PROTOCOL)
        document=copy.deepcopy(document)
        document['seeds'].update(status='MATERIALIZED',partitions=materialize_seeds(document['seeds']['namespace']))
        document.update(protocol_version=2,previous_protocol_hash=reference['protocol_hash'])
        with tempfile.TemporaryDirectory() as temp:
            ref=write_protocol(Path(temp)/'v2.json',document,previous=reference)
            run=run_protocol_reference(ref,partition='test',seed=document['seeds']['partitions']['test'][0],scenario='P')
            self.assertEqual((run['partition'],run['protocol_hash']),('test',ref['protocol_hash']))

    def test_changed_initial_version_rejected_without_revision(self):
        document,_=load_protocol(PROTOCOL);document['limitations'].append('Changed')
        with self.assertRaisesRegex(ContractError,'new version'):
            write_protocol(Path('/tmp/unwritten-stage13c-protocol.json'),document)


class PureWindowPolicyTests(unittest.TestCase):
    def test_boundary_excluded_without_half_threshold(self):
        from analysis.detection.evaluation import WindowTruth,pure_window_groups
        rows=tuple(WindowTruth('run',i,Decimal(i),Decimal(i+1),Decimal(v),Decimal(v))
                   for i,v in enumerate(['0','.1','.5','.9','1']))
        groups=pure_window_groups(rows)
        self.assertEqual([r.window_index for r in groups['benign']],[0])
        self.assertEqual([r.window_index for r in groups['attack']],[4])
        self.assertEqual([r.window_index for r in groups['boundary']],[1,2,3])
        self.assertEqual([r.attack_event_overlap_fraction for r in groups['boundary']],list(map(Decimal,['.1','.5','.9'])))
