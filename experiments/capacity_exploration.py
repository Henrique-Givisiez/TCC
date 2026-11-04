"""One benign run with an external safety observer; simulator code stays intact."""
import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from simulator.experiment_config import ExperimentConfig

GIB=1024**3
VICTIM_IMAGE='edos_target_app:diagnostics-20261104'
SOURCE_IMAGE='edos_sources:diagnostics-20261104'


def host_snapshot():
    fields=list(map(int,Path('/proc/stat').read_text().splitlines()[0].split()[1:]))
    memory={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines()}
    return dict(cpu_total=sum(fields[:8]),cpu_idle=fields[3]+fields[4],available_bytes=memory['MemAvailable'],
                loadavg=Path('/proc/loadavg').read_text().strip())


def safe_json(path):
    try:return json.loads(Path(path).read_text())
    except (FileNotFoundError,json.JSONDecodeError):return None


def tree_bytes(path):
    return sum(p.stat().st_size for p in Path(path).rglob('*') if p.is_file())


class Tail:
    """Bounded streaming tail; physical lines may arrive partially buffered."""
    def __init__(self,path):self.path=Path(path);self.offset=0;self.buffer=b''
    def lines(self):
        if not self.path.exists():return []
        if self.path.stat().st_size<self.offset:raise RuntimeError('observed file truncated')
        with self.path.open('rb') as stream:
            stream.seek(self.offset);chunk=stream.read(1024*1024);self.offset=stream.tell()
        pieces=(self.buffer+chunk).split(b'\n');self.buffer=pieces.pop()
        if len(self.buffer)>65536:raise RuntimeError('oversized incomplete observation')
        return [s.decode() for s in pieces if s]


class Guard:
    def __init__(self):self.host_busy_streak=0;self.pending_streak=defaultdict(int)
    def evaluate(self,snapshot):
        reasons=[]
        if snapshot['available_bytes']<2*GIB:reasons.append('host_available_memory_below_2GiB')
        if snapshot['disk_free_bytes']<4*GIB:reasons.append('disk_free_below_4GiB')
        self.host_busy_streak=self.host_busy_streak+1 if (snapshot.get('host_busy_percent') or 0)>85 else 0
        if self.host_busy_streak>=5:reasons.append('host_busy_budget_5_samples')
        for c in snapshot.get('containers',[]):
            limit=GIB if c['role']=='victim' else GIB//2
            if c['memory_usage_bytes']>limit:reasons.append('container_memory_budget:'+c['id'])
            if c.get('oom_killed') or c.get('restart_count',0):reasons.append('container_oom_or_restart:'+c['id'])
        for source,pending in snapshot.get('pending',{}).items():
            self.pending_streak[source]=self.pending_streak[source]+1 if pending>256 else 0
            if self.pending_streak[source]>=3:reasons.append('pending_budget_3_samples:'+source)
        if snapshot.get('completed_observed',0)>=50 and snapshot.get('failed_observed',0)/snapshot['completed_observed']>.10:
            reasons.append('observed_http_failure_fraction_above_10pct')
        if snapshot.get('diagnostic_errors'):reasons.append('diagnostic_loss_or_persistence_error')
        if snapshot.get('run_bytes',0)>512*1024**2 or snapshot.get('campaign_bytes',0)>GIB:reasons.append('artifact_storage_budget')
        return reasons


def preflight(client,campaign):
    before=host_snapshot();time.sleep(.5);host=host_snapshot();free=shutil.disk_usage(campaign).free
    dt=host['cpu_total']-before['cpu_total']
    host['busy_percent']=100*(1-(host['cpu_idle']-before['cpu_idle'])/dt) if dt>0 else None
    active=[dict(id=c.id,name=c.name) for c in client.containers.list()]
    networks={}
    for name in ('edos_sources','edos_network'):
        network=client.networks.get(name);network.reload();networks[name]=network.attrs.get('Containers',{})
    for image in (VICTIM_IMAGE,SOURCE_IMAGE):client.images.get(image)
    checks=dict(memory=host['available_bytes']>=4*GIB,disk=free>=4*GIB,
                host_cpu_budget=host['busy_percent'] is not None and host['busy_percent']<60,
                no_active_containers=not active,experimental_networks_empty=all(not n for n in networks.values()))
    return dict(ready=all(checks.values()),checks=checks,host=host,disk_free_bytes=free,active=active,networks=networks)


def validate_capacity_config(cfg):
    from simulator.experiment_config import NormalTrafficConfig,ServerConfig
    if (cfg.topology.mode!='direct' or cfg.attack.enabled or cfg.attack.attackers or cfg.autoscaler.enabled
        or cfg.infrastructure.initial_instances!=1 or cfg.normal_traffic.endpoint!='/medium'):
        raise ValueError('capacity observer permits only fixed direct benign /medium runs')
    if (cfg.normal_traffic.clients not in (2,4) or cfg.normal_traffic.clients*cfg.normal_traffic.rate>128
        or cfg.normal_traffic.max_concurrent_sends!=64 or cfg.server.process_pool_workers!=2
        or cfg.normal_traffic.request_timeout_seconds!=2 or cfg.duration_seconds>20
        or cfg.duration_seconds!=int(cfg.duration_seconds)):
        raise ValueError('configuration exceeds the preregistered exploratory envelope')
    if (cfg.normal_traffic.work_units!=NormalTrafficConfig().work_units
        or cfg.server.default_work_units!=ServerConfig().default_work_units):
        raise ValueError('historical work_units must remain unchanged')


def run(config_path,output):
    import docker
    from experiments.summarize_diagnostics import summarize
    from experiments.capacity_analysis import analyze
    from experiments.export_dataset import export_run
    config_path=Path(config_path).resolve();output=Path(output).resolve()
    cfg=ExperimentConfig.load(config_path)
    validate_capacity_config(cfg)
    output.mkdir(parents=True,exist_ok=False)
    client=docker.from_env(environment={'DOCKER_HOST':'unix:///var/run/docker.sock'},timeout=3)
    pf=preflight(client,output.parent)
    (output/'preflight.json').write_text(json.dumps(pf,indent=2)+'\n')
    if not pf['ready']:raise RuntimeError('preflight rejected; see preflight.json')
    shutil.copyfile(config_path,output/'config.json')
    command=[sys.executable,'-B','-m','experiments.diagnostic_run','--config',str(config_path),
        '--output',str(output/'raw'),'--dataset-output',str(output/'dataset'),
        '--victim-image',VICTIM_IMAGE,'--source-image',SOURCE_IMAGE]
    (output/'command.json').write_text(json.dumps(command,indent=2)+'\n')
    started=time.monotonic();guard=Guard();previous=host_snapshot();stop_reasons=[];stop_at=None
    tails={};headers={};counts={};completed=failed=0;container_audits={};last_size_check=0;sizes={}
    with (output/'execution.txt').open('x') as log,(output/'watchdog.jsonl').open('x') as watch:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        while process.poll() is None:
            try:
                now=time.monotonic();host=host_snapshot();dt=host['cpu_total']-previous['cpu_total']
                busy=100*(1-(host['cpu_idle']-previous['cpu_idle'])/dt) if dt>0 else None;previous=host
                inventory=safe_json(output/'raw/source_inventory.json') or []
                containers=[];pending={};origin=None;diagnostic_errors=[]
                for source in inventory:
                    sid=source['source_id'];base=output/'raw/source_artifacts'/sid
                    binding=safe_json(base/'control/command.json')
                    if binding:origin=binding['monotonic']
                    for kind,path in [('events',base/'output/diagnostics/events.jsonl'),('requests',base/'output/local_requests.csv')]:
                        tail=tails.setdefault((sid,kind),Tail(path))
                        for line in tail.lines():
                            if kind=='events':
                                e=json.loads(line)
                                if 'counts' in e:counts[sid]=e['counts']
                            elif sid not in headers:headers[sid]=line
                            else:
                                row=next(csv.DictReader(io.StringIO(headers[sid]+'\n'+line+'\n')))
                                if row.get('end_elapsed_seconds'):
                                    completed+=1;failed+=row['outcome'] in ('http_error','transport_error','client_error')
                    if sid in counts:
                        c=counts[sid];pending[sid]=c['submitted']-c['task_started']-c['cancelled']-c['rejected']
                    summary=safe_json(base/'output/diagnostics/events.summary.json')
                    if summary and not summary['complete']:diagnostic_errors.append(sid)
                backends=safe_json(output/'raw/direct_artifacts/backend_inventory.json') or []
                owned=[(s['container_id'],'source') for s in inventory]+[(v['id'],'victim') for v in backends]
                for cid,role in owned:
                    try:
                        c=client.containers.get(cid)
                        if cid not in container_audits:
                            h=c.attrs['HostConfig'];container_audits[cid]=dict(id=cid,name=c.name,role=role,image_id=c.attrs['Image'],
                                limits={k:h.get(k) for k in ('Memory','NanoCpus','CpuQuota','CpuPeriod','CpusetCpus','PidsLimit','Ulimits')})
                        state=c.attrs['State']
                        usage=client.api.stats(cid,stream=False,one_shot=True)['memory_stats'].get('usage',0) if c.status=='running' else 0
                        containers.append(dict(id=cid,role=role,memory_usage_bytes=usage,oom_killed=state.get('OOMKilled'),
                            restart_count=c.attrs.get('RestartCount',0),state=c.status))
                    except docker.errors.NotFound:continue  # normal cleanup, same owned ID never substituted
                    except docker.errors.APIError as exc:
                        if exc.status_code in (404,409):continue  # container exited between public API calls
                        raise
                victim_summary=safe_json(output/'raw/diagnostics/victim/events.summary.json')
                if victim_summary and not victim_summary['complete']:diagnostic_errors.append('victim')
                if now-last_size_check>=4:
                    sizes=dict(run_bytes=tree_bytes(output),campaign_bytes=tree_bytes(output.parent));last_size_check=now
                elapsed=now-origin if origin is not None else None
                snapshot=dict(utc=datetime.now(timezone.utc).isoformat(),monotonic=now,host_busy_percent=busy,
                    available_bytes=host['available_bytes'],loadavg=host['loadavg'],disk_free_bytes=shutil.disk_usage(output).free,
                    containers=containers,pending=pending,completed_observed=completed,failed_observed=failed,
                    diagnostic_errors=diagnostic_errors,elapsed=elapsed,
                    phase='preparation' if elapsed is None else 'generation' if elapsed<cfg.duration_seconds else 'drain_or_finalize',**sizes)
                reasons=guard.evaluate(snapshot)
                if now-started>cfg.duration_seconds+90:reasons.append('external_duration_budget')
                snapshot['safety_reasons']=reasons;watch.write(json.dumps(snapshot)+'\n');watch.flush()
                if reasons and stop_at is None:
                    stop_reasons=reasons;stop_at=now;process.send_signal(signal.SIGINT)
                if stop_at is not None and now-stop_at>45:
                    raise RuntimeError('cooperative shutdown deadline exceeded; progression blocked')
            except BaseException as exc:
                if process.poll() is None and stop_at is None:
                    stop_reasons=['observer_error:'+repr(exc)];stop_at=time.monotonic();process.send_signal(signal.SIGINT)
                elif isinstance(exc,KeyboardInterrupt):
                    raise
                elif stop_at is not None and time.monotonic()-stop_at>45:
                    (output/'observer_failure.json').write_text(json.dumps(dict(error=repr(exc),reasons=stop_reasons),indent=2)+'\n')
                    raise
            time.sleep(1)
        returncode=process.wait()
    (output/'container_audits.json').write_text(json.dumps(container_audits,indent=2)+'\n')
    result=dict(returncode=returncode,safety_interrupted=bool(stop_reasons),safety_reasons=stop_reasons,
                observer_elapsed_seconds=time.monotonic()-started,status='completed_normally' if returncode==0 and not stop_reasons else 'interrupted_or_invalid')
    (output/'execution_result.json').write_text(json.dumps(result,indent=2)+'\n')
    if (output/'raw/run_status.json').exists() and not (output/'dataset').exists():export_run(output/'raw',output/'dataset')
    if returncode!=0 or stop_reasons:raise RuntimeError('run did not finish normally; all produced evidence retained')
    diagnostic=summarize(output/'raw')
    (output/'diagnostic_summary.json').write_text(json.dumps(diagnostic,indent=2)+'\n')
    if diagnostic['reliability_errors']:raise RuntimeError('diagnostic reliability error')
    with (output/'verification.txt').open('x') as log:
        subprocess.run([sys.executable,'-B','-m','experiments.validate_topology_run','--raw',str(output/'raw'),
            '--dataset',str(output/'dataset'),'--output',str(output/'verification')],stdout=log,stderr=subprocess.STDOUT,check=True)
    capacity=analyze(output/'raw',diagnostic)
    (output/'capacity_summary.json').write_text(json.dumps(capacity,indent=2)+'\n')
    active=[c.id for c in client.containers.list()]
    cleanup=dict(active_containers=active,networks={})
    for name in ('edos_sources','edos_network'):
        n=client.networks.get(name);n.reload();cleanup['networks'][name]=n.attrs.get('Containers',{})
    (output/'cleanup.json').write_text(json.dumps(cleanup,indent=2)+'\n')
    if active or any(cleanup['networks'].values()):raise RuntimeError('cleanup not confirmed; next run blocked')
    return capacity


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();r=run(args.config,args.output)
    print(json.dumps(dict(name=r['name'],nominal=r['nominal_rps'],phases=r['phases'],http_ms=r['http_duration_ms'],
        cpu=r['cpu_docker_percent'],victim=r['victim'],progression=r['progression']),indent=2))


if __name__=='__main__':main()
