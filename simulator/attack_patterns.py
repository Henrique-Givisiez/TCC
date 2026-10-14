"""Deterministic windows on the experiment clock; no HTTP, RNG or victim data."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ContinuousFlood:
    start_seconds: float
    end_seconds: float

    def next_window(self, elapsed):
        if elapsed >= self.end_seconds:
            return None
        return self.start_seconds, self.end_seconds

    def allows(self, elapsed):
        window = self.next_window(elapsed)
        return window is not None and window[0] <= elapsed < window[1]


@dataclass(frozen=True)
class PeriodicBurst(ContinuousFlood):
    period_seconds: float
    burst_duration_seconds: float

    def next_window(self, elapsed):
        if elapsed >= self.end_seconds:
            return None
        index = max(0, math.floor((elapsed - self.start_seconds) / self.period_seconds))
        start = self.start_seconds + index * self.period_seconds
        if elapsed >= start + self.burst_duration_seconds:
            start += self.period_seconds
        if start >= self.end_seconds:
            return None
        return start, min(start + self.burst_duration_seconds, self.end_seconds)


def attack_pattern(settings):
    settings.validate_pattern()
    if settings.profile == 'continuous':
        return ContinuousFlood(settings.start_seconds, settings.end_seconds)
    return PeriodicBurst(settings.start_seconds, settings.end_seconds,
                         settings.burst.period_seconds, settings.burst.duration_seconds)
