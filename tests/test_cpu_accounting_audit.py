"""Deterministic audit of current CPU semantics; no Docker daemon or load."""
from collections import deque
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, mock_open, patch

import docker
from simulator import host_stats
from simulator.stats_collector import StatsCollector
from simulator.proxy_monitor import resources as proxy_resources


def payload(cpu=2_400_000_000, system=4_000_000_000, n=4):
    return dict(read='same-read', preread='previous-read',
        cpu_stats=dict(cpu_usage=dict(total_usage=cpu),system_cpu_usage=system,online_cpus=n),
        precpu_stats=dict(cpu_usage=dict(total_usage=0),system_cpu_usage=0))


class Clock:
    def __init__(self):self.now=100
    def monotonic(self):return self.now


class StopAfterSweeps:
    def __init__(self,clock,sweeps=1):self.clock,self.remaining=clock,sweeps
    def is_set(self):return self.remaining==0
    def wait(self,seconds):
        self.clock.now+=seconds
        self.remaining-=1


class CPUAccountingAuditTests(unittest.TestCase):
    def collector(self, ids=('A','B')):
        collector=StatsCollector(MagicMock(),poll_interval=1,history_seconds=30)
        collector.update_containers(list(ids))
        return collector

    def history(self,collector,identity,values):
        collector._history[identity]=deque((t,cpu,0,identity) for t,cpu in values)
        if values:
            collector._cache[identity]=dict(cpu_percent=values[-1][1],mem_app_mb=0,name=identity,read_ts='old')

    def test_docker_core_convention_exceeds_100_and_interval_scaling(self):
        # 2.4 CPU-seconds used in a 1 wall-second interval on 4 logical CPUs.
        self.assertEqual(StatsCollector._calc_cpu_percent(payload()),240)
        # Same rate over 4 wall-seconds, with all aggregate counters scaled.
        self.assertEqual(StatsCollector._calc_cpu_percent(payload(9_600_000_000,16_000_000_000)),240)
        # online_cpus is the host multiplier; not a per-container quota.
        p=payload();p['cpu_stats']['cpu_usage']['percpu_usage']=[0]*2
        self.assertEqual(StatsCollector._calc_cpu_percent(p),240)
        p['cpu_stats']['online_cpus']=0
        self.assertEqual(StatsCollector._calc_cpu_percent(p),120)
        p['cpu_stats']['cpu_usage'].pop('percpu_usage')
        self.assertEqual(StatsCollector._calc_cpu_percent(p),60)  # fallback 1

    def test_first_collector_read_is_not_forced_to_zero(self):
        self.assertEqual(StatsCollector._calc_cpu_percent(payload()),240)
        first=payload(1_000_000_000,8_000_000_000,n=8)
        first.pop('precpu_stats')
        self.assertEqual(StatsCollector._calc_cpu_percent(first),100)  # missing previous defaults to 0
        self.assertIsNone(proxy_resources(first)['cpu_percent'])  # proxy first-read convention differs

    def test_invalid_delta_and_empty_stats_are_reported_as_zero(self):
        for cpu,system in [(0,10),(-1,10),(1,0),(1,-1)]:
            self.assertEqual(StatsCollector._calc_cpu_percent(payload(cpu,system)),0)
        reset=payload(100,1000)
        reset['precpu_stats']['cpu_usage']['total_usage']=200  # positive counters, negative delta
        self.assertEqual(StatsCollector._calc_cpu_percent(reset),0)
        metrics=StatsCollector._compute_metrics(SimpleNamespace(id='A',name='A'),{})
        self.assertIsNone(metrics['cpu_percent'])  # CPU now belongs to explicit successive-read delta
        self.assertIsNone(metrics['read_ts'])
        bad=payload();bad['cpu_stats']['cpu_usage']['total_usage']=None
        self.assertIsNone(StatsCollector._compute_metrics(SimpleNamespace(id='A',name='A'),bad)['cpu_percent'])

    def test_two_victims_equal_samples_give_mean_not_total(self):
        c=self.collector();self.history(c,'A',[(9,100)]);self.history(c,'B',[(9,200)])
        with patch('simulator.stats_collector.time.monotonic',return_value=10):
            cpu,_,names=c.get_averages(2)
        self.assertEqual(cpu,150)
        self.assertEqual(set(names),{'A','B'})
        self.assertEqual(cpu*2,300)  # total core-equivalent percent only in this aligned equal-support case

    def test_sample_count_weights_differ_from_equal_victim_and_time_weights(self):
        c=self.collector();self.history(c,'A',[(7,20),(10,40)]);self.history(c,'B',[(10,100)])
        with patch('simulator.stats_collector.time.monotonic',return_value=10):
            pooled=c.get_averages(4)[0]
        self.assertAlmostEqual(pooled,160/3)
        per_victim=(30+100)/2
        # A's two rates cover [6,7) and [7,10); B covers [6,10).
        time_and_victim=((20*1+40*3)/4+100)/2
        self.assertEqual(per_victim,65)
        self.assertEqual(time_and_victim,67.5)
        self.assertNotEqual(pooled,per_victim)
        self.assertNotEqual(pooled,time_and_victim)
        self.assertEqual(c.get_averages()[0],70)  # snapshot = last A40 and B100

    def test_stale_fallback_missing_victim_and_empty_population(self):
        c=self.collector();self.history(c,'A',[(9,40)]);self.history(c,'B',[(1,160)])
        with patch('simulator.stats_collector.time.monotonic',return_value=10):
            self.assertEqual(c.get_averages(2)[0],100)  # B9 seconds old, still supported by name
            c._cache.pop('B');c._history.pop('B')
            cpu,_,names=c.get_averages(2)
            self.assertEqual(cpu,40);self.assertEqual(names,['A'])  # not (40+0)/2
            c._cache.clear();c._history.clear()
            self.assertEqual(c.get_averages(2),(0,0,[]))

    def test_window_left_boundary_inclusive_and_samples_can_be_reused(self):
        c=self.collector(('A',));self.history(c,'A',[(7.999,999),(8,20),(10,40)])
        with patch('simulator.stats_collector.time.monotonic',return_value=10):
            self.assertEqual(c.get_averages(2)[0],30)
            self.assertEqual(c.get_averages(2)[0],30)  # reads don't consume samples

    def test_membership_change_drops_old_history_and_new_member_is_not_zero(self):
        c=self.collector();self.history(c,'A',[(9,100)]);self.history(c,'B',[(9,300)])
        c.update_containers(['A','C'])
        self.assertNotIn('B',c._cache);self.assertNotIn('B',c._history)
        with patch('simulator.stats_collector.time.monotonic',return_value=10):
            self.assertEqual(c.get_averages(2)[0],100)
            self.history(c,'C',[(9.5,0)])
            self.assertEqual(c.get_averages(2)[0],50)

    def test_new_acquisition_does_not_refresh_duplicate_daemon_read(self):
        from tests.test_cpu_observations import row, replay
        a=row(1,'.98');b=row(2,'1.98');b['docker_read']=a['docker_read']
        observed=replay([a,b])
        self.assertEqual(observed[-1]['state'],'invalid_timestamp')
        self.assertFalse(observed[-1]['fresh']);self.assertIsNone(observed[-1]['cpu_percent'])

    def test_poll_error_retains_old_cache_notfound_discards_it(self):
        for exception,expected in [(RuntimeError('unavailable'),160),
                                   (docker.errors.NotFound('gone'),0)]:
            c=self.collector(('A',));self.history(c,'A',[(1,160)])
            c.client.containers.get.side_effect=exception
            clock=Clock()
            with patch('simulator.stats_collector.time.monotonic',clock.monotonic):
                observation,_,_=c._acquire('A',100,0)
                self.assertEqual(observation['state'],'acquisition_error')
                cpu,_,names=c.get_averages(1)
            self.assertEqual(cpu,expected)
            self.assertEqual(names,['A'] if expected else [])

    def test_new_contract_does_not_mix_generations_in_a_cpu_delta(self):
        from tests.test_cpu_observations import row, replay
        observed=replay([row(1,'.98'),row(2,'1.98',generation=dict(started_at='new',restarts=1))])
        self.assertEqual(observed[-1]['state'],'generation_changed')
        self.assertIsNone(observed[-1]['cpu_percent'])

    def test_adding_idle_victim_reduces_mean_without_reducing_total(self):
        c=self.collector(('A',));self.history(c,'A',[(9,200)])
        with patch('simulator.stats_collector.time.monotonic',return_value=10):
            before=c.get_averages(2)[0]
            c.update_containers(['A','B']);self.history(c,'B',[(9,0)])
            after=c.get_averages(2)[0]
        self.assertEqual((before,after),(200,100))
        self.assertEqual(before*1,after*2)  # same 2 core-equivalents, changed denominator

    def test_csv_rounds_but_autoscaler_uses_unrounded_input(self):
        import csv
        from pathlib import Path
        import tempfile
        from simulator import main_orchestrator as main
        from simulator.autoscaler_logic import Autoscaler
        from simulator.experiment_config import AutoscalerConfig, InfrastructureConfig
        gt=SimpleNamespace(run_id='run',clock=SimpleNamespace(sample=lambda:(100,1)),context=lambda elapsed:(0,[]))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'metrics.csv'
            with path.open('w',newline='') as stream:
                csv.DictWriter(stream,fieldnames=main.METRICS_FIELDS).writeheader()
            with patch.object(main.config,'METRICS_LOG_FILE',str(path)):
                main.log_metrics_to_csv(gt,1,60.004,0,0,'NO_ACTION',['A'],0)
            with path.open(newline='') as stream:row=next(csv.DictReader(stream))
        self.assertEqual(float(row['average_cpu_percent']),60)
        settings=AutoscalerConfig(enabled=True,scale_up_threshold=60)
        scaler=Autoscaler(settings,InfrastructureConfig(initial_instances=1,min_instances=1,max_instances=2))
        self.assertEqual(scaler.decide_scaling(60.004,1),'SCALE_UP')
        # Separate clean scaler so cooldown cannot explain the different decision.
        self.assertEqual(Autoscaler(settings,scaler.infrastructure).decide_scaling(60,1),'NO_ACTION')

    def test_host_normalization_empty_error_and_guest_double_counting(self):
        with patch.object(host_stats,'_prev_total',None),patch.object(host_stats,'_prev_idle',None), \
             patch.object(host_stats,'_read_cpu_jiffies',side_effect=[(100,50),(200,75),OSError('no proc')]):
            self.assertEqual(host_stats.get_host_cpu_percent(),0)
            self.assertEqual(host_stats.get_host_cpu_percent(),75)
            self.assertEqual(host_stats.get_host_cpu_percent(),0)
        # Linux guest time is already charged to user; summing guest again yields 2/3,
        # while distinct CPU times are user100 + idle100 => true busy fraction 1/2.
        with patch.object(host_stats,'_prev_total',0),patch.object(host_stats,'_prev_idle',0), \
             patch('builtins.open',mock_open(read_data='cpu 100 0 0 100 0 0 0 0 100 0\n')):
            self.assertAlmostEqual(host_stats.get_host_cpu_percent(),200/3)


if __name__=='__main__':unittest.main()
