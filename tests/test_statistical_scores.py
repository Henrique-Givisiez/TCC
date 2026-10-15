"""Stage 12A numeric and artifact tests; no thresholds, labels or efficacy claims."""
from dataclasses import replace
from decimal import Decimal, localcontext, ROUND_UP
from fractions import Fraction
import json
from pathlib import Path
import statistics
import unittest
from unittest.mock import patch

import tests.test_detection_framework as fixtures
from analysis.detection import fit_baseline, score_run, load_series, load_scores
from analysis.detection.artifacts import digest, open_artifact
from analysis.detection.contracts import Observation, ObservedSeries
from analysis.detection.detectors.zscore import ZScore, zscore_spec
from analysis.detection.detectors.cov import CoV, cov_spec
from analysis.detection.inputs import ContractError

D = Decimal


def observations(values, run_id='synthetic'):
    return tuple(Observation(run_id, i, D(i), D(i+1), None if v is None else D(str(v)))
                 for i, v in enumerate(values))


def series(values, run_id='synthetic'):
    return ObservedSeries(run_id, 'service', 'mean_duration_ms', D(1), 1,
                          observations(values, run_id))


def zparams(values):
    return ZScore().fit((series(values),), zscore_spec().config)


def rolling(values, lookback):
    method = CoV(); state = method.start_run(None, cov_spec(lookback=lookback).config)
    return tuple(method.update(o, state) for o in observations(values))


class ZScoreTests(unittest.TestCase):
    def assertClose(self, actual, expected):
        self.assertAlmostEqual(float(actual), float(expected), places=13)

    def test_known_baseline_and_signed_scores(self):
        # n=3, mu=2, sum squared deviations=2, s=sqrt(2/(3-1))=1.
        p=zparams([1,2,3])
        self.assertEqual((p['mu'],p['sigma'],p['n_valid'],p['ddof']), (D(2),D(1),3,1))
        method=ZScore();state=method.start_run(p,zscore_spec().config)
        scores=[method.update(o,state).score for o in observations([3,1,2])]
        self.assertEqual(scores,[D(1),D(-1),D(0)])

    def test_noninteger_mean_and_std_against_independent_library(self):
        values=[1,4,8,9,12]
        p=zparams(values)
        self.assertClose(p['mu'],statistics.mean(values))
        self.assertClose(p['sigma'],statistics.stdev(values))
        score=ZScore().update(observations([7])[0],ZScore().start_run(p,zscore_spec().config)).score
        self.assertClose(score,(7-statistics.mean(values))/statistics.stdev(values))

    def test_null_score_preserved(self):
        method=ZScore();state=method.start_run(zparams([1,2,3]),zscore_spec().config)
        out=method.update(observations([None])[0],state)
        self.assertIsNone(out.score);self.assertEqual(out.reason,'missing_observation')

    def test_baseline_null_excluded_and_counted(self):
        p=zparams([1,None,2,3,None])
        self.assertEqual((p['mu'],p['sigma'],p['n_valid'],p['n_missing']),(D(2),D(1),3,2))
        self.assertEqual(p['support_by_run'],[dict(run_id='synthetic',n_valid=3,n_missing=2)])

    def test_multiple_runs_equal_observation_weight_no_synthetic_adjacency(self):
        p=ZScore().fit((series([1], 'a'),series([2,3], 'b')),zscore_spec().config)
        self.assertEqual((p['mu'],p['sigma'],p['n_valid']),(D(2),D(1),3))
        self.assertEqual(len(p['support_by_run']),2)

    def test_insufficient_baseline(self):
        for values in [[],[1],[None],[None,1,None]]:
            with self.subTest(values=values),self.assertRaisesRegex(ContractError,'insufficient'):
                zparams(values)

    def test_zero_sigma_refuses_baseline(self):
        for values in [[0,0],[7,7,7],[7,None,7]]:
            with self.subTest(values=values),self.assertRaisesRegex(ContractError,'zero_baseline_sigma'):
                zparams(values)

    def test_baseline_required_and_malformed_parameters_refused(self):
        with self.assertRaises(ContractError):ZScore().start_run(None,zscore_spec().config)
        p=zparams([1,2,3]);p['sigma']='0'
        with self.assertRaises(ContractError):ZScore().start_run(p,zscore_spec().config)
        p=zparams([1,2,3]);p['mu']='100'
        with self.assertRaisesRegex(ContractError,'disagree'):ZScore().start_run(p,zscore_spec().config)

    def test_ddof_population_not_silently_accepted(self):
        config=dict(zscore_spec().config,ddof=0)
        with self.assertRaises(ContractError):ZScore().fit((series([1,2,3]),),config)

    def test_large_offset_preserves_real_variation(self):
        a=10**80
        p=zparams([a+1,a+2,a+3])
        self.assertEqual(p['sigma'],D(1))
        state=ZScore().start_run(p,zscore_spec().config)
        self.assertEqual(ZScore().update(observations([a+3])[0],state).score,D(1))

    def test_exact_zero_variance_not_rounding_epsilon(self):
        p=zparams(['1e-100','2e-100','3e-100'])
        self.assertEqual(p['sigma'],D('1e-100'))
        self.assertEqual(ZScore().update(observations(['3e-100'])[0],ZScore().start_run(p,zscore_spec().config)).score,D(1))

    def test_decimal_context_independent(self):
        expected=zparams([1,3,8])
        with localcontext() as ctx:
            ctx.prec=5;ctx.rounding=ROUND_UP
            actual=zparams([1,3,8])
        self.assertEqual(expected,actual)


class CoVTests(unittest.TestCase):
    def test_two_values_sample_formula_and_includes_current(self):
        # [1,3] -> mean=2, sample s=sqrt(2), CV=sqrt(2)/2.
        r=rolling([1,3],2)
        self.assertIsNone(r[0].score)
        self.assertEqual(r[0].reason,'warmup_consecutive_valid')
        self.assertAlmostEqual(float(r[1].score),2**0.5/2,places=14)

    def test_larger_lookback_independent_manual_result(self):
        # [2,4,6] -> mean=4, sample s=2 -> CV=0.5.
        r=rolling([2,4,6,8],3)
        self.assertTrue(all(o.score is None for o in r[:2]))
        self.assertEqual(r[2].score,D('0.5'))
        self.assertAlmostEqual(float(r[3].score),2/6,places=14)

    def test_gap_resets_and_requires_consecutive_valid_recovery(self):
        r=rolling([2,4,6,None,2,4,6],3)
        self.assertEqual(r[2].score,D('0.5'))
        self.assertEqual(r[3].reason,'missing_observation_reset')
        self.assertEqual([o.reason for o in r[4:6]],['warmup_consecutive_valid']*2)
        self.assertEqual(r[6].score,D('0.5'))

    def test_repeated_gaps_do_not_collect_last_valid_values(self):
        r=rolling([2,None,4,None,6,None],2)
        self.assertTrue(all(x.score is None for x in r))

    def test_zero_mean_no_epsilon(self):
        for values in [[0,0],[-1,1]]:
            with self.subTest(values=values):
                out=rolling(values,2)[-1]
                self.assertIsNone(out.score);self.assertEqual(out.reason,'zero_lookback_mean')

    def test_near_zero_mean_still_mathematically_defined(self):
        out=rolling(['1e-100','3e-100'],2)[-1]
        self.assertAlmostEqual(float(out.score),2**0.5/2,places=14)
        # Deliberate signed algebraic fixture: nearly cancelling mean is not masked.
        out=rolling(['-1','1.000000000000000000000000000002'],2)[-1]
        self.assertGreater(out.score,D('1e29'))

    def test_constant_nonzero_zero_cv_and_sliding_history(self):
        r=rolling([5,5,5,10,10,10],3)
        self.assertEqual(r[2].score,D(0));self.assertGreater(r[3].score,D(0))
        self.assertEqual(r[5].score,D(0))
        # A single current value 10 gives different CVs as preceding values change.
        self.assertNotEqual(r[3].score,r[5].score)

    def test_sign_not_changed_to_absolute_mean(self):
        self.assertAlmostEqual(float(rolling([-1,-3],2)[-1].score),-(2**0.5)/2,places=14)

    def test_invalid_lookback(self):
        for value in [None,True,False,0,1,-1,2.0,'2']:
            with self.subTest(value=value),self.assertRaises(ContractError):cov_spec(lookback=value)

    def test_population_ddof_not_supported_and_baseline_not_forced(self):
        spec=cov_spec(lookback=2)
        with self.assertRaises(ContractError):CoV().start_run(None,dict(spec.config,ddof=0))
        with self.assertRaises(ContractError):CoV().start_run(zparams([1,2,3]),spec.config)

    def test_new_run_resets_and_direct_discontinuity_refused(self):
        detector=CoV();config=cov_spec(lookback=2).config
        a=detector.start_run(None,config);b=detector.start_run(None,config)
        obs=observations([2,4,6])
        detector.update(obs[0],a);self.assertIsNotNone(detector.update(obs[1],a).score)
        self.assertIsNone(detector.update(obs[0],b).score)
        with self.assertRaises(ContractError):detector.update(obs[2],b)

    def test_general_sequence_matches_independent_stdev(self):
        values=[0,4,1,8,2,7,9,3]
        for lookback in [2,3,5]:
            actual=rolling(values,lookback)
            for i in range(lookback-1,len(values)):
                v=values[i-lookback+1:i+1]
                self.assertAlmostEqual(float(actual[i].score),statistics.stdev(v)/statistics.mean(v),places=13)

    def test_decimal_context_and_determinism(self):
        expected=rolling([1,3,7,2,9],3)
        with localcontext() as ctx:
            ctx.prec=4;ctx.rounding=ROUND_UP
            actual=rolling([1,3,7,2,9],3)
        self.assertEqual(expected,actual)


class ScoreArtifactTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.DetectionFrameworkTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root

    def load(self,root,role):
        m=json.loads((root/'feature_manifest.json').read_text())
        return load_series(root,run_id=m['source_run_id'],family='service',feature='mean_duration_ms',
                           window_size_seconds='1',feature_schema_version=1,role=role)

    def test_real_methods_fit_score_without_labels_and_read_only(self):
        baseline=self.fixture.fixture('normal','normal',[1,None,2,3])
        target=self.fixture.fixture('target','target',[1,2,None,3,4,5])
        paths=[p for root in [baseline,target] for p in root.rglob('*') if p.is_file()]
        before={str(p):(digest(p),p.stat().st_mtime_ns) for p in paths}
        original=Path.open
        def guard(path,*args,**kwargs):
            if path.name=='labels.csv':raise AssertionError('Detector attempted labels IO')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',guard):
            model=fit_baseline([self.load(baseline,'baseline')],ZScore(),zscore_spec(),self.root/'model-real')
            source=self.load(target,'test')
            z=score_run(source,ZScore(),zscore_spec(),self.root/'z',baseline=model)
            cv=score_run(source,CoV(),cov_spec(lookback=2),self.root/'cv')
            z2=score_run(source,ZScore(),zscore_spec(),self.root/'z2',baseline=model)
            cv2=score_run(source,CoV(),cov_spec(lookback=2),self.root/'cv2')
        self.assertEqual(before,{str(p):(digest(p),p.stat().st_mtime_ns) for p in paths})
        self.assertEqual((z.artifact.root/'scores.csv').read_bytes(),(z2.artifact.root/'scores.csv').read_bytes())
        self.assertEqual((cv.artifact.root/'manifest.json').read_bytes(),(cv2.artifact.root/'manifest.json').read_bytes())
        self.assertEqual((z.artifact.root/'manifest.json').read_bytes(),(z2.artifact.root/'manifest.json').read_bytes())
        for run in [z,cv]:
            self.assertEqual(run.records,load_scores(run.artifact.reference).records)
            self.assertTrue(all(r.available_at_seconds==r.window_end_seconds for r in run.records))
            self.assertFalse((run.artifact.root/'decisions.csv').exists())
        p=open_artifact(model.reference,'baseline').read()
        self.assertEqual((p['parameters']['mu'],p['parameters']['sigma'],p['parameters']['n_valid']),('2','1',3))
        self.assertEqual(p['feature']['feature'],'mean_duration_ms')
        self.assertEqual(p['sources'][0]['feature_manifest_sha256'],digest(baseline/'feature_manifest.json'))
        self.assertEqual(z.artifact.read()['baseline'],model.reference)
        self.assertIsNone(cv.artifact.read()['baseline'])
        self.assertEqual(cv.artifact.read()['component']['config']['lookback'],2)

    def test_failed_degenerate_fit_publishes_no_artifact(self):
        baseline=self.fixture.fixture('constant','constant',[3,3,3])
        with self.assertRaisesRegex(ContractError,'zero_baseline_sigma'):
            fit_baseline([self.load(baseline,'baseline')],ZScore(),zscore_spec(),self.root/'bad-model')
        self.assertFalse((self.root/'bad-model').exists())

    def test_no_future_access_in_rolling_prefix(self):
        one=self.fixture.fixture('prefix','prefix',[2,4,6])
        two=self.fixture.fixture('extension','extension',[2,4,6,1000,0,1])
        a=score_run(self.load(one,'development'),CoV(),cov_spec(lookback=3),self.root/'prefix-scores')
        b=score_run(self.load(two,'development'),CoV(),cov_spec(lookback=3),self.root/'extension-scores')
        self.assertEqual([r.score for r in a.records],[r.score for r in b.records[:3]])


if __name__=='__main__':unittest.main()
