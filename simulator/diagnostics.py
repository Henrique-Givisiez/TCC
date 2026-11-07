"""Optional bounded diagnostic sidecar. Never an input to scientific features."""
import json
import os
from pathlib import Path
import queue
import threading
import time


def clock_metadata():
    info = time.get_clock_info('monotonic')
    try:
        namespace = os.readlink('/proc/self/ns/time')
    except OSError:
        namespace = None
    return dict(kind='CLOCK_MONOTONIC',unit='seconds',resolution_seconds=info.resolution,
                implementation=info.implementation,time_namespace=namespace,pid=os.getpid())


class DiagnosticWriter:
    def __init__(self, path, capacity=4096, context=None, stop_path=None):
        self.before_stop = None
        self.path = Path(path)
        try:self.path.parent.mkdir(parents=True,exist_ok=True)
        except OSError:pass
        self.queue = queue.Queue(maxsize=capacity)
        self.context = context or {}
        self.stop_path = Path(stop_path) if stop_path else None
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.counts = dict(offered=0,enqueued=0,written=0,dropped=0,write_errors=0)
        self.capacity = capacity
        self.clock = clock_metadata()
        self.thread = threading.Thread(target=self._write,name='DiagnosticWriter',daemon=True)
        self.thread.start()

    def emit(self, kind, at=None, **fields):
        record = dict(self.context,kind=kind,at=time.monotonic() if at is None else at,**fields)
        with self.lock:
            self.counts['offered'] += 1
            record['sequence'] = self.counts['offered']
            if self.stop.is_set():
                self.counts['dropped'] += 1
                return
            try:
                self.queue.put_nowait(record)
                self.counts['enqueued'] += 1
            except queue.Full:
                self.counts['dropped'] += 1

    def _write(self):
        stream = None
        try:
            stream = self.path.open('x',buffering=65536)
        except OSError:
            pass
        try:
            while not self.stop.is_set() or not self.queue.empty():
                if self.stop_path is not None and self.stop_path.exists():
                    if self.before_stop:
                        self.before_stop()
                    self.stop.set()
                try:
                    record = self.queue.get(timeout=.1)
                except queue.Empty:
                    if stream:
                        try:stream.flush()
                        except OSError:
                            with self.lock:self.counts['write_errors'] += 1
                    continue
                try:
                    if stream is None:raise OSError('diagnostic output unavailable')
                    stream.write(json.dumps(record,separators=(',',':'),allow_nan=False)+'\n')
                    with self.lock:self.counts['written'] += 1
                except (OSError,ValueError,TypeError):
                    with self.lock:self.counts['write_errors'] += 1
        finally:
            if stream:
                try:stream.close()
                except OSError:
                    with self.lock:self.counts['write_errors'] += 1
            with self.lock:
                summary = dict(schema_version=1,context=self.context,clock=self.clock,
                    capacity=self.capacity,**self.counts,queue_remaining=self.queue.qsize())
            summary['observation_complete'] = getattr(self, 'observation_complete', True)
            summary['complete'] = (summary['observation_complete'] and summary['offered']==summary['written'] and not summary['write_errors']
                                   and not summary['queue_remaining'])
            try:
                self.path.with_suffix('.summary.json').write_text(json.dumps(summary,indent=2)+'\n')
            except OSError:
                pass  # missing summary explicitly means unverified/incomplete diagnostics

    def close(self, timeout=3):
        if self.before_stop:
            self.before_stop()
        self.stop.set()
        self.thread.join(timeout)
        return not self.thread.is_alive()


class DiagnosticExecutor:
    """Observe public submit/Future/shutdown, without changing admission policy.

    `submitted_not_task_started` is an observed difference, not internal queue depth.
    """
    def __init__(self, executor, writer):
        self.executor,self.writer = executor,writer
        self.diagnostics = self
        self.local = threading.local()
        self.lock = threading.Lock()
        self.sequence = 0
        self.counts = dict(submitted=0,task_started=0,task_finished=0,cancelled=0,rejected=0)

    def _id(self):
        with self.lock:
            self.sequence += 1
            return str(self.sequence)

    def plan_wait(self, wait_started, interval):
        attempt_id = self._id()
        self.local.plan = dict(attempt_id=attempt_id,planned_at=wait_started+interval,
                               wait_started_at=wait_started,sampled_interval=interval)
        self.writer.emit('planned',at=wait_started,**self.local.plan)

    def _event(self, kind, attempt_id, at=None, **fields):
        with self.lock:
            if kind in self.counts:self.counts[kind] += 1
            counts = self.counts.copy()
        self.writer.emit(kind,at=at,attempt_id=attempt_id,counts=counts,**fields)

    def submit(self, fn, *args, **kwargs):
        plan = getattr(self.local,'plan',None)
        self.local.plan = None
        attempt_id = kwargs.get('admission_id') or (plan['attempt_id'] if plan else self._id())
        submitted = time.monotonic()
        self._event('submitted',attempt_id,at=submitted,
                    planned_at=plan['planned_at'] if plan else None,
                    target_url=args[1] if len(args)>1 and isinstance(args[1],str) else None)
        def execute():
            self.local.attempt_id = attempt_id
            self._event('task_started',attempt_id)
            error_type = None
            try:return fn(*args,**kwargs)
            except BaseException as exc:
                error_type = type(exc).__name__
                raise
            finally:
                self._event('task_finished',attempt_id,error_type=error_type)
                self.local.attempt_id = None
        try:
            future = self.executor.submit(execute)
        except BaseException as exc:
            self._event('rejected',attempt_id,error_type=type(exc).__name__)
            raise
        def done(result):
            if result.cancelled():self._event('cancelled',attempt_id)
        future.add_done_callback(done)
        return future

    def http_event(self, kind, row, origin):
        elapsed = row['elapsed_seconds'] if kind=='http_started' else row['end_elapsed_seconds']
        self.writer.emit(kind,at=origin+elapsed,attempt_id=getattr(self.local,'attempt_id',None),
            request_id=row['request_id'],elapsed_seconds=elapsed,target_url=row['target_url'],
            outcome=row.get('outcome'),http_status=row.get('http_status'),error_type=row.get('error_type'))

    def shutdown(self, *args, **kwargs):
        return self.executor.shutdown(*args,**kwargs)


def computational_state(events, at, *, observation_complete, ingress_closed=False):
    """Small lifecycle reducer, not an experimental recovery criterion.

    `at` is victim-monotonic time. A caller must establish a valid clock anchor
    before converting a global E, and prove ingress closure independently.
    """
    states, errors = {}, []
    transitions = {'work_submitted': ('absent', 'waiting'),
                   'work_started': ('waiting', 'running'),
                   'work_completed': ('running', 'completed'),
                   'work_failed': ('running', 'failed')}
    for e in sorted(events, key=lambda e: (e['at'], e.get('sequence', 0))):
        if e['at'] > at or e['kind'] not in transitions:
            continue
        key = e['operation_id']
        expected, state = transitions[e['kind']]
        previous = states.get(key, ('absent', 'unknown'))
        if previous[0] != expected:
            errors.append('invalid_transition:' + key)
        cls = e.get('traffic_class', 'unknown')
        states[key] = (state, cls)
    counts = {cls:dict(waiting=0,running=0,completed=0,failed=0,pending=0)
              for cls in ('benign','attack','unknown')}
    for state, cls in states.values():
        group = counts.get(cls, counts['unknown'])
        group[state] += 1
        group['pending'] += state in ('waiting','running')
    for group in counts.values():
        group['submitted'] = group['pending'] + group['completed'] + group['failed']
        group['started'] = group['running'] + group['completed'] + group['failed']
    closures = [e for e in events if e['kind'] == 'computation_observation_closed']
    reliable = observation_complete and not errors and all(e['observation_complete'] for e in closures)
    drainage = ('observation_incomplete' if not reliable else
                'drained_observed' if ingress_closed and counts['attack']['pending']==0 and counts['unknown']['pending']==0 else
                'not_observed')
    return dict(counts=counts, errors=errors, drainage=drainage)
