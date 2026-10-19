"""Synthetic DEVELOPMENT/metadata fixtures only; no real TEST data or preflights."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal as D
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

from analysis.detection.contracts import DecisionRecord, PolicyScore
from analysis.detection.horizons import (EvaluationSelection, select_evaluation_records,
                                        select_for_evaluation, select_campaign_records)
from analysis.detection.evaluation import (EvaluationPlan, WindowTruth, pure_window_groups,
                                          evaluate)
from analysis.detection.evaluation.events import EventTruth, VerifiedEvents, evaluate_events
from analysis.detection.protocol import EVENT_POLICY_V2
from analysis.detection.inputs import ContractError
from analysis.detection.pipeline import DecisionRun
from experiments import stage14_scientific as runner
from tests import test_stage14a1 as metadata_fixtures
from tests import test_detection_framework as framework
from tests import test_ewma_cusum as methods


def scores():
    return tuple(PolicyScore('development',i,D(i),D(i+1),D(i),True,None,D(i+1)) for i in range(145))


class EvaluationSelectionTests(unittest.TestCase):
    def test_primary_and_startup_preserve_original_records_and_timestamps(self):
        original=scores()
        for region,indices in [('primary',range(48,144)),('startup_diagnostic',range(48))]:
            selected,meta=select_evaluation_records(original,EvaluationSelection(region))
            self.assertEqual([r.window_index for r in selected],list(indices))
            self.assertTrue(all(r is original[r.window_index] for r in selected))
            self.assertEqual(meta['observation_scoring_horizon'],['0','144'])
            self.assertEqual(meta['purpose'],'evaluation_only')
        self.assertEqual(len(original),145)

    def test_full_window_containment_excludes_crossing_edges(self):
        bounds=[('47.5','48.5'),('48','49'),('143','144'),('143.5','144.5'),('0','1'),('47','48')]
        rows=tuple(PolicyScore('development',i,D(a),D(b),D(1),True,None,D(b)) for i,(a,b) in enumerate(bounds))
        self.assertEqual([x.window_index for x in select_evaluation_records(rows,EvaluationSelection('primary'))[0]],[1,2])
        self.assertEqual([x.window_index for x in select_evaluation_records(rows,EvaluationSelection('startup_diagnostic'))[0]],[4,5])

    def test_unavailable_is_not_imputed_or_dropped(self):
        rows=list(scores());rows[60]=replace(rows[60],score=None,score_available=False,reason='missing')
        selected,_=select_evaluation_records(rows,EvaluationSelection('primary'))
        self.assertEqual(len(selected),96);self.assertIsNone(selected[12].score)

    def test_invalid_selection_and_unknown_regions_rejected(self):
        for invalid in [None,{},'primary',EvaluationSelection('other')]:
            with self.subTest(selection=invalid),self.assertRaises(ContractError):select_evaluation_records(scores(),invalid)
        with self.assertRaises(ContractError):
            EvaluationPlan('pure_windows_only',{},'closure',selection='primary').validate()

    def test_scoring_campaign_horizon_unchanged(self):
        f=metadata_fixtures.RunnerV2Tests();f.setUp();self.addCleanup(f.doCleanups)
        before=f.protocol.read_bytes()
        selected,_=select_campaign_records(scores(),f.ref,'test')
        self.assertEqual([x.window_index for x in selected],list(range(144)))
        select_evaluation_records(selected,EvaluationSelection('primary'))
        self.assertEqual(before,f.protocol.read_bytes())
        self.assertEqual(f.doc['frozen']['temporal_selections']['test'],[0,144])
        self.assertEqual(f.doc['frozen']['durations']['test'],144)

    def test_test_evaluation_cannot_silently_fall_back_to_full_horizon(self):
        with self.assertRaisesRegex(ContractError,'explicit EvaluationSelection'):
            select_for_evaluation(scores(),{'role':'test'})
        with self.assertRaisesRegex(ContractError,'DEVELOPMENT'):
            select_for_evaluation(scores(),{'role':'calibration'},EvaluationSelection('primary'))

    def test_boundary_semantics_unchanged_after_selection(self):
        rows=tuple(WindowTruth('development',i,D(i),D(i+1),D(v),D(v))
                   for i,v in [(47,'0.5'),(48,'0'),(49,'0.000001'),(50,'1')])
        selected,_=select_evaluation_records(rows,EvaluationSelection('primary'))
        groups=pure_window_groups(selected)
        self.assertEqual([x.window_index for x in groups['benign']],[48])
        self.assertEqual([x.window_index for x in groups['boundary']],[49])
        self.assertEqual([x.window_index for x in groups['attack']],[50])

    def test_selection_has_no_ground_truth_or_dataset_io(self):
        with patch.object(Path,'open',side_effect=AssertionError('Observation IO forbidden')):
            select_evaluation_records(scores(),EvaluationSelection('primary'))
            select_evaluation_records(scores(),EvaluationSelection('startup_diagnostic'))

    def test_all_four_methods_keep_causal_state_at_48_before_selection(self):
        from analysis.detection import score_run
        from analysis.detection.detectors.zscore import ZScore,zscore_spec
        from analysis.detection.detectors.cov import CoV,cov_spec
        from analysis.detection.detectors.ewma import EWMA,ewma_spec
        from analysis.detection.detectors.cusum import CUSUM,cusum_spec
        f=methods.StandardizedArtifactTests();f.setUp();self.addCleanup(f.doCleanups)
        model=f.model('service','mean_duration_ms')
        values=[12]*48+[14]*96
        target=f.fixture.fixture('full-development','full-development',values)
        source=f.fixture.load(target,'development',feature='mean_duration_ms')
        for method,spec in [(ZScore,zscore_spec),(CoV,lambda:cov_spec(lookback=6)),(EWMA,ewma_spec),(CUSUM,cusum_spec)]:
            detector=method();original_start=detector.start_run
            with patch.object(detector,'start_run',wraps=original_start) as start:
                run=score_run(source,detector,spec(),f.root/method.__name__,baseline=None if method is CoV else model)
            self.assertEqual(start.call_count,1)
            self.assertEqual(len(run.records),144)
            before=run.records
            primary,_=select_evaluation_records(run.records,EvaluationSelection('primary'))
            startup,_=select_evaluation_records(run.records,EvaluationSelection('startup_diagnostic'))
            self.assertEqual((len(primary),len(startup)),(96,48));self.assertEqual(run.records,before)
            self.assertIs(primary[0],run.records[48])
            # A deliberately restarted synthetic suffix differs for stateful methods.
            state=original_start(None if method is CoV else methods.frozen_parameters(),spec().config)
            restarted=detector.update(source.series.observations[48],state).score
            if method is ZScore:self.assertEqual(primary[0].score,restarted)
            else:self.assertNotEqual(primary[0].score,restarted)

    def test_evaluation_callback_receives_only_requested_region(self):
        from analysis.detection import score_run,calibrate,decide
        f=framework.DetectionFrameworkTests();f.setUp();self.addCleanup(f.doCleanups)
        target=f.fixture('full-evaluation','full-evaluation',tuple(range(144)))
        source=f.load(target,'development')
        cal_scores=score_run(f.load(f.calibration,'calibration'),framework.FakeDetector(),f.spec,f.root/'cal-scores')
        policy=calibrate([cal_scores],framework.FakeCalibrator(),f.policy_spec,f.root/'cal-policy')
        full_scores=score_run(source,framework.FakeDetector(),f.spec,f.root/'full-scores')
        decisions=decide(full_scores,framework.FakePolicy(),f.policy_spec,policy,f.root/'full-decisions')
        class Inspect:
            def evaluate(self,inputs,plan):
                expected=list(range(48,144)) if plan.selection.region=='primary' else list(range(48))
                for values in [inputs.scores,inputs.decisions,inputs.labels]:
                    self_indices=[x.score.window_index if hasattr(x,'decision') else x.window_index for x in values]
                    assert self_indices==expected
                return {'synthetic_windows':len(expected)}
        for region,count in [('primary',96),('startup_diagnostic',48)]:
            result=evaluate(full_scores,decisions,target,Inspect(),f.spec,
                EvaluationPlan('pure_windows_only',{},'closure',EvaluationSelection(region)),f.root/region).read()
            self.assertEqual(result['results']['synthetic_windows'],count)
            self.assertEqual(result['plan']['selection'],{'region':region,'version':1})
        self.assertEqual((len(full_scores.records),len(decisions.records)),(144,144))


class EventSelectionTests(unittest.TestCase):
    def event(self,start,end,windows,profile='continuous',region='primary'):
        source={'role':'development'}
        event=EventTruth('development','global',D(48),D(84),D(start),D(end),D(100),profile)
        truth=VerifiedEvents((event,),{},Path('/synthetic'),Path('/synthetic-stage8'),source)
        records=tuple(DecisionRecord(PolicyScore('development',i,D(a),D(b),D(1),True,None,D(at)),True,None,D(at))
                      for i,(a,b,at) in enumerate(windows))
        with patch('analysis.detection.pipeline.validate_decision_run',return_value={'source':source}),patch.object(VerifiedEvents,'verify'):
            result=evaluate_events(DecisionRun(records,None),truth,policy=EVENT_POLICY_V2,selection=EvaluationSelection(region))[0]
        self.assertEqual(truth.events[0],event)
        return result

    def test_actual_event_not_redefined_and_late_availability_still_valid(self):
        result=self.event('45.5','48.5',[('47','48','48'),('48','49','50')])
        self.assertTrue(result.detected);self.assertEqual(result.first_detection_available_at_seconds,D(50))
        self.assertEqual(result.detection_delay_seconds,D('4.5'))
        self.assertIsNone(result.censored_at_seconds)

    def test_startup_region_uses_same_actual_event(self):
        result=self.event('45.5','48.5',[('47','48','48'),('48','49','50')],region='startup_diagnostic')
        self.assertEqual(result.detection_delay_seconds,D('2.5'))

    def test_drained_end_not_used_and_miss_has_no_fabricated_delay(self):
        result=self.event('50','84',[('85','86','86')])
        self.assertFalse(result.detected);self.assertIsNone(result.detection_delay_seconds)

    def test_periodic_global_interval_keeps_silence(self):
        result=self.event('50','84',[('55','56','56')],profile='periodic_burst')
        self.assertTrue(result.detected);self.assertEqual(result.detection_delay_seconds,D(6))


class TestPreflightOnlyTests(unittest.TestCase):
    def setUp(self):
        self.fixture=metadata_fixtures.RunnerV2Tests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root;self.binding=self.fixture.binding;self.hash=self.fixture.hashes['binding_sha256']

    def preflight(self,run=19,**kwargs):
        return runner.preflight_entry(self.binding,self.hash,partition='test',run=run,**kwargs)

    def test_locked_preflight_all_three_scenarios_is_metadata_only(self):
        before=sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*'))
        original=Path.open
        def guard(p,*a,**kw):
            if p.is_relative_to(self.root/runner.OUTPUT_ROOT):raise AssertionError('TEST result IO')
            return original(p,*a,**kw)
        with patch.object(Path,'open',guard),patch.object(runner,'run_pipeline',side_effect=AssertionError('Simulation')):
            for order,scenario in [(19,'B'),(20,'C'),(21,'P')]:
                record=self.preflight(order)
                self.assertEqual(record['status'],'dry_run_ready');self.assertEqual(record['environment_comparison']['fatal'],[])
                self.assertEqual(record['row']['scenario'],scenario)
                self.assertEqual(record['row']['duration_seconds'],144)
                self.assertEqual(record['capability'],'preflight_only');self.assertFalse(record['execution_authorized'])
                self.assertEqual(record['test_execution'],'LOCKED');self.assertEqual(record['pipeline'],[])
                self.assertFalse(Path(record['destination']).exists())
        self.assertEqual(before,sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*')))

    def test_execute_test_is_fatal_before_lock_metadata_or_backend_io(self):
        with patch.object(runner,'preflight_entry',side_effect=AssertionError('Preflight reached')),patch.object(runner,'prepare_entry',side_effect=AssertionError('Preparation reached')),patch.object(runner,'run_pipeline',side_effect=AssertionError('Simulation reached')),patch.object(Path,'open',side_effect=AssertionError('Filesystem IO')):
            with self.assertRaisesRegex(ContractError,'TEST locked: scientific execution forbidden'):
                runner.execute_entry(self.binding,self.hash,partition='test',run=19,execute=True)
        self.assertFalse((self.root/'experiment_results/.stage14-scientific.lock').exists())
        self.assertFalse((self.root/runner.OUTPUT_ROOT).exists())

    def test_legacy_dry_run_routes_to_read_only_capability(self):
        result=runner.execute_entry(self.binding,self.hash,partition='test',run=19,execute=False)
        self.assertEqual(result['status'],'dry_run_ready');self.assertFalse(result['execution_authorized'])
        with self.assertRaisesRegex(ContractError,'TEST locked'):
            runner.prepare_entry(self.binding,self.hash,partition='test',run=19)

    def test_invalid_metadata_configuration_and_collisions_still_fatal(self):
        for change in [dict(seed=0),dict(role='calibration'),dict(scenario='P')]:
            with self.subTest(change=change),self.assertRaises(ContractError):self.preflight(**change)
        config=deepcopy(self.preflight()['configuration']);config['attack']['rate']=999
        with self.assertRaisesRegex(ContractError,'Configuration'):self.preflight(configuration=config)
        dest=Path(self.preflight()['destination']);dest.mkdir(parents=True)
        (dest/'tripwire.txt').write_text('synthetic existing output must not be read')
        with self.assertRaisesRegex(ContractError,'collision'):self.preflight()

    def test_environment_drift_and_residuals_reject_preflight(self):
        for key,value in [('runtime_sha256',{'changed':'hash'}),('active_containers',[{'ID':'synthetic'}]),('residual_processes',['synthetic tcpdump'])]:
            env=deepcopy(self.fixture.env);env[key]=value
            self.assertEqual(self.preflight(environment=env)['status'],'preflight_rejected')

    def test_cli_preflight_and_execute_modes_are_mutually_exclusive(self):
        args=['pretest','--binding-sha256','unused','--partition','test','--run','19','--preflight','--execute']
        with patch('sys.argv',args),patch('sys.stderr',new_callable=StringIO),patch.object(runner,'execute_entry',side_effect=AssertionError('Runner reached')):
            with self.assertRaises(SystemExit) as error:runner.main()
        self.assertEqual(error.exception.code,2)

    def test_cli_admin_audit_cannot_create_scientific_test_outputs(self):
        audit=self.root/runner.OUTPUT_ROOT/'administrative.json'
        args=['pretest','--binding',str(self.binding),'--binding-sha256',self.hash,'--partition','test','--run','19','--preflight','--audit-output',str(audit)]
        with patch('sys.argv',args),self.assertRaisesRegex(ContractError,'outside scientific output root'):runner.main()
        self.assertFalse(audit.exists())


if __name__=='__main__':unittest.main()
