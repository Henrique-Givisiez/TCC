"""Explicit synthetic thresholds only. No Docker/calibration/scientific TEST runs."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal as D, localcontext
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from analysis.detection.artifacts import component, encoded, publish
from analysis.detection.contracts import Observation, ObservedSeries
from analysis.detection.cusum_freeze_run import (load_development_run, process_development_run,
    process_series, transition_rows, validate_run)
from analysis.detection.detectors.cusum import CUSUM, cusum_spec
from analysis.detection.detectors.cusum_freeze import CUSUMFreeze, freeze_spec
from analysis.detection.detectors.zscore import ZScore, zscore_spec
from analysis.detection.inputs import ContractError
from analysis.detection.pipeline import feature_key, validate_score_run
from tests.test_ewma_cusum import frozen_parameters, observations
from tests import test_detection_framework as fixtures


def series(values):
    return ObservedSeries('synthetic', 'service', 'request_starts', D(1), 1, observations(values))


def run(values, h='2'):
    return process_series(series(values), h=h, baseline_parameters=frozen_parameters())


class FreezeTests(unittest.TestCase):
    def test_numeric_sequence_candidate_is_published_not_stored_state(self):
        result = run([12, 14, 14, 14, 10, 8, None, 12])
        rows = transition_rows(result)
        self.assertEqual([r['candidate'] for r in rows], [D('.5'), D(2), D('3.5'), D('3.5'), D('1.5'), D(0), None, D('.5')])
        self.assertEqual([r['posterior_state'] for r in rows], [D('.5'), D(2), D(2), D(2), D('1.5'), D(0), D(0), D('.5')])
        self.assertEqual([r['decision'] for r in rows], [False, False, True, True, False, False, None, False])
        self.assertEqual([r['update_accepted'] for r in rows], [True, True, False, False, True, True, None, True])
        self.assertTrue(all(t.score.score == t.candidate and t.decision.score == t.score for t in result.transitions))
        for t in result.transitions:
            self.assertEqual(t.next_state.last_index, t.observation.window_index)
            self.assertEqual(t.next_state.last_end, t.observation.window_end_seconds)

    def test_missing_resets_nonzero_and_does_not_create_negative_decision(self):
        result = run([14, None, None, 12])
        missing = result.transitions[1]
        self.assertEqual(missing.previous_state, D('1.5'))
        self.assertEqual(missing.posterior_state, D(0))
        self.assertFalse(missing.score.score_available)
        self.assertIsNone(missing.decision.decision)
        self.assertIsNone(missing.update_accepted)
        self.assertEqual(missing.decision.reason, 'missing_observation_reset')
        self.assertEqual(result.transitions[-1].candidate, D('.5'))

    def test_zero_threshold_accepts_zero_and_freezes_every_positive_candidate(self):
        result = run([12, 14, 10, 8, None], h=0)
        self.assertEqual([d.decision for d in result.decisions], [True, True, False, False, None])
        self.assertEqual([t.posterior_state for t in result.transitions], [D(0)] * 5)

    def test_explicit_finite_nonnegative_threshold_and_canonical_identity(self):
        for h in ('-1', 'NaN', 'Infinity', '-Infinity', 0.1, True, None):
            with self.subTest(h=h), self.assertRaises(ContractError):
                CUSUMFreeze(h=h)
        self.assertEqual(component(freeze_spec(h='2.00')), component(freeze_spec(h=D('2e0'))))
        self.assertNotEqual(component(freeze_spec(h='2')), component(cusum_spec()))
        detector = CUSUMFreeze(h=2)
        with self.assertRaises(FrozenInstanceError):
            detector.h = D(3)
        with self.assertRaises(TypeError):
            detector.spec().config['h'] = '3'

    def test_changing_h_changes_trajectory_and_requires_reprocessing(self):
        small = run([14, 14, 10], h=2)
        large = run([14, 14, 10], h=4)
        self.assertEqual([t.posterior_state for t in small.transitions], [D('1.5'), D('1.5'), D(1)])
        self.assertEqual([t.posterior_state for t in large.transitions], [D('1.5'), D(3), D('2.5')])
        with self.assertRaises(ContractError):
            validate_run(replace(small, specification_json=large.specification_json))
        bad_decision = replace(small.transitions[1].decision, decision=False)
        bad = replace(small.transitions[1], decision=bad_decision)
        with self.assertRaises(ContractError):
            validate_run(replace(small, transitions=(small.transitions[0], bad, small.transitions[2])))
        with self.assertRaisesRegex(ContractError, 'same h'):
            CUSUMFreeze(h=4).step(series([14, 14]).observations[1], small.transitions[0].next_state)
        with self.assertRaises(ContractError):
            validate_score_run(small)  # cannot feed coupled run to generic decide

    def test_contiguity_and_metadata_after_freeze_and_missing(self):
        detector = CUSUMFreeze(h=0)
        initial = detector.start_run(frozen_parameters())
        first = detector.step(observations([14])[0], initial)
        for bad in (observations([14])[0], observations([14, 14, 14])[2],
                    replace(observations([14, 14])[1], run_id='other'),
                    replace(observations([14, 14])[1], window_start_seconds=D('1.5'))):
            with self.subTest(bad=bad), self.assertRaises(ContractError):
                detector.step(bad, first.next_state)
        missing = detector.step(observations([14, None])[1], first.next_state)
        self.assertEqual((missing.next_state.last_index, missing.next_state.last_end), (1, D(2)))
        self.assertTrue(detector.step(observations([14, None, 14])[2], missing.next_state).decision.decision)
        with self.assertRaises(ContractError):
            detector.step(observations([14, 14])[1], initial)

    def test_prefix_causality_baseline_unchanged_and_precision(self):
        values = [12, 14, 14, None, 10, 18]
        full = run(values)
        for n in range(len(values) + 1):
            self.assertEqual(run(values[:n]).transitions, full.transitions[:n])
        with localcontext() as ctx:
            ctx.prec = 3
            self.assertEqual(run(values), full)
        parameters = frozen_parameters()
        snapshot = deepcopy(parameters)
        with patch.object(ZScore, 'fit', side_effect=AssertionError('No fitting')):
            process_series(series(values), h=2, baseline_parameters=parameters)
        self.assertEqual(parameters, snapshot)
        self.assertEqual(set(Observation.__dataclass_fields__),
            {'run_id', 'window_index', 'window_start_seconds', 'window_end_seconds', 'value'})

    def test_legacy_v1_keeps_accumulating_and_component_unchanged(self):
        detector = CUSUM(); state = detector.start_run(frozen_parameters(), cusum_spec().config)
        scores = [detector.update(o, state).score for o in observations([12, 14, 14, 14, 10])]
        self.assertEqual(scores, [D('.5'), D(2), D('3.5'), D(5), D('4.5')])
        self.assertEqual((cusum_spec().name, cusum_spec().version), ('cusum', '1'))
        self.assertNotIn('h', cusum_spec().config)

    def test_positive_candidate_reaches_evaluator_and_is_true_positive(self):
        result = run([18], h=1)  # z=4, candidate=3.5, stored state=0
        self.assertEqual(result.transitions[0].posterior_state, D(0))
        self.assertGreater(result.transitions[0].score.score, D(1))
        # Only evaluation imports/constructs labels; detector accepts Observation only.
        from analysis.detection.evaluation import EvaluationPlan, WindowTruth
        from analysis.detection.evaluation.cusum_freeze import evaluate_synthetic
        labels = (WindowTruth('synthetic', 0, D(0), D(1), D(1), D(1)),)

        class PureEvaluator:
            def evaluate(self, inputs, plan):
                self.inputs = inputs
                return dict(TP=sum(d.decision is True and t.attack_event_overlap_fraction == 1
                                   for d, t in zip(inputs.decisions, inputs.labels)))

        evaluator = PureEvaluator()
        plan = EvaluationPlan('pure_windows', {}, 'at_window_closure')
        self.assertEqual(evaluate_synthetic(result, labels, evaluator, plan), {'TP': 1})
        self.assertIs(evaluator.inputs.decisions[0], result.decisions[0])
        self.assertIsNone(evaluator.inputs.events)
        with self.assertRaises(ContractError):
            evaluate_synthetic(result, (replace(labels[0], run_id='other'),), evaluator, plan)


class FreezeArtifactTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DetectionFrameworkTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        normal = self.fixture.fixture('normal-freeze', 'normal-freeze', [8, 10, 12])
        self.target = self.fixture.fixture('target-freeze', 'target-freeze', [12, 14, 14, None, 10])
        self.source = self.fixture.load(self.target)
        source = self.fixture.load(normal, 'baseline')
        self.model = publish(self.root / 'freeze-model', 'baseline', dict(
            component=component(zscore_spec()), feature=feature_key(source.series),
            sources=[source.reference], parameters=frozen_parameters(), fixture='synthetic manual moments'))

    def test_artifact_roundtrip_no_labels_io_and_same_h_for_every_record(self):
        original = Path.open

        def no_labels(path, *args, **kwargs):
            if path.name in ('labels.csv', 'attack_events.csv'):
                raise AssertionError('Detector/processor cannot access ground truth')
            return original(path, *args, **kwargs)

        with patch.object(Path, 'open', no_labels), patch.object(ZScore, 'fit', side_effect=AssertionError('No fit')):
            result, artifact = process_development_run(self.source, baseline=self.model, h='2', destination=self.root / 'coupled')
            self.assertEqual(load_development_run(artifact), result)
        manifest = artifact.read('cusum-freeze-run')
        self.assertEqual(manifest['component']['config']['h'], '2')
        self.assertEqual(manifest['transitions'][2]['candidate'], '3.5')
        self.assertTrue(manifest['transitions'][2]['decision'])
        self.assertEqual(manifest['transitions'][2]['posterior_state'], '2.0')
        with self.assertRaises(ContractError):
            process_development_run(self.source, baseline=self.model, h=2, destination=artifact.root)
        path = artifact.root / 'manifest.json'
        path.write_text(path.read_text().replace('3.5', '0.0'))
        with self.assertRaises(ContractError):
            load_development_run(artifact)

    def test_calibration_test_and_campaign_blocked_before_source_or_model_read(self):
        for role in ('test', 'calibration', 'baseline'):
            source = replace(self.source, role=role)
            with self.subTest(role=role), patch.object(type(self.model), 'read', side_effect=AssertionError('Early read')):
                with self.assertRaises(ContractError):
                    process_development_run(source, baseline=self.model, h=2, destination=self.root / role)
        reference = self.source.reference
        reference['campaign'] = {'partition': 'development'}
        with self.assertRaises(ContractError):
            process_development_run(replace(self.source, reference_json=json.dumps(reference)),
                                    baseline=self.model, h=2, destination=self.root / 'campaign')

    def test_wrong_baseline_feature_rejected(self):
        wrong = self.fixture.load(self.target, family='infrastructure', feature='mean_cpu_percent')
        with self.assertRaises(ContractError):
            process_development_run(wrong, baseline=self.model, h=2, destination=self.root / 'wrong')


if __name__ == '__main__':
    unittest.main()
