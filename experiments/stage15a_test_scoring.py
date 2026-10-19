"""Stage 15A: hash-bound primary TEST scores/decisions, without evaluation.

Explicit release gate is scoped to the approved collection and 20 configurations.
The existing generic TEST lock stays intact. Scoring callbacks receive Observation;
policy callbacks receive PolicyScore. No labels or scenario enter either callback.
"""
import argparse
import csv
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from analysis.detection.artifacts import component, encoded, open_artifact
from analysis.detection.contracts import Observation, PolicyScore
from analysis.detection.detectors.zscore import ZScore, zscore_spec
from analysis.detection.detectors.cov import CoV, cov_spec
from analysis.detection.detectors.ewma import EWMA, ewma_spec
from analysis.detection.detectors.cusum import CUSUM, cusum_spec
from analysis.detection.empirical import StrictUpperTail, upper_tail_spec
from analysis.detection.inputs import ContractError, number, read_json, safe_file
from experiments.feature_schema import feature_schema
from experiments.stage14_test_collection import (ROOT, HEAD, IDENTITY, RELEASE,
    RELEASE_SHA, EXPECTED, sha, pairing)
from experiments.stage15a_provenance import (REVIEW, validate_bridge, approve_snapshot)

COLLECTION = 'experiment_results/stage14d-test-campaign-20261019'
INPUTS = {
 'test_inventory': dict(path=COLLECTION+'/test_collection_inventory.json',sha256='10ab05b24e9896d41e944192909f79b366e8cbbe7e08eb24f695b5d2ad1c2b47'),
 'test_collection_freeze': dict(path=COLLECTION+'/test_collection_freeze_manifest.json',sha256='8d784758ff7b751f68dc595d434a65bae1d764d5a21312b0e3d96a5f6613327d'),
 'four_method_freeze': dict(path='experiment_results/stage14-ewma-cusum-calibration-20261019/four_method_calibration_freeze_manifest.json',sha256=EXPECTED['four_method_freeze']),
 'evaluation_protocol': dict(path='experiments/protocols/stage14_test_evaluation_protocol_v1.json',sha256=EXPECTED['evaluation_protocol']),
 'provenance_review': REVIEW,
 'provenance_bridge': dict(path='experiment_results/stage15a-preflight-20261019/provenance_bridge.json',
     sha256='9c361e6b873dc39eb7d1d51de4c2b3476260aa25f4959ea126e0e07dd115c7a7')}
OUTPUT = ROOT/'experiment_results/stage15a-test-scoring-20261019'
FEATURES = ('ingress_packet_count','ingress_tcp_payload_length_sum_bytes','request_starts','mean_duration_ms','mean_cpu_percent')
METHODS = {'zscore':(ZScore,zscore_spec()),'cov':(CoV,cov_spec(lookback=6)),
           'ewma':(EWMA,ewma_spec()),'cusum':(CUSUM,cusum_spec())}
FAMILIES = dict(zip(FEATURES,('network','network','service','service','infrastructure')))
PROCESSING_PARENT = 'ec086c25aaa81ac4da85f5f3c83875dce9b830c1'


def require(condition, message):
    if not condition:
        raise ContractError('STOP: '+message)


def byte_hash(data):
    return hashlib.sha256(data).hexdigest()


@contextmanager
def scoring_only():
    """Fail closed if fitting, calibration or an evaluator is ever called."""
    previous=sys.getprofile()
    def guard(frame,event,arg):
        if event=='call':
            module=frame.f_globals.get('__name__','')
            if module.startswith('analysis.detection'):
                require('.evaluation' not in module and frame.f_code.co_name not in
                        ('fit','fit_baseline','calibrate'), 'forbidden fitting/calibration/evaluation call')
        if previous is not None:
            previous(frame,event,arg)
    sys.setprofile(guard)
    try:
        yield
    finally:
        sys.setprofile(previous)


def checked(ref):
    path=ROOT/ref['path']
    require(sha(path)==ref['sha256'], 'hash mismatch: '+str(path))
    return read_json(path)


def source_hashes():
    paths = sorted((ROOT/'analysis/detection').rglob('*.py'))
    paths += [Path(__file__), ROOT/'experiments/feature_schema.py',ROOT/'experiments/stage14_test_collection.py',
              ROOT/'experiments/stage15a_provenance.py']
    return {str(p.relative_to(ROOT)):sha(p) for p in paths}


def validate_collection():
    validate_bridge(INPUTS['provenance_bridge'])
    docs={key:checked(ref) for key,ref in INPUTS.items()}
    inventory=docs['test_inventory']; freeze=docs['test_collection_freeze']
    require(freeze['status']=='FROZEN' and freeze['campaign_identity']==IDENTITY
            and freeze['collection_authority_head']==HEAD and freeze['inventory']==INPUTS['test_inventory'], 'collection authority')
    release=checked(dict(path=RELEASE,sha256=RELEASE_SHA))
    require(freeze['authority']==release['authority'], 'release authority')
    for key,expected in EXPECTED.items():
        require(freeze['authority'][key]['sha256']==expected, 'authority '+key)
        checked(freeze['authority'][key])
    for ref in freeze['authority']['references'].values():
        checked(ref)
    require(inventory['campaign_identity']==IDENTITY and inventory['collection_authority_head']==HEAD, 'inventory authority')
    entries=inventory['entries']
    pairing([dict(order=e['campaign_entry'],seed=e['seed'],scenario=e['scenario']) for e in entries])
    require(len({e['run_identity'] for e in entries})==48, 'duplicate run')
    for entry in entries:
        require(entry['dataset_valid'] is True and entry['analysis_eligible'] is True
                and entry['attempts']==1 and entry['authority']==freeze['authority'], 'accepted entry')
        root=ROOT/entry['output_path']
        # Bytes only: no parsing ground truth, labels, or scientific observations.
        actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
        require(actual==set(entry['artifacts']), 'TEST file set changed')
        for relative,record in entry['artifacts'].items():
            p=safe_file(root,relative)
            require(p.stat().st_size==record['size'] and sha(p)==record['sha256'], 'TEST modified: '+str(p))
    return docs


@dataclass(frozen=True)
class FrozenConfiguration:
    method: str
    feature: str
    spec: object
    parameters: object
    threshold_parameters: dict
    lineage: dict


def configurations(freeze):
    require(freeze==checked(INPUTS['four_method_freeze']), 'configuration not from frozen authority')
    bridge=validate_bridge(INPUTS['provenance_bridge'])
    rows=freeze['primary_test_configurations']
    expected={(m,f) for m in METHODS for f in FEATURES}
    require(len(rows)==20 and {(r['detector'],r['feature']) for r in rows}==expected, 'primary configuration matrix')
    result=[]
    for row in rows:
        method,feature=row['detector'],row['feature']; cls,spec=METHODS[method]
        require(row['alpha']=='0.01' and row['lookback']==(6 if method=='cov' else None)
                and row['lambda_value']==('0.2' if method=='ewma' else None)
                and row['k']==('0.5' if method=='cusum' else None), 'unfrozen configuration')
        artifact=open_artifact(row['threshold_artifact'],'calibration'); threshold=artifact.read('calibration')
        require(threshold['component']==component(upper_tail_spec(alpha='0.01'))
                and threshold['score_component']==component(spec)
                and threshold['feature']==dict(family=FAMILIES[feature],feature=feature,feature_schema_version=1,window_size_seconds='1')
                and threshold['parameters']['threshold']==row['threshold'], 'threshold identity/config')
        # Exact reviewed pairs only; original historical manifests stay intact.
        for relative,expected_sha in threshold['provenance']['framework_files_sha256'].items():
            actual_sha=sha(ROOT/'analysis/detection'/relative)
            require(actual_sha==bridge['current_framework_sha256'][relative], 'execution dependency '+relative)
            approve_snapshot(relative,expected_sha,actual_sha)
        baseline_ref=None; parameters=None
        if method!='cov':
            ref=freeze['zscore_baseline_models'][feature]; baseline=checked(ref)
            baseline_ref=dict(path=str((ROOT/ref['path']).parent),manifest_sha256=ref['sha256'])
            require(threshold['baseline']==baseline_ref and baseline['component']==component(zscore_spec())
                    and baseline['feature']==threshold['feature'], 'baseline identity')
            parameters=baseline['parameters']
        else:
            require(threshold['baseline'] is None, 'CoV baseline')
        cls().start_run(parameters,spec.config)
        StrictUpperTail().start_run(threshold['parameters'],upper_tail_spec(alpha='0.01').config)
        lineage=dict(configuration=row,component=component(spec),threshold_artifact=artifact.reference,
                     baseline=baseline_ref,threshold_identity=artifact.manifest_sha256)
        result.append(FrozenConfiguration(method,feature,spec,parameters,threshold['parameters'],lineage))
    return tuple(result)


def read_observations(entry,feature):
    """Only the selected observable CSV is parsed; label tables are never opened."""
    root=ROOT/entry['output_path']/'stage10'; manifest=read_json(root/'feature_manifest.json')
    require(sha(root/'feature_manifest.json')==entry['stage10']['sha256'], 'Stage10 manifest')
    require(manifest['source_run_id']==entry['run_identity'] and manifest['window']['size_seconds']=='1', 'series identity')
    schema=feature_schema(); table=schema['tables'][FAMILIES[feature]]
    require(read_json(root/'feature_schema.json')==schema, 'observable schema')
    path=safe_file(root,table['path']); observations=[]; index=-1
    require(sha(path)==entry['artifacts']['stage10/'+table['path']]['sha256'], 'feature input changed')
    with path.open(newline='') as stream:
        reader=csv.DictReader(stream)
        require(reader.fieldnames==[f['name'] for f in table['fields']], 'CSV observable columns')
        for index,row in enumerate(reader):
            require(None not in row and all(v is not None for v in row.values()), 'malformed feature row')
            require(row['run_id']==entry['run_identity'] and row['window_index']==str(index)
                    and number(row['window_start_seconds'])==index and number(row['window_end_seconds'])==index+1, 'grid')
            # Preserve tail in source; [0,144) is the authorized scoring selection.
            if index<144:
                value=None if row[feature]=='' else number(row[feature])
                field=next(f for f in table['fields'] if f['name']==feature)
                require(value is not None or field['nullable'], 'nonnullable feature')
                require(value is None or field['type']!='integer' or value==value.to_integral_value(), 'feature domain')
                observations.append(Observation(entry['run_identity'],index,Decimal(index),Decimal(index+1),value))
    require(index+1==manifest['window']['windows'], 'source window count')
    require(len(observations)==144, 'missing scoring windows')
    return tuple(observations),dict(stage10_manifest=entry['stage10'],
        feature_table=dict(path=str(path.relative_to(ROOT)),sha256=sha(path)),
        feature_schema_sha256=sha(root/'feature_schema.json'),scoring_horizon='[0,144)',
        source_window_count=manifest['window']['windows'],selected_window_indices=list(range(144)))


def score_decide(observations,configuration):
    """Pure callback boundary: no metadata, files, GT, or evaluator capabilities."""
    require(type(configuration) is FrozenConfiguration, 'frozen configuration required')
    require(configuration.method in METHODS and configuration.feature in FEATURES, 'primary configuration only')
    cls,expected_spec=METHODS[configuration.method]
    require(configuration.spec==expected_spec, 'unsupported detector config')
    detector=cls(); state=detector.start_run(configuration.parameters,configuration.spec.config)
    policy=StrictUpperTail()
    policy_state=policy.start_run(configuration.threshold_parameters,upper_tail_spec(alpha='0.01').config)
    records=[]
    run_id=None
    for index,observation in enumerate(observations):
        require(type(observation) is Observation and observation.window_index==index
                and observation.window_start_seconds==index and observation.window_end_seconds==index+1, 'causal origin/grid')
        require(run_id is None or run_id==observation.run_id, 'mixed run observations')
        run_id=observation.run_id
        value=detector.update(observation,state)
        at=value.available_at_seconds if value.available_at_seconds is not None else observation.window_end_seconds
        require(at>=observation.window_end_seconds and (not records or at>=number(records[-1]['available_at'])), 'causal availability')
        score=PolicyScore(observation.run_id,index,observation.window_start_seconds,
            observation.window_end_seconds,value.score,value.score is not None,value.reason,at)
        decision=policy.decide(score,policy_state)
        require(decision.decision==(None if value.score is None else value.score>number(configuration.threshold_parameters['threshold'])), 'strict decision')
        records.append(dict(window_index=index,window_start_seconds=str(observation.window_start_seconds),
            window_end_seconds=str(observation.window_end_seconds),available_at=str(at),
            observation_value=None if observation.value is None else str(observation.value),
            score=None if value.score is None else str(value.score),decision=decision.decision,
            availability=value.score is not None,unavailable_reason=value.reason))
    return records


def combination(entry,configuration):
    observations,source=read_observations(entry,configuration.feature)
    records=score_decide(observations,configuration)
    counts=dict(observation_count=len(records),valid_score_count=sum(r['availability'] for r in records),
        unavailable_score_count=sum(not r['availability'] for r in records),
        positive_decision_count=sum(r['decision'] is True for r in records),
        negative_decision_count=sum(r['decision'] is False for r in records))
    metadata=dict(run_id=entry['run_identity'],campaign_entry=entry['campaign_entry'],seed=entry['seed'],scenario=entry['scenario'],
        method=configuration.method,feature=configuration.feature,detector_configuration=component(configuration.spec),
        threshold_identity=configuration.lineage['threshold_identity'],threshold=configuration.threshold_parameters['threshold'],alpha='0.01')
    # Scenario exists solely in this administrative envelope, outside callbacks.
    return dict(schema_version=1,**metadata,counts=counts,records=records,
        lineage=dict(inputs=INPUTS,source=source,detector=configuration.lineage,
                     collection_authority_head=HEAD,stage9_summary=entry['stage9_summary'],
                     stage9_diagnostics=entry['stage9_diagnostics'],stage10_warnings=entry['stage10_warnings']))


def preflight():
    docs=validate_collection()
    configs=configurations(docs['four_method_freeze'])
    require(len(configs)==20,'primary configurations')
    return docs,configs


def run(destination=OUTPUT,verify=False):
    destination=Path(destination)
    require(destination.resolve()==OUTPUT.resolve(), 'fixed administrative output destination')
    require(verify or not destination.exists(), 'output collision; never overwrite')
    docs,configs=preflight()  # Before any scientific scoring.
    processing_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    subprocess.run(['git','merge-base','--is-ancestor',PROCESSING_PARENT,processing_head],cwd=ROOT,check=True)
    if verify:
        original=read_json(destination/'stage15a_scoring_manifest.json')
        subprocess.run(['git','merge-base','--is-ancestor',original['processing_head'],processing_head],cwd=ROOT,check=True)
        processing_head=original['processing_head']
    else:
        require(processing_head==PROCESSING_PARENT,'unreviewed processing parent')
    execution_sources=source_hashes()
    files=[]; totals={k:0 for k in ('observation_count','valid_score_count','unavailable_score_count','positive_decision_count','negative_decision_count')}
    for entry in docs['test_inventory']['entries']:
        for config in configs:
            value=combination(entry,config)
            data=encoded(value).encode()
            # Replay in memory BEFORE publication, same frozen inputs/configuration.
            require(data==encoded(combination(entry,config)).encode(), 'non-deterministic scores/decisions')
            relative=f"runs/{entry['campaign_entry']:02d}/{config.method}/{config.feature}.json"
            path=destination/relative
            if verify:
                require(path.read_bytes()==data, 'reproduction mismatch: '+relative)
            else:
                path.parent.mkdir(parents=True,exist_ok=True)
                with path.open('xb') as stream: stream.write(data)
            files.append(dict(path=relative,sha256=byte_hash(data),bytes=len(data),
                campaign_entry=entry['campaign_entry'],method=config.method,feature=config.feature,counts=value['counts']))
            for key in totals: totals[key]+=value['counts'][key]
        print('Verified' if verify else 'Materialized', 'campaign entry',entry['campaign_entry'],flush=True)
    require(len(files)==960 and len({f['path'] for f in files})==960, 'combination cardinality')
    validate_collection()  # All input bytes still identical after scoring.
    require(source_hashes()==execution_sources,'execution sources changed during scoring')
    manifest=dict(schema_version=1,stage='15A',status='FROZEN',test_runs=48,methods=4,features=5,
        primary_configurations=20,combinations=960,detector_feature_run_combinations=960,alpha='0.01',cov_L=6,ewma_lambda='0.2',cusum_k='0.5',
        scoring_horizon='[0,144)',scoring_start=0,state_reset_at_48=False,evaluation_performed=False,
        ground_truth_consumed_by_scorer=False,ground_truth_consumed_by_decision_policy=False,
        test_fitting=False,test_calibration=False,test_derived_threshold=False,post_test_tuning=False,
        inputs=INPUTS,collection_authority_head=HEAD,processing_parent_head=PROCESSING_PARENT,processing_head=processing_head,
        provenance_review_sha256=REVIEW['sha256'],provenance_bridge_sha256=INPUTS['provenance_bridge']['sha256'],
        scientific_evaluator_executed=False,
        processing_source_sha256=execution_sources,processing_authority='processing_head with exact execution source hashes; subsequent administrative commit recorded separately',
        configurations=[c.lineage for c in configs],outputs=files,counts=totals,
        outputs_set_sha256=byte_hash(encoded(files).encode()),deterministic_reproduction='byte-identical in-memory replay; verify mode checks published bytes',
        missing_combinations=0,duplicates=0,labels_in_output_tables=False)
    payload=encoded(manifest).encode(); mp=destination/'stage15a_scoring_manifest.json'
    if verify: require(mp.read_bytes()==payload, 'manifest reproduction mismatch')
    else:
        with mp.open('xb') as stream: stream.write(payload)
    expected={f['path'] for f in files}|{'stage15a_scoring_manifest.json'}
    actual={str(p.relative_to(destination)) for p in destination.rglob('*') if p.is_file()}
    require(actual-{'administrative_finalization.json'}==expected, 'extra/missing output artifacts')
    return dict(manifest_sha256=sha(mp),output_artifacts=len(files)+1,counts=totals,combinations=960)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true')
    parser.add_argument('--preflight-only',action='store_true')
    args=parser.parse_args()
    if args.preflight_only:
        docs,configs=preflight()
        print(json.dumps(dict(status='PREFLIGHT_PASSED',runs=len(docs['test_inventory']['entries']),configurations=len(configs),scoring_performed=False)))
    else:
        with scoring_only():
            result=run(verify=args.verify)
        print(json.dumps(result,indent=2))
