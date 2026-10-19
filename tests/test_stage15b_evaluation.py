"""Frozen-source integrity and synthetic-only evaluator semantics/regressions."""
from copy import deepcopy
from dataclasses import fields
from fractions import Fraction as F
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from experiments import stage15b_evaluation as ev
from experiments import stage15b_reproduce as independent


def decisions(values,at=None):
    return tuple(ev.FrozenDecision(i,F(i),F(i+1),F(i+1) if at is None else at(i),v) for i,v in enumerate(values))


def truth(event=None):
    overlap=tuple(F(0) if event is None else max(F(0),min(F(i+1),event.end)-max(F(i),event.start)) for i in range(144))
    return ev.GroundTruth(overlap,event,{})


class Stage15BTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Source integrity only; no TEST metrics computed by the tests below.
        cls.docs=ev.validate_sources()

    def test_frozen_authorities_and_960_sources(self):
        self.assertEqual(len(self.docs['stage15a_manifest']['outputs']),960)
        self.assertEqual(self.docs['stage15a_manifest']['status'],'FROZEN')
        for ref in ev.INPUTS.values():self.assertEqual(ev.sha(ev.ROOT/ref['path']),ref['sha256'])
        self.assertEqual(self.docs['test_collection_freeze']['collection_authority_head'],ev.COLLECTION_HEAD)

    def test_wrong_authority_or_decision_hash_rejected(self):
        for key in ev.INPUTS:
            with self.subTest(key=key),self.assertRaises(ev.IntegrityError):ev.checked(dict(ev.INPUTS[key],sha256='0'*64))
        output=dict(self.docs['stage15a_manifest']['outputs'][0],sha256='0'*64)
        with self.assertRaises(ev.IntegrityError):ev.load_decisions(output,self.docs['test_inventory']['entries'][0])

    def test_unavailable_and_horizon_contract_reject_ambiguity(self):
        for section,key,value in [('scenario_CP','confusion_matrix','undefined'),('scenario_CP','F1','P*R'),('horizons','primary_evaluation',[0,144])]:
            p=deepcopy(self.docs['evaluation_protocol']);p[section][key]=value
            with self.subTest(key=key),self.assertRaises(ev.IntegrityError):ev.validate_protocol(p)

    def test_no_scorer_detector_policy_or_parameter_selection_calls(self):
        for module,name in [('analysis.detection.detectors.ewma','update'),('analysis.detection.empirical','decide'),
                            ('experiments.stage15a_test_scoring','score_decide'),('analysis.detection.pipeline','calibrate'),
                            ('analysis.detection.pipeline','fit_baseline')]:
            scope={'__name__':module};exec('def '+name+'(): return None',scope)
            with self.subTest(module=module),self.assertRaises(ev.IntegrityError):
                with ev.evaluation_only():scope[name]()
        self.assertEqual({f.name for f in fields(ev.FrozenDecision)},{'index','start','end','available_at','value'})
        self.assertNotIn('drained_end',{f.name for f in fields(ev.FrozenEvent)})

    def test_primary_and_startup_are_disjoint(self):
        ds=decisions([True]*48+[False]*96)
        a=ev.window_metrics(ds,truth(),'PRIMARY');b=ev.window_metrics(ds,truth(),'STARTUP_DIAGNOSTIC')
        self.assertEqual((a['candidate_decisions'],a['FP'],a['TN']),(96,0,96))
        self.assertEqual((b['candidate_decisions'],b['FP'],b['TN']),(48,48,0))
        self.assertEqual(b['analysis_scope'],'STARTUP_DIAGNOSTIC')

    def test_boundary_unavailable_and_confusion_counts(self):
        event=ev.FrozenEvent('global',F('48.25'),F('50.75'),'continuous')
        values=[False]*144;values[48]=True;values[49]=True;values[50]=None;values[51]=None;values[52]=True
        row=ev.window_metrics(decisions(values),truth(event),'PRIMARY')
        self.assertEqual((row['TP'],row['FP'],row['TN'],row['FN']),(1,1,91,0))
        self.assertEqual(row['boundary_excluded_count'],2)
        self.assertEqual(row['unavailable_decision_count'],2)
        self.assertEqual(row['unavailable_boundary_decisions'],1)
        self.assertEqual(row['unavailable_benign_decisions'],1)
        self.assertEqual(row['precision'],F(1,2));self.assertEqual(row['recall'],1);self.assertEqual(row['f1'],F(2,3))

    def test_benign_b_recall_undefined_and_no_event(self):
        t=truth();self.assertIsNone(t.event)
        row=ev.window_metrics(decisions([False]*144),t,'PRIMARY')
        self.assertEqual(row['TN'],96);self.assertEqual(row['TP']+row['FN'],0)
        self.assertIsNone(row['recall']);self.assertIsNone(row['precision']);self.assertIsNone(row['f1'])
        self.assertEqual(row['fpr'],0)

    def test_zero_denominators_never_become_zero_and_count_f1(self):
        row=ev.window_metrics(decisions([None]*144),truth(),'PRIMARY')
        self.assertTrue(all(row[k] is None for k in ev.METRIC_NAMES))
        self.assertEqual(row['unavailable_decision_count'],96)
        # Pre-TEST protocol explicitly defines count-form F1, even where precision
        # separately has a zero denominator. This is not null-to-zero imputation.
        result=ev.ratios(dict(TP=0,FP=0,TN=1,FN=1))
        self.assertIsNone(result['precision']);self.assertEqual(result['f1'],0)

    def test_event_actual_end_and_delayed_availability_are_preserved(self):
        event=ev.FrozenEvent('global',F('48.25'),F('48.75'),'continuous')
        values=[False]*144;values[48]=True
        row=ev.event_metrics(decisions(values),event)
        self.assertTrue(row['event_detected']);self.assertEqual(row['detection_time'],49)
        self.assertGreater(row['detection_time'],event.end);self.assertEqual(row['detection_delay_seconds'],F('0.75'))
        self.assertEqual(row['actual_end'],F('48.75'))

    def test_event_detection_minimum_time_miss_and_no_startup_alarm(self):
        e=ev.FrozenEvent('global',F(48),F(55),'continuous');values=[False]*144
        values[47]=True
        missed=ev.event_metrics(decisions(values),e)
        self.assertFalse(missed['event_detected']);self.assertIsNone(missed['detection_time']);self.assertIsNone(missed['detection_delay_seconds'])
        values[49]=True;values[51]=True
        row=ev.event_metrics(decisions(values),e);self.assertEqual(row['detection_time'],50);self.assertEqual(row['detection_delay_seconds'],2)

    def test_periodic_is_one_global_event_including_silence(self):
        event=ev.FrozenEvent('global',F(48),F(84),'periodic_burst');values=[False]*144;values[53]=True
        row=ev.event_metrics(decisions(values),event)
        self.assertTrue(row['event_detected']);self.assertEqual(row['event_id'],'global')
        self.assertEqual(ev.window_metrics(decisions(values),truth(event),'PRIMARY')['attack_windows'],36)

    def test_negative_delay_is_stop(self):
        e=ev.FrozenEvent('global',F('48.5'),F(50),'continuous')
        ds=(ev.FrozenDecision(48,F(48),F(49),F(48),True),)
        with self.assertRaises(ev.IntegrityError):ev.event_metrics(ds,e)

    def test_post_event_uses_actual_end_and_available_denominator(self):
        e=ev.FrozenEvent('global',F(48),F('84.1'),'continuous');values=[False]*144
        values[84]=True;values[85]=True;values[86]=None
        row=ev.post_event_metrics(decisions(values),e)
        self.assertEqual(row['candidate_post_event_decisions'],59)
        self.assertEqual(row['post_event_eligible_windows'],58)
        self.assertEqual(row['post_event_positive_decisions'],1)
        self.assertEqual(row['post_event_alarm_rate'],F(1,58))
        self.assertEqual(row['interval_start'],F('84.1'))

    def test_post_event_without_support_is_null(self):
        e=ev.FrozenEvent('global',F(48),F(144),'continuous')
        self.assertIsNone(ev.post_event_metrics(decisions([False]*144),e)['post_event_alarm_rate'])

    def test_exact_descriptive_statistics_and_defined_support(self):
        self.assertEqual(ev.plain(ev.describe([F(1,3),None,F(2,3)])),ev.plain(independent.describe_independently([F(1,3),None,F(2,3)])))
        self.assertIsNone(ev.describe([None])['mean']);self.assertIsNone(ev.describe([F(1)])['sample_sd'])
        values=[F(1,10),F(2,10),F(9,10)]
        self.assertEqual(ev.encoded(ev.describe(values)),ev.encoded(independent.describe_independently(values)))

    def test_synthetic_48_paired_runs_20_configs_and_independent_reproduction(self):
        entries=[];outputs=[];gt={};run=0
        for seed in range(16):
            for scenario in 'BCP':
                run+=1
                entries.append(dict(campaign_entry=run,run_identity='synthetic-'+str(run),seed=seed,scenario=scenario,
                    stage9_diagnostics=[],dataset_valid=True,analysis_eligible=True))
                event=None if scenario=='B' else ev.FrozenEvent('global',F('48.25'),F('84.75'),'continuous' if scenario=='C' else 'periodic_burst')
                gt[run]=truth(event)
                for method in ev.METHODS:
                    for feature in ev.FEATURES:outputs.append(dict(campaign_entry=run,method=method,feature=feature,path='synthetic',sha256='synthetic'))
        docs=dict(test_inventory=dict(entries=entries),stage15a_manifest=dict(outputs=outputs))
        def synthetic_reader(output,entry):
            values=[None if i%17==0 else bool((i+entry['seed'])%3==0) for i in range(144)]
            return decisions(values)
        with patch.object(ev,'load_decisions',synthetic_reader),patch.object(independent,'load_decisions',synthetic_reader):
            with ev.evaluation_only():
                tables,inventory=ev.evaluate_all(docs,gt);other=independent.independent_tables(docs,gt)
        self.assertEqual(ev.encoded(tables),ev.encoded(other))
        self.assertEqual(len(tables['window_metrics_per_run']),960);self.assertEqual(len(tables['startup_diagnostic_per_run']),960)
        self.assertEqual(len(tables['event_metrics_per_run']),640)
        self.assertEqual({r['scenario'] for r in tables['event_metrics_per_run']},{'C','P'})
        self.assertEqual(len(inventory),960)
        self.assertTrue(all(r['aggregation']=='SUPPLEMENTARY_POOLED_WINDOWS' for r in tables['window_metrics_pooled']))
        for row in tables['window_metrics_per_run']:
            for name in ev.METRIC_NAMES:self.assertTrue(row[name] is None or 0<=row[name]<=1)
        self.assertFalse(any('rank' in k or 'best' in k for rows in tables.values() for row in rows for k in row))
        self.assertEqual(ev.csv_bytes(tables['window_metrics_per_run']),ev.csv_bytes(tables['window_metrics_per_run']))

    def test_csv_null_and_json_null_contract(self):
        self.assertEqual(ev.csv_bytes([dict(metric=None,reason='zero_denominator')]),b'metric,reason\n,zero_denominator\n')
        self.assertIn(b'null',ev.encoded(dict(metric=None)))


class PublishedStage15BTests(unittest.TestCase):
    @unittest.skipUnless((ev.OUTPUT/'stage15b_evaluation_freeze_manifest.json').exists(),'Stage15B not materialized')
    def test_published_freeze_hashes_cardinality_and_isolation(self):
        freeze=ev.json_read(ev.OUTPUT/'stage15b_evaluation_freeze_manifest.json')
        manifest=ev.checked(freeze['manifest'])
        self.assertEqual(manifest['status'],'FROZEN');self.assertEqual(manifest['inputs'],ev.INPUTS)
        self.assertEqual((manifest['primary_run_config_evaluations'],manifest['event_run_config_evaluations']),(960,640))
        self.assertFalse(manifest['scores_modified']);self.assertFalse(manifest['decisions_modified'])
        self.assertFalse(manifest['ranking_performed']);self.assertFalse(manifest['hypothesis_testing_performed'])
        for output in manifest['outputs']:
            self.assertEqual(ev.sha(ev.OUTPUT/output['path']),output['sha256'])
        self.assertEqual(ev.digest(manifest['outputs']),manifest['outputs_set_sha256'])
        tables=ev.json_read(ev.OUTPUT/'evaluation_results.json')
        self.assertEqual(len(tables['window_metrics_per_run']),960)
        self.assertEqual(len(tables['event_metrics_per_run']),640)
        self.assertEqual(len(tables['startup_diagnostic_per_run']),960)
        kept=[r for r in tables['window_metrics_per_run'] if r['campaign_entry']==29]
        self.assertEqual(len(kept),20)
        self.assertTrue(all(r['historical_warning_codes']==['EXPECTED_PHASE_OBSERVATIONS','REQUEST_FAILURES_OBSERVED'] for r in kept))


if __name__=='__main__':unittest.main()
