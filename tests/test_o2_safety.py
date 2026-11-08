import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from analysis.detection.inputs import ContractError, digest
from experiments.scientific_collection import DockerBackend, CollectionFailure
from experiments.scientific_safety import require_storage, require_release
from experiments import c135


class OperationalSafetyTests(unittest.TestCase):
    def test_backend_classifies_real_capture_sidecars_and_conservative_failures(self):
        for mode, expected in [('loss','CAPTURE_LOSS'),('dataset_invalid','DATASET_INVALID'),('mixed','DRAIN_OR_EXECUTION_UNCONFIRMED'),
                               ('drain','DRAIN_OR_EXECUTION_UNCONFIRMED'),('cleanup','CLEANUP_UNCONFIRMED'),
                               ('missing','INDETERMINATE_ATTEMPT'),('readiness','CLEANUP_UNCONFIRMED'),('contradiction','DRAIN_OR_EXECUTION_UNCONFIRMED')]:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                d=Path(tmp);raw=d/'raw';(raw/'source_artifacts').mkdir(parents=True);(d/'dataset').mkdir()
                def put(path,value):path.write_text(json.dumps(value))
                put(d/'config.json',{});put(raw/'effective_config.json',{});put(d/'dataset/dataset_manifest.json',{})
                put(d/'execution.json',{'returncode':0 if mode=='dataset_invalid' else 1});put(d/'cleanup.json',{'verified':mode!='cleanup'})
                if mode=='missing':(d/'execution.json').unlink()
                if mode=='readiness':put(d/'cleanup.json',dict(verified=True,readiness=dict(verified=False)))
                status=dict(status='incomplete',run_id='run',end_reason='simulation_end',producers_drained=True,
                            errors=['capture: tcpdump CSV capture failed: returncode=0, counters={}'],capture_results={})
                if mode=='mixed':status['errors'].append('source aggregation: broken')
                from simulator.capture_lifecycle import parse_capture_counters
                for name,rp,sp in [('csv',raw/'traffic_capture.csv.capture.json',raw/'traffic_capture.stderr'),
                        ('pcap',raw/'source_artifacts/traffic_capture.pcap.capture.json',raw/'source_artifacts/traffic_capture.pcap.stderr')]:
                    diagnostic=f"12 packets captured\n13 packets received by filter\n{1 if name=='csv' else 0} packets dropped by kernel\n"
                    sp.write_text(diagnostic);report=dict(returncode=0,launch_error=None,
                        accepted=name!='csv',capture_counters=parse_capture_counters(diagnostic))
                    status['capture_results'][name]=report;put(rp,report)
                put(raw/'victim_stats.summary.json',dict(run_id='run',worker_finished=True,fatal_error=None))
                if mode=='contradiction':status['capture_results']['csv']['returncode']=2
                put(raw/'run_status.json',status)
                entry=dict(id='slot',config=str(d/'config.json'),config_sha256=digest(d/'config.json'))
                with patch('simulator.experiment_config.ExperimentConfig.load',return_value=SimpleNamespace()), \
                     patch('experiments.stress_processing.reconcile',return_value=({'controlled_closure':mode!='drain','run_id':'run'},[],None)), \
                     patch('experiments.stress_processing.validate_ground_truth'), \
                     patch('experiments.stress_review.replay_observer',return_value={'stop':None}), \
                     patch('experiments.scientific_operations.is_direct',return_value=True), \
                     patch('experiments.scientific_operations.collection_checks',return_value=[]), \
                     patch('experiments.validate_dataset.validate_dataset',return_value={'dataset_valid':False,'analysis_eligible':False}):
                    with self.assertRaises(CollectionFailure) as error:DockerBackend({}).recover(entry,d)
                self.assertEqual(error.exception.code,expected)
                self.assertTrue((raw/'traffic_capture.stderr').exists())

    def test_storage_failure_preserves_existing_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'evidence';p.write_bytes(b'keep')
            with patch('experiments.scientific_safety.shutil.disk_usage',return_value=SimpleNamespace(free=1)):
                with self.assertRaises(ContractError):require_storage(p.parent)
            self.assertEqual(p.read_bytes(),b'keep')

    def test_launcher_pins_and_rejects_conflicting_selection(self):
        with patch.dict('os.environ',{},clear=True):
            env=c135.environment();self.assertEqual(env['SCIENTIFIC_SPEC_SHA256'],c135.SHA256)
            self.assertEqual(env['SCIENTIFIC_SPEC_PATH'],str(c135.PATH))
        with patch.dict('os.environ',{'SCIENTIFIC_SPEC_SHA256':'wrong'}):
            with self.assertRaises(ValueError):c135.environment()
        with patch.object(c135,'SHA256','wrong'):
            with self.assertRaises(ValueError):c135.environment()

    def test_launcher_forwards_arguments_and_environment(self):
        import sys
        with patch.dict('os.environ',{},clear=True), \
             patch.object(sys,'argv',['c135','--plan','example','--plan-sha256','hash','status']), \
             patch('experiments.c135.subprocess.call',return_value=2) as call:
            self.assertEqual(c135.main(),2)
            args=call.call_args
            self.assertEqual(args.kwargs['env']['SCIENTIFIC_SPEC_SHA256'],c135.SHA256)
            self.assertEqual(args.args[0][-5:],['--plan','example','--plan-sha256','hash','status'])

    def test_collection_entrypoint_blocks_before_reading_attempt(self):
        import sys
        from experiments import scientific_collection
        from analysis.detection.scientific import protocol
        spec=json.loads(c135.PATH.read_text())['specification']
        argv=['collection','--config','absent','--output','absent-raw',
              '--dataset-output','absent-dataset','--attempt','absent-attempt']
        with patch.object(sys,'argv',argv),patch.object(protocol,'SPEC',spec), \
             patch('experiments.scientific_collection.read_json') as read:
            with self.assertRaises(ContractError):scientific_collection.main()
            read.assert_not_called()

    def test_release_remains_closed(self):
        spec=json.loads(c135.PATH.read_text())['specification']
        self.assertFalse(spec['execution_release']['allowed'])
        with self.assertRaises(ContractError):require_release(spec)
        with patch('subprocess.Popen') as spawn:
            with self.assertRaises(ContractError):DockerBackend({}).collect({},Path('/tmp'),480)
            spawn.assert_not_called()
