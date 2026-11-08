"""Deterministic replay and conservative 1-second assignment; no detector fitting."""
from collections import Counter
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from simulator.cpu_observations import CONTRACT, MARKER, SAMPLES, SUMMARY, delta, number

PREFIX = 'evidence/other/'
PATHS = tuple(PREFIX+p for p in (MARKER, SAMPLES, SUMMARY))


def validate_evidence(marker, rows, summary, status):
    if (not isinstance(marker, dict) or not isinstance(summary, dict)
            or not isinstance(rows, list) or any(not isinstance(r,dict) for r in rows)):
        raise ValueError('Malformed CPU evidence objects')
    if marker.get('contract') != CONTRACT or type(marker.get('schema_version')) is not int or marker['schema_version'] != 1:
        raise ValueError('Unsupported CPU evidence contract')
    if status.get('cpu_observation_contract', CONTRACT) != CONTRACT:
        raise ValueError('Unsupported declared CPU contract')
    if marker['run_id'] != status['run_id'] or len(marker['container_ids']) != 1:
        raise ValueError('CPU run/single-victim identity mismatch')
    if marker['samples'] != SAMPLES or marker['summary'] != SUMMARY:
        raise ValueError('CPU artifact paths differ')
    for k, source in [('origin_monotonic', 'experiment_start_monotonic'), ('origin_epoch', 'experiment_start_timestamp')]:
        if number(marker[k]) != number(status[source]):
            raise ValueError('CPU clock anchor mismatch')
    if number(marker['interval_seconds']) <= 0:
        raise ValueError('Invalid CPU acquisition interval')
    if (summary.get('contract') != CONTRACT or type(summary.get('schema_version')) is not int or summary['schema_version'] != 1
            or summary.get('run_id') != status['run_id'] or summary.get('worker_finished') is not True
            or summary.get('fatal_error') is not None):
        raise ValueError('CPU worker finalization unconfirmed')
    previous = None
    last_end = Decimal('-Infinity')
    for seq, row in enumerate(rows, 1):
        if (type(row.get('schema_version')) is not int or row['schema_version'] != 1 or row.get('contract') != CONTRACT
                or type(row.get('sequence')) is not int or row['sequence'] != seq or row.get('run_id') != marker['run_id']
                or row.get('container_id') not in marker['container_ids']):
            raise ValueError('CPU sequence/run/container/schema mismatch or duplicate')
        a, b, receipt = map(number, (row['call_start_seconds'], row['call_end_seconds'], row['received_seconds']))
        if not last_end <= a <= b <= receipt or a < 0:
            raise ValueError('CPU acquisition chronology invalid')
        if number(row['delay_seconds']) != max(Decimal(0), a-number(row['scheduled_seconds'])):
            # float subtraction in live collection is serialized; allow only rounding noise.
            if abs(number(row['delay_seconds'])-max(Decimal(0), a-number(row['scheduled_seconds']))) > Decimal('1e-9'):
                raise ValueError('CPU schedule delay inconsistent')
        last_end = receipt
        # Pure replay does not trust stored CPU%, reference or interval bounds.
        derived, previous = delta(row, previous)
        if any(row.get(k) != v for k, v in derived.items()):
            raise ValueError('CPU derived observation differs from counter replay')
    if summary['attempts'] != len(rows) or summary['snapshots'] != sum(r['snapshot_received'] for r in rows):
        raise ValueError('CPU summary counts differ')
    return True


def missing_runs(values):
    runs = []
    first = None
    for i, value in enumerate([*values, 0]):
        if value is None and first is None:
            first = i
        elif value is not None and first is not None:
            runs.append(dict(start=first, end=i, windows=i-first)); first = None
    return runs


def assign_cpu(marker, rows, summary, status, windows, tolerance='0.05'):
    """Use whole acquisition brackets, never prorate crossing intervals.

    Both brackets must fit within +/- tolerance of their nominal boundaries,
    and the new snapshot must have arrived by window closure. These are observed
    approximate intervals, not reconstructed exact integrals of nominal seconds.
    """
    with localcontext() as ctx:
        ctx.prec = 50; ctx.rounding = ROUND_HALF_EVEN
        tol = number(tolerance)
        if not 0 <= tol < Decimal('0.5'):
            raise ValueError('CPU boundary tolerance must be in [0,0.5) seconds')
        validate_evidence(marker, rows, summary, status)
        values = [None]*windows
        candidates = {}
        rejected = []
        for row in rows:
            reason = row['state'] if row['state'] != 'valid' else None
            index = None
            if reason is None:
                a, b = map(number, row['interval_start_bounds'])
                c, d = map(number, row['interval_end_bounds'])
                index = int(((a+b)/2).to_integral_value(rounding=ROUND_HALF_EVEN))
                if not 0 <= index < windows:
                    reason = 'outside_feature_grid'
                elif not (abs(a-index) <= tol and abs(b-index) <= tol
                          and abs(c-(index+1)) <= tol and abs(d-(index+1)) <= tol):
                    reason = 'insufficient_boundary_alignment'
                elif number(row['received_seconds']) > index+1:
                    reason = 'received_after_window_closure'
            if reason:
                rejected.append(dict(sequence=row['sequence'], window_index=index, reason=reason))
            else:
                candidates.setdefault(index, []).append(row)
        assignments = []
        for i, group in sorted(candidates.items()):
            if len(group) != 1:
                rejected.extend(dict(sequence=r['sequence'], window_index=i, reason='multiple_candidates') for r in group)
                continue
            row = group[0]; values[i] = number(row['cpu_percent'])
            assignments.append(dict(window_index=i, sequence=row['sequence'],
                reference_sequence=row['reference_sequence'],
                interval_start_bounds=row['interval_start_bounds'], interval_end_bounds=row['interval_end_bounds'],
                received_seconds=row['received_seconds']))
        consecutive = 0; cov = []
        for value in values:
            consecutive = 0 if value is None else consecutive+1
            cov.append(consecutive >= 6)
        phases = {}
        for name, a, b in [('WARMUP',0,30), ('PRE',30,150), ('ATTACK',150,270), ('POST',270,390)]:
            end = min(b, windows); own = values[a:end]
            if not own:
                continue
            valid = sum(v is not None for v in own)
            phases[name] = dict(expected=len(own), valid=valid, missing=len(own)-valid,
                coverage=str(Decimal(valid)/len(own)), missing_runs=missing_runs(own),
                potential_decisions=dict(zscore=valid, ewma=valid, cusum_freeze=valid,
                                         cov=sum(cov[a:end])))
        quality = dict(schema_version=1, contract=CONTRACT,
            policy=dict(boundary_tolerance_seconds=str(tol), provisional=True,
                        assignment='whole_brackets_near_nominal_boundaries_one_delta_per_window',
                        availability='received_by_window_closure', interpolation=False,
                        coverage_gate_by_phase=False),
            attempts=len(rows), snapshots=sum(r['snapshot_received'] for r in rows),
            valid_deltas=sum(r['state']=='valid' for r in rows),
            invalid_observations=sum(r['state']!='valid' for r in rows),
            states=dict(Counter(r['state'] for r in rows)),
            failures_by_category=dict(Counter(r['error'].split(':',1)[0] for r in rows if r['error'])),
            missed_opportunities=summary['missed_opportunities'],
            fresh_snapshots=sum(r['fresh'] for r in rows),
            acquisition_coverage=(str(Decimal(sum(r['fresh'] for r in rows))/(len(rows)+summary['missed_opportunities']))
                                  if len(rows)+summary['missed_opportunities'] else None),
            observed_intervals_seconds=[r['observed_interval_seconds'] for r in rows if r['observed_interval_seconds'] is not None],
            delays_seconds=[r['delay_seconds'] for r in rows],
            valid_windows=sum(v is not None for v in values), missing_windows=sum(v is None for v in values),
            missing_runs=missing_runs(values), phases=phases, assignments=assignments, rejected=rejected,
            potential_decisions_note='Availability upper bounds only; no baseline, threshold, zero-CoV-mean or eligibility claim.',
            potential_decisions=dict(zscore=sum(v is not None for v in values), ewma=sum(v is not None for v in values),
                                     cusum_freeze=sum(v is not None for v in values), cov=sum(cov)))
        return values, quality


def load_evidence(inputs, status):
    """Marker OR status OR a versioned sample prohibits fallback to historical CPU."""
    declared = status.get('cpu_observation_contract')
    present = PATHS[0] in inputs.index
    if not present and declared is None:
        # Historical victim_stats.jsonl exists too; inspect only to detect new rows.
        if PATHS[1] in inputs.index:
            first = inputs.file(PATHS[1]).open()
            with first:
                import json
                line = first.readline()
                if line and json.loads(line).get('contract'):
                    raise ValueError('New CPU evidence missing contract marker')
        return None
    import json
    # Use native JSON floats for byte-faithful replay of live-derived fields.
    marker = json.loads(inputs.file(PATHS[0]).read_text())
    text = inputs.file(PATHS[1]).read_text()
    if text and not text.endswith('\n'):
        raise ValueError('Incomplete CPU JSONL final line')
    rows = [json.loads(line) for line in text.splitlines()]
    summary = json.loads(inputs.file(PATHS[2]).read_text())
    validate_evidence(marker, rows, summary, status)
    return marker, rows, summary
