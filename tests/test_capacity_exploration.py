from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from experiments.capacity_exploration import Guard,Tail,GIB,validate_capacity_config
from experiments.capacity_analysis import interval_sweep,request_phases,describe
from simulator.experiment_config import ExperimentConfig


class CapacityHelperTests(unittest.TestCase):
    def snapshot(self,**kwargs):
        value=dict(available_bytes=8*GIB,disk_free_bytes=7*GIB,host_busy_percent=10,
            containers=[],pending={},completed_observed=0,failed_observed=0)
        value.update(kwargs);return value

    def test_resource_guards_and_healthy_snapshot(self):
        self.assertEqual(Guard().evaluate(self.snapshot()),[])
        for fields in [dict(available_bytes=GIB),dict(disk_free_bytes=3*GIB),
                       dict(containers=[dict(id='owned',role='source',memory_usage_bytes=GIB)]),
                       dict(completed_observed=50,failed_observed=6),dict(diagnostic_errors=['writer']),
                       dict(run_bytes=600*1024**2)]:
            with self.subTest(fields=fields):self.assertTrue(Guard().evaluate(self.snapshot(**fields)))

    def test_high_cpu_requires_five_observations_and_resets(self):
        guard=Guard()
        for _ in range(4):self.assertFalse(guard.evaluate(self.snapshot(host_busy_percent=90)))
        self.assertTrue(guard.evaluate(self.snapshot(host_busy_percent=90)))
        self.assertFalse(guard.evaluate(self.snapshot(host_busy_percent=10)))

    def test_pending_is_observed_difference_and_needs_three_samples(self):
        guard=Guard()
        for _ in range(2):self.assertFalse(guard.evaluate(self.snapshot(pending={'normal_1':257})))
        self.assertTrue(guard.evaluate(self.snapshot(pending={'normal_1':257})))
        self.assertFalse(guard.evaluate(self.snapshot(pending={'normal_1':0})))

    def test_small_failure_sample_does_not_trigger_ratio_guard(self):
        self.assertEqual(Guard().evaluate(self.snapshot(completed_observed=49,failed_observed=6)),[])

    def test_bounded_tail_preserves_partial_line_and_detects_truncation(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'observed.jsonl';tail=Tail(p);self.assertEqual(tail.lines(),[])
            p.write_text('one\ntw');self.assertEqual(tail.lines(),['one'])
            with p.open('a') as stream:stream.write('o\nthree\n')
            self.assertEqual(tail.lines(),['two','three'])
            p.write_text('x')
            with self.assertRaisesRegex(RuntimeError,'truncated'):tail.lines()

    def test_half_open_worker_intervals_and_clipping(self):
        r=interval_sweep([(-1,.5),(0,1),(1,2),(2,3)],0,2)
        self.assertEqual(r['peak'],2);self.assertEqual(r['mean_occupancy'],1.25)
        self.assertEqual(interval_sweep([(0,1),(1,2)],0,2)['peak'],1)
        with self.assertRaises(ValueError):interval_sweep([(1,0)],0,2)

    def test_generation_and_drain_do_not_share_rate_denominator(self):
        requests=[dict(elapsed_seconds='0',end_elapsed_seconds='1'),
                  dict(elapsed_seconds='1.9',end_elapsed_seconds='2.2'),
                  dict(elapsed_seconds='2',end_elapsed_seconds='2.3'),
                  dict(elapsed_seconds='1.5',end_elapsed_seconds='')]
        r=request_phases(requests,2)
        self.assertEqual(r['starts_in_plan'],3);self.assertEqual(r['starts_tail'],1)
        self.assertEqual(r['completions_in_plan'],1);self.assertEqual(r['completions_tail'],2)
        self.assertEqual(r['cohort_completed_after_plan'],1);self.assertEqual(r['unfinished'],1)
        self.assertEqual(r['started_rps'],1.5);self.assertEqual(r['completed_rps_in_plan'],.5)

    def test_missing_descriptive_values_are_null(self):
        r=describe([]);self.assertIsNone(r['mean']);self.assertIsNone(r['sample_sd'])

    def test_preregistered_envelope_rejects_accidental_scope_expansion(self):
        c=ExperimentConfig.from_dict(dict(duration_seconds=12,topology={'mode':'direct'},traffic_sources={'execution':'containers'},
            infrastructure={'initial_instances':1,'min_instances':1,'max_instances':1},autoscaler={'enabled':False},
            normal_traffic={'clients':2,'rate':4,'endpoint':'/medium'},attack={'enabled':False,'attackers':0}))
        validate_capacity_config(c)
        for bad in [replace(c,normal_traffic=replace(c.normal_traffic,rate=65)),
                    replace(c,normal_traffic=replace(c.normal_traffic,endpoint='/expensive')),
                    replace(c,normal_traffic=replace(c.normal_traffic,work_units=0)),
                    replace(c,normal_traffic=replace(c.normal_traffic,max_concurrent_sends=4)),
                    replace(c,duration_seconds=21)]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):validate_capacity_config(bad)
