"""Persist tcpdump process lifecycle and enforce its end-of-capture counters."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import signal
import time


COUNTER_PATTERNS = {
    "packets_captured": re.compile(r"^(\d+) packets captured$", re.MULTILINE),
    "packets_received_by_filter": re.compile(r"^(\d+) packets received by filter$", re.MULTILINE),
    "packets_dropped_by_kernel": re.compile(r"^(\d+) packets dropped by kernel$", re.MULTILINE),
}


def observed_time():
    """Return paired wall/monotonic samples; neither is the kernel capture timestamp."""
    monotonic = time.monotonic()
    wall = datetime.now(timezone.utc).isoformat()
    return {"utc": wall, "monotonic_seconds": monotonic,
            "basis": "host observation sampled after/before the named process event; not tcpdump packet time"}


def parse_capture_counters(stderr_text):
    counters = {}
    for name, pattern in COUNTER_PATTERNS.items():
        matches = pattern.findall(stderr_text)
        counters[name] = int(matches[-1]) if len(matches) == 1 else None
    counters["statistics_complete"] = all(counters[name] is not None for name in COUNTER_PATTERNS)
    counters["statistics_occurrences"] = {
        name: len(pattern.findall(stderr_text)) for name, pattern in COUNTER_PATTERNS.items()}
    return counters


def capture_result_ok(returncode, stderr_text, accepted_returncodes=(0, -signal.SIGTERM)):
    counters = parse_capture_counters(stderr_text)
    return bool(returncode in accepted_returncodes and counters["statistics_complete"]
                and counters["packets_dropped_by_kernel"] == 0), counters


class CaptureLifecycle:
    """Track observed spawn/readiness/stop/exit and persist a run-local JSON sidecar."""

    def __init__(self, *, name, command, interface, bpf_filter, output_path, stderr_path, report_path):
        self.name = name
        self.command = list(command)
        self.interface = interface
        self.bpf_filter = bpf_filter
        self.output_path = str(output_path)
        self.stderr_path = str(stderr_path)
        self.report_path = Path(report_path)
        self.record = {
            "schema_version": 1,
            "capture": name,
            "command_argv": self.command,
            "interface": interface,
            "bpf_filter": bpf_filter,
            "output_path": self.output_path,
            "stderr_path": self.stderr_path,
            "timestamps": {},
            "termination_signals": [],
        }
        self.report = None

    def process_spawn_observed(self):
        self.record["timestamps"]["process_spawn_returned"] = observed_time()

    def listening_observed(self):
        self.record["timestamps"]["tcpdump_listening_message_observed"] = observed_time()

    def termination_requested(self, sig=signal.SIGTERM):
        name = signal.Signals(sig).name
        self.record["termination_signals"].append({"signal": name, "requested": observed_time()})

    def finish(self, *, returncode, stderr_text, launch_error=None):
        self.record["returncode"] = returncode
        self.record["launch_error"] = launch_error
        self.record["timestamps"]["process_exit_observed"] = observed_time() if returncode is not None else None
        self.record["capture_counters"] = parse_capture_counters(stderr_text)
        self.record["capture_diagnostic_sha256"] = __import__("hashlib").sha256(stderr_text.encode()).hexdigest()
        self.record["accepted_returncodes"] = [0, -signal.SIGTERM]
        self.record["accepted"] = bool(launch_error is None and capture_result_ok(returncode, stderr_text)[0])
        self.record["time_interpretation"] = (
            "process_spawn_returned is the host observation after Popen; "
            "tcpdump_listening_message_observed is when readiness text was read, not the exact first-packet timestamp; "
            "stop requested and process exit are host observations. Packet timestamps remain in capture artifacts.")
        with self.report_path.open("x") as stream:
            json.dump(self.record, stream, indent=2, allow_nan=False)
            stream.write("\n")
        self.report = self.record
        return self.record
