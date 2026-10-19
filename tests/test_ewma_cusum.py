"""Synthetic/DEVELOPMENT only: no scientific CALIBRATION or TEST data access."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal as D, localcontext, ROUND_UP
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from analysis.detection import score_run, load_scores, calibrate, decide
from analysis.detection.artifacts import component, publish
from analysis.detection.contracts import Observation
from analysis.detection.detectors.ewma import EWMA, ewma_spec, LAMBDA
from analysis.detection.detectors.cusum import CUSUM, cusum_spec, K
from analysis.detection.detectors.zscore import ZScore, zscore_spec
from analysis.detection.empirical import EmpiricalUpperTail, StrictUpperTail, upper_tail_spec
from analysis.detection.inputs import ContractError
from analysis.detection.pipeline import feature_key
from tests import test_detection_framework as fixtures


FEATURES = [('network', 'ingress_packet_count'),
            ('network', 'ingress_tcp_payload_length_sum_bytes'),
            ('service', 'request_starts'), ('service', 'mean_duration_ms'),
            ('infrastructure', 'mean_cpu_percent')]
METHODS = [(EWMA, ewma_spec), (CUSUM, cusum_spec)]


def frozen_parameters():
    # A frozen synthetic fixture for baseline [8,10,12]: mu=10, sample sigma=2.
    # No test needs to invoke any fitter to create or consume these parameters.
    return dict(mu='10', sigma='2', mean_exact=dict(numerator='10', denominator='1'),
                variance_exact=dict(numerator='4', denominator='1'), n_valid=3,
                n_missing=0, support_by_run=[dict(run_id='normal', n_valid=3, n_missing=0)],
                ddof=1, config=dict(zscore_spec().config))


def observations(values, run_id='synthetic'):
    return tuple(Observation(run_id, i, D(i), D(i+1), None if v is None else D(str(v)))
                 for i, v in enumerate(values))


def scored(method, spec, values, parameters=None):
    detector=method();state=detector.start_run(parameters or frozen_parameters(), spec().config)
    return tuple(detector.update(o, state) for o in observations(values))


class EWMATests(unittest.TestCase):
    def test_manual_sequence_exact_lambda_zero_initialization(self):
        self.assertEqual(LAMBDA, D('0.2'))
        self.assertEqual(ewma_spec().config['lambda'], '0.2')
        self.assertEqual([x.score for x in scored(EWMA, ewma_spec, [12,14,8,10])],
                         [D('.2'),D('.56'),D('.248'),D('.1984')])

    def test_signed_upper_tail_no_absolute_or_clipping(self):
        self.assertEqual(ewma_spec().config['direction'], 'upper-tail')
        self.assertEqual(scored(EWMA,ewma_spec,[8])[0].score,D('-.2'))
        self.assertGreater(scored(EWMA,ewma_spec,[12])[0].score,D(0))

    def test_null_is_unavailable_and_resets(self):
        out=scored(EWMA,ewma_spec,[None,14,None,None,12,12])
        self.assertEqual([x.score for x in out],[None,D('.4'),None,None,D('.2'),D('.36')])
        for i in [0,2,3]:self.assertEqual(out[i].reason,'missing_observation_reset')
        self.assertIsNone(out[4].reason)

    def test_no_lambda_variants_or_noncanonical_float(self):
        for value in ['0','1','0.1','0.3',0.2,None,True,D('.2')]:
            with self.subTest(value=value),self.assertRaises(ContractError):
                EWMA().start_run(frozen_parameters(),dict(ewma_spec().config,**{'lambda':value}))


class CUSUMTests(unittest.TestCase):
    def test_manual_formula_exact_k_and_zero_initialization(self):
        self.assertEqual(K,D('0.5'));self.assertEqual(cusum_spec().config['k'],'0.5')
        self.assertEqual([x.score for x in scored(CUSUM,cusum_spec,[12,14,10,8,12])],
                         [D('.5'),D('2'),D('1.5'),D(0),D('.5')])

    def test_insufficient_evidence_naturally_resets_to_zero(self):
        self.assertEqual(cusum_spec().config['direction'],'upper-tail')
        self.assertEqual([x.score for x in scored(CUSUM,cusum_spec,[8,10,11,12,8,10])],
                         [D(0),D(0),D(0),D('.5'),D(0),D(0)])

    def test_null_is_unavailable_and_resets(self):
        out=scored(CUSUM,cusum_spec,[None,14,None,None,12,12])
        self.assertEqual([x.score for x in out],[None,D('1.5'),None,None,D('.5'),D('1')])
        for i in [0,2,3]:self.assertEqual(out[i].reason,'missing_observation_reset')

    def test_no_k_variants_or_noncanonical_float(self):
        for value in ['0','-1','0.25','1',0.5,None,True,D('.5')]:
            with self.subTest(value=value),self.assertRaises(ContractError):
                CUSUM().start_run(frozen_parameters(),dict(cusum_spec().config,k=value))


class StandardizedContractTests(unittest.TestCase):
    def test_prefix_causality_and_no_decision_or_truth_in_callbacks(self):
        for method,spec in METHODS:
            with self.subTest(method=method):
                prefix=scored(method,spec,[12,14,None,8])
                extension=scored(method,spec,[12,14,None,8,1000000,0])
                self.assertEqual(prefix,extension[:4])
                self.assertTrue(all(not hasattr(x,'decision') for x in prefix))
                self.assertEqual(set(Observation.__dataclass_fields__),
                                 {'run_id','window_index','window_start_seconds','window_end_seconds','value'})

    def test_parameters_used_without_refitting_or_mutation(self):
        for method,spec in METHODS:
            params=frozen_parameters();before=deepcopy(params)
            # Changing the frozen mu to 20 changes z, rather than learning from x.
            params['mu']='20';params['mean_exact']['numerator']='20'
            with patch.object(ZScore,'fit',side_effect=AssertionError('Refitting forbidden')):
                actual=scored(method,spec,[22],params)[0].score
            self.assertEqual(actual,D('.2') if method is EWMA else D('.5'))
            self.assertEqual(params['mu'],'20');self.assertEqual(params['sigma'],before['sigma'])
            self.assertEqual(params['variance_exact'],before['variance_exact'])
            params2=frozen_parameters();snapshot=deepcopy(params2)
            scored(method,spec,[12,14,None,8],params2)
            self.assertEqual(params2,snapshot)
            self.assertFalse(hasattr(method(),'fit'))

    def test_frozen_sigma_is_used(self):
        for method,spec in METHODS:
            p=frozen_parameters();p.update(sigma='4',variance_exact={'numerator':'16','denominator':'1'})
            actual=scored(method,spec,[14],p)[0].score
            self.assertEqual(actual,D('.2') if method is EWMA else D('.5'))

    def test_missing_or_invalid_baseline_rejected(self):
        for method,spec in METHODS:
            with self.subTest(method=method),self.assertRaises(ContractError):
                method().start_run(None,spec().config)
            for change in [dict(mu='11'),dict(sigma='0'),dict(sigma='3'),dict(ddof=0)]:
                with self.subTest(method=method,change=change),self.assertRaises(ContractError):
                    method().start_run(dict(frozen_parameters(),**change),spec().config)

    def test_invalid_common_configuration_rejected(self):
        for method,spec in METHODS:
            for change in [dict(direction='lower-tail'),dict(initial_state='1'),
                           dict(missing_policy='carry'),dict(normalization='calibration'),
                           dict(decimal_precision=28),dict(extra=True)]:
                with self.subTest(method=method,change=change),self.assertRaises(ContractError):
                    method().start_run(frozen_parameters(),dict(spec().config,**change))

    def test_direct_state_cannot_cross_runs_reorder_or_skip_unknown_windows(self):
        for method,spec in METHODS:
            first=observations([12,14,16])
            for bad in [first[0],first[2],replace(first[1],run_id='other'),
                        replace(first[1],window_start_seconds=D('1.5'))]:
                detector=method();state=detector.start_run(frozen_parameters(),spec().config)
                detector.update(first[0],state)
                with self.subTest(method=method,bad=bad),self.assertRaisesRegex(ContractError,'consecutive'):
                    detector.update(bad,state)

    def test_new_state_and_decimal_context_determinism(self):
        values=[12,14,8,None,16,10,12]
        for method,spec in METHODS:
            expected=scored(method,spec,values)
            with localcontext() as ctx:
                ctx.prec=3;ctx.rounding=ROUND_UP
                actual=scored(method,spec,values)
            self.assertEqual(expected,actual)
            self.assertEqual(expected,scored(method,spec,values))


class StandardizedArtifactTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.DetectionFrameworkTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups);self.root=self.fixture.root
        self.baseline=self.fixture.fixture('normal','normal',[8,10,12])
        self.target=self.fixture.fixture('target','target',[12,14,None,8,12])

    def model(self,family,feature,component_spec=None):
        source=self.fixture.load(self.baseline,'baseline',family=family,feature=feature)
        return publish(self.root/('model-'+feature),'baseline',dict(
            component=component(component_spec or zscore_spec()),feature=feature_key(source.series),
            sources=[source.reference],parameters=frozen_parameters(),
            fixture='Frozen synthetic baseline; manual parameters, no fitter'))

    def guard(self,path,*args,**kwargs):
        if path.name in ('labels.csv','attack_events.csv'):
            raise AssertionError('Ground truth access forbidden')
        return self.original_open(path,*args,**kwargs)

    def test_all_five_features_reuse_zscore_artifact_no_labels_or_fitting(self):
        self.original_open=Path.open
        with patch.object(Path,'open',lambda p,*a,**kw:self.guard(p,*a,**kw)),patch.object(ZScore,'fit',side_effect=AssertionError('Refitting')):
            for family,feature in FEATURES:
                model=self.model(family,feature);before=(model.root/'manifest.json').read_bytes()
                source=self.fixture.load(self.target,'development',family=family,feature=feature)
                for method,spec in METHODS:
                    destination=self.root/(spec().name+'-'+feature)
                    run=score_run(source,method(),spec(),destination,baseline=model)
                    again=score_run(source,method(),spec(),self.root/(spec().name+'-repeat-'+feature),baseline=model)
                    self.assertEqual(run.records,again.records)
                    self.assertEqual((run.artifact.root/'manifest.json').read_bytes(),(again.artifact.root/'manifest.json').read_bytes())
                    self.assertEqual(run.records,load_scores(run.artifact.reference).records)
                    m=run.artifact.read('scores')
                    self.assertEqual(m['baseline'],model.reference)
                    self.assertEqual(m['parameters'],json.loads(before)['parameters'])
                    self.assertEqual(m['baseline_sources'],model.read()['sources'])
                    self.assertEqual(m['component']['name'],spec().name)
                    self.assertNotIn('labels.csv',json.dumps(m))
                    self.assertTrue(all(r.available_at_seconds==r.window_end_seconds for r in run.records))
                    self.assertFalse((destination/'decisions.csv').exists())
                self.assertEqual(before,(model.root/'manifest.json').read_bytes())

    def test_synthetic_pipeline_keeps_calibration_and_decisions_separate(self):
        # Designated calibration role on synthetic fixtures only; no campaign IO.
        model=self.model('service','mean_duration_ms')
        source=self.fixture.load(self.target,'calibration',feature='mean_duration_ms')
        self.original_open=Path.open
        with patch.object(Path,'open',lambda p,*a,**kw:self.guard(p,*a,**kw)),patch.object(ZScore,'fit',side_effect=AssertionError('Refitting')):
            for method,spec in METHODS:
                scores=score_run(source,method(),spec(),self.root/(spec().name+'-scores'),baseline=model)
                pspec=upper_tail_spec(alpha='0.01')
                threshold=calibrate([scores],EmpiricalUpperTail(),pspec,self.root/(spec().name+'-policy'))
                decisions=decide(scores,StrictUpperTail(),pspec,threshold,self.root/(spec().name+'-decisions'))
                self.assertIsNone(scores.records[2].score)
                self.assertIsNone(decisions.records[2].decision)
                self.assertEqual(threshold.read()['baseline'],model.reference)

    def test_baseline_feature_and_component_mismatches_rejected(self):
        wrong_model=self.model('service','mean_duration_ms',ewma_spec())
        source=self.fixture.load(self.target,'development',feature='mean_duration_ms')
        for method,spec in METHODS:
            with self.subTest(method=method),self.assertRaisesRegex(ContractError,'Baseline detector'):
                score_run(source,method(),spec(),self.root/'bad',baseline=wrong_model)
        model=self.model('service','request_starts')
        for method,spec in METHODS:
            with self.subTest(method=method),self.assertRaisesRegex(ContractError,'Baseline detector'):
                score_run(source,method(),spec(),self.root/'bad',baseline=model)

    def test_component_identity_and_feature_scope_rejected_before_publish(self):
        source=self.fixture.load(self.target,'development',feature='mean_duration_ms')
        model=self.model('service','mean_duration_ms')
        for method,spec in METHODS:
            for bad in [replace(spec(),version='2'),replace(spec(),name='other'),replace(spec(),missing='reject')]:
                with self.subTest(method=method,bad=bad),self.assertRaises(ContractError):
                    score_run(source,method(),bad,self.root/'bad',baseline=model)
            unsupported=self.fixture.load(self.target,'development',family='infrastructure',feature='mean_memory_mib')
            with self.subTest(method=method),self.assertRaisesRegex(ContractError,'five frozen features'):
                score_run(unsupported,method(),spec(),self.root/'bad',baseline=model)
        self.assertFalse((self.root/'bad').exists())

    def test_test_partition_still_locked_before_any_dataset_read(self):
        for method,spec in METHODS:
            with patch.object(Path,'open',side_effect=AssertionError('Dataset IO')):
                from analysis.detection.protocol import load_campaign_series
                with self.assertRaisesRegex(ContractError,'TEST locked'):
                    load_campaign_series(self.root/'absent',protocol_reference={},partition='test',seed=0,scenario='B')
        # The pipeline also refuses an alias explicitly reclassified as TEST.
        source=self.fixture.load(self.target,'development',feature='mean_duration_ms')
        reference=source.reference;reference['role']='test'
        alias=replace(source,role='test',reference_json=json.dumps(reference))
        for method,spec in METHODS:
            with self.assertRaisesRegex(ContractError,'TEST locked'):
                score_run(alias,method(),spec(),self.root/'bad')


if __name__=='__main__':unittest.main()
