"""CUSUM freeze v1: one transition owns both candidate score and fixed-h decision.

No files, fitting, calibration, traffic metadata or ground truth are accepted.
This is deliberately not the legacy Detector.update -> ScoreValue interface.
"""
from dataclasses import dataclass
from decimal import Decimal, localcontext
from types import MappingProxyType

from ..contracts import Component, DecisionRecord, Observation, PolicyScore
from ..inputs import ContractError, number
from ._moments import CONTEXT
from ._standardized import COMMON_CONFIG
from .zscore import ZScore, zscore_spec

VERSION = '1'
K = Decimal('0.5')


def threshold_text(h):
    # Exact explicit inputs only; floats would silently encode another threshold.
    if type(h) not in (str, Decimal, int):
        raise ContractError('h requires exact decimal text, Decimal or integer')
    value = number(h)
    if value < 0:
        raise ContractError('h must be finite and nonnegative')
    if value == 0:
        return '0'
    text = format(value, 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def freeze_spec(*, h):
    return Component('cusum-freeze', VERSION, MappingProxyType(dict(COMMON_CONFIG,
        k='0.5', h=threshold_text(h), comparison='>', ties='accept_no_alarm',
        publication='candidate', rejected_update='preserve_previous_state',
        decision_binding='same_h_as_transition')), missing='preserve')


@dataclass(frozen=True)
class FreezeState:
    normalization: object
    h: Decimal
    value: Decimal = Decimal(0)
    run_id: str | None = None
    last_index: int | None = None
    last_end: Decimal | None = None


@dataclass(frozen=True)
class FreezeTransition:
    observation: Observation
    previous_state: Decimal
    residual: Decimal | None
    candidate: Decimal | None
    update_accepted: bool | None
    posterior_state: Decimal
    score: PolicyScore
    decision: DecisionRecord
    next_state: FreezeState


@dataclass(frozen=True, init=False)
class CUSUMFreeze:
    h: Decimal

    def __init__(self, *, h):
        object.__setattr__(self, 'h', Decimal(threshold_text(h)))

    def spec(self):
        return freeze_spec(h=self.h)

    def start_run(self, parameters):
        normalization = ZScore().start_run(parameters, zscore_spec().config)
        return FreezeState(normalization, self.h)

    def step(self, observation, state):
        if type(observation) is not Observation or type(state) is not FreezeState or state.h != self.h:
            raise ContractError('Expected typed observation and state bound to the same h')
        if (not observation.run_id or type(observation.window_index) is not int
                or observation.window_index < 0
                or type(observation.window_start_seconds) is not Decimal
                or type(observation.window_end_seconds) is not Decimal):
            raise ContractError('Invalid observation identity/bounds')
        start, end = number(observation.window_start_seconds), number(observation.window_end_seconds)
        if start < 0 or end <= start:
            raise ContractError('Invalid observation interval')
        if state.last_index is None:
            if observation.window_index != 0 or start != 0:
                raise ContractError('New run requires index zero and origin zero')
        elif (observation.run_id != state.run_id or observation.window_index != state.last_index + 1
              or start != state.last_end):
            raise ContractError('Freeze state requires consecutive windows of the same run')
        if state.value < 0 or state.value > self.h:
            raise ContractError('Stored state must lie in [0,h]')
        z = ZScore().update(observation, state.normalization).score
        if z is None:
            candidate, accepted, decision, posterior = None, None, None, Decimal(0)
            reason = 'missing_observation_reset'
        else:
            with localcontext(CONTEXT):
                candidate = max(Decimal(0), state.value + z - K)
            decision = candidate > self.h
            accepted = not decision
            posterior = candidate if accepted else state.value
            reason = None
        # Temporal metadata advances even when numerical update is rejected/reset.
        next_state = FreezeState(state.normalization, self.h, posterior, observation.run_id,
                                 observation.window_index, end)
        score = PolicyScore(observation.run_id, observation.window_index, start, end,
                            candidate, candidate is not None, reason, end)
        record = DecisionRecord(score, decision, reason, end)
        return FreezeTransition(observation, state.value, z, candidate, accepted,
                                posterior, score, record, next_state)
