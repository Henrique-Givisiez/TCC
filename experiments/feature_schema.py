"""Version 1 observed features; labels are never detector inputs."""
KEYS = ['run_id', 'window_index', 'window_start_seconds', 'window_end_seconds']
FEATURES = {
    'network': ['ingress_packet_count', 'egress_packet_count',
                'ingress_tcp_payload_length_sum_bytes', 'egress_tcp_payload_length_sum_bytes', 'unique_client_src_ips'],
    'service': ['request_starts', 'request_completions', 'request_failures',
                'http_failures', 'transport_failures', 'client_failures', 'mean_duration_ms'],
    'infrastructure': ['mean_cpu_percent', 'mean_memory_mib'],
}
LABELS = ['attack_event_overlap_seconds', 'attack_event_overlap_fraction', 'attack_request_starts']


def feature_schema():
    definitions = {
        'ingress_packet_count': ('integer','records/window','Count of source→proxy CSV packet records, including zero-payload packets and observed retransmissions.'),
        'egress_packet_count': ('integer','records/window','Count of proxy→source CSV packet records.'),
        'ingress_tcp_payload_length_sum_bytes': ('integer','bytes/window','Sum of the existing packet_length TCP-summary field for ingress; not Ethernet/on-wire/unique HTTP bytes.'),
        'egress_tcp_payload_length_sum_bytes': ('integer','bytes/window','Same sum for return traffic; no deduplication.'),
        'unique_client_src_ips': ('integer','addresses/window','Distinct ingress source IPs drawn from ALL source inventory entries, without causal class filtering.'),
        'request_starts': ('integer','attempts/window','Count assigned by elapsed_seconds at beginning.'),
        'request_completions': ('integer','attempts/window','Count assigned by known end_elapsed_seconds, all outcomes.'),
        'request_failures': ('integer','attempts/window','Completed http_error, transport_error or client_error outcomes; unfinished attempts have no invented failure time.'),
        'http_failures': ('integer','attempts/window','Completed outcome=http_error, including HTTP 4xx/5xx.'),
        'transport_failures': ('integer','attempts/window','Completed outcome=transport_error.'),
        'client_failures': ('integer','attempts/window','Completed outcome=client_error.'),
        'mean_duration_ms': ('number','ms','Arithmetic mean of duration_ms over all concluded attempts, including failures; client observed HTTP duration, NOT TCP RTT.'),
        'mean_cpu_percent': ('number','percent','Arithmetic mean of supported average_cpu_percent tick values, already averaged/cached by the existing collector; not time weighted or instantaneous CPU; may exceed 100.'),
        'mean_memory_mib': ('number','MiB','Arithmetic mean of supported mem_usage tick values: existing max(usage-cache,0)/1024² measurements, already averaged/cached.'),
        'attack_event_overlap_seconds': ('number','s','Intersection duration with union of effective global [actual_start,actual_end) events; burst silence remains part of event.'),
        'attack_event_overlap_fraction': ('number','fraction','Overlap seconds divided by full window_size_seconds; no binary threshold.'),
        'attack_request_starts': ('integer','attempts/window','Diagnostic causal attack starts assigned by beginning, stored ONLY in labels.csv.'),
    }
    tables = {}
    for family, names in {**FEATURES, 'labels': LABELS}.items():
        fields = [dict(name='run_id',type='string',unit=None,role='key',nullable=False),
                  dict(name='window_index',type='integer',unit=None,role='key',nullable=False),
                  *[dict(name=n,type='number',unit='s_since_experiment_start',role='key',nullable=False) for n in KEYS[2:]]]
        for name in names:
            kind, unit, meaning = definitions[name]
            nullable = family == 'network' or name.startswith('mean_')
            fields.append(dict(name=name,type=kind,unit=unit,role='label' if family=='labels' else 'feature',nullable=nullable,description=meaning))
        tables[family] = dict(path=f'timeseries/{family}.csv',fields=fields,
                            detector_columns=names if family!='labels' else [])
    return dict(feature_schema_version=1,tables=tables,
                csv_null='Empty cell; no NaN, zero replacement or imputation.',
                zero='Zero packet/request counts and sums mean zero records in the available input, NOT proof of physical inactivity or capture coverage.',
                infrastructure_support='active_containers_names nonempty: collector has support. Empty names/0,0 startup ticks remain in input and per-window manifest diagnostics, excluded from means. Cache freshness is not reconstructed.',
                temporal_semantics='Regular fixed nonoverlapping [start,end) windows from elapsed origin zero; decimal assignment without epsilon.',
                leakage='Only detector_columns are features. Keys, manifest configuration/provenance/diagnostics and labels are not detector inputs.')
