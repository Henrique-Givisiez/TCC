"""Causal journal observer. No Docker dependency or scientific threshold fitting."""
import json
import threading
import time
from pathlib import Path
from simulator.source_aggregate import records

DIRECT_POLICY = 'scientific-direct-v1'

def requires_stop(reason, policy=None):
    """HTTP degradation remains observable; acquisition/observer failures stop."""
    return bool(reason) and (policy != DIRECT_POLICY or reason not in ('service_compromise','generator_queue'))

class SampleFreshness:
    """A cache read or repeated Docker sample cannot refresh acquisition age."""
    def __init__(self): self.fresh={}; self.reads={}; self.lock=threading.Lock()
    def update(self,cid,stats,now):
        stamp=stats.get('read')
        with self.lock:
            if stamp and stamp>self.reads.get(cid,''):
                self.reads[cid]=stamp; self.fresh[cid]=now
    def snapshot(self):
        with self.lock: return dict(self.fresh),dict(self.reads)

class Observer:
    def __init__(self):
        self.high_since = None
        self.last_now = -1

    def evaluate(self, items, now, last_collection):
        if last_collection > now: raise ValueError('future collection sample')
        if now < self.last_now:
            raise ValueError('observer clock regressed')
        self.last_now = now
        begins, finishes = {}, {}
        admitted = abandoned = attack_starts = 0
        for item in items:
            p = item['payload']; kind = item['kind']
            t = p.get('end_elapsed_seconds') if kind == 'request_finish' else p.get('elapsed_seconds')
            if t is not None and float(t) > now:
                continue  # never let a future finish mature a cohort
            if kind == 'request_begin':
                begins[p['request_id']] = p
                attack_starts += p['generator'] == 'attack'
            elif kind == 'request_finish':
                finishes[p['request_id']] = p
            elif kind == 'admission': admitted += 1
            elif kind == 'abandoned_admission': abandoned += 1
        cohort = [p for p in begins.values() if p['generator']=='normal' and now-13 <= float(p['elapsed_seconds']) < now-3]
        good = sum(p['request_id'] in finishes and finishes[p['request_id']].get('http_status') is not None
                   and 200 <= int(finishes[p['request_id']]['http_status']) < 300
                   and float(finishes[p['request_id']]['end_elapsed_seconds']) <= float(p['elapsed_seconds'])+3 for p in cohort)
        queue = admitted-abandoned-attack_starts
        if queue < 0: raise ValueError('negative admitted queue')
        if queue > 128:
            if self.high_since is None: self.high_since = now
        else: self.high_since = None
        reason = None
        if now-last_collection > 5: reason = 'collection_stale'
        elif self.high_since is not None and now-self.high_since >= 10: reason = 'generator_queue'
        elif len(cohort)>=50 and (len(cohort)-good)/len(cohort)>=.20: reason = 'service_compromise'
        return dict(observed_seconds=now, cohort_interval=[now-13,now-3], maturity_seconds=3,
                    cohort_n=len(cohort), unsuccessful_within_3s=len(cohort)-good,
                    offensive_queue=queue, last_collection_seconds=last_collection, reason=reason)

class Watcher:
    def __init__(self, manager, gt, collector):
        self.manager,self.gt,self.collector=manager,gt,collector
        self.done=threading.Event(); self.engine=Observer(); self.failure=None
        self.path=manager.directory/'stress_observer.jsonl'
        self.thread=threading.Thread(target=self.run,daemon=True)
    def start(self): self.thread.start()
    def close(self):
        self.done.set(); self.thread.join(timeout=5)
        if self.thread.is_alive(): raise RuntimeError('observer did not close')
    def run(self):
        while not self.done.is_set():
            try:
                items=records(self.manager.directory,self.manager.entries,strict=False)
                fresh,reads=self.collector.samples.snapshot() if hasattr(self.collector,'samples') else (dict(self.collector.fresh),{})
                stamps=list(fresh.values())
                now=self.gt.clock.elapsed()
                last=min(stamps)-self.gt.clock.monotonic_initial if len(stamps)==len(self.collector._container_ids) and stamps else 0
                result=self.engine.evaluate(items,now,last)
                result['collection_samples']={cid:dict(read=reads.get(cid),received_seconds=t-self.gt.clock.monotonic_initial) for cid,t in fresh.items()}
                result['actionable']=now<270 and not any(x['kind']=='emission_closed' for x in items)
                result['decision_available_seconds']=self.gt.clock.elapsed()
                result['policy']=getattr(self.manager,'observer_policy',None)
                result['run_id']=self.gt.run_id
                result['journal_sequences']={e['source_id']:max([x['sequence'] for x in items if x['source_id']==e['source_id']] or [0]) for e in self.manager.entries}
                with self.path.open('a') as f: f.write(json.dumps(result)+'\n')
                if requires_stop(result['reason'],result['policy']) and result['actionable']: self.manager.stop_attack(result)
            except Exception as exc:
                self.failure=repr(exc)
                self.manager.stop_attack(dict(reason='observer_failure',observed_seconds=self.gt.clock.elapsed(),error=self.failure))
                return
            self.done.wait(.25)
