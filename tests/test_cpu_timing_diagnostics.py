"""Offline timings: operation-driven clocks, fake Docker and temporary files."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from simulator.stats_collector import StatsCollector
from simulator.cpu_observations import SAMPLES, SUMMARY, delta
from experiments.cpu_features import assign_cpu
from tests import test_cpu_observations as cpu_fixtures


class TimingTests(unittest.TestCase):
    def acquire(self, enabled):
        clock = SimpleNamespace(now=50.98)
        calls = []
        class Container:
            id = 'victim'
            @property
            def attrs(self):
                clock.now += .001
                return dict(State=dict(Status='running', StartedAt='boot1'), RestartCount=0)
            def stats(self, **kwargs):
                calls.append(('stats', kwargs)); clock.now += .004
                class Stats(dict):
                    def get(self, *args):
                        clock.now += .001
                        return super().get(*args)
                return Stats(read='1970-01-01T00:01:40.985000Z', cpu_stats=dict(
                    cpu_usage=dict(total_usage=100), system_cpu_usage=400, online_cpus=4))
        client = MagicMock()
        def get(cid):
            calls.append(('get', cid)); clock.now += .003
            return Container()
        client.containers.get.side_effect = get
        c = StatsCollector(client)
        with tempfile.TemporaryDirectory() as tmp:
            c.bind_cpu('run1', SimpleNamespace(monotonic_initial=50, epoch_initial=100), Path(tmp)/SAMPLES)
            if enabled: c.bind_timing_diagnostics(Path(tmp)/'test.cpu-timing-diagnostic.json')
            def measured_delta(*args):
                result = delta(*args); clock.now += .005; return result
            with patch('simulator.stats_collector.time.monotonic', lambda: clock.now), \
                 patch('simulator.stats_collector.time.time', lambda: clock.now+50), \
                 patch('simulator.stats_collector.delta', side_effect=measured_delta):
                row, _, _ = c._acquire('victim', 50.975, 50)
        return row, calls, c

    def test_stage_measurements_preserve_scientific_timestamps_and_docker_calls(self):
        baseline, calls, off = self.acquire(False)
        instrumented, measured_calls, on = self.acquire(True)
        self.assertEqual(baseline, instrumented)
        self.assertEqual(calls, [('get', 'victim'), ('stats', dict(stream=False, one_shot=True))])
        self.assertEqual(calls, measured_calls)
        self.assertIsNone(off.timing_diagnostics)
        record = on.timing_diagnostics.records[0]; t = record['stamps']
        for start, end, expected in [('inspect_start','inspect_end',.003),
                                     ('inspect_end','validation_end',.002),
                                     ('validation_end','stats_end',.004),
                                     ('stats_end','received',.002),
                                     ('delta_start','delta_end',.005)]:
            self.assertAlmostEqual(t[end]-t[start], expected)
        self.assertAlmostEqual(record['schedule_delay_seconds'], .005)
        self.assertEqual(t['received'], instrumented['received_seconds']+50)

    def run_collector(self, root, enabled, capacity=20):
        fixture = cpu_fixtures.CollectorTests()
        c, clock = fixture.fake(root)
        path = root/'test.cpu-timing-diagnostic.json'
        if enabled: c.bind_timing_diagnostics(path, capacity)
        fixture.run_fake(c, clock)
        return c, path

    def test_loop_output_and_assignment_unchanged_and_diagnostics_close(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            off, missing = self.run_collector(Path(a), False)
            on, path = self.run_collector(Path(b), True)
            self.assertFalse(missing.exists())
            self.assertIsNone(off.timing_diagnostics)
            self.assertIsNone(on.failure)
            self.assertEqual((Path(a)/SAMPLES).read_bytes(), (Path(b)/SAMPLES).read_bytes())
            self.assertEqual((Path(a)/SUMMARY).read_bytes(), (Path(b)/SUMMARY).read_bytes())
            rows = [json.loads(line) for line in (Path(b)/SAMPLES).read_text().splitlines()]
            marker, summary, status = cpu_fixtures.contract(rows)
            baseline = assign_cpu(marker, rows, summary, status, 8)
            other = [json.loads(line) for line in (Path(a)/SAMPLES).read_text().splitlines()]
            self.assertEqual(baseline, assign_cpu(marker, other, summary, status, 8))
            doc = json.loads(path.read_text())
            self.assertTrue(doc['collection_complete'])
            self.assertEqual(doc['kind'], 'cpu_timing_diagnostic_non_scientific')
            self.assertEqual([r['sequence'] for r in doc['records']], [1,2,3])
            for record in doc['records']:
                stamps = record['stamps']
                names = ['inspect_start','inspect_end','validation_end','stats_end','received',
                         'delta_start','delta_end','serialization_start','serialization_end',
                         'write_end','flush_end','fsync_end']
                self.assertEqual(sorted(stamps), sorted(names))
                self.assertEqual([stamps[k] for k in names], sorted(stamps.values()))
                self.assertAlmostEqual(record['remaining_until_next_seconds'],
                    record['next_scheduled_monotonic']-record['schedule_observed_monotonic'])
            # Exclusive creation: diagnostics cannot overwrite an earlier result.
            with self.assertRaises(FileExistsError): on.timing_diagnostics.finish('run1', None)

    def test_persistence_stages_are_measured_individually(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture=cpu_fixtures.CollectorTests();c,clock=fixture.fake(root)
            c.bind_timing_diagnostics(root/'test.cpu-timing-diagnostic.json')
            real_open=Path.open;real_dumps=json.dumps
            class ScientificStream:
                def __init__(self, stream): self.stream=stream
                def write(self, value):
                    clock.now+=.003;return self.stream.write(value)
                def flush(self): clock.now+=.004;return self.stream.flush()
                def fileno(self): return self.stream.fileno()
                def close(self): return self.stream.close()
            def opened(path, *args, **kwargs):
                stream=real_open(path,*args,**kwargs)
                return ScientificStream(stream) if path==root/SAMPLES else stream
            def dumps(*args, **kwargs):
                clock.now+=.002;return real_dumps(*args,**kwargs)
            def fsync(fd): clock.now+=.007
            with patch.object(Path,'open',opened), \
                 patch('simulator.stats_collector.json.dumps',side_effect=dumps), \
                 patch('simulator.stats_collector.os.fsync',side_effect=fsync):
                fixture.run_fake(c,clock)
            for record in c.timing_diagnostics.records:
                t=record['stamps']
                for start,end,duration in [('serialization_start','serialization_end',.002),
                        ('serialization_end','write_end',.003),('write_end','flush_end',.004),
                        ('flush_end','fsync_end',.007)]:
                    self.assertAlmostEqual(t[end]-t[start],duration)

    def test_no_diagnostic_io_until_collection_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);fixture = cpu_fixtures.CollectorTests();c,clock = fixture.fake(root)
            path = root/'test.cpu-timing-diagnostic.json';c.bind_timing_diagnostics(path)
            original = c._on_acquisition
            def hook(*args):
                self.assertFalse(path.exists()); original(*args)
            c._on_acquisition = hook
            fixture.run_fake(c,clock)
            self.assertTrue(path.exists())

    def test_capacity_and_output_failure_are_explicit_and_propagate(self):
        with tempfile.TemporaryDirectory() as tmp:
            c,path = self.run_collector(Path(tmp), True, capacity=1)
            self.assertIn('capacity exhausted', c.failure)
            doc = json.loads(path.read_text());self.assertFalse(doc['collection_complete'])
            self.assertEqual(len(doc['records']), 1)
            self.assertIn('capacity exhausted', json.loads((Path(tmp)/SUMMARY).read_text())['fatal_error'])
            c._t = MagicMock(); c._t.is_alive.return_value = False
            with self.assertRaisesRegex(RuntimeError, 'capacity exhausted'): c.stop()
        with tempfile.TemporaryDirectory() as tmp:
            fixture = cpu_fixtures.CollectorTests();root=Path(tmp);c,clock=fixture.fake(root)
            c.bind_timing_diagnostics(root/'missing'/'test.cpu-timing-diagnostic.json')
            fixture.run_fake(c,clock)
            self.assertIn('timing diagnostics', c.failure)
            c._t = MagicMock(); c._t.is_alive.return_value = False
            with self.assertRaisesRegex(RuntimeError,'timing diagnostics'): c.stop()

    def test_failed_acquisition_retains_partial_timing_and_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture=cpu_fixtures.CollectorTests();root=Path(tmp);c,clock=fixture.fake(root,fail=True)
            c.bind_timing_diagnostics(root/'test.cpu-timing-diagnostic.json')
            fixture.run_fake(c,clock)
            record=c.timing_diagnostics.records[1]
            self.assertIn('TimeoutError',record['acquisition_error'])
            self.assertIn('acquisition_exception',record['stamps'])
            self.assertNotIn('stats_end',record['stamps'])
            self.assertIn('fsync_end',record['stamps'])


if __name__ == '__main__': unittest.main()
