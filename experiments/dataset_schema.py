"""Version 1 documentation of existing observations, not a feature schema."""


def field(name, kind, unit, description, nullable=False, domain=None):
    result = dict(name=name, type=kind, unit=unit, nullable=nullable, description=description)
    if domain is not None:
        result['domain'] = domain
    return result


def table(producer, observation, clock, fields):
    for entry in fields:
        entry['origin'] = producer
    return dict(producer=producer, observation=observation, clock=clock, fields=fields)


def schema():
    f = field
    run = lambda: f('run_id', 'string', None, 'Execution identity; scope all joins by this ID.')
    epoch = lambda name, desc, nullable=False: f(name, 'number', 's_since_unix_epoch', desc, nullable)
    elapsed = lambda name, desc, nullable=False: f(name, 'number', 's_since_experiment_start', desc, nullable)
    active = lambda: f('attack_active', 'integer', None, 'Global effective event context, including burst silence; null means uncertain.', True, [0, 1, None])
    ids = lambda: f('active_event_ids', 'json_array_of_strings', None, 'CSV cell contains JSON event IDs; [] does not prove absence when attack_active is null.')
    cls = lambda domain: f('traffic_class', 'string', None, 'Causal generator class for requests; packets deliberately remain unknown.', domain=domain)
    tables = {}
    tables['requests'] = table('RequestLogger; source_aggregate for container sources', 'One HTTP attempt, all outcomes retained', 'client_start_and_end', [
        run(), f('request_id', 'string', None, 'Unique within run; source-prefix ID is not globally unique.'),
        f('generator', 'string', None, 'Producing traffic component.', domain=['normal', 'attack']),
        f('worker_id', 'integer', 'logical_worker_index', 'Global index within generator class; join to source_type/worker_index in inventory.'),
        f('target_url', 'string', None, 'Observed logical destination URL; operation is its path. Legacy query is retained.'),
        epoch('timestamp', 'Client observed beginning, before session.get and after executor scheduling.'),
        elapsed('elapsed_seconds', 'Monotonic beginning relative to shared experiment anchor.'),
        epoch('end_timestamp', 'Observed return/exception before finish persistence.', True),
        elapsed('end_elapsed_seconds', 'Monotonic conclusion; can occur in silence or after event end.', True),
        f('duration_ms', 'number', 'ms', '1000*(end_elapsed_seconds-elapsed_seconds); includes beginning instrumentation and HTTP, not finish persistence.', True),
        cls(['benign', 'attack']), active(),
        f('attack_id', 'string', None, 'Originating attack ID, absent for benign attempts.', True),
        f('event_id', 'string', None, 'Originating event ID, absent for benign attempts.', True), ids(),
        f('http_status', 'integer', 'HTTP_status_code', 'Present when an HTTP response exists.', True),
        f('outcome', 'string', None, 'Recorded client outcome; response includes statuses below 400.', domain=['response', 'http_error', 'transport_error', 'client_error', 'incomplete']),
        f('error_type', 'string', None, 'Python exception type; empty for responses or unfinished attempts.', True)])
    tables['packets'] = table('TcpdumpSniffer', 'One IPv4 TCP summary line recognized by the existing parser', 'packet_epoch', [
        run(), epoch('timestamp', 'Host capture epoch timestamp from tcpdump -tt, not reader time.'),
        elapsed('elapsed_seconds', 'timestamp minus experiment_start_timestamp; wall-clock alignment, not a monotonic sample.'),
        f('src_ip', 'string', 'IPv4_address', 'Observed source address; run attribute, not scientific source identity.'),
        f('src_port', 'integer', 'TCP_port', 'Observed source port.'),
        f('dst_ip', 'string', 'IPv4_address', 'Observed destination address.'),
        f('dst_port', 'integer', 'TCP_port', 'Observed destination port.'),
        f('packet_length', 'integer', 'bytes', 'Length extracted from tcpdump -q TCP summary (tcp N/length N); TCP payload summary, NOT complete frame/on-wire length.'),
        cls(['unknown']), active(), ids()])
    tables['rtt'] = table('RequestLogger.save_rtt; source_aggregate', 'One client duration for a response outcome, a subset of requests', 'client_end', [
        epoch('timestamp', 'Client conclusion epoch, NOT beginning.'),
        f('rtt', 'number', 'ms', 'Same duration_ms as request table for response outcomes; NOT TCP RTT.'),
        run(), f('request_id', 'string', None, 'Join to (run_id, request_id) in requests.'), cls(['benign', 'attack']),
        elapsed('elapsed_seconds', 'Monotonic conclusion; equals request end_elapsed_seconds.')])
    tables['metrics'] = table('main_orchestrator.log_metrics_to_csv; existing StatsCollector/host_stats', 'One existing monitoring tick; already averaged/cached measurements, NOT individual Docker samples', 'host_tick', [
        run(), epoch('timestamp', 'Writing/observation instant after tick actions; not original Docker read time.'),
        elapsed('elapsed_seconds', 'Monotonic tick relative to anchor.'),
        elapsed('elapsed_time_s', 'Redundant elapsed_seconds rounded to 2 decimals; preserved for compatibility.'),
        f('num_instances', 'integer', 'victim_count', 'Active victim count, excluding proxy and sources.'),
        f('average_cpu_percent', 'number', 'percent', 'Existing average of Docker CPU samples over configured history window, with last-cache fallback; can exceed 100.'),
        f('mem_usage', 'number', 'MiB', 'Existing mean application memory: max(usage-cache,0)/1024^2, rounded; name retained.'),
        f('avg_rtt_ms', 'number', 'ms', 'Existing mean of injector monotonic HTTP durations, measured after begin logging; may differ from request duration_ms. Samples selected by global attack window; 0 can mean no samples.'),
        f('decision', 'string', None, 'Existing orchestrator decision; no exporter interpretation.'),
        f('active_containers_names', 'string', None, 'Comma-separated monitored victim names, possibly empty before stats become available; join to backend inventory within run.'),
        active(), ids(), f('host_cpu_percent', 'number', 'percent', 'Existing psutil host CPU observation, rounded.')])
    tables['attacks'] = table('GroundTruth; source_aggregate.reconcile for container sources', 'One global attack event, NOT one burst', 'event_elapsed', [
        f('schema_version', 'integer', None, 'Original ground truth schema version.', domain=[1]),
        f('experiment_id', 'string', None, 'Configured experiment identifier.'), run(),
        epoch('experiment_start_timestamp', 'Initial host epoch anchor.'),
        f('experiment_start_monotonic', 'number', 's_monotonic_since_unspecified_origin', 'Host monotonic anchor; only meaningful within compatible time namespace/host boot.'),
        f('attack_id', 'string', None, 'Attack identifier within run.'), f('event_id', 'string', None, 'Event identifier within run.'),
        f('profile', 'string', None, 'Configured temporal profile; geometry belongs to effective config.', domain=['continuous', 'periodic_burst']),
        elapsed('scheduled_start_seconds', 'Planned global beginning.'), elapsed('scheduled_end_seconds', 'Planned global end, derived from start plus duration.'),
        elapsed('activation_requested_seconds', 'Activation authorizes admission but does not start effective event.', True),
        elapsed('actual_start_seconds', 'First admitted attempt actually begun.', True),
        elapsed('stop_requested_seconds', 'Observed closing of admission requested.', True),
        elapsed('actual_end_seconds', 'Certification: admission closed and no admitted attempt left to begin. NOT drain.', True),
        elapsed('last_request_start_seconds', 'Last observed attack attempt beginning.', True),
        elapsed('drained_end_seconds', 'Last admitted completion, certified after drain; may precede actual_end.', True),
        f('status', 'string', None, 'Event lifecycle, distinct from run status.', domain=['planned', 'activated', 'active', 'stopping', 'emission_ended', 'completed', 'not_executed', 'incomplete']),
        f('end_reason', 'string', None, 'Reason supplied by the lifecycle; absent until stopped.', True)])
    for component, count in [('attack', 'num_attackers'), ('normal', 'num_clients')]:
        tables[component+'_summary'] = table(component+'_summary_logger; source_experiment aggregation',
            'Operational mixed rows: initial plan plus worker stop rows; no explicit record_type or global worker ID', 'worker_lifetime', [
            f(count, 'integer', 'entity_count', 'Filled in plan row; empty in worker result rows.', True),
            f('rps_per_worker', 'number', 'requests/s_per_entity_during_activity', 'Nominal rate per generating entity, not send-pool thread or temporal average.'),
            f('planned_total_rps', 'number', 'requests/s_during_activity', 'rate times entity count; only plan row.', True),
            f('num_targets', 'integer', 'logical_destination_count', 'In proxy mode 1 service endpoint, NOT victim count.', True),
            f('total_requests', 'integer', 'HTTP_response_count', 'Worker result counts HTTP responses, including HTTP error statuses; not necessarily successes.', True),
            f('elapsed_time_s', 'number', 's_of_worker_lifetime', 'Worker lifetime including silence and awaiting futures; not experiment-relative time.', True),
            f('real_rps', 'number', 'responses/s_of_worker_lifetime', 'Existing summary ratio; not instantaneous burst rate.', True),
            f('errors', 'integer', 'transport_error_count', 'Existing worker RequestException counter.', True)])
    return dict(schema_version=1, encoding=dict(csv='UTF-8 CSV; original bytes and column order preserved',
                null='Empty CSV cells remain empty; never impute 0', json_array='JSON encoded inside a CSV cell'),
                tables=tables, clocks={
                    'anchor': 'metadata/run_status.json: experiment_start_timestamp and experiment_start_monotonic, when present',
                    'client_start_and_end': 'Host or source time.time() epoch plus time.monotonic()-monotonic_initial. The pair is not sampled atomically.',
                    'client_end': 'Same domains, sampled at completion.',
                    'host_tick': 'Host epoch/monotonic pair at tick writing. Original Docker read timestamps/history are not persisted.',
                    'event_elapsed': 'Seconds since monotonic anchor; setup-only incomplete runs may have no anchor/event.',
                    'packet_epoch': 'tcpdump host capture epoch; elapsed=epoch-epoch_initial. Wall-clock adjustments may diverge from monotonic elapsed.',
                    'worker_lifetime': 'Monotonic duration local to worker, not a shared anchor timestamp.',
                    'nginx': '$msec is epoch seconds with millisecond precision at log writing/completion; request_time/upstream_time/connect_time are seconds. No silent conversion to client start.',
                    'source_audit': 'clock_validation samples raw host/container monotonic and epoch before release. comparable certifies same time namespace/bracketing for those samples, not continuous wall-clock drift monitoring.',
                    'alignment_limitations': 'Use preserved anchors/audit. Packet CSV and main PCAP are separate tcpdump processes with the same selected interface/BPF, not guaranteed identical captures or a packet-ID join.'},
                correlations={
                    'scope': 'IDs reset across runs. Join with run_id; no new identities invented.',
                    'request_source': 'In container mode: (generator,worker_id) joins (source_type,worker_index) in metadata/source_inventory.json; journal envelope has source_id directly. Request prefix is additional evidence.',
                    'source_packet': 'Observed src/dst IP joins inventory IP within this run; do not overwrite packet traffic_class=unknown.',
                    'request_event': '(run_id,event_id) for attack-origin attempts; active_event_ids expresses temporal context, not causal origin.',
                    'request_victim': 'request_id joins proxy access log/routing evidence; upstream IP:port and body hostname join backend inventory.',
                    'packet_request': 'No direct request_id or packet_id in packet CSV; tuple/time is contextual only. HTTP connection IDs/ephemeral client ports are not in request CSV.',
                    'metrics_victim': 'Names identify monitored set within run; CSV contains aggregated existing samples, not per-container sample history.'},
                metadata_contracts={
                    'configuration': 'Canonical effective_config JSON from ExperimentConfig; preserve all values. attack.rate is nominal per entity during activity; burst.duration_seconds and period_seconds define periodic windows. Legacy work/sleep fields are inert on reserved operations.',
                    'run_status': 'schema_version integer; run_id/experiment_id/status/end_reason strings; status completed|incomplete; errors array; producers_drained boolean when available; optional experiment epoch/monotonic anchors and topology/proxy evidence. Absence is not synthesized.',
                    'source_inventory': 'Array: source_id/source_type/traffic_class strings; run_id nullable during setup; worker_index/send_workers/aggregate_worker_budget integers; ip/container_id/container_name/hostname/network/service_endpoint/image/tag/image_id/digest/base_image/base_digest strings; repo_digests array; status_final nullable object with lifecycle booleans/exit code. IP/container names are run attributes.',
                    'source_manifest': 'source_id/source_type/traffic_class/service_endpoint strings; worker_index/aggregate_worker_budget/seed integers; settings contains entity-specific config/quota. A build recipe copied at setup is not proof that cached image was built from current tree.',
                    'journal': 'JSONL envelope source_id/run_id strings, sequence integer, kind string, payload object. admission/abandoned_admission use event_id and elapsed_seconds; request_begin/finish use request fields; event_snapshot/emission_closed use event fields; latency_sample is injector duration_ms measured after begin logging, distinct from request duration_ms. Other kinds are operational binding/configuration/closure.',
                    'nginx_access': 'JSONL operational log: timestamp string epoch seconds; request/request_id/upstream/upstream_status/request_time/upstream_time/connect_time/phase/remote_addr/connection/connection_requests strings; status integer HTTP code. May include setup/audit probes without request ID and before experiment start.',
                    'routing_evidence': 'JSONL run_id/request_id strings, response_body string, http_status integer. Operational responses, not additional scientific labels.',
                    'provenance': 'Execution provenance is only authoritative when captured before invocation and bound to this run. Export provenance describes export time, never the past run. Git dirty/fingerprints identify changes without reconstructing contents; Docker image identities remain separate from host working-tree identity.'})
