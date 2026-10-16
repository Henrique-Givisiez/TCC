"""Exact empirical policy tests: synthetic data only, never campaign artifacts."""
from dataclasses import replace
from decimal import Decimal as D, localcontext, ROUND_UP
from fractions import Fraction
from itertools import permutations
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from analysis.detection import score_run, calibrate, decide
from analysis.detection.artifacts import encoded
from analysis.detection.contracts import CalibrationScores, PolicyScore, ScoreValue
from analysis.detection.detectors.cov import CoV, cov_spec
from analysis.detection.empirical import EmpiricalUpperTail, StrictUpperTail, upper_tail_spec
from analysis.detection.inputs import ContractError
from tests import test_detection_framework as fixtures


def run(values, rid='synthetic', seed=None):
    return CalibrationScores(rid, tuple(PolicyScore(rid, i, D(i), D(i+1),
        None if x is None else D(str(x)), x is not None,
        'missing' if x is None else None, D(i+1)) for i,x in enumerate(values)), seed)


def fitted(values, alpha='0.01'):
    return EmpiricalUpperTail().calibrate((run(values),), upper_tail_spec(alpha=alpha).config)


class EmpiricalQuantileTests(unittest.TestCase):
    def test_manual_integer_position(self):
        p=fitted([1,2,3,4,5], '0.5')
        self.assertEqual((p['quantile_index_zero_based'],p['threshold']),(2,D(3)))

    def test_manual_between_positions(self):
        p=fitted([1,2,3,4,5], '0.2')
        self.assertEqual((p['quantile_index_zero_based'],p['threshold']),(4,D(5)))
        self.assertEqual(fitted([1,2,3,4,5], '0.6')['threshold'],D(3))

    def test_near_both_extremes(self):
        self.assertEqual(fitted([1,2,3,4,5], '0.999999999999999999999999999999')['threshold'],D(2))
        self.assertEqual(fitted([1,2,3,4,5], '0.000000000000000000000000000001')['threshold'],D(5))

    def test_large_preregistered_alphas(self):
        # ceil(9999*q): 9949.005 -> 9950; 9899.01 -> 9900; 9799.02 -> 9800.
        for alpha,j in [('0.005',9950),('0.01',9900),('0.02',9800)]:
            with self.subTest(alpha=alpha):
                p=fitted(range(10000),alpha)
                self.assertEqual(p['quantile_index_zero_based'],j)
                self.assertEqual(p['threshold'],D(j))

    def test_decimal_and_fraction_alpha_exact(self):
        expected=fitted(range(100),'0.01')
        for alpha in [D('0.01'),Fraction(1,100)]:
            self.assertEqual(fitted(range(100),alpha),expected)
        self.assertEqual(expected['config']['alpha'],{'numerator':'1','denominator':'100'})

    def test_reject_float_alpha(self):
        with self.assertRaises(ContractError):upper_tail_spec(alpha=0.01)

    def test_invalid_alpha(self):
        for alpha in ['0','1','-1','1.1','NaN','Infinity','-Infinity','junk',None,True]:
            with self.subTest(alpha=alpha),self.assertRaises(ContractError):upper_tail_spec(alpha=alpha)

    def test_noncanonical_or_modified_config_rejected(self):
        cfg=dict(upper_tail_spec(alpha='0.01').config)
        for change in [dict(direction='lower-tail'),dict(comparison='>='),dict(extra=1),dict(alpha={'numerator':'2','denominator':'200'})]:
            with self.subTest(change=change),self.assertRaises(ContractError):
                EmpiricalUpperTail().calibrate((run([1,2]),),dict(cfg,**change))

    def test_single_observation(self):
        p=fitted(['1.234567890123456789'])
        self.assertEqual((p['n_valid'],p['quantile_index_zero_based'],p['threshold']),(1,0,D('1.234567890123456789')))
        self.assertEqual(p['realized_calibration_fpr'],D(0))

    def test_zero_valid_rejected(self):
        for values in [[],[None,None]]:
            with self.subTest(values=values),self.assertRaisesRegex(ContractError,'N must be >= 1'):fitted(values)

    def test_repeated_values_ties_negative(self):
        p=fitted([1,2,2,2,3],'0.5')
        self.assertEqual((p['scores_below'],p['scores_equal'],p['scores_above']),(1,3,1))
        self.assertEqual(p['realized_calibration_fpr'],D('0.2'))

    def test_all_equal_no_epsilon_or_threshold_adjustment(self):
        p=fitted([7]*20)
        self.assertEqual(p['threshold'],D(7))
        self.assertEqual((p['scores_equal'],p['scores_above'],p['realized_calibration_fpr']),(20,0,D(0)))

    def test_negative_decimal_scores(self):
        p=fitted(['-3.25','-2.125','-1.00000000000000000001'],'0.5')
        self.assertEqual(p['threshold'],D('-2.125'))

    def test_nulls_counted_per_run_and_global_pool_not_run_quantiles(self):
        a=run([1,None],'a',991001);b=run([2,3,4],'b',991002);c=run([None],'c',991003)
        cfg=upper_tail_spec(alpha='0.5').config
        p=EmpiricalUpperTail().calibrate((a,b,c),cfg)
        self.assertEqual((p['n_candidate'],p['n_valid'],p['n_unavailable'],p['threshold']),(6,4,2,D(3)))
        self.assertEqual(p['support_by_run'][0]['seed'],991001)
        self.assertEqual(p['support_by_run'][1]['scores_above'],1)
        self.assertEqual(p['support_by_run'][2]['realized_run_fpr'],None)
        self.assertEqual(p['realized_calibration_fpr_exact'],{'numerator':1,'denominator':4})

    def test_input_value_order_deterministic(self):
        expected=fitted([1,2,3,4,5],'0.5')
        for values in permutations([1,2,3,4,5]):self.assertEqual(fitted(values,'0.5'),expected)

    def test_run_order_deterministic(self):
        a,b=run([1,2],'a',991001),run([3,4],'b',991002);cfg=upper_tail_spec(alpha='0.5').config
        self.assertEqual(EmpiricalUpperTail().calibrate((a,b),cfg),EmpiricalUpperTail().calibrate((b,a),cfg))

    def test_decimal_context_independence(self):
        expected=encoded(fitted(range(101),'0.2'))
        with localcontext() as context:
            context.prec=3;context.rounding=ROUND_UP
            self.assertEqual(encoded(fitted(range(101),'0.2')),expected)

    def test_nonfinite_and_invalid_score_rejected(self):
        original=run([1]).records[0]
        for value in [D('NaN'),D('Infinity'),D('-Infinity'),'bad',1.0]:
            with self.subTest(value=value),self.assertRaises(ContractError):
                EmpiricalUpperTail().calibrate((CalibrationScores('synthetic',(replace(original,score=value),)),),upper_tail_spec(alpha='0.01').config)

    def test_invalid_available_null_reason_flags(self):
        original=run([1]).records[0]
        for change in [dict(score=None),dict(reason='unexpected'),dict(score_available=False),dict(score_available=1)]:
            with self.subTest(change=change),self.assertRaises(ContractError):
                EmpiricalUpperTail().calibrate((CalibrationScores('synthetic',(replace(original,**change),)),),upper_tail_spec(alpha='0.01').config)

    def test_run_identity_duplicates_and_unordered_rejected(self):
        cfg=upper_tail_spec(alpha='0.01').config;a=run([1,2],'a',991001)
        for inputs in [(a,a),(a,run([3],'b',991001)),(replace(a,run_id='other'),),
                       (replace(a,records=tuple(reversed(a.records))),)]:
            with self.subTest(inputs=inputs),self.assertRaises(ContractError):EmpiricalUpperTail().calibrate(inputs,cfg)

    def test_callbacks_reject_paths_labels_and_noncontracts(self):
        for payload in [({'labels':[1]},),({'path':'TEST'},)]:
            with self.assertRaises(ContractError):EmpiricalUpperTail().calibrate(payload,upper_tail_spec(alpha='0.01').config)


class StrictDecisionTests(unittest.TestCase):
    def setUp(self):
        self.cfg=upper_tail_spec(alpha='0.5').config
        self.params=fitted([-3,-2,-1],'0.5')
        self.policy=StrictUpperTail();self.state=self.policy.start_run(self.params,self.cfg)

    def test_less_equal_above_including_negative_threshold(self):
        for value,expected in [('-3',False),('-2',False),('-1',True),('0',True)]:
            self.assertEqual(self.policy.decide(run([value]).records[0],self.state).decision,expected)

    def test_unavailable_stays_unavailable(self):
        r=run([None]).records[0];out=self.policy.decide(r,self.state)
        self.assertIsNone(out.decision);self.assertEqual(out.reason,'missing');self.assertEqual(out.available_at_seconds,r.available_at_seconds)

    def test_causal_observation_10_11_available_at_11(self):
        r=PolicyScore('synthetic',10,D(10),D(11),D(0),True,None,D(11))
        self.assertEqual(self.policy.decide(r,self.state).available_at_seconds,D(11))
        with self.assertRaises(ContractError):self.policy.decide(replace(r,available_at_seconds=D(10)),self.state)

    def test_delayed_availability_preserved(self):
        r=replace(run([1]).records[0],available_at_seconds=D(5))
        self.assertEqual(self.policy.decide(r,self.state).available_at_seconds,D(5))

    def test_stateless_repeated_decisions(self):
        r=run([1]).records[0]
        self.assertEqual(self.policy.decide(r,self.state),self.policy.decide(r,self.state))
        with self.assertRaises(AttributeError):self.state.value=D(999)

    def test_serialization_roundtrip(self):
        p=json.loads(encoded(self.params));state=self.policy.start_run(p,self.cfg)
        self.assertEqual(self.policy.decide(run([1]).records[0],state),self.policy.decide(run([1]).records[0],self.state))

    def test_threshold_nonfinite_config_or_index_tamper(self):
        for change in [dict(threshold='NaN'),dict(threshold='Infinity'),dict(threshold=1.0),dict(quantile_index_zero_based=999),dict(scores_equal=0),dict(config={})]:
            with self.subTest(change=change),self.assertRaises(ContractError):self.policy.start_run(dict(self.params,**change),self.cfg)

    def test_labels_not_accepted(self):
        with self.assertRaises(ContractError):self.policy.decide({'score':1,'label':True},self.state)


class EmpiricalIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.DetectionFrameworkTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.cfg=upper_tail_spec(alpha='0.01')
        self.source=self.f.load(self.f.fixture('synthetic-development-calibrator','dev-cal',tuple(range(1,31))),role='calibration',feature='mean_duration_ms')
        self.target=self.f.load(self.f.fixture('synthetic-development-target','dev-target',(1,2,3,4,5,6,7,None,9,10,11,12,13)),role='development',feature='mean_duration_ms')

    def scores(self,source,path):
        return score_run(source,CoV(),cov_spec(lookback=6),self.f.root/path)

    def test_end_to_end_fixture_no_ground_truth_provenance_and_repetition(self):
        original=Path.open
        def guard(p,*a,**kw):
            if p.name in ('labels.csv','attack_events.csv'):raise AssertionError('ground truth IO')
            return original(p,*a,**kw)
        with patch.object(Path,'open',guard):
            scores=self.scores(self.source,'cal-scores')
            artifact=calibrate([scores],EmpiricalUpperTail(),self.cfg,self.f.root/'threshold')
            again=calibrate([scores],EmpiricalUpperTail(),self.cfg,self.f.root/'threshold-repeat')
            self.assertEqual(artifact.manifest_sha256,again.manifest_sha256)
            target=self.scores(self.target,'target-scores')
            output=decide(target,StrictUpperTail(),self.cfg,artifact,self.f.root/'decisions')
            repeated=decide(target,StrictUpperTail(),self.cfg,artifact,self.f.root/'decisions-repeat')
            self.assertEqual(output.artifact.manifest_sha256,repeated.artifact.manifest_sha256)
        self.assertEqual(artifact.read()['provenance']['component']['qualified_class'],'analysis.detection.empirical.EmpiricalUpperTail')
        self.assertEqual(output.artifact.read()['provenance']['component']['qualified_class'],'analysis.detection.empirical.StrictUpperTail')
        for score,decision in zip(target.records,output.records):
            self.assertEqual(decision.available_at_seconds,score.available_at_seconds)
            if not score.score_available:self.assertIsNone(decision.decision)
        self.assertIsNone(output.records[7].decision)
        self.assertNotIn('labels.csv',json.dumps(artifact.read()))

    def test_noncalibration_role_and_test_reference_rejected(self):
        for role in ['development','baseline','test']:
            source=self.target
            reference=dict(source.reference,role=role)
            from analysis.detection.pipeline import ScoreRun
            scores=self.scores(source,'scores-'+role)
            manifest=scores.artifact.read();manifest['source']=reference
            with patch('analysis.detection.pipeline.validate_score_run',return_value=manifest):
                with self.assertRaises(ContractError):calibrate([scores],EmpiricalUpperTail(),self.cfg,self.f.root/('bad-'+role))
        with self.assertRaisesRegex(ContractError,'TEST locked'):self.f.load(self.f.test,role='test')

    def test_incompatible_feature_and_detector_config_rejected(self):
        a=self.scores(self.source,'first')
        other=self.f.load(self.f.calibration,role='calibration',feature='request_starts')
        b=self.scores(other,'second')
        with self.assertRaisesRegex(ContractError,'model/feature mismatch'):calibrate([a,b],EmpiricalUpperTail(),self.cfg,self.f.root/'mixed')
        third=self.f.load(self.f.fixture('different-config','third-run'),role='calibration',feature='request_starts')
        c=score_run(third,CoV(),cov_spec(lookback=3),self.f.root/'different-L')
        with self.assertRaisesRegex(ContractError,'model/feature mismatch'):calibrate([b,c],EmpiricalUpperTail(),self.cfg,self.f.root/'mixed-L')

    def test_tampered_lineage_or_artifact_rejected(self):
        s=self.scores(self.source,'scores')
        table=self.source.root/'timeseries/service.csv';table.write_bytes(table.read_bytes()+b'\n')
        with self.assertRaises(ContractError):calibrate([s],EmpiricalUpperTail(),self.cfg,self.f.root/'bad')

    def test_verified_seed_metadata_forwarded_by_pipeline(self):
        scores=self.scores(self.source,'scores-seed')
        manifest=scores.artifact.read()
        manifest['source']['campaign']={'seed':991001,'protocol':{'path':'synthetic','protocol_hash':'fixture'}}
        with patch('analysis.detection.pipeline.validate_score_run',return_value=manifest),patch('analysis.detection.protocol.guard_reference'),patch('analysis.detection.protocol.load_protocol',return_value=({'protocol_version':1},{})):
            artifact=calibrate([scores],EmpiricalUpperTail(),self.cfg,self.f.root/'seed-threshold')
        self.assertEqual(artifact.read()['parameters']['support_by_run'][0]['seed'],991001)

    def test_pipeline_supplied_temporal_selection_only(self):
        scores=self.scores(self.source,'scores-selection');manifest=scores.artifact.read()
        manifest['source']['campaign']={'seed':991001,'protocol':{'path':'synthetic','protocol_hash':'fixture'}}
        selected=scores.records[10:20]
        with patch('analysis.detection.pipeline.validate_score_run',return_value=manifest),patch('analysis.detection.protocol.guard_reference'),patch('analysis.detection.protocol.load_protocol',return_value=({'protocol_version':2},{})),patch('analysis.detection.horizons.select_campaign_records',return_value=(selected,{'synthetic_selection_only':True})):
            artifact=calibrate([scores],EmpiricalUpperTail(),self.cfg,self.f.root/'selected-threshold')
        self.assertEqual(artifact.read()['parameters']['n_candidate'],10)
        self.assertEqual(artifact.read()['parameters']['n_valid'],10)
