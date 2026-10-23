"""Hand-checked synthetic sequences only; never reads scientific TEST artifacts."""
from decimal import Decimal as D
import unittest

from analysis.detection.contracts import Observation, PolicyScore
from analysis.detection.detectors.cusum import CUSUM, K, cusum_spec
from analysis.detection.empirical import StrictUpperTail, upper_tail_spec
from analysis.detection.inputs import ContractError
from tests.test_ewma_cusum import frozen_parameters


def observation(i, value, run='synthetic'):
    return Observation(run, i, D(i), D(i+1), None if value is None else D(str(value)))


def scores(values):
    detector = CUSUM()
    state = detector.start_run(frozen_parameters(), cusum_spec().config)
    return [detector.update(observation(i,v), state).score for i,v in enumerate(values)]


def synthetic_threshold():
    config = upper_tail_spec(alpha='0.01').config
    parameters = dict(policy_version='1', config=dict(config), n_valid=3,
                      quantile_index_zero_based=2, scores_below=2, scores_equal=1,
                      scores_above=0, threshold='2')
    return config, parameters


class CUSUMPersistenceAuditTests(unittest.TestCase):
    def test_at_exact_baseline_mean_no_accumulation(self):
        self.assertEqual(K,D('.5'))
        self.assertEqual(scores([10]*8), [D(0)]*8)

    def test_sustained_increase_then_exact_return_loses_half_per_window(self):
        # mu=10,sigma=2. x=14 gives z=2 and increment=1.5; x=10 gives -.5.
        actual = scores([14]*3 + [10]*9)
        expected = list(map(D,['1.5','3','4.5','4','3.5','3','2.5','2','1.5','1','.5','0']))
        self.assertEqual(actual,expected)
        # h=2: strict equality is not an alarm; 5 baseline observations to turn off.
        self.assertEqual([s>D(2) for s in actual[3:]], [True]*4+[False]*5)

    def test_gradual_recovery_can_still_increase_or_hold_score(self):
        # Recovery z:1.5,1,.5,0,-.5,0,...; increments:1,.5,0,-.5,-1,-.5,...
        actual = scores([14,14,13,12,11,10,9,10,10,10,10,10,10])
        expected = list(map(D,['1.5','3','4','4.5','4.5','4','3','2.5','2','1.5','1','.5','0']))
        self.assertEqual(actual,expected)

    def test_missing_is_unavailable_and_resets_not_baseline_imputation(self):
        self.assertEqual(scores([14,None,10,14]),[D('1.5'),None,D(0),D('1.5')])
        detector=CUSUM(); state=detector.start_run(frozen_parameters(),cusum_spec().config)
        detector.update(observation(0,14),state)
        missing=detector.update(observation(1,None),state)
        self.assertEqual(missing.reason,'missing_observation_reset')
        self.assertEqual(state.value,D(0))

    def test_runs_cannot_share_dynamic_state_and_new_run_starts_zero(self):
        detector=CUSUM();state=detector.start_run(frozen_parameters(),cusum_spec().config)
        self.assertEqual(detector.update(observation(0,14),state).score,D('1.5'))
        with self.assertRaisesRegex(ContractError,'consecutive'):
            detector.update(observation(1,14,'another'),state)
        fresh=detector.start_run(frozen_parameters(),cusum_spec().config)
        self.assertEqual(detector.update(observation(0,10,'another'),fresh).score,D(0))
        self.assertEqual(state.value,D('1.5'))

    def test_zero_sigma_rejected_and_tiny_positive_sigma_has_no_floor(self):
        invalid=frozen_parameters();invalid.update(sigma='0',variance_exact=dict(numerator='0',denominator='1'))
        with self.assertRaisesRegex(ContractError,'sigma'):
            CUSUM().start_run(invalid,cusum_spec().config)
        tiny=frozen_parameters();tiny.update(sigma='0.000000000001',
                    variance_exact=dict(numerator='1',denominator=str(10**24)))
        detector=CUSUM();state=detector.start_run(tiny,cusum_spec().config)
        self.assertEqual(detector.update(observation(0,11),state).score,D('999999999999.5'))

    def test_score_alarm_are_separate_and_alarm_does_not_reset_score(self):
        detector=CUSUM();state=detector.start_run(frozen_parameters(),cusum_spec().config)
        policy=StrictUpperTail();config,params=synthetic_threshold();threshold=policy.start_run(params,config)
        observed=[]
        for i,value in enumerate([14,14,14,10,10,10,10,10,None]):
            score=detector.update(observation(i,value),state)
            self.assertFalse(hasattr(score,'decision'))
            record=PolicyScore('synthetic',i,D(i),D(i+1),score.score,score.score is not None,score.reason,D(i+1))
            before=state.value
            alarm=policy.decide(record,threshold)
            self.assertEqual(state.value,before)  # policy cannot mutate the CUSUM accumulator
            observed.append((score.score,alarm.decision))
        self.assertEqual(observed[:3],[(D('1.5'),False),(D('3'),True),(D('4.5'),True)])
        self.assertEqual(observed[-2:],[(D('2'),False),(None,None)])
        # A positive window is not itself an event-level classification; GT is absent here.
        self.assertFalse(hasattr(policy,'event_detected'))

    def test_persistent_window_alarms_are_not_new_event_detections(self):
        # Invoke only the evaluator's pure arithmetic on SYNTHETIC decisions.
        # No source loader, manifest, TEST series or evaluation pipeline is used.
        from fractions import Fraction as F
        from experiments.stage15b_evaluation import FrozenDecision, FrozenEvent, event_metrics
        signal=scores([10]*48+[14]*3+[10]*93)
        decisions=tuple(FrozenDecision(i,F(i),F(i+1),F(i+1),v>D(2)) for i,v in enumerate(signal))
        event=FrozenEvent('synthetic-event',F(48),F(51),'continuous')
        result=event_metrics(decisions,event)
        self.assertTrue(result['event_detected'])
        self.assertEqual(result['detection_time'],F(50))
        self.assertEqual(result['detection_delay_seconds'],F(2))
        self.assertEqual(sum(d.value is True for d in decisions if d.start>=event.end),4)
        # An alarm whose whole window is after the event does not detect that event.
        post_only=tuple(FrozenDecision(i,F(i),F(i+1),F(i+1),i==51) for i in range(144))
        self.assertFalse(event_metrics(post_only,event)['event_detected'])


if __name__=='__main__':
    unittest.main()
