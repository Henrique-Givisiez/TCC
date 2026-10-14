"""Experimental parameters, independent of Docker access and output paths."""
from dataclasses import asdict, dataclass, field, fields, replace
import hashlib
import json
import math
import secrets
from typing import Optional


@dataclass(frozen=True)
class NormalTrafficConfig:
    clients: int = 4
    rate: float = 10
    endpoint: str = "/"
    # Compatibility only: reserved /light, /medium, /expensive ignore both.
    work_units: int = 10
    sleep_seconds: float = 0.0
    max_concurrent_sends: int = 64
    request_timeout_seconds: float = 2.0


@dataclass(frozen=True)
class BurstConfig:
    period_seconds: Optional[float] = None
    duration_seconds: Optional[float] = None
    jitter_seconds: Optional[float] = None


@dataclass(frozen=True)
class AttackConfig:
    enabled: bool = True
    profile: str = "continuous"
    attackers: int = 4
    rate: float = 10  # RPS per attacking entity, never an aggregate budget.
    start_seconds: float = 20
    duration_seconds: float = 140
    endpoint: str = "/"
    # Compatibility only: reserved /light, /medium, /expensive ignore both.
    work_units: int = 5000
    sleep_seconds: float = 0.0
    max_concurrent_sends: int = 64
    request_timeout_seconds: float = 2.0
    burst: Optional[BurstConfig] = None

    @property
    def end_seconds(self):
        return self.start_seconds + self.duration_seconds

    def validate_pattern(self):
        if self.profile not in ('continuous', 'periodic_burst'):
            raise ValueError('attack.profile must be continuous or periodic_burst')
        if self.burst is not None:
            for f in fields(self.burst):
                value = getattr(self.burst, f.name)
                if value is not None:
                    _number('attack.burst.' + f.name, value)
            if self.burst.jitter_seconds is not None:
                raise ValueError('attack.burst.jitter_seconds is not implemented')
        if self.profile == 'continuous':
            if self.burst is not None and any(getattr(self.burst, f.name) is not None for f in fields(self.burst)):
                raise ValueError('attack.burst requires profile=periodic_burst')
        else:
            for key in ('period_seconds', 'duration_seconds'):
                if self.burst is None or getattr(self.burst, key) is None:
                    raise ValueError('attack.burst.' + key + ' is required for periodic_burst')
                _number('attack.burst.' + key, getattr(self.burst, key), positive=True)
            if self.burst.duration_seconds > self.burst.period_seconds:
                raise ValueError('attack.burst.duration_seconds must be <= period_seconds')
        return self


@dataclass(frozen=True)
class InfrastructureConfig:
    initial_instances: int = 1
    min_instances: int = 1
    max_instances: int = 4
    cost_per_instance_per_hour: float = 0.02


@dataclass(frozen=True)
class AutoscalerConfig:
    enabled: bool = True
    scale_up_threshold: float = 60.0
    scale_down_threshold: float = 25.0
    cooldown_seconds: float = 20


@dataclass(frozen=True)
class ServerConfig:
    process_pool_workers: int = 2
    default_work_units: int = 1000000
    default_sleep_seconds: float = 0.0


@dataclass(frozen=True)
class MonitoringConfig:
    interval_seconds: float = 5
    stats_poll_interval_seconds: float = 1.0
    history_seconds: float = 30.0


@dataclass(frozen=True)
class LoadBalancerConfig:
    enabled: bool = False


@dataclass(frozen=True)
class TrafficSourcesConfig:
    execution: str = "host"


@dataclass(frozen=True)
class ExperimentConfig:
    id: str = "default"
    duration_seconds: float = 180
    seed: Optional[int] = None
    normal_traffic: NormalTrafficConfig = field(default_factory=NormalTrafficConfig)
    attack: AttackConfig = field(default_factory=AttackConfig)
    infrastructure: InfrastructureConfig = field(default_factory=InfrastructureConfig)
    autoscaler: AutoscalerConfig = field(default_factory=AutoscalerConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    load_balancer: LoadBalancerConfig = field(default_factory=LoadBalancerConfig)

    traffic_sources: TrafficSourcesConfig = field(default_factory=TrafficSourcesConfig)

    def validate(self):
        _validate_types(self, "experiment")
        if not self.id.strip():
            raise ValueError("id must not be empty")
        _number("duration_seconds", self.duration_seconds, positive=True)
        if self.seed is not None:
            _number("seed", self.seed)
        for name, group, count in [("normal_traffic", self.normal_traffic, "clients"),
                                   ("attack", self.attack, "attackers")]:
            for key in (count, "rate", "work_units", "sleep_seconds"):
                _number(name + "." + key, getattr(group, key))
            for key in ("max_concurrent_sends", "request_timeout_seconds"):
                _number(name + "." + key, getattr(group, key), positive=True)
            if not group.endpoint.startswith("/") or "?" in group.endpoint or "#" in group.endpoint:
                raise ValueError(name + ".endpoint must be a path starting with / without query or fragment")
        if self.traffic_sources.execution not in ("host", "containers"):
            raise ValueError("traffic_sources.execution must be host or containers")
        if self.traffic_sources.execution == "containers":
            if not self.load_balancer.enabled or self.autoscaler.enabled:
                raise ValueError("container sources require proxy enabled and autoscaler disabled")
            for name, count in (("normal_traffic", self.normal_traffic.clients), ("attack", self.attack.attackers)):
                if count > getattr(self, name).max_concurrent_sends:
                    raise ValueError(name + ": sources exceed aggregate send worker budget")
        a = self.attack
        a.validate_pattern()
        _number("attack.start_seconds", a.start_seconds)
        _number("attack.duration_seconds", a.duration_seconds)
        if a.enabled and (a.start_seconds >= self.duration_seconds or a.end_seconds > self.duration_seconds):
            raise ValueError("attack window must fit within experiment duration")
        i = self.infrastructure
        for key in ("min_instances", "initial_instances", "max_instances", "cost_per_instance_per_hour"):
            _number("infrastructure." + key, getattr(i, key))
        if not i.min_instances <= i.initial_instances <= i.max_instances or i.max_instances == 0:
            raise ValueError("require 0 <= min_instances <= initial_instances <= max_instances, max_instances > 0")
        ac = self.autoscaler
        if self.load_balancer.enabled:
            if ac.enabled:
                raise ValueError("load_balancer enabled requires autoscaler.enabled=false: dynamic upstream updates are not implemented")
            if i.initial_instances < 1:
                raise ValueError("load_balancer requires at least one victim")
        for key in ("scale_down_threshold", "scale_up_threshold", "cooldown_seconds"):
            _number("autoscaler." + key, getattr(ac, key))
        if ac.scale_down_threshold >= ac.scale_up_threshold:
            raise ValueError("scale_down_threshold must be lower than scale_up_threshold")
        _number("server.process_pool_workers", self.server.process_pool_workers, positive=True)
        _number("server.default_work_units", self.server.default_work_units)
        _number("server.default_sleep_seconds", self.server.default_sleep_seconds)
        for f in fields(self.monitoring):
            _number("monitoring." + f.name, getattr(self.monitoring, f.name), positive=True)
        if self.monitoring.history_seconds < self.monitoring.interval_seconds:
            raise ValueError("monitoring.history_seconds must cover interval_seconds")
        return self

    def resolve_seed(self):
        self.validate()
        return replace(self, seed=secrets.randbits(64)) if self.seed is None else self

    def to_json(self):
        self.validate()
        return json.dumps(asdict(self), indent=2, allow_nan=False) + "\n"

    @classmethod
    def from_dict(cls, data):
        return _construct(cls, data, "experiment").validate()

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as stream:
            return cls.from_dict(json.load(stream, object_pairs_hook=_unique_object))


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate configuration key: " + key)
        result[key] = value
    return result


def _number(name, value, positive=False):
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(name + (" must be finite and > 0" if positive else " must be finite and >= 0"))


def _validate_types(obj, path):
    for f in fields(obj):
        value = getattr(obj, f.name)
        expected = f.type
        name = path + "." + f.name
        if hasattr(value, "__dataclass_fields__"):
            if expected not in (type(value), Optional[type(value)]):
                raise ValueError(name + " has wrong group type")
            _validate_types(value, name)
        elif expected in (float, Optional[float]):
            if value is None and expected == Optional[float]:
                continue
            if type(value) not in (int, float):
                raise ValueError(name + " must be a number")
        elif expected in (int, Optional[int]):
            if value is None and expected == Optional[int]:
                continue
            if type(value) is not int:
                raise ValueError(name + " must be an integer")
        elif expected == Optional[BurstConfig] and value is None:
            continue
        elif type(value) is not expected:
            raise ValueError(name + " has invalid type")


def _construct(cls, data, path):
    if not isinstance(data, dict):
        raise ValueError(path + " must be an object")
    known = {f.name: f for f in fields(cls)}
    unknown = set(data) - set(known)
    if unknown:
        raise ValueError(path + ": unknown fields: " + ", ".join(sorted(unknown)))
    values = dict(data)
    for name, value in data.items():
        target = known[name].type
        if target == Optional[BurstConfig]:
            target = BurstConfig
            if value is None:
                continue
        if hasattr(target, "__dataclass_fields__"):
            values[name] = _construct(target, value, path + "." + name)
    return cls(**values)


def worker_seed(seed, component, index):
    """Stable independent RNG streams; never depends on thread scheduling/hash()."""
    digest = hashlib.sha256((str(seed) + ":" + component + ":" + str(index)).encode()).digest()
    return int.from_bytes(digest, "big")
