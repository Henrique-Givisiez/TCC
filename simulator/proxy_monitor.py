"""Independent, append-only proxy observations; never feeds victim metrics."""
import json
import math
import re
import threading
import time

import docker

from simulator import config

FIELDS = ('active_connections', 'accepted_connections_total', 'handled_connections_total',
          'requests_total', 'reading_connections', 'writing_connections', 'waiting_connections')


def parse_status(body):
    match = re.fullmatch(r'Active connections:\s*(\d+)\s+server accepts handled requests\s+'
                         r'(\d+)\s+(\d+)\s+(\d+)\s+Reading:\s*(\d+)\s+Writing:\s*(\d+)\s+Waiting:\s*(\d+)\s*', body)
    if not match:
        raise ValueError('invalid stub_status response')
    return dict(zip(FIELDS, map(int, match.groups())))


def resources(stats, previous=None, elapsed=None):
    """Raw memory usage, Docker CPU convention, per-interface counters/rates."""
    result = dict(cpu_percent=None, memory_usage_bytes=stats.get('memory_stats', {}).get('usage'),
                  docker_read=stats.get('read'), interfaces={}, delta_state='first_read')
    if previous is not None:
        old, old_elapsed = previous
        dt = elapsed - old_elapsed
        result['observed_interval_seconds'] = dt
        result['delta_state'] = 'valid' if dt > 0 else 'invalid_interval'
        try:
            current_cpu, old_cpu = stats['cpu_stats'], old['cpu_stats']
            dc = current_cpu['cpu_usage']['total_usage'] - old_cpu['cpu_usage']['total_usage']
            ds = current_cpu['system_cpu_usage'] - old_cpu['system_cpu_usage']
            n = current_cpu.get('online_cpus') or len(current_cpu['cpu_usage']['percpu_usage'])
            if dt > 0 and ds > 0 and dc >= 0:
                result['cpu_percent'] = dc / ds * n * 100
            else:
                result['delta_state'] = 'reset_or_invalid_cpu_delta'
        except (KeyError, TypeError):
            result['delta_state'] = 'missing_cpu_counters'
    for interface, counters in stats.get('networks', {}).items():
        row = {key: counters.get(key) for key in ('rx_bytes', 'tx_bytes')}
        row.update(rx_bytes_per_second=None, tx_bytes_per_second=None, delta_state='first_read')
        if previous is not None:
            before = previous[0].get('networks', {}).get(interface, {})
            dt = elapsed - previous[1]
            for direction in ('rx', 'tx'):
                key = direction + '_bytes'
                a, b = counters.get(key), before.get(key)
                if dt > 0 and a is not None and b is not None and a >= b:
                    row[key + '_per_second'] = (a - b) / dt
                else:
                    row['delta_state'] = 'reset_missing_or_invalid_delta'
            if all(row[k + '_bytes_per_second'] is not None for k in ('rx', 'tx')):
                row['delta_state'] = 'valid'
        result['interfaces'][interface] = row
    return result


class ProxyMonitor:
    def __init__(self, proxy, clock, interval=None):
        self.proxy, self.clock = proxy, clock
        self.interval = config.PROXY_POLL_INTERVAL_SECONDS if interval is None else interval
        if not math.isfinite(self.interval) or self.interval <= 0:
            raise ValueError('proxy poll interval must be positive and finite')
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, name='ProxyMonitor', daemon=True)
        self.previous = None
        self.attempts = 0
        self.client = None
        self.source_errors = {"status": 0, "docker": 0}

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=2 * config.PROXY_COLLECTION_TIMEOUT_SECONDS + 2)
        self.summary(thread_alive=self.thread.is_alive())

    def summary(self, **extra):
        path = self.proxy.directory / 'monitor_summary.json'
        existing = json.loads(path.read_text()) if path.exists() else {}
        value = dict(existing, schema_version=1, run_id=self.proxy.run_id, container_id=self.proxy.expected_id,
                     monitoring_queries_attempted=self.attempts, source_errors=self.source_errors, **extra)
        path.write_text(json.dumps(value, indent=2) + '\n')

    def sample(self, scheduled):
        timestamp, elapsed = self.clock.sample()
        begin = time.monotonic()
        row = dict(schema_version=1, run_id=self.proxy.run_id, container_id=self.proxy.expected_id,
                   timestamp=timestamp, elapsed_seconds=elapsed, scheduled_elapsed_seconds=scheduled,
                   delay_seconds=max(0, elapsed-scheduled), monitoring_query_sequence=self.attempts+1)
        for source in ('status', 'docker'):
            started = time.monotonic()
            observed_timestamp, observed_elapsed = self.clock.sample()
            observation = dict(timestamp=observed_timestamp, elapsed_seconds=observed_elapsed,
                               success=False, error=None, data=None)
            try:
                if source == 'status':
                    self.attempts += 1
                    container = self.client.containers.get(self.proxy.expected_id)
                    response = container.exec_run(['wget', '-T', '1', '-qO-',
                        '--header=X-Edos-Phase: monitoring', 'http://127.0.0.1:8081/nginx_status'])
                    if response.exit_code != 0:
                        raise RuntimeError('status exec exit=' + str(response.exit_code))
                    observation['data'] = parse_status(response.output.decode())
                else:
                    stats = self.client.api.stats(self.proxy.expected_id, stream=False, one_shot=True)
                    if self.previous is not None and stats.get('read') == self.previous[0].get('read'):
                        raise ValueError('stale Docker read timestamp')
                    observation['data'] = resources(stats, self.previous, observed_elapsed)
                    self.previous = (stats, observed_elapsed)
                observation['success'] = True
            except Exception as exc:
                self.source_errors[source] += 1
                observation['error'] = type(exc).__name__ + ': ' + str(exc)
            observation['duration_seconds'] = time.monotonic() - started
            row[source] = observation
        row['collection_duration_seconds'] = time.monotonic() - begin
        return row

    def run(self):
        path = self.proxy.directory / 'monitor_samples.jsonl'
        try:
            self.client = docker.DockerClient(base_url=config.DOCKER_ENGINE_SOCKET,
                                              timeout=config.PROXY_COLLECTION_TIMEOUT_SECONDS)
            with path.open('x', buffering=1) as output:
                scheduled = self.clock.elapsed()
                while not self.stop_event.is_set():
                    row = self.sample(scheduled)
                    output.write(json.dumps(row, allow_nan=False) + '\n')
                    scheduled += self.interval
                    # Skip missed slots, exposing their number on the next observation.
                    missed = max(0, math.floor((self.clock.elapsed()-scheduled)/self.interval))
                    scheduled += missed*self.interval
                    self.stop_event.wait(max(0, scheduled-self.clock.elapsed()))
        except Exception as exc:
            self.summary(fatal_error=type(exc).__name__ + ': ' + str(exc))
        finally:
            if self.client is not None:
                self.client.close()
