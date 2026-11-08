"""Offline volume, drain and error contracts for the CSV reader."""
import csv
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tests.test_capture_lifecycle import FakeGroundTruth, FakeTcpdump
from simulator.tcpdump_sniffer import TcpdumpSniffer, PACKET_FIELDS


class WriterTests(unittest.TestCase):
    def test_volume_drains_in_order_and_matches_synchronous_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'volume.csv'
            sniffer = TcpdumpSniffer('offline', path, FakeGroundTruth())
            count = 100000
            lines = ''.join(f'{i}.125 IP 172.20.0.3.40000 > 172.20.0.2.80: tcp {i % 1400}\n' for i in range(count))
            def fake(command, **kwargs):
                process = FakeTcpdump(command, **kwargs)
                process.stdout = io.StringIO(lines)
                return process
            with patch('simulator.tcpdump_sniffer.subprocess.Popen', side_effect=fake):
                sniffer.start()
                sniffer.stop()  # joins reader through EOF, closes writer before finalization
            self.assertFalse(sniffer.thread.is_alive())
            with path.open(newline='') as stream:
                reader = csv.DictReader(stream)
                self.assertEqual(reader.fieldnames, PACKET_FIELDS)
                rows = list(reader)
            self.assertEqual(len(rows), count)
            for i, row in enumerate(rows):
                self.assertEqual(float(row['timestamp']), i+.125)
                self.assertEqual(float(row['elapsed_seconds']), i+.125)
                self.assertEqual(int(row['packet_length']), i % 1400)
                self.assertEqual(row['attack_active'], 'False')
            other = TcpdumpSniffer('offline', Path(tmp)/'sync.csv', FakeGroundTruth())
            for i in range(100):
                other._write_row(dict(time=f'{i}.125',src_ip='172.20.0.3',src_port='40000',dst_ip='172.20.0.2',dst_port='80',length=str(i%1400)))
            self.assertEqual(other.output_csv.read_bytes(), b''.join(path.read_bytes().splitlines(keepends=True)[:101]))

    def test_open_read_write_and_close_errors_propagate(self):
        for stage in ('open','read','write','close'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmp:
                s = TcpdumpSniffer('offline', Path(tmp)/'capture.csv', FakeGroundTruth())
                failure = OSError(stage)
                class Stream(io.StringIO):
                    def write(self, value):
                        if stage == 'write': raise failure
                        return super().write(value)
                    def close(self):
                        super().close()
                        if stage == 'close': raise failure
                stdout = io.StringIO('1.25 IP 172.20.0.3.40000 > 172.20.0.2.80: tcp 10\n')
                if stage == 'read':
                    stdout = SimpleNamespace(readline=lambda: (_ for _ in ()).throw(failure))
                s.process = SimpleNamespace(stdout=stdout)
                kwargs = {'side_effect':failure} if stage == 'open' else {'return_value':Stream()}
                with patch('simulator.tcpdump_sniffer.open', **kwargs): s._reader_loop()
                self.assertIs(s.reader_error, failure)
                with self.assertRaisesRegex(RuntimeError,'writer failed'): s.check_running()

    def test_final_timeline_uses_packet_time_after_reader_closes(self):
        from simulator.ground_truth import GroundTruth
        with tempfile.TemporaryDirectory() as tmp:
            from tests.test_ground_truth import Clock
            from simulator.request_logger import RequestLogger
            clock = Clock()
            gt = GroundTruth('timeline', Path(tmp)/'events.csv', clock)
            s = TcpdumpSniffer('offline', Path(tmp)/'capture.csv', gt)
            timestamp = gt.clock.epoch_initial + 160
            s.process = SimpleNamespace(stdout=io.StringIO(
                f'{timestamp:.6f} IP 172.20.0.3.40000 > 172.20.0.2.80: tcp 10\n'))
            s._reader_loop()
            gt.plan_event('attack', 'event', 'continuous', 150, 270)
            clock.now = 150
            gt.activate('event')
            gt.admit('event')
            RequestLogger(gt, Path(tmp)/'requests.csv').begin('attack', 0, 'http://localhost:80', 'event')
            s.finalize_context()
            with s.output_csv.open(newline='') as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(row['attack_active'], '1')
            self.assertAlmostEqual(float(row['elapsed_seconds']), 160, places=5)

    def test_stop_reports_close_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = TcpdumpSniffer('offline',Path(tmp)/'capture.csv',FakeGroundTruth())
            with patch('simulator.tcpdump_sniffer.subprocess.Popen',side_effect=FakeTcpdump):
                s.start(); s.thread.join()
                s.reader_error = OSError('flush failed')
                with self.assertRaisesRegex(RuntimeError,'writer failed'): s.stop()


if __name__ == '__main__': unittest.main()
