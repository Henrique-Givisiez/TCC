"""Small benign infrastructure validation, independent of campaign phase gates.

Reconciles the five existing features with raw records. PCAP decoding uses only
the standard library, independently of the realtime tcpdump text parser.
"""
import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal
import json
from pathlib import Path
import socket
import struct

from experiments.dataset_provenance import sha256_file
from experiments.validate_dataset import validate_dataset, write_report
from experiments.extract_features import extract_features


def read(path):
    return json.loads(Path(path).read_text())


def rows(path):
    with Path(path).open() as stream:
        return list(csv.DictReader(stream))


def pcap_packets(path):
    """Yield observed IPv4 TCP tuples and TCP payload, retaining retransmissions."""
    with Path(path).open('rb') as stream:
        magic = stream.read(4)
        formats = {b'\xd4\xc3\xb2\xa1':('<',1e6), b'\xa1\xb2\xc3\xd4':('>',1e6),
                   b'\x4d\x3c\xb2\xa1':('<',1e9), b'\xa1\xb2\x3c\x4d':('>',1e9)}
        endian, scale = formats[magic]
        header = stream.read(20)
        link = struct.unpack(endian+'HHIIII',header)[-1]
        offset = {1:14,113:16,276:20}[link]
        while header := stream.read(16):
            sec, fraction, size, original = struct.unpack(endian+'IIII',header)
            packet = stream.read(size)
            if len(packet) != size:
                raise ValueError('truncated PCAP record')
            ip = packet[offset:]
            if not ip or ip[0] >> 4 != 4 or ip[9] != 6:
                raise ValueError('non IPv4 TCP packet in declared segment')
            ihl = (ip[0] & 15)*4
            if int.from_bytes(ip[6:8],'big') & 0x3fff:
                raise ValueError('fragmented IP requires explicit reassembly; validation inconclusive')
            total = int.from_bytes(ip[2:4],'big')
            tcp = ip[ihl:]
            thl = (tcp[12] >> 4)*4
            if len(ip) < total or total < ihl+thl:
                raise ValueError('truncated TCP payload')
            sport,dport,seq = struct.unpack('!HHI',tcp[:8])
            yield dict(timestamp=sec+fraction/scale,src_ip=socket.inet_ntoa(ip[12:16]),
                dst_ip=socket.inet_ntoa(ip[16:20]),src_port=sport,dst_port=dport,
                payload=total-ihl-thl,seq=seq,flags=tcp[13])


def collection_checks(raw, run_id):
    """Pass/fail/N/A checks; missing essential artifacts always fail."""
    raw=Path(raw);checks=[]
    def check(name, passed, evidence=None, applicable=True):
        checks.append(dict(name=name,status=('passed' if passed else 'failed') if applicable else 'not_applicable',evidence=evidence))
    status=read(raw/'run_status.json');cfg=read(raw/'effective_config.json')
    mode=cfg.get('topology',{}).get('mode','proxy')
    essential=['source_inventory.json','request_log.csv','attack_events.csv','simulation_metrics.csv',
        'traffic_capture.csv','traffic_capture.csv.capture.json','traffic_capture.stderr','victim_stats.jsonl',
        'source_artifacts/traffic_capture.pcap','source_artifacts/traffic_capture.pcap.capture.json',
        'source_artifacts/traffic_capture.pcap.stderr','source_artifacts/aggregation_audit.json',
        'source_artifacts/clock_validation.json','source_artifacts/network_audit/comparison.json',
        'source_artifacts/network_audit/isolation.json',mode+'_artifacts/capture_metadata.json',
        mode+'_artifacts/backend_inventory.json']
    if mode=='direct':essential.append('direct_artifacts/target_identity.json')
    missing=[p for p in essential if not (raw/p).is_file()]
    check('essential_artifacts',not missing,dict(missing=missing))
    if missing:return checks
    check('completed_and_drained',status.get('status')=='completed' and status.get('producers_drained') and not status.get('errors'),status)
    for name,artifact in [('csv',raw/'traffic_capture.csv'),('pcap',raw/'source_artifacts/traffic_capture.pcap')]:
        report_path=Path(str(artifact)+'.capture.json')
        report=read(report_path) if report_path.exists() else {}
        counters=report.get('capture_counters',{})
        stderr=raw/'traffic_capture.stderr' if name=='csv' else Path(str(artifact)+'.stderr')
        check('capture_'+name,artifact.exists() and report.get('accepted') and
            counters.get('statistics_complete') and counters.get('packets_dropped_by_kernel')==0 and
            stderr.exists() and sha256_file(stderr)==report.get('capture_diagnostic_sha256') and
            status.get('capture_results',{}).get(name)==report,report)
    inventory=read(raw/'source_inventory.json')
    source_missing=[str(Path(s['source_id'])/'output'/name) for s in inventory
        for name in ('journal.jsonl','final_status.json','local_requests.csv')
        if not (raw/'source_artifacts'/s['source_id']/'output'/name).is_file()]
    check('source_artifacts',not source_missing,dict(missing=source_missing))
    check('benign_sources_only',bool(inventory) and all(s['source_type']=='normal' and s['run_id']==run_id and
        s.get('status_final',{}).get('drained') and s['status_final'].get('logger_complete') and
        not s['status_final'].get('forced') and s['status_final'].get('exit_code')==0 for s in inventory),inventory)
    check('no_offensive_events',not rows(raw/'attack_events.csv'))
    check('http_records',bool(rows(raw/'request_log.csv')) and all(r['end_elapsed_seconds'] and r['traffic_class']=='benign' for r in rows(raw/'request_log.csv')))
    check('source_aggregation',read(raw/'source_artifacts/aggregation_audit.json').get('complete'))
    check('source_clocks',read(raw/'source_artifacts/clock_validation.json').get('comparable'))
    comparison=read(raw/'source_artifacts/network_audit/comparison.json')
    check('network_audit',comparison.get('topology')==mode and bool(comparison.get('selected_interface')) and
        len(comparison.get('replies',[]))==len(inventory),comparison)
    isolation=read(raw/'source_artifacts/network_audit/isolation.json')
    from experiments.source_network_audit import validate_isolation
    isolation_valid=len(isolation.get('probes',[]))==len(inventory)
    for probe in isolation.get('probes',[]):
        try:
            validate_isolation(probe.get('probes',{}),mode)
        except RuntimeError:
            isolation_valid=False
        if probe.get('networks')!=['edos_sources']:
            isolation_valid=False
    check('network_isolation',isolation_valid,isolation)
    metrics=rows(raw/'simulation_metrics.csv')
    check('victim_metrics',any(r['active_containers_names'] for r in metrics))
    if mode=='proxy':
        monitor=raw/'proxy_artifacts/monitor_summary.json'
        m=read(monitor) if monitor.exists() else {}
        check('proxy_artifacts', all((raw/'proxy_artifacts'/n).exists() for n in
            ('proxy_access.log','proxy_error.log','monitor_samples.jsonl','monitor_summary.json','proxy_identity.json')) and
            m.get('run_id')==run_id and not m.get('thread_alive',True) and not m.get('fatal_error'),m)
    else:
        check('proxy_artifacts',True,'No proxy exists in direct topology',applicable=False)
        check('no_proxy_artifact_directory',not (raw/'proxy_artifacts').exists() and status.get('proxy_integrity') is None)
        identity=read(raw/'direct_artifacts/target_identity.json')
        check('victim_target_identity',identity.get('id')==comparison.get('target_id') and identity.get('run_id')==run_id,identity)
    return checks


def verify(raw, dataset, features):
    raw,dataset,features=map(Path,(raw,dataset,features))
    status=read(raw/'run_status.json');cfg=read(raw/'effective_config.json');mode=cfg.get('topology',{}).get('mode','proxy')
    capture=read(raw/(mode+'_artifacts')/'capture_metadata.json')
    target=capture['target_ip'];port=capture['target_port']
    sources={s['ip'] for s in read(raw/'source_inventory.json')}
    checks=collection_checks(raw,status['run_id'])
    requests=rows(raw/'request_log.csv');metrics=rows(raw/'simulation_metrics.csv');packets=rows(raw/'traffic_capture.csv')
    window=lambda t:int(Decimal(str(t)))
    ingress=Counter();payload=Counter();raw_ingress=Counter();raw_payload=Counter();starts=Counter()
    durations=defaultdict(list);cpu=defaultdict(list)
    for p in packets:
        if p['src_ip'] in sources and p['dst_ip']==target and int(p['dst_port'])==port:
            i=window(p['elapsed_seconds']);ingress[i]+=1;payload[i]+=int(p['packet_length'])
    signatures=Counter();covered=set();zero_payload=0
    for p in pcap_packets(raw/'source_artifacts/traffic_capture.pcap'):
        if p['src_ip'] in sources and p['dst_ip']==target and p['dst_port']==port:
            elapsed=p['timestamp']-status['experiment_start_timestamp']
            if elapsed < 0:raise ValueError('pre-origin packet contamination')
            i=window(elapsed);raw_ingress[i]+=1;raw_payload[i]+=p['payload'];covered.add(p['src_ip'])
            zero_payload+=p['payload']==0
            signatures[tuple(p.values())]+=1
        elif not (p['src_ip']==target and p['src_port']==port and p['dst_ip'] in sources):
            raise ValueError('PCAP packet outside segment')
    checks.append(dict(name='pcap_csv_independent_reconciliation',status='passed' if raw_ingress==ingress and raw_payload==payload and covered==sources else 'failed',
        evidence=dict(pcap_ingress=dict(raw_ingress),csv_ingress=dict(ingress),pcap_payload=dict(raw_payload),csv_payload=dict(payload),
            zero_payload_packets=zero_payload,exact_timestamp_duplicate_records=sum(n-1 for n in signatures.values() if n>1),covered_sources=sorted(covered))))
    for r in requests:
        starts[window(r['elapsed_seconds'])]+=1
        if r['end_elapsed_seconds'] and r['duration_ms']:
            durations[window(r['end_elapsed_seconds'])].append(Decimal(r['duration_ms']))
    for r in metrics:
        if r['active_containers_names']:cpu[window(r['elapsed_seconds'])].append(Decimal(r['average_cpu_percent']))
    raw_stats=[json.loads(s) for s in (raw/'victim_stats.jsonl').read_text().splitlines()]
    from simulator.stats_collector import StatsCollector
    expected_id=status['target_integrity']['id'] if mode=='direct' else read(raw/'proxy_artifacts/backend_inventory.json')[0]['id']
    checks.append(dict(name='raw_cpu_identity_scale',status='passed' if raw_stats and all(s['container_id']==expected_id and
        s['metrics']['cpu_percent']==StatsCollector._calc_cpu_percent(s) for s in raw_stats) else 'failed',evidence=dict(samples=len(raw_stats),container_id=expected_id,
            accounting='Docker cgroup total_usage includes all container processes; online_cpus * delta/container system delta * 100')))
    def mean(values):return sum(values)/len(values) if values else None
    specs=[('network','ingress_packet_count',lambda i:Decimal(ingress[i])),
           ('network','ingress_tcp_payload_length_sum_bytes',lambda i:Decimal(payload[i])),
           ('service','request_starts',lambda i:Decimal(starts[i])),
           ('service','mean_duration_ms',lambda i:mean(durations[i])),
           ('infrastructure','mean_cpu_percent',lambda i:mean(cpu[i]))]
    features_report=[]
    for family,column,expected in specs:
        series=rows(features/f'timeseries/{family}.csv');values=[];mismatches=[]
        for r in series:
            i=int(r['window_index']);value=Decimal(r[column]) if r[column] else None;want=expected(i)
            if value is not None:values.append(value)
            if (value is None)!=(want is None) or (value is not None and abs(value-want)>Decimal('1e-20')):
                mismatches.append(dict(window=i,observed=str(value),expected=str(want)))
        features_report.append(dict(column=column,windows=len(series),valid=len(values),null=len(series)-len(values),
            minimum=str(min(values)) if values else None,maximum=str(max(values)) if values else None,
            status='passed' if not mismatches else 'failed',mismatches=mismatches))
    return dict(topology=mode,run_id=status['run_id'],checks=checks,features=features_report,
        accepted=all(c['status']!='failed' for c in checks+features_report))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,required=True);parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    report=validate_dataset(args.dataset)
    report_path=args.output/'dataset_validation.json';write_report(report,report_path,args.dataset)
    if not report['analysis_eligible']:raise RuntimeError('Dataset validation not eligible; see report')
    extract_features(args.dataset,report_path,args.output/'features')
    result=verify(args.raw,args.dataset,args.output/'features')
    (args.output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(accepted=result['accepted'],features=result['features']),indent=2))
    if not result['accepted']:raise RuntimeError('Infrastructure verification failed; see verification.json')


if __name__=='__main__':main()
