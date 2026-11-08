import time
import threading
import json
import math
import os
from pathlib import Path
from collections import deque
from typing import Dict, List, Optional, Tuple
import docker
from simulator import config

from simulator.experiment_config import MonitoringConfig
from simulator.cpu_observations import CONTRACT, MARKER, SUMMARY, delta, next_slot

class StatsCollector:
    """
    Thread que coleta docker stats periodicamente e guarda num cache thread-safe.
    O loop principal lê somente desse cache (sem fazer chamadas ao Docker).
    """
    def __init__(self, client: Optional[docker.DockerClient] = None, poll_interval: float = MonitoringConfig().stats_poll_interval_seconds,
                 history_seconds: float = MonitoringConfig().history_seconds):
        self.client = client or docker.from_env(environment={'DOCKER_HOST': config.DOCKER_ENGINE_SOCKET})
        self.poll_interval = poll_interval
        self.history_seconds = history_seconds  # quanto histórico de amostras manter por container

        self._container_ids: List[str] = []  # lista de IDs (ou names) a monitorar
        self._cache: Dict[str, dict] = {}    # id -> métricas calculadas (leitura mais recente)
        self._history: Dict[str, deque] = {}  # id -> deque de (timestamp, cpu_percent, mem_app_mb, name)
        self._lock = threading.Lock()
        self._stop_evt = threading.Event()
        self.evidence_path = None
        self.clock = None
        self.run_id = None
        self.dedicated_client = False
        self.request_timeout = 2.0
        self._references = {}
        self._sequence = 0
        self.failure = None
        self.timing_diagnostics = None
        self._summary = dict(attempts=0, snapshots=0, missed_opportunities=0)

        self._t = threading.Thread(target=self._run, name="DockerStatsCollector", daemon=True)

    # --------- API pública ---------
    def start(self):
        self._t.start()

    def stop(self, timeout: Optional[float] = None):
        self._stop_evt.set()
        self._t.join(timeout=2*self.request_timeout+2 if timeout is None else timeout)
        if self._t.is_alive():
            raise RuntimeError('stats collector thread still alive; shutdown unconfirmed')
        if self.failure:
            raise RuntimeError('stats collector failed: ' + self.failure)

    def bind_cpu(self, run_id, clock, path):
        """Declare the prospective contract before starting; never overwrite evidence."""
        if self._t.is_alive() or self.evidence_path is not None:
            raise RuntimeError('CPU evidence already bound')
        self.run_id, self.clock, self.evidence_path = run_id, clock, Path(path)
        marker = dict(contract=CONTRACT, schema_version=1, run_id=run_id,
                      container_ids=self._copy_ids(), origin_monotonic=clock.monotonic_initial,
                      origin_epoch=clock.epoch_initial, interval_seconds=self.poll_interval,
                      scheduling_lead_seconds=0.025, bounds='monotonic acquisition brackets',
                      samples=self.evidence_path.name, summary=SUMMARY)
        with (self.evidence_path.parent/MARKER).open('x') as stream:
            json.dump(marker, stream, allow_nan=False); stream.flush(); os.fsync(stream.fileno())

    def bind_timing_diagnostics(self, path, max_records=2048):
        """Opt in before start/bind completion; separate, non-scientific output."""
        if self._t.ident is not None or self.timing_diagnostics is not None:
            raise RuntimeError('Timing diagnostics must be bound once before start')
        if self.evidence_path is None:
            raise RuntimeError('Bind scientific CPU evidence first')
        from simulator.cpu_diagnostics import CPUTimingDiagnostics
        self.timing_diagnostics = CPUTimingDiagnostics(path, max_records)

    def _on_acquisition(self, container, stats, received_monotonic):
        """Hook for freshness adapters; called only for genuinely advancing snapshots."""

    def update_containers(self, containers: List):
        """
        Recebe objetos docker.Container OU strings (IDs/names).
        Guarda apenas os IDs para consulta interna.
        """
        ids = []
        for c in containers:
            ids.append(c.id if hasattr(c, "id") else str(c))
        with self._lock:
            self._container_ids = ids
            # remove do cache/histórico quem saiu
            self._cache = {cid: v for cid, v in self._cache.items() if cid in ids}
            self._history = {cid: v for cid, v in self._history.items() if cid in ids}
            self._references = {cid: v for cid, v in self._references.items() if cid in ids}

    def get_snapshot(self) -> Dict[str, dict]:
        """
        Retorna uma cópia rasa do cache: {container_id: {name, cpu_percent, mem_app_mb, raw_mem_usage, cache_mem}}
        """
        with self._lock:
            return {k: v.copy() for k, v in self._cache.items()}

    def get_averages(self, window_seconds: Optional[float] = None) -> Tuple[float, float, List[str]]:
        """
        Retorna (avg_cpu_percent, avg_mem_app_mb, container_names).

        Sem window_seconds: usa apenas a leitura mais recente de cada container
        (comportamento original — uma única amostra, útil para inspeção pontual).

        Com window_seconds: calcula a média de TODAS as amostras coletadas nos
        últimos `window_seconds`, para representar corretamente um intervalo de
        monitoramento inteiro (em vez de depender de qual amostra ~instantânea
        calhou de estar em cache no momento da chamada).
        """
        if window_seconds is None:
            snap = self.get_snapshot()
            if not snap:
                return 0.0, 0.0, []
            cpu = [v['cpu_percent'] for v in snap.values() if v.get('cpu_percent') is not None]
            mem = [v.get("mem_app_mb", 0.0) for v in snap.values()]
            names = [v.get("name", "") for v in snap.values()]
            return (sum(cpu) / len(cpu) if cpu else 0.0, sum(mem) / len(mem), names)

        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            container_ids = list(self._container_ids)
            histories = {cid: list(self._history.get(cid, [])) for cid in container_ids}
            cache_snapshot = {cid: self._cache.get(cid) for cid in container_ids}

        cpu_samples: List[float] = []
        mem_samples: List[float] = []
        names = set()
        for cid in container_ids:
            recent = [h for h in histories.get(cid, []) if h[0] >= cutoff]
            if not recent:
                # Sem amostras dentro da janela (ex.: poll_interval > window_seconds,
                # ou container recém-adicionado): cai para a última leitura conhecida.
                snap = cache_snapshot.get(cid)
                if snap:
                    recent = [(now, snap.get("cpu_percent", 0.0), snap.get("mem_app_mb", 0.0), snap.get("name", ""))]
            for _, cpu, mem, name in recent:
                cpu_samples.append(cpu)
                mem_samples.append(mem)
                if name:
                    names.add(name)

        if not cpu_samples:
            return 0.0, 0.0, []
        valid_cpu = [value for value in cpu_samples if value is not None]
        return (sum(valid_cpu) / len(valid_cpu) if valid_cpu else 0.0,
                sum(mem_samples) / len(mem_samples), list(names))

    # --------- Loop interno ---------
    def _run(self):
        stream = None
        missed_before = 0
        own_client = None
        try:
            if not math.isfinite(self.poll_interval) or self.poll_interval <= 0:
                raise ValueError('invalid stats interval')
            if self.dedicated_client:
                own_client = docker.DockerClient(base_url=config.DOCKER_ENGINE_SOCKET,
                                                timeout=self.request_timeout)
                self.client = own_client
            if self.evidence_path is not None:
                stream = Path(self.evidence_path).open('x', buffering=1)
            now = time.monotonic()
            origin = self.clock.monotonic_initial if self.clock else now
            scheduled = origin + (math.ceil((now-origin+0.025)/self.poll_interval)
                                  * self.poll_interval) - 0.025
            while not self._stop_evt.is_set():
                self._stop_evt.wait(max(0, scheduled-time.monotonic()))
                if self._stop_evt.is_set():
                    break
                for cid in self._copy_ids():
                    row, container, stats = self._acquire(cid, scheduled, origin)
                    row['missed_opportunities_before'] = missed_before
                    if stream:
                        if self.timing_diagnostics is None:
                            stream.write(json.dumps(row, allow_nan=False) + '\n')
                            stream.flush(); os.fsync(stream.fileno())
                        else:
                            timing = self.timing_diagnostics
                            diagnostic = timing.records[-1]
                            timing.mark(diagnostic, 'serialization_start')
                            encoded = json.dumps(row, allow_nan=False) + '\n'
                            timing.mark(diagnostic, 'serialization_end')
                            stream.write(encoded)
                            timing.mark(diagnostic, 'write_end')
                            stream.flush()
                            timing.mark(diagnostic, 'flush_end')
                            os.fsync(stream.fileno())
                            timing.mark(diagnostic, 'fsync_end')
                    if container is not None and stats is not None:
                        metrics = self._compute_metrics(container, stats)
                        if metrics is not None:
                            metrics['cpu_percent'] = float(row['cpu_percent']) if row['cpu_percent'] is not None else None
                            # Invalid/stale reads cannot refresh operational acquisition age.
                            metrics['read_ts'] = row['docker_read'] if row['fresh'] else None
                            metrics['received_monotonic'] = row['received_seconds'] + origin
                            with self._lock:
                                self._cache[cid] = metrics
                                hist = self._history.setdefault(cid, deque())
                                hist.append((metrics['received_monotonic'], metrics['cpu_percent'], metrics['mem_app_mb'], metrics['name']))
                                while hist and hist[0][0] < time.monotonic()-self.history_seconds:
                                    hist.popleft()
                        if row['fresh']:
                            self._on_acquisition(container, stats, row['received_seconds']+origin)
                scheduled, missed = next_slot(scheduled, time.monotonic(), self.poll_interval)
                self._summary['missed_opportunities'] += missed
                missed_before = missed
                if self.timing_diagnostics is not None:
                    self.timing_diagnostics.next_schedule(scheduled)
        except Exception as exc:
            self.failure = type(exc).__name__ + ': ' + str(exc)
        finally:
            if stream:
                try: stream.close()
                except Exception as exc: self.failure = self.failure or repr(exc)
            if own_client:
                try: own_client.close()
                except Exception as exc: self.failure = self.failure or repr(exc)
            if self.timing_diagnostics is not None:
                try: self.timing_diagnostics.finish(self.run_id, self.failure)
                except Exception as exc:
                    self.failure = (self.failure + '; ' if self.failure else '') + 'timing diagnostics: ' + repr(exc)
            if self.evidence_path is not None:
                try:
                    with (Path(self.evidence_path).parent/SUMMARY).open('x') as output:
                        json.dump(dict(schema_version=1, contract=CONTRACT, run_id=self.run_id,
                                       **self._summary, fatal_error=self.failure,
                                       worker_finished=True), output, allow_nan=False)
                        output.flush(); os.fsync(output.fileno())
                except Exception as exc:
                    self.failure = self.failure or repr(exc)

    def _acquire(self, cid, scheduled, origin):
        """One auditable attempt; API failures do not discard the last valid reference."""
        self._sequence += 1
        begin = time.monotonic()
        row = dict(schema_version=1, contract=CONTRACT, run_id=self.run_id,
                   sequence=self._sequence, container_id=cid, generation=None,
                   scheduled_seconds=scheduled-origin, call_start_seconds=begin-origin,
                   call_start_epoch=time.time(), snapshot_received=False, docker_read=None,
                   counters=None, error=None, delay_seconds=max(0, begin-scheduled))
        row['reference_invalidated'] = False
        container = stats = None
        timing = self.timing_diagnostics
        diagnostic = timing.begin(self._sequence, cid, scheduled, begin) if timing is not None else None
        if timing is not None:
            timing.mark(diagnostic, 'inspect_start')
        try:
            container = self.client.containers.get(cid)
            if timing is not None:
                timing.mark(diagnostic, 'inspect_end')
            if container.id != cid:
                raise ValueError('container identity changed')
            state = container.attrs['State']
            if state['Status'] != 'running':
                raise ValueError('victim not running')
            row['generation'] = dict(started_at=state['StartedAt'], restarts=container.attrs['RestartCount'])
            if not row['generation']['started_at']:
                raise ValueError('missing StartedAt')
            if timing is not None:
                timing.mark(diagnostic, 'validation_end')
            stats = container.stats(stream=False, one_shot=True)
            if timing is not None:
                timing.mark(diagnostic, 'stats_end')
            row.update(snapshot_received=True, docker_read=stats.get('read'))
            cpu = stats.get('cpu_stats', {})
            row['counters'] = dict(total_usage=cpu.get('cpu_usage', {}).get('total_usage'),
                                   system_cpu_usage=cpu.get('system_cpu_usage'),
                                   online_cpus=cpu.get('online_cpus') or len(cpu.get('cpu_usage', {}).get('percpu_usage', [])))
        except Exception as exc:
            if timing is not None:
                timing.mark(diagnostic, 'acquisition_exception')
            row['error'] = type(exc).__name__ + ': ' + str(exc)
            if isinstance(exc, docker.errors.NotFound) or isinstance(exc, ValueError):
                row['reference_invalidated'] = True
            if isinstance(exc, docker.errors.NotFound):
                with self._lock:
                    self._cache.pop(cid, None); self._history.pop(cid, None)
        row['call_end_epoch'] = time.time()
        row['call_end_seconds'] = time.monotonic()-origin
        row['received_seconds'] = row['call_end_seconds']
        row['monotonic'] = row['received_seconds']+origin  # compatibility for raw evidence readers
        row['duration_seconds'] = row['call_end_seconds']-row['call_start_seconds']
        if timing is not None:
            diagnostic['stamps']['received'] = row['received_seconds'] + origin
            diagnostic['acquisition_error'] = row['error']
            timing.mark(diagnostic, 'delta_start')
        derived, reference = delta(row, self._references.get(cid))
        if timing is not None:
            timing.mark(diagnostic, 'delta_end')
        row.update(derived)
        self._references[cid] = reference
        self._summary['attempts'] += 1
        self._summary['snapshots'] += int(row['snapshot_received'])
        # Keep memory/legacy analysis fields; scientific extraction uses raw counters.
        row['cpu_stats'] = stats.get('cpu_stats') if stats is not None else None
        return row, container, stats

    def _copy_ids(self) -> List[str]:
        with self._lock:
            return list(self._container_ids)

    @staticmethod
    def _compute_metrics(container, stats: dict) -> Optional[dict]:
        """
        Memory/cache compatibility hook. CPU is supplied by successive-read delta().
        """
        try:
            mem_usage = stats.get("memory_stats", {}).get("usage", 0) or 0
            cache_mem = stats.get("memory_stats", {}).get("stats", {}).get("cache", 0) or 0
            app_mem = max(mem_usage - cache_mem, 0)
            return {
                "id": container.id,
                "name": container.name,
                "cpu_percent": None,
                "mem_app_mb": app_mem / (1024 * 1024),
                "raw_mem_usage": mem_usage,
                "cache_mem": cache_mem,
                "read_ts": stats.get("read", None),
            }
        except Exception:
            return None

    @staticmethod
    def _calc_cpu_percent(stats: dict) -> float:
        """
        Historical formula helper, retained for audit/replay tests only.
        Active acquisition never uses implicit precpu_stats.
        """
        cpu_stats = stats.get("cpu_stats", {})
        precpu_stats = stats.get("precpu_stats", {})

        cpu_delta = float(cpu_stats.get("cpu_usage", {}).get("total_usage", 0)) - \
                    float(precpu_stats.get("cpu_usage", {}).get("total_usage", 0))
        system_delta = float(cpu_stats.get("system_cpu_usage", 0)) - \
                       float(precpu_stats.get("system_cpu_usage", 0))

        online_cpus = cpu_stats.get("online_cpus")
        if not online_cpus:
            online_cpus = len(cpu_stats.get("cpu_usage", {}).get("percpu_usage", []) or []) or 1

        if system_delta > 0.0 and cpu_delta > 0.0:
            return (cpu_delta / system_delta) * online_cpus * 100.0
        return 0.0
