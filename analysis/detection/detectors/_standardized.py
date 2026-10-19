"""Shared state and baseline contract for the two standardized upper-tail scores."""
from dataclasses import dataclass
from decimal import Decimal

from ..inputs import ContractError
from ._moments import PRECISION
from .zscore import ZScore, zscore_spec

FEATURES = frozenset({
    ('network', 'ingress_packet_count'),
    ('network', 'ingress_tcp_payload_length_sum_bytes'),
    ('service', 'request_starts'),
    ('service', 'mean_duration_ms'),
    ('infrastructure', 'mean_cpu_percent'),
})

COMMON_CONFIG = dict(normalization='frozen_zscore_baseline', direction='upper-tail',
                     initial_state='0', missing_policy='unavailable_reset_zero',
                     decimal_precision=PRECISION, rounding='ROUND_HALF_EVEN')


@dataclass
class _State:
    normalization: object
    value: Decimal = Decimal(0)
    run_id: str | None = None
    last_index: int | None = None
    last_end: Decimal | None = None


class StandardizedUpperTail:
    """No fitter: normalization delegates only to the frozen Z-score reader.

    baseline_spec is an explicit pipeline capability, not a different fit. It
    validates detector identity and the five-feature scope before any scoring.
    """
    def baseline_spec(self, spec, feature):
        if spec != self.spec():
            raise ContractError('Unsupported standardized detector component/configuration')
        if (feature['family'], feature['feature']) not in FEATURES:
            raise ContractError('Standardized detector requires one of the five frozen features')
        return zscore_spec()

    def start_run(self, parameters, config):
        if dict(config) != dict(self.spec().config):
            raise ContractError('Unsupported standardized detector configuration')
        # ZScore.start_run validates the persisted exact moments and sigma. Its
        # fit method is never invoked, and parameters are never modified.
        return _State(ZScore().start_run(parameters, zscore_spec().config))

    def residual(self, observation, state):
        if state.last_index is not None and (
                observation.run_id != state.run_id
                or observation.window_index != state.last_index + 1
                or observation.window_start_seconds != state.last_end):
            raise ContractError('Standardized detector state requires consecutive windows of the same run')
        state.run_id = observation.run_id
        state.last_index = observation.window_index
        state.last_end = observation.window_end_seconds
        result = ZScore().update(observation, state.normalization)
        if result.score is None:
            state.value = Decimal(0)
        return result.score
