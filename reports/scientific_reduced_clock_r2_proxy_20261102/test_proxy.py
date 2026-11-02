"""Verificações dirigidas do parser, fases e ausências; sem runtime experimental."""
import importlib.util
import os
from pathlib import Path
import unittest
os.environ.setdefault('MPLCONFIGDIR','/tmp/clock-r2-matplotlib')
os.environ.setdefault('XDG_CACHE_HOME','/tmp/clock-r2-cache')
import numpy as np
import matplotlib.pyplot as plt

spec=importlib.util.spec_from_file_location('proxy_presentation',Path(__file__).with_name('generate.py'))
g=importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


class ProxyPresentationTests(unittest.TestCase):
    def test_scalar_times_preserve_zero_and_reject_lists(self):
        cases=[(None,'missing'),('','missing'),('-','marker_no_value'),('0.1, 0.2','multiple_upstreams'),
            ('0.1 : 0.2','multiple_upstreams'),('oops','malformed'),('-0.1','negative'),
            ('NaN','nonfinite'),('Infinity','nonfinite')]
        for raw,reason in cases:
            with self.subTest(raw=raw):
                self.assertEqual(g.scalar_time(raw),(None,reason))
        self.assertEqual(g.scalar_time('0.000'),(0.,'valid'))
        self.assertEqual(g.scalar_time('0.125'),(.125,'valid'))

    def test_phase_boundaries_are_half_open_and_use_real_end(self):
        phases=dict(PRE=(30.,150.),ACTIVE=(150.,240.568891248),POST=(240.568891248,390.))
        for t,phase in [(29.999,None),(30.,'PRE'),(149.999,'PRE'),(150.,'ACTIVE'),
                        (240.568891247,'ACTIVE'),(240.568891248,'POST'),(390.,None),(None,None)]:
            self.assertEqual(g.phase_for(t,phases),phase)
        # C16 operational boundary is not an offensive event.
        self.assertEqual(g.phase_for(270.,dict(PRE=(30.,150.),ACTIVE=(150.,270.),POST=(270.,390.))),'POST')

    def test_epoch_anchor_alignment_retains_pre_origin(self):
        epoch=g.Decimal('1793327819.719817')
        self.assertAlmostEqual(g.log_elapsed('1793327970.720',epoch),151.000183)
        self.assertLess(g.log_elapsed('1793327814.206',epoch),0)
        self.assertIsNone(g.log_elapsed('-',epoch))

    def test_resource_units_and_sample_mean(self):
        self.assertEqual(1048576/g.MIB,1.)
        self.assertEqual(g.mean([None,1.,3.]),2.)
        self.assertIsNone(g.mean([None]))

    def test_no_line_through_missing_read_or_large_spacing(self):
        fig,ax=plt.subplots()
        gaps=g.native_line(ax,[30.,31.,32.,35.],[1.,None,2.,3.],color='black')
        values=ax.lines[0].get_ydata()
        self.assertTrue(np.isnan(values[1]))
        self.assertTrue(np.isnan(values[3]))
        self.assertEqual(gaps,[(32.,35.)])
        plt.close(fig)

    def test_coverage_is_point_support_not_continuous_observation(self):
        r=g.support([30.05,31.05,34.05],30.,35.)
        self.assertEqual(r['n'],3)
        self.assertEqual(r['occupied_bins_1s'],3)
        self.assertEqual(r['empty_bins_1s'],2)
        self.assertAlmostEqual(r['max_gap_including_edges_seconds'],3.)
        self.assertEqual(g.support([],30.,35.)['max_gap_including_edges_seconds'],5.)


if __name__=='__main__':
    unittest.main()
