"""Plot independent proxy observations from a completed or incomplete run."""
import argparse
import csv
import json
from pathlib import Path


def observation_series(rows, source, field, scale=1):
    """Use source acquisition starts; keep unavailable values as gaps."""
    xs, ys = [], []
    for row in rows:
        observation = row[source]
        value = (observation.get('data') or {}).get(field) if observation['success'] else None
        xs.append(observation['elapsed_seconds'])
        ys.append(float('nan') if value is None else value / scale)
    return xs, ys


def plot(run, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    run = Path(run)
    rows = [json.loads(line) for line in (run/'proxy_artifacts/monitor_samples.jsonl').read_text().splitlines()]
    fig, axes = plt.subplots(3, 1, sharex=True, figsize=(9, 7))
    for ax, source, field, scale, label in zip(axes, ['docker', 'docker', 'status'],
            ['cpu_percent', 'memory_usage_bytes', 'active_connections'], [1, 1024**2, 1],
            ['CPU Docker (%)\ninterval ending at point', 'Memory usage (MiB)', 'Active connections']):
        xs, ys = observation_series(rows, source, field, scale)
        # Points avoid interpolation through failures, missed slots, or CPU intervals.
        ax.plot(xs, ys, marker='.', linestyle='None')
        ax.set_ylabel(label)
        ax.grid(alpha=.25)
        with (run/'attack_events.csv').open() as stream:
            for event in csv.DictReader(stream):
                start, end = event.get('actual_start_seconds'), event.get('actual_end_seconds')
                if start and end:
                    ax.axvspan(float(start), float(end), color='red', alpha=.15)
    axes[-1].set_xlabel('Experiment elapsed (s); red = actual attack admission interval')
    fig.suptitle(run.name)
    fig.tight_layout()
    fig.savefig(output, dpi=140)
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    plot(args.run, args.output)
