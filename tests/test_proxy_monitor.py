import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

from simulator.ground_truth import ExperimentClock
from simulator.http_proxy import nginx_config
from simulator.proxy_monitor import ProxyMonitor, parse_status, resources
from tests.test_dataset_export import DatasetExportTests


class MonitorTests(unittest.TestCase):
    def test_status(self):
        data = parse_status('Active connections: 3 \nserver accepts handled requests\n 20 19 45\nReading: 1 Writing: 1 Waiting: 1\n')
        self.assertEqual(data['requests_total'], 45)
        self.assertEqual(data['waiting_connections'], 1)
        with self.assertRaises(ValueError):
            parse_status('Active connections: unavailable')
        conf = nginx_config(['victim'])
        self.assertIn('listen 127.0.0.1:8081;', conf)
        self.assertIn('location = /nginx_status { stub_status; }', conf)

    def test_resources_first_reset_missing_and_multicore(self):
        def stats(cpu, system, rx):
            return dict(cpu_stats=dict(cpu_usage=dict(total_usage=cpu), system_cpu_usage=system, online_cpus=4),
                        memory_stats=dict(usage=123), networks=dict(eth0=dict(rx_bytes=rx, tx_bytes=rx*2)))
        a, b = stats(10, 100, 50), stats(70, 200, 90)
        first = resources(a)
        self.assertIsNone(first['cpu_percent'])
        self.assertIsNone(first['interfaces']['eth0']['rx_bytes_per_second'])
        observed = resources(b, (a, 1), 3)
        self.assertEqual(observed['cpu_percent'], 240)
        self.assertEqual(observed['memory_usage_bytes'], 123)
        self.assertEqual(observed['interfaces']['eth0']['rx_bytes_per_second'], 20)
        reset = resources(a, (b, 3), 4)
        self.assertIsNone(reset['cpu_percent'])
        self.assertIsNone(reset['interfaces']['eth0']['rx_bytes_per_second'])
        self.assertIsNone(resources({})['memory_usage_bytes'])
        self.assertIsNone(resources(b, (a, 3), 3)['cpu_percent'])

    def test_errors_alignment_stale_and_preservation(self):
        with tempfile.TemporaryDirectory() as folder:
            proxy = MagicMock(directory=Path(folder), run_id='run', expected_id='container')
            monitor = ProxyMonitor(proxy, ExperimentClock(), .01)
            monitor.client = MagicMock()
            monitor.client.containers.get.side_effect = TimeoutError('timeout')
            monitor.client.api.stats.return_value = dict(read='now')
            first = monitor.sample(0)
            self.assertEqual(first['run_id'], 'run')
            self.assertEqual(first['container_id'], 'container')
            self.assertGreaterEqual(first['status']['elapsed_seconds'], first['elapsed_seconds'])
            self.assertIn('TimeoutError', first['status']['error'])
            self.assertIsNone(first['status']['data'])
            self.assertTrue(first['docker']['success'])
            second = monitor.sample(0)
            self.assertFalse(second['docker']['success'])
            self.assertIn('stale', second['docker']['error'])
            self.assertEqual(monitor.attempts, 2)
            monitor.summary(fatal_error='failure')
            monitor.summary(thread_alive=False)
            self.assertEqual(json.loads((Path(folder)/'monitor_summary.json').read_text())['fatal_error'], 'failure')
            monitor.client.api.stats.side_effect = RuntimeError('unavailable')
            row = monitor.sample(0)
            self.assertIsNone(row['docker']['data'])

    def test_background_shutdown_flushes_samples(self):
        with tempfile.TemporaryDirectory() as folder:
            from unittest.mock import patch
            proxy = MagicMock(directory=Path(folder), run_id='run', expected_id='container')
            monitor = ProxyMonitor(proxy, ExperimentClock(), .01)
            with patch('simulator.proxy_monitor.docker.DockerClient') as client:
                client.return_value.api.stats.side_effect = TimeoutError('timeout')
                monitor.start()
                monitor.stop_event.wait(.04)
                monitor.stop()
            rows = [json.loads(line) for line in (Path(folder)/'monitor_samples.jsonl').read_text().splitlines()]
            self.assertTrue(rows)
            self.assertFalse(monitor.thread.is_alive())
            self.assertFalse(rows[0]['docker']['success'])

    def test_status_finishes_before_docker_stats_and_errors_counted(self):
        with tempfile.TemporaryDirectory() as folder:
            proxy = MagicMock(directory=Path(folder), run_id='run', expected_id='container')
            monitor = ProxyMonitor(proxy, ExperimentClock())
            monitor.client = MagicMock()
            order = []
            def status(*args):
                order.append('wget_done')
                return MagicMock(exit_code=0, output=b'Active connections: 1\nserver accepts handled requests\n1 1 1\nReading: 0 Writing: 1 Waiting: 0\n')
            def stats(*args, **kwargs):
                order.append('stats')
                return dict(read='new')
            monitor.client.containers.get.return_value.exec_run.side_effect = status
            monitor.client.api.stats.side_effect = stats
            row = monitor.sample(0)
            self.assertEqual(order, ['wget_done', 'stats'])
            self.assertGreaterEqual(row['docker']['elapsed_seconds'],
                row['status']['elapsed_seconds'] + row['status']['duration_seconds'] - .001)
            monitor.summary()
            summary = json.loads((Path(folder)/'monitor_summary.json').read_text())
            self.assertEqual(summary['source_errors'], dict(status=0, docker=0))
            monitor.client.containers.get.side_effect = TimeoutError('before exec')
            monitor.sample(0)  # Same Docker read timestamp is stale.
            monitor.summary()
            summary = json.loads((Path(folder)/'monitor_summary.json').read_text())
            self.assertEqual(summary['source_errors'], dict(status=1, docker=1))
            self.assertEqual(summary['monitoring_queries_attempted'], 2)

    def test_plot_source_times_nulls_and_failed_observations(self):
        import math
        from experiments.plot_proxy_monitor import observation_series
        rows = [dict(elapsed_seconds=100, docker=dict(elapsed_seconds=2, success=True,
                    data=dict(cpu_percent=None))),
                dict(elapsed_seconds=101, docker=dict(elapsed_seconds=3, success=False,
                    data=dict(cpu_percent=999))),
                dict(elapsed_seconds=102, docker=dict(elapsed_seconds=5, success=True,
                    data=dict(cpu_percent=12)))]
        xs, ys = observation_series(rows, 'docker', 'cpu_percent')
        self.assertEqual(xs, [2, 3, 5])
        self.assertTrue(math.isnan(ys[0]))
        self.assertTrue(math.isnan(ys[1]))
        self.assertEqual(ys[2], 12)
        status_rows = [dict(status=dict(elapsed_seconds=1.5, success=True,
                                       data=dict(active_connections=0)))]
        self.assertEqual(observation_series(status_rows, 'status', 'active_connections'), ([1.5], [0]))

    def test_plot_does_not_draw_lines_across_collection_gaps(self):
        from unittest.mock import patch
        from experiments.plot_proxy_monitor import plot
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'proxy_artifacts').mkdir()
            row = dict(docker=dict(success=False, elapsed_seconds=2, data=None),
                       status=dict(success=False, elapsed_seconds=1, data=None))
            (root/'proxy_artifacts/monitor_samples.jsonl').write_text(json.dumps(row)+'\n')
            (root/'attack_events.csv').write_text('actual_start_seconds,actual_end_seconds\n')
            fig, axes = MagicMock(), [MagicMock() for _ in range(3)]
            with patch('matplotlib.pyplot.subplots', return_value=(fig, axes)), \
                 patch('matplotlib.pyplot.close'):
                plot(root, root/'plot.png')
            for ax in axes:
                self.assertEqual(ax.plot.call_args.kwargs['linestyle'], 'None')


class MonitorExportTests(DatasetExportTests):
    def test_monitor_evidence_export_bytes(self):
        self.write('proxy_artifacts/monitor_samples.jsonl', dict(run_id='run1', cpu_percent=120))
        self.write('proxy_artifacts/monitor_summary.json', dict(run_id='run1'))
        original = (self.source/'proxy_artifacts/monitor_samples.jsonl').read_bytes()
        self.export()
        self.assertEqual((self.destination/'evidence/proxy/monitor_samples.jsonl').read_bytes(), original)

    def test_monitor_directory_archived_with_run(self):
        from experiments.result_archive import move_result
        self.write('proxy_artifacts/proxy_identity.json', dict(run_id='run1'))
        self.write('proxy_artifacts/monitor_samples.jsonl', dict(run_id='run1'))
        archived = self.root/'archive'
        archived.mkdir()
        move_result(str(self.source/'simulation_metrics.csv'), str(archived/'metrics_smoke.csv'))
        self.assertTrue((archived/'proxy_artifacts_smoke/monitor_samples.jsonl').exists())
