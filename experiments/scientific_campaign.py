"""Checkpointed, partition-authorized campaign runner. No import-time Docker IO."""
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime,timezone
import argparse
import fcntl
import json
import time

from analysis.detection.inputs import ContractError,read_json,digest
from analysis.detection.artifacts import encoded,open_artifact
from analysis.detection.scientific import protocol as p
from analysis.detection.scientific import engine,evaluation
from analysis.detection.scientific.data import load_source,verify_receipt
from experiments.scientific_collection import DockerBackend,CollectionFailure,save


class Halt(RuntimeError):pass


class Campaign:
    def __init__(self,plan_path,plan_hash,backend=None):
        self.plan_path=Path(plan_path).resolve();self.plan_hash=plan_hash
        self.plan=p.load_plan(self.plan_path,plan_hash)
        self.handoff=p.validate_handoff(self.plan)
        self.root=Path(self.plan['results_root']).resolve();p.validate_destination(self.root)
        self.backend=backend if backend is not None else DockerBackend(self.plan)
        self.authority=dict(plan_path=str(self.plan_path),plan_sha256=plan_hash,
            protocol=self.plan['protocol'],environment=self.plan['environment'])

    @contextmanager
    def locked(self):
        if self.handoff:p.validate_handoff(self.plan)
        new=not self.root.exists();self.root.mkdir(parents=True,exist_ok=True)
        with (self.root/'runner.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc:raise Halt('Another campaign controller holds the lock') from exc
            try:
                binding=self.root/'binding.json'
                if binding.exists():
                    if read_json(binding)!=self.authority:raise ContractError('Result root belongs to another authority')
                else:
                    if any(x.name!='runner.lock' for x in self.root.iterdir()):raise ContractError('Nonempty unbound output root')
                    save(binding,self.authority)
                if self.handoff and not self.events():
                    self.append('HANDOFF_IMPORTED',artifact=self.plan['handoff'],consumed_attempts=1,substitution_approved=False)
                    self.append('TECHNICAL_FAILURE',entry=self.handoff['entry_id'],failure_path=self.handoff['failure_path'],failure_sha256=digest(self.handoff['failure_path']))
                yield
            finally:fcntl.flock(lock,fcntl.LOCK_UN)

    def events(self):
        result=[];previous=None
        paths=sorted((self.root/'journal').glob('*.json')) if (self.root/'journal').exists() else []
        for i,path in enumerate(paths,1):
            event=read_json(path)
            if event['sequence']!=i or event['previous_sha256']!=previous or event['plan_sha256']!=self.plan_hash:
                raise ContractError('Checkpoint journal chain differs')
            previous=digest(path);result.append((event,previous))
        return result

    def append(self,kind,**payload):
        events=self.events();event=dict(sequence=len(events)+1,previous_sha256=events[-1][1] if events else None,
            plan_sha256=self.plan_hash,kind=kind,payload=payload,utc=datetime.now(timezone.utc).isoformat())
        path=self.root/'journal'/f'{len(events)+1:06d}.json';save(path,event)
        return digest(path)

    def verify_graph(self,ref,seen):
        key=(ref['path'],ref['manifest_sha256'])
        if key in seen:return
        seen.add(key);doc=open_artifact(ref).read()
        def walk(value):
            if isinstance(value,dict):
                if 'path' in value and 'manifest_sha256' in value:
                    self.verify_graph(value,seen);return
                if 'observable_path' in value and 'feature_manifest_sha256' in value:
                    from analysis.detection.scientific.data import verify_reference
                    verify_reference(value)
                for key in ('failure','cleanup'):
                    if key+'_path' in value and key+'_sha256' in value and digest(value[key+'_path'])!=value[key+'_sha256']:
                        raise ContractError('Technical evidence changed')
                if 'intent_path' in value and digest(value['intent_path'])!=value['intent_sha256']:
                    raise ContractError('Consumed attempt changed')
                for child in value.values():walk(child)
            elif isinstance(value,list):
                for child in value:walk(child)
        if doc['kind']=='scientific-collection':verify_receipt(doc['receipt'])
        walk(doc)

    def checkpoints(self):
        result={}
        for event,h in self.events():
            if event['kind']=='PARTITION_COMPLETE':result[event['payload']['partition']]=event['payload']['artifact']
        seen=set()
        for part,ref in result.items():
            self.verify_graph(ref,seen)
            doc=open_artifact(ref,'scientific-checkpoint').read()
            if doc['authority']!=self.authority or doc['partition']!=part:raise ContractError('Checkpoint authority differs')
            for receipt in doc['receipts']:self.receipt_document(receipt,verify_files=False)
        return result

    def receipt_document(self,ref,verify_files=True):
        doc=open_artifact(ref,'scientific-collection').read()
        if doc['authority']!=self.authority:raise ContractError('Collection authority changed')
        entry=next((e for e in self.plan['entries'] if e['id']==doc['entry']['id']),None)
        if entry!=doc['entry']:raise ContractError('Collection entry differs from frozen slot')
        if verify_files:verify_receipt(doc['receipt'])
        return doc['receipt']

    def accepted(self):
        result={}
        for event,h in self.events():
            if event['kind']=='COLLECTION_ACCEPTED':
                entry=event['payload']['entry'];ref=event['payload']['artifact']
                if entry in result and result[entry]!=ref:raise ContractError('Two accepted attempts for a logical slot')
                self.receipt_document(ref,verify_files=False);result[entry]=ref
        return result

    def authorize_replacement(self,failure_hash):
        with self.locked():
            events=self.events();failure=None;approvals=[]
            for event,h in events:
                if event['kind']=='TECHNICAL_FAILURE' and event['payload']['failure_sha256']==failure_hash:failure=event['payload']
                if event['kind']=='REPLACEMENT_APPROVED':approvals.append(event['payload'])
            if failure is None:raise Halt('Select a recorded failure hash')
            path=Path(failure['failure_path']);doc=read_json(path)
            if digest(path)!=failure_hash or (doc['code'] not in p.TECHNICAL_CODES and not (self.handoff and self.handoff['failure_path']==str(path) and self.handoff['entry_id']==doc['entry_id'] and digest(path)==self.handoff['evidence_hashes'][str(path)])) or doc['attempt_number']!=1:
                raise Halt('Failure is not eligible for a technical replacement')
            if len(approvals)>=2 or any(x['entry']==doc['entry_id'] for x in approvals):raise Halt('Technical replacement budget exhausted or already approved')
            if doc['entry_id'] in self.accepted() or doc['entry_id'] in self.technical_attrition():raise Halt('Accepted logical slot cannot be replaced')
            self.append('REPLACEMENT_APPROVED',entry=doc['entry_id'],failure_sha256=failure_hash,
                same_partition_seed_scenario=True)

    def technical_attrition(self):
        result={}
        for event,h in self.events():
            if event['kind']=='TEST_TECHNICAL_ATTRITION':
                value=event['payload']
                if digest(value['failure_path'])!=value['failure_sha256']:raise ContractError('Attrition evidence changed')
                result[value['entry']]=value
        return result

    def record_attrition(self,failure_hash):
        """Explicit closure of a diagnosed failed TEST slot; never automatic."""
        with self.locked():
            failure=next((e['payload'] for e,h in self.events() if e['kind']=='TECHNICAL_FAILURE' and e['payload']['failure_sha256']==failure_hash),None)
            if failure is None:raise Halt('Select recorded technical failure')
            path=Path(failure['failure_path']);doc=read_json(path)
            entry=next(e for e in self.plan['entries'] if e['id']==doc['entry_id'])
            if doc['authority']!=self.authority:raise Halt('Failure authority differs')
            if entry['partition']!='TEST' or doc['code'] not in p.TECHNICAL_CODES or digest(path)!=failure_hash or entry['id'] in self.accepted():raise Halt('Only failed technical TEST slots can close as attrition')
            cleanup=path.parent/'cleanup.json'
            if not cleanup.exists() or not read_json(cleanup)['verified']:raise Halt('Cleanup must be confirmed before technical attrition')
            if entry['id'] in self.technical_attrition():raise Halt('Slot already closed')
            self.append('TEST_TECHNICAL_ATTRITION',entry=entry['id'],failure_path=str(path),failure_sha256=failure_hash,cleanup_path=str(cleanup),cleanup_sha256=digest(cleanup))

    def wait_idle(self):
        receipts=[self.receipt_document(ref,verify_files=False) for ref in self.accepted().values()]
        if receipts:
            remaining=60-(time.time()-max(x['cleanup_epoch'] for x in receipts))
            if remaining>61:raise Halt('Cleanup clock is ahead of host time; diagnose before continuation')
            if remaining>0:
                self.append('IDLE_WAIT',seconds=remaining)
                time.sleep(remaining)

    def collect_slot(self,entry):
        if self.handoff:p.validate_handoff(self.plan)
        accepted=self.accepted()
        for ref in accepted.values():
            op=self.receipt_document(ref,False).get('operational')
            if op and op.get('recovery_confirmed') is False:raise Halt('Service recovery unconfirmed; preserve valid run and diagnose before further collection')
        if entry['id'] in accepted:
            self.receipt_document(accepted[entry['id']]);return accepted[entry['id']]
        approvals=[e['payload'] for e,h in self.events() if e['kind']=='REPLACEMENT_APPROVED' and e['payload']['entry']==entry['id']]
        if approvals:
            original=Path(self.handoff['failure_path']) if self.handoff and entry['id']==self.handoff['entry_id'] else self.root/'collection'/entry['id']/'attempt-1/failure.json'
            if digest(original)!=approvals[0]['failure_sha256']:raise ContractError('Approved failure evidence changed')
        if self.handoff and entry['id']==self.handoff['entry_id'] and not approvals:raise Halt('Consumed predecessor slot requires explicit approval of its bound failure hash')
        attempt_number=2 if approvals else 1
        directory=self.root/'collection'/entry['id']/f'attempt-{attempt_number}'
        directory.mkdir(parents=True,exist_ok=True)
        receipt_path=directory/'receipt'
        failure_path=directory/'failure.json'
        if failure_path.exists():
            failure=read_json(failure_path)
            if not any(e['kind']=='TECHNICAL_FAILURE' and e['payload']['failure_sha256']==digest(failure_path) for e,h in self.events()):
                self.append('TECHNICAL_FAILURE',entry=entry['id'],failure_path=str(failure_path),failure_sha256=digest(failure_path))
            raise Halt('Attempt already failed; no automatic retry: '+str(failure_path))
        if receipt_path.exists():
            ref=dict(path=str(receipt_path),manifest_sha256=digest(receipt_path/'manifest.json'))
            self.receipt_document(ref)
            self.append('COLLECTION_ACCEPTED',entry=entry['id'],artifact=ref)
            return ref
        intent=directory/'attempt.json'
        try:
            if intent.exists():
                claim=read_json(intent)
                if claim['authority']!=self.authority or claim['entry']!=entry:raise ContractError('Consumed attempt identity changed')
                # Recovery never calls preflight/collect or creates another intent.
                receipt=self.backend.recover(entry,directory)
            else:
                if (self.handoff['original_consumed_attempts'] if self.handoff else 0)+sum(1 for x in (self.root/'collection').glob('*/attempt-*/attempt.json'))>=p.SPEC['replacements']['maximum_total_attempts']:raise Halt('Total attempt budget exhausted')
                self.wait_idle()
                preflights=sorted((directory/'preflights').glob('*/preparation.json')) if (directory/'preflights').exists() else []
                started=min([read_json(x)['started_epoch'] for x in preflights],default=time.time())
                if time.time()-started>600:raise Halt('Per-entry administrative allowance exhausted')
                pf=directory/'preflights'/f'pf-{len(preflights)+1:04d}';pf.mkdir(parents=True,exist_ok=False)
                save(pf/'preparation.json',dict(started_epoch=time.time(),authority=self.authority,entry_id=entry['id']))
                ready=self.backend.preflight(entry,pf)
                if not ready['ready']:raise Halt('Preflight not ready; no attempt consumed')
                # Recheck plan/code/config immediately before the irreversible claim.
                if digest(self.plan_path)!=self.plan_hash or self.plan['runtime_hashes']!=p.runtime_hashes() or digest(entry['config'])!=entry['config_sha256']:
                    raise ContractError('Authority changed during readiness')
                remaining=1080-(time.time()-started)
                if remaining<480:raise Halt('18-minute envelope lacks nominal/drain/idle reserve')
                save(intent,dict(authority=self.authority,entry=entry,attempt_number=attempt_number,
                    preflight_path=str(pf/'preflight.json'),preflight_sha256=digest(pf/'preflight.json'),
                    replacement_failure_sha256=approvals[0]['failure_sha256'] if approvals else None,started_epoch=time.time()))
                self.append('ATTEMPT_CONSUMED',entry=entry['id'],attempt_number=attempt_number,path=str(intent),sha256=digest(intent))
                receipt=self.backend.collect(entry,directory,min(480,remaining-60))
            if receipt['entry_id']!=entry['id']:raise ContractError('Backend returned a different entry')
            if receipt['run_id'] in {self.receipt_document(ref,False)['run_id'] for ref in accepted.values()}:
                raise ContractError('Collected run aliases another logical slot')
            verify_receipt(receipt)
            a=engine.artifact(receipt_path,'scientific-collection',dict(authority=self.authority,entry=entry,
                intent_path=str(intent),intent_sha256=digest(intent),receipt=receipt))
            self.append('COLLECTION_ACCEPTED',entry=entry['id'],artifact=a.reference)
            return a.reference
        except CollectionFailure as exc:
            if not intent.exists():raise Halt('Preflight failure; no attempt consumed: '+str(exc)) from exc
            failure=dict(entry_id=entry['id'],attempt_number=attempt_number,code=exc.code,message=str(exc),
                consumed_attempt_path=str(intent),consumed_attempt_sha256=digest(intent),authority=self.authority)
            save(failure_path,failure)
            self.append('TECHNICAL_FAILURE',entry=entry['id'],failure_path=str(failure_path),failure_sha256=digest(failure_path))
            raise Halt('Collection stopped: '+str(failure_path)) from exc

    def run_partition(self,partition,authorize_partition,checkpoint_hash=None):
        if p.SPEC.get('execution_release',{}).get('allowed') is False:
            raise Halt('Structural specification only; C1.3.2/C1.3.3 and integrated validation pending')
        if partition not in p.PARTITIONS or authorize_partition!=partition:raise Halt('Explicit authorization must name the selected partition')
        with self.locked():
            checkpoints=self.checkpoints();index=p.PARTITIONS.index(partition)
            if partition in checkpoints:return open_artifact(checkpoints[partition],'scientific-checkpoint')
            if set(checkpoints)!=set(p.PARTITIONS[:index]):raise Halt('Partition order/checkpoint gate not satisfied')
            if index and checkpoint_hash!=checkpoints[p.PARTITIONS[index-1]]['manifest_sha256']:
                raise Halt('Select immediate predecessor checkpoint hash')
            rejected=[e['payload'] for e,h in self.events() if e['kind']=='ANALYSIS_REJECTED' and e['payload']['partition']==partition]
            if rejected:
                open_artifact(rejected[-1]['artifact']).read()
                raise Halt('Partition already rejected under this frozen authority; no retuning or repeat')
            attrition=self.technical_attrition() if partition=='TEST' else {}
            entries=[e for e in self.plan['entries'] if e['partition']==partition and e['id'] not in attrition]
            refs=[self.collect_slot(entry) for entry in entries]
            receipts=[self.receipt_document(ref) for ref in refs]
            artifacts={};evals=[]
            for family,feature in p.FEATURES:
                feature_root=self.root/'analysis'/feature
                sources=[load_source(entry,receipt,family,feature,authority=self.authority,
                    test_release=checkpoints.get('CAL_B') if partition=='TEST' else None) for entry,receipt in zip(entries,receipts)]
                if partition=='BASELINE':
                    try:model=engine.fit(sources,feature_root/'baseline',self.authority)
                    except ContractError as exc:
                        rejection=engine.artifact(feature_root/'baseline-rejection','scientific-rejection',dict(authority=self.authority,reason=str(exc)))
                        self.append('ANALYSIS_REJECTED',partition=partition,artifact=rejection.reference)
                        raise Halt('BASELINE model rejected; no sample-size or normalization adjustment') from exc
                    artifacts[feature]=model.reference
                elif partition=='CAL_A':
                    model=open_artifact(open_artifact(checkpoints['BASELINE']).read()['artifacts'][feature])
                    calibration=engine.calibrate(sources,model,feature_root/'calibration',self.authority)
                    artifacts[feature]=calibration.reference
                    if not engine.pair_contract() and feature=='request_starts' and not calibration.read()['eligible']:
                        self.append('ANALYSIS_REJECTED',partition=partition,artifact=calibration.reference)
                        raise Halt('CAL-A has no eligible primary thresholds; TEST remains locked')
                else:
                    baseline=open_artifact(open_artifact(checkpoints['BASELINE']).read()['artifacts'][feature])
                    calibration=open_artifact(open_artifact(checkpoints['CAL_A']).read()['artifacts'][feature])
                    verification=None if partition=='CAL_B' else open_artifact(open_artifact(checkpoints['CAL_B']).read()['artifacts'][feature])
                    runs=[engine.process(source,baseline,calibration,feature_root/partition/entry['id'],self.authority,verification)
                          for source,entry in zip(sources,entries)]
                    if partition=='CAL_B':
                        v=engine.verify(sources,runs,calibration,feature_root/'verification',self.authority);artifacts[feature]=v.reference
                        if not engine.pair_contract() and feature=='request_starts' and not v.read()['approved']:
                            self.append('ANALYSIS_REJECTED',partition=partition,artifact=v.reference)
                            raise Halt('CAL-B primary verification rejected; no retuning, substitution or TEST')
                    else:
                        for entry,receipt,run in zip(entries,receipts,runs):
                            evals.append(evaluation.evaluate(entry,receipt,run,feature_root/'evaluation'/entry['id'],self.authority))
                        artifacts[feature]=[a.reference for a in runs]
            if partition=='TEST':artifacts['summary']=evaluation.aggregate(evals,self.root/'analysis/summary',self.authority,attrition).reference
            self.wait_idle()
            checkpoint=engine.artifact(self.root/'checkpoints'/partition,'scientific-checkpoint',dict(authority=self.authority,
                partition=partition,receipts=refs,artifacts=artifacts,previous_checkpoint=None if not index else checkpoints[p.PARTITIONS[index-1]],
                expected_slots=p.SPEC['counts'][partition],technical_attrition=attrition,test_order=p.SPEC['test_order'],scientific_execution_of_next_partition_authorized=False))
            self.append('PARTITION_COMPLETE',partition=partition,artifact=checkpoint.reference)
            return checkpoint


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--plan-sha256',required=True)
    sub=parser.add_subparsers(dest='action',required=True)
    sub.add_parser('validate');sub.add_parser('status')
    run=sub.add_parser('run');run.add_argument('--partition',choices=p.PARTITIONS,required=True)
    run.add_argument('--authorize-partition',required=True);run.add_argument('--checkpoint-sha256')
    replace=sub.add_parser('approve-technical-replacement');replace.add_argument('--failure-sha256',required=True)
    attr=sub.add_parser('record-test-attrition');attr.add_argument('--failure-sha256',required=True)
    args=parser.parse_args();campaign=Campaign(args.plan,args.plan_sha256)
    if args.action=='validate':out=dict(valid=True,logical_runs=sum(p.SPEC['counts'].values()),maximum_attempts=p.SPEC['replacements']['maximum_total_attempts'],docker_accessed=False)
    elif args.action=='status':out=dict(checkpoints=campaign.checkpoints(),events=len(campaign.events()),docker_accessed=False)
    elif args.action=='approve-technical-replacement':campaign.authorize_replacement(args.failure_sha256);out=dict(replacement_approved=True,experiment_executed=False)
    elif args.action=='record-test-attrition':campaign.record_attrition(args.failure_sha256);out=dict(attrition_recorded=True,experiment_executed=False)
    else:
        try:
            checkpoint=campaign.run_partition(args.partition,args.authorize_partition,args.checkpoint_sha256)
            out=dict(partition=args.partition,checkpoint=checkpoint.reference,next_partition_requires_approval=True)
        except (Halt,ContractError) as exc:parser.exit(2,str(exc)+'\n')
    print(json.dumps(out))


if __name__=='__main__':main()
