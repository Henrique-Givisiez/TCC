import csv
import io
import json
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from simulator.app import simple_server as server
from simulator import config, normal_traffic, traffic_injectorV0
from simulator.experiment_config import ExperimentConfig, worker_seed
from simulator.ground_truth import GroundTruth
from simulator.request_logger import RequestLogger
from simulator.service_destination import request_url


class ApplicationOperationsTests(unittest.TestCase):
    def test_server_budgets_and_query_independence(self):
        self.assertEqual(server.OPERATION_WORK_UNITS,
                         {'/light': 10000, '/medium': 100000, '/expensive': 1000000})
        with patch.dict(server.os.environ, WORK_UNITS='invalid', PROCESSING_TIME='invalid'):
            for path, cost in server.OPERATION_WORK_UNITS.items():
                for query in ('', '?work=0&sleep=10', '?work=999999999999',
                              '?work=invalid&sleep=invalid', '?work=-1&work=7'):
                    with self.subTest(path=path, query=query):
                        self.assertEqual(server.request_workload(path + query), (cost, 0.0))

    def test_handler_submits_selected_cpu_work_without_sleep(self):
        for path, cost in server.OPERATION_WORK_UNITS.items():
            handler = server.SimpleAppHandler.__new__(server.SimpleAppHandler)
            handler.path = path + '?work=0&sleep=100'
            handler.wfile = io.BytesIO()
            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            with patch.object(server, '_pool') as pool, patch.object(server.time, 'sleep') as sleep:
                handler.do_GET()
                pool.submit.assert_called_once_with(server._burn_cpu, cost)
                pool.submit.return_value.result.assert_called_once_with()
                sleep.assert_not_called()
            handler.send_response.assert_called_once_with(200)
            body = handler.wfile.getvalue()
            self.assertTrue(body.startswith(b'host='))
            self.assertIn(f'work={cost} sleep=0.0000s'.encode(), body)
            handler.send_header.assert_any_call('Content-Length', str(len(body)))

    def test_legacy_catch_all_query_and_environment(self):
        with patch.dict(server.os.environ, WORK_UNITS='23', PROCESSING_TIME='0.1'):
            self.assertEqual(server.request_workload('/'), (23, .1))
            self.assertEqual(server.request_workload('/protocol/path?work=17&sleep=0.001&encoded=a%2Fb'), (17, .001))
            self.assertEqual(server.request_workload('/?work=0&sleep=0'), (0, 0))
            # Exact reserved paths: do not silently change historical catch-all paths.
            self.assertEqual(server.request_workload('/expensive/?work=7'), (7, .1))
        with patch.dict(server.os.environ, WORK_UNITS='invalid'):
            with self.assertRaises(ValueError):
                server.request_workload('/?work=17&sleep=0')

    def test_new_configuration_omits_client_costs_and_roundtrips(self):
        path = Path('experiments/configs/application_operations.json')
        raw = json.loads(path.read_text())
        for group in ('normal_traffic', 'attack'):
            self.assertNotIn('work_units', raw[group])
            self.assertNotIn('sleep_seconds', raw[group])
        experiment = ExperimentConfig.load(path)
        self.assertEqual(ExperimentConfig.from_dict(json.loads(experiment.to_json())), experiment)
        for settings in (experiment.normal_traffic, experiment.attack):
            self.assertEqual(request_url(config.SOURCE_SERVICE_ENDPOINT, settings),
                             config.SOURCE_SERVICE_ENDPOINT + settings.endpoint)

    def test_both_generators_send_paths_and_preserve_seed_and_proxy_boundary(self):
        for module, original, flag, worker, component in (
                (normal_traffic, ExperimentConfig().normal_traffic, 'traffic_active',
                 normal_traffic.normal_http_request_worker, 'normal'),
                (traffic_injectorV0, ExperimentConfig().attack, 'attack_active',
                 traffic_injectorV0.http_request_worker, 'attack')):
            for path in server.OPERATION_WORK_UNITS:
                settings = replace(original, endpoint=path, work_units=999999999, sleep_seconds=100)
                module.configure(settings, 42, service_endpoint=config.SOURCE_SERVICE_ENDPOINT)
                try:
                    done = Future()
                    done.set_result(None)
                    def submit(*args):
                        setattr(module, flag, False)
                        return done
                    setattr(module, flag, True)
                    with patch.object(module._send_pool, 'submit', side_effect=submit) as send, \
                         patch.object(module.time, 'sleep') as sleep, patch('builtins.print'), \
                         patch.object(module, 'normal_traffic_summary_logger' if component == 'normal' else 'attack_summary_logger'):
                        worker(settings.rate, 2)
                        self.assertEqual(send.call_args.args[2], config.SOURCE_SERVICE_ENDPOINT + path)
                        sleep.assert_called_once_with(random.Random(worker_seed(42, component, 2)).expovariate(settings.rate))
                    self.assertIsNone(module._load_balancer)
                finally:
                    setattr(module, flag, False)
                    module._send_pool.shutdown()
            module.configure(original, 42)
            module._send_pool.shutdown()

    def test_ground_truth_is_origin_based_even_with_same_operation_and_drain(self):
        class Clock:
            epoch_initial = 1700000000
            monotonic_initial = 100
            now = 0
            def elapsed(self):
                return self.now
            def sample(self):
                return self.epoch_initial + self.now, self.now
        with tempfile.TemporaryDirectory() as directory:
            root, clock = Path(directory), Clock()
            gt = GroundTruth('operations', root/'events.csv', clock)
            log = RequestLogger(gt, root/'requests.csv')
            gt.plan_event('attack_001', 'event_001', 'continuous', 2, 4)
            clock.now = 2
            gt.activate('event_001')
            gt.admit('event_001')
            clock.now = 2.1
            attack = log.begin('attack', 0, config.SOURCE_SERVICE_ENDPOINT+'/expensive', 'event_001')
            clock.now = 3
            benign = log.begin('normal', 0, config.SOURCE_SERVICE_ENDPOINT+'/expensive')
            log.finish(benign, MagicMock(status_code=200))
            clock.now = 4
            gt.stop('event_001')
            clock.now = 5
            log.finish(attack, MagicMock(status_code=200))
            after = log.begin('normal', 0, config.SOURCE_SERVICE_ENDPOINT+'/light')
            log.finish(after, MagicMock(status_code=200))
            self.assertTrue(log.finalize())
            gt.finalize()
            event = gt.event('event_001')
            self.assertEqual((event['actual_start_seconds'], event['actual_end_seconds'], event['drained_end_seconds']), (2.1, 4, 5))
            with (root/'requests.csv').open() as stream:
                rows = {r['request_id']: r for r in csv.DictReader(stream)}
            self.assertEqual((rows[attack['request_id']]['traffic_class'], rows[attack['request_id']]['attack_active']), ('attack', '1'))
            self.assertEqual((rows[benign['request_id']]['traffic_class'], rows[benign['request_id']]['attack_active']), ('benign', '1'))
            self.assertEqual(rows[after['request_id']]['attack_active'], '0')
            self.assertIsNone(benign['event_id'])


if __name__ == '__main__':
    unittest.main()
