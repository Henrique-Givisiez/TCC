import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.dataset_schema import schema
from experiments.dataset_provenance import capture_provenance, sha256_file
from experiments.export_dataset import export_run, TABLES


class DatasetExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'run'
        self.source.mkdir()
        self.destination = self.root / 'dataset'
        self.config = dict(seed=0, attack=dict(profile='periodic_burst', endpoint='/expensive', rate=10,
                           attackers=1, burst=dict(duration_seconds=1, period_seconds=3)),
                           normal_traffic=dict(clients=1, endpoint='/light'),
                           traffic_sources=dict(execution='containers'))
        self.write('effective_config.json', self.config)
        self.write('run_status.json', dict(run_id='run1', status='completed', errors=[],
                  experiment_start_timestamp=100, experiment_start_monotonic=20))
        self.write('source_inventory.json', [dict(run_id='run1', source_id='normal_1', source_type='normal',
                   worker_index=0, traffic_class='benign', ip='172.20.0.3', container_name='ephemeral')])
        for name, key in TABLES.items():
            fields = [f['name'] for f in schema()['tables'][key]['fields']]
            with (self.source / name).open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                if key == 'requests':
                    for i, operation in enumerate(['/light', '/medium', '/expensive']):
                        writer.writerow(dict(run_id='run1', request_id=str(i), generator='normal', worker_id=0,
                                             target_url='http://edos_service'+operation, traffic_class='benign',
                                             attack_active=1, elapsed_seconds=5, timestamp=105,
                                             outcome='transport_error' if i == 0 else 'response'))
                elif key == 'attacks':
                    writer.writerow(dict(run_id='run1', event_id='event1', profile='periodic_burst',
                                         actual_start_seconds=2, actual_end_seconds=13.5, drained_end_seconds=12))
                elif key == 'packets':
                    writer.writerow(dict(run_id='run1', src_ip='172.20.0.3', traffic_class='unknown', attack_active=1))
        self.write('source_artifacts/normal_1/manifest.json', dict(source_id='normal_1', seed=0))
        (self.source / 'diagnostic.txt').write_text('Do not discard errors\n')

    def write(self, name, value):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def export(self):
        return export_run(self.source, self.destination)

    def test_export_version_identity_seed_configuration_status(self):
        result = self.export()
        self.assertEqual((result['schema_version'], result['run_id'], result['status']), (1, 'run1', 'completed'))
        self.assertEqual(json.loads((self.destination / result['configuration']).read_text()), self.config)
        self.assertEqual(result['structural_status'], 'complete')

    def test_all_original_bytes_and_modification_times_preserved(self):
        before = {p: (sha256_file(p), p.stat().st_mtime_ns) for p in self.source.rglob('*') if p.is_file()}
        result = self.export()
        for entry in result['files']:
            if entry['origin_path']:
                original = Path(entry['origin_path'])
                self.assertEqual(entry['sha256'], before[original][0])
                self.assertEqual(sha256_file(self.destination / entry['path']), before[original][0])
        self.assertEqual(before, {p: (sha256_file(p), p.stat().st_mtime_ns) for p in before})
        self.assertEqual(len(before), sum(e['origin_path'] is not None for e in result['files']))

    def test_source_identity_ip_and_journal_metadata_preserved(self):
        result = self.export()
        source = json.loads((self.destination / result['source_inventory']).read_text())[0]
        self.assertEqual((source['source_id'], source['ip'], source['traffic_class']), ('normal_1', '172.20.0.3', 'benign'))
        self.assertTrue((self.destination / 'evidence/sources/normal_1/manifest.json').exists())

    def test_ground_truth_benign_context_errors_operations_unchanged(self):
        self.export()
        with (self.destination / 'raw/service/request_log.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual({r['traffic_class'] for r in rows}, {'benign'})
        self.assertEqual({r['attack_active'] for r in rows}, {'1'})
        self.assertEqual({r['target_url'].split('service')[1] for r in rows}, {'/light', '/medium', '/expensive'})
        self.assertEqual(rows[0]['outcome'], 'transport_error')
        self.assertEqual((self.destination / 'raw/attacks/attack_events.csv').read_bytes(), (self.source / 'attack_events.csv').read_bytes())

    def test_patterns_and_parameters_remain_canonical(self):
        for profile in ['continuous', 'periodic_burst']:
            with self.subTest(profile=profile):
                self.config['attack']['profile'] = profile
                self.write('effective_config.json', self.config)
                destination = self.root / profile
                manifest = export_run(self.source, destination)
                attack = json.loads((destination / manifest['configuration']).read_text())['attack']
                self.assertEqual(attack['profile'], profile)
                self.assertEqual(attack['burst'], dict(duration_seconds=1, period_seconds=3))
                self.assertEqual(attack['rate'], 10)

    def test_incomplete_with_missing_artifacts_keeps_reason(self):
        self.write('run_status.json', dict(run_id='run1', status='incomplete', errors=['proxy died']))
        (self.source / 'traffic_capture.csv').unlink()
        result = self.export()
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['missing_artifacts'], ['traffic_capture.csv'])
        self.assertEqual(json.loads((self.destination / result['run_status']).read_text())['errors'], ['proxy died'])

    def test_completed_missing_required_fails_without_output(self):
        (self.source / 'request_log.csv').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing required.*request_log'):
            self.export()
        self.assertFalse(self.destination.exists())

    def test_mixed_run_is_rejected(self):
        path = self.source / 'request_log.csv'
        path.write_text(path.read_text().replace('run1', 'another'))
        with self.assertRaisesRegex(ValueError, 'Mixed run IDs'):
            self.export()

    def test_inventory_from_another_run_rejected(self):
        self.write('source_inventory.json', [dict(run_id='another', source_id='normal_1')])
        with self.assertRaisesRegex(ValueError, 'Mixed run IDs.*inventory'):
            self.export()

    def test_missing_canonical_metadata_is_not_invented(self):
        (self.source / 'effective_config.json').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing required artifact.*effective_config'):
            self.export()

    def test_pcap_and_unknown_diagnostics_are_retained(self):
        (self.source / 'source_artifacts/traffic_capture.pcap').write_bytes(b'raw\x00\xff')
        result = self.export()
        self.assertEqual((self.destination / 'raw/traffic/traffic_capture.pcap').read_bytes(), b'raw\x00\xff')
        self.assertTrue(any(e['path']=='evidence/other/diagnostic.txt' for e in result['files']))

    def test_source_id_is_stable_when_execution_ip_changes(self):
        first = self.export()
        inventory = json.loads((self.source / 'source_inventory.json').read_text())
        inventory[0]['ip'] = '172.20.0.8'
        self.write('source_inventory.json', inventory)
        second_path = self.root / 'another-export'
        second = export_run(self.source, second_path)
        a = json.loads((self.destination / first['source_inventory']).read_text())[0]
        b = json.loads((second_path / second['source_inventory']).read_text())[0]
        self.assertEqual(a['source_id'], b['source_id'])
        self.assertNotEqual(a['ip'], b['ip'])

    def test_historical_stage3_aliases(self):
        (self.source / 'request_log.csv').rename(self.source / 'request_log_run.csv')
        self.export()
        self.assertTrue((self.destination / 'raw/service/request_log.csv').exists())

    def test_ambiguous_alias_rejected(self):
        (self.source / 'request_log_run.csv').write_bytes((self.source / 'request_log.csv').read_bytes())
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            self.export()

    def test_schema_documents_every_field_and_clocks(self):
        self.export()
        document = json.loads((self.destination / 'schema.json').read_text())
        for table in document['tables'].values():
            for field in table['fields']:
                self.assertTrue({'name', 'type', 'unit', 'nullable', 'description', 'origin'} <= field.keys())
        self.assertEqual(next(f for f in document['tables']['rtt']['fields'] if f['name']=='rtt')['unit'], 'ms')
        self.assertIn('NOT TCP RTT', str(document))
        self.assertIn('not guaranteed identical', document['clocks']['alignment_limitations'])

    def test_old_execution_provenance_not_inferred_from_export(self):
        result = self.export()
        self.assertEqual(result['execution_provenance']['status'], 'not_recorded')
        self.assertEqual(json.loads((self.destination / result['export_provenance']).read_text())['scope'], 'export')

    def test_recorded_execution_provenance_is_preserved(self):
        self.write('run_provenance.json', dict(scope='execution_before_invocation', run_id='run1', code=dict(commit='abc', dirty=True)))
        result = self.export()
        self.assertEqual(result['execution_provenance']['status'], 'recorded')
        self.assertEqual((self.destination / 'metadata/run_provenance.json').read_bytes(), (self.source / 'run_provenance.json').read_bytes())

    def test_provenance_for_different_run_rejected(self):
        self.write('run_provenance.json', dict(scope='export', run_id='run1'))
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.export()

    def test_no_overwrite_or_nested_destination(self):
        with self.assertRaisesRegex(ValueError, 'nesting'):
            export_run(self.source, self.source / 'dataset')
        self.export()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.export()

    def test_symlink_rejected(self):
        (self.source / 'link').symlink_to(self.source / 'run_status.json')
        with self.assertRaisesRegex(ValueError, 'Symlinks'):
            self.export()

    def test_unrecognized_incomplete_header_preserved_with_warning(self):
        self.write('run_status.json', dict(run_id='run1', status='incomplete'))
        (self.source / 'traffic_capture.csv').write_text('partial\n')
        result = self.export()
        self.assertTrue(result['warnings'])
        self.assertEqual((self.destination / 'raw/traffic/traffic_capture.csv').read_text(), 'partial\n')

    def test_unavailable_git_is_explicit(self):
        provenance = capture_provenance('export', repository=self.root)
        self.assertEqual(provenance['code']['git']['status'], 'unavailable')
        self.assertIsNone(provenance['code']['git']['commit'])

    def test_run_wrapper_records_before_invocation_and_restores_paths(self):
        from experiments.dataset_run import run_recorded
        from simulator import config
        from simulator.experiment_config import ExperimentConfig
        output = self.root / 'new-run'
        previous = config.REQUEST_LOG_FILE
        def fake_main(experiment):
            self.assertTrue((output / 'run_provenance.json').exists())
            self.assertEqual(json.loads((output / 'effective_config.json').read_text())['seed'], 42)
            Path(config.RUN_STATUS_FILE).write_text(json.dumps(dict(run_id='new1', status='completed')))
        with patch('experiments.dataset_run.capture_provenance', return_value=dict(scope='execution_before_invocation')), patch('simulator.main_orchestrator.main', side_effect=fake_main):
            run_recorded(ExperimentConfig.from_dict(dict(seed=42)), output)
        self.assertEqual(config.REQUEST_LOG_FILE, previous)
        self.assertEqual(json.loads((output / 'run_provenance.json').read_text())['run_id'], 'new1')


if __name__ == '__main__':
    unittest.main()
