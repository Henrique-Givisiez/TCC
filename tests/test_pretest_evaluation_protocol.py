"""Administrative manifest checks only; no TEST observations or preflights."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path, PurePosixPath
import unittest

from analysis.detection.horizons import EvaluationSelection


ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'experiments/protocols/stage14_test_evaluation_protocol_v1.json'
FEATURES={'ingress_packet_count','ingress_tcp_payload_length_sum_bytes',
          'request_starts','mean_duration_ms','mean_cpu_percent'}


class PretestEvaluationProtocolTests(unittest.TestCase):
    def setUp(self):
        def unique(items):
            result={}
            for key,value in items:
                if key in result:raise ValueError('Duplicate JSON key')
                result[key]=value
            return result
        def reject(value):raise ValueError('Nonfinite JSON value')
        self.p=json.loads(PATH.read_text(),object_pairs_hook=unique,parse_constant=reject)

    def test_version_status_and_non_circular_approval_authority(self):
        p=self.p
        self.assertEqual((p['schema_version'],p['version'],p['status']),(1,1,'FROZEN'))
        self.assertEqual(p['authority_head'],'b0b025b3edbc6d981d6cff9929fa3b256ebaf00a')
        self.assertTrue(p['finalization']['no_self_commit_hash'])
        self.assertTrue(p['finalization']['post_commit_sidecar_pins_new_HEAD_and_manifest_SHA'])
        self.assertEqual(p['four_method_freeze']['sha256'],'898e79394ac48a86a734100d324d0b6b966412166a0eac105dbdeccb2bd236f5')

    def test_original_design_references_and_paired_seed_plan(self):
        p=self.p
        for key in ['protocol_v2','seed_plan','matrix']:
            reference=p[key]
            self.assertEqual(hashlib.sha256((ROOT/reference['path']).read_bytes()).hexdigest(),reference['sha256'])
        seedplan=json.loads((ROOT/p['seed_plan']['path']).read_text())
        paired=p['paired_design']
        self.assertEqual(paired['seeds'],seedplan['partitions']['test'])
        self.assertEqual((len(paired['seeds']),len(set(paired['seeds']))),(16,16))
        self.assertEqual(paired['scenarios'],['B','C','P'])
        self.assertEqual(paired['total_entries'],48)
        self.assertEqual(p['experimental_unit'],'run/seed')
        self.assertFalse(p['windows_are_independent_replicates'])

    def test_exactly_twenty_fixed_primary_configurations(self):
        p=self.p;configs=p['primary_configurations']
        self.assertEqual(len(configs),20);self.assertEqual(len({c['id'] for c in configs}),20)
        self.assertEqual({(c['method'],c['feature']) for c in configs},
                         {(m,f) for m in ['zscore','cov','ewma','cusum'] for f in FEATURES})
        for c in configs:
            self.assertEqual(c['alpha'],'0.01')
            self.assertEqual(c['parameters'],{'lookback':6} if c['method']=='cov' else {'lambda':'0.2'} if c['method']=='ewma' else {'k':'0.5'} if c['method']=='cusum' else {})
            self.assertTrue(Decimal(c['threshold']['value']).is_finite())
            ref=c['threshold']['artifact'];path=PurePosixPath(ref['path'])
            self.assertFalse(path.is_absolute());self.assertNotIn('..',path.parts)
            self.assertRegex(ref['sha256'],r'^[0-9a-f]{64}$')
        self.assertEqual(set(p['frozen_baseline_models']),FEATURES)

    def test_evaluation_regions_match_existing_selection_contract(self):
        h=self.p['horizons']
        self.assertEqual(h['observation_scoring'],[0,144])
        self.assertEqual(h['primary_evaluation'],list(EvaluationSelection('primary').bounds()))
        self.assertEqual(h['startup_diagnostic'],list(EvaluationSelection('startup_diagnostic').bounds()))
        self.assertEqual(h['inclusion'],'whole_windows_contained_in_half_open_interval')
        self.assertTrue(h['selection_after_scoring_and_decisions']);self.assertFalse(h['reset_at_48'])
        self.assertEqual(h['nominal_candidate_windows_per_primary_run'],96)
        self.assertTrue(h['original_protocol_v2_unchanged'])

    def test_pure_binary_boundaries_and_undefined_rules(self):
        truth=self.p['window_ground_truth']
        self.assertEqual((truth['benign'],truth['attack'],truth['boundary']),('overlap == 0','overlap == 1','0 < overlap < 1'))
        self.assertTrue(truth['boundary_excluded_from_primary_binary_metrics']);self.assertFalse(truth['round_overlap'])
        self.assertTrue(truth['preserve_continuous_overlap'])
        self.assertEqual(self.p['scenario_CP']['F1'],'2*TP/(2*TP+FP+FN)')
        self.assertEqual(self.p['undefined_metrics']['zero_denominator'],'null/undefined; never invent zero')
        self.assertEqual(self.p['undefined_metrics']['sample_standard_deviation_ddof'],1)

    def test_events_keep_effective_time_and_periodic_global_semantics(self):
        event=self.p['event_level']
        self.assertEqual(event['policy'],'global_observation_overlap_decision_availability_v2')
        self.assertFalse(event['availability_used_for_overlap_eligibility'])
        self.assertFalse(event['require_available_at_before_or_at_actual_end'])
        self.assertFalse(event['drained_end_as_attacker_endpoint']);self.assertIsNone(event['miss_delay'])
        self.assertTrue(event['event_not_clipped_to_primary_horizon'])
        self.assertFalse(self.p['periodic']['bursts_are_independent_primary_events'])
        self.assertEqual(self.p['post_event']['interval'],'[max(E.actual_end,48),144)')
        self.assertFalse(self.p['post_event']['threshold_or_reset_policy_change'])

    def test_run_seed_summaries_are_primary_and_pooled_complementary(self):
        s=self.p['between_seed_statistics']
        self.assertEqual(s['unit'],'run/seed');self.assertEqual(s['number_of_seeds_per_scenario'],16)
        self.assertTrue(s['paired_BCP_identity_preserved']);self.assertFalse(s['pooled_metrics_primary'])
        self.assertFalse(s['consecutive_windows_independent']);self.assertFalse(s['hypothesis_tests_implemented_this_step'])
        self.assertFalse(self.p['method_comparison']['global_weighted_ranking'])

    def test_no_leakage_sensitivity_substitution_or_test_release(self):
        p=self.p
        self.assertTrue(all(value is False for value in p['anti_leakage'].values()))
        self.assertFalse(p['sensitivity']['may_replace_primary_after_TEST'])
        self.assertEqual(p['sensitivity']['alpha'],['0.005','0.02'])
        self.assertEqual(p['sensitivity']['CoV_lookback'],[3,12])
        self.assertEqual(p['test_execution'],'LOCKED');self.assertFalse(p['TEST_release'])
        self.assertFalse(p['preflight_contract']['execution_authorized'])
        self.assertFalse(p['preflight_contract']['observed_data_access'])
        self.assertFalse(p['campaign_runner_implemented_this_step'])


if __name__=='__main__':unittest.main()
