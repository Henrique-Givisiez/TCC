"""Release permissions and integration: synthetic metadata/mocked execution only."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analysis.detection.inputs import ContractError
from experiments import stage14_campaign as campaign
from experiments import stage14_scientific as scientific
from experiments import stage14_test_release as release
from tests.test_stage14_campaign import DevelopmentExecutor
from tests import test_stage14a1 as fixtures


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RunnerV2Tests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.binding = self.fixture.binding
        self.binding_sha = self.fixture.hashes['binding_sha256']
        self.path = self.root/'administrative_release.json'
        self.evaluation = self.root/'evaluation.json'
        self.evaluation.write_text('{}')
        self.evaluation_sha = scientific.sha(self.evaluation)
        binding, _, _, documents = scientific.load_bundle(self.binding, self.binding_sha)
        self.plan = dict(authority=dict(head='fixture',
            binding=dict(path=str(self.binding.relative_to(self.root)), sha256=self.binding_sha),
            environment=binding['references']['environment_lock'],
            evaluation_protocol=dict(path='evaluation.json', sha256=self.evaluation_sha),
            four_method_freeze=dict(path='freeze.json', sha256='freeze-hash'),
            references=binding['references']), entries=[dict(order=row['order'],
                matrix_identity=campaign.digest(row)) for row in documents['matrix']['runs']
                if row['partition']=='test'])
        self.document = release.release_document(self.plan, authorized_at=scientific.now(),
                                                 authorization='SYNTHETIC DEVELOPMENT authorization')
        self.write()
        mock = patch.object(campaign.FrozenExecutor, 'plan', return_value=deepcopy(self.plan))
        self.mock_plan = mock.start()
        self.addCleanup(mock.stop)

    def write(self):
        self.path.write_bytes(scientific.encode(self.document))
        self.release_sha = scientific.sha(self.path)

    def validate(self, **kwargs):
        return release.validate_release(self.path, self.release_sha,
            binding_path=self.binding, binding_sha256=self.binding_sha,
            evaluation_path=self.evaluation, evaluation_sha256=self.evaluation_sha, **kwargs)

    def execute(self, **kwargs):
        return scientific.execute_entry(self.binding, self.binding_sha, partition='test', run=19,
            execute=True, release_path=self.path, release_sha256=self.release_sha, **kwargs)

    def test_valid_release_authorizes_only_exact_campaign(self):
        result = self.validate(run=19)
        self.assertTrue(result['execution_authorized'])
        self.assertEqual(result['campaign_identity'], campaign.digest(self.plan))
        self.assertEqual(self.document['expected_runs'], 48)

    def test_absent_release_fatal_before_executor_io(self):
        with patch.object(scientific, 'run_pipeline') as pipeline:
            with self.assertRaisesRegex(ContractError, 'locked'):
                scientific.execute_entry(self.binding, self.binding_sha, partition='test', run=19, execute=True)
        pipeline.assert_not_called()

    def test_wrong_head_environment_binding_freeze_evaluation_rejected(self):
        original = deepcopy(self.document)
        for key in ('head', 'environment', 'binding', 'four_method_freeze', 'evaluation_protocol'):
            with self.subTest(field=key):
                self.document = deepcopy(original)
                self.document['authority'][key] = 'wrong' if key=='head' else dict(path='wrong', sha256='wrong')
                self.write()
                with self.assertRaises(ContractError):
                    self.validate()

    def test_wrong_matrix_protocol_seed_plan_rejected(self):
        original = deepcopy(self.document)
        for key in ('matrix', 'protocol', 'seed_plan'):
            with self.subTest(field=key):
                self.document = deepcopy(original)
                self.document['authority']['references'][key]['sha256'] = 'wrong'
                self.write()
                with self.assertRaisesRegex(ContractError, 'authority mismatch'):
                    self.validate()

    def test_actual_authority_drift_rejected_even_unmodified_release(self):
        changed = deepcopy(self.plan)
        changed['authority']['head'] = 'different-runtime-head'
        self.mock_plan.return_value = changed
        with self.assertRaisesRegex(ContractError, 'authority mismatch'):
            self.validate()

    def test_other_campaign_and_reordered_entries_rejected(self):
        for key, value in [('campaign_identity', 'another-campaign'), ('expected_runs', 47),
                           ('ordered_matrix_identities', list(reversed(self.document['ordered_matrix_identities'])))]:
            with self.subTest(field=key):
                old = deepcopy(self.document)
                self.document[key] = value
                self.write()
                with self.assertRaisesRegex(ContractError, 'scope/identity'):
                    self.validate()
                self.document = old

    def test_fitting_calibration_tuning_scoring_evaluation_forbidden(self):
        for operation in ('fitting', 'calibration', 'tuning', 'scientific_scoring', 'scientific_evaluation'):
            with self.subTest(operation=operation), self.assertRaises(ContractError):
                self.validate(operation=operation)

    def test_release_cannot_relax_prohibitions_or_grant_extra_operation(self):
        original = deepcopy(self.document)
        for key in release.PROHIBITIONS:
            self.document = deepcopy(original)
            self.document['prohibitions'][key] = False
            self.write()
            with self.subTest(prohibition=key), self.assertRaises(ContractError):
                self.validate()
        self.document = deepcopy(original)
        self.document['allowed_operations'].append('tuning')
        self.write()
        with self.assertRaises(ContractError):
            self.validate()

    def test_hash_missing_partial_or_unparseable_release_rejected(self):
        with self.assertRaises(ContractError):
            release.validate_release(self.path, 'wrong', binding_path=self.binding, binding_sha256=self.binding_sha)
        self.path.write_text('{broken')
        self.release_sha = scientific.sha(self.path)
        with self.assertRaises(ContractError):
            self.validate()
        self.document = dict(release_version=1)
        self.write()
        with self.assertRaises(ContractError):
            self.validate()

    def test_run_outside_campaign_rejected(self):
        for run in (1, 18, 67):
            with self.assertRaises(ContractError):
                self.validate(run=run)

    def test_preflight_independent_of_absent_or_invalid_release(self):
        self.path.write_text('invalid')
        with patch.object(scientific, 'run_pipeline', side_effect=AssertionError('no execution')):
            result = scientific.execute_entry(self.binding, self.binding_sha, partition='test', run=19,
                execute=False, release_path=self.path, release_sha256='wrong')
        self.assertEqual(result['status'], 'dry_run_ready')
        self.assertFalse(result['execution_authorized'])

    def test_valid_release_reaches_only_mock_pipeline_and_persists_authorization(self):
        def fake(configuration, destination):
            self.assertEqual(configuration['seed'], self.fixture.doc['seeds']['partitions']['test'][0])
            scientific.write(destination/'DEVELOPMENT.json', dict(synthetic=True))
            return dict(run_id='synthetic-only')
        with patch.object(scientific, 'run_pipeline', side_effect=fake) as pipeline:
            result = self.execute()
        pipeline.assert_called_once()
        self.assertTrue(result['execution_authorized'])
        self.assertEqual(result['release']['sha256'], self.release_sha)
        self.assertEqual(result['status'], 'completed')
        self.assertTrue((Path(result['destination'])/'scientific_run_after.json').exists())

    def test_invalid_release_never_invokes_mock_pipeline_or_creates_outputs(self):
        self.document['campaign_identity'] = 'wrong'
        self.write()
        with patch.object(scientific, 'run_pipeline') as pipeline:
            with self.assertRaises(ContractError):
                self.execute()
        pipeline.assert_not_called()
        self.assertFalse((self.root/scientific.OUTPUT_ROOT).exists())

    def test_release_change_between_authorization_and_invocation_is_fatal(self):
        original = scientific.preflight_entry

        def tamper(*args, **kwargs):
            result = original(*args, **kwargs)
            self.path.write_text('changed after preflight')
            return result
        with patch.object(scientific, 'preflight_entry', side_effect=tamper), \
                patch.object(scientific, 'run_pipeline') as pipeline:
            with self.assertRaises(ContractError):
                self.execute()
        pipeline.assert_not_called()

    def test_detector_and_threshold_artifacts_not_read_or_written_by_release(self):
        before = deepcopy(self.plan)
        self.validate()
        self.assertEqual(self.plan, before)
        self.assertEqual(self.validate()['prohibitions']['threshold_changes'], True)
        self.assertEqual(self.validate()['prohibitions']['detector_changes'], True)


class ReleasedCheckpointTests(unittest.TestCase):
    def test_initialization_no_execution_and_release_bound_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            executor = DevelopmentExecutor(directory)
            original = executor.plan
            capsule = dict(path='synthetic-release', sha256='synthetic-release-sha')
            def plan():
                return dict(**original(), release=deepcopy(capsule))
            executor.plan = plan
            coordinator = campaign.Campaign(Path(directory)/'admin', executor)
            initial = coordinator.initialize_authorized()
            self.assertEqual(initial['plan']['release'], capsule)
            self.assertEqual(initial['campaign_identity'], release.campaign_identity(plan()))
            self.assertEqual(executor.calls, [])
            self.assertEqual(campaign.status(coordinator.directory)['pending'], 3)
            coordinator.run(resume=True)
            self.assertEqual([x for x in executor.calls if x[0]=='execute'], [('execute',0),('execute',1),('execute',2)])
            before = campaign.inventory(Path(directory))
            coordinator.run(resume=True)
            self.assertEqual(campaign.inventory(Path(directory)), before)
            capsule['sha256'] = 'different-release'
            with self.assertRaises(ContractError):
                coordinator.run(resume=True)

    def test_real_adapter_forwards_exact_release_to_executor(self):
        adapter = campaign.FrozenExecutor('binding','binding-sha','evaluation','evaluation-sha',
                                          release_path='release', release_sha256='release-sha')
        with patch.object(scientific, 'execute_entry', return_value={}) as invoke:
            adapter.execute(dict(order=23))
        self.assertEqual(invoke.call_args.kwargs['release_path'], 'release')
        self.assertEqual(invoke.call_args.kwargs['release_sha256'], 'release-sha')


if __name__ == '__main__':
    unittest.main()
