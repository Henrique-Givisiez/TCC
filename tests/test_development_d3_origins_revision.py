"""R2 emission/drain lifecycle fixtures and prospective authority regression."""
from copy import deepcopy
from pathlib import Path
import csv
import json
import tempfile
import unittest
from unittest.mock import patch

from experiments import development_d3_origins as c
from experiments import development_d3_origins_processing as processing
from experiments import development_d3_origins_revision as revision
from experiments import development_d3_origins_revision_ops as ops
from tests.test_development_d3 import fixture,put,csvwrite
from tests.test_development_d3_origins import origins_fixture
from tests import test_development_d3_origins as previous_tests
from simulator.ground_truth import EVENT_FIELDS


def in_flight_fixture(raw,entry):
    cfg=origins_fixture(raw,entry);changed={};events=[]
    for i in range(cfg.attack.attackers):
        sid=f'attack_{i+1}';out=raw/'source_artifacts'/sid/'output'
        event=c.base.old.csv_rows(out/'local_events.csv')[0]
        rows=c.base.old.csv_rows(out/'local_requests.csv');last=rows[-1]
        last.update(end_elapsed_seconds=float(event['actual_end_seconds'])+.05)
        last.update(end_timestamp=1000+last['end_elapsed_seconds'],duration_ms=(last['end_elapsed_seconds']-float(last['elapsed_seconds']))*1000)
        changed[last['request_id']]=last
        event['drained_end_seconds']=last['end_elapsed_seconds'];events.append(event)
        csvwrite(out/'local_events.csv',EVENT_FIELDS,[event])
        items=[json.loads(x) for x in (out/'journal.jsonl').read_text().splitlines()]
        finish=next(x for x in items if x['kind']=='request_finish' and x['payload']['request_id']==last['request_id'])
        items.remove(finish);finish['payload'].update({key:last[key] for key in ('end_elapsed_seconds','end_timestamp','duration_ms')})
        for item in items:
            if item['kind']=='emission_closed':item['payload']={**event,'status':'emission_ended','drained_end_seconds':None}
            elif item['kind']=='event_snapshot':item['payload']=dict(event)
        index=next(j for j,x in enumerate(items) if x['kind']=='emission_closed')
        items.insert(index+1,finish)
        for j,item in enumerate(items,1):item['sequence']=j
        (out/'journal.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in items))
    # Exact local/aggregate/RTT correspondence, changing only offensive finishes.
    for path in raw.rglob('*.csv'):
        if path.name not in ('local_requests.csv','request_log.csv','local_rtt.csv','rtt_log.csv'):continue
        with path.open(newline='') as stream:reader=csv.DictReader(stream);fields=reader.fieldnames;rows=list(reader)
        for row in rows:
            if row.get('request_id') not in changed:continue
            last=changed[row['request_id']]
            if 'outcome' in row:
                row.update({key:last[key] for key in ('end_elapsed_seconds','end_timestamp','duration_ms')})
            else:row.update(elapsed_seconds=last['end_elapsed_seconds'],timestamp=last['end_timestamp'],rtt=last['duration_ms'])
        csvwrite(path,fields,rows)
    global_event=dict(events[0]);global_event['actual_end_seconds']=max(float(e['actual_end_seconds']) for e in events)
    global_event['drained_end_seconds']=max(float(e['drained_end_seconds']) for e in events)
    csvwrite(raw/'attack_events.csv',EVENT_FIELDS,[global_event])
    return cfg


class RevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.control_raw=cls.root/'control';cfg=fixture(cls.control_raw,'C')
        cls.control=c.base.old.build_review(cls.control_raw,cfg)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_N1_N2_inflight_and_invalid_certificates(self):
        plan=c.read(revision.DEFAULT_MANIFEST)
        for entry in plan['entries'][:2]:
            raw=self.root/entry['id'];cfg=in_flight_fixture(raw,entry)
            report=c.assess_raw(raw,cfg,self.control_raw,self.control)
            self.assertTrue(report['classification']['technical_integrity'],report['technical_checks'])
            original_source=c.read(revision.DEFAULT_MANIFEST)['processing_revision']['archived_sources']['experiments/development_d3_origins_processing.py']['path']
            namespace=dict(processing.__dict__)
            exec(compile((c.ROOT/original_source).read_text(),original_source,'exec'),namespace)
            with patch.object(processing,'certify_event',namespace['certify_event']):
                self.assertFalse(c.assess_raw(raw,cfg,self.control_raw,self.control)['classification']['technical_integrity'])
            count=cfg.attack.attackers
            offense=next(x for x in report['generator']['nominal_start_adherence'] if x['traffic_class']=='attack')
            self.assertEqual([x['starts'] for x in offense['per_origin']],[960//count]*count)
            journal=raw/f'source_artifacts/attack_{count}/output/journal.jsonl';saved=journal.read_bytes()
            items=[json.loads(x) for x in saved.splitlines()]
            emitted=next(i for i,x in enumerate(items) if x['kind']=='emission_closed')
            final=max(i for i,x in enumerate(items) if x['kind']=='event_snapshot')
            def reject(mutator):
                bad=deepcopy(items);mutator(bad)
                for i,item in enumerate(bad,1):item['sequence']=i
                journal.write_text(''.join(json.dumps(x)+'\n' for x in bad))
                failed=c.assess_raw(raw,cfg,self.control_raw,self.control)
                self.assertFalse(failed['classification']['technical_integrity'],bad[emitted])
                journal.write_bytes(saved)
            with self.subTest(condition=entry['condition'],case='identity'):
                reject(lambda x:x[emitted]['payload'].update(run_id='wrong'))
            with self.subTest(condition=entry['condition'],case='emission-time'):
                reject(lambda x:x[emitted]['payload'].update(actual_end_seconds=270))
            with self.subTest(condition=entry['condition'],case='early-drain'):
                reject(lambda x:x[emitted]['payload'].update(drained_end_seconds=270.08))
            with self.subTest(condition=entry['condition'],case='premature-completed'):
                reject(lambda x:x[emitted]['payload'].update(status='completed',drained_end_seconds=x[final]['payload']['drained_end_seconds']))
            with self.subTest(condition=entry['condition'],case='missing-completed-drain'):
                reject(lambda x:x[emitted]['payload'].update(status='completed'))
            with self.subTest(condition=entry['condition'],case='drain-regression'):
                def regress(x):
                    extra=deepcopy(x[final]);extra['payload'].update(status='emission_ended',drained_end_seconds=None)
                    x.insert(final+1,extra)
                reject(regress)
            with self.subTest(condition=entry['condition'],case='lost-certificate'):
                reject(lambda x:x.pop(emitted))
            with self.subTest(condition=entry['condition'],case='final-snapshot'):
                reject(lambda x:x[final]['payload'].update(drained_end_seconds=280))
            with self.subTest(condition=entry['condition'],case='missing-source-closure'):
                reject(lambda x:x.pop())

    def test_four_inflight_runs_export_review_compare_and_old_guards(self):
        # Exercise the existing full export/dataset/review/comparison integration
        # with the new lifecycle, retaining inventory/quota/CSV/end/hash guards.
        instance=previous_tests.OriginsTests('test_four_run_fixture_pipeline_and_seed_paired_comparison')
        instance.root=self.root/'pipeline-integration';instance.root.mkdir()
        instance.control_raw=self.control_raw;instance.control=deepcopy(self.control)
        instance.control['preserved_raw_hashes']={str(p):c.base.sha(p) for p in self.control_raw.rglob('*') if p.is_file()}
        with patch.object(c,'DEFAULT_MANIFEST',revision.DEFAULT_MANIFEST),patch('tests.test_development_d3_origins.origins_fixture',in_flight_fixture):
            instance.test_four_run_fixture_pipeline_and_seed_paired_comparison()

    def test_historical_execution_uses_archived_source_and_consumed_attempt(self):
        plan=c.read(revision.DEFAULT_MANIFEST);entry=plan['entries'][0]
        result=revision.historical_operation_checks(plan,entry,revision.DEFAULT_MANIFEST)
        self.assertTrue(result['cleanup_verified']);self.assertTrue(result['attempt_reused'])
        self.assertFalse(result['new_attempt_consumed'])
        source=result['execution_sources_verified']['experiments/development_d3_origins_processing.py']
        self.assertTrue(source['archived'])
        bad=deepcopy(plan);bad['processing_revision']['archived_sources']['experiments/development_d3_origins_processing.py']['path']='experiments/development_d3_origins_processing.py'
        with self.assertRaisesRegex(ValueError,'Execution source evidence changed'):
            revision.historical_operation_checks(bad,entry,revision.DEFAULT_MANIFEST)

    def test_release_binds_parent_configs_budget_and_restores_context(self):
        valid=revision.validate_plan();self.assertEqual(valid['entry_count'],4)
        original=c.DEFAULT_MANIFEST
        with self.assertRaisesRegex(RuntimeError,'sentinel'):
            with ops.release_context():
                self.assertEqual(c.DEFAULT_MANIFEST,revision.DEFAULT_MANIFEST)
                self.assertEqual(ops.previous.get_plan,ops.get_plan)
                plan=c.read(revision.DEFAULT_MANIFEST);self.assertEqual(plan['budget']['envelope_seconds'],4320)
                raise RuntimeError('sentinel')
        self.assertEqual(c.DEFAULT_MANIFEST,original)
        plan=c.read(revision.DEFAULT_MANIFEST);plan['entries'][1]['effective_configuration']['attack']['rate']=8
        path=self.root/'bad-release.json';put(path,plan)
        with self.assertRaises(ValueError):revision.validate_plan(path)


if __name__=='__main__':unittest.main()
