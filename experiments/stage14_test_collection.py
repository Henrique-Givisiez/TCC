"""Read-only Stage 14D.1 collection audit; no execution or detector imports.

Only materialize() writes, exclusively new administrative inventory/freeze files.
Historical scientific authority is never rebound to the administrative commit.
"""
import csv
import fcntl
import hashlib
import json
from collections import Counter
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path

from experiments.stage14_campaign import FrozenExecutor, campaign_identity, digest
from experiments.feature_schema import feature_schema
from experiments.dataset_schema import schema

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT/'experiment_results/stage14d-test-campaign-20261019'
HEAD = 'f27a5ae6117667f980f6de0217222d25da0e6e42'
IDENTITY = '56c72f0445a08bb909d5abde24078fab448d2b47691decbf99df1d7cdd582ad3'
RELEASE = 'experiment_results/stage14d-release-20261019/test_campaign_release_v1.json'
EXPECTED = dict(binding='45eeed559cf863873ff6d0e70bf01571a4591789c1cf863279a8e530fe2fa46b',
 environment='a6859c8b2db988560dfdb2717cbfa3a582b38a06fa5b23ab439dcf42e7ce5ed7',
 four_method_freeze='898e79394ac48a86a734100d324d0b6b966412166a0eac105dbdeccb2bd236f5',
 evaluation_protocol='c2e1ab6314ab67c984b6b0e8f505982d72ea4de2f463e8607488e73c2764ef20')
RELEASE_SHA = 'ae4aa451b7088696071fc12ff17557e72c2df0eaa0427d5c8600173d0cc4400e'


def require(condition, message):
    if not condition:
        raise ValueError('STOP: '+message)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False)+'\n').encode()


def checked(ref):
    path = ROOT/ref['path']
    require(sha(path) == ref['sha256'], 'authority hash '+str(path))
    return read(path)


def pairing(entries):
    require(len(entries) == 48, 'cardinality')
    require(Counter(e['scenario'] for e in entries) == Counter(B=16,C=16,P=16), 'scenarios')
    seeds = {e['seed'] for e in entries}
    require(len(seeds) == 16, 'seed cardinality')
    for seed in seeds:
        require(Counter(e['scenario'] for e in entries if e['seed']==seed)==Counter('BCP'), 'pairing')
    require(len({e['order'] for e in entries}) == 48, 'duplicate entry')


def operations(logs, orders):
    expected = Counter(checkpoint_updated=97, transition=96, execution_authority_accepted=48,
                       entry_start=48, technical_validation=48)
    require(Counter(x['event'] for x in logs)==expected, 'unexpected operations/attempt')
    for order in orders:
        rows = [x for x in logs if x.get('order')==order]
        require(Counter(x['event'] for x in rows)==Counter(transition=2, execution_authority_accepted=1,
                entry_start=1, technical_validation=1), 'extra/missing attempt')
        transitions = [(x['previous'],x['state']) for x in rows if x['event']=='transition']
        require(transitions==[('PENDING','RUNNING'),('RUNNING','COMPLETED_VALID')], 'failed/retried attempt')
        require(next(x for x in rows if x['event']=='technical_validation')['cleanup']['status']=='verified_idle', 'cleanup')


def audit():
    release = checked(dict(path=RELEASE,sha256=RELEASE_SHA))
    authority = release['authority']
    require(authority['head']==HEAD, 'collection HEAD')
    for key, expected in EXPECTED.items():
        require(authority[key]['sha256']==expected, 'expected authority '+key)
        checked(authority[key])
    for ref in authority['references'].values():
        checked(ref)
    state = read(DIRECTORY/'campaign_state.json')
    require(state['campaign_identity']==IDENTITY==campaign_identity(state['plan']), 'campaign identity')
    require(state['plan']['authority']==authority, 'checkpoint authority')
    require(state['total_entries']==48 and len(state['entries'])==48, 'checkpoint count')
    require(not (DIRECTORY/'stop_requested.json').exists(), 'stop requested')
    with (DIRECTORY/'campaign.lock').open('r') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX|fcntl.LOCK_NB)
        fcntl.flock(stream, fcntl.LOCK_UN)
    matrix = checked(authority['references']['matrix'])
    rows = [r for r in matrix['runs'] if r['partition']=='test']
    pairing(rows)
    require([digest(r) for r in rows]==release['ordered_matrix_identities'], 'released matrix')
    operations([json.loads(x) for x in (DIRECTORY/'operations.jsonl').read_text().splitlines()], [r['order'] for r in rows])
    executor = FrozenExecutor(authority['binding']['path'],EXPECTED['binding'],
        authority['evaluation_protocol']['path'],EXPECTED['evaluation_protocol'],RELEASE,RELEASE_SHA)
    accepted = []
    for entry,row in zip(state['entries'], rows):
        plan = entry['plan']; root = Path(plan['output'])
        require(entry['state']=='COMPLETED_VALID' and entry['attempt']==1 and entry['reason'] is None, 'attempt/status')
        require(entry['cleanup']['status']=='verified_idle' and entry['started_at'] < entry['finished_at'], 'open run')
        require(plan['matrix_identity']==digest(row) and plan['configuration']==row['config']
                and plan['config_sha256']==digest(row['config']), 'matrix/config identity')
        for key in ('order','seed','scenario','role'):
            require(plan[key]==row[key], 'entry '+key)
        receipt = executor.validate(plan)
        require(receipt==entry['validation'], 'historical receipt differs')
        for name in receipt['inventory']:
            require(name in ('scientific_run_before.json','scientific_run_after.json')
                    or name.split('/')[0] in ('raw','stage8','stage9','stage10'),
                    'unexpected scientific evaluation artifact')
            require(not any(word in Path(name).name.lower() for word in
                    ('score','decision','evaluation','threshold','detector')), 'detector artifact')
        after = read(root/'scientific_run_after.json'); before = read(root/'scientific_run_before.json')
        s8 = read(root/'stage8/dataset_manifest.json'); s9 = read(root/'stage9/validation_report.json')
        s10 = read(root/'stage10/feature_manifest.json')
        for cert in (before, after):
            require(cert['released_campaign_identity']==IDENTITY and cert['row']==row, 'run campaign/row')
            require(cert['environment']['stable']['git_head']==HEAD and not cert['environment']['dynamic']['git_status'], 'run HEAD/dirty')
            require(not cert['environment_comparison']['fatal'], 'run environment divergence')
        require(before['execution_id']==after['execution_id'], 'execution replaced')
        for provenance_path in ('raw/run_provenance.json','stage8/metadata/export_provenance.json'):
            provenance = read(root/provenance_path)
            require(provenance['code']['git']['commit']==HEAD
                    and not provenance['code']['git']['dirty'], 'Stage8/raw code authority')
        require(s8['schema_version']==1 and s8['missing_artifacts']==[] and s8['structural_status']=='complete', 'Stage8 contract')
        require(read(root/'stage8/schema.json')==schema(), 'Stage8 schema')
        for file in s8['files']:
            if file.get('origin_path') is not None:
                origin = Path(file['origin_path'])
                require(origin.resolve().is_relative_to((root/'raw').resolve()) and sha(origin)==file['sha256'], 'raw/export lineage')
        require(read(root/'stage10/feature_schema.json')==feature_schema(), 'feature schema/no imputation contract')
        require(s10['provenance']['code']['git']['commit']==HEAD and not s10['provenance']['code']['git']['dirty'], 'Stage10 authority')
        window=s10['window']; require(window['size_seconds']=='1' and window['planned_duration_seconds']=='144', 'window protocol')
        last=Decimal(window['last_observation_seconds'])
        require(window['windows']==max(144,int(last.to_integral_value(rounding=ROUND_FLOOR))+1), 'horizon')
        for family, table in feature_schema()['tables'].items():
            with (root/'stage10'/table['path']).open(newline='') as stream:
                reader=csv.DictReader(stream)
                require(reader.fieldnames==[f['name'] for f in table['fields']], 'features/labels schema')
                count=0
                for i,record in enumerate(reader):
                    require(record['run_id']==receipt['run_id'] and int(record['window_index'])==i
                            and Decimal(record['window_start_seconds'])==i
                            and Decimal(record['window_end_seconds'])==i+1, 'window identity/grid')
                    count+=1
                require(count==window['windows'], 'missing windows')
        with (root/'raw/attack_events.csv').open(newline='') as stream:
            events=list(csv.DictReader(stream))
        require(len(events)==(0 if row['scenario']=='B' else 1), 'GT event count')
        for event in events:
            require(event['run_id']==receipt['run_id'] and event['status']=='completed', 'GT identity/status')
            require(event['profile']==('continuous' if row['scenario']=='C' else 'periodic_burst'), 'GT global profile')
            times={k:Decimal(event[k]) for k in ('scheduled_start_seconds','scheduled_end_seconds','actual_start_seconds','actual_end_seconds','drained_end_seconds','last_request_start_seconds')}
            require(all(t.is_finite() and t>=0 for t in times.values()), 'GT invalid time')
            require(times['scheduled_start_seconds']==48 and times['scheduled_end_seconds']==84
                    and times['actual_start_seconds']<=times['actual_end_seconds']
                    and times['actual_start_seconds']<=times['last_request_start_seconds']<=times['drained_end_seconds'], 'GT temporal integrity')
        accepted.append(dict(campaign_entry=row['order'],run_identity=receipt['run_id'],seed=row['seed'],scenario=row['scenario'],
            matrix_identity=digest(row),configuration_sha256=row['config_sha256'],output_path=str(root.relative_to(ROOT)),
            stage8=dict(path='stage8/dataset_manifest.json',sha256=sha(root/'stage8/dataset_manifest.json')),
            stage9=dict(path='stage9/validation_report.json',sha256=sha(root/'stage9/validation_report.json')),
            stage10=dict(path='stage10/feature_manifest.json',sha256=sha(root/'stage10/feature_manifest.json')),
            dataset_valid=True,analysis_eligible=True,accepted_attempt=1,attempts=1,authority=authority,
            artifacts=receipt['inventory'],stage8_warnings=s8['warnings'],stage9_summary=s9['summary'],
            stage9_diagnostics=[c for c in s9['checks'] if c['severity']=='WARNING' or not c['passed']],
            stage10_warnings=s10['warnings'],stage10_diagnostics=s10['diagnostics']))
    require(len({e['run_identity'] for e in accepted})==48, 'run collision')
    output_root=Path(state['entries'][0]['plan']['output']).parent
    require({p.name for p in output_root.iterdir() if '_test_' in p.name}=={Path(e['output_path']).name for e in accepted}, 'extra TEST output')
    inventory=dict(schema_version=1,campaign_identity=IDENTITY,collection_authority_head=HEAD,experimental_unit='run/seed',entries=accepted)
    freeze=dict(schema_version=1,status='FROZEN',campaign_identity=IDENTITY,campaign_total=48,accepted_runs=48,
        B=16,C=16,P=16,unique_seeds=16,failed=0,incomplete=0,invalid=0,automatic_retries=0,replacement_runs=0,
        dataset_valid='48/48',analysis_eligible='48/48',collection_authority_head=HEAD,authority=authority,
        release=dict(path=RELEASE,sha256=RELEASE_SHA),
        inventory=dict(path=str((DIRECTORY/'test_collection_inventory.json').relative_to(ROOT)),sha256=hashlib.sha256(encode(inventory)).hexdigest()),
        administrative_evidence={name:sha(DIRECTORY/name) for name in ('campaign_state.json','operations.jsonl','console.log')},
        scientific_evaluation_performed_before_freeze=False,
        isolation_evidence='Exhaustive run receipts; unchanged authority hashes and clean collection Git records; exactly one execution per matrix entry. Negative claims limited to available administrative records.',
        post_test_tuning=False,threshold_changes=False,detector_changes=False,feature_selection_changes=False,
        matrix_changes=False,seed_changes=False,evaluation_protocol_changes=False,
        genealogy='Post-collection administrative commit is recorded separately; never collection authority.')
    return inventory, freeze


def materialize():
    inventory,freeze=audit()
    # A second independent read must reproduce exactly before any freeze write.
    require((inventory,freeze)==audit(), 'non-deterministic audit')
    for name,value in [('test_collection_inventory.json',inventory),('test_collection_freeze_manifest.json',freeze)]:
        path=DIRECTORY/name
        payload=encode(value)
        if path.exists():
            require(path.read_bytes()==payload, 'existing administrative artifact differs')
        else:
            with path.open('xb') as stream:
                stream.write(payload)
        require(path.read_bytes()==payload, 'materialization mismatch')
    return {name:sha(DIRECTORY/name) for name in ('test_collection_inventory.json','test_collection_freeze_manifest.json')}


if __name__=='__main__':
    print(json.dumps(materialize(),indent=2))
