"""Single host writer for scientific outputs, based on source lifecycle evidence."""
import csv
import json
from pathlib import Path
from simulator.ground_truth import encode_event_ids
from simulator.request_logger import REQUEST_FIELDS, RTT_FIELDS


def records(directory, entries, strict=True):
    result = []
    for entry in entries:
        path = Path(directory)/entry['source_id']/'output/journal.jsonl'
        if not path.exists():
            continue
        lines = path.read_text().splitlines(keepends=True)
        for index, line in enumerate(lines):
            if not line.endswith('\n') and not strict:
                break
            item = json.loads(line)
            if item['sequence'] != index+1 or item['source_id'] != entry['source_id'] or item['run_id'] != entry['run_id']:
                raise ValueError('source journal identity/sequence mismatch')
            result.append(item)
    return result


def reconcile(ground_truth, entries, journal, final=False):
    """Close global emission only when every attacker certifies local closure."""
    attackers = [e['source_id'] for e in entries if e['source_type']=='attack']
    if not attackers or 'event_001' not in ground_truth._events:
        return
    snapshots, closed = {}, {}
    for item in journal:
        if item['kind'] in ('event_snapshot', 'emission_closed'):
            snapshots[item['source_id']] = item['payload']
        if item['kind']=='source_closed':
            closed[item['source_id']] = item['payload']
    event = ground_truth._events['event_001']
    row = event.row
    local = [snapshots[s] for s in attackers if s in snapshots]
    def values(key):
        return [r[key] for r in local if r.get(key) is not None]
    starts, lasts = values('actual_start_seconds'), values('last_request_start_seconds')
    activations, stops = values('activation_requested_seconds'), values('stop_requested_seconds')
    row.update(actual_start_seconds=min(starts) if starts else None,
               last_request_start_seconds=max(lasts) if lasts else None,
               activation_requested_seconds=min(activations) if activations else None,
               stop_requested_seconds=min(stops) if stops else None,
               actual_end_seconds=None, drained_end_seconds=None)
    emission_known = len(local)==len(attackers) and all(
        r['actual_end_seconds'] is not None or
        (r['actual_start_seconds'] is None and r['status']=='not_executed' and r['stop_requested_seconds'] is not None)
        for r in local)
    if starts and emission_known:
        # This is closure of admission + queued STARTs, never completion time.
        row['actual_end_seconds'] = max(r['actual_end_seconds'] if r['actual_start_seconds'] is not None
                                       else r['stop_requested_seconds'] for r in local)
    drained = emission_known and all(s in closed and closed[s]['drained'] and closed[s]['logger_complete'] for s in attackers)
    if starts:
        row['status'] = 'completed' if drained else 'emission_ended' if emission_known else 'stopping' if stops else 'active'
        if drained:
            row['drained_end_seconds'] = max(values('drained_end_seconds'))
    else:
        row['status'] = 'not_executed' if emission_known else 'activated' if activations else 'planned'
    if final and not drained and attackers:
        row['status'] = 'incomplete'
    if stops:
        row['end_reason'] = next(r['end_reason'] for r in local if r['stop_requested_seconds']==min(stops))
    event.accepting = not emission_known
    ground_truth.persist()


def write_csv(path, fields, rows):
    with open(path, 'w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def aggregate(ground_truth, entries, directory, request_file, rtt_file, routing_file, metrics_file):
    journal = records(directory, entries)
    reconcile(ground_truth, entries, journal, final=True)
    begins, finishes = {}, {}
    for item in journal:
        row = item['payload']
        if item['kind']=='request_begin':
            if row['request_id'] in begins:
                raise ValueError('duplicate request ID')
            begins[row['request_id']] = row.copy()
        elif item['kind']=='request_finish':
            if row['request_id'] in finishes:
                raise ValueError('duplicate request completion')
            finishes[row['request_id']] = row.copy()
    if set(finishes)-set(begins):
        raise ValueError('completion without request beginning')
    requests, rtts = [], []
    for request_id, begin in begins.items():
        row = finishes.get(request_id, dict(begin, outcome='incomplete'))
        active, ids = ground_truth.context(row['elapsed_seconds'])
        row.update(attack_active=active, active_event_ids=encode_event_ids(ids))
        requests.append(row)
        if row['outcome']=='response':
            rtts.append(dict(timestamp=row['end_timestamp'], rtt=row['duration_ms'], run_id=row['run_id'],
                             request_id=request_id, traffic_class=row['traffic_class'], elapsed_seconds=row['end_elapsed_seconds']))
    requests.sort(key=lambda r:(r['elapsed_seconds'],r['request_id']))
    rtts.sort(key=lambda r:(r['elapsed_seconds'],r['request_id']))
    admission_audit = []
    admission_complete = True
    for entry in entries:
        source = entry['source_id']
        own = [item for item in journal if item['source_id']==source]
        admitted = sum(item['kind']=='admission' for item in own)
        abandoned = sum(item['kind']=='abandoned_admission' for item in own)
        started = sum(item['kind']=='request_begin' for item in own)
        finished = sum(item['kind']=='request_finish' for item in own)
        certified = True if entry['source_type']!='attack' else admitted-abandoned==started
        admission_complete = certified and admission_complete
        admission_audit.append(dict(source_id=source, admitted=admitted, abandoned=abandoned,
                                    started=started, finished=finished, emission_counts_consistent=certified))
    (Path(directory)/'aggregation_audit.json').write_text(json.dumps(dict(run_id=ground_truth.run_id,
        sources=admission_audit, complete=admission_complete and len(begins)==len(finishes)),indent=2)+'\n')
    write_csv(request_file, REQUEST_FIELDS, requests)
    write_csv(rtt_file, RTT_FIELDS, rtts)
    with open(routing_file, 'w') as destination:
        for entry in entries:
            source = Path(directory)/entry['source_id']/'output/routing_evidence.jsonl'
            if source.exists():
                destination.write(source.read_text())
    path = Path(metrics_file)
    if path.exists():
        with path.open(newline='') as stream:
            reader = csv.DictReader(stream)
            fields, metrics = reader.fieldnames, list(reader)
        for row in metrics:
            active, ids = ground_truth.context(float(row['elapsed_seconds']))
            row.update(attack_active=active, active_event_ids=encode_event_ids(ids))
        write_csv(path, fields, metrics)
    return admission_complete and len(begins)==len(finishes), requests
