import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from simulator.experiment_config import ExperimentConfig
from simulator.http_proxy import HttpProxy, ProxyIntegrityError, nginx_config
from simulator import normal_traffic, traffic_injectorV0, config
from simulator.ground_truth import GroundTruth
from simulator.request_logger import RequestLogger


class ProxyTests(unittest.TestCase):
    def tearDown(self):
        for module, settings in [(normal_traffic, ExperimentConfig().normal_traffic),
                                 (traffic_injectorV0, ExperimentConfig().attack)]:
            module.configure(settings, 42)
            module._send_pool.shutdown()

    def test_configuration_rejects_autoscaler_and_empty_inventory(self):
        with self.assertRaisesRegex(ValueError, 'autoscaler'):
            ExperimentConfig.from_dict({'load_balancer': {'enabled': True}})
        with self.assertRaisesRegex(ValueError, 'at least one'):
            ExperimentConfig.from_dict({'load_balancer': {'enabled': True}, 'autoscaler': {'enabled': False},
                                        'infrastructure': {'initial_instances': 0, 'min_instances': 0}})
        c = ExperimentConfig.load('experiments/configs/proxy_single_victim.json')
        self.assertEqual(ExperimentConfig.from_dict(json.loads(c.to_json())), c)
        self.assertTrue(c.load_balancer.enabled)

    def test_n_backends_and_no_config_injection(self):
        rendered = nginx_config(['victim1', 'victim2', 'victim3'])
        self.assertEqual(rendered.count('max_fails=0;'), 3)
        self.assertIn('proxy_next_upstream off;', rendered)
        self.assertIn('proxy_pass http://victims;', rendered)
        for names in ([], ['victim; evil'], ['http://localhost:8081']):
            with self.assertRaises(ValueError):
                nginx_config(names)

    def test_proxy_identity_failure_and_unknown_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            client = MagicMock()
            proxy = HttpProxy(client, Path(root) / 'proxy')
            proxy.expected_id = 'original'
            client.containers.get.return_value = MagicMock(id='original', status='running')
            proxy.verify()
            for victim in [MagicMock(id='original', status='exited'), MagicMock(id='replacement', status='running')]:
                client.containers.get.return_value = victim
                with self.assertRaises(ProxyIntegrityError):
                    proxy.verify()
            client.containers.get.side_effect = RuntimeError('Docker unavailable')
            with self.assertRaisesRegex(ProxyIntegrityError, 'unable to verify'):
                proxy.verify()

    def test_generators_isolated_and_poisson_preserved(self):
        from concurrent.futures import Future
        import random
        from simulator.experiment_config import worker_seed
        for module, settings, flag, worker, component in [
                (normal_traffic, ExperimentConfig().normal_traffic, 'traffic_active', normal_traffic.normal_http_request_worker, 'normal'),
                (traffic_injectorV0, ExperimentConfig().attack, 'attack_active', traffic_injectorV0.http_request_worker, 'attack')]:
            module.configure(settings, 42, service_endpoint=config.SERVICE_ENDPOINT)
            self.assertIsNone(module._load_balancer)
            self.assertEqual(module._service_endpoint, config.SERVICE_ENDPOINT)
            self.assertFalse(hasattr(module, 'config'))
            with self.assertRaises(RuntimeError):
                module.update_targets(['http://victim1:80'])
            done = Future(); done.set_result(None)
            def submit(*args):
                setattr(module, flag, False)
                return done
            setattr(module, flag, True)
            with patch.object(module._send_pool, 'submit', side_effect=submit) as send, \
                 patch.object(module.time, 'sleep') as sleep, patch('builtins.print'), \
                 patch.object(module, 'normal_traffic_summary_logger' if component=='normal' else 'attack_summary_logger'):
                worker(settings.rate, 2)
                self.assertEqual(send.call_args.args[2], config.SERVICE_ENDPOINT + '/?work=' + str(settings.work_units) + '&sleep=0.0')
                sleep.assert_called_once_with(random.Random(worker_seed(42, component, 2)).expovariate(settings.rate))
            self.assertIsNone(module._load_balancer)

    def test_endpoint_only_and_no_redirect_or_retry_configuration(self):
        settings = ExperimentConfig().normal_traffic
        for endpoint in ['http://victim1:80', ['http://127.0.0.1:8080'], 'http://127.0.0.1:8081']:
            with self.assertRaises((ValueError, AttributeError)):
                normal_traffic.configure(settings, 42, service_endpoint=endpoint)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gt = GroundTruth('proxy', root / 'events.csv')
            logger = RequestLogger(gt, root / 'requests.csv', routing_log=root / 'routing.jsonl')
            normal_traffic.configure(settings, 42, gt, logger, config.SERVICE_ENDPOINT)
            response = MagicMock(status_code=200, text='host=backend work=10')
            session = MagicMock(); session.get.return_value = response
            import threading
            normal_traffic._send_one_normal(session, config.SERVICE_ENDPOINT + '/?work=10', {'ok':0,'err':0}, threading.Lock())
            self.assertFalse(session.get.call_args.kwargs['allow_redirects'])
            self.assertEqual(session.get.call_args.kwargs['headers']['X-Edos-Request-Id'], 'request_000000001')
            evidence = json.loads((root / 'routing.jsonl').read_text())
            self.assertEqual(evidence['response_body'], response.text)
            session.get.reset_mock()
            with self.assertRaisesRegex(ValueError, 'service endpoint'):
                normal_traffic._send_one_normal(session, 'http://victim1:80/', {'ok':0,'err':0}, threading.Lock())
            session.get.assert_not_called()
            self.assertTrue(logger.finalize())

    def test_victims_without_published_ports(self):
        with patch('docker.from_env'):
            from simulator import docker_manager
        import docker
        with patch.object(docker_manager, 'client') as client, patch.object(docker_manager.time, 'sleep'):
            client.containers.get.side_effect = docker.errors.NotFound('missing')
            docker_manager.start_instance(1, publish_ports=False)
            self.assertEqual(client.containers.run.call_args.kwargs['ports'], {})
            self.assertEqual(client.containers.run.call_args.kwargs['network'], config.DOCKER_NETWORK_NAME)

    def test_proxy_consult_failure_produces_incomplete_without_recovery(self):
        from simulator import main_orchestrator as main
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gt = GroundTruth('proxy_failure', root / 'events.csv')
            proxy = MagicMock()
            proxy.identity = {'id':'original'}
            proxy.verify.side_effect = ProxyIntegrityError('unable to verify proxy')
            with patch.multiple(main, ground_truth=gt, request_logger=None, sniffer=None,
                                stats_collector=None, http_proxy=proxy, normal_traffic=None,
                                traffic_injectorV0=None, docker_manager=MagicMock(), run_errors=[],
                                topology_integrity=None, create=True), \
                 patch.object(config, 'RUN_STATUS_FILE', str(root / 'status.json')):
                main._shutdown('simulation_end')
            status = json.loads((root / 'status.json').read_text())
            self.assertEqual(status['status'], 'incomplete')
            self.assertIn('unable to verify proxy', status['errors'])
            proxy.start.assert_not_called()

    def test_setup_failure_persists_status_without_invented_clock_or_event(self):
        from simulator import main_orchestrator as main
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def fail(experiment):
                main.setup_status = dict(run_id='setup', experiment_id='proxy', status='incomplete', end_reason='setup_error')
                raise ProxyIntegrityError('proxy configuration invalid')
            with patch.object(main, '_run', side_effect=fail), \
                 patch.multiple(main, normal_traffic=None, traffic_injectorV0=None,
                                docker_manager=None, create=True), \
                 patch.object(config, 'RUN_STATUS_FILE', str(root / 'status.json')):
                with self.assertRaises(ProxyIntegrityError):
                    main.main()
            status = json.loads((root / 'status.json').read_text())
            self.assertEqual(status['status'], 'incomplete')
            self.assertNotIn('experiment_start_timestamp', status)
            self.assertFalse((root / 'events.csv').exists())

    def test_archive_associates_proxy_artifacts_with_run(self):
        from experiments.result_archive import move_result
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'archive'; output.mkdir()
            (root/'simulation_metrics.csv').write_text('run_id,num_instances\nR,1\n')
            for filename in ('request_log.csv','attack_events.csv'):
                (root/filename).write_text('run_id\nR\n')
            (root/'run_status.json').write_text('{"run_id":"R"}')
            proxy = root/'proxy_artifacts'; proxy.mkdir()
            (proxy/'proxy_identity.json').write_text('{"run_id":"R"}')
            (proxy/'proxy_config.conf').write_text('example')
            (root/'effective_config.json').write_text('{"load_balancer":{"enabled":true}}')
            move_result(root/'simulation_metrics.csv', output/'metrics_test.csv')
            self.assertEqual((output/'proxy_artifacts_test/proxy_config.conf').read_text(), 'example')
            self.assertTrue((output/'effective_config_test.json').exists())


if __name__ == '__main__':
    unittest.main()
