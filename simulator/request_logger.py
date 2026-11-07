"""One row per HTTP attempt; generator identity is the class source of truth."""
import csv
import threading
import json

from simulator.ground_truth import encode_event_ids

REQUEST_FIELDS = [
    'run_id', 'request_id', 'generator', 'worker_id', 'target_url',
    'timestamp', 'elapsed_seconds', 'end_timestamp', 'end_elapsed_seconds',
    'duration_ms', 'traffic_class', 'attack_active', 'attack_id', 'event_id',
    'active_event_ids', 'http_status', 'outcome', 'error_type',
]
RTT_FIELDS = ['timestamp', 'rtt', 'run_id', 'request_id', 'traffic_class', 'elapsed_seconds']


class RequestLogger:
    def __init__(self, ground_truth, output_csv, routing_log=None, source_id=None, journal=None):
        self.source_id = source_id
        self.journal = journal
        self.ground_truth = ground_truth
        self.output_csv = output_csv
        self._lock = threading.Lock()
        self._next_id = 0
        self._pending = {}
        self._rtts = []
        self._closed = False
        self.routing_log = routing_log
        self.diagnostics = None
        if routing_log is not None:
            open(routing_log, 'w').close()
        with open(output_csv, 'w', newline='') as f:
            csv.DictWriter(f, fieldnames=REQUEST_FIELDS).writeheader()

    def begin(self, generator, worker_id, target_url, event_id=None, admit_if=None, admission_id=None):
        traffic_class = {'normal': 'benign', 'attack': 'attack'}[generator]
        if (generator == 'attack') != (event_id is not None):
            raise ValueError('only attack attempts must identify their originating event')
        with self._lock:
            if self._closed:
                raise RuntimeError('request log finalized')
            if admission_id is not None:
                beginning = self.ground_truth.begin_request(event_id, admission_id=admission_id)
            elif admit_if is None:
                beginning = self.ground_truth.begin_request(event_id)
            else:
                beginning = self.ground_truth.begin_request(event_id, admit_if=admit_if)
            if beginning is None:
                return None
            timestamp, elapsed, active, ids = beginning
            self._next_id += 1
            row = dict.fromkeys(REQUEST_FIELDS, None)
            row.update(run_id=self.ground_truth.run_id, request_id=(f'request_{self.source_id}_{self._next_id:09d}' if self.source_id else f'request_{self._next_id:09d}'),
                       generator=generator, worker_id=worker_id, target_url=target_url,
                       timestamp=timestamp, elapsed_seconds=elapsed, traffic_class=traffic_class,
                       attack_active=active, event_id=event_id, active_event_ids=encode_event_ids(ids))
            if event_id is not None:
                row['attack_id'] = self.ground_truth.event(event_id)['attack_id']
            self._pending[row['request_id']] = row
            if self.journal:
                self.journal("request_begin", dict(row, **({"admission_id": admission_id} if admission_id else {})))
            if self.diagnostics:
                self.diagnostics.http_event('http_started', row, self.ground_truth.clock.monotonic_initial)
            return row.copy()

    def instrumentation_headers(self, attempt):
        """Declared experimental identity only; never affects request admission."""
        if not attempt:
            return {'X-Edos-Request-Id': ''}
        values = {k: attempt.get(k) for k in ('run_id', 'request_id', 'event_id', 'traffic_class')}
        values['source_id'] = self.source_id
        if values['traffic_class'] == 'attack':
            from urllib.parse import urlsplit
            endpoint = urlsplit(attempt.get('target_url', '')).path
            values['attack_mechanism'] = {'/expensive':'computational_asymmetry', '/medium':'http_request_flooding'}.get(endpoint, 'unspecified')
        return {'X-Edos-' + k.replace('_', '-').title(): str(v)
                for k, v in values.items() if v is not None}

    def finish(self, attempt, response=None, error=None, end_sample=None):
        from requests.exceptions import RequestException
        end_timestamp, end_elapsed = end_sample or self.ground_truth.clock.sample()
        with self._lock:
            row = self._pending.pop(attempt['request_id'], None)
            if row is None:  # finalized incomplete attempts cannot acquire fabricated ends
                return None
            row.update(end_timestamp=end_timestamp, end_elapsed_seconds=end_elapsed,
                       duration_ms=(end_elapsed - row['elapsed_seconds']) * 1000,
                       http_status=getattr(response, 'status_code', None),
                       outcome=('transport_error' if isinstance(error, RequestException) else 'client_error') if error else
                               'http_error' if getattr(response, 'status_code', 0) >= 400 else 'response',
                       error_type=type(error).__name__ if error else None)
            if self.diagnostics:
                self.diagnostics.http_event('http_finished', row, self.ground_truth.clock.monotonic_initial)
            if self.journal:
                self.journal("request_finish", row)
            self._append(row)
            if error is None and row['outcome'] == 'response':
                self._rtts.append(dict(timestamp=end_timestamp, rtt=row['duration_ms'],
                                       run_id=row['run_id'], request_id=row['request_id'],
                                       traffic_class=row['traffic_class'], elapsed_seconds=end_elapsed))
            if row['event_id'] is not None:
                self.ground_truth.finish_request(row['event_id'], end_elapsed)
            # Operational response evidence is separate from scientific schemas/classes.
            if self.routing_log is not None and response is not None:
                with open(self.routing_log, 'a') as stream:
                    stream.write(json.dumps(dict(run_id=row['run_id'], request_id=row['request_id'],
                                                 response_body=response.text, http_status=response.status_code)) + '\n')
            return row.copy()

    def finalize(self):
        with self._lock:
            for row in self._pending.values():
                row.update(outcome='incomplete')
                self._append(row)
            complete = not self._pending
            self._pending.clear()
            self._closed = True
            return complete

    def save_rtt(self, filename):
        with self._lock, open(filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=RTT_FIELDS)
            writer.writeheader()
            writer.writerows(self._rtts)

    def _append(self, row):
        with open(self.output_csv, 'a', newline='') as f:
            csv.DictWriter(f, fieldnames=REQUEST_FIELDS).writerow(row)
