"""Testes descritivos/alinhamento: não importam runtime experimental."""
import importlib.util
from pathlib import Path
import unittest
import numpy as np
spec=importlib.util.spec_from_file_location('memory_presentation',Path(__file__).with_name('generate.py'))
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)


class MemoryChecks(unittest.TestCase):
    def test_ranks_with_ties_and_no_inferential_output(self):
        self.assertTrue(np.array_equal(g.ranks([5,2,2,8]),[3.,1.5,1.5,4.]))
        rho,n,reason=g.correlation(range(12),range(11,-1,-1))
        self.assertAlmostEqual(rho,-1.);self.assertEqual(n,12);self.assertIsNone(reason)

    def test_constant_missing_and_short_support_remain_undefined(self):
        self.assertEqual(g.correlation(range(12),[0]*12),(None,12,'constant_variable'))
        self.assertEqual(g.correlation([1,2,None],[2,4,6]),(None,2,'insufficient_pairs'))

    def test_unique_bounded_monitor_log_match_without_reuse(self):
        used=set()
        self.assertEqual(g.paired_monitor_log(10.,.03,[10.02],used),(0,'unique'))
        self.assertEqual(g.paired_monitor_log(10.,.03,[10.02],used),(None,'already_matched'))
        self.assertEqual(g.paired_monitor_log(10.,.03,[10.5],set()),(None,'no_candidate'))
        self.assertEqual(g.paired_monitor_log(10.,.03,[10.01,10.02],set()),(None,'ambiguous'))

    def test_absence_is_not_zero_and_no_high_low_cut(self):
        q=g.quantiles([None,float('nan')]);self.assertEqual(q['n'],0);self.assertIsNone(q['mean'])
        q=g.quantiles([0,2]);self.assertEqual(q['n'],2);self.assertEqual(q['mean'],1.)
        self.assertNotIn('memory_threshold',g.RULES)
        self.assertEqual(g.RULES['log_window_seconds'],1.)
        self.assertEqual(g.RULES['status_max_distance_seconds'],.5)

    def test_memory_components_are_discovered_from_saved_keys(self):
        paths=g.memory_key_paths({'memory_stats':{'usage':123,'stats':{'rss':64,'cache':32}}})
        self.assertIn('.memory_stats',paths)
        self.assertIn('.memory_stats.stats.rss',paths)
        self.assertIn('.memory_stats.stats.cache',paths)
        self.assertEqual(4096/g.MIB,.00390625)


if __name__=='__main__':unittest.main()
