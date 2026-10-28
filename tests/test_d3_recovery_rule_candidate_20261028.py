"""Synthetic validation of an unreleased proposal; never reads pilot observations."""
import unittest
from analysis.d3_recovery_rule_candidate_20261028 import (synthetic_cases,trace,make_reference,
    measure,Request,Opportunity,evaluate)


class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases=synthetic_cases()

    def test_benign_arrival_variation_not_confused_with_service_loss(self):
        r=self.cases['benign_arrival_variation']
        self.assertTrue(all(w['qualified'] for w in r['windows']))
        self.assertEqual(r['state'],'post_compatible_no_prior_impairment')
        self.assertIsNone(r['recovery_confirmed_by'])
        self.assertFalse(r['loss_of_qualification_after_confirmation'])
        self.assertLess(r['windows'][0]['measurements']['terminal_2xx_rps']/r['windows'][1]['measurements']['terminal_2xx_rps'],.9)

    def test_small_certification_delay_clips_exposure_without_changing_grid(self):
        w=self.cases['benign_arrival_variation']['windows'][0]
        self.assertEqual(w['nominal_interval'],[270,300])
        self.assertEqual(w['effective_interval'],[270.0015,300])
        self.assertGreater(w['coverage'],.999)
        self.assertTrue(w['qualified'])
        self.assertAlmostEqual(w['measurements']['start_rps'],440/29.9985)

    def test_persistent_degradation_never_confirms_recovery(self):
        r=self.cases['persistent_degradation']
        self.assertTrue(all(w['state']=='service_impaired' for w in r['windows']))
        self.assertTrue(r['right_censored'])
        self.assertEqual(r['censor_at'],390)
        self.assertIsNone(r['recovery_confirmed_by'])

    def test_real_recovery_requires_two_qualified_windows(self):
        r=self.cases['real_recovery']
        self.assertEqual([w['qualified'] for w in r['windows']],[False,True,True,True])
        self.assertEqual(r['recovery_confirmed_by'],360)
        self.assertTrue(r['prior_impairment_verified_from_synthetic_active'])
        self.assertLess(r['active_metrics']['success_fraction'],.99)
        self.assertTrue(r['last_two_qualified'])
        self.assertFalse(r['right_censored'])

    def test_missing_offer_evidence_does_not_prove_planned_load_recovery(self):
        r=self.cases['unknown_real_offer']
        self.assertTrue(all(w['state']=='arrival_unknown_or_inadequate' for w in r['windows']))
        self.assertTrue(all(all(w['service_checks'].values()) for w in r['windows']))
        self.assertIsNone(r['first_post_compatibility_confirmed_by'])

    def test_under_generation_is_reported_separately(self):
        r=self.cases['generator_shortfall']
        self.assertTrue(all(not w['arrival']['adequate'] for w in r['windows']))
        self.assertTrue(all(all(w['service_checks'].values()) for w in r['windows']))
        self.assertTrue(all(w['measurements']['starts']==240 for w in r['windows']))

    def test_old_pending_prevents_false_recovery(self):
        r=self.cases['old_pending_despite_new_success']
        self.assertTrue(all(w['measurements']['success_fraction']==1 for w in r['windows']))
        self.assertTrue(all(not w['service_checks']['no_aged_pending'] for w in r['windows']))
        self.assertIsNone(r['recovery_confirmed_by'])

    def test_collection_failure_is_not_service_censoring(self):
        r=self.cases['collection_failure']
        self.assertEqual(r['state'],'unassessable_collection_or_emission')
        self.assertFalse(r['right_censored'])

    def test_large_delay_keeps_short_window_unqualified_and_no_merging(self):
        r=self.cases['large_certification_delay']
        self.assertEqual(r['windows'][0]['effective_interval'],[272,300])
        self.assertLess(r['windows'][0]['coverage'],.95)
        self.assertFalse(r['windows'][0]['qualified'])
        self.assertEqual(r['windows'][1]['effective_interval'],[300,330])

    def test_cross_boundary_ends_preserve_conservation(self):
        requests=[Request(269,271),Request(280,310),Request(300,301),Request(285,None)]
        m=measure(requests,270,300,cutoff=420)
        self.assertEqual((m['starts'],m['terminal_ends'],m['pending_at_start'],m['pending_at_end']),(2,1,1,2))
        self.assertEqual(m['pending_change'],m['starts']-m['terminal_ends'])

    def test_future_completion_cannot_hide_deadline_miss(self):
        records=trace(270,300,480,duration=50)
        m=measure(records,270,300,cutoff=420)
        self.assertEqual(m['success_fraction'],0)
        self.assertEqual(m['failure_or_deadline_miss_fraction'],1)

    def test_complete_cohort_needs_no_fabricated_extra_observation(self):
        records=trace(360,390,480)
        m=measure(records,360,390,cutoff=390.1)
        self.assertTrue(m['cohort_mature'])
        self.assertEqual(m['success_fraction'],1)
        records.append(Request(389,400))
        m=measure(records,360,390,cutoff=390.1)
        self.assertFalse(m['cohort_mature'])
        m=measure(records,360,390,cutoff=393)
        self.assertTrue(m['cohort_mature'])
        self.assertLess(m['success_fraction'],1)

    def test_offensive_pending_is_not_mislabeled_legitimate_service_impairment(self):
        pre=trace(30,150,1920); ctrl=trace(30,390,5760)
        refs=[make_reference(pre,30,150,cutoff=420),make_reference(ctrl,30,390,cutoff=420)]
        requests=pre+[r for i in range(4) for r in trace(270+i*30,300+i*30,480)]
        offers=[Opportunity(r.start-.001,r.origin) for r in requests]
        r=evaluate(requests,offers,refs,emission_end=270,attack_requests=[Request(260,None)])
        self.assertTrue(all(w['state']=='offensive_client_drain_pending' for w in r['windows']))
        self.assertFalse(any(w['qualified'] for w in r['windows']))

    def test_no_synthetic_case_authorizes_a_run(self):
        self.assertTrue(all(not r['progression_eligible'] for r in self.cases.values()))


if __name__=='__main__':
    unittest.main()
