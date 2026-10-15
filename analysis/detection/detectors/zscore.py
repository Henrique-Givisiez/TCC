"""Signed Z-score against an independently designated normal baseline. No decisions."""
from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction

from ..contracts import Component, ScoreValue
from ..inputs import ContractError, number
from ._moments import (CONTEXT, PRECISION, decimal_ratio, finite_fraction,
                       fraction_record, read_fraction, sample_moments, standard_deviation)

VERSION = '1'
CONFIG = dict(ddof=1, baseline_missing='exclude_and_count',
              score_missing='unavailable', zero_sigma='reject_baseline',
              weighting='equal_observations_across_runs',
              decimal_precision=PRECISION, rounding='ROUND_HALF_EVEN')


def zscore_spec():
    return Component('zscore', VERSION, dict(CONFIG), missing='preserve')


def validate_config(config):
    if dict(config) != CONFIG:
        raise ContractError('Unsupported Z-score configuration; use zscore_spec()')


@dataclass(frozen=True)
class _State:
    mean: Fraction
    sigma: Decimal


class ZScore:
    """Both Fitter and Detector contracts; fit never receives ground truth.

    Null baseline values are excluded explicitly and counted. Constant/insufficient
    baselines are rejected, not patched with epsilon. Scoring is stateless per run.
    """
    def fit(self, series, config):
        validate_config(config)
        if not series:
            raise ContractError('Baseline series required')
        key = lambda s: (s.family, s.feature, s.window_size_seconds, s.feature_schema_version)
        if any(key(s) != key(series[0]) for s in series):
            raise ContractError('Baseline feature/window mismatch')
        if len({s.run_id for s in series}) != len(series):
            raise ContractError('Duplicate baseline run')
        values, support = [], []
        for s in series:
            valid = [o.value for o in s.observations if o.value is not None]
            values.extend(valid)
            support.append(dict(run_id=s.run_id, n_valid=len(valid),
                                n_missing=len(s.observations) - len(valid)))
        mean, variance = sample_moments(values)
        if variance == 0:
            raise ContractError('zero_baseline_sigma: constant baseline cannot define Z-score')
        return dict(mu=decimal_ratio(mean), sigma=standard_deviation(variance),
                    mean_exact=fraction_record(mean), variance_exact=fraction_record(variance),
                    n_valid=len(values), n_missing=sum(s['n_missing'] for s in support),
                    support_by_run=support, ddof=1, config=dict(CONFIG))

    def start_run(self, parameters, config):
        validate_config(config)
        if parameters is None:
            raise ContractError('Z-score requires a fitted baseline artifact')
        try:
            if (parameters['config'] != CONFIG or parameters['ddof'] != 1
                    or type(parameters['n_valid']) is not int or parameters['n_valid'] < 2):
                raise ContractError('Invalid baseline convention/support')
            mean = read_fraction(parameters['mean_exact'])
            variance = read_fraction(parameters['variance_exact'])
            sigma = number(parameters['sigma'])
            if variance <= 0 or sigma <= 0:
                raise ContractError('zero_or_invalid_baseline_sigma')
            if (number(parameters['mu']) != decimal_ratio(mean)
                    or sigma != standard_deviation(variance)):
                raise ContractError('Baseline moment parameters disagree')
        except (KeyError, TypeError) as exc:
            raise ContractError('Malformed Z-score baseline parameters') from exc
        return _State(mean, sigma)

    def update(self, observation, state):
        if observation.value is None:
            return ScoreValue(None, 'missing_observation')
        # Subtract the exact learned mean before rounding: preserves tiny changes
        # about a large offset. sigma and the final score are 50-digit decimals.
        with localcontext(CONTEXT):
            score = decimal_ratio(finite_fraction(observation.value) - state.mean) / state.sigma
        return ScoreValue(score)
