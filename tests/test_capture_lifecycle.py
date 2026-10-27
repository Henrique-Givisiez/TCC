"""Offline capture-contract tests; all tcpdump processes are fakes."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from simulator.capture_evidence import RawCapture
from simulator.capture_lifecycle import capture_result_ok, parse_capture_counters
from simulator.tcpdump_sniffer import TcpdumpSniffer


READY = "listening on br-test, link-type EN10MB (Ethernet), snapshot length 262144 bytes\n"
COUNTERS = "12 packets captured\n12 packets received by filter\n0 packets dropped by kernel\n"


class FakeTcpdump:
    def __init__(self, command, *, stderr, stdout=None, final_diagnostic=COUNTERS, exit_after_terminate=-15,
                 text=False, bufsize=None):
        self.command = command
        self.stderr = stderr
        self.stdout = io.StringIO("")
        self.returncode = None
        self.final_diagnostic = final_diagnostic
        self.exit_after_terminate = exit_after_terminate
        stderr.write(READY + final_diagnostic)
        stderr.flush()

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = self.exit_after_terminate

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


class FakeGroundTruth:
    class Clock:
        @staticmethod
        def from_epoch(value):
            return value
    clock = Clock()
    run_id = "synthetic-capture"

    @staticmethod
    def context(_elapsed):
        return False, ()


class CaptureLifecycleTests(unittest.TestCase):
    def test_capture_artifacts_have_distinct_stderr_and_metadata_paths(self):
        csv_paths = TcpdumpSniffer.artifact_paths("traffic_capture.csv")
        pcap_paths = RawCapture.artifact_paths("traffic_capture.pcap")
        self.assertNotEqual(csv_paths["stderr"], pcap_paths["stderr"])
        self.assertNotEqual(csv_paths["lifecycle"], pcap_paths["lifecycle"])
        self.assertEqual(str(pcap_paths["stderr"]), "traffic_capture.pcap.stderr")

    def test_csv_command_has_explicit_4096_kib_buffer(self):
        sniffer = TcpdumpSniffer("br-test", "capture.csv", FakeGroundTruth(),
                                 bpf_filter="tcp and port 80")
        command = sniffer.build_command()
        self.assertEqual(command[command.index("-B") + 1], "4096")
        self.assertEqual(command[-1], "tcp and port 80")
        self.assertEqual(command[command.index("-i") + 1], "br-test")

    def test_counter_parser_preserves_all_values_and_strictly_rejects_bad_stats(self):
        ok, counters = capture_result_ok(-15, COUNTERS)
        self.assertTrue(ok)
        self.assertEqual(counters["packets_captured"], 12)
        self.assertEqual(counters["packets_received_by_filter"], 12)
        self.assertEqual(counters["packets_dropped_by_kernel"], 0)
        dropped = parse_capture_counters(COUNTERS.replace("0 packets dropped", "2 packets dropped"))
        self.assertEqual(dropped["packets_dropped_by_kernel"], 2)
        self.assertFalse(capture_result_ok(-15, COUNTERS.replace("0 packets dropped", "2 packets dropped"))[0])
        self.assertFalse(capture_result_ok(-15, "12 packets captured\n")[0])
        self.assertFalse(capture_result_ok(1, COUNTERS)[0])

    def test_pcap_process_saves_command_counters_code_and_lifecycle_and_rejects_drops(self):
        for diagnostic, accepted in ((COUNTERS, True), (COUNTERS.replace("0 packets dropped", "2 packets dropped"), False),
                                     ("statistics missing\n", False)):
            with self.subTest(accepted=accepted, diagnostic=diagnostic), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "traffic_capture.pcap"
                fake = lambda command, **kwargs: FakeTcpdump(command, final_diagnostic=diagnostic, **kwargs)
                with patch("simulator.capture_evidence.subprocess.Popen", side_effect=fake):
                    capture = RawCapture("br-test", "tcp and port 80", output)
                    if accepted:
                        report = capture.stop()
                    else:
                        with self.assertRaises(RuntimeError):
                            capture.stop()
                        report = json.loads(Path(str(output) + ".capture.json").read_text())
                self.assertEqual(report["returncode"], -15)
                self.assertEqual(report["capture_counters"]["statistics_complete"], diagnostic == COUNTERS or "packets captured" in diagnostic)
                self.assertEqual(report["accepted"], accepted)
                self.assertTrue(Path(str(output) + ".stderr").is_file())
                self.assertEqual(report["command_argv"][-1], "tcp and port 80")
                self.assertIn("process_spawn_returned", report["timestamps"])
                self.assertIn("tcpdump_listening_message_observed", report["timestamps"])
                self.assertIn("process_exit_observed", report["timestamps"])

    def test_csv_process_persists_stderr_metadata_and_rejects_exit_drop_or_missing_stats(self):
        variants = ((COUNTERS, -15, True),
                    (COUNTERS, 1, False),
                    (COUNTERS.replace("0 packets dropped", "1 packets dropped"), -15, False),
                    ("no final counters\n", -15, False))
        for diagnostic, exitcode, accepted in variants:
            with self.subTest(exitcode=exitcode, accepted=accepted), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "traffic_capture.csv"
                sniffer = TcpdumpSniffer("br-test", str(output), FakeGroundTruth(), bpf_filter="tcp and port 80")
                fake = lambda command, **kwargs: FakeTcpdump(command, final_diagnostic=diagnostic,
                                                              exit_after_terminate=exitcode, **kwargs)
                with patch("simulator.tcpdump_sniffer.subprocess.Popen", side_effect=fake):
                    sniffer.start()
                    sniffer.wait_ready()
                    if accepted:
                        report = sniffer.stop()
                    else:
                        with self.assertRaises(RuntimeError):
                            sniffer.stop()
                        report = json.loads(sniffer.lifecycle_path.read_text())
                self.assertEqual(report["returncode"], exitcode)
                self.assertEqual(report["accepted"], accepted)
                self.assertEqual(report["command_argv"][report["command_argv"].index("-B") + 1], "4096")
                self.assertTrue(sniffer.stderr_path.is_file())
                self.assertTrue(sniffer.lifecycle_path.is_file())
                self.assertIn("process_exit_observed", report["timestamps"])


if __name__ == "__main__":
    unittest.main()
