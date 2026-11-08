"""Read-only Stage 10 extraction of regular observed features, without detectors."""
import argparse
import csv
from decimal import Decimal, InvalidOperation, localcontext, ROUND_FLOOR, ROUND_CEILING, ROUND_HALF_EVEN
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile

from experiments.dataset_provenance import capture_provenance, sha256_file
from experiments.feature_schema import FEATURES, KEYS, LABELS, feature_schema
from experiments.cpu_features import load_evidence, assign_cpu

SOURCES = {
    'configuration': 'metadata/effective_config.json', 'status': 'metadata/run_status.json',
    'network': 'raw/traffic/traffic_capture.csv', 'service': 'raw/service/request_log.csv',
    'infrastructure': 'raw/infrastructure/simulation_metrics.csv', 'events': 'raw/attacks/attack_events.csv',
}


def decimal(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f'Invalid decimal input: {value}') from exc
    if not result.is_finite():
        raise ValueError('Nonfinite decimal input')
    return result


def text_number(value):
    if value == 0:
        return '0'
    return format(value, 'f')


def safe_file(root, relative):
    if not isinstance(relative,str) or not relative or '\\' in relative:
        raise ValueError('Invalid input path')
    pure = PurePosixPath(relative)
    if pure.is_absolute() or '..' in pure.parts or pure.as_posix()!=relative:
        raise ValueError(f'Unsafe input path: {relative}')
    path = root / relative
    if root not in path.resolve().parents:
        raise ValueError(f'Input path escapes dataset: {relative}')
    current = path
    while current != root:
        if current.is_symlink():
            raise ValueError(f'Symlink input is not supported: {relative}')
        current = current.parent
    if not path.is_file():
        raise ValueError(f'Missing input file: {relative}')
    return path


def read_json(path, decimal_numbers=True):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise ValueError(f'Duplicate JSON key: {key}')
            result[key]=value
        return result
    def reject(value):
        raise ValueError(f'Nonfinite JSON value: {value}')
    return json.loads(path.read_text(encoding='utf-8'),parse_float=Decimal if decimal_numbers else float,object_pairs_hook=unique,parse_constant=reject)


def write_json(path, value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')


class Inputs:
    def __init__(self, dataset, report):
        self.root = Path(dataset).resolve()
        self.manifest_path = safe_file(self.root,'dataset_manifest.json')
        self.manifest = read_json(self.manifest_path)
        self.manifest_hash = sha256_file(self.manifest_path)
        self.report_path = Path(report).resolve()
        if not self.report_path.is_file():
            raise ValueError('Missing Stage 9 validation report')
        self.report = read_json(self.report_path,decimal_numbers=False)
        self.report_hash = sha256_file(self.report_path)
        if not isinstance(self.manifest,dict) or not isinstance(self.report,dict):
            raise ValueError('Dataset manifest and Stage 9 report must be JSON objects')
        versions=[self.manifest.get('schema_version'),self.report.get('validation_schema_version'),self.report.get('dataset_schema_version')]
        if any(type(v) is not int or v!=1 for v in versions):
            raise ValueError('Unsupported dataset/report schema version')
        if self.report.get('dataset_manifest_sha256') != self.manifest_hash or self.report.get('run_id') != self.manifest.get('run_id'):
            raise ValueError('Stage 9 report does not correspond to this manifest/run')
        if self.report.get('analysis_eligible') is not True or self.report.get('dataset_valid') is not True:
            raise ValueError('Stage 9 dataset is not analysis_eligible')
        self.index = {}
        if not isinstance(self.manifest.get('files'),list):
            raise ValueError('Manifest must index input files')
        for entry in self.manifest['files']:
            if not isinstance(entry,dict) or not isinstance(entry.get('path'),str) or not entry['path'] or entry['path'] in self.index:
                raise ValueError('Invalid or duplicate manifest file entry')
            self.index[entry['path']] = entry
        self.consumed = {}

    def file(self, relative):
        path = safe_file(self.root,relative)
        entry = self.index.get(relative)
        if entry is None or entry.get('sha256') != sha256_file(path) or entry.get('bytes') != path.stat().st_size:
            raise ValueError(f'Consumed input hash/size mismatch or unindexed file: {relative}')
        self.consumed[relative] = dict(path=relative,sha256=entry['sha256'],bytes=entry['bytes'])
        return path

    def json(self, relative):
        return read_json(self.file(relative))

    def csv(self, relative):
        with self.file(relative).open(encoding='utf-8',newline='') as stream:
            reader=csv.DictReader(stream,strict=True)
            rows=list(reader)
            if any(None in row or any(value is None for value in row.values()) for row in rows):
                raise ValueError(f'Malformed CSV width: {relative}')
            return rows

    def unchanged(self):
        if sha256_file(self.manifest_path)!=self.manifest_hash or sha256_file(self.report_path)!=self.report_hash:
            raise ValueError('Manifest or Stage 9 report changed during extraction')
        for relative, entry in self.consumed.items():
            if sha256_file(safe_file(self.root,relative))!=entry['sha256']:
                raise ValueError(f'Consumed input changed during extraction: {relative}')


def extractor_provenance():
    # Do not add a changing extraction timestamp or output paths to deterministic output.
    value = capture_provenance('feature_extraction')
    value.pop('captured_at_utc',None)
    git = value['code']['git']
    runtime = value['code']['runtime_files_sha256']
    changes = [c for c in git['changes'] if c['path'] in runtime or c.get('original_path') in runtime]
    git['changes'] = changes
    git['dirty'] = bool(changes) if git['status']=='recorded' else None
    git['dirty_scope'] = 'Runtime code, recipes and requirements; excludes generated output and documentation'
    value['extractor_files_sha256'] = {f'experiments/{p.name}':sha256_file(p) for p in
                                     [Path(__file__),Path(__file__).with_name('feature_schema.py'),Path(__file__).with_name('dataset_provenance.py')]}
    return value


def observed_span(values):
    return dict(first_seconds=text_number(min(values)) if values else None,
                last_seconds=text_number(max(values)) if values else None,
                observations=len(values),completeness='not_proven')


def extract_features(dataset, validation_report, destination, window_size_seconds='1', *, cpu_boundary_tolerance_seconds='0.05'):
    width=decimal(window_size_seconds)
    if width <= 0:
        raise ValueError('window_size_seconds must be positive')
    inputs=Inputs(dataset,validation_report)
    destination=Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('Feature destination already exists')
    destination=destination.resolve()
    if destination==inputs.root or destination in inputs.root.parents or inputs.root in destination.parents:
        raise ValueError('Feature output and dataset must be separate without nesting')
    if destination==inputs.report_path or destination in inputs.report_path.parents:
        raise ValueError('Feature output must not contain the Stage 9 input report')
    if inputs.manifest.get('configuration')!=SOURCES['configuration'] or inputs.manifest.get('run_status')!=SOURCES['status']:
        raise ValueError('Unsupported canonical input references')
    config=inputs.json(SOURCES['configuration']);status=inputs.json(SOURCES['status'])
    packets=inputs.csv(SOURCES['network']);requests=inputs.csv(SOURCES['service']);metrics=inputs.csv(SOURCES['infrastructure']);events=inputs.csv(SOURCES['events'])
    if status.get('run_id')!=inputs.manifest['run_id'] or status.get('status')!='completed':
        raise ValueError('Canonical status does not describe the eligible completed run')
    cpu_evidence = load_evidence(inputs, status)
    version = 2 if cpu_evidence is not None else 1
    if cpu_evidence is not None and width != 1:
        raise ValueError('CPU snapshot contract requires one-second feature windows')
    # Use inventory topology only, NEVER source causal class, to identify network clients.
    clients=None;proxy=None;service_port=None;warnings=[]
    mode=config.get('topology',{}).get('mode','proxy')
    cap_path=f'metadata/topology/{mode}/capture_metadata.json'
    if all(f'metadata/topology/{m}/capture_metadata.json' in inputs.index for m in ('proxy','direct')):
        raise ValueError('Ambiguous capture topology metadata')
    segment=None
    inv_path=inputs.manifest.get('source_inventory')
    if inv_path and cap_path in inputs.index:
        inventory=inputs.json(inv_path);capture=inputs.json(cap_path)
        from experiments.capture_topology import capture_destination
        proxy,declared_port=capture_destination(capture,config)
        segment=capture['segment']
        if proxy:
            from urllib.parse import urlsplit
            endpoints={urlsplit(s['service_endpoint']).port or 80 for s in inventory}
            if len(endpoints)!=1:
                raise ValueError('Source service ports are ambiguous')
            clients={s['ip'] for s in inventory};service_port=endpoints.pop()
            if service_port != declared_port:
                raise ValueError('Capture port contradicts source endpoint')
    if mode=='direct' and clients is None:
        raise ValueError('Direct capture metadata/source inventory missing')
    network_supported=clients is not None
    if not network_supported:
        warnings.append(dict(code='NETWORK_DIRECTION_UNAVAILABLE',message='No supported capture inventory/metadata. Network features are null; packet observations still define horizon and coverage metadata.'))
    times={
        'network':[decimal(p['elapsed_seconds']) for p in packets],
        'service_starts':[decimal(r['elapsed_seconds']) for r in requests],
        'service_completions':[decimal(r['end_elapsed_seconds']) for r in requests if r['end_elapsed_seconds']],
        'infrastructure_records':[decimal(r['elapsed_seconds']) for r in metrics],
        'infrastructure_supported':[decimal(r['elapsed_seconds']) for r in metrics if r['active_containers_names']],
    }
    observed=times['network']+times['service_starts']+times['service_completions']+times['infrastructure_records']
    if any(t<0 for t in observed):
        raise ValueError('Negative elapsed observations cannot be silently dropped from origin-zero feature grid')
    duration=decimal(config['duration_seconds'])
    if duration<=0:
        raise ValueError('Planned duration must be positive')
    # Enough precision for exact decimal boundary division/subtraction of finite inputs.
    values=observed+[duration,width]
    precision=max(50,max(v.adjusted() for v in values)-min(v.as_tuple().exponent for v in values)+10)
    with localcontext() as context:
        context.prec=precision
        context.rounding=ROUND_HALF_EVEN
        maximum=max(observed) if observed else Decimal(0)
        windows=max(int((duration/width).to_integral_value(rounding=ROUND_CEILING)),int((maximum/width).to_integral_value(rounding=ROUND_FLOOR))+1)
        def index(t):
            return int((t/width).to_integral_value(rounding=ROUND_FLOOR))
        network=[{n:0 if network_supported else None for n in FEATURES['network']} for _ in range(windows)]
        service=[{n:0 if n!='mean_duration_ms' else None for n in FEATURES['service']} for _ in range(windows)]
        infrastructure=[{n:None for n in FEATURES['infrastructure']} for _ in range(windows)]
        labels=[dict(attack_event_overlap_seconds=Decimal(0),attack_event_overlap_fraction=Decimal(0),attack_request_starts=0) for _ in range(windows)]
        client_sets=[set() for _ in range(windows)];durations=[[] for _ in range(windows)];cpu=[[] for _ in range(windows)];memory=[[] for _ in range(windows)]
        unsupported=[];unfinished=[]
        for p,t in zip(packets,times['network']):
            if not network_supported:continue
            i=index(t)
            if p['src_ip'] in clients and p['dst_ip']==proxy and int(p['dst_port'])==service_port:
                direction='ingress';client_sets[i].add(p['src_ip'])
            elif p['src_ip']==proxy and int(p['src_port'])==service_port and p['dst_ip'] in clients:
                direction='egress'
            else:
                raise ValueError('Packet cannot be assigned to the declared '+segment+' directions')
            network[i][direction+'_packet_count']+=1
            network[i][direction+'_tcp_payload_length_sum_bytes']+=int(p['packet_length'])
        for i in range(windows):
            if network_supported:network[i]['unique_client_src_ips']=len(client_sets[i])
        failure_columns={'http_error':'http_failures','transport_error':'transport_failures','client_error':'client_failures'}
        for r in requests:
            i=index(decimal(r['elapsed_seconds']));service[i]['request_starts']+=1
            if r['traffic_class']=='attack':labels[i]['attack_request_starts']+=1
            if not r['end_elapsed_seconds']:
                unfinished.append(r['request_id']);continue
            j=index(decimal(r['end_elapsed_seconds']));service[j]['request_completions']+=1
            if r['outcome'] in failure_columns:
                service[j]['request_failures']+=1;service[j][failure_columns[r['outcome']]]+=1
            if not r['duration_ms']:
                raise ValueError('Completed request lacks observed duration')
            durations[j].append(decimal(r['duration_ms']))
        for row in metrics:
            i=index(decimal(row['elapsed_seconds']))
            if not row['active_containers_names']:
                unsupported.append(dict(window_index=i,elapsed_seconds=row['elapsed_seconds'],reported_cpu_percent=row['average_cpu_percent'],reported_memory_mib=row['mem_usage'],reason='collector_support_absent'))
                continue
            cpu[i].append(decimal(row['average_cpu_percent']));memory[i].append(decimal(row['mem_usage']))
        def mean(samples):
            if not samples:return None
            # Deterministic equal-weight mean of stored values, never smoothing/imputation.
            with localcontext() as mean_context:
                mean_context.prec=50
                mean_context.rounding=ROUND_HALF_EVEN
                return sum(sorted(samples),Decimal(0))/len(samples)
        for i in range(windows):
            service[i]['mean_duration_ms']=mean(durations[i])
            infrastructure[i]['mean_cpu_percent']=mean(cpu[i]);infrastructure[i]['mean_memory_mib']=mean(memory[i])
        cpu_quality = None
        if cpu_evidence is not None:
            cpu_values, cpu_quality = assign_cpu(*cpu_evidence, status, windows, cpu_boundary_tolerance_seconds)
            for i, value in enumerate(cpu_values):
                infrastructure[i]['mean_cpu_percent'] = value
        intervals=[]
        for event in events:
            if not event['actual_start_seconds']:
                continue
            if not event['actual_end_seconds']:
                raise ValueError('Global attack overlap is unknown; cannot synthesize labels')
            intervals.append((decimal(event['actual_start_seconds']),decimal(event['actual_end_seconds'])))
        union=[]
        for start,end in sorted(intervals):
            if end<start:raise ValueError('Invalid effective event interval')
            if union and start<=union[-1][1]:union[-1]=(union[-1][0],max(end,union[-1][1]))
            else:union.append((start,end))
        for i in range(windows):
            start,end=i*width,(i+1)*width
            overlap=sum((max(Decimal(0),min(end,b)-max(start,a)) for a,b in union),Decimal(0))
            labels[i]['attack_event_overlap_seconds']=overlap;labels[i]['attack_event_overlap_fraction']=overlap/width
        if unsupported:warnings.append(dict(code='INFRASTRUCTURE_RECORDS_WITHOUT_SUPPORT',records=len(unsupported),message='Recorded collector placeholders preserved in diagnostics, excluded from resource means.'))
        if unfinished:warnings.append(dict(code='REQUESTS_WITHOUT_COMPLETION',request_ids=unfinished,message='No conclusion/failure time or duration invented.'))
        warnings.extend(dict(code='STAGE9_WARNING',check_id=c['check_id'],evidence=c.get('evidence',{})) for c in inputs.report.get('checks',[]) if c.get('severity')=='WARNING' and c.get('passed') is False)
        provenance=extractor_provenance()
        destination.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.feature-extract-',dir=destination.parent) as temporary:
            staging=Path(temporary)/'features';(staging/'timeseries').mkdir(parents=True);(staging/'evidence').mkdir()
            outputs=[]
            for family,rows in [('network',network),('service',service),('infrastructure',infrastructure),('labels',labels)]:
                names=LABELS if family=='labels' else FEATURES[family]
                relative=f'timeseries/{family}.csv';path=staging/relative
                with path.open('w',encoding='utf-8',newline='') as stream:
                    writer=csv.DictWriter(stream,fieldnames=KEYS+names,lineterminator='\n');writer.writeheader()
                    for i,row in enumerate(rows):
                        record=dict(run_id=inputs.manifest['run_id'],window_index=i,window_start_seconds=text_number(i*width),window_end_seconds=text_number((i+1)*width))
                        record.update({k:text_number(v) if isinstance(v,Decimal) else v for k,v in row.items()});writer.writerow(record)
                outputs.append(dict(path=relative,sha256=sha256_file(path),bytes=path.stat().st_size))
            write_json(staging/'feature_schema.json',feature_schema(version))
            if cpu_quality is not None:
                write_json(staging/'cpu_quality.json', cpu_quality)
                path = staging/'cpu_quality.json'
                outputs.append(dict(path='cpu_quality.json',sha256=sha256_file(path),bytes=path.stat().st_size))
            shutil.copyfile(inputs.report_path,staging/'evidence/stage9_validation_report.json')
            for relative in ('feature_schema.json','evidence/stage9_validation_report.json'):
                path=staging/relative;outputs.append(dict(path=relative,sha256=sha256_file(path),bytes=path.stat().st_size))
            horizon=windows*width
            manifest=dict(feature_schema_version=version,extractor_version=version,source_run_id=inputs.manifest['run_id'],
                dataset_manifest_sha256=inputs.manifest_hash,
                stage9_validation_report=dict(path='evidence/stage9_validation_report.json',sha256=inputs.report_hash,analysis_eligible=True),
                window=dict(size_seconds=text_number(width),origin_seconds='0',semantics='[start,end)',windows=windows,
                    planned_duration_seconds=text_number(duration),last_observation_seconds=text_number(maximum),grid_end_seconds=text_number(horizon),
                    horizon_policy='max(ceil(planned_duration/width),floor(last_observation/width)+1)',
                    anchors={k:text_number(decimal(status[k])) if status.get(k) is not None else None for k in ('experiment_start_timestamp','experiment_start_monotonic')},
                    tail_after_plan_seconds=text_number(max(Decimal(0),horizon-duration)),
                    after_last_observation_seconds=text_number(horizon-maximum),
                    padding_after_observations_and_plan_seconds=text_number(horizon-max(duration,maximum)),
                    padding_is_observed_coverage=False,decimal_boundary_precision=precision,mean_precision=50),
                input_files=[inputs.consumed[k] for k in sorted(inputs.consumed)],
                input_path_semantics='Relative to the source Stage 8 dataset identified by run ID and manifest SHA256; raw inputs are not copied.',
                observed_coverage={**{k:observed_span(v) for k,v in times.items()},
                    'service':observed_span(times['service_starts']+times['service_completions']),
                    'infrastructure':observed_span(times['infrastructure_supported'])},
                network_direction=dict(supported=network_supported,segment=segment if network_supported else None,
                    proxy_ip=proxy if segment=='source_proxy' else None,target_ip=proxy,
                    service_port=service_port,client_ips=sorted(clients) if clients is not None else None,
                    uses_source_causal_class=False,duplicates_removed=False),
                diagnostics=dict(infrastructure_without_support=unsupported,unfinished_request_ids=unfinished),
                detector_columns=FEATURES,labels_path='timeseries/labels.csv',warnings=warnings,
                provenance=provenance,outputs=outputs)
            if cpu_quality is not None:
                manifest['cpu_observation_contract'] = cpu_quality['contract']
                manifest['cpu_quality_path'] = 'cpu_quality.json'
                manifest['cpu_policy'] = cpu_quality['policy']
            write_json(staging/'feature_manifest.json',manifest)
            inputs.unchanged()
            if sha256_file(staging/'evidence/stage9_validation_report.json')!=inputs.report_hash:
                raise ValueError('Copied validation evidence does not match original report')
            staging.rename(destination)
        return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset',type=Path);parser.add_argument('--validation-report',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--window-size-seconds',default='1')
    parser.add_argument('--cpu-boundary-tolerance-seconds', default='0.05',
                        help='Provisional CPU alignment tolerance; freeze before scientific collection')
    args=parser.parse_args()
    try:
        manifest=extract_features(args.dataset,args.validation_report,args.output,args.window_size_seconds,
                                  cpu_boundary_tolerance_seconds=args.cpu_boundary_tolerance_seconds)
    except (ValueError,OSError,KeyError,csv.Error) as exc:
        parser.exit(1,f'Feature extraction failed: {exc}\n')
    print(json.dumps(dict(run_id=manifest['source_run_id'],windows=manifest['window']['windows'],warnings=len(manifest['warnings']),output=str(args.output))))


if __name__=='__main__':main()
