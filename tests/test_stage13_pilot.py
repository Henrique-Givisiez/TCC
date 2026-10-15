"""Pilot design and descriptive accounting tests; never execute the simulator."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from simulator.experiment_config import ExperimentConfig
from pilot_stage13.run import configuration,ORDERS
from pilot_stage13.analyze import quantile,describe,phase,block


class PilotDesignTests(unittest.TestCase):
    def test_curated_design_only_changes_intended_factors(self):
        for seed in ORDERS:
            configs=[]
            for scenario in 'BCP':
                c=configuration(seed,scenario);ExperimentConfig.from_dict(c)
                self.assertEqual(c['normal_traffic']['endpoint'],c['attack']['endpoint'])
                self.assertEqual(c['duration_seconds'],84)
                self.assertEqual(c['attack']['start_seconds'],24)
                self.assertEqual(c['attack']['duration_seconds'],36)
                c.pop('id');c['attack'].pop('enabled');c['attack'].pop('profile');c['attack'].pop('burst')
                configs.append(c)
            self.assertEqual(configs[0],configs[1]);self.assertEqual(configs[1],configs[2])

    def test_five_distinct_seeds_all_three_scenarios(self):
        self.assertEqual(len(ORDERS),5);self.assertNotIn(42,ORDERS)
        for order in ORDERS.values():self.assertEqual(set(order),set('BCP'))

    def test_quantiles_and_sample_spread(self):
        self.assertEqual(quantile([0,10],.25),2.5)
        d=describe([1,2,3,None]);self.assertEqual(d['n'],3)
        self.assertEqual(d['mean'],2);self.assertEqual(d['sd'],1)
        self.assertEqual(d['descriptive_relative_sd'],.5)
        self.assertIsNone(describe([0,0])['descriptive_relative_sd'])
        self.assertIsNone(describe([1])['sd'])

    def test_replay_refused_before_touching_cost_or_environment(self):
        from pilot_stage13.run import require_fresh_outputs
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with patch('pilot_stage13.run.OUT',root):
                require_fresh_outputs(101,'B')
                p=root/'cost/101/B.json';p.parent.mkdir(parents=True);p.write_text('original')
                with self.assertRaises(FileExistsError):require_fresh_outputs(101,'B')
                self.assertEqual(p.read_text(),'original')

    def test_regions_do_not_drop_tail_or_relabel_boundaries(self):
        self.assertEqual([phase(t) for t in [0,23,24,59,60,83,84]],
                         ['PRE','PRE','EVENT_POSITION','EVENT_POSITION','POST','POST','TAIL'])
        self.assertEqual(block(12),'PRE_LATE');self.assertEqual(block(72),'POST_LATE')


if __name__=='__main__':unittest.main()
