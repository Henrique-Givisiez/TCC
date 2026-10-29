import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from experiments.stress_observer import Observer
from experiments.stress_runtime import StressManager
from experiments import stress_pilot as pilot, stress_processing as proc
from experiments.stress_review import assess_raw
from tests.test_development_d3_origins import origins_fixture
from tests.test_development_d3 import csvwrite,put
from simulator.source_aggregate import records
from simulator.request_logger import REQUEST_FIELDS
from simulator.ground_truth import EVENT_FIELDS

def item(kind,p): return dict(kind=kind,payload=p)
class Tests(unittest.TestCase):
 def test_maturity_future_and_threshold(self):
  rows=[]
  for i in range(50):
   rows.append(item('request_begin',dict(request_id=str(i),generator='normal',elapsed_seconds=10+i/100)))
  # All future successful finishes must remain invisible, even if supplied.
  for i in range(50):rows.append(item('request_finish',dict(request_id=str(i),http_status=200,end_elapsed_seconds=30)))
  self.assertIsNone(Observer().evaluate(rows,12,12)['reason'])
  self.assertEqual(Observer().evaluate(rows,14,14)['reason'],'service_compromise')
  for r in rows[50:90]:r['payload']['end_elapsed_seconds']=11
  self.assertEqual(Observer().evaluate(rows,14,14)['unsuccessful_within_3s'],10)
  rows[90]['payload']['end_elapsed_seconds']=11
  self.assertIsNone(Observer().evaluate(rows,14,14)['reason'])
 def test_queue_and_collection(self):
  rows=[item('admission',dict(elapsed_seconds=0)) for _ in range(129)]
  o=Observer();self.assertIsNone(o.evaluate(rows,1,1)['reason'])
  self.assertIsNone(o.evaluate(rows,10.99,10.99)['reason'])
  self.assertEqual(o.evaluate(rows,11,11)['reason'],'generator_queue')
  self.assertIsNone(Observer().evaluate([],5,0)['reason'])
  self.assertEqual(Observer().evaluate([],5.01,0)['reason'],'collection_stale')
 def test_cpu_freshness_is_sample_based(self):
  from experiments.stress_observer import SampleFreshness
  s=SampleFreshness()
  s.update('v',dict(read='2026-10-29T10:00:00Z',cpu=100),1)
  s.update('v',dict(read='2026-10-29T10:00:00Z',cpu=110),7)
  self.assertEqual(s.fresh['v'],1)
  s.update('v',dict(read='2026-10-29T10:00:01Z',cpu=110),8)
  self.assertEqual(s.fresh['v'],8)
  s.update('v',dict(read='2026-10-29T09:59:00Z',cpu=200),9)
  self.assertEqual(s.fresh['v'],8)
 def test_control_only_attack_and_idempotence(self):
  with tempfile.TemporaryDirectory() as t:
   m=StressManager.__new__(StressManager);m.directory=Path(t);m.stop_record=None
   m.gt=SimpleNamespace(run_id='r',clock=SimpleNamespace(elapsed=lambda:170))
   m.entries=[dict(source_id='normal_1',source_type='normal'),dict(source_id='attack_1',source_type='attack')]
   m.bindings={x['source_id']:dict(run_id='r') for x in m.entries};m.command=Mock()
   m.stop_attack(dict(reason='service_compromise',observed_seconds=169.9));m.stop_attack(dict(reason='collection_stale',observed_seconds=171))
   self.assertEqual(m.command.call_count,1);self.assertEqual(m.command.call_args.args[0],'attack_1')
   self.assertEqual(json.loads((Path(t)/'stress_stop.json').read_text())['reason'],'service_compromise')
 def test_live_journal_partial_line(self):
  from simulator.source_journal import Journal
  with tempfile.TemporaryDirectory() as t:
   d=Path(t)/'normal_1/output';d.mkdir(parents=True)
   j=Journal(d/'journal.jsonl','normal_1','r');j('request_begin',dict(elapsed_seconds=1))
   e=[dict(source_id='normal_1',run_id='r')]
   self.assertEqual(len(records(t,e,strict=False)),1)
   with (d/'journal.jsonl').open('a') as f:f.write('{')
   self.assertEqual(len(records(t,e,strict=False)),1)
   with self.assertRaises(ValueError):records(t,e)
 def test_queued_start_and_response_drain_after_stop(self):
  from simulator.source_journal import JournalGroundTruth,Journal
  from simulator.request_logger import RequestLogger
  class Clock:
   epoch_initial=1000;monotonic_initial=500;t=150
   def elapsed(self):return self.t
   def sample(self):return (1000+self.t,self.t)
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);clock=Clock();j=Journal(root/'journal.jsonl','attack_1','r')
   gt=JournalGroundTruth('test',root/'events.csv',clock=clock,run_id='r',journal=j)
   gt.plan_event('attack_001','event_001','continuous',150,270);gt.activate('event_001')
   log=RequestLogger(gt,root/'requests.csv',source_id='attack_1',journal=j)
   gt.admit('event_001');gt.admit('event_001')
   first=log.begin('attack',0,'http://edos_service:80/expensive','event_001')
   clock.t=170;gt.stop('event_001','stress_service_compromise')
   self.assertIsNone(gt.event('event_001')['actual_end_seconds'])
   clock.t=170.1;second=log.begin('attack',0,'http://edos_service:80/expensive','event_001')
   clock.t=170.2;gt.stop('event_001','stress_service_compromise')
   emission=gt.event('event_001')['actual_end_seconds']
   self.assertIsNotNone(emission)
   self.assertFalse(gt.admit('event_001'))
   clock.t=171
   response=SimpleNamespace(status_code=200)
   log.finish(first,response=response);log.finish(second,response=response)
   self.assertTrue(log.finalize());gt.finalize('stress_service_compromise',complete=True)
   self.assertEqual(gt.event('event_001')['actual_end_seconds'],emission)
   self.assertEqual(gt.event('event_001')['drained_end_seconds'],171)
   self.assertLess(emission,171)
 def test_resource_gate_before_release(self):
  with tempfile.TemporaryDirectory() as t:
   m=StressManager.__new__(StressManager);m.directory=Path(t);m.client=Mock()
   m.collector=SimpleNamespace(_container_ids=['v']);m.expected_resources=dict(affinity=[0,1],limits=dict(zip(('cpu.max','cpuset.cpus.effective','memory.max','pids.max'),('max 100000','0-1','max','max'))),host_cgroup_ancestors=[dict(limits={'cpu.max':'max 100000'})])
   from copy import deepcopy
   bad=deepcopy(m.expected_resources);bad['limits']['cpu.max']='100000 100000'
   with patch('experiments.stress_runtime.resources',return_value=bad),patch('simulator.source_manager.SourceManager.release') as release:
    with self.assertRaises(RuntimeError):m.release(SimpleNamespace())
    release.assert_not_called()
   with patch('experiments.stress_runtime.resources',return_value=m.expected_resources),patch('simulator.source_manager.SourceManager.release') as release,patch('experiments.stress_runtime.Watcher'):
    m.release(SimpleNamespace());release.assert_called_once()
 def test_watcher_reads_live_and_preserves_cohort_support(self):
  from experiments.stress_observer import Watcher
  import time
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);d=root/'normal_1/output';d.mkdir(parents=True)
   (d/'journal.jsonl').write_text('')
   manager=SimpleNamespace(directory=root,entries=[dict(source_id='normal_1',run_id='r')],stop_attack=Mock())
   gt=SimpleNamespace(run_id='r',clock=SimpleNamespace(elapsed=lambda:1,monotonic_initial=500))
   collector=SimpleNamespace(fresh={'victim':501},_container_ids=['victim'])
   w=Watcher(manager,gt,collector);w.start()
   deadline=time.monotonic()+2
   while not w.path.exists() and time.monotonic()<deadline:time.sleep(.01)
   w.close();self.assertIsNone(w.failure)
   self.assertEqual(json.loads(w.path.read_text().splitlines()[0])['cohort_n'],0)
   manager.stop_attack.assert_not_called()
 def test_early_closure_review_and_invalid_certificate(self):
  with tempfile.TemporaryDirectory() as t:
   raw=Path(t)/'raw';entry=pilot.base.read(pilot.DEFAULT_MANIFEST)['entries'][0]
   cfg=origins_fixture(raw,entry)
   # Compress only offensive timing to a certified stop at 210; retain nominal270.
   out=raw/'source_artifacts/attack_1/output'
   items=[json.loads(x) for x in (out/'journal.jsonl').read_text().splitlines()]
   def scale(p):
    for k in ('elapsed_seconds','end_elapsed_seconds','actual_start_seconds','stop_requested_seconds','actual_end_seconds','last_request_start_seconds','drained_end_seconds'):
     if p.get(k) is not None:p[k]=150+(float(p[k])-150)/2
    if p.get('timestamp') is not None:p['timestamp']=1000+p['elapsed_seconds']
    if p.get('end_timestamp') is not None:p['end_timestamp']=1000+p['end_elapsed_seconds']
    if p.get('duration_ms') is not None:p['duration_ms']=(p['end_elapsed_seconds']-p['elapsed_seconds'])*1000
   for x in items:scale(x['payload'])
   event=next(x['payload'] for x in items if x['kind']=='event_snapshot')
   event['end_reason']='stress_service_compromise'
   next(x['payload'] for x in items if x['kind']=='emission_closed').update(end_reason='stress_service_compromise',status='emission_ended',drained_end_seconds=None)
   (out/'journal.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in items))
   csvwrite(out/'local_events.csv',EVENT_FIELDS,[event]);csvwrite(raw/'attack_events.csv',EVENT_FIELDS,[event])
   local=pilot.base.old.csv_rows(out/'local_requests.csv')
   for row in local:
    for k in ('elapsed_seconds','end_elapsed_seconds','duration_ms','timestamp','end_timestamp'):row[k]=float(row[k])
    scale(row)
   csvwrite(out/'local_requests.csv',REQUEST_FIELDS,local)
   allrows=pilot.base.old.csv_rows(raw/'request_log.csv');lookup={x['request_id']:x for x in local}
   for r in allrows:
    if r['request_id'] in lookup:r.update(lookup[r['request_id']])
    active=event['actual_start_seconds']<=float(r['elapsed_seconds'])<event['actual_end_seconds']
    r.update(attack_active=int(active),active_event_ids='["event_001"]' if active else '[]')
   csvwrite(raw/'request_log.csv',REQUEST_FIELDS,allrows)
   final=pilot.base.read(out/'final_status.json');final['reason']='stress_service_compromise';put(out/'final_status.json',final)
   inventory=pilot.base.read(raw/'source_inventory.json')
   for e in inventory:
    if e['source_type']=='attack':e['status_final']['reason']='stress_service_compromise'
   put(raw/'source_inventory.json',inventory)
   run=event['run_id'];put(raw/'source_artifacts/stress_stop.json',dict(run_id=run,reason='service_compromise',observed_seconds=209.9,command_seconds=210))
   life,rows,requests=proc.reconcile(raw,cfg)
   self.assertTrue(life['controlled_closure'])
   m=StressManager.__new__(StressManager);m.directory=raw/'source_artifacts';m.entries=inventory
   m.stop_record=dict(reason='service_compromise',command_seconds=210)
   m.client=SimpleNamespace(containers=SimpleNamespace(get=lambda cid:SimpleNamespace(id=cid,status='exited' if cid=='attack_1' else 'running',attrs={'State':{'ExitCode':0}})))
   m.verify();self.assertEqual(len(m.entries),5)
   bad=dict(final,drained=False);put(out/'final_status.json',bad)
   with self.assertRaises(RuntimeError):m.verify()
   put(out/'final_status.json',final)
   gt=proc.validate_ground_truth(raw,cfg,rows,run)
   self.assertAlmostEqual(float(gt['actual_emission_intervals'][0][1]),210.005)
   journal=records(raw/'source_artifacts',pilot.base.read(raw/'source_inventory.json'))
   # Snapshot available at the decision, before emission closure/source closure.
   journal=[x for x in journal if x['kind'] not in ('source_closed','emission_closed','event_snapshot') and float(x['payload'].get('end_elapsed_seconds') or x['payload'].get('elapsed_seconds',0))<=209.9]
   tick=Observer().evaluate(journal,209.9,209.9)
   self.assertEqual(tick['reason'],'service_compromise')
   tick.update(run_id=run,actionable=True,collection_samples={'v':dict(read='2026-10-29T10:00:00Z',received_seconds=209.9)},journal_sequences={e['source_id']:max(x['sequence'] for x in journal if x['source_id']==e['source_id']) for e in pilot.base.read(raw/'source_inventory.json')})
   (raw/'source_artifacts/stress_observer.jsonl').write_text(json.dumps(tick)+'\n')
   report=assess_raw(raw,cfg,None,None)
   self.assertTrue(report['classification']['technical_integrity'],report['technical_checks'])
   self.assertFalse(report['service']['saturation_proven'])
   self.assertEqual(float(report['service']['actual_emission_end']),210.005)
   self.assertTrue(all(float(w['metrics']['bin_end_seconds'])<=210.005 for w in report['service']['active_windows']))
   # Full exported fixture, including actual event context and corrected RTTs.
   from experiments.export_dataset import export_run
   from experiments.validate_dataset import validate_dataset
   from simulator.request_logger import RTT_FIELDS
   csvwrite(raw/'rtt_log.csv',RTT_FIELDS,[dict(timestamp=r['end_timestamp'],rtt=r['duration_ms'],run_id=run,request_id=r['request_id'],traffic_class=r['traffic_class'],elapsed_seconds=r['end_elapsed_seconds']) for r in allrows if r['outcome']=='response'])
   metrics=pilot.base.old.csv_rows(raw/'simulation_metrics.csv')
   for r in metrics:
    active=event['actual_start_seconds']<=float(r['elapsed_seconds'])<event['actual_end_seconds']
    r.update(attack_active=int(active),active_event_ids='["event_001"]' if active else '[]')
   csvwrite(raw/'simulation_metrics.csv',list(metrics[0]),metrics)
   dataset=Path(t)/'dataset';export_run(raw,dataset)
   validation=validate_dataset(dataset)
   self.assertTrue(validation['dataset_valid'],validation['summary'])
   from copy import deepcopy
   plan=deepcopy(pilot.base.read(pilot.DEFAULT_MANIFEST));plan['runtime_source_hashes']={}
   e=plan['entries'][0];e['config']='config.json'
   e['outputs']=dict(raw='raw',dataset='dataset',analysis='analysis.json',review='review.json',validation='validation.json')
   plan['secondary_reference']['raw']='unused';put(Path(t)/'config.json',json.loads(cfg.to_json()))
   manifest=Path(t)/'manifest.json';put(manifest,plan)
   op=Path(t)/plan['results_root']/'operations'/e['id'];pf=op/'pf-0001/report.json'
   put(pf,dict(ready=True,preflight_id='pf-0001',manifest_sha256=pilot.base.sha(manifest),approved_entry=e['id'],checks=dict(operational_code_sha256={},containers_before=[])))
   put(op/'attempt.json',dict(authorization_scope=e['id'],manifest_sha256=pilot.base.sha(manifest),preflight_path=str(pf.relative_to(t)),preflight_sha256=pilot.base.sha(pf),preflight_id='pf-0001',approved_source_hashes={}))
   put(op/'execution_result.json',dict(returncode=0))
   put(op/'cleanup_observation.json',dict(containers=[],no_active_containers=True,no_scientific_processes=True,port_check_returncode=0,port_8080='State header\n',observed_epoch=1))
   with patch.object(pilot.base,'ROOT',Path(t)),patch.object(pilot.base.old,'ROOT',Path(t)),patch.object(pilot.base,'validate_plan',return_value={}),patch.object(pilot.base,'verify_reference',return_value={}),patch.object(pilot.base,'assess_raw',assess_raw):
    published=pilot.base.review_entry(manifest)
    self.assertTrue(published['classification']['technical_integrity'],published['technical_checks'])
    with self.assertRaises(FileExistsError):pilot.base.review_entry(manifest)
   items[-2]['payload']['run_id']='bad'
   (out/'journal.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in items))
   with self.assertRaises(ValueError):proc.validate_ground_truth(raw,cfg,rows,run)
if __name__=='__main__':unittest.main()
