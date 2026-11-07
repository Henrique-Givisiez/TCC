"""Protected compositions and image inspection: no Docker daemon or traffic."""
import io
import json
import tarfile
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch
from simulator.experiment_config import ExperimentConfig, AttackConfig
from simulator.exploratory_operations import Policy, Operations, validate_composition, resource_reasons
from experiments.diagnostic_run import prepare_attempt
from experiments.image_code_evidence import expected_files, verify_image_code
from tests.test_exploratory_operations import cfg, policy, IMAGE


def configuration(composition, mechanism='http_request_flooding'):
    base=cfg(duration=150,n=0 if composition=='offensive' else 2,budget=64,rate=8)
    attack=AttackConfig(enabled=composition!='legitimate',attackers=0 if composition=='legitimate' else 2,
        mechanism='' if composition=='legitimate' else mechanism,endpoint='/expensive' if mechanism=='computational_asymmetry' else '/medium',
        rate=0 if composition=='legitimate' else 16,start_seconds=30,duration_seconds=30)
    return replace(base,attack=attack)


def protected_policy(): return replace(policy(),version='exploratory-offensive-v1')


class CompositionTests(unittest.TestCase):
    def test_all_shapes_and_mechanisms(self):
        for composition in ('legitimate','offensive','combined'):
            for mechanism in ('computational_asymmetry','http_request_flooding'):
                c=configuration(composition,mechanism)
                protected_policy().validate(c)
                self.assertEqual(validate_composition(c,composition),composition)
                self.assertEqual(ExperimentConfig.from_dict(json.loads(c.to_json())),c)
                self.assertEqual(c.server.process_pool_workers,2)
    def test_no_legitimate_source_required(self):
        c=configuration('offensive')
        self.assertEqual(c.normal_traffic.clients,0)
        protected_policy().validate(c)
    def test_bad_configurations_before_runtime(self):
        c=configuration('combined')
        for attack in (replace(c.attack,mechanism=''), replace(c.attack,endpoint='/'),
                       replace(c.attack,mechanism='both'), replace(c.attack,attackers=0),
                       replace(c.attack,rate=0),replace(c.attack,duration_seconds=0)):
            with self.assertRaises(ValueError): protected_policy().validate(replace(c,attack=attack))
        with self.assertRaises(ValueError): validate_composition(c,'offensive')
        with self.assertRaises(ValueError): protected_policy().validate(replace(c,normal_traffic=replace(c.normal_traffic,endpoint='/expensive')))
    def test_legacy_i1_and_canonical_config_preserved(self):
        policy().validate(cfg())
        with self.assertRaises(ValueError): policy().validate(configuration('combined'))
        self.assertNotIn('mechanism',json.loads(cfg().to_json())['attack'])
    def test_degradation_and_resources(self):
        s=dict(available_bytes=2,disk_free_bytes=2,artifact_bytes=0,containers=[],cpu=999,latency=999,timeouts=999,nominal_miss=True)
        self.assertEqual(resource_reasons(s,protected_policy()),[])
        s['disk_free_bytes']=0
        self.assertEqual(resource_reasons(s,protected_policy()),['disk_space'])
        s['available_bytes']=0
        self.assertIn('host_memory',resource_reasons(s,protected_policy()))
    def test_global_budget_includes_preflight_time(self):
        with tempfile.TemporaryDirectory() as d:
            op=Operations(protected_policy(),{},d)
            op.report['attempt']={'started_monotonic':10}
            with patch('signal.getitimer',return_value=(0,0)),patch('signal.signal'),patch('signal.setitimer') as timer,patch('time.monotonic',return_value=20):
                op.arm();self.assertEqual(timer.call_args.args[1],230);op.disarm()
    def test_attempt_no_overwrite_and_failure_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            op=Operations(protected_policy(),{'victim':IMAGE,'source':IMAGE},Path(d)/'raw')
            client=MagicMock();client.api.timeout=9
            with patch.object(Operations,'arm'),patch.object(Operations,'disarm'),patch.object(Operations,'ready',side_effect=RuntimeError('memory')):
                with self.assertRaises(RuntimeError):prepare_attempt(op,configuration('offensive'),client,'offensive')
            evidence=json.loads((Path(d)/'raw.attempt/attempt.json').read_text())
            self.assertEqual(evidence['status'],'preflight_failed')
            self.assertEqual(client.api.timeout,9)
            with self.assertRaises(FileExistsError):prepare_attempt(op,configuration('offensive'),client,'offensive')
            client.containers.create.assert_not_called()


class ImageTests(unittest.TestCase):
    def fake(self, role, corrupt=False):
        root=Path(__file__).resolve().parents[1]
        files=expected_files(role)
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w') as tar:
            for path in files:
                # Get original bytes matching the declared manifest.
                source=root/'simulator/app'/Path(path).name if role=='victim' and path!='/app/diagnostics.py' else root/'simulator'/Path(path).name
                if path=='/app/requirements.txt':source=root/'docker/requirements.sources.txt'
                data=source.read_bytes()
                if corrupt:data=b'old code'
                member=tarfile.TarInfo(path.lstrip('/'));member.size=len(data)
                tar.addfile(member,io.BytesIO(data))
        client=MagicMock();container=client.containers.create.return_value
        container.attrs={'Image':IMAGE};container.get_archive.return_value=([stream.getvalue()],{})
        client.images.get.return_value.attrs={'Config':dict(WorkingDir='/app',Entrypoint=['python','-B','-m','simulator.source_runner'] if role=='source' else None,Cmd=['python','simple_server.py'])}
        return client,container
    def test_current_image_code_without_execution(self):
        for role in ('victim','source'):
            client,container=self.fake(role)
            self.assertTrue(verify_image_code(client,{role:IMAGE})[role]['verified'])
            container.start.assert_not_called();container.remove.assert_called_once_with(force=True)
            client.images.build.assert_not_called();client.images.pull.assert_not_called()
    def test_stale_image_rejected_and_removed(self):
        client,container=self.fake('victim',True)
        with self.assertRaisesRegex(RuntimeError,'differs'):verify_image_code(client,{'victim':IMAGE})
        container.remove.assert_called_once()
    def test_wrong_entrypoint_rejected(self):
        client,container=self.fake('source');client.images.get.return_value.attrs['Config']['Entrypoint']=['old']
        with self.assertRaisesRegex(RuntimeError,'launch'):verify_image_code(client,{'source':IMAGE})
        client.containers.create.assert_not_called()

class ProtectedCertificationTests(unittest.TestCase):
    def fixture(self, root):
        import csv
        from tests.test_exploratory_certification import CertificationTests
        op,destination=CertificationTests().fixture(root)
        op.policy=protected_policy()
        configuration_data=json.loads(configuration('offensive').to_json())
        (root/'effective_config.json').write_text(json.dumps(configuration_data))
        (root/'diagnostics/victim').mkdir(parents=True)
        (root/'diagnostics/victim/events.summary.json').write_text('{"complete":true,"observation_complete":true,"pending":4}')
        (root/'request_log.csv').write_text('generator,outcome,elapsed_seconds,end_elapsed_seconds\nattack,transport_error,31,33\n')
        (destination/'dataset_manifest.json').write_text('{"run_id":"r"}')
        return op,destination
    def test_http_degradation_allowed_after_real_validation_gate(self):
        with tempfile.TemporaryDirectory() as d:
            op,destination=self.fixture(Path(d))
            with patch('experiments.validate_dataset.validate_dataset',return_value={'dataset_valid':True,'analysis_eligible':True}) as validator,patch('experiments.validate_dataset.write_report'):
                op.certify(destination,[])
            validator.assert_called_once_with(destination)
            self.assertTrue(op.report['progression_allowed'],op.report)
            self.assertEqual(op.report['outcome'],'completed_with_http_degradation')
            self.assertEqual(op.report['traffic_rates']['attack']['nominal_rps'],32)
            self.assertEqual(op.report['traffic_rates']['attack']['realized_start_rps'],1/30)
    def test_validation_failure_blocks_even_with_clean_shutdown(self):
        with tempfile.TemporaryDirectory() as d:
            op,destination=self.fixture(Path(d))
            with patch('experiments.validate_dataset.validate_dataset',return_value={'dataset_valid':False,'analysis_eligible':False}),patch('experiments.validate_dataset.write_report'):
                op.certify(destination,[])
            self.assertFalse(op.report['progression_allowed'])
            self.assertEqual(op.report['certification'],'blocked')
    def test_observation_loss_blocks_but_pending_does_not(self):
        with tempfile.TemporaryDirectory() as d:
            op,destination=self.fixture(Path(d))
            (Path(d)/'diagnostics/victim/events.summary.json').write_text('{"complete":false,"observation_complete":false}')
            op.certify(destination,[])
            self.assertFalse(op.report['progression_allowed'])
            self.assertTrue(any('victim diagnostics incomplete' in r for r in op.report['failures']))
    def test_new_policy_requires_prepared_attempt(self):
        import sys
        from types import SimpleNamespace
        from experiments.dataset_run import run_recorded
        with tempfile.TemporaryDirectory() as d,patch.dict(sys.modules,{'simulator.main_orchestrator':MagicMock()}):
            op=Operations(protected_policy(),{},Path(d)/'raw')
            with self.assertRaisesRegex(RuntimeError,'prepared attempt'):
                run_recorded(configuration('offensive'),Path(d)/'raw',op)

class AttemptIntegrationTests(unittest.TestCase):
    def test_prepared_attempt_binds_preflight_and_actual_run(self):
        import hashlib
        from experiments.dataset_run import run_recorded
        from simulator import main_orchestrator
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); c=replace(configuration('offensive'),seed=42)
            op=Operations(protected_policy(),{'victim':IMAGE,'source':IMAGE},root/'raw')
            client=MagicMock();client.api.timeout=9;client.images.get.return_value.id=IMAGE
            evidence={r:dict(image_id=IMAGE,files=expected_files(r),verified=True) for r in ('victim','source')}
            with patch.object(Operations,'arm'),patch.object(Operations,'disarm'),patch.object(Operations,'ready',lambda this,c:this.persist()),patch('experiments.image_code_evidence.verify_image_code',return_value=evidence):
                prepare_attempt(op,c,client,'offensive')
            attempt=json.loads((root/'raw.attempt/attempt.json').read_text())
            self.assertEqual(attempt['status'],'ready')
            self.assertEqual(attempt['phases'],{'pre':[0,30],'attack':[30,60],'post':[60,150]})
            self.assertEqual(attempt['configuration_sha256'],hashlib.sha256(c.to_json().encode()).hexdigest())
            self.assertEqual(client.api.timeout,9)
            with patch.object(main_orchestrator,'main',return_value=None) as run:
                run_recorded(c,root/'raw',op)
            self.assertEqual(run.call_args.kwargs['operational'],op)
            self.assertEqual(hashlib.sha256((root/'raw/preflight.json').read_bytes()).hexdigest(),attempt['preflight_sha256'])
            self.assertEqual(json.loads((root/'raw/attempt.json').read_text())['composition'],'offensive')
    def test_configuration_templates(self):
        root=Path('experiments/configs/protected_compositions')
        for path in root.glob('pilot-*.json'):
            c=ExperimentConfig.load(path)
            protected_policy().validate(c)
            self.assertEqual(c.duration_seconds,150)
            self.assertEqual(c.seed,20261107)
