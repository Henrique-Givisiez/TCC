"""Descriptive-stage tests. Never execute detectors, policies or evaluator."""
from fractions import Fraction as F
from decimal import Decimal
from pathlib import Path
import unittest
from experiments import stage15c_analysis as a


def row(seed,tp,fp,tn,fn,scenario='C'):
    r=dict(seed=seed,scenario=scenario,method='zscore',feature=a.FEATURES[0],TP=tp,FP=fp,TN=tn,FN=fn,analysis_scope='PRIMARY')
    for key,(num,den) in dict(precision=(tp,tp+fp),recall=(tp,tp+fn),f1=(2*tp,2*tp+fp+fn),fpr=(fp,fp+tn)).items():r[key]=a.text(F(num,den)) if den else None
    return r


class Stage15CDescriptiveTests(unittest.TestCase):
    def test_quantile_type7_and_sample_support(self):
        stats=a.describe([F(0),F(10),F(20),F(30)])
        self.assertEqual(stats['q1'],F(15,2));self.assertEqual(stats['q3'],F(45,2));self.assertEqual(stats['median'],15)
        self.assertEqual(stats['defined_n'],4);self.assertEqual(stats['undefined_n'],0)
        self.assertIsNone(a.describe([None])['mean']);self.assertIsNone(a.describe([None,F(3)])['sample_sd'])
        self.assertEqual(a.describe([None,F(0)])['defined_n'],1)

    def test_null_is_not_zero_and_csv_representation(self):
        self.assertNotEqual(a.describe([None,1])['mean'],a.describe([0,1])['mean'])
        self.assertEqual(a.csv_bytes([dict(metric=None,n=0)]),b'metric,n\n,0\n')
        self.assertIn(b'null',a.encode(dict(metric=None)))

    def test_f1_is_not_derived_from_mean_precision_recall(self):
        rows=[row(i,1,0,10,0) if i<8 else row(i,0,0,10,1) for i in range(16)]
        summaries=a.summarize(rows,('precision','recall','f1'),'PRIMARY');d={r['metric']:r for r in summaries}
        self.assertEqual(d['f1']['mean'],F(1,2));self.assertEqual(d['precision']['mean'],1)
        self.assertEqual(d['recall']['mean'],F(1,2));self.assertEqual(d['precision']['defined_n'],8)
        self.assertNotEqual(d['f1']['mean'],2*d['precision']['mean']*d['recall']['mean']/(d['precision']['mean']+d['recall']['mean']))

    def test_frozen_ratio_reconciliation_rejects_wrong_value(self):
        good=row(1,1,2,3,4);self.assertEqual(a.exact_metric(good,'precision'),F(1,3))
        good['precision']='0'
        with self.assertRaises(ValueError):a.exact_metric(good,'precision')

    def test_paired_complete_cases_and_delay_selection(self):
        c=[row(1,1,0,1,0),row(2,0,0,1,0)];p=[row(1,0,0,1,1,'P'),row(2,1,0,1,0,'P')]
        post=[dict(seed=i,scenario=s,method='zscore',feature=a.FEATURES[0],post_event_positive_decisions=0,
                   post_event_eligible_windows=1,post_event_alarm_rate='0') for i in (1,2) for s in 'CP']
        events=[dict(seed=i,scenario=s,method='zscore',feature=a.FEATURES[0],event_detected=not(i==2 and s=='C'),
                     detection_delay_seconds=None if i==2 and s=='C' else ('2' if s=='C' else '5')) for i in (1,2) for s in 'CP']
        diffs,delays,summaries=a.paired_results(dict(window_metrics_per_run=c+p,post_event_metrics_per_run=post,event_metrics_per_run=events))
        recall=[r for r in diffs if r['metric']=='recall']
        self.assertEqual([r['p_minus_c'] for r in recall],[F(-1),None])
        self.assertEqual([r['p_minus_c'] for r in delays],[F(3),None])
        self.assertEqual(delays[1]['selection'],'DETECTED_IN_BOTH_SCENARIOS')
        summary=next(r for r in summaries if r['metric']=='recall')
        self.assertEqual((summary['defined_n'],summary['undefined_n']),(1,1))

    def test_analysis_guard_rejects_pipeline_calls(self):
        for module in ('analysis.detection.detectors.cusum','analysis.detection.empirical','experiments.stage15b_evaluation'):
            scope={'__name__':module};exec('def forbidden(): return 1',scope)
            with self.assertRaises(ValueError):
                with a.analysis_only():scope['forbidden']()

    def test_wrong_hash_is_stop(self):
        with self.assertRaises(ValueError):a.checked(dict(path='experiments/protocols/stage14_test_evaluation_protocol_v1.json',sha256='0'*64))


class FrozenStage15CIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with a.analysis_only():
            cls.bundle=a.preflight();cls.tables,cls.meta=a.build_tables(cls.bundle)

    def test_cardinality_pairing_and_entry29(self):
        t=self.tables
        self.assertEqual(len(t['primary_per_run']),960);self.assertEqual(len(t['startup_per_run']),960)
        self.assertEqual(len(t['event_per_run']),640);self.assertEqual(len(t['post_event_per_run']),640)
        self.assertEqual(len(self.bundle['seeds']),16)
        self.assertEqual(len([r for r in t['primary_per_run'] if r['campaign_entry']==29]),20)
        self.assertEqual(self.meta['example_seed'],min(self.bundle['seeds']))

    def test_all_frozen_summaries_reconciled(self):
        self.assertEqual(len(self.tables['reconciliation']),560)
        self.assertTrue(all(r['all_five_statistics_identical'] for r in self.tables['reconciliation']))
        self.assertTrue(all(r['recall'] is None for r in self.tables['primary_per_run'] if r['scenario']=='B'))

    def test_complete_pairs_and_delay_misses(self):
        self.assertEqual(len(self.tables['paired_p_minus_c']),1280)
        self.assertEqual(len(self.tables['paired_delay_detected_both']),320)
        for r in self.tables['paired_p_minus_c']:
            self.assertEqual(r['complete_pair'],r['c_value'] is not None and r['p_value'] is not None)
            self.assertIsNone(r['p_minus_c']) if not r['complete_pair'] else self.assertEqual(r['p_minus_c'],r['p_value']-r['c_value'])
        for r in self.tables['paired_delay_detected_both']:
            if not r['complete_pair']:self.assertIsNone(r['p_minus_c'])

    def test_persistence_has_original_support_and_observation_evidence(self):
        self.assertEqual(len(self.tables['persistence_per_run']),640)
        for r in self.tables['persistence_per_run']:
            self.assertLessEqual(r['post_positive_observation_at_or_below_baseline_mean_n'],r['post_positive_n'])
            self.assertEqual(r['post_positive_n'],r['post_positive_with_observation_n'])
        self.assertEqual(len(self.tables['temporal_example']),3*4*5*144)
        lookup={(r['seed'],r['scenario'],r['method'],r['feature']):r for r in self.tables['primary_per_run']}
        for r in self.tables['post_event_per_run']:
            w=lookup[r['seed'],r['scenario'],r['method'],r['feature']]
            self.assertEqual(w['FP'],r['post_event_positive_decisions'])
            self.assertEqual(w['eligible_benign_windows'],r['post_event_eligible_windows'])
            self.assertEqual(w['fpr'],r['post_event_alarm_rate'])

    def test_tables_deterministic_without_scientific_reexecution(self):
        with a.analysis_only():other,meta=a.build_tables(self.bundle)
        self.assertEqual(a.encode(other),a.encode(self.tables));self.assertEqual(meta,self.meta)


if __name__=='__main__':unittest.main()
