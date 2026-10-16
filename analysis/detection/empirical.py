"""Versioned, label-free empirical upper-tail calibration and strict decisions.

Use through pipeline.calibrate/decide: those gates verify artifact lineage,
CALIBRATION roles, compatible detector/feature/model and campaign membership.
Callbacks receive only typed scores and verified run/seed metadata, never files.
"""
from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction

from .contracts import CalibrationScores, Component, DecisionValue, PolicyScore
from .inputs import ContractError, number

VERSION = '1'
FIXED = dict(direction='upper-tail', quantile='empirical_higher',
             index='ceil((N-1)*(1-alpha))', index_base=0, comparison='>',
             ties='negative', confirmation='none', hysteresis='none',
             unavailable='exclude_and_count', fpr='nominal_benign_window_target',
             reporting_precision=50, rounding='ROUND_HALF_EVEN')
CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN)


def exact_alpha(value):
    """No binary floating point: decimal text/Decimal or exact Fraction only."""
    if isinstance(value, Fraction):
        result = value
    elif isinstance(value, (str, Decimal)):
        decimal = number(value)
        result = Fraction(decimal)
    else:
        raise ContractError('alpha requires exact decimal text, Decimal or Fraction')
    if not 0 < result < 1:
        raise ContractError('alpha must satisfy 0 < alpha < 1')
    return result


def upper_tail_spec(*, alpha):
    value = exact_alpha(alpha)
    return Component('empirical-upper-tail', VERSION,
                     dict(FIXED, alpha=dict(numerator=str(value.numerator),
                                            denominator=str(value.denominator))),
                     missing='preserve')


def validate_config(config):
    try:
        pair = config['alpha']
        if (set(pair) != {'numerator', 'denominator'}
                or any(not isinstance(pair[k], str) for k in pair)
                or int(pair['denominator']) <= 0):
            raise ValueError('Invalid rational alpha')
        alpha = exact_alpha(Fraction(int(pair['numerator']), int(pair['denominator'])))
        if dict(config) != dict(upper_tail_spec(alpha=alpha).config):
            raise ValueError('Noncanonical or unsupported configuration')
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise ContractError('Invalid empirical upper-tail configuration') from exc
    return alpha


def quantile_index(n, alpha):
    if type(n) is not int or n < 1:
        raise ContractError('No available calibration scores: N must be >= 1')
    alpha = exact_alpha(alpha)
    position = (n - 1) * (1 - alpha)
    return (position.numerator + position.denominator - 1) // position.denominator


def ratio(above, valid):
    if valid == 0:
        return None
    with localcontext(CONTEXT):
        return Decimal(above) / Decimal(valid)


def checked_score(record):
    if type(record) is not PolicyScore:
        raise ContractError('Expected label-free PolicyScore')
    if (not isinstance(record.run_id, str) or not record.run_id
            or type(record.window_index) is not int or record.window_index < 0
            or type(record.score_available) is not bool):
        raise ContractError('Invalid score identity/availability')
    start, end, at = map(number, (record.window_start_seconds,
                                 record.window_end_seconds, record.available_at_seconds))
    if start < 0 or end <= start or at < end:
        raise ContractError('Score availability precedes observation closure')
    if record.score_available:
        if (not isinstance(record.score, Decimal) or not record.score.is_finite()
                or record.reason is not None):
            raise ContractError('Invalid available score')
    elif record.score is not None or not isinstance(record.reason, str) or not record.reason:
        raise ContractError('Unavailable score requires None and reason')
    return record.score


class EmpiricalUpperTail:
    """One pooled threshold; realized FPR is descriptive, never a tuning loop."""
    def calibrate(self, scores, config):
        alpha = validate_config(config)
        if not scores or any(type(run) is not CalibrationScores for run in scores):
            raise ContractError('Expected label-free CalibrationScores runs')
        if any(not isinstance(run.run_id, str) or not run.run_id for run in scores):
            raise ContractError('Invalid run ID')
        if len({run.run_id for run in scores}) != len(scores):
            raise ContractError('Duplicate calibration run')
        seeds = [run.seed for run in scores if run.seed is not None]
        if any(type(seed) is not int or seed < 0 for seed in seeds) or len(set(seeds)) != len(seeds):
            raise ContractError('Invalid or duplicate campaign seed')
        pools = []
        for run in sorted(scores, key=lambda r: r.run_id):
            if not isinstance(run.run_id, str) or not run.run_id:
                raise ContractError('Invalid run ID')
            values, previous = [], None
            for record in run.records:
                value = checked_score(record)
                if record.run_id != run.run_id:
                    raise ContractError('Mixed run IDs')
                if previous is not None and (record.window_index <= previous.window_index
                        or number(record.window_start_seconds) < number(previous.window_end_seconds)
                        or number(record.available_at_seconds) < number(previous.available_at_seconds)):
                    raise ContractError('Unordered/overlapping calibration windows')
                if value is not None:
                    values.append(value)
                previous = record
            pools.append((run, values))
        ordered = sorted(value for _, values in pools for value in values)
        n = len(ordered)
        j = quantile_index(n, alpha)
        threshold = ordered[j]
        support = []
        for run, values in pools:
            above = sum(v > threshold for v in values)
            equal = sum(v == threshold for v in values)
            support.append(dict(run_id=run.run_id, seed=run.seed,
                candidate_windows=len(run.records), valid_scores=len(values),
                unavailable_scores=len(run.records)-len(values),
                scores_below=len(values)-above-equal, scores_equal=equal, scores_above=above,
                realized_run_fpr=ratio(above, len(values)),
                realized_run_fpr_exact=dict(numerator=above, denominator=len(values)) if values else None))
        above = sum(s['scores_above'] for s in support)
        equal = sum(s['scores_equal'] for s in support)
        return dict(policy_version=VERSION, config=dict(config), n_valid=n,
            n_candidate=sum(s['candidate_windows'] for s in support),
            n_unavailable=sum(s['unavailable_scores'] for s in support),
            quantile_index_zero_based=j, threshold=threshold,
            scores_below=n-above-equal, scores_equal=equal, scores_above=above,
            realized_calibration_fpr=ratio(above, n),
            realized_calibration_fpr_exact=dict(numerator=above, denominator=n),
            support_by_run=support,
            interpretation='Nominal benign window-level target; order statistic/ties may yield lower FPR; no post-hoc adjustment')


@dataclass(frozen=True)
class _Threshold:
    value: Decimal


class StrictUpperTail:
    """Immutable threshold, no temporal state; ties negative, missing unavailable."""
    def start_run(self, parameters, config):
        alpha = validate_config(config)
        try:
            if parameters['policy_version'] != VERSION or parameters['config'] != dict(config):
                raise ContractError('Threshold policy/configuration mismatch')
            n = parameters['n_valid']
            if (type(parameters['quantile_index_zero_based']) is not int
                    or parameters['quantile_index_zero_based'] != quantile_index(n, alpha)):
                raise ContractError('Threshold order statistic mismatch')
            counts = [parameters[k] for k in ('scores_below', 'scores_equal', 'scores_above')]
            if any(type(c) is not int or c < 0 for c in counts) or sum(counts) != n or counts[1] < 1:
                raise ContractError('Invalid calibration counts')
            threshold = parameters['threshold']
            if not isinstance(threshold, (str, Decimal)):
                raise ContractError('Threshold requires exact Decimal representation')
            return _Threshold(number(threshold))
        except (KeyError, TypeError) as exc:
            raise ContractError('Malformed calibrated threshold') from exc

    def decide(self, score, state):
        value = checked_score(score)
        if type(state) is not _Threshold:
            raise ContractError('Expected immutable calibrated threshold')
        if value is None:
            return DecisionValue(None, score.reason, score.available_at_seconds)
        return DecisionValue(value > state.value, None, score.available_at_seconds)
