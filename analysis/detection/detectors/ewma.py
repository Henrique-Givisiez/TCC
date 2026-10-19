"""Causal signed EWMA of frozen-baseline standardized residuals; no decisions."""
from decimal import Decimal, localcontext

from ..contracts import Component, ScoreValue
from ._moments import CONTEXT
from ._standardized import COMMON_CONFIG, StandardizedUpperTail

VERSION = '1'
LAMBDA = Decimal('0.2')


def ewma_spec():
    """The only supported configuration: exact lambda=0.2, upper tail."""
    return Component('ewma', VERSION, dict(COMMON_CONFIG, **{'lambda': '0.2'}),
                     missing='preserve')


class EWMA(StandardizedUpperTail):
    spec = staticmethod(ewma_spec)

    def update(self, observation, state):
        z = self.residual(observation, state)
        if z is None:
            return ScoreValue(None, 'missing_observation_reset')
        with localcontext(CONTEXT):
            state.value = LAMBDA * z + (Decimal(1) - LAMBDA) * state.value
        return ScoreValue(state.value)
