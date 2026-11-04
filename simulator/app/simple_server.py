# app/simple_server.py
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from concurrent.futures import ProcessPoolExecutor
import time
import os
import math
import threading
try:
    from simulator.diagnostics import DiagnosticWriter, clock_metadata
except ModuleNotFoundError:
    from diagnostics import DiagnosticWriter, clock_metadata

from urllib.parse import urlparse, parse_qs


# Server-owned CPU budgets. Neither query parameters nor legacy env defaults
# change these operations. Keep the same deterministic CPU kernel and pool.
OPERATION_WORK_UNITS = {
    "/light": 10000,
    "/medium": 100000,
    "/expensive": 1000000,
}


def request_workload(path):
    parsed = urlparse(path)
    if parsed.path in OPERATION_WORK_UNITS:
        return OPERATION_WORK_UNITS[parsed.path], 0.0
    # Historical catch-all paths retain query/env behavior for old experiments,
    # proxy readiness and protocol/network regression checks.
    default_work = int(os.getenv("WORK_UNITS", "1000000"))
    default_sleep = float(os.getenv("PROCESSING_TIME", "0"))
    qs = parse_qs(parsed.query)
    return (int(qs.get("work", [default_work])[0]),
            float(qs.get("sleep", [default_sleep])[0]))


def _burn_cpu(work_units):
    """
    Função de trabalho executada nos processos persistentes do pool (_pool).
    Precisa ser definida no nível do módulo para ser "picklable" pelo
    ProcessPoolExecutor.
    """
    for _ in range(work_units):
        _ = math.sqrt(123.456) * math.sin(123.456)


# Pool de processos persistente, criado uma única vez no startup do servidor
# (ver bloco __main__). Isso dá paralelismo real entre núcleos para o trabalho
# de CPU, sem pagar o custo de criar um processo novo a cada requisição.
_pool = None
_diagnostics = None
_handlers_lock = threading.Lock()
_active_handlers = 0
_worker_clock = None


def _timed_burn_cpu(work_units):
    # Return only fixed-size metadata; workers never write or share writer locks.
    global _worker_clock
    if _worker_clock is None:
        _worker_clock = clock_metadata()
    started = time.monotonic()
    cpu = time.process_time()
    _burn_cpu(work_units)
    cpu_end = time.process_time()
    return dict(work_started_at=started,work_finished_at=time.monotonic(),
                work_cpu_seconds=cpu_end-cpu,worker_clock=_worker_clock)


class SimpleAppHandler(BaseHTTPRequestHandler):
    # Habilita keep-alive (reaproveitamento de conexão TCP entre requisições).
    # Sem isso, cada requisição abre e fecha uma conexão nova, o que sob alta
    # taxa de requisições esgota as portas efêmeras/tabela de conexões do
    # ambiente (sockets em TIME_WAIT se acumulam mais rápido do que expiram).
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        global _active_handlers
        if _diagnostics is None:
            return self._serve()
        timeline = dict(handler_started_at=time.monotonic(),request_id=self.headers.get('X-Edos-Request-Id'),
            phase=self.headers.get('X-Edos-Phase'),endpoint=self.path.split('?',1)[0],
            run_id=None,http_status=None,error_type=None)
        with _handlers_lock:
            _active_handlers += 1
            timeline['active_handlers_at_start'] = _active_handlers
        _diagnostics.emit('handler_started',at=timeline['handler_started_at'],**timeline)
        try:
            return self._serve(timeline)
        except BaseException as exc:
            timeline['error_type'] = type(exc).__name__
            raise
        finally:
            timeline['handler_finished_at'] = time.monotonic()
            with _handlers_lock:
                _active_handlers -= 1
                timeline['active_handlers_at_finish'] = _active_handlers
            _diagnostics.emit('handler_finished',at=timeline['handler_finished_at'],**timeline)

    def _serve(self, timeline=None):
        work_units, processing_time = request_workload(self.path)

        t0 = time.perf_counter()

        if timeline is None:
            _pool.submit(_burn_cpu, work_units).result()
        else:
            timeline['work_submitted_at'] = time.monotonic()
            timeline.update(_pool.submit(_timed_burn_cpu, work_units).result())
            timeline['work_result_observed_at'] = time.monotonic()
        if processing_time > 0:
            time.sleep(processing_time)
        t1 = time.perf_counter()

        hostname = os.getenv("HOSTNAME", "unknown_container")
        body = f"host={hostname} work={work_units} sleep={processing_time:.4f}s elapsed={t1-t0:.4f}s\n".encode()

        # Content-Length é obrigatório com keep-alive (HTTP/1.1): sem ele o
        # cliente não tem como saber onde a resposta termina numa conexão
        # que continua aberta para a próxima requisição.
        self.send_response(200)
        if timeline is not None:
            timeline['http_status'] = 200
        self.send_header('Content-type', 'text/plain')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

if __name__ == '__main__':
    # Dentro do container, mantenha 80; no host você mapeia pra 8080
    server_port = int(os.getenv("APP_PORT", "80"))
    pool_size = int(os.getenv("INSTANCE_MAX_CONCURRENT_REQUESTS", "2"))
    diagnostic_path = os.getenv('EDOS_DIAGNOSTIC_PATH')
    if diagnostic_path:
        _diagnostics = DiagnosticWriter(diagnostic_path,
            capacity=int(os.getenv('EDOS_DIAGNOSTIC_CAPACITY','4096')),
            context=dict(component='victim'),stop_path=os.getenv('EDOS_DIAGNOSTIC_STOP'))
    _pool = ProcessPoolExecutor(max_workers=pool_size)

    httpd = ThreadingHTTPServer(('', server_port), SimpleAppHandler)
    print(f"Simple app server running on port {server_port} (threading + persistent process pool, pool_size={pool_size})")
    httpd.serve_forever()
