"""Raw evidence from the selected point, separate from scientific CSV schemas."""
import os
from pathlib import Path
import subprocess
import time


class RawCapture:
    def __init__(self, interface, bpf, path):
        self.path = Path(path)
        self.diagnostic_path = self.path.with_suffix('.stderr')
        self.stderr = self.diagnostic_path.open('w+')
        self.process = subprocess.Popen(['tcpdump','--immediate-mode','-U','-i',interface,'-n',
                                         '-w',str(self.path),bpf],stderr=self.stderr,stdout=subprocess.DEVNULL)
        deadline = time.monotonic()+5
        while b'listening on' not in os.pread(self.stderr.fileno(),8192,0):
            self.verify()
            if time.monotonic()>deadline:
                self.stop()
                raise RuntimeError('raw capture readiness timeout')
            time.sleep(.02)

    def verify(self):
        if self.process.poll() is not None:
            raise RuntimeError('raw evidence capture stopped')

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait(timeout=5)
        self.stderr.close()
        if self.process.returncode not in (0,-15):
            raise RuntimeError('raw evidence capture failed')
        diagnostic = self.diagnostic_path.read_text()
        import re
        dropped = re.search(r'(\d+) packets dropped by kernel',diagnostic)
        if dropped is None or int(dropped.group(1)):
            raise RuntimeError('raw evidence kernel drops or missing statistics: '+diagnostic)
