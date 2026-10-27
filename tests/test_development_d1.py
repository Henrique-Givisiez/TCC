"""D1 preparation and synthetic lifecycle resolution only; no Docker calls."""
import csv
from decimal import Decimal as D
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments import development_d1 as d1
from simulator.experiment_config import ExperimentConfig
from simulator.request_logger import REQUEST_FIELDS

MANIFEST = d1.ROOT / 'experiments/protocols/development_d1_20261027/manifest.json'


class D1PreparationTests(unittest.TestCase):
    def test_capturefix_continuation_binds_parent_failure_seed_and_new_paths(self):
        from experiments import development_d1_ops as ops
        old_manifest = ops.ACTIVE_MANIFEST
        try:
            ops.ACTIVE_MANIFEST = ops.CONTINUATION
            plan, validation = ops.get_plan()
            entry = ops.find_entry(plan, 'd1_L04_B_CF1')
            self.assertTrue(validation['bound_parent'])
            self.assertEqual(plan['maximum_attempts'], 11)
            self.assertEqual(entry['effective_configuration']['seed'], 3803721254044484793)
            self.assertEqual(entry['replacement_of'], 'd1_L04_B')
            self.assertTrue(entry['outputs']['raw'].endswith('d1_L04_B_CF1'))
            self.assertFalse((d1.ROOT / entry['outputs']['raw']).exists())
            self.assertFalse(json.loads((d1.ROOT / 'experiment_results/development-d1-20261027/analysis/d1_L04_B-review.json').read_text())
                             ['decision']['d1_L04_B_all_criteria_pass'])
        finally:
            ops.ACTIVE_MANIFEST = old_manifest

    def test_all_ten_complete_configs_and_seed_reservation(self):
        manifest = json.loads(MANIFEST.read_text())
        self.assertEqual(len(manifest['entries']), 10)
        self.assertEqual([e['aggregate_rps'] for e in manifest['entries']], [4,4,8,8,16,16,32,32,64,64])
        for entry in manifest['entries']:
            config = ExperimentConfig.load(d1.ROOT / entry['config'])
            self.assertEqual(json.loads((d1.ROOT / entry['config']).read_text()), json.loads(config.to_json()))
            self.assertFalse(config.attack.enabled)
            self.assertFalse(config.autoscaler.enabled)
            self.assertEqual(config.infrastructure.max_instances, 1)
            self.assertEqual(config.normal_traffic.clients, 4)
            self.assertEqual(config.normal_traffic.endpoint, '/medium')

    def test_seed_extraction_includes_partitions_pilot_smoke_and_explicit_seeds(self):
        metadata = dict(seed=42, partitions=dict(baseline=[101], calibration=[201], test=[301]),
                        pilot_exclusions=[99], smoke_development=dict(seeds=[12]), duration_seconds=150)
        self.assertEqual(d1.collect_seeds(metadata), {42,101,201,301,99,12})

    def test_seed_audit_excludes_own_future_runs_but_not_other_history(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            own=root/'experiment_results/development-d1-20261027/raw/d1_L01_A/effective_config.json'
            historical=root/'experiment_results/previous/raw/effective_config.json'
            for path in (own,historical):
                path.parent.mkdir(parents=True);path.write_text('{"seed": 42}')
            self.assertEqual(d1.historical_seed_inputs(root),[historical])

    def fixture(self, root, cutoff='152.25', missing_closure=False):
        config = ExperimentConfig.load(d1.ROOT / 'experiments/configs/development_d1_20261027/d1_L01_A.json')
        raw = root / 'raw'
        raw.mkdir()
        (raw / 'effective_config.json').write_text(config.to_json())
        (raw / 'run_status.json').write_text(json.dumps(dict(run_id='synthetic-d1',status='completed' if D(cutoff)>=150 else 'incomplete',
            producers_drained=True,end_reason='simulation_end',errors=[])))
        inventory, requests = [], []
        for worker in range(4):
            source = f'normal_{worker+1}'
            inventory.append(dict(source_id=source,source_type='normal',worker_index=worker,run_id='synthetic-d1'))
            start, end = (D('149'), D('150.2')) if D(cutoff)>=150 else (D(40), D(41))
            row = dict.fromkeys(REQUEST_FIELDS, '')
            row.update(run_id='synthetic-d1', request_id=f'request-{worker}', generator='normal',worker_id=worker,
                       target_url='http://edos_service:80/medium',timestamp=str(1000+start),elapsed_seconds=str(start),
                       end_timestamp=str(1000+end),end_elapsed_seconds=str(end),duration_ms=str((end-start)*1000),
                       traffic_class='benign',http_status=200,outcome='response',active_event_ids='[]')
            requests.append(row)
            records = [('request_begin', row), ('request_finish', row)]
            if not missing_closure or worker != 3:
                records.append(('source_closed',dict(elapsed_seconds=str(D(cutoff)-D(3-worker)/10),drained=True,logger_complete=True)))
            path = raw / 'source_artifacts' / source / 'output/journal.jsonl'
            path.parent.mkdir(parents=True)
            path.write_text(''.join(json.dumps(dict(source_id=source,run_id='synthetic-d1',sequence=i,kind=kind,payload=payload))+'\n'
                                    for i,(kind,payload) in enumerate(records,1)))
        (raw / 'source_inventory.json').write_text(json.dumps(inventory))
        with (raw / 'request_log.csv').open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=REQUEST_FIELDS);writer.writeheader();writer.writerows(requests)
        return raw, config

    def test_observed_drain_uses_closure_not_last_http_end(self):
        with tempfile.TemporaryDirectory() as folder:
            raw, config = self.fixture(Path(folder))
            phases, cutoff, evidence = d1.resolve_observation(raw,config)
            self.assertEqual(cutoff, D('152.25'))
            self.assertEqual(phases['phases'][-1], dict(name='DRAIN',start_seconds='150',end_seconds='152.25'))
            self.assertEqual(evidence['observed_drain_seconds'], D('2.25'))
            self.assertTrue(evidence['technical_status_complete'])

    def test_missing_closure_and_journal_csv_disagreement_stop_without_padding(self):
        with tempfile.TemporaryDirectory() as folder:
            raw, config = self.fixture(Path(folder),missing_closure=True)
            with self.assertRaisesRegex(ValueError,'Missing/duplicate source_closed'):
                d1.resolve_observation(raw,config)
        with tempfile.TemporaryDirectory() as folder:
            raw, config = self.fixture(Path(folder))
            path=raw/'request_log.csv';lines=path.read_text().splitlines(keepends=True)
            path.write_text(''.join(lines[:-1]))
            with self.assertRaisesRegex(ValueError,'do not reconcile'):
                d1.resolve_observation(raw,config)

    def test_summary_integration_and_early_run_null_adherence(self):
        for cutoff in ('152.25','80'):
            with self.subTest(cutoff=cutoff), tempfile.TemporaryDirectory() as folder:
                root=Path(folder)
                raw, config = self.fixture(root,cutoff=cutoff)
                plan=dict(entries=[dict(id='d1_L01_A',effective_configuration=json.loads(config.to_json()),
                                       outputs=dict(raw='raw',analysis='analysis'))])
                manifest=root/'manifest.json';manifest.write_text(json.dumps(plan))
                with patch.object(d1,'ROOT',root), patch.object(d1,'validate_plan'):
                    result=d1.summarize_entry(manifest,'d1_L01_A',root/'analysis')
                    self.assertEqual(result['reconciliation']['included_starts'],4)
                    self.assertEqual(len(result['d1_30s_cohorts']),4)
                    self.assertEqual(result['as_of_seconds'],D(cutoff))
                    if cutoff=='80':
                        self.assertTrue(all(s['achieved_over_nominal'] is None for s in result['d1_evidence']['per_source_useful_interval']))
                        self.assertFalse(result['d1_evidence']['technical_status_complete'])
                    with self.assertRaises(FileExistsError):
                        d1.summarize_entry(manifest,'d1_L01_A',root/'analysis')


if __name__ == '__main__':
    unittest.main()
