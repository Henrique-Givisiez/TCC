import time
import threading
import json
from collections import deque
from typing import Dict, List, Optional, Tuple
import docker
from simulator import config

from simulator.experiment_config import MonitoringConfig

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

        self._t = threading.Thread(target=self._run, name="DockerStatsCollector", daemon=True)

    # --------- API pública ---------
    def start(self):
        self._t.start()

    def stop(self, timeout: Optional[float] = 2.0):
        self._stop_evt.set()
        self._t.join(timeout=timeout)

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
            cpu = [v.get("cpu_percent", 0.0) for v in snap.values()]
            mem = [v.get("mem_app_mb", 0.0) for v in snap.values()]
            names = [v.get("name", "") for v in snap.values()]
            return (sum(cpu) / len(cpu), sum(mem) / len(mem), names)

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
        return (sum(cpu_samples) / len(cpu_samples), sum(mem_samples) / len(mem_samples), list(names))

    # --------- Loop interno ---------
    def _run(self):
        while not self._stop_evt.is_set():
            ids = self._copy_ids()
            for cid in ids:
                try:
                    c = self.client.containers.get(cid)
                    stats = c.stats(stream=False)
                    metrics = self._compute_metrics(c, stats)
                    if metrics:
                        now = time.monotonic()
                        if self.evidence_path is not None:
                            with open(self.evidence_path, 'a') as evidence:
                                evidence.write(json.dumps(dict(monotonic=now, container_id=c.id,
                                    metrics=metrics, cpu_stats=stats.get('cpu_stats'),
                                    precpu_stats=stats.get('precpu_stats'))) + '\n')
                        with self._lock:
                            self._cache[cid] = metrics
                            hist = self._history.setdefault(cid, deque())
                            hist.append((now, metrics["cpu_percent"], metrics["mem_app_mb"], metrics["name"]))
                            cutoff = now - self.history_seconds
                            while hist and hist[0][0] < cutoff:
                                hist.popleft()
                except docker.errors.NotFound:
                    with self._lock:
                        self._cache.pop(cid, None)
                        self._history.pop(cid, None)
                except Exception:
                    # Evita derrubar o coletor por erro pontual de um contêiner
                    pass
            # pequeno sleep entre varreduras
            self._stop_evt.wait(self.poll_interval)

    def _copy_ids(self) -> List[str]:
        with self._lock:
            return list(self._container_ids)

    @staticmethod
    def _compute_metrics(container, stats: dict) -> Optional[dict]:
        """
        Calcula cpu_percent e memória (sem cache) a partir do payload do Docker.
        """
        try:
            cpu_percent = StatsCollector._calc_cpu_percent(stats)
            mem_usage = stats.get("memory_stats", {}).get("usage", 0) or 0
            cache_mem = stats.get("memory_stats", {}).get("stats", {}).get("cache", 0) or 0
            app_mem = max(mem_usage - cache_mem, 0)
            return {
                "id": container.id,
                "name": container.name,
                "cpu_percent": float(cpu_percent),
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
        Fórmula oficial (Docker) usando cpu_stats e precpu_stats.
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
