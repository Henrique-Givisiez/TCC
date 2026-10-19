"""Synthetic-only historical/current comparison. No TEST IO or evaluators."""
import ast
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT))
from analysis.detection import pipeline as current
from analysis.detection.artifacts import component, encoded, open_artifact, publish
from analysis.detection.contracts import Observation, ObservedSeries, PolicyScore
from analysis.detection.inputs import BoundSeries
from analysis.detection.detectors.zscore import ZScore,zscore_spec
from analysis.detection.detectors.cov import CoV,cov_spec
from analysis.detection.detectors.ewma import EWMA,ewma_spec
from analysis.detection.detectors.cusum import CUSUM,cusum_spec
from analysis.detection.empirical import StrictUpperTail,upper_tail_spec

CAL='6c5d9b6d26bc667bfb29e770bc39228d78982909'
EXT='63cba02cf1e11722a66df6f2643e78d88bfdc477'

def git(*args):return subprocess.check_output(['git',*args])
def hash_bytes(data):return hashlib.sha256(data).hexdigest()
def sha(p):return hash_bytes(Path(p).read_bytes())
def old_pipeline(commit):
    name='analysis.detection._review_pipeline_'+commit[:7]
    module=types.ModuleType(name);module.__package__='analysis.detection';sys.modules[name]=module
    module.__file__='<git:'+commit+':analysis/detection/pipeline.py>'
    exec(compile(git('show',commit+':analysis/detection/pipeline.py'),module.__file__,'exec'),module.__dict__)
    return module

historical={CAL:old_pipeline(CAL),EXT:old_pipeline(EXT)}
freeze_path=ROOT/'experiment_results/stage14-ewma-cusum-calibration-20261019/four_method_calibration_freeze_manifest.json'
freeze=json.loads(freeze_path.read_text())
# Input access guard rejects ALL scientific run observations, TEST administrative
# collection, and labels/GT, even though the fixtures never request these files.
def guard(event,args):
    if event=='open' and isinstance(args[0],(str,bytes)):
        path=str(args[0])
        if any(s in path for s in ('stage14-scientific-v2','stage14d-test-campaign','labels.csv','attack_events.csv')):
            raise RuntimeError('Forbidden scientific observation/GT input: '+path)
sys.addaudithook(guard)
forbidden_calls=[]
def profile(frame,event,arg):
    if event=='call':
        module=frame.f_globals.get('__name__','')
        name=frame.f_code.co_name
        if module.startswith('analysis.detection') and ('.evaluation' in module or name in ('fit','fit_baseline','calibrate')):
            forbidden_calls.append(module+'.'+name)
            raise RuntimeError('Forbidden fitting/calibration/evaluation call')
sys.setprofile(profile)
features=['ingress_packet_count','ingress_tcp_payload_length_sum_bytes','request_starts','mean_duration_ms','mean_cpu_percent']
families=['network','network','service','service','infrastructure']
methods={'zscore':(ZScore,zscore_spec()),'cov':(CoV,cov_spec(lookback=6)), 'ewma':(EWMA,ewma_spec()),'cusum':(CUSUM,cusum_spec())}
patterns={
 'positive_variable':[Decimal((i*7)%23+1) for i in range(144)],
 'all_zero':[Decimal(0)]*144,
 'null_reset_warmup':[None if i%11 in (0,1) else Decimal(i%17) for i in range(144)],
 'signed':[Decimal((-1 if i%2 else 1)*(i%9)) for i in range(144)],
 'large_offset_small_variance':[Decimal('1000000000000000000000000.'+str(i%9)) for i in range(144)],
 'boundary_nulls':[None if i in (0,46,47,49,80,81) else Decimal(100+i%5) for i in range(144)],
 'boundary_state':[Decimal(100)]*144,
 'all_null':[None]*144,
}
checks=[];evidence_digest=hashlib.sha256()
with tempfile.TemporaryDirectory(prefix='stage15a-review-synthetic-') as directory:
    temp=Path(directory)
    for feature,family in zip(features,families):
        baseline_record=freeze['zscore_baseline_models'][feature]
        baseline_path=ROOT/baseline_record['path']
        assert sha(baseline_path)==baseline_record['sha256']
        baseline_manifest=json.loads(baseline_path.read_text())
        # Synthetic envelopes reuse EXACT existing frozen numeric parameters.
        # No fitting/calibration and no reading scientific observation tables.
        key=dict(family=family,feature=feature,feature_schema_version=1,window_size_seconds='1')
        model=publish(temp/feature/'synthetic-model-envelope','baseline',dict(
            component=component(zscore_spec()),feature=key,sources=[],parameters=baseline_manifest['parameters']))
        for method,(cls,spec) in methods.items():
            row=next(r for r in freeze['primary_test_configurations'] if r['detector']==method and r['feature']==feature)
            actual=open_artifact(row['threshold_artifact'],'calibration').read('calibration')
            assert actual['parameters']['threshold']==row['threshold']
            baseline=model if method!='cov' else None
            threshold=publish(temp/feature/method/'synthetic-threshold-envelope','calibration',dict(
                component=actual['component'],score_component=component(spec),feature=key,
                baseline=baseline.reference if baseline else None,baseline_sources=[],sources=[],score_artifacts=[],
                parameters=actual['parameters']))
            version=CAL if method in ('zscore','cov') else EXT
            old=historical[version]
            for pattern,values in patterns.items():
                observations=tuple(Observation('synthetic-'+pattern,i,Decimal(i),Decimal(i+1),v) for i,v in enumerate(values))
                observed=ObservedSeries('synthetic-'+pattern,family,feature,Decimal(1),1,observations)
                # A label-free in-memory DEVELOPMENT source, snapshot empty by design.
                root=temp/'observable-input';root.mkdir(exist_ok=True)
                ref=dict(role='development',feature_dataset=str(root),run_id=observed.run_id,consumed_files_sha256={})
                source=BoundSeries(observed,'development',root,(),json.dumps(ref))
                results=[]
                for name,pipeline in [('historical',old),('current',current)]:
                    dest=temp/feature/method/pattern/name
                    scores=pipeline.score_run(source,cls(),spec,dest/'scores',baseline=baseline)
                    decisions=pipeline.decide(scores,StrictUpperTail(),upper_tail_spec(alpha='0.01'),threshold,dest/'decisions')
                    results.append((scores,decisions))
                a,b=results
                assert a[0].records==b[0].records
                assert a[1].records==b[1].records
                assert (a[0].artifact.root/'scores.csv').read_bytes()==(b[0].artifact.root/'scores.csv').read_bytes()
                assert (a[1].artifact.root/'decisions.csv').read_bytes()==(b[1].artifact.root/'decisions.csv').read_bytes()
                evidence_digest.update((b[0].artifact.root/'scores.csv').read_bytes())
                # Digest decision values without temporary directory policy-reference.
                evidence_digest.update(encoded([dict(index=r.score.window_index,decision=r.decision,reason=r.reason,at=r.available_at_seconds) for r in b[1].records]).encode())
                checks.append(dict(method=method,feature=feature,pattern=pattern,windows=144,
                    historical_head=version,scores_equal=True,decisions_equal=True,score_csv_byte_equal=True,decision_csv_byte_equal=True))
            # Boundary/ties/null policy test using existing frozen threshold.
            policy=StrictUpperTail();state=policy.start_run(actual['parameters'],upper_tail_spec(alpha='0.01').config)
            t=Decimal(row['threshold'])
            for value,available,reason,expected in [(t,True,None,False),(None,False,'missing',None)]:
                score=PolicyScore('synthetic-tie',0,Decimal(0),Decimal(1),value,available,reason,Decimal(1))
                assert policy.decide(score,state).decision is expected
sys.setprofile(None)
assert forbidden_calls==[]
assert not any(name.startswith('analysis.detection.evaluation') for name in sys.modules)
# For unchanged dependencies, byte identity makes current dependency use equivalent
# to the complete historical subtree, not just equivalent imported names.
numeric=['contracts.py','inputs.py','artifacts.py','empirical.py','protocol.py','detectors/_moments.py','detectors/zscore.py','detectors/cov.py']
identities=[]
for commit in (CAL,EXT):
    paths=list(numeric)
    if commit==EXT:paths+=['detectors/_standardized.py','detectors/ewma.py','detectors/cusum.py']
    for relative in paths:
        old=git('show',commit+':analysis/detection/'+relative)
        assert old==(ROOT/'analysis/detection'/relative).read_bytes(), (commit,relative)
        identities.append(dict(head=commit,path='analysis/detection/'+relative,sha256=hash_bytes(old),byte_identical=True))
result=dict(scope='SYNTHETIC_ONLY; frozen numeric parameters read from existing BASELINE/threshold manifests; no scientific observations read',
 comparisons=len(checks),windows_per_comparison=144,total_windows_compared=len(checks)*144,
 all_score_records_equal=True,all_decision_records_equal=True,all_score_csv_byte_equal=True,all_decision_csv_byte_equal=True,
 forbidden_fit_calibrate_evaluate_calls=forbidden_calls,evaluator_modules_imported=False,
 test_observations_read=False,ground_truth_read=False,scientific_observation_tables_read=False,
 numeric_parameters_new_or_reestimated=False,temporary_artifacts_removed=True,
 tie_negative_checks=20,unavailable_preserved_checks=20,
 checks=checks,unchanged_dependency_checks=identities,
 canonical_synthetic_result_sha256=evidence_digest.hexdigest())
p=ROOT/'experiment_results/stage15a-preflight-20261019/synthetic_reproduction_evidence.json'
with p.open('x') as stream:json.dump(result,stream,sort_keys=True,indent=2);stream.write('\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('checks','unchanged_dependency_checks')},indent=2))
