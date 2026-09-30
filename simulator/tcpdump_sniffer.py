# tcpdump_realtime_sniffer.py
import subprocess
import threading
import csv
import time
import re
from typing import Optional

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
    def __init__(self, interface: str, output_csv: str, simulation_start_time: float,
                 port_range: Optional[tuple] = None):
        self.interface = interface
        self.output_csv = output_csv
        self.process: Optional[subprocess.Popen] = None
        self.thread: Optional[threading.Thread] = None
        self.running = False
        self.current_label = "benign"
        self.label_lock = threading.Lock()
        self.simulation_start_time = simulation_start_time
        # (min_port, max_port) dos containers alvo: restringe a captura a
        # essas portas via filtro BPF, em vez de depender de qual interface
        # de rede é escolhida (ver start()).
        self.port_range = port_range
        self._init_csv()
    
    def set_label(self, label: str):
        with self.label_lock:
            self.current_label = label
        print(f"[Sniffer] Label set to: {label}")


    def _init_csv(self):
        with open(self.output_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "src_ip",
                "src_port",
                "dst_ip",
                "dst_port",
                "packet_length",
                "label"
            ])
    

    def start(self):
        if self.running:
            print("[Sniffer] Realtime tcpdump already running.")
            return

        # -i any: a captura roda no host (fora dos containers), e o tráfego
        # do simulador contra "http://localhost:<porta>" trafega pela
        # interface de loopback (lo), não pela bridge Docker (br-xxxx) — só
        # o lado do container é que aparece nela. Uma interface Docker
        # específica ficaria cega para esse tráfego, então "any" é
        # intencional aqui, não um placeholder. O escopo é restrito via
        # filtro de portas (BPF) abaixo em vez de por interface, o que
        # também evita depender de um nome de bridge gerado dinamicamente
        # pelo Docker (muda se a rede for recriada).
        bpf_filter = "tcp"
        if self.port_range:
            lo, hi = self.port_range
            bpf_filter = f"tcp and portrange {lo}-{hi}"

        cmd = [
            "tcpdump",
            "-i", self.interface,
            "-l",
            "-n",
            "-tt",
            "-q",     # saída mais simples
            bpf_filter
            ]

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1
        )

        self.running = True
        self.thread = threading.Thread(
            target=self._reader_loop,
            daemon=True
        )
        self.thread.start()

        print(f"[Sniffer] Realtime tcpdump started on {self.interface}")

    def _reader_loop(self):
        while self.running and self.process and self.process.stdout:
            line = self.process.stdout.readline()
            if not line:
                break

            
            match = TCPDUMP_REGEX.search(line)
            if not match:
                continue

            data = match.groupdict()
            self._write_row(data)
        

    def _write_row(self, data):
        with open(self.output_csv, "a", newline="") as f:
            writer = csv.writer(f)
            with self.label_lock:
                label = self.current_label

            writer.writerow([
                time.time() - self.simulation_start_time,
                data["src_ip"],
                int(data["src_port"]),
                data["dst_ip"],
                int(data["dst_port"]),
                int(data["length"]),
                label
            ])

    def stop(self):
        if not self.running:
            return

        self.running = False

        if self.process:
            self.process.terminate()
            self.process.wait()

        if self.thread:
            self.thread.join(timeout=2)

        print("[Sniffer] Realtime tcpdump stopped.")
