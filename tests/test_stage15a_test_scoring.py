"""Stage15A gates plus synthetic scoring; no TEST scoring in this suite."""
from copy import deepcopy
from dataclasses import fields, replace
from decimal import Decimal as D
import csv
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analysis.detection.artifacts import encoded
from analysis.detection.contracts import Observation, PolicyScore
from analysis.detection.empirical import StrictUpperTail, upper_tail_spec
from analysis.detection.inputs import ContractError
from experiments import stage15a_test_scoring as scoring
from experiments import stage15a_provenance as provenance


def observations(values):
    return tuple(Observation('synthetic',i,D(i),D(i+1),None if x is None else D(str(x))) for i,x in enumerate(values))


class Stage15ATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.freeze=scoring.checked(scoring.INPUTS['four_method_freeze'])
        cls.configs=scoring.configurations(cls.freeze)

    def config(self,method):
        return next(c for c in self.configs if c.method==method and c.feature=='ingress_packet_count')

    def test_approved_bridge_is_content_and_hash_bound(self):
        actual=provenance.validate_bridge(scoring.INPUTS['provenance_bridge'])
        self.assertEqual(actual['human_decision'],'OPTION A APPROVED')
        self.assertFalse(actual['historical_provenance_equals_current_repository_provenance'])
        bad=dict(scoring.INPUTS['provenance_bridge'],sha256='0'*64)
        with self.assertRaises(ContractError):provenance.validate_bridge(bad)
        altered=deepcopy(actual);altered['scope']='unrestricted'
        with patch.object(provenance,'checked',return_value=altered),patch.object(provenance,'bridge_document',return_value=actual):
            with self.assertRaises(ContractError):provenance.validate_bridge(scoring.INPUTS['provenance_bridge'])

    def test_new_provenance_pair_is_rejected(self):
        for path,(old,current,_) in provenance.APPROVED_PAIRS.items():
            provenance.approve_snapshot(path,old,current)
            for pair in [(old,'0'*64),('0'*64,current)]:
                with self.assertRaises(ContractError):provenance.approve_snapshot(path,*pair)
        with self.assertRaises(ContractError):provenance.approve_snapshot('detectors/zscore.py','0'*64,'1'*64)
        with patch.object(provenance,'sha',return_value='0'*64):
            with self.assertRaises(ContractError):provenance.validate_bridge(scoring.INPUTS['provenance_bridge'])

    def test_incorrect_collection_and_calibration_hash_rejected(self):
        for key in ('test_collection_freeze','test_inventory','four_method_freeze','evaluation_protocol','provenance_review'):
            with self.subTest(key=key),self.assertRaises(ContractError):
                scoring.checked(dict(scoring.INPUTS[key],sha256='0'*64))

    def test_48_by_20_matrix_is_complete_and_unique(self):
        # Administrative inventory only, never observations or GT.
        entries=scoring.checked(scoring.INPUTS['test_inventory'])['entries']
        combinations={(e['campaign_entry'],c.method,c.feature) for e in entries for c in self.configs}
        self.assertEqual(len(entries),48);self.assertEqual(len(self.configs),20)
        self.assertEqual(len(combinations),960)
        for entry in entries:
            self.assertEqual(sum(k[0]==entry['campaign_entry'] for k in combinations),20)
        self.assertTrue(all(e['analysis_eligible'] and e['dataset_valid'] for e in entries))

    def test_configuration_and_threshold_identity_are_frozen(self):
        for c in self.configs:
            row=c.lineage['configuration']
            self.assertEqual(row['alpha'],'0.01')
            self.assertEqual(c.threshold_parameters['threshold'],row['threshold'])
            self.assertEqual(c.lineage['threshold_identity'],row['threshold_artifact']['manifest_sha256'])
            if c.method=='cov':self.assertEqual(c.spec.config['lookback'],6)
            if c.method=='ewma':self.assertEqual(c.spec.config['lambda'],'0.2')
            if c.method=='cusum':self.assertEqual(c.spec.config['k'],'0.5')
        for key,value in [('alpha','0.02'),('threshold','0'),('lookback',3),('lambda_value','0.3'),('k','1')]:
            bad=deepcopy(self.freeze);bad['primary_test_configurations'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ContractError):scoring.configurations(bad)

    def test_strict_threshold_ties_and_unavailable(self):
        for c in self.configs:
            policy=StrictUpperTail();state=policy.start_run(c.threshold_parameters,upper_tail_spec(alpha='0.01').config)
            t=D(c.threshold_parameters['threshold'])
            for value,expected in [(t,False),(t.next_plus(),True),(t.next_minus(),False),(None,None)]:
                score=PolicyScore('synthetic',0,D(0),D(1),value,value is not None,None if value is not None else 'null',D(1))
                self.assertIs(policy.decide(score,state).decision,expected)

    def test_signed_zscore_and_null_preserved(self):
        result=scoring.score_decide(observations([0,None]),self.config('zscore'))
        self.assertLess(D(result[0]['score']),0)
        self.assertIsNone(result[1]['score']);self.assertIsNone(result[1]['decision'])

    def test_null_resets_and_cov_warmup_six(self):
        for method in ('ewma','cusum'):
            c=self.config(method)
            out=scoring.score_decide(observations([100,100,None,100]),c)
            self.assertIsNone(out[2]['score']);self.assertIsNone(out[2]['decision'])
            self.assertEqual(out[3]['score'],scoring.score_decide(observations([100]),c)[0]['score'])
        cov=scoring.score_decide(observations([1]*6+[None]+[1]*6),self.config('cov'))
        self.assertTrue(all(r['score'] is None for r in cov[:5]))
        self.assertEqual(D(cov[5]['score']),0)
        self.assertTrue(all(r['score'] is None for r in cov[6:12]))
        self.assertEqual(D(cov[12]['score']),0)
        self.assertIsNone(scoring.score_decide(observations([0]*6),self.config('cov'))[-1]['score'])

    def test_causal_state_continues_through_48(self):
        for method in ('cov','ewma','cusum'):
            c=self.config(method);full=scoring.score_decide(observations([100]*144),c)
            prefix=scoring.score_decide(observations([100]*49),c)
            self.assertEqual(full[:49],prefix)
            self.assertNotEqual(full[48]['score'],full[0]['score'])
            self.assertEqual(full[48]['available_at'],'49')
        with self.assertRaises(ContractError):
            scoring.score_decide((Observation('synthetic',48,D(48),D(49),D(1)),),self.config('ewma'))

    def test_deterministic_synthetic_output(self):
        values=[None if i%13==0 else i%7 for i in range(144)]
        for c in self.configs:
            with scoring.scoring_only():
                a=scoring.score_decide(observations(values),c)
                b=scoring.score_decide(observations(values),c)
            self.assertEqual(encoded(a),encoded(b))

    def test_callbacks_are_label_free_and_do_not_open_files(self):
        self.assertEqual({f.name for f in fields(Observation)},
            {'run_id','window_index','window_start_seconds','window_end_seconds','value'})
        self.assertNotIn('scenario',{f.name for f in fields(PolicyScore)})
        original=StrictUpperTail.decide
        seen=[]
        def inspect_policy(policy,score,state):
            self.assertIs(type(score),PolicyScore);self.assertFalse(hasattr(score,'labels'))
            seen.append(score)
            return original(policy,score,state)
        with patch.object(StrictUpperTail,'decide',inspect_policy),patch.object(Path,'open',side_effect=AssertionError('callback file IO')):
            with scoring.scoring_only():scoring.score_decide(observations([1,None,2]),self.config('ewma'))
        self.assertEqual(len(seen),3)

    def test_execution_guard_rejects_evaluator_fitter_calibrator(self):
        for module,name in [('analysis.detection.evaluation','evaluate'),('analysis.detection.evaluation.events','evaluate_events'),
                            ('analysis.detection.detectors.zscore','fit'),('analysis.detection.empirical','calibrate')]:
            scope={'__name__':module};exec('def '+name+'(): return None',scope)
            with self.subTest(name=name),self.assertRaises(ContractError):
                with scoring.scoring_only():scope[name]()

    def test_feature_reader_preserves_horizon_null_and_never_opens_labels(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);stage=root/'run/stage10';stage.mkdir(parents=True)
            schema=scoring.feature_schema();table=schema['tables']['network'];path=stage/table['path'];path.parent.mkdir()
            (stage/'feature_schema.json').write_text(json.dumps(schema))
            with path.open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=[f['name'] for f in table['fields']]);writer.writeheader()
                for i in range(147):
                    writer.writerow(dict(run_id='synthetic',window_index=i,window_start_seconds=i,window_end_seconds=i+1,
                        **{f['name']:('' if i==0 else 0) for f in table['fields'][4:]}))
            manifest=dict(source_run_id='synthetic',window=dict(size_seconds='1',windows=147))
            (stage/'feature_manifest.json').write_text(json.dumps(manifest))
            entry=dict(output_path='run',run_identity='synthetic',stage10=dict(sha256=scoring.sha(stage/'feature_manifest.json')),
                       artifacts={'stage10/'+table['path']:dict(sha256=scoring.sha(path))})
            original=Path.open;opened=[]
            def monitor(path,*args,**kwargs):
                self.assertNotIn('labels',str(path));self.assertNotIn('attack_events',str(path));opened.append(str(path))
                return original(path,*args,**kwargs)
            with patch.object(scoring,'ROOT',root),patch.object(Path,'open',monitor):
                result,lineage=scoring.read_observations(entry,'ingress_packet_count')
            self.assertEqual(len(result),144);self.assertEqual(result[0].window_index,0)
            self.assertIsNone(result[0].value);self.assertEqual(result[1].value,D(0))
            self.assertEqual(lineage['source_window_count'],147)
            self.assertEqual(lineage['feature_table']['sha256'],scoring.sha(path))




class PublishedStage15AIntegrityTests(unittest.TestCase):
    @unittest.skipUnless((scoring.OUTPUT/'stage15a_scoring_manifest.json').exists(), 'No published Stage15A collection yet')
    def test_frozen_outputs_cardinality_lineage_counts_and_hashes(self):
        # Structural output audit only; no labels, GT, or efficacy interpretation.
        manifest=scoring.read_json(scoring.OUTPUT/'stage15a_scoring_manifest.json')
        inventory=scoring.checked(scoring.INPUTS['test_inventory'])
        entries={e['campaign_entry']:e for e in inventory['entries']}
        expected={(order,method,feature) for order in entries for method in scoring.METHODS for feature in scoring.FEATURES}
        seen=set();totals={k:0 for k in manifest['counts']}
        self.assertEqual(manifest['status'],'FROZEN')
        self.assertEqual(manifest['inputs'],scoring.INPUTS)
        self.assertEqual(manifest['provenance_bridge_sha256'],scoring.INPUTS['provenance_bridge']['sha256'])
        for output in manifest['outputs']:
            key=(output['campaign_entry'],output['method'],output['feature'])
            self.assertNotIn(key,seen);seen.add(key)
            path=scoring.OUTPUT/output['path']
            self.assertEqual(scoring.sha(path),output['sha256'])
            self.assertEqual(path.stat().st_size,output['bytes'])
            result=scoring.read_json(path);entry=entries[key[0]]
            self.assertEqual(result['run_id'],entry['run_identity'])
            self.assertEqual(result['lineage']['inputs'],scoring.INPUTS)
            self.assertEqual(result['lineage']['source']['stage10_manifest'],entry['stage10'])
            self.assertEqual(result['lineage']['stage9_diagnostics'],entry['stage9_diagnostics'])
            self.assertEqual(result['alpha'],'0.01')
            self.assertEqual(result['threshold_identity'],result['lineage']['detector']['threshold_identity'])
            records=result['records'];self.assertEqual(len(records),144)
            self.assertEqual([r['window_index'] for r in records],list(range(144)))
            for i,row in enumerate(records):
                self.assertEqual(D(row['window_start_seconds']),i)
                self.assertEqual(D(row['window_end_seconds']),i+1)
                self.assertEqual(D(row['available_at']),i+1)
                self.assertEqual(row['availability'],row['score'] is not None)
                if row['score'] is None:self.assertIsNone(row['decision'])
                else:self.assertEqual(row['decision'],D(row['score'])>D(result['threshold']))
                self.assertTrue(set(row).isdisjoint({'labels','overlap','actual_start','actual_end','drained_end','attack_active'}))
            counts=dict(observation_count=144,valid_score_count=sum(r['availability'] for r in records),
                unavailable_score_count=sum(not r['availability'] for r in records),
                positive_decision_count=sum(r['decision'] is True for r in records),
                negative_decision_count=sum(r['decision'] is False for r in records))
            self.assertEqual(counts,result['counts']);self.assertEqual(counts,output['counts'])
            for k,v in counts.items():totals[k]+=v
        self.assertEqual(seen,expected);self.assertEqual(len(seen),960)
        self.assertEqual(totals,manifest['counts'])
        self.assertFalse(manifest['scientific_evaluator_executed'])
        self.assertFalse(manifest['ground_truth_consumed_by_scorer'])
        self.assertFalse(manifest['ground_truth_consumed_by_decision_policy'])
        self.assertEqual(scoring.byte_hash(encoded(manifest['outputs']).encode()),manifest['outputs_set_sha256'])


if __name__=='__main__':unittest.main()
