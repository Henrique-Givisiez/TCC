"""Versioned victim CPU evidence. Pure functions: no Docker or wall-clock IO."""
from datetime import datetime, timezone
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
import re

CONTRACT = 'victim-cpu-snapshots-v1'
MARKER = 'cpu_observation_contract.json'
SAMPLES = 'victim_stats.jsonl'
SUMMARY = 'victim_stats.summary.json'


def number(value):
    if isinstance(value, bool):
        raise ValueError('boolean is not a counter/time')
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('nonfinite counter/time')
    return result


def read_epoch(text):
    """Preserve Docker RFC3339 fractional seconds, including nanoseconds."""
    match = re.fullmatch(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?Z', text or '')
    if not match:
        raise ValueError('invalid Docker read timestamp')
    seconds = int(datetime.fromisoformat(match[1]).replace(tzinfo=timezone.utc).timestamp())
    return Decimal(seconds) + Decimal('0.' + (match[2] or '0'))


def delta(row, previous=None):
    with localcontext() as context:
        context.prec = 50; context.rounding = ROUND_HALF_EVEN
        return _delta(row, previous)


def _delta(row, previous=None):
    """Return derived fields and next reference. API failures retain last valid read.

    Resets rebase at the current snapshot. Repeated/regressive reads never refresh
    a reference. Counter units are Docker nanoseconds; n is online host CPUs,
    a multiplier in the Docker convention, NOT a normalization denominator.
    """
    result = dict(cpu_percent=None, state='acquisition_error', reason=row.get('error'),
                  reference_sequence=None, observed_interval_seconds=None,
                  interval_start_bounds=None, interval_end_bounds=None, fresh=False)
    if not row['snapshot_received']:
        return result, None if row.get('reference_invalidated') else previous
    if previous is not None and (row['container_id'], row['generation']) == (previous['container_id'], previous['generation']):
        try:
            if read_epoch(row['docker_read']) <= read_epoch(previous['docker_read']):
                result.update(state='invalid_timestamp', reason='repeated_or_regressive_read')
                return result, previous
        except (ValueError, TypeError):
            pass  # normal invalid-snapshot handling below
    try:
        stamp = read_epoch(row['docker_read'])
        counters = row['counters']
        u, s, n = (number(counters[k]) for k in ('total_usage', 'system_cpu_usage', 'online_cpus'))
        if u < 0 or s < 0 or n <= 0 or n != int(n) or u != int(u) or s != int(s):
            raise ValueError('invalid counters')
        if not row['container_id'] or not row['generation']:
            raise ValueError('missing container generation')
        generation = row['generation']
        if (not isinstance(generation['started_at'], str) or not generation['started_at']
                or type(generation['restarts']) is not int or generation['restarts'] < 0):
            raise ValueError('invalid execution generation')
        a, b = map(number, (row['call_start_seconds'], row['call_end_seconds']))
        if not a <= b <= number(row['received_seconds']):
            raise ValueError('invalid acquisition order')
        if not number(row['call_start_epoch']) <= stamp <= number(row['call_end_epoch']):
            raise ValueError('Docker read outside acquisition wall-clock bracket')
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        result.update(state='invalid_snapshot', reason=str(exc))
        # Missing/reset counter support must not bridge unknown generations.
        return result, None
    result.update(state='first_read', reason='reference_required', fresh=True)
    if previous is None:
        return result, row
    if (row['container_id'], row['generation']) != (previous['container_id'], previous['generation']):
        result.update(state='generation_changed', reason='reference_invalidated')
        return result, row
    old = previous['counters']
    dc, ds = u-number(old['total_usage']), s-number(old['system_cpu_usage'])
    if dc < 0 or ds <= 0 or n != number(old['online_cpus']):
        result.update(state='counter_reset', reason='regressive_or_invalid_delta_or_cpu_count_changed')
        return result, row
    if number(previous['call_end_seconds']) > a:
        result.update(state='invalid_interval', reason='overlapping_acquisition_brackets')
        return result, row
    with localcontext() as ctx:
        ctx.prec = 50
        cpu = dc/ds*n*100
        dt = stamp-read_epoch(previous['docker_read'])
    result.update(cpu_percent=str(cpu), state='valid', reason=None,
                  reference_sequence=previous['sequence'], observed_interval_seconds=str(dt),
                  interval_start_bounds=[previous['call_start_seconds'], previous['call_end_seconds']],
                  interval_end_bounds=[row['call_start_seconds'], row['call_end_seconds']])
    return result, row


def next_slot(scheduled, finished, interval):
    """No backlog: skip every opportunity strictly before the current time."""
    import math
    following = scheduled + interval
    missed = max(0, math.ceil((finished-following)/interval))
    return following + missed*interval, missed
