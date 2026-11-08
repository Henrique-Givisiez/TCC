"""Container-origin execution mode; host is the sole scientific CSV aggregator."""
import csv
import json
from pathlib import Path
import statistics
import time
import uuid
from simulator import config, host_stats
from simulator.ground_truth import GroundTruth
from simulator.http_proxy import HttpProxy, write_json
from simulator.source_manager import SourceManager
from simulator.source_aggregate import records, reconcile, aggregate, write_csv
from simulator.tcpdump_sniffer import TcpdumpSniffer
from simulator.direct_target import DirectTarget, require_empty_network

# Exposed only to host integration fault injection, never to source manifests.
active_proxy = None
active_manager = None
active_ground_truth = None


def run(experiment, operational=None):
    global active_proxy, active_manager, active_ground_truth
    from simulator import docker_manager, main_orchestrator
    from simulator.stats_collector import StatsCollector
    from experiments.source_network_audit import audit
    active_proxy = active_manager = active_ground_truth = None
    client = docker_manager.client
    errors, victims = [], []
    cost_intervals = []
    manager = proxy = gt = sniffer = collector = None
    raw_capture = None
    owned_networks = []
    complete = True
    drained = False
    shutdown_steps = []
    reason = 'simulation_end'
    status = dict(schema_version=1, experiment_id=experiment.id, run_id=uuid.uuid4().hex,
                  status='incomplete', end_reason='setup_error')
    if experiment.attack.profile == 'continuous':
        status['offensive_start_contract'] = 'scheduled-half-open-v1'
    diagnostic_root = Path(config.RUN_STATUS_FILE).parent/'diagnostics'
    api_timeout_saved = False
    try:
        Path(config.RUN_STATUS_FILE).parent.mkdir(parents=True, exist_ok=True)
        if experiment.diagnostics.enabled:
            (diagnostic_root/'victim').mkdir(parents=True,exist_ok=False)
        write_json(Path(config.RUN_STATUS_FILE).parent/'effective_config.json', json.loads(experiment.to_json()))
        if operational:
            operational.policy.validate(experiment)
            previous_api_timeout = client.api.timeout
            api_timeout_saved = True
            client.api.timeout = operational.policy.docker_timeout_seconds
            operational.arm()
        if operational:
            operational.ready(client)
        try:
            client.networks.get(config.DOCKER_NETWORK_NAME)
        except Exception as exc:
            if getattr(exc, 'status_code', None) != 404:
                raise
            owned_networks.append(config.DOCKER_NETWORK_NAME)
        if not (True if operational else docker_manager.build_docker_image()) or not docker_manager.ensure_docker_network():
            raise RuntimeError('victim infrastructure setup failed')
        # Refuse existing resources rather than removing a different run's victims.
        if client.containers.list(all=True, filters={'name': config.BASE_CONTAINER_NAME}):
            raise RuntimeError('victim resources already exist; refusing to overwrite')
        try:
            network = client.networks.get(config.SOURCE_NETWORK_NAME)
        except Exception as exc:
            if getattr(exc,'status_code',None)!=404:
                raise
            network = client.networks.create(config.SOURCE_NETWORK_NAME, driver='bridge')
            owned_networks.append(config.SOURCE_NETWORK_NAME)
        require_empty_network(network)
        for index in range(experiment.infrastructure.initial_instances):
            diagnostic_options = (dict(diagnostic_directory=diagnostic_root/'victim',
                diagnostic_capacity=experiment.diagnostics.queue_capacity) if experiment.diagnostics.enabled else {})
            victim = docker_manager.start_instance(index+1, experiment.server, publish_ports=False, **diagnostic_options)
            if victim is None:
                raise RuntimeError('victim start failed')
            victims.append(victim)
            if operational: operational.own(victim, "victim")
        direct = experiment.topology.mode == 'direct'
        proxy = (DirectTarget(client, Path(config.RUN_STATUS_FILE).parent/'direct_artifacts') if direct
                 else HttpProxy(client,config.PROXY_ARTIFACT_DIR))
        active_proxy = None if direct else proxy
        proxy.start(victims, source_network=network)
        manager = SourceManager(client,network,config.SOURCE_ARTIFACT_DIR,config.SOURCE_INVENTORY_FILE,experiment)
        active_manager = manager
        if operational:
            manager.on_created = lambda c: operational.own(c, 'source')
        manager.start()  # rejects incomparable clocks before any timeline is used
        if operational:
            for c in manager.containers: operational.own(c, "source")
        inventory = json.loads((proxy.directory/'backend_inventory.json').read_text())
        capture = audit(manager,proxy,inventory,manager.directory/'network_audit')
        if experiment.diagnostics.enabled:
            from simulator.source_manager import validate_clocks
            validate_clocks(victims,diagnostic_root/'victim_clock_validation.json')
        gt = GroundTruth(experiment.id,config.ATTACK_EVENTS_LOG_FILE)
        active_ground_truth = gt
        if experiment.diagnostics.enabled:
            from simulator.diagnostics import clock_metadata
            import hashlib
            repository = Path(__file__).resolve().parents[1]
            hashes = {str(p.relative_to(repository)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted((repository/'simulator').rglob('*.py'))}
            write_json(diagnostic_root/'metadata.json',dict(schema_version=1,run_id=gt.run_id,
                origin_monotonic=gt.clock.monotonic_initial,origin_epoch=gt.clock.epoch_initial,
                host_clock=clock_metadata(),source_sha256=hashes,configuration=json.loads(experiment.to_json()),
                victim_image_id=victims[0].image.id,source_image=config.SOURCE_IMAGE,
                container_limits={c.id:{k:c.attrs['HostConfig'].get(k) for k in
                    ('Memory','NanoCpus','CpuQuota','CpuPeriod','CpusetCpus','PidsLimit','Ulimits')}
                    for c in victims+manager.containers},
                correlation='Declared X-Edos run/source/request/event/class headers; computational lifecycle v1',
                computational_lifecycle_schema=1,
                victim_run_id='Declared by instrumentation headers; setup handlers may be unidentified'))
        status.update(run_id=gt.run_id,experiment_start_timestamp=gt.clock.epoch_initial,
                      experiment_start_monotonic=gt.clock.monotonic_initial)
        if experiment.attack.enabled:
            gt.plan_event('attack_001','event_001',experiment.attack.profile,experiment.attack.start_seconds,experiment.attack.end_seconds)
        proxy.bind_run(gt.run_id)
        proxy.start_monitoring(gt.clock)
        write_json(proxy.directory/'capture_metadata.json',dict(run_id=gt.run_id,
                   topology=experiment.topology.mode,segment='source_victim' if direct else 'source_proxy',
                   target_id=proxy.expected_id, target_ip=capture['proxy_ip'],target_port=config.APP_CONTAINER_PORT,
                   capture_point='host_network_interface',
                   interface=capture['selected_interface'],bpf=capture['bpf'],
                   **({'victim_ip':capture['proxy_ip']} if direct else {'proxy_ip':capture['proxy_ip']}),
                   audit='source_artifacts/network_audit/comparison.json'))
        sniffer = TcpdumpSniffer(capture['selected_interface'],config.TCPDUMP_OUTPUT_CSV,gt,bpf_filter=capture['bpf'])
        sniffer.start()
        sniffer.wait_ready()
        from simulator.capture_evidence import RawCapture
        raw_capture = RawCapture(capture['selected_interface'],capture['bpf'],manager.directory/'traffic_capture.pcap')
        collector = StatsCollector(client,experiment.monitoring.stats_poll_interval_seconds,experiment.monitoring.history_seconds)
        collector.update_containers(victims)
        collector.dedicated_client = True
        collector.bind_cpu(gt.run_id, gt.clock, Path(config.RUN_STATUS_FILE).parent/'victim_stats.jsonl')
        status['cpu_observation_contract'] = 'victim-cpu-snapshots-v1'
        collector.start()
        if operational: operational.collection_started = time.monotonic()
        write_csv(config.METRICS_LOG_FILE,main_orchestrator.METRICS_FIELDS,[])
        manager.release(gt)
        consumed = set()
        next_tick = gt.clock.monotonic_initial
        while gt.clock.elapsed()<experiment.duration_seconds:
            if operational: operational.observe(client, collector)
            proxy.verify()
            manager.verify()
            sniffer.check_running()
            raw_capture.verify()
            for victim in victims:
                main_orchestrator.verify_fixed_victim([victim],victim.id,client)
            journal = records(manager.directory,manager.entries,strict=False)
            if experiment.attack.enabled and not any(e['source_type']=='attack' for e in manager.entries):
                event = gt.event('event_001')
                if gt.clock.elapsed()>=experiment.attack.start_seconds and event['status']=='planned':
                    gt.activate('event_001')
                if gt.clock.elapsed()>=experiment.attack.end_seconds:
                    gt.stop('event_001')
            reconcile(gt,manager.entries,journal)
            normal, attack = [], []
            for item in journal:
                key = item['source_id'],item['sequence']
                if item['kind']=='latency_sample' and key not in consumed:
                    consumed.add(key)
                    payload = item['payload']
                    (attack if payload['generator']=='attack' else normal).append(payload['duration_ms'])
            avg_cpu,avg_mem,names = collector.get_averages(window_seconds=experiment.monitoring.interval_seconds)
            attack_operational = experiment.attack.enabled and experiment.attack.start_seconds<=gt.clock.elapsed()<experiment.attack.end_seconds
            latencies = attack if attack_operational else normal
            main_orchestrator.log_metrics_to_csv(gt,len(victims),avg_cpu,avg_mem,
                         statistics.mean(latencies) if latencies else 0,'NO_ACTION',names,host_stats.get_host_cpu_percent())
            cost_intervals.append((len(victims),experiment.monitoring.interval_seconds))
            next_tick += experiment.monitoring.interval_seconds
            time.sleep(max(0,next_tick-time.monotonic()))
        proxy.verify()
        manager.verify()
    except BaseException as exc:
        reason = 'interrupted' if isinstance(exc,KeyboardInterrupt) else 'error'
        errors.append(str(exc))
        if operational:
            operational.report['actions'].append(dict(reasons=['runtime_exception'], condition=repr(exc), action='stop_all', at=time.monotonic()))
        complete = False
    finally:
        if operational:
            try: operational.disarm()
            except Exception as exc:
                errors.append('timer finalization: '+repr(exc))
                complete = False
        if operational and manager:
            for c in manager.containers:
                operational.owned.setdefault(c.id, "source")
        if manager:
            try:
                drained = manager.stop(reason)
                shutdown_steps.append(dict(component="sources", complete=drained))
                complete = drained and complete
                if not drained:
                    errors.append('source drain incomplete')
            except Exception as exc:
                shutdown_steps.append(dict(component='sources', error=str(exc)))
                errors.append('source stop: '+str(exc))
                complete = False
        if proxy:
            try:
                proxy.verify()
            except Exception as exc:
                errors.append(str(exc))
                complete = False
        if gt and manager:
            try:
                if experiment.attack.enabled and not any(e['source_type']=='attack' for e in manager.entries):
                    gt.finalize(reason,complete=drained)
                logs_complete, requests = aggregate(gt,manager.entries,manager.directory,config.REQUEST_LOG_FILE,
                       config.RTT_LOG_FILE,proxy.directory/'routing_evidence.jsonl',config.METRICS_LOG_FILE)
                complete = logs_complete and complete
                if not logs_complete:
                    errors.append('requests without completion evidence')
                # Preserve legacy summary schemas; one global start plus source worker rows.
                for component,summary_module,filename in [('normal','normal_traffic_summary_logger',config.NORMAL_TRAFFIC_SUMMARY_LOG_FILE),
                                                          ('attack','attack_summary_logger',config.ATTACK_SUMMARY_LOG_FILE)]:
                    from importlib import import_module
                    fields = import_module('simulator.'+summary_module).FIELDNAMES
                    summaries = []
                    starts = []
                    for entry in manager.entries:
                        if entry['source_type']!=component:
                            continue
                        path = manager.directory/entry['source_id']/'output/local_summary.csv'
                        if path.exists():
                            with path.open(newline='') as stream:
                                for row in csv.DictReader(stream):
                                    (starts if row.get('num_targets') else summaries).append(row)
                    if starts:
                        first = starts[0].copy()
                        key = 'num_clients' if component=='normal' else 'num_attackers'
                        first[key] = len(starts)
                        first['planned_total_rps'] = sum(float(r['planned_total_rps']) for r in starts)
                        summaries.insert(0,first)
                    write_csv(filename,fields,summaries)
            except Exception as exc:
                errors.append('source aggregation: '+str(exc))
                complete = False
        for name, component in [('raw_capture',raw_capture),('capture',sniffer),('stats',collector)]:
            if component:
                try:
                    component.stop()
                    if operational and name == "stats" and component._t.is_alive():
                        raise RuntimeError("stats collector did not close")
                    shutdown_steps.append(dict(component=name, complete=True))
                except Exception as exc:
                    shutdown_steps.append(dict(component=name, error=str(exc)))
                    errors.append(name+': '+str(exc))
                    complete = False
        if manager:
            try:
                manager.remove()
                shutdown_steps.append(dict(component="source_removal", complete=True))
            except Exception as exc:
                errors.append(str(exc))
                complete = False
        if proxy:
            try:
                proxy.close(True)  # remaining sources have been terminated/removed first
            except Exception as exc:
                errors.append('proxy cleanup: '+str(exc))
                complete = False
        if experiment.diagnostics.enabled:
            try:
                (diagnostic_root/'victim/stop').touch()
            except Exception as exc:
                errors.append('diagnostic close: '+str(exc))
                complete = False
            deadline = time.monotonic()+3
            try:
                while not (diagnostic_root/'victim/events.summary.json').exists() and time.monotonic()<deadline:
                    time.sleep(.02)
                if not (diagnostic_root/'victim/events.summary.json').exists():
                    raise RuntimeError('victim observation closure missing')
                observation = json.loads((diagnostic_root/'victim/events.summary.json').read_text())
                status['victim_observation_complete'] = observation.get('observation_complete', observation.get('complete'))
                if observation.get('complete') is not True:
                    raise RuntimeError('victim observation technically incomplete')
            except Exception as exc:
                errors.append('diagnostic wait: '+repr(exc))
                complete = False
        for victim in victims:
            try:
                if not docker_manager.stop_instance(victim.id):
                    raise RuntimeError('stop/remove returned false')
                shutdown_steps.append(dict(component='victim', id=victim.id, complete=True))
            except Exception as exc:
                shutdown_steps.append(dict(component='victim', id=victim.id, error=str(exc)))
                errors.append('victim cleanup failed: '+victim.id+': '+str(exc))
                complete = False
        for name in reversed(owned_networks):
            try:
                client.networks.get(name).remove()
            except Exception as exc:
                errors.append('network cleanup: '+str(exc))
                complete = False
        if operational:
            operational.report['shutdown_steps'] = shutdown_steps
            operational.report['temporary_networks'] = owned_networks
            operational.report['nominal_seconds'] = experiment.duration_seconds
            if api_timeout_saved:
                try: client.api.timeout = previous_api_timeout
                except Exception as exc: errors.append('Docker timeout restoration: '+repr(exc))
            try:
                operational.finish(client, errors)
            except Exception as exc:
                errors.append('operational evidence: '+str(exc))
            complete = complete and not errors
        capture_results = {}
        for name, component in [('pcap',raw_capture),('csv',sniffer)]:
            lifecycle = getattr(component,'lifecycle',None) if component else None
            capture_results[name] = lifecycle.report if lifecycle else None
        status.update(status='completed' if complete and reason=='simulation_end' else 'incomplete',
                      end_reason=reason,producers_drained=drained,errors=errors,
                      capture_results=capture_results,
                      topology=experiment.topology.mode,
                      proxy_integrity=proxy.identity if proxy and experiment.topology.mode=='proxy' else None,
                      target_integrity=proxy.identity if proxy else None,
                      source_inventory=config.SOURCE_INVENTORY_FILE)
        try:
            write_json(config.RUN_STATUS_FILE,status)
        except Exception as exc:
            if operational:
                operational.report['failures'].append('run_status persistence: '+repr(exc))
                operational.report['progression_allowed'] = False
                operational.persist()
            raise
    if complete and reason=='simulation_end':
        from simulator.cost_calculator import calculate_total_cost_from_intervals
        cost = calculate_total_cost_from_intervals(cost_intervals,experiment.infrastructure.cost_per_instance_per_hour)
        print(f'[Sources] Total fictional victim cost: ${cost:.4f}')
    if not complete or reason!='simulation_end':
        raise RuntimeError('incomplete source experiment: '+ '; '.join(errors))
