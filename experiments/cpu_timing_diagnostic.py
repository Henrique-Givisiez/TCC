"""Explicit exploratory-only CPU timing activation; no Docker access at import."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil

from simulator.experiment_config import ExperimentConfig

CONFIG_ROOT = Path(__file__).parent/'configs/cpu_timing_d1'


@dataclass(frozen=True)
class TimingRequest:
    directory: Path
    configuration: str

    def bind(self, collector, experiment, operational):
        attempt = operational.report.get('attempt', {})
        if (experiment.to_json() != self.configuration
                or attempt.get('cpu_timing_exploratory') is not True
                or attempt.get('campaign_slot') is not False
                or attempt.get('scientific_pilot')):
            raise ValueError('CPU timing requires the explicit exploratory attempt')
        collector.bind_timing_diagnostics(self.directory/'collector.cpu-timing-diagnostic.json', max_records=512)


def prepare_request(experiment, directory, output, dataset, policy_path, images, composition, pilot):
    """Fail before Docker imports; never reuse raw/dataset/diagnostic directories."""
    expected = ExperimentConfig.load(CONFIG_ROOT/'f96_240.json').resolve_seed()
    if experiment.to_json() != expected.to_json():
        raise ValueError('CPU timing requires the dedicated F96 240-second configuration')
    if pilot or composition != 'combined' or policy_path is None:
        raise ValueError('CPU timing is exploratory combined only, never a scientific pilot')
    policy = json.loads(Path(policy_path).read_text())
    if policy != json.loads((CONFIG_ROOT/'policy.json').read_text()):
        raise ValueError('CPU timing requires the pinned protected operational policy')
    if images != json.loads((CONFIG_ROOT/'reference.json').read_text())['images']:
        raise ValueError('CPU timing requires the pinned F96 image IDs')
    directory, output, dataset = map(lambda p: Path(p).resolve(), (directory, output, dataset))
    attempt = output.with_name(output.name+'.attempt')
    paths = (directory, output, dataset, attempt)
    if any(a == b or a in b.parents or b in a.parents for i,a in enumerate(paths) for b in paths[i+1:]):
        raise ValueError('Diagnostic, raw, attempt and dataset directories must be disjoint')
    if any(p.exists() for p in paths):
        raise FileExistsError('All diagnostic run outputs must be new')
    existing = directory.parent
    while not existing.exists():
        existing = existing.parent
    if shutil.disk_usage(existing).free < policy['min_disk_bytes']:
        raise RuntimeError('Insufficient free disk for CPU timing diagnostic')
    directory.mkdir(parents=True, exist_ok=False)
    request = TimingRequest(directory, experiment.to_json())
    with (directory/'request.json').open('x') as stream:
        json.dump(dict(kind='exploratory_cpu_timing_request', campaign_slot=False,
                       configuration=json.loads(request.configuration), images=images,
                       configuration_sha256=hashlib.sha256(request.configuration.encode()).hexdigest(),
                       output=str(output), dataset=str(dataset)), stream, indent=2)
    return request


def bind_collector(collector, experiment, operational):
    request = getattr(operational, 'cpu_timing_request', None) if operational is not None else None
    if request is None:
        return
    if type(request) is not TimingRequest:
        raise ValueError('Invalid exploratory CPU timing request')
    request.bind(collector, experiment, operational)
