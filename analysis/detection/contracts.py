"""Small callback contracts. Ground truth is deliberately absent from this module."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class Component:
    name: str
    version: str
    config: Mapping[str, Any]
    # Preserve requires the implementation to handle None and gaps explicitly.
    missing: str = 'reject'


@dataclass(frozen=True)
class Observation:
    run_id: str
    window_index: int
    window_start_seconds: Decimal
    window_end_seconds: Decimal
    value: Decimal | None


@dataclass(frozen=True)
class ObservedSeries:
    run_id: str
    family: str
    feature: str
    window_size_seconds: Decimal
    feature_schema_version: int
    observations: tuple[Observation, ...]


@dataclass(frozen=True)
class ScoreValue:
    score: Decimal | None
    reason: str | None = None
    # None means simulated availability at window closure, not measured latency.
    available_at_seconds: Decimal | None = None


@dataclass(frozen=True)
class ScoreRecord:
    observation: Observation
    score: Decimal | None
    score_available: bool
    reason: str | None
    available_at_seconds: Decimal


@dataclass(frozen=True)
class CalibrationScores:
    """Only scores and alignment keys; no feature values, paths or labels."""
    run_id: str
    records: tuple['PolicyScore', ...]


@dataclass(frozen=True)
class PolicyScore:
    run_id: str
    window_index: int
    window_start_seconds: Decimal
    window_end_seconds: Decimal
    score: Decimal | None
    score_available: bool
    reason: str | None
    available_at_seconds: Decimal


@dataclass(frozen=True)
class DecisionValue:
    decision: bool | None
    reason: str | None = None
    available_at_seconds: Decimal | None = None


@dataclass(frozen=True)
class DecisionRecord:
    score: PolicyScore
    decision: bool | None
    reason: str | None
    available_at_seconds: Decimal


class Fitter(Protocol):
    def fit(self, series: tuple[ObservedSeries, ...], config: Mapping) -> Mapping: ...


class Detector(Protocol):
    def start_run(self, parameters: Mapping | None, config: Mapping) -> Any: ...
    def update(self, observation: Observation, state: Any) -> ScoreValue: ...


class Calibrator(Protocol):
    def calibrate(self, scores: tuple[CalibrationScores, ...], config: Mapping) -> Mapping: ...


class DecisionPolicy(Protocol):
    def start_run(self, parameters: Mapping, config: Mapping) -> Any: ...
    def decide(self, score: PolicyScore, state: Any) -> DecisionValue: ...
