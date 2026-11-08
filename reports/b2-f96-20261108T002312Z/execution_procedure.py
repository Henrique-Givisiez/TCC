"""One-shot B2-F96, using the existing protected executor; never retries."""
import datetime,json,pathlib,subprocess,sys,platform,shutil
root=pathlib.Path.cwd()
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
run=root/'experiment_results'/('b2-f96-'+stamp);report=root/'reports'/run.name
run.mkdir();report.mkdir()
shutil.copy(__file__,report/'execution_procedure.py')
def command(args):
 p=subprocess.run(args,text=True,capture_output=True)
 return dict(args=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
audit={name:command(args) for name,args in {
 'branch':['git','branch','--show-current'],'head':['git','rev-parse','HEAD'],
 'working_tree':['git','status','--short'],'docker':['docker','version','--format','{{json .}}'],
 'docker_info':['docker','info','--format','{{json .}}'],'containers':['docker','ps','-a','--no-trunc','--format','{{json .}}'],
 'resources':['free','-b'],'disk':['df','-B1','.'],'tcpdump':['tcpdump','--version'],
 'packages':[sys.executable,'-m','pip','freeze']}.items()}
audit.update(python=sys.version,platform=platform.platform(),utc=stamp)
(report/'initial_environment.json').write_text(json.dumps(audit,indent=2))
template=root/'experiment_results/b2-f-20261108T000313Z/raw/effective_config.json'
reference=json.loads(template.read_text())
cfg=json.loads(template.read_text());cfg['id']='B2-F96-L2-F2-'+stamp;cfg['attack']['max_concurrent_sends']=96
assert reference['attack']['rate']==cfg['attack']['rate']==32
assert reference['attack']['max_concurrent_sends']==64
restored=json.loads(json.dumps(cfg));restored['id']=reference['id'];restored['attack']['max_concurrent_sends']=64
assert restored==reference,'Unexpected configuration change'

base=json.loads((root/'reports/b2-l-20261107T232559Z/summary.json').read_text())
for key in ('normal_traffic','server','monitoring','diagnostics','topology','autoscaler','infrastructure','load_balancer','traffic_sources'):
 assert cfg[key]==base['configuration'][key],key
assert cfg['duration_seconds']==150 and cfg['attack']['attackers']==2
images=dict(victim='sha256:03a186aa90eec03b874c82a887b245e7190fa45cd7256af3c077cb64943d52b0',source='sha256:b94212edd4d31c34998aea870caebc4ba145c1593d1b8dfdc27fe4917719fe3e')
assert images==base['certificate']['images']
prior=json.loads((root/'reports/b2-a-20261107T234426Z/summary.json').read_text())
assert images==prior['certificate']['images']
for key in ('normal_traffic','server','monitoring','diagnostics','topology','autoscaler','infrastructure','load_balancer','traffic_sources'):
 assert cfg[key]==prior['configuration'][key],key
assert cfg['attack']['mechanism']=='http_request_flooding' and cfg['attack']['endpoint']=='/medium'
assert cfg['attack']['rate']==32 and cfg['attack']['start_seconds']==30 and cfg['attack']['duration_seconds']==30

(run/'config.json').write_text(json.dumps(cfg,indent=2)+'\n')
shutil.copy(run/'config.json',report/'configuration.json')
shutil.copy('experiments/configs/protected_compositions/policy.json',run/'policy.json')
assert json.loads((run/'policy.json').read_text())==base['certificate']['limits']
inspection=command(['docker','image','inspect',*images.values()])
(report/'image_inspect.json').write_text(json.dumps(inspection,indent=2))
assert inspection['returncode']==0,'Images unavailable; stop before execution'
(report/'compatibility.json').write_text(json.dumps(dict(b2l_run_id=base['run_id'],images=images,unchanged_sections=['normal_traffic','server','monitoring','diagnostics','topology','autoscaler','infrastructure','load_balancer','traffic_sources'],policy_unchanged=True,template=str(template),changes={'id':cfg['id'],'attack.max_concurrent_sends':96}),indent=2))
args=[sys.executable,'-B','-m','experiments.diagnostic_run','--config',str(run/'config.json'),'--composition','combined','--operational-policy',str(run/'policy.json'),'--previous-run',str(root/'experiment_results/b2-f-20261108T000313Z/raw'),'--victim-image',images['victim'],'--source-image',images['source'],'--output',str(run/'raw'),'--dataset-output',str(run/'dataset')]
(report/'command.json').write_text(json.dumps(args,indent=2))
print(str(run),flush=True)
with (report/'execution.log').open('w') as log:p=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT)
(report/'execution_result.json').write_text(json.dumps(dict(returncode=p.returncode,run=str(run),report=str(report)),indent=2))
final={name:command(args) for name,args in {'containers':['docker','ps','-a','--no-trunc','--format','{{json .}}'],'networks':['docker','network','inspect','edos_sources','edos_network'],'resources':['free','-b'],'disk':['df','-B1','.']}.items()}
(report/'final_environment.json').write_text(json.dumps(final,indent=2))
print('returncode',p.returncode,flush=True)
sys.exit(p.returncode)
