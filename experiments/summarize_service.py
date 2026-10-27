"""Offline client service summaries. Does not import simulator execution or detectors."""
import argparse
import csv
import hashlib
import json
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

from simulator.request_logger import REQUEST_FIELDS


CLASSES = ('benign', 'attack')
OUTCOMES = ('success_2xx', 'other_response', 'http_error', 'transport_error', 'client_error')
END_BOUNDARY = '__at_observation_end__'


def number(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Expected finite decimal') from exc
    if not result.is_finite():
        raise ValueError('Expected finite decimal')
    return result


def ratio(numerator, denominator):
    if not denominator:
        return None
    with localcontext() as ctx:
        ctx.prec = 50
        return Decimal(numerator) / Decimal(denominator)


def quantile(values, probability):
    """Linear type-7 empirical quantile; no minimum-support claim."""
    if not values:
        return None
    values = sorted(values)
    with localcontext() as ctx:
        ctx.prec = 50
        position = (len(values) - 1) * Decimal(probability)
        low = int(position)
        high = min(low + 1, len(values) - 1)
        return values[low] + (values[high] - values[low]) * (position - low)


def validate_plan(plan):
    if plan.get('schema_version') != 1 or not isinstance(plan.get('run_id'), str) or not plan['run_id']:
        raise ValueError('Phase plan requires schema_version=1 and nonempty run_id')
    phases = plan.get('phases')
    if not isinstance(phases, list) or not phases:
        raise ValueError('Nonempty contiguous phase partition required')
    result = []
    previous = Decimal(0)
    names = set()
    for phase in phases:
        name = phase['name']
        start, end = number(phase['start_seconds']), number(phase['end_seconds'])
        if (not isinstance(name, str) or not name or name == END_BOUNDARY or name in names
                or start != previous or end <= start):
            raise ValueError('Phases must be unique, contiguous, positive-width and start at zero')
        names.add(name)
        result.append((name, start, end))
        previous = end
    return result


def load_requests(path, run_id):
    """Validate final request_log contract, including incomplete rows; no GT read."""
    result, seen = [], set()
    with Path(path).open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if (reader.fieldnames is None or len(set(reader.fieldnames)) != len(reader.fieldnames)
                or not set(REQUEST_FIELDS).issubset(reader.fieldnames)):
            raise ValueError('request_log.csv contract columns missing or duplicated')
        for line, row in enumerate(reader, 2):
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError('Malformed CSV row')
                identity = row['request_id']
                if row['run_id'] != run_id or not identity or identity in seen:
                    raise ValueError('Mixed runs or missing/duplicate request ID')
                seen.add(identity)
                cls = row['traffic_class']
                if cls not in CLASSES or row['generator'] != {'benign': 'normal', 'attack': 'attack'}[cls]:
                    raise ValueError('Generator/class mismatch')
                start = number(row['elapsed_seconds'])
                end = None if row['end_elapsed_seconds'] == '' else number(row['end_elapsed_seconds'])
                duration = None if row['duration_ms'] == '' else number(row['duration_ms'])
                status = None if row['http_status'] == '' else int(row['http_status'])
                outcome = row['outcome']
                if start < 0 or (end is not None and end < start):
                    raise ValueError('Invalid request interval')
                if outcome == 'incomplete':
                    if end is not None or duration is not None or row['end_timestamp'] != '' or status is not None:
                        raise ValueError('Incomplete must not have fabricated terminal fields')
                else:
                    if outcome not in ('response', 'http_error', 'transport_error', 'client_error'):
                        raise ValueError('Unknown outcome')
                    if end is None or duration is None or duration < 0 or not row['end_timestamp']:
                        raise ValueError('Concluded request requires terminal fields')
                    # Logger serializes binary floating-point arithmetic. Allow only
                    # tiny representation error, not a scientifically different duration.
                    if abs(duration - (end - start) * 1000) > Decimal('0.000001'):
                        raise ValueError('duration_ms inconsistent with client interval')
                    if outcome == 'response' and (status is None or not 100 <= status < 400):
                        raise ValueError('Response status incompatible with outcome')
                    if outcome == 'http_error' and (status is None or status < 400):
                        raise ValueError('HTTP error status incompatible with outcome')
                category = ('success_2xx' if outcome == 'response' and 200 <= status < 300 else
                            'other_response' if outcome == 'response' else outcome)
                result.append(dict(request_id=identity, traffic_class=cls, start=start, end=end,
                                   duration=duration, category=category))
            except (ValueError, KeyError) as exc:
                raise ValueError(f'Invalid request row {line}: {exc}') from exc
    return result


def summarize(request_path, plan, *, as_of=None):
    phases = validate_plan(plan)
    horizon = phases[-1][2]
    cutoff = horizon if as_of is None else number(as_of)
    if cutoff < 0 or cutoff > horizon:
        raise ValueError('as_of must lie within phase partition')
    requests = load_requests(request_path, plan['run_id'])

    def phase_at(time):
        if time == horizon:
            return END_BOUNDARY
        for name, start, end in phases:
            if start <= time < end:
                return name
        raise ValueError('Observed request outside supplied phase partition')

    rows = {}
    for cls in CLASSES:
        for name, start, end in phases + [(END_BOUNDARY, horizon, horizon)]:
            rows[cls, name] = dict(traffic_class=cls, phase=name,
                start_seconds=start, end_seconds=end,
                exposure_seconds=max(Decimal(0), min(end, cutoff) - start),
                starts=0, known_ends=0, cohort_known_ends=0,
                cohort_open_as_of=0, cohort_incomplete_no_end=0,
                cohort_end_after_cutoff=0, completed_cross_phase=0,
                open_crossed_phase_boundary=0,
                cohort_outcomes={k: 0 for k in OUTCOMES},
                end_outcomes={k: 0 for k in OUTCOMES}, _durations=[])
    included = ignored = 0
    for request in requests:
        start, end = request['start'], request['end']
        if start >= cutoff:
            ignored += 1
            continue
        included += 1
        cohort = rows[request['traffic_class'], phase_at(start)]
        cohort['starts'] += 1
        if end is None or end > cutoff:
            cohort['cohort_open_as_of'] += 1
            cohort['cohort_incomplete_no_end' if end is None else 'cohort_end_after_cutoff'] += 1
            # A boundary at cutoff is already reached; the request has no known
            # end by then. This says nothing about when an incomplete truly ended.
            cohort['open_crossed_phase_boundary'] += int(any(start < b <= cutoff for _, b, _ in phases[1:]))
            continue
        category = request['category']
        cohort['cohort_known_ends'] += 1
        cohort['cohort_outcomes'][category] += 1
        terminal = rows[request['traffic_class'], phase_at(end)]
        terminal['known_ends'] += 1
        terminal['end_outcomes'][category] += 1
        cohort['completed_cross_phase'] += int(terminal['phase'] != cohort['phase'])
        if category == 'success_2xx':
            cohort['_durations'].append(request['duration'])

    for row in rows.values():
        durations = row.pop('_durations')
        success = row['cohort_outcomes']['success_2xx']
        failures = sum(row['cohort_outcomes'][k] for k in ('http_error', 'transport_error', 'client_error'))
        row['duration_success_2xx_ms'] = dict(n=len(durations), eligible_known_successes=success,
            mean=ratio(sum(durations), len(durations)), p50=quantile(durations, '.5'),
            p95=quantile(durations, '.95'), quantile='linear_type_7')
        row['rates_per_second'] = dict(starts=ratio(row['starts'], row['exposure_seconds']),
            known_ends=ratio(row['known_ends'], row['exposure_seconds']),
            success_2xx_ends=ratio(row['end_outcomes']['success_2xx'], row['exposure_seconds']),
            end_outcomes={k: ratio(v, row['exposure_seconds']) for k, v in row['end_outcomes'].items()})
        row['cohort_fractions'] = dict(success_2xx_per_started=ratio(success, row['starts']),
            failures_per_started=ratio(failures, row['starts']),
            failures_per_known_end=ratio(failures, row['cohort_known_ends']),
            incomplete_no_end_per_started=ratio(row['cohort_incomplete_no_end'], row['starts']),
            denominator_started=row['starts'], denominator_known_end=row['cohort_known_ends'],
            unresolved=row['cohort_open_as_of'], final=row['cohort_open_as_of'] == 0)
        assert row['starts'] == row['cohort_known_ends'] + row['cohort_open_as_of']
        assert row['cohort_known_ends'] == sum(row['cohort_outcomes'].values())
        assert row['known_ends'] == sum(row['end_outcomes'].values())
    known = sum(r['known_ends'] for r in rows.values())
    opened = sum(r['cohort_open_as_of'] for r in rows.values())
    assert included == known + opened
    return dict(schema_version=1, run_id=plan['run_id'], as_of_seconds=cutoff,
        phase_semantics='[start,end); ends at final boundary use zero-exposure boundary bucket',
        source=dict(path=str(Path(request_path)), sha256=hashlib.sha256(Path(request_path).read_bytes()).hexdigest()),
        phase_plan=plan, rows=list(rows.values()),
        reconciliation=dict(input_rows=len(requests), included_starts=included,
            ignored_starts_at_or_after_cutoff=ignored, known_ends=known, open_as_of=opened,
            starts_equal_known_ends_plus_open=included == known + opened),
        limitations=['Only persisted attempts are visible; not a live collector or crash recovery.',
            'Incomplete means no known end, not proof of a still-running request.',
            'Open-cohort fractions and duration summaries are conditional on observed ends, not final estimates.'])


def json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request_log', type=Path)
    parser.add_argument('--phases', type=Path, required=True)
    parser.add_argument('--as-of', help='Inclusive cutoff for known ends; starts must be strictly earlier')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.request_log, json.loads(args.phases.read_text()), as_of=args.as_of)
    # Exclusive creation: never replace an existing result or scientific input.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, default=json_default, allow_nan=False)
        stream.write('\n')


if __name__ == '__main__':
    main()
