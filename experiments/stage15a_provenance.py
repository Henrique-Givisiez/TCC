"""Stage 15A-only, exact-hash provenance bridge approved in human review.

Historical manifests are never rewritten. Only four reviewed historical/current
hash pairs are mapped; every other file, threshold and snapshot remains strict.
"""
from pathlib import Path
import subprocess

from analysis.detection.artifacts import encoded
from analysis.detection.inputs import ContractError, read_json
from experiments.stage14_test_collection import ROOT, sha

DIRECTORY = ROOT/'experiment_results/stage15a-preflight-20261019'
REVIEW = dict(path='experiment_results/stage15a-preflight-20261019/provenance_review.json',
              sha256='31b9fe33452b7b92af226569149c2e40938015ed2653ac0f2615d6a5ab572923')
STOP = dict(path='experiment_results/stage15a-preflight-20261019/stop_report.json',
            sha256='17f987bc0419d86ec350be9a913dd83f47e21280d15bf8124e9fdd14ca19d857')
BRIDGE_PATH = DIRECTORY/'provenance_bridge.json'
APPROVED_PAIRS = {
 'evaluation/__init__.py': ('d8dd1ac7bbf145691326898f8e29d37e42cc3340d54f0d23c449ac411cf2d59f',
                          '31ddb70da03505f8e506b3a6581d3b4a8186c684eea0998bff0a8c8d2594da98','EVALUATION_ONLY'),
 'evaluation/events.py': ('44836f114f560c7735ffd90f82bded4b1f5e45dcf05562abc8d90b12a0d55084',
                         'e6c0c18d00c577a7ff42f9bc57e8f07b9015aa3c04d66a9ae530ae27978b8dec','EVALUATION_ONLY'),
 'horizons.py': ('f4e04910ee68bbdaf8b1997dde6257f0a3332ab65be2127a65c3bf3e3e0099d1',
                 '3626399fa7b45f0dcb9b729f25ac54c5d9945eca0c9837e5d8ced06e4703a4cc','EVALUATION_ONLY'),
 'pipeline.py': ('651bbaa11c4e8696d86b0bbf3ad498f441f927fefbc6eaafd9685e8531ab80e6',
                 '22cb26f9a5e9da26ea9a2373faba6accb3b935b860c2e983316a9ca7e1e5db48','SCIENTIFIC_EQUIVALENT')}


def require(condition, message):
    if not condition:
        raise ContractError('STOP: '+message)


def checked(ref):
    path=ROOT/ref['path']
    require(sha(path)==ref['sha256'],'provenance evidence hash: '+ref['path'])
    return read_json(path)


def approve_snapshot(relative, historical, actual):
    """No caller-supplied allowlist and no wildcard exceptions."""
    if historical==actual:
        return
    pair=APPROVED_PAIRS.get(relative)
    require(pair is not None and (historical,actual)==pair[:2],
            'unreviewed historical/current provenance pair: '+relative)


def bridge_document():
    review=checked(REVIEW); checked(STOP)
    for ref in review['evidence'].values():
        require(sha(ROOT/ref['path'])==ref['sha256'],'review evidence modified')
    require(review['recommendation']['option']=='OPTION A','review recommendation')
    genealogy=read_json(DIRECTORY/'threshold_provenance_genealogy.json')
    historical_union={}
    threshold_records=[]
    for entry in genealogy:
        path=ROOT/entry['threshold_manifest_path']
        require(sha(path)==entry['threshold_manifest_sha256'],'threshold changed')
        manifest=read_json(path)
        historical=manifest['provenance']['framework_files_sha256']
        for relative,expected in historical.items():
            actual=sha(ROOT/'analysis/detection'/relative)
            approve_snapshot(relative,expected,actual)
            previous=historical_union.get(relative)
            require(previous is None or previous==actual,'inconsistent framework snapshot')
            historical_union[relative]=actual
        threshold_records.append(dict(method=entry['method'],feature=entry['feature'],
            path=entry['threshold_manifest_path'],sha256=entry['threshold_manifest_sha256'],
            historical_head=entry['provenance_head'],historical_framework_sha256=historical))
    current_files={str(p.relative_to(ROOT/'analysis/detection')):sha(p)
                   for p in sorted((ROOT/'analysis/detection').rglob('*.py'))}
    require(current_files==historical_union,'new/missing framework dependency')
    differences={}
    for relative,(historical,current,classification) in APPROVED_PAIRS.items():
        approved=review['divergence_analysis'][relative]
        require((approved['recorded_sha256'],approved['current_sha256'],approved['classification'])
                ==(historical,current,classification),'approved review pair')
        differences[relative]=dict(historical_sha256=historical,current_sha256=current,
             classification=classification,affected_configurations=approved['affected_primary_configurations'],
             change_commit=approved['change_commit'])
    return dict(schema_version=1,scope='Stage 15A frozen primary scoring and decisions ONLY',
        status='HUMAN_OPTION_A_APPROVED',human_decision='OPTION A APPROVED',
        human_authorization='Explicit human approval in this session; preserve history and accept only exact reviewed pairs; no evaluation or metrics.',
        original_stop=STOP,provenance_review=REVIEW,
        historical_provenance_equals_current_repository_provenance=False,
        scientific_score_decision_behavior='verified equivalent for exactly the approved divergences',
        approved_divergences=differences,
        equivalence_evidence=review['evidence'],
        protected_dataflow=review['dataflow'],
        threshold_historical_provenance=threshold_records,
        current_framework_sha256=current_files,
        reviewed_repository_head=review['head'],
        exclusions_are_not_generic=True,historical_artifacts_modified=False,
        evaluation_authorized=False,metrics_authorized=False,parameter_changes_authorized=False)


def materialize_bridge():
    document=bridge_document();payload=encoded(document).encode()
    if BRIDGE_PATH.exists():
        require(BRIDGE_PATH.read_bytes()==payload,'existing bridge differs')
    else:
        with BRIDGE_PATH.open('xb') as stream:stream.write(payload)
    return dict(path=str(BRIDGE_PATH.relative_to(ROOT)),sha256=sha(BRIDGE_PATH))


def validate_bridge(reference):
    require(reference['path']==str(BRIDGE_PATH.relative_to(ROOT)),'bridge path')
    document=checked(reference)
    require(encoded(document)==encoded(bridge_document()),'bridge content differs from approved authority')
    return document
