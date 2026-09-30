import json
from dataclasses import replace
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from simulator.experiment_config import ExperimentConfig, worker_seed, BurstConfig


class ConfigurationTests(unittest.TestCase):
    def test_default_and_roundtrip(self):
        default = ExperimentConfig.load('experiments/configs/default.json')
        self.assertEqual(default, ExperimentConfig())
        resolved = default.resolve_seed()
        self.assertIsInstance(resolved.seed, int)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'experiment.json'
            path.write_text(resolved.to_json())
            self.assertEqual(resolved, ExperimentConfig.load(path))

    def test_invalid(self):
        cases = [dict(duration_seconds=0), dict(seed=True), dict(seed=-1), dict(id=''),
                 dict(normal_traffic={'clients': -1}), dict(normal_traffic={'clients': 1.5}),
                 dict(attack={'rate': -1}), dict(attack={'start_seconds': 180}),
                 dict(attack={'duration_seconds': -1}), dict(attack={'duration_seconds': 200}),
                 dict(attack={'enabled': 'yes'}), dict(attack={'profile': 'ldos'}),
                 dict(attack={'burst': {'duration_seconds': -1}}),
                 dict(attack={'burst': {'period_seconds': 5}}),
                 dict(infrastructure={'initial_instances': 5}),
                 dict(autoscaler={'scale_up_threshold': 20}), dict(autoscaler={'cooldown_seconds': -1}),
                 dict(monitoring={'interval_seconds': 0}), dict(monitoring={'history_seconds': 1}),
                 dict(server={'process_pool_workers': 0}), dict(normal_traffic={'endpoint': 'http://other'}),
                 dict(duration_seconds=float('nan')), dict(unknown=1), dict(attack=None)]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                ExperimentConfig.from_dict(case)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'duplicate.json'
            path.write_text('{"seed": 1, "seed": 2}')
            with self.assertRaises(ValueError):
                ExperimentConfig.load(path)

    def test_seed_streams(self):
        seeds = [worker_seed(42, component, index) for component in ('normal', 'attack') for index in range(4)]
        self.assertEqual(len(set(seeds)), 8)
        a, b = random.Random(seeds[0]), random.Random(worker_seed(42, 'normal', 0))
        self.assertEqual([a.expovariate(10) for _ in range(20)], [b.expovariate(10) for _ in range(20)])

    def test_cli_without_docker(self):
        cmd = [sys.executable, '-m', 'simulator.main_orchestrator']
        result = subprocess.run(cmd + ['--config', 'experiments/configs/default.json', '--print-config'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsInstance(json.loads(result.stdout)['seed'], int)
        result = subprocess.run(cmd + ['--duration', '2', '--attack-duration', '0', '--normal-rps', '3', '--print-config'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        effective = json.loads(result.stdout)
        self.assertEqual(effective['normal_traffic']['rate'], 3)
        self.assertFalse(effective['attack']['enabled'])
        for flags in [['--config', 'experiments/configs/default.json', '--rps', '2'], ['--attack-duration', '-1']]:
            self.assertEqual(subprocess.run(cmd + flags, capture_output=True).returncode, 2)

    def test_component_propagation(self):
        from simulator import normal_traffic, traffic_injectorV0, autoscaler_logic, cost_calculator
        from simulator.stats_collector import StatsCollector
        configs = [ExperimentConfig(seed=7), ExperimentConfig.from_dict({
            'seed': 9, 'normal_traffic': {'rate': 3, 'clients': 2, 'work_units': 17, 'max_concurrent_sends': 3},
            'attack': {'rate': 4, 'attackers': 1, 'work_units': 91, 'max_concurrent_sends': 2},
            'server': {'process_pool_workers': 3, 'default_work_units': 123, 'default_sleep_seconds': .1},
            'autoscaler': {'enabled': False}, 'monitoring': {'stats_poll_interval_seconds': 2, 'history_seconds': 40}})]
        with patch('docker.from_env') as from_env:
            from simulator import docker_manager
            for c in configs:
                normal_traffic.configure(c.normal_traffic, c.seed)
                traffic_injectorV0.configure(c.attack, c.seed)
                self.assertEqual(normal_traffic._settings, c.normal_traffic)
                self.assertEqual(normal_traffic._send_pool._max_workers, c.normal_traffic.max_concurrent_sends)
                self.assertEqual(traffic_injectorV0._send_pool._max_workers, c.attack.max_concurrent_sends)
                session = MagicMock()
                normal_traffic._send_one_normal(session, 'http://test', {'ok': 0, 'err': 0}, normal_traffic.rtt_lock)
                self.assertEqual(session.get.call_args.kwargs['timeout'], c.normal_traffic.request_timeout_seconds)
                ac = autoscaler_logic.Autoscaler(c.autoscaler, c.infrastructure)
                self.assertEqual(ac.decide_scaling(90, 1), 'SCALE_UP' if c.autoscaler.enabled else 'NO_ACTION')
                collector = StatsCollector(from_env.return_value, c.monitoring.stats_poll_interval_seconds, c.monitoring.history_seconds)
                self.assertEqual(collector.poll_interval, c.monitoring.stats_poll_interval_seconds)
                with patch.object(docker_manager, 'client') as client, patch('simulator.docker_manager.time.sleep'):
                    import docker
                    client.containers.get.side_effect = docker.errors.NotFound('missing')
                    docker_manager.start_instance(1, c.server)
                    env = client.containers.run.call_args.kwargs['environment']
                    self.assertEqual(env['INSTANCE_MAX_CONCURRENT_REQUESTS'], str(c.server.process_pool_workers))
                    self.assertEqual(env['WORK_UNITS'], str(c.server.default_work_units))
                self.assertEqual(cost_calculator.calculate_total_cost_from_intervals([(2, 3600)], .5), 1)
        normal_traffic._send_pool.shutdown()
        traffic_injectorV0._send_pool.shutdown()

    def test_zero_rate_starters_send_no_requests(self):
        from simulator import normal_traffic, traffic_injectorV0
        for module, starter, active in [
            (normal_traffic, normal_traffic.start_http_traffic, 'traffic_active'),
            (traffic_injectorV0, traffic_injectorV0.start_http_flood, 'attack_active')]:
            with self.subTest(component=module.__name__), \
                 patch.object(module, active, False), \
                 patch.object(module, '_send_pool') as pool, \
                 patch.object(module.threading, 'Thread') as thread, \
                 patch.object(module.requests, 'Session') as session:
                starter(['http://localhost:8080'], 0, 4)
                pool.submit.assert_not_called()
                thread.assert_not_called()
                session.assert_not_called()
                self.assertFalse(getattr(module, active))
                with self.assertRaises(ValueError):
                    starter(['http://localhost:8080'], -1, 4)

    def test_zero_rate_workers_send_no_requests(self):
        from simulator import normal_traffic, traffic_injectorV0
        # Call workers directly with an active flag: guards must precede any send.
        for module, worker, active in [
            (normal_traffic, normal_traffic.normal_http_request_worker, 'traffic_active'),
            (traffic_injectorV0, traffic_injectorV0.http_request_worker, 'attack_active')]:
            with self.subTest(component=module.__name__), \
                 patch.object(module, active, True), \
                 patch.object(module, '_send_pool') as pool, \
                 patch.object(module.requests, 'Session') as session, \
                 patch.object(module.time, 'sleep') as sleep:
                worker(0)
                pool.submit.assert_not_called()
                session.assert_not_called()
                sleep.assert_not_called()
                with self.assertRaises(ValueError):
                    worker(-1)

    def test_reproducible_example(self):
        example = ExperimentConfig.load('experiments/configs/example_reproducible.json')
        self.assertEqual(example, replace(ExperimentConfig(), seed=42))
        self.assertEqual(example.resolve_seed(), example)

    def test_workers_receive_workload_and_rate(self):
        from simulator import normal_traffic, traffic_injectorV0
        from simulator.experiment_config import NormalTrafficConfig, AttackConfig
        for module, settings, active, worker in [
            (normal_traffic, NormalTrafficConfig(rate=3, endpoint='/normal', work_units=17, sleep_seconds=.2),
             'traffic_active', normal_traffic.normal_http_request_worker),
            (traffic_injectorV0, AttackConfig(rate=7, endpoint='/attack', work_units=91, sleep_seconds=.3),
             'attack_active', traffic_injectorV0.http_request_worker)]:
            module.configure(settings, 42)
            module.update_targets(['http://localhost:8080'])
            def send_once(*args):
                setattr(module, active, False)
                return MagicMock()
            setattr(module, active, True)
            with patch.object(module._send_pool, 'submit', side_effect=send_once) as submit, \
                 patch.object(module.time, 'sleep') as sleep, \
                 patch('builtins.print'), \
                 patch.object(module, 'normal_traffic_summary_logger' if module is normal_traffic else 'attack_summary_logger'):
                worker(settings.rate, 2)
                self.assertEqual(submit.call_args.args[2],
                    'http://localhost:8080' + settings.endpoint + '?work=' + str(settings.work_units) + '&sleep=' + str(settings.sleep_seconds))
                component = 'normal' if module is normal_traffic else 'attack'
                expected = random.Random(worker_seed(42, component, 2)).expovariate(settings.rate)
                sleep.assert_called_once_with(expected)
            module._send_pool.shutdown()

    def test_orchestrator_wiring(self):
        from simulator import main_orchestrator as main, normal_traffic, traffic_injectorV0
        from simulator.stats_collector import StatsCollector
        with patch('docker.from_env'):
            from simulator import docker_manager
        c = ExperimentConfig.from_dict({'seed': 42, 'duration_seconds': 1,
            'attack': {'start_seconds': .2, 'duration_seconds': .4, 'rate': 7, 'attackers': 2},
            'normal_traffic': {'rate': 3, 'clients': 1},
            'monitoring': {'interval_seconds': .1, 'stats_poll_interval_seconds': .05}})
        container = MagicMock()
        container.attrs = {'NetworkSettings': {'Ports': {'80/tcp': [{'HostPort': '8080'}]}}}
        collector = MagicMock()
        collector.get_averages.return_value = (40, 1, ['target_instance_1'])
        ticks = iter([n / 10 for n in range(100)])
        with tempfile.TemporaryDirectory() as directory, \
             patch.multiple(main.config, **{key: str(Path(directory) / key) for key in
                ['METRICS_LOG_FILE', 'RTT_LOG_FILE', 'TCPDUMP_OUTPUT_CSV', 'ATTACK_SUMMARY_LOG_FILE', 'NORMAL_TRAFFIC_SUMMARY_LOG_FILE',
                 'ATTACK_EVENTS_LOG_FILE', 'REQUEST_LOG_FILE', 'RUN_STATUS_FILE']}), \
             patch.object(main, 'TcpdumpSniffer'), \
             patch('simulator.stats_collector.StatsCollector', return_value=collector), \
             patch.multiple(docker_manager, build_docker_image=MagicMock(return_value=True),
                ensure_docker_network=MagicMock(return_value=True), cleanup_all_simulation_instances=MagicMock(),
                start_instance=MagicMock(return_value=container)), \
             patch.multiple(normal_traffic, configure=MagicMock(), start_http_traffic=MagicMock(),
                update_targets=MagicMock(), stop_http_traffic=MagicMock(), save_rtt_log=MagicMock()), \
             patch.multiple(traffic_injectorV0, configure=MagicMock(), start_http_flood=MagicMock(),
                update_targets=MagicMock(), stop_http_flood=MagicMock()), \
             patch.object(main.time, 'monotonic', side_effect=lambda: next(ticks)), \
             patch.object(main.time, 'sleep'), patch('builtins.print'):
            main.main(c)
            normal_traffic.configure.assert_called_once_with(c.normal_traffic, 42,
                ground_truth=main.ground_truth, request_logger=main.request_logger)
            traffic_injectorV0.configure.assert_called_once_with(c.attack, 42,
                ground_truth=main.ground_truth, request_logger=main.request_logger)
            normal_traffic.start_http_traffic.assert_called_once_with(['http://localhost:8080'], 3, 1)
            traffic_injectorV0.start_http_flood.assert_called_once_with(['http://localhost:8080'], 7, 2, event_id='event_001')
            docker_manager.start_instance.assert_called_once_with(1, c.server)
            collector.get_averages.assert_called_with(window_seconds=.1)


if __name__ == '__main__':
    unittest.main()
