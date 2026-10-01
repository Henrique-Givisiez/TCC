import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from simulator import main_orchestrator as main
from simulator.autoscaler_logic import Autoscaler
from simulator.experiment_config import ExperimentConfig
from simulator.ground_truth import GroundTruth
from experiments.validate_single_victim import scenario_configs


class SingleVictimTests(unittest.TestCase):
    def setUp(self):
        self.config = ExperimentConfig.load(Path(__file__).resolve().parents[1] / 'experiments/configs/single_victim.json')
        self.victim = MagicMock(id='original', status='running')
        self.client = MagicMock()
        self.client.containers.get.return_value = self.victim

    def test_config_and_scenarios_preserve_defaults(self):
        self.assertTrue(main.is_fixed_single_victim(self.config))
        self.assertEqual(self.config.seed, 42)
        self.assertEqual(self.config.normal_traffic, ExperimentConfig().normal_traffic)
        for label, c in scenario_configs(self.config).items():
            c.validate()
            self.assertTrue(main.is_fixed_single_victim(c))
            self.assertEqual(c.attack.profile, 'continuous')
            self.assertEqual(c.attack.rate, ExperimentConfig().attack.rate)
            self.assertEqual(c.normal_traffic.clients, 0 if label == 'B' else 4)
            self.assertEqual(c.attack.enabled, label != 'A')

    def test_disabled_never_scales_for_any_cpu(self):
        scaler = Autoscaler(self.config.autoscaler, self.config.infrastructure)
        for cpu in [0, 25, 60, 100, 1000]:
            self.assertEqual(scaler.decide_scaling(cpu, 1), 'NO_ACTION')
        self.assertEqual(scaler.cooldown_until, 0)

    def test_same_running_identity(self):
        for _ in range(3):
            self.assertIs(main.verify_fixed_victim([self.victim], 'original', self.client), self.victim)
        self.client.containers.get.assert_called_with('original')

    def test_count_identity_state_and_unknown_fail_closed(self):
        for containers in [[], [self.victim, self.victim], [MagicMock(id='replacement')]]:
            with self.assertRaisesRegex(main.VictimIntegrityError, 'identity/count'):
                main.verify_fixed_victim(containers, 'original', self.client)
        self.client.containers.get.return_value = MagicMock(id='replacement', status='running')
        with self.assertRaisesRegex(main.VictimIntegrityError, 'identity changed'):
            main.verify_fixed_victim([self.victim], 'original', self.client)
        self.client.containers.get.return_value = self.victim
        self.victim.status = 'exited'
        with self.assertRaisesRegex(main.VictimIntegrityError, 'stopped'):
            main.verify_fixed_victim([self.victim], 'original', self.client)
        for code, message in [(404, 'missing'), (500, 'unable to verify')]:
            exc = RuntimeError('Docker error'); exc.status_code = code
            self.client.containers.get.side_effect = exc
            with self.assertRaisesRegex(main.VictimIntegrityError, message):
                main.verify_fixed_victim([self.victim], 'original', self.client)

    def test_orchestrator_fixed_window_never_adds_or_removes_and_detects_failure(self):
        import csv
        from contextlib import ExitStack
        from dataclasses import replace
        from simulator import normal_traffic, traffic_injectorV0
        with patch('docker.from_env'):
            from simulator import docker_manager
        for failure in [None, 'exited', 'api_error']:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                root = Path(directory)
                c = replace(self.config, duration_seconds=3,
                            attack=replace(self.config.attack, start_seconds=1, duration_seconds=1))
                victim = MagicMock(id='fixed', status='running')
                victim.attrs = {'NetworkSettings': {'Ports': {'80/tcp': [{'HostPort': '8080'}]}}}
                client = MagicMock()
                calls = [0]
                def inspect(identity):
                    self.assertEqual(identity, 'fixed')
                    calls[0] += 1
                    if failure and calls[0] > 2:
                        if failure == 'api_error':
                            raise RuntimeError('Docker unavailable')
                        victim.status = failure
                    return victim
                client.containers.get.side_effect = inspect
                collector = MagicMock()
                collector.get_averages.side_effect = lambda **kw: (1000 if calls[0] % 2 else 0, 1, ['victim'])
                stack.enter_context(patch.multiple(main.config, **{key: str(root / key) for key in
                    ['METRICS_LOG_FILE', 'RTT_LOG_FILE', 'TCPDUMP_OUTPUT_CSV', 'ATTACK_SUMMARY_LOG_FILE',
                     'NORMAL_TRAFFIC_SUMMARY_LOG_FILE', 'ATTACK_EVENTS_LOG_FILE', 'REQUEST_LOG_FILE', 'RUN_STATUS_FILE']}))
                stack.enter_context(patch.object(main, 'TcpdumpSniffer'))
                stack.enter_context(patch('simulator.stats_collector.StatsCollector', return_value=collector))
                stack.enter_context(patch.multiple(docker_manager, client=client,
                    build_docker_image=MagicMock(return_value=True), ensure_docker_network=MagicMock(return_value=True),
                    cleanup_all_simulation_instances=MagicMock(), start_instance=MagicMock(return_value=victim),
                    stop_instance=MagicMock()))
                for module, starter, stopper in [(normal_traffic, 'start_http_traffic', 'stop_http_traffic'),
                                                 (traffic_injectorV0, 'start_http_flood', 'stop_http_flood')]:
                    stack.enter_context(patch.multiple(module, **{key: MagicMock() for key in
                        ['configure', 'update_targets', starter, stopper]}, drain=MagicMock(return_value=True)))
                ticks = iter(n / 10 for n in range(1000))
                stack.enter_context(patch.object(main.time, 'monotonic', side_effect=lambda: next(ticks)))
                stack.enter_context(patch.object(main.time, 'sleep'))
                stack.enter_context(patch('builtins.print'))
                if failure:
                    with self.assertRaises(main.VictimIntegrityError):
                        main.main(c)
                else:
                    main.main(c)
                docker_manager.start_instance.assert_called_once_with(1, c.server)
                docker_manager.stop_instance.assert_not_called()
                with (root / 'METRICS_LOG_FILE').open() as stream:
                    records = list(csv.DictReader(stream))
                self.assertTrue(records)
                self.assertTrue(all(r['num_instances'] == '1' and r['decision'] == 'NO_ACTION' for r in records))
                status = json.loads((root / 'RUN_STATUS_FILE').read_text())
                self.assertEqual(status['status'], 'incomplete' if failure else 'completed')
                self.assertEqual(status['topology_integrity']['verified_victim_ids'], ['fixed'])
                if failure:
                    self.assertTrue(status['errors'])

    def test_integrity_error_persisted_as_incomplete_without_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gt = GroundTruth('failed', root / 'attack_events.csv')
            manager = MagicMock()
            def fail(experiment):
                main.ground_truth = gt
                main.topology_integrity = {'expected_victim_id': 'original', 'checks': 0}
                main.verify_fixed_victim([self.victim], 'original', self.client)
            self.victim.status = 'exited'
            with patch.object(main, '_run', side_effect=fail), patch.multiple(main,
                    docker_manager=manager, normal_traffic=None, traffic_injectorV0=None, create=True), \
                    patch.object(main.config, 'RUN_STATUS_FILE', str(root / 'run_status.json')):
                with self.assertRaisesRegex(main.VictimIntegrityError, 'stopped'):
                    main.main(self.config)
            status = json.loads((root / 'run_status.json').read_text())
            self.assertEqual(status['status'], 'incomplete')
            self.assertEqual(status['end_reason'], 'error')
            self.assertIn('stopped', status['errors'][0])
            manager.start_instance.assert_not_called()
            manager.stop_instance.assert_not_called()
            self.assertEqual(status['topology_integrity']['expected_victim_id'], 'original')


if __name__ == '__main__':
    unittest.main()
