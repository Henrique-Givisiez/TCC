"""Optional bounded, in-memory timings; never scientific CPU observations."""
import json
import os
import time
from pathlib import Path


class CPUTimingDiagnostics:
    def __init__(self, path, max_records=2048):
        self.path = Path(path)
        if not self.path.name.endswith('.cpu-timing-diagnostic.json'):
            raise ValueError('Use a distinct .cpu-timing-diagnostic.json file')
        if type(max_records) is not int or max_records <= 0:
            raise ValueError('Diagnostic capacity must be a positive integer')
        if self.path.exists():
            raise FileExistsError(self.path)
        self.max_records = max_records
        self.records = []
        self.pending = []

    def begin(self, sequence, container_id, scheduled, begin):
        if len(self.records) >= self.max_records:
            raise RuntimeError('CPU timing diagnostic capacity exhausted; no silent drops')
        record = dict(sequence=sequence, container_id=container_id,
                      scheduled_monotonic=scheduled, call_start_monotonic=begin,
                      schedule_delay_seconds=max(0, begin-scheduled), stamps={})
        self.records.append(record)
        self.pending.append(record)
        return record

    @staticmethod
    def mark(record, name):
        record['stamps'][name] = time.monotonic()

    def next_schedule(self, scheduled):
        observed = time.monotonic()
        for record in self.pending:
            record.update(next_scheduled_monotonic=scheduled,
                          schedule_observed_monotonic=observed,
                          remaining_until_next_seconds=scheduled-observed)
        self.pending.clear()

    def finish(self, run_id, failure):
        # Only after acquisition ends: no diagnostic serialization/file IO per tick.
        with self.path.open('x') as output:
            json.dump(dict(schema_version=1, kind='cpu_timing_diagnostic_non_scientific',
                           run_id=run_id, clock='host_monotonic_seconds',
                           capacity=self.max_records, records=self.records,
                           collection_complete=failure is None,
                           collector_failure=failure), output, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
