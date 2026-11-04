"""Single-origin runner. Only the service endpoint enters its destination API."""
import argparse
import json
import os
from pathlib import Path
import signal
import threading
import time
from simulator.experiment_config import NormalTrafficConfig, AttackConfig, BurstConfig
from simulator.ground_truth import ExperimentClock
from simulator.request_logger import RequestLogger
from simulator.source_journal import Journal, JournalGroundTruth, SharedClock


def atomic_json(path, payload):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload) + '\n')
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    root = Path('/output')
    command = Path('/control/command.json')
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    atomic_json(root / 'ready.json', dict(source_id=manifest['source_id'],
                monotonic=time.monotonic(), epoch=time.time(), time_namespace=os.readlink('/proc/self/ns/time')))
    while not command.exists():
        if stopped.wait(.01):
            return
    start = json.loads(command.read_text())
    clock = SharedClock(start['epoch'], start['monotonic'])
    journal = Journal(root / 'journal.jsonl', manifest['source_id'], start['run_id'])
    journal('run_binding', dict(run_id=start['run_id'], epoch=start['epoch'], monotonic=start['monotonic']))
    gt = JournalGroundTruth(start['experiment_id'], root / 'local_events.csv', clock=clock,
                            run_id=start['run_id'], journal=journal)
    logger = RequestLogger(gt, root / 'local_requests.csv', routing_log=root / 'routing_evidence.jsonl',
                           source_id=manifest['source_id'], journal=journal)
    is_attack = manifest['source_type'] == 'attack'
    if is_attack:
        from simulator import traffic_injectorV0 as module, attack_summary_logger as summary
        values = dict(manifest['settings'])
        if values.get('burst') is not None:
            values['burst'] = BurstConfig(**values['burst'])
        settings = AttackConfig(**values)
        gt.plan_event('attack_001', 'event_001', settings.profile, settings.start_seconds, settings.end_seconds)
        worker = module.http_request_worker
    else:
        from simulator import normal_traffic as module, normal_traffic_summary_logger as summary
        settings = NormalTrafficConfig(**manifest['settings'])
        worker = module.normal_http_request_worker
    summary.configure_output(root / 'local_summary.csv')
    (summary.init_attack_summary_log if is_attack else summary.init_normal_traffic_summary_log)()
    module.configure(settings, manifest['seed'], gt, logger, manifest['service_endpoint'],
                     duration_observer=lambda duration, elapsed: journal("latency_sample",
                         dict(generator="attack" if is_attack else "normal", duration_ms=duration, elapsed_seconds=elapsed)))
    diagnostic_writer = None
    if manifest.get('diagnostics',{}).get('enabled'):
        from simulator.diagnostics import DiagnosticWriter, DiagnosticExecutor
        diagnostic_writer = DiagnosticWriter(root/'diagnostics/events.jsonl',
            manifest['diagnostics']['queue_capacity'],
            context=dict(run_id=start['run_id'],source_id=manifest['source_id'],component='source'))
        module._send_pool = DiagnosticExecutor(module._send_pool, diagnostic_writer)
        logger.diagnostics = module._send_pool
    journal('configured', dict(worker_index=manifest['worker_index'], worker_budget=settings.max_concurrent_sends,
                              service_endpoint=manifest['service_endpoint']))
    started = False
    thread = None
    reason = 'simulation_end'
    try:
        while not stopped.is_set():
            control = json.loads(command.read_text())
            if control.get('stop'):
                reason = control.get('reason', 'simulation_end')
                break
            elapsed = clock.elapsed()
            if elapsed >= start['duration_seconds']:
                break
            should_start = not is_attack or settings.start_seconds <= elapsed < settings.end_seconds
            if should_start and not started:
                started = True
                if is_attack:
                    gt.activate('event_001')
                    module._event_id = 'event_001'
                    module.attack_active = True
                    summary.log_attack_start([manifest['service_endpoint']], settings.rate, 1)
                    threads = module.attacker_threads
                else:
                    module.traffic_active = True
                    summary.log_traffic_start([manifest['service_endpoint']], settings.rate, 1)
                    threads = module.client_threads
                thread = threading.Thread(target=worker, args=(settings.rate, manifest['worker_index']), daemon=True)
                threads.append(thread)
                thread.start()
            if is_attack and started and elapsed >= settings.end_seconds:
                module.stop_http_flood('scheduled_end')
                break
            stopped.wait(.01)
    finally:
        if is_attack:
            if started:
                module.stop_http_flood(reason)
            else:
                gt.stop('event_001', reason)
        else:
            module.stop_http_traffic()
        drained = module.drain(timeout=30)
        logger_complete = logger.finalize()
        logger.save_rtt(root / 'local_rtt.csv')
        gt.finalize(reason, complete=drained and logger_complete)
        journal('source_closed', dict(drained=drained, logger_complete=logger_complete,
                                      elapsed_seconds=clock.elapsed()))
        atomic_json(root / 'final_status.json', dict(source_id=manifest['source_id'], run_id=start['run_id'],
                    drained=drained, logger_complete=logger_complete, reason=reason))
        if diagnostic_writer:
            diagnostic_writer.emit('source_closed',at=time.monotonic(),
                counts=module._send_pool.counts.copy(),drained=drained,logger_complete=logger_complete)
            diagnostic_writer.close()
        if not drained or not logger_complete:
            os._exit(2)  # executor shutdown cannot keep an incomplete source alive indefinitely


if __name__ == '__main__':
    main()
