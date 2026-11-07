"""Focused certification corruption tests; no Docker or traffic generation."""
import copy
import unittest
from simulator.source_aggregate import identified_admission_errors
from tests import test_dataset_validation as fixtures


def record(kind, token='a', source='attack_1', event='E', **fields):
    return dict(kind=kind, source_id=source, payload=dict(admission_id=token, event_id=event, elapsed_seconds=3, **fields))


def started():
    return [record('admission'), record('task_resolution', decision='started'), record('request_begin')]


def discarded():
    return [record('admission'), record('task_resolution', decision='expired_before_http'),
            record('abandoned_admission', reason='expired_before_http')]


class IndividualReconciliationTests(unittest.TestCase):
    def test_valid_started_and_discarded(self):
        for rows in (started(), discarded()): self.assertEqual(identified_admission_errors(rows), [])
    def test_missing_abandonment(self):
        self.assertIn('discard without abandoned_admission', str(identified_admission_errors(discarded()[:2])))
    def test_duplicate_abandonment(self):
        rows=discarded(); rows.append(copy.deepcopy(rows[-1]))
        self.assertIn('duplicate abandoned_admission', str(identified_admission_errors(rows)))
    def test_orphan_abandonment(self):
        self.assertIn('abandonment without admission', str(identified_admission_errors(discarded()[2:])))
    def test_started_and_abandoned(self):
        self.assertIn('started admission abandoned', str(identified_admission_errors(started()+discarded()[2:])))
    def test_reason_mismatch(self):
        rows=discarded(); rows[-1]['payload']['reason']='rejected_before_http'
        self.assertIn('reason mismatch',str(identified_admission_errors(rows)))
    def test_event_and_source_mismatch(self):
        for kind, rows in [('abandoned_admission',discarded()), ('request_begin',started())]:
            for key,value in [('event_id','other'), ('source_id','other')]:
                sample=copy.deepcopy(rows)
                if key=='source_id': sample[-1][key]=value
                else: sample[-1]['payload'][key]=value
                self.assertTrue(identified_admission_errors(sample), (kind,key))
    def test_aggregate_counts_cannot_hide_wrong_links(self):
        rows=started()+[record('admission','b'),record('task_resolution','b',decision='expired_before_http'),
                        record('abandoned_admission','a',reason='expired_before_http')]
        self.assertTrue(identified_admission_errors(rows))
    def test_duplicate_resolution_begin_and_unresolved(self):
        for rows in (started()+[started()[1]], started()+[started()[2]], [record('admission')]):
            self.assertTrue(identified_admission_errors(rows))
    def test_historical_unidentified_journal(self):
        rows=discarded()
        for r in rows: r['payload'].pop('admission_id')
        self.assertEqual(identified_admission_errors(rows),[])


class ScheduledWindowIntegrationTests(unittest.TestCase):
    setUp = fixtures.ScientificValidationTests.setUp
    put_json = staticmethod(fixtures.ScientificValidationTests.put_json)
    put_csv = staticmethod(fixtures.ScientificValidationTests.put_csv)
    refresh = fixtures.ScientificValidationTests.refresh
    json_change = fixtures.ScientificValidationTests.json_change
    csv_change = fixtures.ScientificValidationTests.csv_change
    report = fixtures.ScientificValidationTests.report

    def configure_contract(self, start, marker=True):
        self.json_change('metadata/effective_config.json',lambda c:c['attack'].update(profile='continuous',burst=None))
        if marker:
            self.json_change('metadata/run_status.json',lambda s:s.update(offensive_start_contract='scheduled-half-open-v1'))
        self.csv_change('raw/service/request_log.csv','requests',lambda rows:rows[2].update(
            elapsed_seconds=start,timestamp=100+start,end_elapsed_seconds=7,end_timestamp=107,duration_ms=(7-start)*1000))
        self.csv_change('raw/service/rtt_log.csv','rtt',lambda rows:rows[2].update(timestamp=107,elapsed_seconds=7,rtt=(7-start)*1000))
        self.csv_change('raw/attacks/attack_events.csv','attacks',lambda rows:rows[0].update(
            profile='continuous',actual_start_seconds=min(start,2.2),last_request_start_seconds=max(start,2.2),
            actual_end_seconds=6.5,drained_end_seconds=7))
    def window_check(self):
        return next(c for c in self.report()['checks'] if c['check_id']=='CONTINUOUS_SCHEDULED_START_WINDOW')
    def test_window_boundaries(self):
        # Export/parse and invoke the real validator for each boundary.
        for start,valid in [(2,True),(1.999,False),(5.999,True),(6,False),(6.1,False)]:
            with self.subTest(start=start):
                self.configure_contract(start)
                self.assertEqual(self.window_check()['passed'],valid)
                if not valid: self.assertFalse(self.report()['dataset_valid'])
    def test_valid_start_late_completion(self):
        self.configure_contract(5.999)
        self.assertTrue(self.window_check()['passed'])
    def test_legacy_still_checks_effective_timeline(self):
        fixtures.ScientificValidationTests.test_continuous_queued_start_after_planned_end_allowed(self)
        self.assertFalse(any(c['check_id']=='CONTINUOUS_SCHEDULED_START_WINDOW' for c in self.report()['checks']))

    def test_identified_journal_enables_contract_without_marker(self):
        import json
        from experiments.dataset_provenance import sha256_file
        self.configure_contract(6.1, marker=False)
        relative='evidence/sources/attack_1/output/journal.jsonl'
        path=self.dataset/relative; path.parent.mkdir(parents=True,exist_ok=True)
        row=record('admission',event='event1')
        row.update(run_id='run1',sequence=1)
        path.write_text(json.dumps(row)+'\n')
        mp=self.dataset/'dataset_manifest.json'; manifest=json.loads(mp.read_text())
        manifest['files'].append(dict(path=relative,sha256=sha256_file(path),bytes=path.stat().st_size))
        self.put_json(mp,manifest)
        self.assertFalse(self.window_check()['passed'])
        self.assertFalse(self.report()['dataset_valid'])
