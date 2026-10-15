"""Clean-commit runtime binding tests. No real simulation or scientific data."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from analysis.detection.inputs import ContractError
from experiments import stage14_finalize as finalizer
from experiments import stage14_scientific as runner
from experiments.stage14a.prepare import sha
from tests import test_stage14a1 as fixtures


class DefinitiveBindingTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.RunnerV2Tests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root
        self.current=deepcopy(self.fixture.env)
        self.current['stable']['git_head']='a'*40
        self.current['dynamic']['git_status']=''
        for name,value in [('HISTORICAL_BINDING_SHA256',self.fixture.hashes['binding_sha256']),
                           ('PROTOCOL_V2_SHA256',sha(self.fixture.protocol))]:
            p=patch.object(finalizer,name,value);p.start();self.addCleanup(p.stop)

    def finalize(self):
        with patch.object(runner,'run_pipeline',side_effect=AssertionError('Simulation forbidden')):
            return finalizer.finalize(self.current)

    def test_post_commit_binding_preserves_scientific_refs_and_six_dry_runs(self):
        before=sha(self.fixture.protocol)
        summary=self.finalize()
        self.assertEqual(len(summary['baseline_preflights']),6)
        self.assertEqual({r['status'] for r in summary['baseline_preflights']},{'dry_run_ready'})
        self.assertEqual(sha(self.fixture.protocol),before)
        self.assertFalse((self.root/runner.OUTPUT_ROOT).exists())
        b,_,_,docs=runner.load_bundle(self.root/summary['binding'],summary['binding_sha256'])
        self.assertEqual(docs['environment_lock']['reference']['dynamic']['git_status'],'')
        self.assertEqual(docs['environment_lock']['reference']['stable']['git_head'],'a'*40)
        self.assertEqual(docs['historical_environment_lock']['reference']['stable']['git_head'],'fixture')
        self.assertEqual(b['references']['matrix'],json.loads(self.fixture.binding.read_text())['references']['matrix'])

    def test_dirty_tree_refused(self):
        self.current['dynamic']['git_status']=' M source.py'
        with self.assertRaisesRegex(ContractError,'clean Git'):self.finalize()

    def test_old_head_refused(self):
        self.current['stable']['git_head']='fixture'
        with self.assertRaisesRegex(ContractError,'new post-commit'):self.finalize()

    def test_unapproved_software_change_refused(self):
        self.current['stable']['os_id']='other'
        with self.assertRaisesRegex(ContractError,'environment change'):self.finalize()

    def test_unapproved_runtime_change_refused(self):
        self.current['runtime_sha256']={'simulator/config.py':'changed'}
        with self.assertRaisesRegex(ContractError,'runtime change'):self.finalize()

    def test_no_overwrite_definitive_outputs(self):
        self.finalize()
        with self.assertRaises(FileExistsError):self.finalize()

    def test_definitive_runner_requires_current_clean_head(self):
        summary=self.finalize()
        dirty=deepcopy(self.current);dirty['dynamic']['git_status']='?? newfile'
        result=runner.prepare_entry(self.root/summary['binding'],summary['binding_sha256'],
            partition='baseline',run=1,environment=dirty)
        self.assertIn('git_tree_not_clean',result['environment_comparison']['fatal'])
        changed=deepcopy(self.current);changed['stable']['git_head']='b'*40
        result=runner.prepare_entry(self.root/summary['binding'],summary['binding_sha256'],
            partition='baseline',run=1,environment=changed)
        self.assertIn('stable.git_head',result['environment_comparison']['fatal'])

    def test_test_remains_locked(self):
        summary=self.finalize()
        with self.assertRaisesRegex(ContractError,'TEST locked'):
            runner.prepare_entry(self.root/summary['binding'],summary['binding_sha256'],partition='test',run=19,environment=self.current)

    def test_definitive_environment_hash_tamper_refused(self):
        summary=self.finalize()
        lock=self.root/summary['environment_lock'];lock.write_bytes(lock.read_bytes()+b'\n')
        with self.assertRaisesRegex(ContractError,'hash'):
            runner.load_bundle(self.root/summary['binding'],summary['binding_sha256'])
