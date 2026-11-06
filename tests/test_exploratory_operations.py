"""I1 tests: fakes only; never starts Docker or sends requests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from simulator.exploratory_operations import Policy, Operations, resolve_images, verify_image, resource_reasons
from simulator.experiment_config import ExperimentConfig
from simulator.source_manager import worker_quotas

IMAGE='sha256:'+'a'*64


def cfg(n=2, budget=4, duration=60, endpoint='/medium', rate=1):
    return ExperimentConfig.from_dict(dict(topology={'mode':'direct'},traffic_sources={'execution':'containers'},
        load_balancer={'enabled':False},autoscaler={'enabled':False},
        infrastructure={'initial_instances':1,'min_instances':1,'max_instances':1},
        diagnostics={'enabled':True},attack={'enabled':False,'attackers':0,'rate':0},
        normal_traffic={'clients':n,'max_concurrent_sends':budget,'endpoint':endpoint,'rate':rate},duration_seconds=duration))


def policy():
    return Policy(1,1,100,100,1000,5,240,3)


class OperationsTests(unittest.TestCase):
    def test_images_existing_and_missing_never_build(self):
        client=MagicMock(); client.images.get.return_value.id=IMAGE
        self.assertEqual(resolve_images(client,IMAGE,IMAGE)['victim'],IMAGE)
        client.images.get.side_effect=RuntimeError('missing')
        with self.assertRaisesRegex(RuntimeError,'missing'):resolve_images(client,IMAGE,IMAGE)
        client.images.build.assert_not_called();client.images.pull.assert_not_called()

    def test_image_mismatch_and_tags(self):
        client=MagicMock();client.images.get.return_value.id='other'
        with self.assertRaises(RuntimeError):resolve_images(client,IMAGE,IMAGE)
        with self.assertRaises(ValueError):resolve_images(client,'tag',IMAGE)
        c=MagicMock();c.attrs={'Image':'other'}
        with self.assertRaises(RuntimeError):verify_image(c,IMAGE)

    def test_all_approved_shapes(self):
        for n,rate,budget,duration,endpoint in [(2,1,4,60,'/medium'),(2,1,4,60,'/expensive'),
                    (2,8,64,150,'/medium'),(4,4,64,150,'/medium'),(2,16,64,150,'/medium'),(4,8,64,150,'/medium')]:
            c=cfg(n,budget,duration,endpoint,rate);policy().validate(c)
            self.assertEqual(sum(worker_quotas(budget,n)),budget)
            self.assertEqual(c.server.process_pool_workers,2);self.assertFalse(c.attack.enabled)

    def test_pending_limits_and_timeout_reserve(self):
        with self.assertRaisesRegex(ValueError,'pending'):Policy().validate(cfg())
        with self.assertRaisesRegex(ValueError,'reserve'):
            Policy(1,1,100,100,1000,5,70,3).validate(cfg())

    def test_degradation_not_a_resource_trigger(self):
        s=dict(available_bytes=2,disk_free_bytes=2,artifact_bytes=0,containers=[],cpu=999,http_failures=100,worker_wait=999)
        self.assertEqual(resource_reasons(s,policy()),[])
        s['available_bytes']=0;self.assertEqual(resource_reasons(s,policy()),['host_memory'])

    def test_readiness_refuses_residual_without_removal(self):
        with tempfile.TemporaryDirectory() as t:
            op=Operations(policy(),{},t);client=MagicMock();client.containers.list.return_value=[MagicMock(id='foreign')]
            client.networks.get.return_value.attrs={'Containers':{}}
            with patch('experiments.development_d1_ops.process_rows',return_value=[]):
                with self.assertRaisesRegex(RuntimeError,'readiness'):op.ready(client)
            client.containers.get.assert_not_called()
            self.assertFalse(op.report['readiness']['verified'])

    def test_clean_readiness_and_verification_error(self):
        with tempfile.TemporaryDirectory() as t:
            op=Operations(policy(),{},t);client=MagicMock();client.containers.list.return_value=[]
            client.networks.get.return_value.attrs={'Containers':{}}
            with patch('experiments.development_d1_ops.process_rows',return_value=[]),patch.object(op,'observe'):
                op.ready(client)
            self.assertTrue(op.report['readiness']['verified'])
            with patch('experiments.development_d1_ops.process_rows',side_effect=RuntimeError('unverified')):
                with self.assertRaises(RuntimeError):op.ready(client)

    def test_cleanup_failure_continues_owned_only(self):
        with tempfile.TemporaryDirectory() as t:
            op=Operations(policy(),{},t);op.owned={'one':'source','two':'victim'};client=MagicMock()
            client.containers.get.side_effect=[RuntimeError('cannot inspect'),MagicMock()];errors=[]
            op.finish(client,errors)
            self.assertEqual(client.containers.get.call_count,2);self.assertTrue(errors)
            self.assertFalse(op.report['cleanup_verified'])

    def test_policy_persisted_and_timer(self):
        with tempfile.TemporaryDirectory() as t:
            op=Operations(policy(),{'victim':IMAGE},t)
            with patch('signal.getitimer',return_value=(0.,0.)),patch('signal.signal') as handler,patch('signal.setitimer'):
                op.arm();callback=handler.call_args.args[1]
                with self.assertRaises(TimeoutError):callback()
                op.disarm()
            op.persist();self.assertTrue((Path(t)/'operational_policy.json').exists())
            self.assertEqual(op.report['actions'][0]['reasons'],['global_timeout'])

    def test_historical_builder_still_builds_when_missing(self):
        import sys
        fake=MagicMock()
        import docker
        fake.images.get.side_effect=docker.errors.ImageNotFound('missing')
        fake.images.build.return_value=(MagicMock(),[])
        with patch('docker.from_env',return_value=fake):
            from simulator import docker_manager
        with patch.object(docker_manager,'client',fake):
            self.assertTrue(docker_manager.build_docker_image())
        fake.images.build.assert_called_once()

    def test_memory_oom_storage_actions(self):
        s=dict(available_bytes=2,disk_free_bytes=2,artifact_bytes=1001,
               containers=[dict(id='owned',role='victim',oom=True,restarts=0,memory=101)])
        self.assertEqual(resource_reasons(s,policy()),['artifact_budget','oom_or_restart:owned','container_memory:owned'])
