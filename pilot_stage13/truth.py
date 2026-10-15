"""Post-scoring ground-truth adapter for pilot diagnostics, NEVER a detector input.

Does not implement event evaluation/delay or change Stage 10. Stage 8 events are
read only to audit experimental timing/counts, with original hashes preserved.
"""
import csv
from analysis.detection.evaluation import load_window_truth
from analysis.detection.inputs import checked_output, read_json, digest


def window_truth(source):
    validated,_=load_window_truth(source.root,source.reference)
    manifest=read_json(source.root/'feature_manifest.json')
    p=checked_output(source.root,manifest,'timeseries/labels.csv')
    with p.open(newline='') as stream:rows=list(csv.DictReader(stream))
    return tuple(dict(window_index=t.window_index,
        overlap=str(t.attack_event_overlap_fraction),attack_request_starts=int(r['attack_request_starts']))
        for t,r in zip(validated,rows))


def event_audit(dataset):
    manifest=read_json(dataset/'dataset_manifest.json')
    refs={x['path']:x for x in manifest['files']}
    def records(relative):
        p=dataset/relative
        assert digest(p)==refs[relative]['sha256']
        with p.open(newline='') as stream:return list(csv.DictReader(stream))
    events=records('raw/attacks/attack_events.csv')
    requests=records('raw/service/request_log.csv')
    attack=[r for r in requests if r['traffic_class']=='attack']
    benign=[r for r in requests if r['traffic_class']=='benign']
    failures=sum(r['outcome']!='response' for r in requests)
    end_values=[float(r['end_elapsed_seconds']) for r in requests if r['end_elapsed_seconds']]
    by_burst=[sum(24+6*i<=float(r['elapsed_seconds'])<26+6*i for r in attack) for i in range(6)]
    return dict(events=events,attack_starts=len(attack),benign_starts=len(benign),requests_total=len(requests),
        failures=failures,last_request_completion=max(end_values) if end_values else None,
        burst_start_counts_programmed=by_burst,
        event_file_sha256=refs['raw/attacks/attack_events.csv']['sha256'],
        requests_file_sha256=refs['raw/service/request_log.csv']['sha256'])
