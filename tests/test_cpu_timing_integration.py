"""D1.1 preparation/activation contracts; no Docker daemon or traffic."""
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from experiments.cpu_timing_diagnostic import CONFIG_ROOT, prepare_request, bind_collector
from simulator.experiment_config import ExperimentConfig
from simulator.stats_collector import StatsCollector


class TimingIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.experiment=ExperimentConfig.load(CONFIG_ROOT/'f96_240.json').resolve_seed()
        self.images=json.loads((CONFIG_ROOT/'reference.json').read_text())['images']

    def request(self, **changes):
        args=dict(experiment=self.experiment,directory=self.root/'diagnostics',output=self.root/'raw',
                  dataset=self.root/'dataset',policy_path=CONFIG_ROOT/'policy.json',
                  images=self.images,composition='combined',pilot=None)
        args.update(changes)
        return prepare_request(**args)

    def test_configuration_preserves_f96_load_and_changes_only_schedule(self):
        e=self.experiment
        self.assertEqual((e.duration_seconds,e.attack.start_seconds,e.attack.duration_seconds), (240,30,120))
        self.assertEqual((e.topology.mode,e.traffic_sources.execution),('direct','containers'))
        self.assertEqual((e.normal_traffic.clients,e.normal_traffic.rate,e.normal_traffic.endpoint,
                          e.normal_traffic.max_concurrent_sends), (2,8,'/medium',64))
        self.assertEqual((e.attack.attackers,e.attack.rate,e.attack.endpoint,e.attack.max_concurrent_sends),
                         (2,32,'/medium',96))
        self.assertEqual((e.monitoring.stats_poll_interval_seconds,e.server.process_pool_workers),(1,2))
        self.assertTrue(all(ref.startswith('sha256:') and len(ref)==71 for ref in self.images.values()))

    def test_explicit_activation_after_cpu_bind_and_before_start(self):
        request=self.request()
        c=StatsCollector(MagicMock());clock=SimpleNamespace(monotonic_initial=50,epoch_initial=100)
        c.bind_cpu('run1',clock,self.root/'victim_stats.jsonl')
        op=SimpleNamespace(cpu_timing_request=request,report={'attempt':dict(
            cpu_timing_exploratory=True,campaign_slot=False)})
        bind_collector(c,self.experiment,op)
        self.assertIsNone(c._t.ident)
        self.assertEqual(c.timing_diagnostics.path,request.directory/'collector.cpu-timing-diagnostic.json')
        self.assertEqual(c.timing_diagnostics.max_records,512)
        self.assertFalse(c.timing_diagnostics.path.exists())
        self.assertTrue((request.directory/'request.json').exists())
        unbound=StatsCollector(MagicMock())
        with self.assertRaisesRegex(RuntimeError,'Bind scientific CPU evidence first'):
            bind_collector(unbound,self.experiment,op)

    def test_normal_paths_disabled_and_scientific_attempt_rejected(self):
        c=MagicMock()
        for op in (None,SimpleNamespace(report={'attempt':{'scientific_pilot':True}})):
            bind_collector(c,self.experiment,op)
        c.bind_timing_diagnostics.assert_not_called()
        request=self.request()
        for attempt in ({},dict(cpu_timing_exploratory=True,campaign_slot=True),
                        dict(cpu_timing_exploratory=True,campaign_slot=False,scientific_pilot=True)):
            op=SimpleNamespace(cpu_timing_request=request,report={'attempt':attempt})
            with self.assertRaises(ValueError):bind_collector(c,self.experiment,op)
        c.bind_timing_diagnostics.assert_not_called()

    def test_rejects_wrong_config_images_policy_or_pilot_before_creating_directory(self):
        for changes in (dict(experiment=replace(self.experiment,duration_seconds=390)),
                        dict(images={'victim':'mutable:tag','source':self.images['source']}),
                        dict(policy_path=None),dict(pilot='F96'),dict(composition='offensive')):
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.request(**changes)
            self.assertFalse((self.root/'diagnostics').exists())

    def test_disjoint_fresh_paths_and_disk_gate(self):
        for directory in (self.root/'raw'/'diagnostics',self.root/'dataset',self.root):
            with self.assertRaises(ValueError):self.request(directory=directory)
        with patch('experiments.cpu_timing_diagnostic.shutil.disk_usage',return_value=SimpleNamespace(free=1)):
            with self.assertRaisesRegex(RuntimeError,'free disk'):self.request()
        self.assertFalse((self.root/'diagnostics').exists())
        self.request()
        with self.assertRaises(FileExistsError):self.request()

    def test_cli_passes_explicit_request_only_to_exploratory_operations(self):
        import sys
        from experiments import diagnostic_run
        from simulator import config
        from simulator.exploratory_operations import Operations
        fake_docker=SimpleNamespace(client=MagicMock())
        args=['diagnostic_run','--config',str(CONFIG_ROOT/'f96_240.json'),
              '--output',str(self.root/'raw'),'--dataset-output',str(self.root/'dataset'),
              '--operational-policy',str(CONFIG_ROOT/'policy.json'),'--composition','combined',
              '--victim-image',self.images['victim'],'--source-image',self.images['source'],
              '--cpu-timing-diagnostic-dir',str(self.root/'diagnostics')]
        before=(config.DOCKER_IMAGE_NAME,config.SOURCE_IMAGE)
        def prepared(op,*args): op.report['attempt']={}
        def procedure(run,export,op,*args):
            self.assertEqual(op.cpu_timing_request.directory,self.root/'diagnostics')
            self.assertTrue(op.report['attempt']['cpu_timing_exploratory'])
            self.assertFalse(op.report['attempt']['campaign_slot'])
            self.assertEqual(op.images,self.images)
        with patch.object(sys,'argv',args), \
             patch.dict(sys.modules,{'simulator.docker_manager':fake_docker}), \
             patch('experiments.diagnostic_run.prepare_attempt',side_effect=prepared), \
             patch('experiments.diagnostic_run.complete_procedure',side_effect=procedure) as execute:
            diagnostic_run.main()
        execute.assert_called_once()
        self.assertEqual((config.DOCKER_IMAGE_NAME,config.SOURCE_IMAGE),before)

    def test_cli_rejects_timing_with_pilot_without_docker_import(self):
        import sys
        from experiments import diagnostic_run
        args=['diagnostic_run','--config',str(CONFIG_ROOT/'f96_240.json'),
              '--output',str(self.root/'raw'),'--dataset-output',str(self.root/'dataset'),
              '--operational-policy',str(CONFIG_ROOT/'policy.json'),'--composition','combined',
              '--victim-image',self.images['victim'],'--source-image',self.images['source'],
              '--scientific-pilot-scenario','F96','--cpu-timing-diagnostic-dir',str(self.root/'diagnostics')]
        with patch.object(sys,'argv',args), self.assertRaisesRegex(ValueError,'never a scientific pilot'):
            diagnostic_run.main()
        self.assertFalse((self.root/'diagnostics').exists())


if __name__=='__main__':unittest.main()
