import json,time,resource,sys
from pathlib import Path
from experiments.offensive_analysis import characterize
from tests.test_protected_compositions import configuration
N=8000;req=[];ev=[];journal=[]
for i in range(N):
 t=30+i*30/N;rid='r'+str(i);op='o'+str(i)
 req.append(dict(request_id=rid,run_id='run',generator='attack',traffic_class='attack',event_id='e',elapsed_seconds=t,end_elapsed_seconds=t+.02,duration_ms=20,http_status=200,outcome='response',error_type=None))
 for kind,at in [('handler_started',t+.001),('work_submitted',t+.002),('work_started',t+.003),('work_completed',t+.01),('handler_finished',t+.011)]:
  ev.append(dict(kind=kind,at=at,operation_id=op,sequence=len(ev)+1,traffic_class='attack',request_id=rid,run_id='run',event_id='e',work_started_at=t+.003,work_finished_at=t+.01,work_cpu_seconds=.007))
 for kind in ('admission','submitted','task_started','task_resolution','request_begin','request_finish','task_finished'):
  journal.append(dict(kind=kind,source_id='attack_1',payload=dict(admission_id='a'+str(i),request_id=rid,event_id='e',elapsed_seconds=t,decision='started')))
ev.append(dict(kind='computation_observation_closed',at=150,sequence=len(ev)+1,observation_complete=True))
c=json.loads(configuration('offensive').to_json())
rss_before=next(line for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('VmRSS:'))
t=time.perf_counter();s,series=characterize(c,req,journal,ev,[],[],0,True,dict(complete=True,observation_complete=True,written=len(ev)))
result=dict(requests=N,events=len(ev),journal_records=len(journal),seconds=time.perf_counter()-t,peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,starts=s['groups']['attack']['starts_in_window'],rows=len(series))
result['rss_before']=rss_before
result['rss_after']=next(line for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('VmRSS:'))
Path(sys.argv[1]).write_text(json.dumps(result,indent=2)+'\n');print(result)
