# app/simple_server.py
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from concurrent.futures import ProcessPoolExecutor
import time
import os
import math
import threading
import multiprocessing
import queue
import uuid
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


_work_channel = None
_work_sequence = None
_work_losses = None
_work_lock = None
_computation = None


def _worker_instrumentation(channel, sequence, losses, lock):
    global _work_channel, _work_sequence, _work_losses, _work_lock
    _work_channel, _work_sequence, _work_losses, _work_lock = channel, sequence, losses, lock


def _worker_event(kind, operation_id, **fields):
    with _work_lock:
        _work_sequence.value += 1
        event = dict(kind=kind, operation_id=operation_id, worker_sequence=_work_sequence.value,
                     at=fields.get('work_finished_at', time.monotonic()), **fields)
        event.setdefault('worker_clock', clock_metadata())
        try:
            _work_channel.put_nowait(event)
        except (queue.Full, OSError, ValueError):
            _work_losses.value += 1


def _observed_work(work_units, operation_id):
    _worker_event('work_started', operation_id)
    try:
        result = _timed_burn_cpu(work_units)
    except BaseException as exc:
        _worker_event('work_failed', operation_id, error_type=type(exc).__name__)
        raise
    _worker_event('work_completed', operation_id, **result)
    return result


class ComputationObservation:
    """Bounded worker IPC feeding the existing writer; no worker disk writes.

    Snapshot cuts the worker sequence under its lock, then waits at most one
    second for that prefix. A missing prefix is an observation failure.
    """
    def __init__(self, writer, capacity=4096):
        self.writer = writer
        self.channel = multiprocessing.Queue(capacity)
        self.sequence = multiprocessing.Value('q', 0)
        self.losses = multiprocessing.Value('q', 0)
        self.worker_lock = multiprocessing.RLock()
        self.lock = threading.RLock()
        self.operations = {}
        self.seen = set()
        self.errors = []
        self.closed = False
        self.limit = None
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._consume, daemon=True)
        self.thread.start()
        writer.before_stop = self.close

    def initializer_args(self):
        return self.channel, self.sequence, self.losses, self.worker_lock

    def _emit(self, kind, identity, **fields):
        self.writer.emit(kind, **identity, **fields)

    def submit(self, pool, units, identity):
        with self.lock:
            if self.closed or self.limit is not None:
                return pool.submit(_timed_burn_cpu, units)  # Outside the recorded horizon.
            operation_id = identity['operation_id']
            self.operations[operation_id] = dict(identity=identity, state='waiting')
            submitted_at = time.monotonic()
            try:
                future = pool.submit(_observed_work, units, operation_id)
            except BaseException as exc:
                self.operations[operation_id]['state'] = 'submission_failed'
                self._emit('work_submission_failed', identity, error_type=type(exc).__name__)
                raise
            self._emit('work_submitted', identity, at=submitted_at)
            def done(result):
                # A worker crash has no guaranteed terminal IPC event. Keep it
                # explicitly unresolved, rather than fabricating completion.
                if result.cancelled() or (result.exception() is not None and
                        type(result.exception()).__name__ == 'BrokenProcessPool'):
                    with self.lock:
                        if not self.closed:
                            self.errors.append('executor_lost:' + operation_id)
                            self._emit('work_execution_unresolved', identity)
            future.add_done_callback(done)
            return future

    def _consume(self):
        while not self.stop.is_set():
            try:
                event = self.channel.get(timeout=.02)
            except queue.Empty:
                continue
            with self.lock:
                seq = event['worker_sequence']
                if event.get('worker_clock', {}).get('time_namespace') != clock_metadata()['time_namespace']:
                    self.errors.append('worker_clock_not_comparable')
                if self.closed or (self.limit is not None and seq > self.limit):
                    continue
                if seq in self.seen:
                    self.errors.append('duplicate_worker_event'); continue
                self.seen.add(seq)
                op = self.operations.get(event['operation_id'])
                if op is None:
                    self.errors.append('unknown_operation'); continue
                kind = event.pop('kind')
                expected = 'waiting' if kind == 'work_started' else 'running'
                if op['state'] != expected:
                    self.errors.append('invalid_transition:' + event['operation_id'])
                op['state'] = 'running' if kind == 'work_started' else 'completed' if kind == 'work_completed' else 'failed'
                identity = dict(op['identity']); event.pop('operation_id')
                self._emit(kind, identity, **event)

    def close(self):
        with self.lock:
            if self.closed:
                return
            with self.worker_lock:
                self.limit = self.sequence.value
                cutoff = time.monotonic()
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            with self.lock:
                if len(self.seen) >= self.limit:
                    break
            time.sleep(.005)
        with self.lock:
            self.closed = True
            complete = not self.errors and self.losses.value == 0 and self.seen == set(range(1, self.limit+1))
            counts = {}
            for op in self.operations.values():
                cls = op['identity']['traffic_class']
                group = counts.setdefault(cls, dict(waiting=0,running=0,completed=0,failed=0,submission_failed=0))
                group[op['state']] += 1
            for group in counts.values():
                group['pending'] = group['waiting'] + group['running']
                group['submitted'] = group['pending'] + group['completed'] + group['failed']
                group['started'] = group['running'] + group['completed'] + group['failed']
            self.writer.observation_complete = complete
            self.writer.emit('computation_observation_closed', at=cutoff, counts=counts,
                observation_complete=complete, worker_events_expected=self.limit,
                worker_events_received=len(self.seen), ipc_losses=self.losses.value, errors=self.errors,
                ingress_closed=False, pending=[dict(op['identity'],state=op['state'])
                    for op in self.operations.values() if op['state'] in ('waiting','running')])
        self.stop.set()
        self.thread.join(timeout=.1)


def _handler_event(kind, at, timeline):
    if _computation is None:
        _diagnostics.emit(kind, at=at, **timeline)
    else:
        with _computation.lock:
            if _computation.limit is None and not _computation.closed:
                _diagnostics.emit(kind, at=at, **timeline)


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
            operation_id=uuid.uuid4().hex, source_id=self.headers.get('X-Edos-Source-Id'),
            event_id=self.headers.get('X-Edos-Event-Id'),
            attack_mechanism=self.headers.get('X-Edos-Attack-Mechanism'),
            traffic_class=self.headers.get('X-Edos-Traffic-Class', 'unknown'),
            phase=self.headers.get('X-Edos-Phase'),endpoint=self.path.split('?',1)[0],
            run_id=self.headers.get('X-Edos-Run-Id'),http_status=None,error_type=None)
        if not timeline['run_id'] or not timeline['request_id'] or timeline['traffic_class'] not in ('benign','attack') or (timeline['traffic_class']=='attack' and not timeline['event_id']):
            timeline['traffic_class'] = 'unknown'
        with _handlers_lock:
            _active_handlers += 1
            timeline['active_handlers_at_start'] = _active_handlers
        _handler_event('handler_started', timeline['handler_started_at'], timeline)
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
            _handler_event('handler_finished', timeline['handler_finished_at'], timeline)

    def _serve(self, timeline=None):
        work_units, processing_time = request_workload(self.path)

        t0 = time.perf_counter()

        if timeline is None:
            _pool.submit(_burn_cpu, work_units).result()
        else:
            timeline['work_submitted_at'] = time.monotonic()
            if _computation is None:
                timeline.update(_pool.submit(_timed_burn_cpu, work_units).result())
            else:
                identity = {k:timeline[k] for k in ('operation_id','run_id','source_id','request_id','event_id','traffic_class','endpoint','attack_mechanism')}
                timeline.update(_computation.submit(_pool, work_units, identity).result())
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
    if _diagnostics:
        _computation = ComputationObservation(_diagnostics, int(os.getenv('EDOS_DIAGNOSTIC_CAPACITY','4096')))
        _pool = ProcessPoolExecutor(max_workers=pool_size, initializer=_worker_instrumentation,
                                    initargs=_computation.initializer_args())
    else:
        _pool = ProcessPoolExecutor(max_workers=pool_size)

    httpd = ThreadingHTTPServer(('', server_port), SimpleAppHandler)
    print(f"Simple app server running on port {server_port} (threading + persistent process pool, pool_size={pool_size})")
    httpd.serve_forever()
