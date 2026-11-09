"""Read-only host observations and fail-closed energy checks. Never sets policies."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
SYS = Path('/sys')


class EnvironmentChanged(RuntimeError):
    pass


def command(args):
    return subprocess.check_output(args, text=True, timeout=3, cwd=ROOT).strip()


def read(path):
    return Path(path).read_text().strip()


def optional(path):
    try:
        return read(path)
    except (OSError, ValueError) as exc:
        return {'unavailable': type(exc).__name__}


def snapshot():
    """Policy values and instantaneous observations are deliberately separate."""
    policies = {}
    for p in sorted((SYS/'devices/system/cpu/cpufreq').glob('policy*')):
        policies[p.name] = {k: read(p/k) for k in (
            'affected_cpus', 'scaling_driver', 'scaling_governor',
            'energy_performance_preference', 'scaling_min_freq', 'scaling_max_freq')}
    if not policies:
        raise EnvironmentChanged('CPU policies unavailable')
    supplies = {}
    for p in (SYS/'class/power_supply').iterdir():
        kind = read(p/'type')
        if kind == 'Mains':
            supplies[p.name] = read(p/'online')
    if not supplies:
        raise EnvironmentChanged('External power cannot be verified')
    policy = dict(profile=command(['powerprofilesctl', 'get']),
        acpi_profile=read(SYS/'firmware/acpi/platform_profile'),
        external_power=supplies, policies=policies,
        boot_id=read('/proc/sys/kernel/random/boot_id'), kernel=os.uname().release,
        affinity=sorted(os.sched_getaffinity(0)),
        intel_pstate={k:read(SYS/'devices/system/cpu/intel_pstate'/k)
                      for k in ('status', 'min_perf_pct', 'max_perf_pct', 'no_turbo')})
    instantaneous = dict(
        suspend_offset_seconds=time.clock_gettime(time.CLOCK_BOOTTIME)-time.monotonic(),
        frequency_khz={p.name:optional(p/'scaling_cur_freq')
                       for p in (SYS/'devices/system/cpu/cpufreq').glob('policy*')},
        temperatures_millicelsius={p.name:optional(p/'temp')
                                  for p in (SYS/'class/thermal').glob('thermal_zone*')},
        battery={p.name:{k:optional(p/k) for k in ('status','capacity','power_now')}
                 for p in (SYS/'class/power_supply').iterdir()
                 if optional(p/'type') == 'Battery'},
        throttling={str(p.relative_to(SYS)):optional(p)
                    for p in (SYS/'devices/system/cpu').glob('cpu[0-9]*/thermal_throttle/*_throttle_count')})
    return dict(utc=datetime.now(timezone.utc).isoformat(), policy=policy,
                instantaneous=instantaneous,
                semantics='frequency is a driver snapshot, not measured workload mean frequency')


def validate(observation, reference=None):
    p = observation['policy']
    if p['profile'] != 'power-saver':
        raise EnvironmentChanged('Select power-saver manually; observed: '+p['profile'])
    if p['acpi_profile'] != 'low-power':
        raise EnvironmentChanged('Expected ACPI low-power; observed: '+p['acpi_profile'])
    if not p['external_power'] or any(v != '1' for v in p['external_power'].values()):
        raise EnvironmentChanged('External power absent or unverifiable')
    if reference is not None and p != reference['policy']:
        raise EnvironmentChanged('Frozen host policy/boot/affinity changed')
    if reference is not None:
        old=reference['instantaneous'].get('suspend_offset_seconds')
        new=observation['instantaneous'].get('suspend_offset_seconds')
        if old is not None and new is not None and abs(new-old)>.25:
            raise EnvironmentChanged('Suspend/resume detected by BOOTTIME versus MONOTONIC')
    return observation


def provenance():
    return dict(commit=command(['git','rev-parse','HEAD']),
                working_tree=command(['git','status','--short']))


def container_observations(client, images):
    """Read Docker inspect and host cgroups; no exec, probes or new containers."""
    values = []
    for c in client.containers.list():
        try:c.reload()
        except Exception as exc:
            # A normally cleaned container may disappear between list and inspect.
            if type(exc).__name__=='NotFound':continue
            raise
        attrs=c.attrs
        if attrs['State']['Status']!='running':continue
        if attrs['Image'] not in images.values():
            raise EnvironmentChanged('Unexpected active container: '+c.id)
        fields = {k:attrs['HostConfig'].get(k) for k in
                  ('NanoCpus','CpuQuota','CpuPeriod','CpusetCpus','Memory','PidsLimit','CgroupParent')}
        if any(fields[k] not in (0, '', None) for k in fields):
            raise EnvironmentChanged('Unexpected container limit: '+c.id)
        pid=attrs['State']['Pid']
        try:membership=read(f'/proc/{pid}/cgroup').split('::',1)[1]
        except FileNotFoundError:
            c.reload()
            if c.attrs['State']['Status']!='running':continue
            raise
        current=Path('/sys/fs/cgroup')/membership.lstrip('/')
        ancestors=[]
        while current.is_relative_to('/sys/fs/cgroup'):
            limits={k:read(current/k) for k in ('cpu.max','cpuset.cpus.effective','memory.max')
                    if (current/k).exists()}
            if limits.get('cpu.max', 'max 100000').split()[0] != 'max':
                raise EnvironmentChanged('Container/ancestor CPU quota changed: '+c.id)
            if limits.get('memory.max','max') != 'max':
                raise EnvironmentChanged('Container/ancestor memory limit changed: '+c.id)
            if limits.get('cpuset.cpus.effective','0-11') != '0-11':
                raise EnvironmentChanged('Container CPU set changed: '+c.id)
            ancestors.append(dict(path=str(current),limits=limits))
            if current==Path('/sys/fs/cgroup'):break
            current=current.parent
        values.append(dict(id=c.id,image=attrs['Image'],host_config=fields,ancestors=ancestors))
    return values
