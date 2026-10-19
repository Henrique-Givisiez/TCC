"""DEVELOPMENT-only coordinator fixtures. No TEST execution or observed data."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analysis.detection.inputs import ContractError
from experiments import stage14_campaign as campaign


class PowerLoss(BaseException):
    pass


class DevelopmentExecutor:
    def __init__(self, root, size=3):
        self.root = Path(root)
        self.calls = []
        self.fail = None
        self.crash = None
        self.locked = False
        self.authority = 'development-v1'
        self.rows = [dict(order=i, seed=i // 3, scenario=('B', 'C', 'P')[i % 3],
                          role='development', output=str(self.root/f'output-{i}'))
                     for i in range(size)]

    def plan(self):
        return dict(authority=self.authority, entries=deepcopy(self.rows))

    def require_execution(self):
        if self.locked:
            raise ContractError('LOCKED')

    def preflight(self, entry):
        self.calls.append(('preflight', entry['order']))

    def execute(self, entry):
        self.calls.append(('execute', entry['order']))
        if self.fail:
            raise campaign.TechnicalFailure(self.fail, 'objective fixture failure')
        destination = Path(entry['output'])
        destination.mkdir()
        (destination/'certificate.json').write_text('{"DEVELOPMENT":true}')
        if self.crash == 'after_output':
            raise PowerLoss()

    def validate(self, entry):
        files = campaign.inventory(Path(entry['output']))
        return dict(status='valid', inventory=files, inventory_sha256=campaign.digest(files))

    def cleanup(self, entry):
        self.calls.append(('cleanup', entry['order']))
        return dict(status='verified_idle')


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.executor = DevelopmentExecutor(self.root)
        self.runner = campaign.Campaign(self.root/'admin', self.executor)

    def executed(self):
        return [order for action, order in self.executor.calls if action == 'execute']

    def checkpoint(self):
        return campaign.read_json(self.runner.path)

    def initialize(self):
        with campaign.campaign_lock(self.runner.directory):
            return self.runner.initialize(self.executor.plan())

    def test_order_48_entries_and_transitions(self):
        self.executor.rows = DevelopmentExecutor(self.root, 48).rows
        result = self.runner.run()
        self.assertEqual(result['total_entries'], 48)
        self.assertEqual(self.executed(), list(range(48)))
        self.assertTrue(all(e['state'] == 'COMPLETED_VALID' for e in result['entries']))
        events = [json.loads(line) for line in (self.runner.directory/'operations.jsonl').read_text().splitlines()]
        transitions = [(e['previous'], e['state']) for e in events if e['event'] == 'transition']
        self.assertEqual(transitions, [('PENDING', 'RUNNING'), ('RUNNING', 'COMPLETED_VALID')] * 48)
        self.assertTrue(all(e['attempt'] == 1 for e in result['entries']))

    def test_checkpoint_creation_and_no_overwrite(self):
        checkpoint = self.initialize()
        self.assertEqual(checkpoint['campaign_identity'], campaign.digest(self.executor.plan()))
        self.assertTrue(all(e['state'] == 'PENDING' for e in checkpoint['entries']))
        with self.assertRaises(ContractError):
            self.initialize()

    def test_exceptional_states_stop_and_never_retry(self):
        for state in campaign.EXCEPTIONAL:
            with self.subTest(state=state), tempfile.TemporaryDirectory() as directory:
                executor = DevelopmentExecutor(directory)
                executor.fail = state
                runner = campaign.Campaign(Path(directory)/'admin', executor)
                with self.assertRaisesRegex(ContractError, state):
                    runner.run()
                self.assertEqual(campaign.read_json(runner.path)['entries'][0]['state'], state)
                executor.fail = None
                with self.assertRaisesRegex(ContractError, state):
                    runner.run(resume=True)
                self.assertEqual([x for x in executor.calls if x[0] == 'execute'], [('execute', 0)])

    def test_resume_after_completed_preserves_and_advances_pending(self):
        original = self.runner.transition

        def crash_after_completed(*args, **kwargs):
            original(*args, **kwargs)
            if args[2] == 'COMPLETED_VALID':
                raise PowerLoss()
        with patch.object(self.runner, 'transition', side_effect=crash_after_completed):
            with self.assertRaises(PowerLoss):
                self.runner.run()
        before = campaign.inventory(self.root/'output-0')
        result = self.runner.run(resume=True)
        self.assertEqual(self.executed(), [0, 1, 2])
        self.assertEqual(before, campaign.inventory(self.root/'output-0'))
        self.assertEqual(result['entries'][-1]['state'], 'COMPLETED_VALID')

    def test_complete_resume_idempotent_no_writes(self):
        self.runner.run()
        before = campaign.inventory(self.root)
        self.runner.run(resume=True)
        self.assertEqual(before, campaign.inventory(self.root))
        self.assertEqual(self.executed(), [0, 1, 2])

    def test_interruption_before_running_remains_pending(self):
        self.initialize()
        with patch.object(self.executor, 'preflight', side_effect=PowerLoss):
            with self.assertRaises(PowerLoss):
                self.runner.run(resume=True)
        self.assertEqual(self.checkpoint()['entries'][0]['state'], 'PENDING')
        self.runner.run(resume=True)
        self.assertEqual(self.executed(), [0, 1, 2])

    def test_interruption_after_running_or_output_is_orphan_no_rerun(self):
        for when in ('after_running', 'after_output'):
            with self.subTest(when=when), tempfile.TemporaryDirectory() as directory:
                executor = DevelopmentExecutor(directory)
                runner = campaign.Campaign(Path(directory)/'admin', executor)
                if when == 'after_output':
                    executor.crash = when
                    context = patch.object(executor, 'preflight', wraps=executor.preflight)
                else:
                    context = patch.object(executor, 'execute', side_effect=PowerLoss)
                with context, self.assertRaises(PowerLoss):
                    runner.run()
                before = (campaign.inventory(Path(directory)/'output-0')
                          if when == 'after_output' else None)
                with self.assertRaisesRegex(ContractError, 'orphan RUNNING'):
                    runner.run(resume=True)
                record = campaign.read_json(runner.path)['entries'][0]
                self.assertEqual(record['state'], 'INCOMPLETE')
                self.assertIn('completion unknown', record['reason'])
                if before is not None:
                    self.assertEqual(before, campaign.inventory(Path(directory)/'output-0'))
                self.assertEqual(len([c for c in executor.calls if c[0] == 'execute']),
                                 1 if when == 'after_output' else 0)

    def test_corrupt_checkpoint_stops(self):
        self.initialize()
        self.runner.path.write_text('{broken')
        with self.assertRaisesRegex(ContractError, 'Unreadable'):
            self.runner.run(resume=True)
        self.assertEqual(self.executed(), [])

    def test_authority_mismatch_stops(self):
        self.initialize()
        self.executor.authority = 'different'
        with self.assertRaisesRegex(ContractError, 'identity'):
            self.runner.run(resume=True)
        self.assertEqual(self.executed(), [])

    def test_output_collision_before_start_and_resume(self):
        self.initialize()
        (self.root/'output-1').mkdir()
        with self.assertRaisesRegex(ContractError, 'unexpected output'):
            self.runner.run(resume=True)
        with self.assertRaisesRegex(ContractError, 'collision'):
            campaign.Campaign(self.root/'other-admin', self.executor).run()
        self.assertEqual(self.executed(), [])

    def test_completed_hash_mismatch_stops_no_retry(self):
        self.runner.run()
        (self.root/'output-0/certificate.json').write_text('changed')
        with self.assertRaisesRegex(ContractError, 'hash mismatch'):
            self.runner.run(resume=True)
        self.assertEqual(self.executed(), [0, 1, 2])

    def test_atomic_checkpoint_failed_replace_preserves_previous(self):
        self.initialize()
        before = self.runner.path.read_bytes()
        with patch.object(campaign.os, 'replace', side_effect=OSError('injected crash')):
            with self.assertRaises(OSError):
                campaign.atomic_json(self.runner.path, {'replacement': True})
        self.assertEqual(self.runner.path.read_bytes(), before)
        self.assertEqual(list(self.runner.directory.glob('.campaign_state.json.*')), [])

    def test_atomic_checkpoint_flush_fsync_then_replace_and_directory_fsync(self):
        events = []
        replace = campaign.os.replace
        with patch.object(campaign.os, 'fsync', side_effect=lambda _: events.append('fsync')), \
                patch.object(campaign.os, 'replace', side_effect=lambda a, b: (events.append('replace'), replace(a, b))):
            campaign.atomic_json(self.root/'checkpoint.json', {'value': 1})
        self.assertEqual(events, ['fsync', 'replace', 'fsync'])

    def test_locked_execution_gate_precedes_checkpoint_and_backend(self):
        self.executor.locked = True
        with self.assertRaisesRegex(ContractError, 'LOCKED'):
            self.runner.run()
        self.assertFalse(self.runner.path.exists())
        self.assertEqual(self.executor.calls, [])

    def test_production_test_guard_fatal_without_any_scientific_call(self):
        executor = campaign.FrozenExecutor('binding', 'sha', 'eval', 'sha')
        with patch.object(campaign.scientific, 'execute_entry') as execute, \
                patch.object(campaign.scientific, 'preflight_entry') as preflight:
            with self.assertRaisesRegex(ContractError, 'LOCKED'):
                executor.require_execution()
        execute.assert_not_called()
        preflight.assert_not_called()
        # The underlying executor independently retains its own fatal guard.
        with self.assertRaisesRegex(ContractError, 'locked'):
            campaign.scientific.execute_entry('nonexistent', 'sha', partition='test', run=1, execute=True)

    def test_status_read_only_no_executor_or_scientific_reads(self):
        self.initialize()
        before = campaign.inventory(self.runner.directory)
        with patch.object(self.executor, 'plan', side_effect=AssertionError('no environment IO')), \
                patch.object(campaign, 'inventory', side_effect=AssertionError('no output IO')):
            result = campaign.status(self.runner.directory)
        self.assertEqual(result['pending'], 3)
        self.assertEqual(result['running'], 0)
        self.assertEqual(before, campaign.inventory(self.runner.directory))

    def test_abort_stops_at_safe_boundary(self):
        self.initialize()
        campaign.request_stop(self.runner.directory)
        self.runner.run(resume=True)
        self.assertEqual(self.executed(), [])
        self.assertEqual(campaign.status(self.runner.directory)['pending'], 3)

    def test_abort_during_entry_finishes_current_only(self):
        original = self.executor.execute

        def abort(entry):
            original(entry)
            campaign.request_stop(self.runner.directory)
        with patch.object(self.executor, 'execute', side_effect=abort):
            self.runner.run()
        self.assertEqual(self.executed(), [0])
        self.assertEqual(campaign.status(self.runner.directory)['completed_valid'], 1)

    def test_concurrent_coordinator_stops(self):
        with campaign.campaign_lock(self.runner.directory):
            with self.assertRaisesRegex(ContractError, 'active coordinator'):
                self.runner.run()
        self.assertFalse(self.runner.path.exists())

    def test_checkpoint_illegal_state_attempt_and_order_rejected(self):
        original = self.initialize()
        for field, value in [('state', 'RETRY'), ('attempt', 2), ('plan', {})]:
            broken = deepcopy(original)
            broken['entries'][0][field] = value
            campaign.atomic_json(self.runner.path, broken)
            with self.assertRaises(ContractError):
                self.runner.run(resume=True)
        self.assertEqual(self.executed(), [])

    def test_forbidden_retry_transition(self):
        checkpoint = self.initialize()
        entry = checkpoint['entries'][0]
        entry['state'] = 'FAILED'
        with self.assertRaisesRegex(ContractError, 'Forbidden'):
            self.runner.transition(checkpoint, entry, 'PENDING')

    def test_cleanup_failure_stops_campaign(self):
        with patch.object(self.executor, 'cleanup', side_effect=ContractError('residual fixture process')):
            with self.assertRaisesRegex(ContractError, 'FAILED'):
                self.runner.run()
        self.assertEqual(self.executed(), [0])
        self.assertEqual(self.checkpoint()['entries'][0]['cleanup']['status'], 'operator_review_required')

    def test_validation_rejection_does_not_accept_or_advance(self):
        with patch.object(self.executor, 'validate', return_value=dict(status='invalid')):
            with self.assertRaisesRegex(ContractError, 'INVALID'):
                self.runner.run()
        self.assertEqual(self.executed(), [0])
        self.assertEqual(self.checkpoint()['entries'][0]['state'], 'INVALID')

    def test_keyboard_interrupt_is_incomplete_and_preserved(self):
        with patch.object(self.executor, 'execute', side_effect=KeyboardInterrupt):
            with self.assertRaisesRegex(ContractError, 'INCOMPLETE'):
                self.runner.run()
        self.assertEqual(self.checkpoint()['entries'][0]['state'], 'INCOMPLETE')

    def test_authority_revalidated_between_entries(self):
        original = self.executor.execute

        def change(entry):
            original(entry)
            self.executor.authority = 'changed-after-entry'
        with patch.object(self.executor, 'execute', side_effect=change):
            with self.assertRaisesRegex(ContractError, 'Authority'):
                self.runner.run()
        self.assertEqual(self.executed(), [0])

    def test_output_collision_at_preflight_is_not_overwritten(self):
        def collide(entry):
            Path(entry['output']).mkdir()
        with patch.object(self.executor, 'preflight', side_effect=collide):
            with self.assertRaisesRegex(ContractError, 'collision'):
                self.runner.run()
        self.assertEqual(self.executed(), [])
        self.assertEqual(self.checkpoint()['entries'][0]['state'], 'PENDING')

    def test_no_evaluator_score_decision_metrics_dependencies(self):
        import ast
        tree = ast.parse(Path(campaign.__file__).read_text())
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertFalse(any(any(token in (name or '') for token in
                                 ('evaluation', 'scores', 'calibration', 'decisions')) for name in imports))
        self.runner.run()
        files = [p.name for p in self.root.rglob('*') if p.is_file()]
        self.assertTrue(set(files) <= {'campaign_state.json', 'campaign.lock', 'operations.jsonl', 'certificate.json'})


class PlanTests(unittest.TestCase):
    def test_adapter_consumes_ordered_matrix_metadata_without_preflighting_48(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [dict(order=19+i, partition='test', role='test', seed=i//3,
                         scenario=('B', 'P', 'C')[i % 3], config={'fixture': i},
                         config_sha256=campaign.digest({'fixture': i})) for i in range(48)]
            refs = {key: {'path': key, 'sha256': key} for key in
                    ('protocol', 'seed_plan', 'matrix', 'definitive_environment_lock')}
            binding = dict(campaign_git_head='fixture-head', references=refs)
            evaluation = dict(status='FROZEN', test_execution='LOCKED',
                protocol_v2=refs['protocol'], seed_plan=refs['seed_plan'], matrix=refs['matrix'],
                four_method_freeze={'path': 'freeze', 'sha256': 'freeze'},
                paired_design=dict(total_entries=48, seeds=list(range(16)), scenarios=['B', 'C', 'P']))
            documents = dict(matrix=dict(runs=rows), environment_lock=dict(reference={}))
            executor = campaign.FrozenExecutor(root/'binding', 'binding-sha', root/'evaluation', 'eval-sha')
            with patch.object(campaign.scientific, 'ROOT', root), \
                    patch.object(campaign.scientific, 'load_bundle', return_value=(binding, {}, {}, documents)), \
                    patch.object(campaign.scientific, 'checked_reference', return_value=(root/'evaluation', evaluation)), \
                    patch.object(campaign.scientific, 'observe_environment', return_value={'dynamic': {'git_status': ''}}), \
                    patch.object(campaign.scientific, 'environment_check', return_value={'fatal': []}), \
                    patch.object(campaign.scientific, 'preflight_entry', side_effect=AssertionError('no real preflights')):
                plan = executor.plan()
                self.assertEqual([e['matrix_identity'] for e in plan['entries']], [campaign.digest(r) for r in rows])
                self.assertEqual([e['scenario'] for e in plan['entries'][:3]], ['B', 'P', 'C'])
                self.assertEqual(len(plan['entries']), 48)
                self.assertEqual(plan['authority']['head'], 'fixture-head')
                rows.reverse()
                with self.assertRaisesRegex(ContractError, 'order mismatch'):
                    executor.plan()


class TechnicalCertificateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.executor = campaign.FrozenExecutor(self.root/'binding', 'binding-sha', self.root/'evaluation', 'eval-sha')
        self.entry = dict(order=1, role='development', output=str(self.root), configuration={'duration_seconds': 144})
        self.put('raw/run_status.json', dict(status='completed', run_id='synthetic-run'))
        self.put('stage8/dataset_manifest.json', dict(run_id='synthetic-run', files=[]))
        self.dataset_hash = campaign.scientific.sha(self.root/'stage8/dataset_manifest.json')
        self.report = dict(dataset_valid=True, analysis_eligible=True, run_id='synthetic-run',
                           dataset_manifest_sha256=self.dataset_hash)
        self.put('stage9/validation_report.json', self.report)
        self.put('stage10/evidence/validation.json', self.report)
        self.feature = dict(source_run_id='synthetic-run', dataset_manifest_sha256=self.dataset_hash,
            network_direction=dict(supported=True), window=dict(planned_duration_seconds='144'),
            input_files=[], outputs=[], stage9_validation_report=dict(path='evidence/validation.json',
                sha256=campaign.scientific.sha(self.root/'stage9/validation_report.json')))
        self.put('stage10/feature_manifest.json', self.feature)
        self.seal()

    def put(self, relative, value):
        path = self.root/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def seal(self):
        after = dict(status='completed', row=dict(order=1), role='development',
            configuration=self.entry['configuration'], binding=dict(sha256='binding-sha'),
            lineage=dict(run_id='synthetic-run'), outputs_sha256={
                p: v['sha256'] for p, v in campaign.inventory(self.root).items()
                if p != 'scientific_run_after.json'})
        self.put('scientific_run_after.json', after)

    def test_certificates_hashes_lineage_valid_without_label_parsing(self):
        result = self.executor.validate(self.entry)
        self.assertTrue(result['dataset_valid'])
        self.assertTrue(result['analysis_eligible'])
        self.assertEqual(result['run_id'], 'synthetic-run')

    def test_missing_stage_is_incomplete(self):
        (self.root/'stage10/feature_manifest.json').unlink()
        with self.assertRaises(campaign.TechnicalFailure) as error:
            self.executor.validate(self.entry)
        self.assertEqual(error.exception.state, 'INCOMPLETE')

    def test_invalid_eligibility_is_invalid(self):
        self.report['analysis_eligible'] = False
        self.put('stage9/validation_report.json', self.report)
        self.seal()
        with self.assertRaises(campaign.TechnicalFailure) as error:
            self.executor.validate(self.entry)
        self.assertEqual(error.exception.state, 'INVALID')

    def test_lineage_mismatch_is_invalid(self):
        self.feature['source_run_id'] = 'wrong-run'
        self.put('stage10/feature_manifest.json', self.feature)
        self.seal()
        with self.assertRaisesRegex(campaign.TechnicalFailure, 'lineage'):
            self.executor.validate(self.entry)

    def test_changed_file_fails_hash_validation(self):
        self.put('raw/run_status.json', dict(status='completed', run_id='synthetic-run', extra=True))
        with self.assertRaisesRegex(campaign.TechnicalFailure, 'integrity mismatch'):
            self.executor.validate(self.entry)

    def test_unexpected_file_is_invalid(self):
        self.put('unexpected.json', {})
        with self.assertRaisesRegex(campaign.TechnicalFailure, 'not exhaustive'):
            self.executor.validate(self.entry)

    def test_symlink_and_path_escape_are_rejected(self):
        (self.root/'link').symlink_to('/tmp')
        with self.assertRaisesRegex(ContractError, 'Symlink'):
            campaign.inventory(self.root)
        with self.assertRaisesRegex(ContractError, 'integrity mismatch'):
            campaign.checked_files(self.root, [dict(path='../outside', sha256='x')])


if __name__ == '__main__':
    unittest.main()
