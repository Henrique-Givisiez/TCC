"""Development-only historical smoke check and post-hoc score inspection.

No traffic generation, decisions, calibration or efficacy metrics. Only curated
nominally comparable Stage 5 A->C is used for external Z-score baseline scoring.
"""
import argparse
import csv
import json
from pathlib import Path
from unittest.mock import patch

from . import fit_baseline, load_series, score_run
from .artifacts import digest, encoded
from .detectors.zscore import ZScore, zscore_spec
from .detectors.cov import CoV, cov_spec
from .evaluation import load_window_truth
from .inputs import read_json

FEATURES = [('network', 'ingress_packet_count'),
            ('network', 'ingress_tcp_payload_length_sum_bytes'),
            ('service', 'request_starts'), ('service', 'mean_duration_ms'),
            ('infrastructure', 'mean_cpu_percent')]
CASES = ['stage7-regressions/stage5/A', 'stage7-regressions/stage5/C',
         'stage7-validation/continuous', 'stage7-validation/periodic',
         'stage7-regressions/stage6/expensive']


def validate_existing(destination, *, development_lookback):
    cov_config = cov_spec(lookback=development_lookback)
    root = Path(__file__).resolve().parents[2] / 'experiment_results/stage10-final'
    destination = Path(destination).resolve()
    # This curated validator is deliberately not a configurable experiment runner.
    if root == destination or root in destination.parents or destination in root.parents:
        raise ValueError('Output overlaps historical inputs')
    destination.mkdir(parents=True, exist_ok=False)
    sources, models, runs, snapshots = {}, {}, [], {}
    original_open = Path.open
    def block_labels(path, *args, **kwargs):
        if path.name == 'labels.csv':
            raise AssertionError('Labels may only be accessed in post-hoc evaluator inspection')
        return original_open(path, *args, **kwargs)

    # The access guard covers all loading/fitting/scoring, including hash reads.
    with patch.object(Path, 'open', block_labels):
        for case in CASES:
            m = read_json(root / case / 'feature_manifest.json')
            for family, feature in FEATURES:
                role = 'baseline' if case == CASES[0] else 'development'
                s = load_series(root / case, run_id=m['source_run_id'], family=family,
                    feature=feature, window_size_seconds='1', feature_schema_version=1, role=role)
                sources[case, feature] = s
                for relative, sha in s.snapshot:
                    path = s.root / relative
                    snapshots[str(path)] = (sha, path.stat().st_mtime_ns)
        for _, feature in FEATURES:
            models[feature] = fit_baseline([sources[CASES[0], feature]], ZScore(),
                zscore_spec(), destination / 'baselines' / feature)
            runs.append(('zscore', CASES[1], feature, score_run(sources[CASES[1], feature],
                ZScore(), zscore_spec(), destination / 'scores/zscore' / CASES[1] / feature,
                baseline=models[feature])))
        for case in CASES:
            for _, feature in FEATURES:
                # A is also the fitting source above; its CoV scoring is separate,
                # local-history development validation, with no fitted parameters.
                s = sources[case, feature]
                runs.append(('cov', case, feature, score_run(s, CoV(), cov_config,
                    destination / 'scores/cov' / case / feature)))
        for s in sources.values():
            s.verify()

    # Scores are already finalized. Only the evaluator's reader opens labels now;
    # truth is joined for inspection, never sent back to fit/start_run/update.
    truth_cache, truth_refs = {}, {}
    for case in CASES:
        source = sources[case, FEATURES[0][1]]
        truth_cache[case], truth_refs[case] = load_window_truth(source.root, source.reference)
    columns = ['method', 'case', 'run_id', 'family', 'feature', 'window_index',
               'window_start_seconds', 'window_end_seconds', 'feature_value',
               'score', 'score_available', 'unavailable_reason', 'available_at_seconds',
               'attack_event_overlap_fraction_posthoc']
    diagnostic = destination / 'diagnostics.csv'
    with diagnostic.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n')
        writer.writeheader()
        for method, case, feature, run in runs:
            source = sources[case, feature]
            for obs, score, truth in zip(source.series.observations, run.records, truth_cache[case]):
                assert obs.window_index == score.window_index == truth.window_index
                writer.writerow(dict(method=method, case=case, run_id=obs.run_id,
                    family=source.series.family, feature=feature, window_index=obs.window_index,
                    window_start_seconds=obs.window_start_seconds, window_end_seconds=obs.window_end_seconds,
                    feature_value='' if obs.value is None else obs.value,
                    score='' if score.score is None else score.score,
                    score_available=score.score_available, unavailable_reason=score.reason or '',
                    available_at_seconds=score.available_at_seconds,
                    attack_event_overlap_fraction_posthoc=truth.attack_event_overlap_fraction))
    changed = [p for p, (sha, mtime) in snapshots.items()
               if digest(p) != sha or Path(p).stat().st_mtime_ns != mtime]
    if changed:
        raise ValueError(f'Inputs changed: {changed}')
    summary = dict(scope='historical development/functional validation only; no efficacy evaluation',
        development_lookback=development_lookback, ddof=1,
        zscore_baseline_justification='Stage 5 A/C: same nominal benign / operation, four normal sources at 10 RPS/source, containers+proxy, one victim; historical provenance unknown, seed 42 only',
        zscore_not_applied_to=['stage7-validation/continuous', 'stage7-validation/periodic',
                              'stage7-regressions/stage6/expensive'],
        reason='No independent equivalent normal baseline for those operation/load scenarios',
        baselines={f: a.reference for f, a in models.items()},
        runs=[dict(method=m, case=c, feature=f, artifact=r.artifact.reference,
                   windows=len(r.records), available=sum(x.score_available for x in r.records))
              for m, c, f, r in runs],
        diagnostics=dict(path=diagnostic.name, sha256=digest(diagnostic),
                         truth_references=truth_refs, truth_access='posthoc evaluator only'),
        consumed_files_checked_hash_and_mtime=len(snapshots), changed_inputs=changed,
        decisions_produced=False, metrics_produced=False, new_experiments=False)
    (destination / 'summary.json').write_text(encoded(summary))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--development-lookback', required=True, type=int,
                        help='Functional-only parameter; not an optimal/scientific choice')
    args = parser.parse_args()
    summary = validate_existing(args.output, development_lookback=args.development_lookback)
    print(f"Validated {len(summary['runs'])} score artifacts; no decisions or metrics")


if __name__ == '__main__':
    main()
