"""Sample coefficient of variation over L consecutive observations including x_t."""
from collections import deque
from dataclasses import dataclass
from decimal import Decimal, localcontext

from ..contracts import Component, ScoreValue
from ..inputs import ContractError
from ._moments import CONTEXT, PRECISION, decimal_ratio, sample_moments, standard_deviation

VERSION = '1'
FIXED_CONFIG = dict(ddof=1, includes_current=True, missing_policy='consecutive_valid_reset',
                    zero_mean='unavailable', definition='sigma/mean',
                    decimal_precision=PRECISION, rounding='ROUND_HALF_EVEN')


def cov_spec(*, lookback):
    if type(lookback) is not int or lookback < 2:
        raise ContractError('CoV lookback must be an explicit integer >=2 (ddof=1)')
    return Component('cov', VERSION, dict(FIXED_CONFIG, lookback=lookback), missing='preserve')


@dataclass
class _State:
    values: deque
    run_id: str | None = None
    last_index: int | None = None
    last_end: Decimal | None = None


class CoV:
    """No fit/static baseline. Sample sigma / arithmetic mean, with no abs/epsilon.

    O(L) arithmetic and O(L) memory per score, deliberately recomputed from the
    retained history to avoid sliding variance drift. Null resets the history.
    """
    def start_run(self, parameters, config):
        if parameters is not None:
            raise ContractError('Local CoV does not accept a static baseline')
        if 'lookback' not in config:
            raise ContractError('Explicit CoV lookback required')
        expected = cov_spec(lookback=config['lookback']).config
        if dict(config) != expected:
            raise ContractError('Unsupported CoV configuration; use cov_spec(lookback=...)')
        return _State(deque(maxlen=config['lookback']))

    def update(self, observation, state):
        if state.last_index is not None and (observation.run_id != state.run_id
                or observation.window_index != state.last_index + 1
                or observation.window_start_seconds != state.last_end):
            raise ContractError('CoV state requires consecutive windows of the same run')
        state.run_id = observation.run_id
        state.last_index = observation.window_index
        state.last_end = observation.window_end_seconds
        if observation.value is None:
            state.values.clear()
            return ScoreValue(None, 'missing_observation_reset')
        state.values.append(observation.value)
        if len(state.values) < state.values.maxlen:
            return ScoreValue(None, 'warmup_consecutive_valid')
        mean, variance = sample_moments(state.values)
        if mean == 0:
            return ScoreValue(None, 'zero_lookback_mean')
        with localcontext(CONTEXT):
            score = standard_deviation(variance) / decimal_ratio(mean)
        return ScoreValue(score)
