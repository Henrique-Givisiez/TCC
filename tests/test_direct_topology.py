"""Topology selection and identity guards without a Docker daemon."""
import unittest
from unittest.mock import MagicMock
from simulator.experiment_config import ExperimentConfig
from simulator.direct_target import DirectTarget, require_empty_network
from experiments.capture_topology import capture_destination


def direct_config(**overrides):
    data = dict(topology=dict(mode='direct'), traffic_sources=dict(execution='containers'),
        load_balancer=dict(enabled=False), autoscaler=dict(enabled=False),
        infrastructure=dict(initial_instances=1,min_instances=1,max_instances=1))
    data.update(overrides)
    return ExperimentConfig.from_dict(data)


class TopologyTests(unittest.TestCase):
    def test_historical_and_explicit_proxy(self):
        import json
        self.assertEqual(ExperimentConfig().topology.mode, 'proxy')
        self.assertEqual(ExperimentConfig.from_dict({'topology':{'mode':'proxy'}}).topology.mode,'proxy')
        self.assertNotIn('topology',json.loads(ExperimentConfig().to_json()))

    def test_direct_roundtrip(self):
        import json
        c = direct_config()
        self.assertEqual(ExperimentConfig.from_dict(json.loads(c.to_json())),c)

    def test_contradictions(self):
        for overrides in [dict(topology=dict(mode='other')),dict(load_balancer=dict(enabled=True)),
                          dict(autoscaler=dict(enabled=True)),dict(traffic_sources=dict(execution='host')),
                          dict(infrastructure=dict(initial_instances=2,min_instances=1,max_instances=2))]:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                direct_config(**overrides)

    def test_occupied_network_rejected(self):
        network=MagicMock();network.attrs={'Containers':{'stale':{}}}
        with self.assertRaisesRegex(RuntimeError,'occupied'):require_empty_network(network)
        network.attrs={'Containers':{}};require_empty_network(network)

    def test_direct_identity_and_networks(self):
        from simulator import config
        target=DirectTarget.__new__(DirectTarget)
        target.client=MagicMock();target.expected_id='victim'
        target.identity={'source_network':'sources'}
        c=target.client.containers.get.return_value;c.id='victim';c.status='running'
        c.attrs={'NetworkSettings':{'Networks':{config.DOCKER_NETWORK_NAME:{},'sources':{}}},'HostConfig':{'PortBindings':{}}}
        self.assertIs(target.verify(),c)
        c.attrs['NetworkSettings']['Networks']['foreign']={}
        with self.assertRaisesRegex(RuntimeError,'networks'):target.verify()
        c.id='replacement'
        with self.assertRaisesRegex(RuntimeError,'identity'):target.verify()

    def test_capture_contracts(self):
        legacy=dict(segment='source_proxy',proxy_ip='172.20.0.2')
        direct=dict(segment='source_victim',victim_ip='172.20.0.2',target_ip='172.20.0.2',target_id='victim')
        self.assertEqual(capture_destination(legacy,{}),('172.20.0.2',80))
        self.assertEqual(capture_destination(direct,{'topology':{'mode':'direct'}}),('172.20.0.2',80))
        for capture, cfg in [(direct,{}),(legacy,{'topology':{'mode':'direct'}}),
                             ({},{}),(dict(direct,target_id=None),{'topology':{'mode':'direct'}}),
                             (dict(legacy,topology='direct'),{})]:
            with self.subTest(capture=capture), self.assertRaises(ValueError):capture_destination(capture,cfg)

    def test_isolation_is_specific_to_topology(self):
        from experiments.source_network_audit import validate_isolation
        permitted=dict(victim_name='CONNECTED',victim_ip='TimeoutError')
        validate_isolation(permitted,'direct')
        validate_isolation(dict(victim_name='gaierror',victim_ip='TimeoutError'),'proxy')
        for probes,mode in [(permitted,'proxy'),(dict(victim_name='gaierror',victim_ip='TimeoutError'),'direct'),
                            (dict(victim_name='CONNECTED',victim_ip='CONNECTED'),'direct')]:
            with self.subTest(mode=mode,probes=probes),self.assertRaises(RuntimeError):validate_isolation(probes,mode)
