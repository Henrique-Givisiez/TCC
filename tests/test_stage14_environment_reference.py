"""Hash-bound definitive locks at explicit paths; synthetic fixtures only."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from analysis.detection.inputs import ContractError
from experiments import stage14_scientific as runner
from experiments.stage14a.prepare import sha, write
from tests import test_stage14_finalize as fixtures


class EnvironmentReferenceTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.DefinitiveBindingTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root = fixture.root
        self.current = deepcopy(fixture.current)
        summary = fixture.finalize()
        self.current['stable'].update(kernel='7.0.0-fixture', engine_kernel='7.0.0-fixture')
        self.original_lock = self.root / summary['environment_lock']
        self.original_lock_hash = sha(self.original_lock)
        self.lock = self.root / 'experiment_results/refreeze/new-environment.json'
        self.lock_doc = json.loads(self.original_lock.read_text())
        self.lock_doc['reference']['stable'].update(self.current['stable'])
        write(self.lock, self.lock_doc)
        self.binding = self.root / 'experiment_results/refreeze/binding.json'
        self.binding_doc = json.loads((self.root / summary['binding']).read_text())
        self.binding_doc['references']['definitive_environment_lock'] = self.reference(self.lock)
        write(self.binding, self.binding_doc)
        guard = patch.object(runner, 'run_pipeline', side_effect=AssertionError('Simulation forbidden'))
        guard.start()
        self.addCleanup(guard.stop)

    def reference(self, path):
        return dict(path=str(path.relative_to(self.root)), sha256=sha(path))

    def save_binding(self):
        self.binding.write_text(json.dumps(self.binding_doc))

    def save_lock(self):
        self.lock.write_text(json.dumps(self.lock_doc))
        self.binding_doc['references']['definitive_environment_lock'] = self.reference(self.lock)
        self.save_binding()

    def prepare(self, environment=None):
        return runner.prepare_entry(self.binding, sha(self.binding), partition='baseline', run=1,
                                    environment=self.current if environment is None else environment)

    def test_valid_lock_outside_old_path_and_historical_lock_preserved(self):
        result = self.prepare()
        self.assertEqual(result['status'], 'dry_run_ready')
        self.assertEqual(result['environment_comparison']['fatal'], [])
        self.assertEqual(result['references']['definitive_environment_lock'], self.reference(self.lock))
        self.assertEqual(sha(self.original_lock), self.original_lock_hash)
        self.assertFalse((self.root / runner.OUTPUT_ROOT).exists())

    def test_missing_lock_rejected(self):
        self.binding_doc['references']['definitive_environment_lock']['path'] = 'missing.json'
        self.save_binding()
        with self.assertRaisesRegex(ContractError, 'hash/path mismatch'):
            self.prepare()

    def test_changed_path_to_different_content_without_matching_hash_rejected(self):
        other = self.root / 'experiment_results/refreeze/other.json'
        write(other, dict(unrelated=True))
        self.binding_doc['references']['definitive_environment_lock']['path'] = str(other.relative_to(self.root))
        self.save_binding()
        with self.assertRaisesRegex(ContractError, 'hash/path mismatch'):
            self.prepare()

    def test_path_outside_repository_rejected(self):
        self.binding_doc['references']['definitive_environment_lock']['path'] = '../outside.json'
        self.save_binding()
        with self.assertRaisesRegex(ContractError, 'hash/path mismatch'):
            self.prepare()

    def test_changed_content_rejected(self):
        self.lock.write_bytes(self.lock.read_bytes() + b'\n')
        with self.assertRaisesRegex(ContractError, 'hash/path mismatch'):
            self.prepare()

    def test_incorrect_lock_hash_rejected(self):
        self.binding_doc['references']['definitive_environment_lock']['sha256'] = '0' * 64
        self.save_binding()
        with self.assertRaisesRegex(ContractError, 'hash/path mismatch'):
            self.prepare()

    def test_missing_lock_hash_rejected(self):
        del self.binding_doc['references']['definitive_environment_lock']['sha256']
        self.save_binding()
        with self.assertRaisesRegex(ContractError, 'Explicit path/hash'):
            self.prepare()

    def test_other_head_in_rehashed_lock_rejected(self):
        self.lock_doc['reference']['stable']['git_head'] = 'b' * 40
        self.save_lock()
        with self.assertRaisesRegex(ContractError, 'matching clean campaign HEAD/history'):
            self.prepare()

    def test_other_head_in_both_rehashed_binding_and_lock_is_fatal(self):
        self.lock_doc['reference']['stable']['git_head'] = 'b' * 40
        self.binding_doc['campaign_git_head'] = 'b' * 40
        self.save_lock()
        result = self.prepare()
        self.assertEqual(result['status'], 'preflight_rejected')
        self.assertIn('stable.git_head', result['environment_comparison']['fatal'])

    def test_dirty_rehashed_lock_rejected(self):
        self.lock_doc['reference']['dynamic']['git_status'] = ' M source.py'
        self.save_lock()
        with self.assertRaisesRegex(ContractError, 'matching clean campaign HEAD/history'):
            self.prepare()

    def test_current_dirty_tree_is_fatal(self):
        current = deepcopy(self.current)
        current['dynamic']['git_status'] = '?? unreviewed.py'
        self.assertIn('git_tree_not_clean', self.prepare(current)['environment_comparison']['fatal'])

    def replace_scientific_document(self, name, mutate):
        ref = self.binding_doc['references'][name]
        path = self.root / ref['path']
        doc = json.loads(path.read_text())
        mutate(doc)
        path.write_text(json.dumps(doc))
        # Rehash to exercise content/genealogy checks, not only byte integrity.
        ref['sha256'] = sha(path)
        self.save_binding()

    def test_divergent_rehashed_protocol_rejected(self):
        self.replace_scientific_document('protocol', lambda d: d.update(protocol_version=999))
        with self.assertRaises(ContractError):
            self.prepare()

    def test_divergent_rehashed_seed_plan_rejected(self):
        self.replace_scientific_document('seed_plan', lambda d: d['partitions']['baseline'].__setitem__(0, 42))
        with self.assertRaisesRegex(ContractError, 'Protocol binding mismatch'):
            self.prepare()

    def test_divergent_rehashed_matrix_rejected(self):
        self.replace_scientific_document('matrix', lambda d: d['runs'][0].update(seed=42))
        with self.assertRaisesRegex(ContractError, 'Protocol binding mismatch'):
            self.prepare()

    def test_rehashed_historical_lock_reference_tamper_rejected(self):
        self.lock_doc['historical_environment_lock']['sha256'] = '0' * 64
        self.save_lock()
        with self.assertRaisesRegex(ContractError, 'matching clean campaign HEAD/history'):
            self.prepare()

    def test_rehashed_source_binding_reference_tamper_rejected(self):
        self.lock_doc['source_binding']['sha256'] = '0' * 64
        self.save_lock()
        with self.assertRaisesRegex(ContractError, 'hash/path mismatch'):
            self.prepare()

    def test_rehashed_source_binding_scientific_genealogy_tamper_rejected(self):
        source = self.root / 'experiment_results/refreeze/false-history.json'
        doc = json.loads((self.root / self.lock_doc['source_binding']['path']).read_text())
        doc['references']['matrix']['sha256'] = '0' * 64
        write(source, doc)
        self.lock_doc['source_binding'] = self.reference(source)
        self.save_lock()
        with self.assertRaisesRegex(ContractError, 'changed historical scientific references'):
            self.prepare()

    def test_kernel_divergence_is_fatal(self):
        current = deepcopy(self.current)
        current['stable']['kernel'] = 'different'
        result = self.prepare(current)
        self.assertEqual(result['status'], 'preflight_rejected')
        self.assertIn('stable.kernel', result['environment_comparison']['fatal'])

    def test_engine_kernel_divergence_is_fatal(self):
        current = deepcopy(self.current)
        current['stable']['engine_kernel'] = 'different'
        result = self.prepare(current)
        self.assertEqual(result['status'], 'preflight_rejected')
        self.assertIn('stable.engine_kernel', result['environment_comparison']['fatal'])

    def test_binding_tampered_after_authorized_hash_rejected(self):
        authorized = sha(self.binding)
        self.binding.write_bytes(self.binding.read_bytes() + b'\n')
        with self.assertRaisesRegex(ContractError, 'Binding manifest hash mismatch'):
            runner.prepare_entry(self.binding, authorized, partition='baseline', run=1,
                                 environment=self.current)

    def test_rehashed_binding_kind_tamper_rejected(self):
        self.binding_doc['binding_kind'] = 'arbitrary'
        self.save_binding()
        with self.assertRaisesRegex(ContractError, 'Explicit definitive binding kind'):
            self.prepare()
