"""One local writer per source; emission closure is independent of HTTP drain."""
import json
import threading
from simulator.ground_truth import ExperimentClock, GroundTruth


class SharedClock(ExperimentClock):
    def __init__(self, epoch, monotonic):
        self.epoch_initial = epoch
        self.monotonic_initial = monotonic


class Journal:
    def __init__(self, path, source_id, run_id):
        self.path, self.source_id, self.run_id = path, source_id, run_id
        self.lock = threading.Lock()
        self.sequence = 0

    def __call__(self, kind, payload):
        with self.lock:
            self.sequence += 1
            record = dict(source_id=self.source_id, run_id=self.run_id,
                          sequence=self.sequence, kind=kind, payload=payload)
            with open(self.path, 'a') as stream:
                stream.write(json.dumps(record, separators=(',', ':')) + '\n')


class JournalGroundTruth(GroundTruth):
    def __init__(self, *args, journal, **kwargs):
        self.journal = journal
        super().__init__(*args, **kwargs)

    def _persist(self):
        super()._persist()
        for event in self._events.values():
            self.journal('event_snapshot', event.row.copy())

    def admit(self, event_id):
        with self._lock:
            admitted = super().admit(event_id)
            if admitted:
                self._record_admission(event_id, self.clock.elapsed())
            return admitted

    def _record_admission(self, event_id, elapsed):
        self.journal('admission', dict(event_id=event_id, elapsed_seconds=elapsed))

    def abandon_admission(self, event_id):
        with self._lock:
            super().abandon_admission(event_id)
            self.journal('abandoned_admission', dict(event_id=event_id, elapsed_seconds=self.clock.elapsed()))

    def begin_request(self, event_id=None, admit_if=None, admission_id=None):
        with self._lock:
            result = super().begin_request(event_id, admit_if=admit_if, admission_id=admission_id)
            if event_id is not None and result is not None:
                self.journal('event_snapshot', self.event(event_id))
            return result

    def _close_emission(self, event):
        previous = event.row['actual_end_seconds']
        super()._close_emission(event)
        if previous is None and event.row['actual_end_seconds'] is not None:
            self.journal('emission_closed', event.row.copy())
