"""V2 method/runner tests: synthetic fixtures and mocked execution ONLY."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal as D
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analysis.detection.contracts import PolicyScore,DecisionRecord
from analysis.detection.evaluation.events import evaluate_events
from analysis.detection.horizons import select_campaign_records
from analysis.detection.inputs import ContractError
from analysis.detection.protocol import EVENT_POLICY_V2,load_protocol,validate_protocol
from experiments import stage14_scientific as runner
from experiments.stage14_bundle import materialize
from experiments.stage14a.prepare import write,sha
from tests import test_stage13c as old
from tests import test_detection_framework as framework


class EventV2Tests(unittest.TestCase):
    def setUp(self):
        self.fixture=old.OriginalEventTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)

    def event(self,start,end,windows,profile='periodic_burst'):
        truth=self.fixture.truth()
        event=replace(truth.events[0],actual_start_seconds=D(str(start)),actual_end_seconds=D(str(end)),profile=profile)
        truth=replace(truth,events=(event,))
        records=tuple(DecisionRecord(PolicyScore('run1',i,D(str(a)),D(str(b)),D(1),True,None,D(str(b))),
                     positive,None,D(str(available))) for i,(a,b,available,positive) in enumerate(windows))
        from analysis.detection.pipeline import DecisionRun
        with patch('analysis.detection.pipeline.validate_decision_run',return_value={'source':truth.source_reference}),patch.object(type(truth),'verify'):
            return evaluate_events(DecisionRun(records,None),truth,policy=EVENT_POLICY_V2)[0]

    def test_window_fully_inside(self):
        r=self.event(5.2,10.5,[(6,7,7,True)])
        self.assertTrue(r.detected);self.assertEqual(r.detection_delay_seconds,D('1.8'))

    def test_first_partial_overlap(self):
        self.assertEqual(self.event(5.2,10.5,[(5,6,6,True)]).detection_delay_seconds,D('.8'))

    def test_last_partial_overlap_mandatory_example(self):
        r=self.event(5.2,10.5,[(10,11,11,True)])
        self.assertTrue(r.detected);self.assertEqual(r.detection_delay_seconds,D('5.8'))
        self.assertIsNone(r.censored_at_seconds)

    def test_computational_availability_after_event(self):
        r=self.event(5.2,10.5,[(6,7,12,True)])
        self.assertEqual(r.detection_delay_seconds,D('6.8'))

    def test_before_event_no_overlap(self):
        self.assertFalse(self.event(5.2,10.5,[(3,4,4,True)]).detected)
        self.assertFalse(self.event(5.2,10.5,[(3,4,9,True)]).detected)

    def test_never_detected(self):
        r=self.event(5.2,10.5,[(6,7,7,False)])
        self.assertFalse(r.detected);self.assertIsNone(r.detection_delay_seconds)
        self.assertIsNone(r.censored_at_seconds)

    def test_periodic_global_silence(self):
        # One global event; synthetic silence window is still inside the event.
        r=self.event(2.2,14.5,[(7,8,8,True)],profile='periodic_burst')
        self.assertTrue(r.detected);self.assertEqual(r.detection_delay_seconds,D('5.8'))

    def test_exact_half_open_boundaries(self):
        for window in [(4,5,5,True),(10,11,11,True)]:
            self.assertFalse(self.event(5,10,[window]).detected)
        for window in [(5,6,6,True),(9,10,10,True)]:
            self.assertTrue(self.event(5,10,[window]).detected)
        self.assertFalse(self.event(5,5,[(4,6,6,True)]).detected)

    def test_first_available_eligible_decision(self):
        r=self.event(5.2,10.5,[(5,6,14,True),(6,7,7,True),(10,11,11,True)])
        self.assertEqual(r.first_detection_available_at_seconds,D(7))


    def test_persisted_pipeline_detects_last_partial_window(self):
        from analysis.detection import score_run,calibrate,decide
        from analysis.detection.contracts import DecisionValue
        from analysis.detection.evaluation import evaluate,EvaluationPlan
        f=framework.DetectionFrameworkTests();f.setUp();self.addCleanup(f.doCleanups)
        cal_scores=score_run(f.load(f.calibration,'calibration'),framework.FakeDetector(),f.spec,f.root/'cal-scores')
        calibration=calibrate([cal_scores],framework.FakeCalibrator(),f.policy_spec,f.root/'cal-policy')
        class LastWindowPolicy(framework.FakePolicy):
            def decide(self,score,state):return DecisionValue(score.window_index==6)
        original=Path.open
        def guard(path,*a,**kw):
            if path.name in ('labels.csv','attack_events.csv'):raise AssertionError('Truth during scoring')
            return original(path,*a,**kw)
        with patch.object(Path,'open',guard):
            scores=score_run(self.fixture.source,framework.FakeDetector(),f.spec,f.root/'scores')
            decisions=decide(scores,LastWindowPolicy(),f.policy_spec,calibration,f.root/'decisions')
        result=evaluate(scores,decisions,self.fixture.source.root,old.DummyEventEvaluator(),f.spec,
            EvaluationPlan('pure_windows_only',{},'closure'),f.root/'evaluation',
            event_truth=self.fixture.truth(),event_policy=EVENT_POLICY_V2).read()
        self.assertTrue(result['event_results'][0]['event_detected'])
        self.assertEqual(result['event_results'][0]['detection_delay_seconds'],'4.8')
        self.assertEqual(result['event_results'][0]['first_detection_available_at_seconds'],'7')
        self.assertIsNone(result['event_results'][0]['censored_at_seconds'])


class RunnerV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for relative in [runner.PLAN_PATH,'experiments/protocols/stage14_protocol.json']:
            dest=self.root/relative;dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes((runner.ROOT/relative).read_bytes())
        self.env=dict(stable=dict(os_id='ubuntu',docker_context='default',engine_os='Ubuntu',git_head='fixture'),
            dynamic=dict(branch='fixture',git_status='?? fixture'),runtime_sha256={},
            active_containers=[],residual_processes=[])
        self.hashes=materialize(self.root,deepcopy(self.env))
        self.binding=self.root/'experiments/protocols/stage14_binding_v2.json'
        self.protocol=self.root/'experiments/protocols/stage14_protocol_v2.json'
        self.doc,self.ref=load_protocol(self.protocol)
        p=patch.object(runner,'ROOT',self.root);p.start();self.addCleanup(p.stop)
        p=patch.object(runner,'observe_environment',return_value=deepcopy(self.env));p.start();self.addCleanup(p.stop)

    def prepare(self,**kw):
        args=dict(partition='baseline',run=1);args.update(kw)
        return runner.prepare_entry(self.binding,self.hashes['binding_sha256'],**args)

    def test_valid_plan_dry_run_has_no_scientific_output(self):
        with patch.object(runner,'run_pipeline',side_effect=AssertionError('Simulation invoked')):
            r=runner.execute_entry(self.binding,self.hashes['binding_sha256'],partition='baseline',run=1)
        self.assertEqual(r['status'],'dry_run_ready')
        self.assertEqual(r['protocol']['protocol_version'],2)
        self.assertFalse(Path(r['destination']).exists())
        self.assertIn('effective_configuration',r)
        self.assertEqual(set(r['references']),{'protocol','seed_plan','matrix','environment_lock','source_stage14a_plan'})

    def test_wrong_seed_rejected(self):
        with self.assertRaises(ContractError):self.prepare(seed=self.doc['seeds']['partitions']['test'][0])

    def test_wrong_role_rejected(self):
        with self.assertRaises(ContractError):self.prepare(role='test')

    def test_wrong_scenario_rejected(self):
        with self.assertRaises(ContractError):self.prepare(scenario='C')

    def test_arbitrary_row_or_partition_rejected(self):
        for args in [dict(run=67),dict(partition='calibration',run=1),dict(partition='other')]:
            with self.subTest(args=args),self.assertRaises(ContractError):self.prepare(**args)

    def test_wrong_binding_hash_rejected(self):
        with self.assertRaisesRegex(ContractError,'Binding'):runner.load_bundle(self.binding,'0'*64)

    def tamper(self,name):
        b=json.loads(self.binding.read_text());path=self.root/b['references'][name]['path']
        path.write_bytes(path.read_bytes()+b'\n')
        with self.assertRaisesRegex(ContractError,'hash'):self.prepare()

    def test_protocol_hash_rejected(self):self.tamper('protocol')
    def test_seed_plan_hash_rejected(self):self.tamper('seed_plan')
    def test_matrix_hash_rejected(self):self.tamper('matrix')
    def test_environment_lock_hash_rejected(self):self.tamper('environment_lock')

    def test_output_collision(self):
        r=self.prepare();Path(r['destination']).mkdir(parents=True)
        with self.assertRaisesRegex(ContractError,'collision'):self.prepare()

    def test_test_never_released_even_dry_run(self):
        with patch.object(runner,'run_pipeline',side_effect=AssertionError('TEST invoked')):
            with self.assertRaisesRegex(ContractError,'TEST locked'):self.prepare(partition='test',run=19)

    def test_configuration_divergence(self):
        r=self.prepare();config=deepcopy(r['configuration']);config['attack']['enabled']=True
        with self.assertRaisesRegex(ContractError,'Configuration'):self.prepare(configuration=config)

    def test_rehashed_matrix_still_cannot_change_scientific_config(self):
        b=json.loads(self.binding.read_text());path=self.root/b['references']['matrix']['path']
        m=json.loads(path.read_text());m['runs'][0]['config']['normal_traffic']['rate']=99
        path.write_text(json.dumps(m));b['references']['matrix']['sha256']=sha(path)
        doc=json.loads(self.protocol.read_text());doc['references'][b['references']['matrix']['path']]=sha(path)
        self.protocol.write_text(json.dumps(doc));b['references']['protocol']['sha256']=sha(self.protocol)
        self.binding.write_text(json.dumps(b))
        with self.assertRaisesRegex(ContractError,'matrix/configuration'):
            runner.prepare_entry(self.binding,sha(self.binding),partition='baseline',run=1)

    def test_environment_fatal_prevents_execution_and_records_audit(self):
        changed=deepcopy(self.env);changed['stable']['git_head']='changed'
        with patch.object(runner,'observe_environment',return_value=changed),patch.object(runner,'run_pipeline',side_effect=AssertionError('Executed')):
            r=runner.execute_entry(self.binding,self.hashes['binding_sha256'],partition='baseline',run=1,execute=True)
        self.assertEqual(r['status'],'preflight_rejected')
        self.assertFalse(Path(r['destination']).exists())
        self.assertEqual(len(list((self.root/'experiment_results/stage14-preflight-v2').glob('*.json'))),1)

    def test_dynamic_environment_only_recorded(self):
        changed=deepcopy(self.env);changed['dynamic']['git_status']='dirty docs';changed['dynamic']['load_average']=[9,8,7]
        self.assertEqual(self.prepare(environment=changed)['environment_comparison']['fatal'],[])

    def test_runtime_drift_and_residuals_fatal(self):
        for key,value in [('runtime_sha256',{'changed':'hash'}),('active_containers',[{'ID':'active'}]),('residual_processes',['tcpdump'])]:
            env=deepcopy(self.env);env[key]=value
            self.assertTrue(self.prepare(environment=env)['environment_comparison']['fatal'])

    def test_mock_execution_materializes_pre_and_post_lineage(self):
        def fake(config,out):
            self.assertTrue((out/'scientific_run_before.json').exists())
            write(out/'fixture.json',{'synthetic_only':True})
            return dict(run_id='synthetic-run',stage8={'manifest_sha256':'a'*64},stage9={'report_sha256':'b'*64},stage10={'manifest_sha256':'c'*64})
        with patch.object(runner,'run_pipeline',side_effect=fake) as invoke:
            r=runner.execute_entry(self.binding,self.hashes['binding_sha256'],partition='baseline',run=1,execute=True)
        self.assertEqual(invoke.call_count,1);self.assertEqual(r['status'],'completed')
        after=json.loads((Path(r['destination'])/'scientific_run_after.json').read_text())
        self.assertEqual(after['lineage']['run_id'],'synthetic-run');self.assertIn('fixture.json',after['outputs_sha256'])
        with self.assertRaises(ContractError):self.prepare()

    def test_backend_failure_preserves_failure_evidence(self):
        with patch.object(runner,'run_pipeline',side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):runner.execute_entry(self.binding,self.hashes['binding_sha256'],partition='baseline',run=1,execute=True)
        path=next((self.root/runner.OUTPUT_ROOT).glob('*/scientific_run_after.json'))
        self.assertEqual(json.loads(path.read_text())['status'],'failed')

    def test_protocol_v2_only_changes_approved_frozen_fields(self):
        v1=json.loads((self.root/'experiments/protocols/stage14_protocol.json').read_text())
        self.assertEqual({k:v for k,v in self.doc['frozen'].items() if k not in ('event_truth','temporal_selections')},
                         {k:v for k,v in v1['frozen'].items() if k!='event_truth'})
        self.assertEqual(self.doc['frozen']['temporal_selections']['calibration'],[48,360])
        for key in ['operation','cov']:
            bad=deepcopy(self.doc);bad['frozen'][key]=None
            with self.assertRaises(ContractError):validate_protocol(bad)

    def select(self,partition):
        records=tuple(PolicyScore('fixture',i,D(i),D(i+1),None if i==60 else D(i),i!=60,
            'missing' if i==60 else None,D(i+1)) for i in range(362))
        return records,*select_campaign_records(records,self.ref,partition)

    def test_baseline_horizon(self):
        full,selected,meta=self.select('baseline');self.assertEqual([r.window_index for r in selected],list(range(48,240)))
        self.assertEqual(len(full),362)

    def test_calibration_horizon_and_exposure(self):
        _,selected,meta=self.select('calibration');self.assertEqual([r.window_index for r in selected],list(range(48,360)))
        self.assertEqual(meta['nominal_exposure_seconds'],'312');self.assertEqual(12*len(selected),3744)

    def test_test_horizon_no_tail(self):
        _,selected,meta=self.select('test');self.assertEqual([r.window_index for r in selected],list(range(144)))
        self.assertEqual(meta['end_seconds'],'144')

    def test_null_preserved(self):
        _,selected,_=self.select('calibration');r=next(r for r in selected if r.window_index==60)
        self.assertIsNone(r.score);self.assertFalse(r.score_available)

    def test_partial_boundary_windows_excluded(self):
        rows=tuple(PolicyScore('x',i,D(a),D(b),D(1),True,None,D(b)) for i,(a,b) in enumerate([('47.5','48.5'),('48','49'),('359','360'),('359.5','360.5')]))
        selected,_=select_campaign_records(rows,self.ref,'calibration')
        self.assertEqual([r.window_index for r in selected],[1,2])

    def test_temporal_selection_does_not_open_labels(self):
        original=Path.open
        def guard(path,*a,**kw):
            if path.name in ('labels.csv','attack_events.csv'):raise AssertionError('Truth access')
            return original(path,*a,**kw)
        with patch.object(Path,'open',guard):self.select('calibration')

    def test_backend_stage8_to_10_binding_with_mocks(self):
        config=self.prepare()['configuration'];dest=self.root/'mock-backend'
        effective=json.loads(runner.ExperimentConfig.from_dict(config).to_json())
        calls=[]
        def simulation(experiment,raw):
            calls.append('simulation');write(raw/'run_status.json',{'status':'completed','run_id':'mock-stage8-run'})
            write(raw/'effective_config.json',effective)
        def export(raw,dataset):
            calls.append('stage8');write(dataset/'dataset_manifest.json',{'run_id':'mock-stage8-run'})
        def validation(dataset):
            calls.append('stage9');return {'dataset_valid':True,'analysis_eligible':True}
        def validation_output(report,path,dataset):write(path,report)
        def extract(dataset,report,features,width):
            calls.append('stage10')
            result={'source_run_id':'mock-stage8-run','dataset_manifest_sha256':sha(dataset/'dataset_manifest.json'),
                    'network_direction':{'supported':True},'window':{'size_seconds':'1','planned_duration_seconds':'240'}}
            write(features/'feature_manifest.json',result);return result
        with patch('experiments.dataset_run.run_recorded',side_effect=simulation),patch('experiments.export_dataset.export_run',side_effect=export),patch('experiments.validate_dataset.validate_dataset',side_effect=validation),patch('experiments.validate_dataset.write_report',side_effect=validation_output),patch('experiments.extract_features.extract_features',side_effect=extract):
            lineage=runner.run_pipeline(config,dest)
        self.assertEqual(calls,['simulation','stage8','stage9','stage10'])
        self.assertEqual(lineage['stage8']['manifest_sha256'],lineage['stage10']['dataset_manifest_sha256'])
        self.assertEqual(lineage['run_id'],'mock-stage8-run')

    def test_campaign_calibration_filters_callback_not_scoring_history(self):
        from analysis.detection import score_run,calibrate
        from analysis.detection.protocol import bind_source
        f=framework.DetectionFrameworkTests();f.setUp();self.addCleanup(f.doCleanups)
        path=f.fixture('long-calibration','long-c',tuple(None if i==60 else i for i in range(362)))
        source=bind_source(f.load(path,'calibration',feature='mean_duration_ms'),self.ref,
            partition='calibration',seed=self.doc['seeds']['partitions']['calibration'][0],scenario='B')
        captured=[]
        class InspectCalibrator:
            def calibrate(self,runs,config):
                captured.extend(runs[0].records)
                return {'test_only':True}
        original=Path.open
        def guard(path,*a,**kw):
            if path.name in ('labels.csv','attack_events.csv'):raise AssertionError('Truth leakage')
            return original(path,*a,**kw)
        with patch.object(Path,'open',guard):
            scores=score_run(source,framework.FakeDetector(),f.spec,f.root/'scores-full')
            policy=calibrate([scores],InspectCalibrator(),f.policy_spec,f.root/'selected-calibration')
        self.assertEqual(len(scores.records),362)
        self.assertEqual([r.window_index for r in captured],list(range(48,360)))
        self.assertIsNone(next(r for r in captured if r.window_index==60).score)
        # Fake score=observation count proves detector did not restart at t=48.
        self.assertEqual(captured[0].score,D(49))
        self.assertEqual(policy.read()['temporal_selections'][0]['selected_windows'],312)

    def test_evaluation_callback_receives_only_selected_windows(self):
        from analysis.detection import score_run,calibrate,decide
        from analysis.detection.protocol import bind_source
        from analysis.detection.evaluation import evaluate,EvaluationPlan
        f=framework.DetectionFrameworkTests();f.setUp();self.addCleanup(f.doCleanups)
        path=f.fixture('eval-calibration','eval-c',tuple(range(362)))
        source=bind_source(f.load(path,'calibration'),self.ref,partition='calibration',
            seed=self.doc['seeds']['partitions']['calibration'][0],scenario='B')
        scores=score_run(source,framework.FakeDetector(),f.spec,f.root/'full-scores')
        calibration=calibrate([scores],framework.FakeCalibrator(),f.policy_spec,f.root/'cal')
        decisions=decide(scores,framework.FakePolicy(),f.policy_spec,calibration,f.root/'decisions')
        result=evaluate(scores,decisions,path,framework.FakeEvaluator(),f.spec,
            EvaluationPlan('test_only_no_metrics',{},'closure'),f.root/'evaluation').read()
        self.assertEqual(result['results']['test_only_label_rows'],312)
        self.assertEqual(result['temporal_selection']['selected_windows'],312)
        self.assertEqual(len(scores.records),362)
