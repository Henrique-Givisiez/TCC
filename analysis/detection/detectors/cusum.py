"""Causal one-sided upper CUSUM of frozen-baseline residuals; no decisions."""
from decimal import Decimal, localcontext

from ..contracts import Component, ScoreValue
from ._moments import CONTEXT
from ._standardized import COMMON_CONFIG, StandardizedUpperTail

VERSION = '1'
K = Decimal('0.5')


def cusum_spec():
    """The only supported configuration: exact k=0.5, upper tail."""
    return Component('cusum', VERSION, dict(COMMON_CONFIG, k='0.5'), missing='preserve')


class CUSUM(StandardizedUpperTail):
    spec = staticmethod(cusum_spec)

    def update(self, observation, state):
        z = self.residual(observation, state)
        if z is None:
            return ScoreValue(None, 'missing_observation_reset')
        with localcontext(CONTEXT):
            state.value = max(Decimal(0), state.value + z - K)
        return ScoreValue(state.value)
