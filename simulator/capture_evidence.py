"""Raw evidence from the selected point, separate from scientific CSV schemas."""
import os
from pathlib import Path
import subprocess
import signal
import time
from simulator.capture_lifecycle import CaptureLifecycle


class RawCapture:
    DEFAULT_CAPTURE_BUFFER_KIB = 4096

    @staticmethod
    def artifact_paths(path):
        path = Path(path)
        return {"stderr": Path(str(path) + ".stderr"),
                "lifecycle": Path(str(path) + ".capture.json")}

    def __init__(self, interface, bpf, path):
        self.path = Path(path)
        paths = self.artifact_paths(self.path)
        self.diagnostic_path = paths['stderr']
        self.report_path = paths['lifecycle']
        self.process = None
        self.stderr = None
        self.lifecycle = CaptureLifecycle(name='pcap', command=['tcpdump','--immediate-mode','-B',str(self.DEFAULT_CAPTURE_BUFFER_KIB),
                                       '-U','-i',interface,'-n',
                                       '-w',str(self.path),bpf], interface=interface, bpf_filter=bpf,
                                       output_path=self.path, stderr_path=self.diagnostic_path, report_path=self.report_path)
        try:
            self.stderr = self.diagnostic_path.open('x+')
            self.process = subprocess.Popen(self.lifecycle.command, stderr=self.stderr, stdout=subprocess.DEVNULL)
            self.lifecycle.process_spawn_observed()
            deadline = time.monotonic()+5
            while b'listening on' not in os.pread(self.stderr.fileno(),8192,0):
                self.verify()
                if time.monotonic()>deadline:
                    raise RuntimeError('raw capture readiness timeout')
                time.sleep(.02)
            self.lifecycle.listening_observed()
        except BaseException as exc:
            try:
                self.stop(launch_error=repr(exc))
            except Exception:
                pass
            raise

    def verify(self):
        if self.process.poll() is not None:
            raise RuntimeError('raw evidence capture stopped')

    def stop(self, launch_error=None):
        if self.lifecycle.report is not None:
            if not self.lifecycle.report['accepted']:
                raise RuntimeError('raw evidence capture failed')
            return self.lifecycle.report
        returncode = None
        wait_error = launch_error
        if self.process is not None:
            if self.process.poll() is None:
                self.lifecycle.termination_requested(signal.SIGTERM)
                self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except Exception as exc:
                wait_error = repr(exc)
                if self.process.poll() is None:
                    self.lifecycle.termination_requested(signal.SIGKILL)
                    self.process.kill()
                try:
                    self.process.wait(timeout=5)
                except Exception as kill_exc:
                    wait_error += "; kill_wait=" + repr(kill_exc)
            returncode = self.process.returncode
        diagnostic = ''
        if self.stderr is not None:
            self.stderr.close()
            self.stderr = None
            diagnostic = self.diagnostic_path.read_text()
        report = self.lifecycle.finish(returncode=returncode, stderr_text=diagnostic,
                                       launch_error=wait_error)
        if not report['accepted']:
            if returncode not in (0,-signal.SIGTERM):
                raise RuntimeError(f'raw evidence tcpdump exited with status {returncode}: {report["capture_counters"]}')
            counters = report['capture_counters']
            raise RuntimeError(f"raw evidence capture failed: returncode={returncode}, counters={counters}")
        return report
