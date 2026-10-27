# tcpdump_realtime_sniffer.py
import subprocess
import threading
import csv
import os
import tempfile
import re
import signal
import time
from pathlib import Path
from typing import Optional
from simulator.ground_truth import encode_event_ids
from simulator.capture_lifecycle import CaptureLifecycle

PACKET_FIELDS = ["run_id", "timestamp", "elapsed_seconds", "src_ip", "src_port",
                 "dst_ip", "dst_port", "packet_length", "traffic_class",
                 "attack_active", "active_event_ids"]

TCP_FLAG_MAP = {
    "S": "SYN",
    ".": "ACK",
    "F": "FIN",
    "R": "RST",
    "P": "PSH",
    "U": "URG",
    "E": "ECE",
    "W": "CWR"
}



TCPDUMP_REGEX = re.compile(
    r'(?P<time>\d+\.\d+).*?IP\s+'
    r'(?P<src_ip>\d+\.\d+\.\d+\.\d+)\.(?P<src_port>\d+)\s+>\s+'
    r'(?P<dst_ip>\d+\.\d+\.\d+\.\d+)\.(?P<dst_port>\d+):.*?'
    r'(?:length|tcp)\s+(?P<length>\d+)'
)


class TcpdumpSniffer:
    DEFAULT_CAPTURE_BUFFER_KIB = 4096

    def __init__(self, interface: str, output_csv: str, ground_truth,
                 port_range: Optional[tuple] = None, bpf_filter=None,
                 buffer_size_kib: int = DEFAULT_CAPTURE_BUFFER_KIB):
        self.interface = interface
        self.output_csv = output_csv
        self.buffer_size_kib = buffer_size_kib
        self.process: Optional[subprocess.Popen] = None
        self.thread: Optional[threading.Thread] = None
        self.running = False
        self.ground_truth = ground_truth
        self.reader_error = None
        self.stderr_file = None
        self.capture_diagnostic = None
        paths = self.artifact_paths(output_csv)
        self.stderr_path = paths['stderr']
        self.lifecycle_path = paths['lifecycle']
        self.lifecycle = None
        # (min_port, max_port) dos containers alvo: restringe a captura a
        # essas portas via filtro BPF, em vez de depender de qual interface
        # de rede é escolhida (ver start()).
        self.port_range = port_range
        self.bpf_filter = bpf_filter
        self._init_csv()

    @staticmethod
    def artifact_paths(output_csv):
        path = Path(output_csv)
        return {"stderr": path.with_suffix('.stderr'),
                "lifecycle": path.with_suffix(path.suffix + '.capture.json')}

    def build_command(self):
        bpf_filter = "tcp"
        if self.port_range:
            lo, hi = self.port_range
            bpf_filter = f"tcp and portrange {lo}-{hi}"
        if self.bpf_filter is not None:
            bpf_filter = self.bpf_filter
        return ["tcpdump", "--immediate-mode", "-B", str(self.buffer_size_kib),
                "-i", self.interface, "-l", "-n", "-tt", "-q", bpf_filter]

    def _init_csv(self):
        with open(self.output_csv, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=PACKET_FIELDS).writeheader()

    def start(self):
        if self.running:
            print("[Sniffer] Realtime tcpdump already running.")
            return

        cmd = self.build_command()
        bpf_filter = cmd[-1]
        self.lifecycle = CaptureLifecycle(name='csv', command=cmd, interface=self.interface,
            bpf_filter=bpf_filter, output_path=self.output_csv, stderr_path=self.stderr_path,
            report_path=self.lifecycle_path)

        self.stderr_file = tempfile.TemporaryFile(mode='w+t')
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=self.stderr_file,
                text=True,
                bufsize=1
            )
            self.lifecycle.process_spawn_observed()
        except BaseException as exc:
            self.stderr_file.close()
            self.stderr_file = None
            self.stderr_path.open('x').close()
            self.lifecycle.finish(returncode=None, stderr_text='', launch_error=repr(exc))
            raise

        self.running = True
        self.thread = threading.Thread(
            target=self._reader_loop,
            daemon=True
        )
        self.thread.start()

        print(f"[Sniffer] Realtime tcpdump started on {self.interface}")

    def wait_ready(self, timeout=3):
        """Wait for tcpdump's listening message, without sending probe traffic."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.check_running()
            # pread does not change the descriptor position used by tcpdump.
            if b'listening on' in os.pread(self.stderr_file.fileno(), 8192, 0):
                if 'tcpdump_listening_message_observed' not in self.lifecycle.record['timestamps']:
                    self.lifecycle.listening_observed()
                return
            time.sleep(.02)
        raise RuntimeError('tcpdump readiness timeout')

    def check_running(self):
        if self.reader_error:
            raise RuntimeError('tcpdump CSV writer failed') from self.reader_error
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError('tcpdump stopped during experiment')

    def _reader_loop(self):
        while self.process and self.process.stdout:
            line = self.process.stdout.readline()
            if not line:
                break


            match = TCPDUMP_REGEX.search(line)
            if not match:
                continue

            data = match.groupdict()
            try:
                self._write_row(data)
            except Exception as exc:
                self.reader_error = exc
                break


    def _write_row(self, data):
        timestamp = float(data['time'])
        elapsed = self.ground_truth.clock.from_epoch(timestamp)
        active, ids = self.ground_truth.context(elapsed)
        row = dict(run_id=self.ground_truth.run_id, timestamp=timestamp,
                   elapsed_seconds=elapsed, src_ip=data['src_ip'], src_port=int(data['src_port']),
                   dst_ip=data['dst_ip'], dst_port=int(data['dst_port']),
                   packet_length=int(data['length']), traffic_class='unknown',
                   attack_active=active, active_event_ids=encode_event_ids(ids))
        with open(self.output_csv, 'a', newline='') as f:
            csv.DictWriter(f, fieldnames=PACKET_FIELDS).writerow(row)

    def finalize_context(self):
        # A packet can be processed before an event transition is recorded.
        # Requery the SAME official timeline after producers drain, never infer origin.
        temporary = str(self.output_csv) + '.tmp'
        with open(self.output_csv, newline='') as src, open(temporary, 'w', newline='') as dst:
            writer = csv.DictWriter(dst, fieldnames=PACKET_FIELDS)
            writer.writeheader()
            for row in csv.DictReader(src):
                active, ids = self.ground_truth.context(float(row['elapsed_seconds']))
                row.update(attack_active=active, active_event_ids=encode_event_ids(ids))
                writer.writerow(row)
        os.replace(temporary, self.output_csv)

    def stop(self):
        if self.process is None:
            if self.lifecycle is not None and self.lifecycle.report is not None:
                if not self.lifecycle.report['accepted']:
                    raise RuntimeError('tcpdump CSV launch/capture failed')
                return self.lifecycle.report
            return None
        wait_error = None
        if self.process.poll() is None:
            self.lifecycle.termination_requested(signal.SIGTERM)
            self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except Exception as exc:
            wait_error = exc
            if self.process.poll() is None:
                self.lifecycle.termination_requested(signal.SIGKILL)
                self.process.kill()
                try:
                    self.process.wait(timeout=5)
                except Exception as kill_exc:
                    wait_error = RuntimeError(f"{exc!r}; kill_wait={kill_exc!r}")
        if self.thread:
            self.thread.join(timeout=5)  # consume stdout through EOF, including buffered lines
        self.running = False
        diagnostic = ''
        if self.stderr_file is not None:
            self.stderr_file.seek(0)
            diagnostic = self.stderr_file.read()
            self.stderr_file.close()
            self.stderr_file = None
        self.capture_diagnostic = diagnostic
        with self.stderr_path.open('x') as stream:
            stream.write(diagnostic + ('\n' if diagnostic and not diagnostic.endswith('\n') else ''))
        report = self.lifecycle.finish(returncode=self.process.returncode, stderr_text=diagnostic,
                                       launch_error=repr(wait_error) if wait_error else None)
        finalize_error = None
        try:
            self.finalize_context()  # partial captures retain the authoritative final timeline too
        except Exception as exc:
            finalize_error = exc
        if self.thread and self.thread.is_alive():
            raise RuntimeError('tcpdump reader did not drain')
        if self.reader_error:
            raise RuntimeError('tcpdump CSV writer failed') from self.reader_error
        if finalize_error:
            raise RuntimeError('tcpdump CSV context finalization failed') from finalize_error
        if not report['accepted']:
            if self.process.returncode not in (0,-signal.SIGTERM):
                raise RuntimeError(f'tcpdump exited with status {self.process.returncode}: {report["capture_counters"]}')
            raise RuntimeError(f"tcpdump CSV capture failed: returncode={self.process.returncode}, counters={report['capture_counters']}")
        print("[Sniffer] Realtime tcpdump stopped.")
        return report
