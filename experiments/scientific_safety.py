"""Fail-closed operational guards; no Docker access."""
from pathlib import Path
import shutil
from analysis.detection.inputs import ContractError, read_json


def require_storage(path, additional_bytes=0):
    ancestor = Path(path).resolve()
    while not ancestor.exists():
        ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < 4*1024**3 + additional_bytes:
        raise ContractError('Storage reserve insufficient; preserve artifacts and diagnose')


def require_release(spec):
    if spec.get('execution_release', {}).get('allowed') is not True:
        raise ContractError('Scientific execution is not released')


def confirmed_capture_loss(raw, status, returncode):
    """Recognize only the normal capture-integrity failure with proven closure.

    Unknown exits, mixed errors, incomplete statistics or contradictory sidecars
    remain execution failures. Backend cleanup is checked by recover first.
    """
    from simulator.capture_lifecycle import parse_capture_counters
    if (returncode != 1 or status.get('status') != 'incomplete'
            or status.get('end_reason') != 'simulation_end'
            or status.get('producers_drained') is not True):
        return False
    errors = status.get('errors', [])
    prefixes = ('capture: ', 'raw_capture: ',
                "cleanup verification: {'component': 'capture',",
                "cleanup verification: {'component': 'raw_capture',")
    if not errors or any(not isinstance(e,str) or not e.startswith(prefixes)
                         or 'capture failed: returncode=' not in e or 'counters=' not in e for e in errors):
        return False
    summary = read_json(raw/'victim_stats.summary.json')
    if (summary.get('worker_finished') is not True or summary.get('fatal_error') is not None
            or summary.get('run_id') != status.get('run_id')):
        return False
    lost = False
    for name, report_path, stderr_path in (
        ('csv', raw/'traffic_capture.csv.capture.json', raw/'traffic_capture.stderr'),
        ('pcap', raw/'source_artifacts/traffic_capture.pcap.capture.json',
         raw/'source_artifacts/traffic_capture.pcap.stderr')):
        report = read_json(report_path)
        counters = parse_capture_counters(stderr_path.read_text())
        if (report != status.get('capture_results',{}).get(name)
                or report.get('returncode') not in (0,-15) or report.get('launch_error') is not None
                or report.get('capture_counters') != counters or not counters['statistics_complete']):
            return False
        drops = counters['packets_dropped_by_kernel']
        if report.get('accepted') is not (drops == 0):
            return False
        lost |= drops > 0
    return lost
