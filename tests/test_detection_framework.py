"""Synthetic Stage 11 tests. All algorithms here are test-only fakes."""
import csv
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.feature_schema import feature_schema, FEATURES, KEYS
from analysis.detection import (load_series, fit_baseline, score_run, calibrate, decide,
                                Component, ScoreValue)
from analysis.detection.artifacts import digest, open_artifact
from analysis.detection.contracts import DecisionValue, ObservedSeries, PolicyScore
from analysis.detection.evaluation import EvaluationPlan, evaluate
from analysis.detection.inputs import ContractError
from analysis.detection.pipeline import validate_score_run, validate_decision_run


class FakeFitter:
    def fit(self, series, config):
        assert all(type(s) is ObservedSeries for s in series)
        assert not any(hasattr(s, 'labels') or hasattr(s, 'root') for s in series)
        return {'test_only_token': config['token']}


class FakeDetector:
    def start_run(self, parameters, config):
        return {'seen': 0, 'parameters': parameters}

    def update(self, observation, state):
        assert not hasattr(observation, 'attack_event_overlap_fraction')
        state['seen'] += 1
        if observation.value is None:
            return ScoreValue(None, 'missing_observation')
        if state['seen'] < 3:
            return ScoreValue(None, 'test_only_warmup')
        return ScoreValue(Decimal(state['seen']))


class FakeCalibrator:
    def calibrate(self, scores, config):
        assert all(type(r) is PolicyScore for s in scores for r in s.records)
        assert not any(hasattr(s, 'labels') or hasattr(s, 'root') for s in scores)
        # Literal test token, not estimated from any data.
        return {'test_only_decision_token': config['token']}


class FakePolicy:
    def start_run(self, parameters, config):
        return parameters

    def decide(self, score, state):
        assert type(score) is PolicyScore
        # Fixed synthetic behavior demonstrates a policy; no statistical threshold.
        return DecisionValue(score.window_index % 2 == 0)


class FakeEvaluator:
    def evaluate(self, inputs, plan):
        assert plan.overlap_policy == 'test_only_no_metrics'
        assert inputs.events is None
        return {'test_only_label_rows': len(inputs.labels), 'metrics_implemented': False}


class DetectionFrameworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.spec = Component('test-only-fake', '1', {'token': 'fixed'}, 'preserve')
        self.policy_spec = Component('test-only-policy', '1', {'token': 'fixed'})
        self.baseline = self.fixture('baseline', 'b')
        self.calibration = self.fixture('calibration', 'c')
        self.test = self.fixture('test', 't')

    def write_json(self, p, value):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value, indent=2) + '\n')

    def fixture(self, name, rid, values=(1, 2, 3, 4, 5)):
        root = self.root / name
        schema = feature_schema()
        self.write_json(root / 'feature_schema.json', schema)
        report = dict(run_id=rid, dataset_manifest_sha256='a' * 64,
                      dataset_valid=True, analysis_eligible=True)
        self.write_json(root / 'evidence/stage9_validation_report.json', report)
        for family, table in schema['tables'].items():
            path = root / table['path']; path.parent.mkdir(parents=True, exist_ok=True)
            columns = [f['name'] for f in table['fields']]
            with path.open('w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=columns); writer.writeheader()
                for i, value in enumerate(values):
                    row = dict(run_id=rid, window_index=i, window_start_seconds=i, window_end_seconds=i+1)
                    for field in table['fields'][4:]:
                        row[field['name']] = '' if value is None and field['nullable'] else (0 if value is None else value)
                    if family == 'labels':
                        row.update(attack_event_overlap_seconds='0.5' if i == 1 else 0,
                                   attack_event_overlap_fraction='0.5' if i == 1 else 0,
                                   attack_request_starts=0)
                    writer.writerow(row)
        manifest = dict(feature_schema_version=1, source_run_id=rid,
            dataset_manifest_sha256='a' * 64, window=dict(size_seconds='1', windows=len(values), decimal_boundary_precision=50),
            detector_columns=FEATURES, network_direction=dict(supported=True),
            stage9_validation_report=dict(path='evidence/stage9_validation_report.json',
                sha256=digest(root / 'evidence/stage9_validation_report.json'), analysis_eligible=True),
            outputs=[])
        for path in [root / 'feature_schema.json', root / 'evidence/stage9_validation_report.json', *sorted((root/'timeseries').glob('*.csv'))]:
            manifest['outputs'].append(dict(path=str(path.relative_to(root)), sha256=digest(path), bytes=path.stat().st_size))
        self.write_json(root/'feature_manifest.json', manifest)
        return root

    def load(self, root=None, role='test', family='service', feature='request_starts', **overrides):
        root = root or self.test
        m = json.loads((root/'feature_manifest.json').read_text())
        args = dict(run_id=m['source_run_id'], family=family, feature=feature,
                    window_size_seconds='1', feature_schema_version=1, role=role)
        args.update(overrides)
        return load_series(root, **args)

    def change_manifest(self, root, fn):
        p=root/'feature_manifest.json'; m=json.loads(p.read_text());fn(m);self.write_json(p,m)

    def refresh(self, root, relative):
        def update(m):
            for x in m['outputs']:
                if x['path']==relative:x.update(sha256=digest(root/relative),bytes=(root/relative).stat().st_size)
        self.change_manifest(root,update)

    def fit(self):
        return fit_baseline([self.load(self.baseline,'baseline')],FakeFitter(),self.spec,self.root/'model')

    def pipeline(self):
        model=self.fit()
        calibration_scores=score_run(self.load(self.calibration,'calibration'),FakeDetector(),self.spec,self.root/'cal-scores',baseline=model)
        policy=calibrate([calibration_scores],FakeCalibrator(),self.policy_spec,self.root/'policy')
        scores=score_run(self.load(),FakeDetector(),self.spec,self.root/'scores',baseline=model)
        decisions=decide(scores,FakePolicy(),self.policy_spec,policy,self.root/'decisions')
        return model,policy,scores,decisions

    def test_explicit_feature_required(self):
        with self.assertRaises(TypeError):load_series(self.test)

    def test_forbidden_selections(self):
        for family,feature in [('labels','attack_event_overlap_fraction'),('service','attack_request_starts'),('service','run_id'),('service','window_start_seconds'),('service','unknown')]:
            with self.subTest(feature=feature),self.assertRaises(ContractError):self.load(family=family,feature=feature)

    def test_identity_mismatches(self):
        for kwargs in [dict(run_id='wrong'),dict(feature_schema_version=2),dict(window_size_seconds='0.5'),dict(role='')]:
            with self.subTest(kwargs=kwargs),self.assertRaises(ContractError):self.load(**kwargs)

    def test_network_unavailable(self):
        self.change_manifest(self.test,lambda m:m['network_direction'].update(supported=False))
        with self.assertRaisesRegex(ContractError,'feature_unavailable'):self.load(family='network',feature='ingress_packet_count')

    def test_all_null_unavailable(self):
        root=self.fixture('empty','empty',(None,)*5)
        with self.assertRaisesRegex(ContractError,'feature_unavailable'):self.load(root,feature='mean_duration_ms')

    def test_missing_never_zero_and_explicit_policy(self):
        root=self.fixture('partial','p',(1,None,3,4,5)); source=self.load(root,feature='mean_duration_ms')
        self.assertIsNone(source.series.observations[1].value)
        with self.assertRaisesRegex(ContractError,'Partial null'):
            score_run(source,FakeDetector(),replace(self.spec,missing='reject'),self.root/'reject')
        run=score_run(source,FakeDetector(),self.spec,self.root/'partial-scores')
        self.assertIsNone(run.records[1].score);self.assertEqual(run.records[1].reason,'missing_observation')

    def test_missing_cannot_be_scored_as_observation(self):
        class Bad(FakeDetector):
            def update(self,o,s):return ScoreValue(Decimal(0))
        root=self.fixture('partial','p',(1,None,3));source=self.load(root,feature='mean_duration_ms')
        with self.assertRaisesRegex(ContractError,'Missing observation'):
            score_run(source,Bad(),self.spec,self.root/'bad')

    def test_warmup_and_state_reset(self):
        d=FakeDetector();s=self.load()
        a=score_run(s,d,self.spec,self.root/'a');b=score_run(s,d,self.spec,self.root/'bb')
        self.assertEqual(a.records,b.records)
        self.assertIsNone(a.records[0].score);self.assertFalse(a.records[1].score_available)
        self.assertEqual(a.records[2].score,Decimal(3))

    def test_full_pipeline_no_labels_io_and_separate_artifacts(self):
        original=Path.open
        def guard(path,*a,**kw):
            if path.name=='labels.csv':raise AssertionError('labels IO outside evaluator')
            return original(path,*a,**kw)
        with patch.object(Path,'open',guard):model,policy,scores,decisions=self.pipeline()
        self.assertNotEqual(scores.artifact.root,decisions.artifact.root)
        self.assertEqual(scores.artifact.read()['kind'],'scores')
        self.assertEqual(decisions.artifact.read()['kind'],'decisions')
        self.assertIsNone(decisions.records[0].decision)
        self.assertEqual(decisions.records[0].reason,'test_only_warmup')
        self.assertEqual(decisions.artifact.read()['calibration'],policy.reference)
        self.assertEqual(scores.artifact.read()['baseline'],model.reference)
        self.assertNotIn('labels.csv',json.dumps(model.read()))

    def test_calibration_never_uses_test_scores(self):
        s=score_run(self.load(),FakeDetector(),self.spec,self.root/'s')
        with self.assertRaisesRegex(ContractError,'only designated calibration'):
            calibrate([s],FakeCalibrator(),self.policy_spec,self.root/'c-bad')
        self.assertFalse((self.root/'c-bad').exists())

    def test_fit_never_uses_test(self):
        with self.assertRaisesRegex(ContractError,'requires baseline'):
            fit_baseline([self.load()],FakeFitter(),self.spec,self.root/'bad')

    def test_duplicate_alias_refused(self):
        b=self.load(self.baseline,'baseline')
        with self.assertRaisesRegex(ContractError,'Duplicate'):
            fit_baseline([b,b],FakeFitter(),self.spec,self.root/'bad')

    def test_same_run_cannot_be_test_after_fit(self):
        model=self.fit()
        with self.assertRaisesRegex(ContractError,'disjoint'):
            score_run(self.load(self.baseline,'test'),FakeDetector(),self.spec,self.root/'bad',baseline=model)

    def test_same_run_cannot_be_test_after_calibration(self):
        _,policy,_,_=self.pipeline()
        model=open_artifact(policy.read()['baseline'],'baseline')
        s=score_run(self.load(self.calibration,'test'),FakeDetector(),self.spec,self.root/'same-s',baseline=model)
        with self.assertRaisesRegex(ContractError,'overlaps'):
            decide(s,FakePolicy(),self.policy_spec,policy,self.root/'bad')

    def test_model_configuration_mismatch(self):
        model=self.fit()
        with self.assertRaisesRegex(ContractError,'Baseline detector'):
            score_run(self.load(),FakeDetector(),replace(self.spec,version='2'),self.root/'bad',baseline=model)

    def test_decision_policy_mismatch(self):
        _,policy,s,_=self.pipeline()
        with self.assertRaisesRegex(ContractError,'Calibration/policy'):
            decide(s,FakePolicy(),replace(self.policy_spec,version='2'),policy,self.root/'bad')

    def test_evaluator_only_labels_reader_explicit_plan(self):
        _,_,s,d=self.pipeline()
        with self.assertRaises(ContractError):evaluate(s,d,self.test,FakeEvaluator(),self.spec,None,self.root/'bad')
        with self.assertRaises(ContractError):evaluate(s,d,self.test,FakeEvaluator(),self.spec,EvaluationPlan('',{},''),self.root/'bad')
        a=evaluate(s,d,self.test,FakeEvaluator(),self.spec,
                   EvaluationPlan('test_only_no_metrics',{},'closure'),self.root/'eval')
        self.assertEqual(a.read()['results']['test_only_label_rows'],5)
        self.assertEqual(a.read()['event_truth'],'unavailable_in_stage10_v1_union_labels')

    def test_available_times_at_closure(self):
        _,_,s,d=self.pipeline()
        for score,decision in zip(s.records,d.records):
            self.assertEqual(score.available_at_seconds,score.window_end_seconds)
            self.assertEqual(decision.available_at_seconds,score.available_at_seconds)

    def test_early_score_time_refused(self):
        class Bad(FakeDetector):
            def update(self,o,s):return ScoreValue(Decimal(1),available_at_seconds=o.window_start_seconds)
        with self.assertRaisesRegex(ContractError,'availability'):
            score_run(self.load(),Bad(),self.spec,self.root/'bad')

    def test_early_decision_time_refused(self):
        class Bad(FakePolicy):
            def decide(self,s,state):return DecisionValue(True,available_at_seconds=s.window_start_seconds)
        _,p,s,_=self.pipeline()
        with self.assertRaisesRegex(ContractError,'availability'):
            decide(s,Bad(),self.policy_spec,p,self.root/'bad')

    def test_nonfinite_score_and_missing_reason_refused(self):
        class Bad(FakeDetector):
            def update(self,o,s):return ScoreValue(Decimal('NaN'))
        with self.assertRaises(ContractError):score_run(self.load(),Bad(),self.spec,self.root/'bad')
        class Missing(FakeDetector):
            def update(self,o,s):return ScoreValue(None)
        with self.assertRaises(ContractError):score_run(self.load(),Missing(),self.spec,self.root/'bad2')

    def test_deterministic_artifacts(self):
        source=self.load();a=score_run(source,FakeDetector(),self.spec,self.root/'a')
        b=score_run(source,FakeDetector(),self.spec,self.root/'bb')
        self.assertEqual((a.artifact.root/'manifest.json').read_bytes(),(b.artifact.root/'manifest.json').read_bytes())
        self.assertEqual((a.artifact.root/'scores.csv').read_bytes(),(b.artifact.root/'scores.csv').read_bytes())

    def test_inputs_unchanged(self):
        paths=[p for r in (self.baseline,self.calibration,self.test) for p in r.rglob('*') if p.is_file()]
        before={p:(digest(p),p.stat().st_mtime_ns) for p in paths}
        self.pipeline()
        self.assertEqual(before,{p:(digest(p),p.stat().st_mtime_ns) for p in paths})

    def test_bad_manifest_binding(self):
        self.change_manifest(self.test,lambda m:m.update(source_run_id='bad'))
        with self.assertRaises(ContractError):self.load(run_id='t')

    def test_bad_report_binding(self):
        p=self.test/'evidence/stage9_validation_report.json';v=json.loads(p.read_text());v['analysis_eligible']=False;self.write_json(p,v)
        self.refresh(self.test,'evidence/stage9_validation_report.json')
        self.change_manifest(self.test,lambda m:m['stage9_validation_report'].update(sha256=digest(p)))
        with self.assertRaises(ContractError):self.load()

    def test_schema_cannot_redirect_observable_to_labels(self):
        p=self.test/'feature_schema.json';v=json.loads(p.read_text());v['tables']['service']['path']='timeseries/labels.csv';self.write_json(p,v);self.refresh(self.test,'feature_schema.json')
        with self.assertRaisesRegex(ContractError,'Schema differs'):self.load()

    def test_tampering_before_read(self):
        p=self.test/'timeseries/service.csv';p.write_text(p.read_text()+'\n')
        with self.assertRaisesRegex(ContractError,'hash/size'):self.load()

    def test_post_load_mutation_refused(self):
        source=self.load();p=self.test/'timeseries/service.csv';p.write_text(p.read_text()+'\n')
        with self.assertRaisesRegex(ContractError,'changed'):score_run(source,FakeDetector(),self.spec,self.root/'bad')

    def test_mutation_during_callback_no_output(self):
        path=self.test/'timeseries/service.csv'
        class Mutating(FakeDetector):
            def update(self,o,s):
                if o.window_index==0:path.write_text(path.read_text()+'\n')
                return super().update(o,s)
        with self.assertRaises(ContractError):score_run(self.load(),Mutating(),self.spec,self.root/'bad')
        self.assertFalse((self.root/'bad').exists())

    def test_baseline_and_output_tampering_refused(self):
        model,_,scores,_=self.pipeline()
        self.assertEqual(model.read()['sources'][0]['run_id'],'b')
        (model.root/'manifest.json').write_text('{}')
        with self.assertRaisesRegex(ContractError,'changed'):validate_score_run(scores)

    def test_score_output_tampering(self):
        s=score_run(self.load(),FakeDetector(),self.spec,self.root/'s')
        (s.artifact.root/'scores.csv').write_text('corrupt')
        with self.assertRaises(ContractError):validate_score_run(s)

    def test_in_memory_record_tampering(self):
        _,_,s,d=self.pipeline()
        altered=replace(s,records=(replace(s.records[0],score=Decimal(42)),*s.records[1:]))
        with self.assertRaises(ContractError):validate_score_run(altered)
        altered_d=replace(d,records=(replace(d.records[0],decision=True),*d.records[1:]))
        with self.assertRaises(ContractError):validate_decision_run(altered_d)

    def test_labels_tampering_detected_only_by_evaluator(self):
        _,_,s,d=self.pipeline();p=self.test/'timeseries/labels.csv';p.write_text('corrupt')
        validate_score_run(s)
        with self.assertRaises(ContractError):evaluate(s,d,self.test,FakeEvaluator(),self.spec,EvaluationPlan('test_only_no_metrics',{},'closure'),self.root/'bad')

    def test_output_cannot_overlap_inputs_or_overwrite(self):
        s=self.load()
        with self.assertRaises(ContractError):score_run(s,FakeDetector(),self.spec,self.test/'nested')
        # Existing inputs still intact; no directory created inside them.
        self.assertFalse((self.test/'nested').exists())
        score_run(s,FakeDetector(),self.spec,self.root/'s')
        with self.assertRaises(ContractError):score_run(s,FakeDetector(),self.spec,self.root/'s')

    def test_persisted_phase_roundtrip(self):
        from analysis.detection import load_scores, load_decisions
        _,_,s,d=self.pipeline()
        loaded_s=load_scores(s.artifact.reference)
        loaded_d=load_decisions(d.artifact.reference)
        self.assertEqual(s.records,loaded_s.records)
        self.assertEqual(d.records,loaded_d.records)
        a=evaluate(loaded_s,loaded_d,self.test,FakeEvaluator(),self.spec,
                   EvaluationPlan('test_only_no_metrics',{},'closure'),self.root/'loaded-eval')
        self.assertFalse(a.read()['results']['metrics_implemented'])

    def test_changed_calibration_source_invalidates_decision_reference(self):
        _,_,_,d=self.pipeline()
        p=self.calibration/'timeseries/service.csv';p.write_text(p.read_text()+'\n')
        with self.assertRaises(ContractError):validate_decision_run(d)

    def test_irregular_grid_and_nonfinite_feature(self):
        p=self.test/'timeseries/service.csv'
        text=p.read_text();p.write_text(text.replace('t,0,0,1,','t,0,0,2,'))
        self.refresh(self.test,'timeseries/service.csv')
        with self.assertRaisesRegex(ContractError,'Irregular grid'):self.load()
        p.write_text(text.replace('t,0,0,1,1,','t,0,0,1,NaN,'))
        self.refresh(self.test,'timeseries/service.csv')
        with self.assertRaisesRegex(ContractError,'Nonfinite'):self.load()

    def test_decimal_grid_independent_of_global_precision(self):
        from decimal import localcontext
        width=Decimal('0.123456789012345678901234567890123456789')
        p=self.test/'timeseries/service.csv'
        with p.open(newline='') as f:
            reader=csv.DictReader(f);columns=reader.fieldnames;rows=list(reader)
        with localcontext() as ctx:
            ctx.prec=100
            for i,r in enumerate(rows):
                r.update(window_start_seconds=str(width*i),window_end_seconds=str(width*(i+1)))
        with p.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(rows)
        self.refresh(self.test,'timeseries/service.csv')
        self.change_manifest(self.test,lambda m:m['window'].update(size_seconds=str(width)))
        with localcontext() as ctx:
            ctx.prec=6
            source=self.load(window_size_seconds=str(width))
        self.assertEqual(source.series.observations[1].window_start_seconds,width)

    def test_unsafe_path_and_symlink(self):
        self.change_manifest(self.test,lambda m:m['outputs'][0].update(path='../escape'))
        with self.assertRaises(ContractError):self.load()
        self.test=self.fixture('link-target','tt')
        p=self.test/'timeseries/service.csv';target=self.root/'moved.csv';p.rename(target);p.symlink_to(target)
        with self.assertRaises(ContractError):self.load()


if __name__=='__main__':unittest.main()
