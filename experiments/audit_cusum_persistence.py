"""Read-only arithmetic diagnostic of existing frozen CUSUM/request_starts evidence.

Does not import detection/scoring/calibration/evaluation pipelines. One-step checks
use the PREVIOUS OFFICIAL score, never publish replacement scores or decisions.
"""
import argparse
from collections import Counter
import csv
from decimal import Context, Decimal as D, ROUND_HALF_EVEN, ROUND_CEILING, localcontext
from fractions import Fraction
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN)
EXPECTED = {
    'stage15a_scoring_manifest.json': '089a25681dd13810a94a92def805aa9a7e314955ebdcca671d625d959ae3a9d5',
    'stage15b_evaluation_manifest.json': '2b36134d60f9dd5a4dc5bd721f4c5df194cc8ad695ab5d71c73156b5bb5863ca',
    'stage15b_evaluation_freeze_manifest.json': '8232ce397022963dd8741d7e14746630a822cdf74cda4f4a113d7ca5a974f2c2',
    'stage15c_analysis_manifest.json': '8cf1340484b89378996d3b29b485e186f2a82074809c025c3ca645be4ce44f9a',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


class Evidence:
    def __init__(self):
        self.inputs = {}

    def check(self, ref, *, manifest=False):
        path = Path(ref['path'])
        path = (ROOT/path).resolve() if not path.is_absolute() else path.resolve()
        if manifest:
            path = path/'manifest.json'
        path.relative_to(ROOT)
        expected = ref.get('sha256', ref.get('manifest_sha256'))
        assert sha(path) == expected, 'hash mismatch: ' + str(path)
        size = ref.get('bytes', ref.get('size'))
        assert size is None or path.stat().st_size == size, 'size mismatch'
        self.inputs[str(path.relative_to(ROOT))] = dict(sha256=expected, bytes=path.stat().st_size)
        return path

    def document(self, ref, **kwargs):
        return json.loads(self.check(ref, **kwargs).read_text())

    def locate(self, filename):
        matches = [p for p in (ROOT/'experiment_results').glob('*/'+filename) if sha(p)==EXPECTED[filename]]
        assert len(matches)==1, 'expected one authoritative manifest: '+filename
        path = matches[0]
        return path, self.document(dict(path=str(path), sha256=EXPECTED[filename]))


def describe(values):
    if not values:
        return dict(n=0, min=None, mean=None, max=None)
    with localcontext(CONTEXT):
        return dict(n=len(values), min=min(values), mean=sum(values)/D(len(values)), max=max(values))


def audit():
    evidence = Evidence()
    apath,a = evidence.locate('stage15a_scoring_manifest.json')
    bpath,b = evidence.locate('stage15b_evaluation_manifest.json')
    _,bf = evidence.locate('stage15b_evaluation_freeze_manifest.json')
    _,c = evidence.locate('stage15c_analysis_manifest.json')
    assert a['status']==b['status']==bf['status']=='FROZEN'
    assert b['inputs']['stage15a_manifest']['sha256']==sha(apath)
    assert bf['manifest']==dict(path=str(bpath.relative_to(ROOT)),sha256=sha(bpath))
    assert c['inputs']['stage15a_manifest']==b['inputs']['stage15a_manifest']
    inventory = evidence.document(a['inputs']['test_inventory'])
    freeze = evidence.document(a['inputs']['four_method_freeze'])
    evidence.document(a['inputs']['test_collection_freeze'])
    seed = c['example']['example_seed']
    assert seed==171864802==min(e['seed'] for e in inventory['entries'])
    entries = {e['scenario']:e for e in inventory['entries'] if e['seed']==seed}
    baseline = evidence.document(freeze['zscore_baseline_models']['request_starts'])
    params = baseline['parameters']
    mean = Fraction(int(params['mean_exact']['numerator']), int(params['mean_exact']['denominator']))
    sigma = D(params['sigma'])
    config = next(x for x in freeze['primary_test_configurations'] if x['detector']=='cusum' and x['feature']=='request_starts')
    threshold_doc = evidence.document(config['threshold_artifact'],manifest=True)
    threshold = D(threshold_doc['parameters']['threshold'])
    assert threshold==D(config['threshold']) and config['k']=='0.5'
    datasets = {}
    for scenario in ('B','C'):
        entry = entries[scenario]
        output = next(o for o in a['outputs'] if o['campaign_entry']==entry['campaign_entry'] and o['method']=='cusum' and o['feature']=='request_starts')
        data = evidence.document(dict(output,path=str(apath.parent/output['path'])))
        assert (data['seed'],data['scenario'],data['run_id'])==(seed,scenario,entry['run_identity'])
        assert D(data['threshold'])==threshold
        assert data['threshold_identity']==config['threshold_artifact']['manifest_sha256']
        assert data['lineage']['detector']['baseline']['manifest_sha256']==freeze['zscore_baseline_models']['request_starts']['sha256']
        assert data['detector_configuration']==freeze['CUSUM']['component']
        table = csv_rows(evidence.check(data['lineage']['source']['feature_table']))
        assert len(data['records'])==144
        for r in data['records']:
            observed = table[r['window_index']]['request_starts']
            assert r['observation_value']==observed and table[r['window_index']]['run_id']==data['run_id']
        datasets[scenario] = data
    entry = entries['C']
    def run_file(name):
        ref = entry['artifacts'][name]
        return evidence.check(dict(ref,path=str(ROOT/entry['output_path']/name)))
    events = csv_rows(run_file('raw/attack_events.csv'))
    event = events[0]
    assert len(events)==1 and event['run_id']==entry['run_identity'] and event['profile']=='continuous'
    requests = csv_rows(run_file('raw/request_log.csv'))
    assert all(r['run_id']==entry['run_identity'] for r in requests)
    journals=[]
    for name in entry['artifacts']:
        if name.startswith('raw/source_artifacts/attack_') and name.endswith('/output/journal.jsonl'):
            local=[json.loads(l) for l in run_file(name).read_text().splitlines()]
            assert all(r['run_id']==entry['run_identity'] and r['sequence']==i+1 for i,r in enumerate(local))
            journals.extend(local)
    observed_starts=Counter(int(D(r['elapsed_seconds']).to_integral_value(rounding='ROUND_FLOOR')) for r in requests)
    assert all(observed_starts[r['window_index']]==int(r['observation_value']) for r in datasets['C']['records'])
    journal_begins={r['payload']['request_id']:r['payload'] for r in journals if r['kind']=='request_begin'}
    attack_rows={r['request_id']:r for r in requests if r['generator']=='attack'}
    assert set(journal_begins)==set(attack_rows)
    assert all(D(str(r['elapsed_seconds']))==D(attack_rows[k]['elapsed_seconds']) for k,r in journal_begins.items())
    gt = {k:D(event[k]) for k in ('scheduled_end_seconds','stop_requested_seconds','actual_start_seconds',
                               'actual_end_seconds','last_request_start_seconds','drained_end_seconds')}
    records = datasets['C']['records']
    diagnostic=[]
    previous=D(0)
    with localcontext(CONTEXT):
        for r in records:
            x=D(r['observation_value']) if r['observation_value'] is not None else None
            # Match the declared exact-mean subtraction and two 50-digit rounding steps.
            if x is None:
                z=increment=expected=error=None
            else:
                difference=Fraction(x)-mean
                z=(D(difference.numerator)/D(difference.denominator))/sigma
                increment=z-D('.5')
                expected=max(D(0),previous+z-D('.5'))
                error=D(r['score'])-expected
                assert (D(r['score'])>threshold)==r['decision']
            diagnostic.append(dict(window_index=r['window_index'],start=r['window_start_seconds'],end=r['window_end_seconds'],
                observation=x,z=z,increment_z_minus_k=increment,previous_official_score=previous,
                official_score=r['score'],expected_one_step_DIAGNOSTIC=expected,official_minus_expected=error,
                official_decision=r['decision'],fully_post_event=D(r['window_start_seconds'])>=gt['actual_end_seconds']))
            previous=D(r['score']) if r['score'] is not None else D(0)
        post=[d for d in diagnostic if d['fully_post_event'] and D(d['end'])<=144]
        at_end=max((r for r in records if D(r['available_at'])<=gt['actual_end_seconds']),key=lambda r:D(r['available_at']))
        crossing=next(r for r in records if D(r['window_start_seconds'])<gt['actual_end_seconds']<D(r['window_end_seconds']))
        late=[r for r in requests if r['generator']=='attack']
        post_requests=[r for r in requests if D(r['elapsed_seconds'])>=gt['actual_end_seconds']]
        paired=[D(datasets['B']['records'][d['window_index']]['observation_value']) for d in post]
        event_ref=next(o for o in b['outputs'] if o['path']=='event_metrics_per_run.csv')
        event_rows=csv_rows(evidence.check(dict(event_ref,path=str(bpath.parent/event_ref['path']))))
        official_event=next(r for r in event_rows if r['campaign_entry']==str(entry['campaign_entry']) and r['method']=='cusum' and r['feature']=='request_starts')
        result = dict(diagnostic_only=True, pipeline_reexecuted=False, official_outputs_replaced=False,
            raw_start_counts_match_all_144_frozen_observations=True,attack_journal_begins_match_raw=True,
            seed=seed,scenario='C',campaign_entry=entry['campaign_entry'],run_id=entry['run_identity'],
            baseline=dict(parameters=params,runs=len(baseline['sources']),fit_selections=baseline['fit_selections']),
            calibration=dict(threshold=threshold,n=threshold_doc['parameters']['n_valid'],
                quantile_index=threshold_doc['parameters']['quantile_index_zero_based'],
                calibration_runs=len(threshold_doc['sources']),temporal_selections=threshold_doc['temporal_selections']),
            event=gt,official_event_detection=official_event,
            score_last_available_at_effective_end=at_end,event_crossing_window=crossing,
            first_fully_post_event=post[0],last_fully_post_event=post[-1],post_windows=len(post),
            positive_post_windows=sum(d['official_decision'] is True for d in post),
            post_full_window_exposure_seconds=D(post[-1]['end'])-D(post[0]['start']),
            last_available_minus_effective_end_seconds=D(records[-1]['available_at'])-gt['actual_end_seconds'],
            post_observations=describe([d['observation'] for d in post]),paired_B_observations=describe(paired),
            post_standardized=describe([d['z'] for d in post]),post_increments=describe([d['increment_z_minus_k'] for d in post]),
            sum_post_z=sum(d['z'] for d in post),sum_post_increments=sum(d['increment_z_minus_k'] for d in post),
            positive_increment_sum=sum(d['increment_z_minus_k'] for d in post if d['increment_z_minus_k']>0),
            negative_increment_sum=sum(d['increment_z_minus_k'] for d in post if d['increment_z_minus_k']<0),
            increment_direction_counts=dict(Counter('grow' if d['increment_z_minus_k']>0 else 'fall' if d['increment_z_minus_k']<0 else 'hold' for d in post)),
            post_at_or_below_baseline_mean=sum(Fraction(d['observation'])<=mean for d in post),
            post_observation_frequency=dict(Counter(str(d['observation']) for d in post)),
            recurrence_mismatches=sum(d['official_minus_expected']!=0 for d in diagnostic if d['official_minus_expected'] is not None),
            max_abs_recurrence_error=max(abs(d['official_minus_expected']) for d in diagnostic if d['official_minus_expected'] is not None),
            ideal_baseline_windows_to_nonpositive_alarm_at_effective_end=((D(at_end['score'])-threshold)/D('.5')).to_integral_value(rounding=ROUND_CEILING),
            ideal_baseline_additional_windows_after_last=((D(records[-1]['score'])-threshold)/D('.5')).to_integral_value(rounding=ROUND_CEILING),
            recovery_censored=post[-1]['official_decision'] is True,
            attack_starts_at_or_after_nominal_end=sum(D(r['elapsed_seconds'])>=gt['scheduled_end_seconds'] for r in late),
            attack_starts_at_or_after_effective_end=sum(D(r['elapsed_seconds'])>=gt['actual_end_seconds'] for r in late),
            attack_completions_at_or_after_effective_end=sum(D(r['end_elapsed_seconds'])>=gt['actual_end_seconds'] for r in late if r['end_elapsed_seconds']),
            post_request_classes=dict(Counter(r['traffic_class'] for r in post_requests)),
            journal_counts=dict(Counter(r['kind'] for r in journals)))
    for name,ref in evidence.inputs.items():
        assert sha(ROOT/name)==ref['sha256'], 'input changed during audit'
    result['verified_inputs']=evidence.inputs
    return result,diagnostic


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result,diagnostic=audit()
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'diagnostic.json').write_text(json.dumps(result,default=str,indent=2)+'\n')
    with (args.output/'window_arithmetic_DIAGNOSTIC.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(diagnostic[0]));writer.writeheader();writer.writerows(diagnostic)
    print(json.dumps({k:result[k] for k in ('seed','run_id','post_windows','positive_post_windows','recurrence_mismatches','recovery_censored')},default=str))


if __name__=='__main__':
    main()
