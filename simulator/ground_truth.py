"""Per-run temporal ground truth, independent of observed service performance."""
import csv
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass

EVENT_FIELDS = [
    'schema_version', 'experiment_id', 'run_id', 'experiment_start_timestamp',
    'experiment_start_monotonic', 'attack_id', 'event_id', 'profile',
    'scheduled_start_seconds', 'scheduled_end_seconds', 'activation_requested_seconds',
    'actual_start_seconds', 'stop_requested_seconds', 'actual_end_seconds',
    'last_request_start_seconds', 'drained_end_seconds', 'status', 'end_reason',
]


class ExperimentClock:
    def __init__(self):
        self.monotonic_initial = time.monotonic()
        self.epoch_initial = time.time()

    def sample(self):
        return time.time(), time.monotonic() - self.monotonic_initial

    def elapsed(self):
        return time.monotonic() - self.monotonic_initial

    def from_epoch(self, timestamp):
        # tcpdump uses the wall clock, not Python's monotonic clock.
        return timestamp - self.epoch_initial


@dataclass
class AttackEvent:
    row: dict
    accepting: bool = False
    pending: int = 0
    in_flight: int = 0
    last_completion: float = None


class GroundTruth:
    def __init__(self, experiment_id, output_csv, clock=None, run_id=None):
        self.clock = clock or ExperimentClock()
        self.run_id = run_id or uuid.uuid4().hex
        self.experiment_id = experiment_id
        self.output_csv = output_csv
        self._events = {}
        self._lock = threading.RLock()
        self._admissions = {}
        self._admission_sequence = 0
        self._persist()

    def _task_record(self, kind, **payload):
        journal = getattr(self, 'journal', None)
        if journal:
            journal(kind, payload)

    def admit_continuous(self, event_id):
        """Identified admission on the absolute clock, without backpressure."""
        with self._lock:
            event = self._events[event_id]
            elapsed = self.clock.elapsed()
            if not event.accepting or not (event.row['scheduled_start_seconds'] <= elapsed < event.row['scheduled_end_seconds']):
                return None
            self._admission_sequence += 1
            token = 'admission_' + str(self._admission_sequence)
            self._admissions[token] = dict(event_id=event_id, state='pending')
            event.pending += 1
            self._task_record('admission', event_id=event_id, admission_id=token, elapsed_seconds=elapsed)
            return token

    def resolve_admission(self, event_id, admission_id, reason, elapsed=None):
        with self._lock:
            item = self._admissions[admission_id]
            if item['event_id'] != event_id or item['state'] != 'pending':
                raise RuntimeError('admission already resolved or event mismatch')
            elapsed = self.clock.elapsed() if elapsed is None else elapsed
            item['state'] = reason
            self._events[event_id].pending -= 1
            self._task_record('task_resolution', event_id=event_id, admission_id=admission_id,
                              decision=reason, elapsed_seconds=elapsed)
            self._task_record('abandoned_admission', event_id=event_id, admission_id=admission_id,
                              reason=reason, elapsed_seconds=elapsed)
            self._close_emission(self._events[event_id])
            self._persist()

    def plan_event(self, attack_id, event_id, profile, scheduled_start, scheduled_end):
        with self._lock:
            if event_id in self._events:
                raise ValueError('event_id must be unique within a run')
            row = dict.fromkeys(EVENT_FIELDS, None)
            row.update(schema_version=1, experiment_id=self.experiment_id, run_id=self.run_id,
                       experiment_start_timestamp=self.clock.epoch_initial,
                       experiment_start_monotonic=self.clock.monotonic_initial,
                       attack_id=attack_id, event_id=event_id, profile=profile,
                       scheduled_start_seconds=scheduled_start,
                       scheduled_end_seconds=scheduled_end, status='planned')
            self._events[event_id] = AttackEvent(row)
            self._persist()

    def activate(self, event_id):
        with self._lock:
            event = self._events[event_id]
            if event.row['status'] != 'planned':
                raise RuntimeError('event already activated or finalized')
            event.accepting = True
            event.row.update(activation_requested_seconds=self.clock.elapsed(), status='activated')
            self._persist()

    def admit(self, event_id):
        """Register before submit; admission and stop share this same lock."""
        with self._lock:
            event = self._events[event_id]
            if not event.accepting:
                return False
            event.pending += 1
            return True

    def abandon_admission(self, event_id):
        with self._lock:
            event = self._events[event_id]
            event.pending -= 1
            self._close_emission(event)
            self._persist()

    def _record_admission(self, event_id, elapsed):
        """Optional source journal hook; no change to scientific schemas."""

    def begin_request(self, event_id=None, admit_if=None, admission_id=None):
        with self._lock:
            timestamp, elapsed = self.clock.sample()
            if event_id is not None:
                event = self._events[event_id]
                if admission_id is not None:
                    if admit_if is not None:
                        raise ValueError('identified admission cannot admit twice')
                    item = self._admissions[admission_id]
                    if item['event_id'] != event_id or item['state'] != 'pending':
                        raise RuntimeError('admission already resolved or event mismatch')
                    start, end = event.row['scheduled_start_seconds'], event.row['scheduled_end_seconds']
                    reason = ('before_window' if elapsed < start else 'expired_before_http' if elapsed >= end
                              else 'stopped_before_http' if not event.accepting else None)
                    if reason:
                        self.resolve_admission(event_id, admission_id, reason, elapsed)
                        return None
                    item['state'] = 'started'
                    self._task_record('task_resolution', event_id=event_id, admission_id=admission_id,
                                      decision='started', elapsed_seconds=elapsed)
                if admit_if is not None:
                    # Admission and observed beginning use the SAME clock sample
                    # and event lock. Expired opportunities never become attempts.
                    if not event.accepting or not admit_if(elapsed):
                        return None
                    event.pending += 1
                    self._record_admission(event_id, elapsed)
                if event.pending <= 0:
                    raise RuntimeError('attack attempt must be admitted before it starts')
                event.pending -= 1
                event.in_flight += 1
                if event.row['actual_start_seconds'] is None:
                    event.row['actual_start_seconds'] = elapsed
                event.row['last_request_start_seconds'] = elapsed
                event.row['status'] = 'stopping' if not event.accepting else 'active'
            active, ids = self._context(elapsed)
            # Sample closure AFTER the beginning, preserving the last start inside
            # [actual_start, actual_end). No executor internals are changed.
            if event_id is not None:
                self._close_emission(event)
            return timestamp, elapsed, active, ids

    def finish_request(self, event_id, elapsed):
        with self._lock:
            event = self._events[event_id]
            event.in_flight -= 1
            event.last_completion = max(event.last_completion or elapsed, elapsed)
            self._close_emission(event)
            self._persist()

    def stop(self, event_id, reason='scheduled_end'):
        with self._lock:
            event = self._events[event_id]
            event.accepting = False
            if event.row['stop_requested_seconds'] is None:
                event.row.update(stop_requested_seconds=self.clock.elapsed(), end_reason=reason)
            self._close_emission(event)
            self._persist()

    def _close_emission(self, event):
        if event.accepting or event.pending:
            return
        row = event.row
        if row['actual_start_seconds'] is None:
            row['status'] = 'not_executed'
            return
        if row['actual_end_seconds'] is None:
            closure = self.clock.elapsed()
            if closure <= row['last_request_start_seconds']:
                return  # clock resolution cannot certify a distinct end yet
            row['actual_end_seconds'] = closure
        row['status'] = 'emission_ended'
        if event.in_flight == 0:
            row.update(drained_end_seconds=event.last_completion, status='completed')

    def finalize(self, reason='simulation_end', complete=True):
        with self._lock:
            for event_id, event in self._events.items():
                self.stop(event_id, reason)
                if (not complete or event.pending or event.in_flight or
                        (event.row['actual_start_seconds'] is not None and
                         event.row['actual_end_seconds'] is None)):
                    event.row['status'] = 'incomplete'
            self._persist()

    def _context(self, elapsed):
        ids, uncertain = [], False
        for event in self._events.values():
            row = event.row
            start, end = row['actual_start_seconds'], row['actual_end_seconds']
            if start is None:
                activation = row['activation_requested_seconds']
                if row['status'] == 'incomplete' and activation is not None and elapsed >= activation:
                    uncertain = True
                continue
            if elapsed < start or (end is not None and elapsed >= end):
                continue
            if end is None and row['status'] == 'incomplete' and elapsed > row['last_request_start_seconds']:
                uncertain = True
            else:
                ids.append(row['event_id'])
        return (1 if ids else None if uncertain else 0), ids

    def context(self, elapsed):
        with self._lock:
            return self._context(elapsed)

    def is_attack_active(self, elapsed_seconds):
        return self.context(elapsed_seconds)[0]

    def active_event_ids(self, elapsed_seconds):
        return self.context(elapsed_seconds)[1]

    def event(self, event_id):
        with self._lock:
            return self._events[event_id].row.copy()

    def persist(self):
        with self._lock:
            self._persist()

    def _persist(self):
        temporary = str(self.output_csv) + '.tmp'
        with open(temporary, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
            writer.writeheader()
            writer.writerows(event.row for event in self._events.values())
        os.replace(temporary, self.output_csv)


def encode_event_ids(ids):
    return json.dumps(ids, separators=(',', ':'))
