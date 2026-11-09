"""Energy-controlled adapter around C1.3.5; no automatic OS changes or retries."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import fcntl
import hashlib
import importlib.metadata
import json
import os
import signal
import subprocess
import sys
import time

from experiments import energy_control as host

ROOT=host.ROOT
PARENT=ROOT/'docs/scientific_protocol_direct_c135_o3_20261108.json'
PARENT_HASH='c97f8ece0198af720af4781409c12332508b45073cb62234a2c105864bf28018'
IDENTITY='energy-powersaver-20261109'
BUNDLE=ROOT/'experiments/protocols'/IDENTITY
RESULT=ROOT/'experiment_results'/('scientific-'+IDENTITY)
PILOTS=ROOT/'experiment_results'/('pilots-'+IDENTITY)


def select():
    if hashlib.sha256(PARENT.read_bytes()).hexdigest()!=PARENT_HASH:
        raise ValueError('Parent scientific contract changed')
    for key,value in [('SCIENTIFIC_SPEC_PATH',str(PARENT)),('SCIENTIFIC_SPEC_SHA256',PARENT_HASH)]:
        if key in os.environ and os.environ[key]!=value:raise ValueError('Conflicting scientific selector')
        os.environ[key]=value


def read(path):return json.loads(Path(path).read_text())
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    from experiments.scientific_collection import save as publish
    publish(path,value)


def event(root, kind, **fields):
    folder=Path(root)/'automation/events';folder.mkdir(parents=True,exist_ok=True)
    n=max((int(f.stem) for f in folder.glob('*.json')),default=0)+1
    save(folder/f'{n:06d}.json',dict(utc=datetime.now(timezone.utc).isoformat(),
                                  epoch=time.time(),kind=kind,**fields))


def stopped(root, session):
    return any(read(f)['epoch']>=session for f in (Path(root)/'automation/stop').glob('*.json'))


def checked(reference, directory, name, client=None, images=None):
    value=host.snapshot()
    # Publish observations even when validation rejects them.
    save(Path(directory)/(name+'.json'),value)
    host.validate(value,reference)
    if client is not None:host.container_observations(client,images)
    return value


def supervised(command, directory, reference, client, images, timeout, stop=lambda:False,
               authority_check=lambda:None, daemon_id=None):
    """Reuse existing child CLI and its cleanup; monitor only read-only APIs."""
    directory=Path(directory);started=time.time();proc=None;failure=None;last_valid=None
    authority_check()
    checked(reference,directory,'environment-before',client,images)
    save(directory/'controller-provenance.json',host.provenance())
    with (directory/'execution.log').open('x') as log, (directory/'environment.jsonl').open('x') as observations:
        try:
            proc=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            due=0
            while True:
                now=time.monotonic()
                if stop():raise InterruptedError('Operator requested stop')
                if now>=due:
                    authority_check()
                    if daemon_id is not None and client.info()['ID']!=daemon_id:
                        raise host.EnvironmentChanged('Docker daemon identity changed')
                    value=host.snapshot();value['containers']=host.container_observations(client,images)
                    observations.write(json.dumps(value)+'\n');observations.flush()
                    host.validate(value,reference);last_valid=value
                    due=now+5
                if proc.poll() is not None:break
                if time.time()-started>timeout:raise TimeoutError('Collection allowance exhausted')
                time.sleep(.25)
            checked(reference,directory,'environment-after',client,images)
            authority_check()
            if proc.returncode:raise RuntimeError('Collection process failed: '+str(proc.returncode))
        except BaseException as exc:
            failure=exc
            if proc is not None and proc.poll() is None:
                os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(timeout=35)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        finally:
            observations.flush();os.fsync(observations.fileno())
            save(directory/'execution.json',dict(command=command,returncode=None if proc is None else proc.returncode,
                 started_epoch=started,finished_epoch=time.time(),error=None if failure is None else repr(failure)))
            save(directory/'environment-complete.json',dict(valid=failure is None,last_valid=last_valid,
                 error=None if failure is None else repr(failure),reference_sha256=hashlib.sha256(json.dumps(reference,sort_keys=True).encode()).hexdigest(),
                 observation_sha256=digest(directory/'environment.jsonl')))
    if failure is not None:raise failure


def historical_seeds(exclude=()):
    from experiments.development_d1 import collect_seeds
    sources=[];used=set()
    for folder in ('experiments/configs','experiments/protocols','docs/stage14a/materialized','experiment_results','reports'):
        for f in sorted((ROOT/folder).rglob('*.json')):
            if f.resolve() in exclude or RESULT in f.resolve().parents:continue
            values=sorted(collect_seeds(read(f))) if f.stat().st_size else []
            if values:sources.append(dict(path=str(f.resolve()),sha256=digest(f),seeds=values));used.update(values)
    return sources,used


def prepare():
    """Prepare two B2-length pilots only; no Docker contact or profile changes."""
    if BUNDLE.exists():raise FileExistsError('Preparation already exists; inspect, never overwrite: '+str(BUNDLE))
    _,used=historical_seeds()
    configs={}
    for scenario,tag in [('A3','b2-a-20261107T234426Z'),('F96','b2-f96-20261108T002312Z')]:
        cfg=read(ROOT/'experiment_results'/tag/'raw/effective_config.json')
        n=0
        while True:
            seed=int.from_bytes(hashlib.sha256(f'{IDENTITY}:pilot:{scenario}:{n}'.encode()).digest()[:8],'big')
            if seed not in used:break
            n+=1
        used.add(seed);cfg.update(id=IDENTITY+'-pilot-'+scenario,seed=seed)
        path=BUNDLE/'pilots'/(scenario+'.json');save(path,cfg)
        configs[scenario]=dict(path=str(path),sha256=digest(path))
    spec=read(PARENT)['specification']
    policy=read(ROOT/spec['operational_policy']['resource_policy']['path'])
    save(BUNDLE/'pilot-policy.json',policy)
    save(BUNDLE/'preparation.json',dict(identity=IDENTITY,version=1,parent=dict(path=str(PARENT),sha256=PARENT_HASH),
        pilots=configs,pilot_policy_sha256=digest(BUNDLE/'pilot-policy.json'),results_root=str(RESULT),
        pilot_root=str(PILOTS),full_campaign_authorized=False,
        scientific_changes=False,provenance=host.provenance(),
        runtime_hashes=__import__('analysis.detection.scientific.protocol',fromlist=['runtime_hashes']).runtime_hashes()))
    return dict(prepared=True,pilots_executed=0,campaign_frozen=False)


def pilot(scenario):
    prep=read(BUNDLE/'preparation.json');ref=prep['pilots'][scenario]
    if digest(ref['path'])!=ref['sha256'] or digest(BUNDLE/'pilot-policy.json')!=prep['pilot_policy_sha256']:
        raise ValueError('Pilot freeze changed')
    from analysis.detection.scientific.protocol import runtime_hashes
    if runtime_hashes()!=prep['runtime_hashes']:raise ValueError('Prepared pilot code changed')
    if scenario=='F96' and not (PILOTS/'A3/accepted.json').exists():
        raise ValueError('A3 must be accepted and cleaned before F96')
    current=host.validate(host.snapshot()) # Refuse before consuming the sole pilot.
    baseline=PILOTS/'environment-reference.json'
    if baseline.exists():reference=read(baseline);host.validate(current,reference)
    else:reference=current
    import docker
    lock=read(ROOT/'experiments/protocols/c135_final_20261108/environment.json')
    client=docker.DockerClient(base_url='unix:///var/run/docker.sock',timeout=3)
    try:
        if client.containers.list():raise host.EnvironmentChanged('Active containers prevent pilot')
        if scenario=='F96':
            previous=read(PILOTS/'A3/execution.json')['finished_epoch']
            remaining=60-(time.time()-previous)
            if remaining>0:time.sleep(remaining)
            host.validate(host.snapshot(),reference)
        if not baseline.exists():save(baseline,reference)
        directory=PILOTS/scenario
        directory.mkdir(parents=True,exist_ok=False)
        save(directory/'pilot-intent.json',dict(scenario=scenario,config=ref,seed=read(ref['path'])['seed'],
             scope='one_B2_length_pilot_not_campaign_slot',maximum_attempts=1,utc=datetime.now(timezone.utc).isoformat()))
        command=[str(ROOT/'.venv/bin/python'),'-B','-m','experiments.diagnostic_run',
             '--config',ref['path'],'--output',str(directory/'raw'),'--dataset-output',str(directory/'dataset'),
             '--victim-image',lock['images']['victim'],'--source-image',lock['images']['source'],
             '--operational-policy',str(BUNDLE/'pilot-policy.json'),'--composition','combined']
        if scenario=='F96':command+=['--previous-run',str(PILOTS/'A3/raw')]
        frozen_code = prep['runtime_hashes']
        def unchanged():
            from analysis.detection.scientific.protocol import runtime_hashes
            if runtime_hashes()!=frozen_code or digest(ref['path'])!=ref['sha256']:
                raise host.EnvironmentChanged('Pilot code/configuration changed')
        supervised(command,directory,reference,client,lock['images'],240,
                   authority_check=unchanged,daemon_id=lock['daemon_id'])
        from experiments.validate_dataset import validate_dataset
        validity=validate_dataset(directory/'dataset');save(directory/'validation.json',validity)
        if not validity['dataset_valid'] or not validity['analysis_eligible']:raise RuntimeError('Pilot dataset rejected')
        certificate=read(directory/'raw/operational_policy.json')
        if certificate.get('certification')!='completed' or not certificate.get('cleanup_verified'):
            raise RuntimeError('Pilot operational certification rejected')
        save(directory/'accepted.json',dict(scenario=scenario,technical_valid=True,
             environment_sha256=digest(directory/'environment-complete.json'),dataset_sha256=digest(directory/'dataset/dataset_manifest.json'),
             interpretation='descriptive_only_researcher_decides_stress_adequacy'))
        return dict(pilot=scenario,accepted=True,directory=str(directory))
    finally:client.close()


def freeze():
    """Materialize a separate 80-slot plan only after both authorized pilots."""
    from analysis.detection.scientific import protocol as p
    from analysis.detection.scientific.direct_contract import draft_entries,configuration
    for scenario in ('A3','F96'):
        if not (PILOTS/scenario/'accepted.json').exists():raise ValueError('Both pilot receipts required before freeze')
    if not (ROOT/'reports'/IDENTITY/'manifest.json').exists():
        raise ValueError('Pilot characterization required before freeze')
    pilot_refs={}
    for scenario in ('A3','F96'):
        receipt=PILOTS/scenario/'accepted.json';value=read(receipt)
        proof=PILOTS/scenario/'environment-complete.json'
        if (not value.get('technical_valid') or not read(proof).get('valid')
            or value['environment_sha256']!=digest(proof)
            or value['dataset_sha256']!=digest(PILOTS/scenario/'dataset/dataset_manifest.json')):
            raise ValueError('Pilot receipt/environment/dataset changed')
        pilot_refs[scenario]=dict(path=str(receipt),sha256=digest(receipt))
    report=ROOT/'reports'/IDENTITY/'manifest.json'
    for ref in read(report)['files'].values():
        if digest(ref['path'])!=ref['sha256']:raise ValueError('Pilot characterization changed')
    reference=read(PILOTS/'environment-reference.json');host.validate(host.snapshot(),reference)
    path=BUNDLE/'plan.json'
    if path.exists():raise FileExistsError('Plan already frozen')
    # Dependency/environment locks retain the original closed schema.
    import docker
    client=docker.DockerClient(base_url='unix:///var/run/docker.sock',timeout=3)
    try:
        info=client.info();previous=read(ROOT/'experiments/protocols/c135_final_20261108/environment.json')
        for identity in previous['images'].values():
            if client.images.get(identity).id!=identity:raise ValueError('Image differs')
        environment=dict(daemon_id=info['ID'],kernel=info['KernelVersion'],python=sys.version.split()[0],images=previous['images'],
             packages={k:importlib.metadata.version(k) for k in previous['packages']})
    finally:client.close()
    save(BUNDLE/'environment.json',environment)
    _,used=historical_seeds()
    entries=draft_entries(p.SPEC,used,IDENTITY)
    for e in entries:
        e['id']='ps_'+e['id'];cfg=BUNDLE/'configs'/(e['id']+'.json')
        save(cfg,configuration(p.SPEC,e['scenario'],e['id'],e['seed']))
        e.update(config=str(cfg),config_sha256=digest(cfg))
    audit=BUNDLE/'seed_audit.json'
    sources,_=historical_seeds(exclude={Path(e['config']).resolve() for e in entries})
    save(audit,dict(sources=sources))
    plan=dict(protocol=dict(path=str(PARENT),sha256=PARENT_HASH),runtime_hashes=p.runtime_hashes(),
         environment=dict(path=str(BUNDLE/'environment.json'),sha256=digest(BUNDLE/'environment.json')),
         seed_audit=dict(path=str(audit),sha256=digest(audit)),entries=entries,results_root=str(RESULT))
    save(path,plan)
    save(BUNDLE/'control.json',dict(version=1,identity=IDENTITY,plan=dict(path=str(path),sha256=digest(path)),
         reference=reference,provenance=host.provenance(),full_campaign_authorized=False,
         pilot_receipts=pilot_refs,pilot_analysis=dict(path=str(report),sha256=digest(report)),
         automatic_replacements=False,monitor_seconds=5,
         limitation='Sampling cannot prove absence of changes between observations; no per-worker frequency measurement',
         calibration='unchanged C1.3.5 pair eligibility; per-pair rejection does not retune or change gates'))
    p.load_plan(path,digest(path))
    return dict(frozen=True,logical_slots=80,control_sha256=digest(BUNDLE/'control.json'),campaign_started=False)


def authorization(value):
    if value!=IDENTITY:raise PermissionError('Explicit --authorize-campaign '+IDENTITY+' required')


def load_control(expected):
    if digest(BUNDLE/'control.json')!=expected:raise ValueError('Control hash differs')
    c=read(BUNDLE/'control.json')
    if c['identity']!=IDENTITY or c['plan']['path']!=str(BUNDLE/'plan.json'):raise ValueError('Wrong campaign authority')
    references=list(c.get('pilot_receipts',{}).values())
    if 'pilot_analysis' in c:references.append(c['pilot_analysis'])
    for ref in references:
        if digest(ref['path'])!=ref['sha256']:raise ValueError('Pilot evidence changed after freeze')
    return c


def run(control_hash, authorize, resume=False, reason=None):
    authorization(authorize) # Must precede any campaign creation or Docker contact.
    c=load_control(control_hash)
    from experiments.scientific_campaign import Campaign
    from experiments.scientific_collection import DockerBackend
    import docker
    client=docker.DockerClient(base_url='unix:///var/run/docker.sock',timeout=3)
    session=time.time();reference=c['reference']
    class GuardedBackend(DockerBackend):
        def preflight(self,entry,directory):
            if stopped(RESULT,session):raise InterruptedError('Operator stop')
            checked(reference,directory,'environment-preflight')
            return super().preflight(entry,directory)
        def collect(self,entry,directory,timeout):
            event(RESULT,'RUNNING',entry=entry['id'],partition=entry['partition'])
            command=[str(ROOT/'.venv/bin/python'),'-B','-m','experiments.scientific_collection',
                '--config',entry['config'],'--output',str(directory/'raw'),
                '--dataset-output',str(directory/'dataset'),'--attempt',str(directory/'attempt.json')]
            def unchanged():
                from analysis.detection.scientific.protocol import runtime_hashes
                if (runtime_hashes()!=self.plan['runtime_hashes'] or digest(entry['config'])!=entry['config_sha256']
                    or digest(c['plan']['path'])!=c['plan']['sha256'] or digest(BUNDLE/'control.json')!=control_hash):
                    raise host.EnvironmentChanged('Frozen code/configuration/authority changed')
            lock=read(self.plan['environment']['path'])
            try:supervised(command,directory,reference,client,lock['images'],timeout,
                           lambda:stopped(RESULT,session),unchanged,lock['daemon_id'])
            finally:self.cleanup(directory)
            return self.recover(entry,directory)
        def recover(self,entry,directory):
            proof=directory/'environment-complete.json'
            if not proof.exists() or read(proof).get('valid') is not True:
                raise host.EnvironmentChanged('Consumed attempt has no valid environment seal; diagnosis required, never recollect')
            if read(proof)['observation_sha256']!=digest(directory/'environment.jsonl'):
                raise host.EnvironmentChanged('Environment evidence changed')
            if read(proof)['reference_sha256']!=hashlib.sha256(json.dumps(reference,sort_keys=True).encode()).hexdigest():
                raise host.EnvironmentChanged('Environment reference differs')
            receipt=super().recover(entry,directory)
            for name in ('environment-before.json','environment-after.json','environment.jsonl','environment-complete.json','controller-provenance.json'):
                f=directory/name;receipt['files'][str(f.resolve())]=digest(f)
            return receipt
    class ControlledCampaign(Campaign):
        def continue_after_failure(self,entry):
            raise RuntimeError('Progression stopped; explicit diagnosis required for '+entry['id'])
        def collect_slot(self,entry):
            if stopped(RESULT,session):raise InterruptedError('Operator stop')
            host.validate(host.snapshot(),reference)
            ref=super().collect_slot(entry)
            host.validate(host.snapshot(),reference)
            return ref
    campaign=ControlledCampaign(c['plan']['path'],c['plan']['sha256'],backend=GuardedBackend(read(c['plan']['path'])))
    try:
        host.validate(host.snapshot(),reference)
        with campaign.locked():pass
        with (RESULT/'automation.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            existing=list((RESULT/'automation/events').glob('*.json'))
            if existing and (not resume or not reason):raise ValueError('Existing invocation requires --resume --reason')
            event(RESULT,'RESUME' if resume else 'START',reason=reason,control_sha256=control_hash)
            for index,partition in enumerate(('BASELINE','CAL_A','CAL_B','TEST')):
                cps=campaign.checkpoints()
                if partition in cps:continue
                if stopped(RESULT,session):raise InterruptedError('Operator stop')
                event(RESULT,'TRANSITION',partition=partition,environment=host.validate(host.snapshot(),reference))
                previous=None if index==0 else cps[('BASELINE','CAL_A','CAL_B','TEST')[index-1]]['manifest_sha256']
                campaign.run_partition(partition,partition,previous)
                host.validate(host.snapshot(),reference)
                event(RESULT,'PARTITION_COMPLETE',partition=partition)
            event(RESULT,'COMPLETE',environment=host.validate(host.snapshot(),reference))
            return dict(complete=True,results=str(RESULT))
    except BaseException as exc:
        if RESULT.exists():event(RESULT,'INTERRUPTED' if isinstance(exc,(InterruptedError,KeyboardInterrupt,host.EnvironmentChanged)) else 'FAILED',error=repr(exc))
        raise
    finally:client.close()


def status():
    """Cheap read-only view; does not import Docker or rehash the whole dataset."""
    states={};part=None;accepted=set();failures=[];events=[]
    if (BUNDLE/'plan.json').exists():
        for e in read(BUNDLE/'plan.json')['entries']:states[e['id']]='PENDING'
    for f in sorted((RESULT/'automation/events').glob('*.json')):
        e=read(f);events.append(e)
        if e['kind']=='RUNNING':states[e['entry']]='RUNNING';part=e['partition']
        if e['kind']=='TRANSITION':part=e['partition']
        if e['kind'] in ('FAILED','INTERRUPTED'):failures.append(e)
    for f in sorted((RESULT/'journal').glob('*.json')):
        e=read(f)
        if e['kind']=='ATTEMPT_CONSUMED':states[e['payload']['entry']]='RUNNING'
        if e['kind']=='COLLECTION_ACCEPTED':states[e['payload']['entry']]='ACCEPTED';accepted.add(e['payload']['entry'])
        if e['kind']=='TECHNICAL_FAILURE':states[e['payload']['entry']]='REJECTED'
    if events and events[-1]['kind'] in ('FAILED','INTERRUPTED'):
        for k,v in states.items():
            if v=='RUNNING':states[k]=events[-1]['kind']
    from collections import Counter
    elapsed=None if not events else time.time()-events[0]['epoch']
    latest_environment=None
    latest_running=next((e for e in reversed(events) if e['kind']=='RUNNING'),None)
    if latest_running:
        f=RESULT/'collection'/latest_running['entry']/'attempt-1/environment.jsonl'
        if f.exists():
            with f.open('rb') as stream:
                stream.seek(max(0,f.stat().st_size-65536))
                rows=stream.read().splitlines(keepends=True)
            for row in reversed(rows):
                if not row.endswith(b'\n'):continue
                try:latest_environment=json.loads(row);break
                except ValueError:continue
    counts=Counter(states.values())
    return dict(identity=IDENTITY,frozen=(BUNDLE/'control.json').exists(),partition=part,states=states,
        counts={k:counts[k] for k in ('PENDING','RUNNING','ACCEPTED','REJECTED','FAILED','INTERRUPTED')},
        last_environment=latest_environment,elapsed_seconds=elapsed,
        estimated_remaining_seconds=None if not accepted else (80-len(accepted))*elapsed/len(accepted),
        last_error=failures[-1] if failures else None,last_event=events[-1] if events else None,
        authorization='explicit campaign ID and control SHA required; not granted by preparation')


def main():
    select()
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    for action in ('prepare','check','freeze','validate','status','stop','analyze-pilots'):sub.add_parser(action)
    pp=sub.add_parser('pilot');pp.add_argument('--scenario',choices=['A3','F96'],required=True)
    rr=sub.add_parser('run');rr.add_argument('--control-sha256',required=True);rr.add_argument('--authorize-campaign',required=True)
    rr.add_argument('--resume',action='store_true');rr.add_argument('--reason')
    args=parser.parse_args()
    if args.action in ('run','pilot'):
        def terminate(signum,frame):raise InterruptedError('Controller received signal '+str(signum))
        signal.signal(signal.SIGTERM,terminate)
    if args.action=='prepare':result=prepare()
    elif args.action=='check':result=dict(environment=host.validate(host.snapshot()),provenance=host.provenance())
    elif args.action=='pilot':result=pilot(args.scenario)
    elif args.action=='freeze':result=freeze()
    elif args.action=='analyze-pilots':
        from experiments.energy_pilot_analysis import analyze_pilots
        result=analyze_pilots()
    elif args.action=='status':result=status()
    elif args.action=='stop':
        if not (RESULT/'binding.json').exists():raise ValueError('No campaign to stop')
        save(RESULT/'automation/stop'/f'{time.time_ns()}.json',dict(epoch=time.time(),reason='operator'))
        result=dict(stop_requested=True)
    elif args.action=='validate':
        from analysis.detection.scientific import protocol as p
        p.load_plan(BUNDLE/'plan.json',digest(BUNDLE/'plan.json'))
        result=dict(valid=True,slots=80,campaign_started=False,control_sha256=digest(BUNDLE/'control.json'))
    else:result=run(args.control_sha256,args.authorize_campaign,args.resume,args.reason)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
