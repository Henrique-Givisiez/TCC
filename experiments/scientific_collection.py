"""Lazy real collection backend. Importing this module never contacts Docker."""
from pathlib import Path
import json
import os
import signal
import subprocess
import time
from analysis.detection.inputs import ContractError,digest,read_json
from analysis.detection.artifacts import encoded


class CollectionFailure(RuntimeError):
    def __init__(self,code,message):super().__init__(message);self.code=code


def save(path,value):
    """Durable append-only JSON publication; an existing name is never replaced."""
    import tempfile
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.pending-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:f.write(encoded(value));f.flush();os.fsync(f.fileno())
        os.link(temp,path)
        directory_fd=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(directory_fd)
        finally:os.close(directory_fd)
    finally:os.unlink(temp)


class DockerBackend:
    def __init__(self,plan):self.plan=plan

    def preflight(self,entry,directory):
        import docker
        import socket,io,tarfile,hashlib,platform,importlib.metadata
        from simulator import config
        from analysis.detection.scientific.protocol import ROOT,runtime_hashes
        from experiments.development_d1_ops import process_rows
        if digest(self.plan['environment']['path'])!=self.plan['environment']['sha256']:raise ContractError('Frozen environment lock changed')
        lock=read_json(self.plan['environment']['path'])
        if set(lock)!={'daemon_id','kernel','python','images','packages'}:raise ContractError('Environment lock fields incomplete')
        import sys
        if lock['python']!=sys.version.split()[0]:raise ContractError('Python differs from frozen environment')
        if runtime_hashes()!=self.plan['runtime_hashes']:raise ContractError('Code changed before collection')
        for name,version in lock['packages'].items():
            if importlib.metadata.version(name)!=version:raise ContractError('Dependency changed: '+name)
        client=docker.DockerClient(base_url=config.DOCKER_ENGINE_SOCKET)
        report=dict(ready=False,started_epoch=time.time())
        try:
            info=client.info()
            if info['ID']!=lock['daemon_id'] or info['KernelVersion']!=lock['kernel']:raise ContractError('Docker environment differs from frozen lock')
            if client.containers.list() or process_rows():raise CollectionFailure('PREFLIGHT_FAILED','Competing containers/processes')
            image_names=(config.DOCKER_IMAGE_NAME,config.SOURCE_IMAGE,config.PROXY_IMAGE+'@'+config.PROXY_IMAGE_DIGEST)
            if set(lock['images'])!=set(image_names):raise ContractError('Image lock does not cover expected runtime images')
            for name in image_names:
                if client.images.get(name).id!=lock['images'][name]:raise ContractError('Frozen image changed: '+name)
            source_names=('__init__.py','experiment_config.py','service_destination.py','ground_truth.py','request_logger.py',
                'normal_traffic.py','traffic_injectorV0.py','normal_traffic_summary_logger.py','attack_summary_logger.py',
                'source_journal.py','source_runner.py','attack_patterns.py')
            bindings=[]
            for image,remote,mapping in ((config.SOURCE_IMAGE,'/app/simulator',{name:ROOT/'simulator'/name for name in source_names}),
                (config.DOCKER_IMAGE_NAME,'/app/simple_server.py',{'simple_server.py':ROOT/'simulator/app/simple_server.py'})):
                container=client.containers.create(image)
                try:
                    chunks,_=container.get_archive(remote)
                    with tarfile.open(fileobj=io.BytesIO(b''.join(chunks))) as archive:
                        found={Path(x.name).name:x for x in archive.getmembers() if x.isfile()}
                        for name,path in mapping.items():
                            actual=hashlib.sha256(archive.extractfile(found[name]).read()).hexdigest()
                            if actual!=digest(path):raise ContractError('Image code differs: '+name)
                            bindings.append(dict(image=image,path=name,sha256=actual))
                finally:container.remove()
            with socket.socket() as sock:sock.bind(('127.0.0.1',8080))
            with (directory/'capture.stderr').open('x') as stderr:
                capture=subprocess.Popen(['tcpdump','--immediate-mode','-i','lo','-p','-nn','-w',str(directory/'capture.pcap'),'tcp and port 1'],stdout=subprocess.DEVNULL,stderr=stderr)
                try:
                    time.sleep(1)
                    if capture.poll() is None:capture.send_signal(signal.SIGINT)
                    rc=capture.wait(timeout=5)
                finally:
                    if capture.poll() is None:capture.kill();capture.wait()
            diagnostic=(directory/'capture.stderr').read_text()
            if rc or 'listening on' not in diagnostic:raise CollectionFailure('PREFLIGHT_FAILED','Capture readiness failed')
            from experiments.stress_runtime import resources
            probe=client.containers.run(config.SOURCE_IMAGE,detach=True,entrypoint=['python','-c'],command=['import time;time.sleep(60)'],network_mode='none')
            try: report['effective_resource_probe']=resources(probe)
            finally:
                probe.stop(timeout=2);probe.remove()
            report.update(ready=True,image_sources=bindings,environment=self.plan['environment'],backend='docker',probe_traffic_generated=False)
            return report
        finally:
            report['finished_epoch']=time.time();save(directory/'preflight.json',report);client.close()

    def collect(self,entry,directory,timeout):
        """Only the future authorized CLI invokes this method."""
        from analysis.detection.scientific.protocol import ROOT
        command=[str(ROOT/'.venv/bin/python'),'-B','-m','experiments.scientific_collection','--config',entry['config'],
            '--output',str(directory/'raw'),'--dataset-output',str(directory/'dataset'),'--attempt',str(directory/'attempt.json')]
        started=time.time();rc=None
        with (directory/'execution.log').open('x') as stream:
            proc=subprocess.Popen(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            try:rc=proc.wait(timeout=timeout)
            except BaseException:
                if proc.poll() is None:
                    os.killpg(proc.pid,signal.SIGTERM)
                    try:proc.wait(timeout=35)
                    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                raise
            finally:save(directory/'execution.json',dict(command=command,returncode=rc,started_epoch=started,finished_epoch=time.time()))
        self.cleanup(directory)
        return self.recover(entry,directory)

    def cleanup(self,directory):
        import docker
        from simulator import config
        from experiments.development_d1_ops import process_rows
        client=docker.DockerClient(base_url=config.DOCKER_ENGINE_SOCKET)
        try:
            # Existing orchestrator owns normal cleanup. Leftovers stop progression;
            # this backend never deletes or stops unrelated containers.
            running=[dict(id=x.id,name=x.name) for x in client.containers.list()]
            processes=process_rows()
            report=dict(verified=not running and not processes,running=running,processes=processes,observed_epoch=time.time())
            save(directory/'cleanup.json',report)
            if not report['verified']:raise CollectionFailure('CLEANUP_UNCONFIRMED','Cleanup requires diagnosis')
        finally:client.close()

    def recover(self,entry,directory):
        """Read-only collection recovery plus resumable deterministic offline outputs.

        No process is launched and no Docker access occurs here.
        """
        required=[directory/'execution.json',directory/'cleanup.json']
        if any(not p.exists() for p in required):raise CollectionFailure('INDETERMINATE_ATTEMPT','Consumed attempt lacks execution/cleanup/data evidence; never repeat automatically')
        cleanup=read_json(directory/'cleanup.json');execution=read_json(directory/'execution.json')
        if not cleanup['verified']:raise CollectionFailure('CLEANUP_UNCONFIRMED','Unconfirmed cleanup is not a replacement authorization')
        status_path=directory/'raw/run_status.json'
        inventory_path=directory/'raw/source_inventory.json'
        if status_path.exists() and inventory_path.exists():
            status=read_json(status_path);inventory=read_json(inventory_path)
            sources=directory/'raw/source_artifacts'
            if (execution['returncode']!=0 and status.get('status')=='incomplete'
                and any('source monotonic clock is not demonstrably comparable' in e for e in status.get('errors',[]))
                and inventory and all(e.get('run_id') is None for e in inventory)
                and not any(sources.glob('*/control/command.json'))
                and not any(sources.glob('*/output/journal.jsonl'))):
                raise CollectionFailure('PRE_RELEASE_CLOCK_FAILURE','Clock guard rejected before source release; missing request CSV is not journal mismatch; preserve attempt and diagnose')
        if not (directory/'raw/run_status.json').exists() or not (directory/'dataset/dataset_manifest.json').exists():
            code='MISSING_REQUIRED_ARTIFACTS' if execution['returncode']==0 else 'INDETERMINATE_ATTEMPT'
            raise CollectionFailure(code,'Execution/cleanup recorded but required collected artifacts absent')
        from experiments import stress_processing as processing
        from experiments import development_d3 as legacy
        from simulator.experiment_config import ExperimentConfig
        from experiments.validate_dataset import validate_dataset
        from experiments.extract_features import extract_features
        raw=directory/'raw'
        if digest(entry['config'])!=entry['config_sha256']:raise ContractError('Configuration changed after preflight')
        try:
            cfg=ExperimentConfig.load(raw/'effective_config.json')
            if read_json(raw/'effective_config.json')!=read_json(entry['config']):raise ValueError('Effective config changed')
            life,rows,_=processing.reconcile(raw,cfg)
            processing.validate_ground_truth(raw,cfg,rows,life['run_id'])
        except (OSError,ValueError,KeyError) as exc:raise CollectionFailure('IDENTITY_JOURNAL_MISMATCH',str(exc)) from exc
        if not life['controlled_closure'] or execution['returncode']!=0:
            raise CollectionFailure('DRAIN_OR_EXECUTION_UNCONFIRMED','Preserved incomplete service/exit requires diagnosis, not automatic substitution')
        from experiments.stress_review import replay_observer
        try:
            observed=replay_observer(raw,life['run_id'])
            if observed['stop'] and observed['stop']['reason']=='collection_stale':raise ValueError('Observer acquisition stale')
        except (OSError,ValueError,KeyError) as exc:raise CollectionFailure('MONITOR_SUPPORT',str(exc)) from exc
        checks=legacy.collection_checks(raw,life['run_id'])
        if any(not x['passed'] for x in checks):
            code='CAPTURE_LOSS' if any(not x['passed'] and x['name'].startswith('capture_') for x in checks) else 'MONITOR_SUPPORT'
            raise CollectionFailure(code,str([x for x in checks if not x['passed']]))
        validation=validate_dataset(directory/'dataset')
        if not validation['dataset_valid'] or not validation['analysis_eligible']:raise CollectionFailure('DATASET_INVALID','Dataset failed objective structural/integrity eligibility')
        report_path=directory/'validation.json'
        if report_path.exists():
            if encoded(read_json(report_path))!=encoded(validation):raise ContractError('Validation replay differs')
        else:save(report_path,validation)
        feature_path=directory/'features'
        if not feature_path.exists():extract_features(directory/'dataset',report_path,feature_path,'1')
        from experiments.export_dataset import placement
        for p in raw.rglob('*'):
            if p.is_file():
                exported=directory/'dataset'/placement(p.relative_to(raw))[0]
                if not exported.exists() or digest(exported)!=digest(p):raise CollectionFailure('DATASET_INVALID','Raw/export mismatch: '+str(p))
        from analysis.detection.scientific.evaluation import impact
        operational=impact(raw)
        files={str(p.resolve()):digest(p) for folder in (raw,directory/'dataset',feature_path) for p in folder.rglob('*') if p.is_file()}
        return dict(entry_id=entry['id'],run_id=life['run_id'],features=str(feature_path.resolve()),dataset=str((directory/'dataset').resolve()),
            feature_manifest_sha256=digest(feature_path/'feature_manifest.json'),dataset_manifest_sha256=digest(directory/'dataset/dataset_manifest.json'),
            technical_valid=True,cleanup_verified=True,cleanup_epoch=cleanup['observed_epoch'],files=files,technical_checks=checks,
            backend='docker',original_attempt=str(directory.resolve()),operational=operational)


def main():
    """Consumed scientific attempt only; opt-in reuse of validated stress protection."""
    import argparse
    from analysis.detection.scientific import protocol
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--dataset-output',type=Path,required=True)
    parser.add_argument('--attempt',type=Path,required=True);args=parser.parse_args()
    claim=read_json(args.attempt);entry=claim['entry'];authority=claim['authority']
    plan=protocol.load_plan(authority['plan_path'],authority['plan_sha256'])
    directory=args.attempt.parent.resolve()
    if (entry not in plan['entries'] or args.config.resolve()!=Path(entry['config']).resolve()
        or args.output.resolve()!=directory/'raw' or args.dataset_output.resolve()!=directory/'dataset'
        or digest(claim['preflight_path'])!=claim['preflight_sha256']):raise ContractError('Scientific invocation differs from consumed attempt')
    save(directory/'runtime_invocation.json',dict(attempt_sha256=digest(args.attempt),started_epoch=time.time()))
    from experiments.stress_runtime import StressManager
    from experiments.stress_observer import SampleFreshness
    from simulator import source_experiment,stats_collector
    StressManager.expected_resources=read_json(claim['preflight_path'])['effective_resource_probe']
    original=stats_collector.StatsCollector
    class ProtectedCollector(original):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw);self.samples=SampleFreshness();self.fresh=self.samples.fresh;StressManager.collector=self
        def _on_acquisition(self,c,stats,received_monotonic):
            self.samples.update(c.id,stats,received_monotonic)
    source_experiment.SourceManager=StressManager;stats_collector.StatsCollector=ProtectedCollector
    from experiments.dataset_run import run_recorded
    from experiments.export_dataset import export_run
    from simulator.experiment_config import ExperimentConfig
    try:run_recorded(ExperimentConfig.load(args.config),args.output)
    finally:
        if (args.output/'run_status.json').exists():export_run(args.output,args.dataset_output)

if __name__=='__main__':main()
