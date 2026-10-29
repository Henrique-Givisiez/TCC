"""Opt-in E12 runtime: preserve historical runtime files and image contents."""
import json
import time
import copy
from pathlib import Path
from simulator.source_manager import SourceManager
from experiments.stress_observer import Watcher, SampleFreshness

RESOURCE_SCRIPT = '''import json,os,pathlib
p=pathlib.Path('/sys/fs/cgroup')
r={'affinity':sorted(os.sched_getaffinity(0)), 'cgroup':pathlib.Path('/proc/self/cgroup').read_text(), 'limits':{}}
for name in ['cpu.max','cpuset.cpus.effective','memory.max','pids.max','cpu.stat']:
 f=p/name
 if f.exists():r['limits'][name]=f.read_text().strip()
print(json.dumps(r))'''

def resources(container):
    container.reload()
    result=container.exec_run(['python','-c',RESOURCE_SCRIPT])
    if result.exit_code: raise RuntimeError('effective resource inspection failed')
    value=json.loads(result.output)
    if not value['affinity'] or 'cpu.max' not in value['limits']: raise RuntimeError('effective cgroup v2 limits unavailable')
    pid=container.attrs['State']['Pid']
    membership=Path(f'/proc/{pid}/cgroup').read_text().strip().split('::',1)[1]
    current=Path('/sys/fs/cgroup')/membership.lstrip('/')
    ancestors=[]
    while current.is_relative_to('/sys/fs/cgroup'):
        limits={k:(current/k).read_text().strip() for k in ('cpu.max','cpuset.cpus.effective','memory.max','pids.max') if (current/k).exists()}
        ancestors.append(dict(path=str(current),limits=limits))
        if current==Path('/sys/fs/cgroup'): break
        current=current.parent
    if not any(x['limits'].get('cpu.max') for x in ancestors): raise RuntimeError('host quota ancestry unavailable')
    value['host_cgroup_ancestors']=ancestors
    value['container_id']=container.id
    value['host_config']={k:container.attrs['HostConfig'].get(k) for k in ['NanoCpus','CpuQuota','CpuPeriod','CpusetCpus','Memory','PidsLimit','CgroupParent']}
    return value

class StressManager(SourceManager):
    collector=None
    expected_resources=None
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw); self.stop_record=None; self.watcher=None
    def release(self,gt):
        from simulator import source_experiment
        evidence=[resources(self.client.containers.get(cid)) for cid in self.collector._container_ids]
        if self.expected_resources:
            for actual in evidence:
                if [x['limits'] for x in actual['host_cgroup_ancestors']] != [x['limits'] for x in self.expected_resources['host_cgroup_ancestors']] or actual['affinity']!=self.expected_resources['affinity'] or any(actual['limits'][k]!=self.expected_resources['limits'][k] for k in ('cpu.max','cpuset.cpus.effective','memory.max','pids.max')):
                    raise RuntimeError('actual victim limits differ from preflight; no source release')
        (self.directory/'effective_resources.json').write_text(json.dumps(evidence,indent=2)+'\n')
        self.gt=gt
        super().release(gt)
        self.watcher=Watcher(self,gt,self.collector); self.watcher.start()
    def stop_attack(self,record):
        if self.stop_record is not None: return
        self.stop_record=dict(record,run_id=self.gt.run_id,command_seconds=self.gt.clock.elapsed(),command_epoch=time.time())
        with (self.directory/'stress_stop.json').open('x') as f: json.dump(self.stop_record,f,indent=2)
        for entry in self.entries:
            if entry['source_type']=='attack':
                try:
                    self.command(entry['source_id'],dict(self.bindings[entry['source_id']],stop=True,reason='stress_'+record['reason']))
                except Exception:
                    # SIGTERM is handled by source_runner with the same controlled drain.
                    self.client.containers.get(entry['container_id']).kill(signal='SIGTERM')
                    raise
    def verify(self,setup=False):
        # Preserve all original identity/drain/exit checks; only the authorized
        # attack's earliest allowed closure changes. Never change nominal config.
        if not self.stop_record: return super().verify(setup)
        for entry in self.entries:
            if entry['source_type']!='attack': continue
            c=self.client.containers.get(entry['container_id'])
            if c.status=='running': continue
            output=self.directory/entry['source_id']/'output'
            final=json.loads((output/'final_status.json').read_text())
            items=__import__('simulator.source_aggregate',fromlist=['records']).records(self.directory,[entry])
            certificates=[x['payload'] for x in items if x['kind']=='emission_closed']
            if (c.id!=entry['container_id'] or c.attrs['State']['ExitCode']!=0 or not final['drained'] or not final['logger_complete']
                or final['run_id']!=entry['run_id'] or final['source_id']!=entry['source_id']
                or final['reason']!='stress_'+self.stop_record['reason'] or len(certificates)!=1
                or certificates[0]['stop_requested_seconds']<self.stop_record['command_seconds']
                or items[-1]['kind']!='source_closed' or not items[-1]['payload']['drained'] or not items[-1]['payload']['logger_complete']):
                raise RuntimeError('uncertified controlled attack stop')
        # Original verifier still covers every normal source.
        selected=copy.copy(self)
        selected.entries=[e for e in self.entries if e['source_type']!='attack' or self.client.containers.get(e['container_id']).status=='running']
        SourceManager.verify(selected,setup)
    def stop(self,reason):
        if self.watcher: self.watcher.close()
        result=super().stop(reason)
        if self.watcher and self.watcher.failure: return False
        return result

def main():
    from experiments import stress_pilot as pilot
    pilot.validate_plan(check_outputs=True)
    from experiments.development_d1_ops import read,sha
    plan=read(pilot.DEFAULT_MANIFEST)
    attempt=read(pilot.ROOT/plan['results_root']/'operations'/pilot.ENTRY_ID/'attempt.json')
    pf=pilot.ROOT/attempt['preflight_path']
    if attempt['manifest_sha256']!=sha(pilot.DEFAULT_MANIFEST) or sha(pf)!=attempt['preflight_sha256']:
        raise ValueError('runtime lacks bound consumed attempt/preflight')
    import sys
    if sys.argv[1:]!=attempt['command'][4:]: raise ValueError('runtime arguments differ from consumed attempt')
    marker=pilot.ROOT/plan['results_root']/'operations'/pilot.ENTRY_ID/'runtime_invocation.json'
    with marker.open('x') as stream: json.dump(dict(manifest_sha256=sha(pilot.DEFAULT_MANIFEST),invoked_epoch=time.time()),stream)
    StressManager.expected_resources=read(pf)['checks']['effective_resource_probe']
    from simulator import source_experiment, stats_collector
    original=stats_collector.StatsCollector
    class FreshCollector(original):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw); self.samples=SampleFreshness(); self.fresh=self.samples.fresh; StressManager.collector=self
        def _compute_metrics(self,c,stats):
            value=original._compute_metrics(c,stats)
            # Advancing Docker sample timestamp, not changed CPU value/cache read.
            if value: self.samples.update(c.id,stats,time.monotonic())
            return value
    source_experiment.SourceManager=StressManager
    stats_collector.StatsCollector=FreshCollector
    from experiments.dataset_run import main as run
    run()
if __name__=='__main__': main()
