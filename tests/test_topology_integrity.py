"""Deterministic collection gates and independent PCAP decoding."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from experiments.validate_topology_run import collection_checks, pcap_packets
from experiments.dataset_provenance import sha256_file


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)

    def put(self,path,value):
        p=self.root/path;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(value) if not isinstance(value,str) else value)

    def fixture(self,mode):
        self.put('effective_config.json',{'topology':{'mode':mode}})
        status=dict(status='completed',producers_drained=True,errors=[],capture_results={},proxy_integrity=None)
        for name,artifact in [('csv','traffic_capture.csv'),('pcap','source_artifacts/traffic_capture.pcap')]:
            self.put(artifact,'synthetic test fixture')
            stderr='traffic_capture.stderr' if name=='csv' else artifact+'.stderr'
            self.put(stderr,'diagnostic')
            report=dict(accepted=True,capture_counters=dict(statistics_complete=True,packets_dropped_by_kernel=0),
                capture_diagnostic_sha256=sha256_file(self.root/stderr))
            self.put(artifact+'.capture.json',report);status['capture_results'][name]=report
        self.put('run_status.json',status)
        self.put('source_inventory.json',[dict(source_id='normal_1',source_type='normal',run_id='run',status_final=dict(drained=True,logger_complete=True,forced=False,exit_code=0))])
        for name in ('journal.jsonl','final_status.json','local_requests.csv'):
            self.put('source_artifacts/normal_1/output/'+name,'synthetic test fixture')
        self.put('request_log.csv','end_elapsed_seconds,traffic_class\n1,benign\n')
        self.put('attack_events.csv','event_id\n')
        self.put('simulation_metrics.csv','active_containers_names\nvictim\n')
        self.put('victim_stats.jsonl','{}\n')
        self.put('source_artifacts/aggregation_audit.json',{'complete':True})
        self.put('source_artifacts/clock_validation.json',{'comparable':True})
        self.put('source_artifacts/network_audit/comparison.json',dict(topology=mode,target_id='victim',selected_interface='bridge',replies=[{}]))
        self.put('source_artifacts/network_audit/isolation.json',{'probes':[dict(
            probes=dict(victim_name='CONNECTED' if mode=='direct' else 'gaierror',victim_ip='TimeoutError'),networks=['edos_sources'])]})
        self.put(mode+'_artifacts/capture_metadata.json',{})
        self.put(mode+'_artifacts/backend_inventory.json',[])
        if mode=='direct':self.put('direct_artifacts/target_identity.json',dict(id='victim',run_id='run'))

    def checks(self):return {c['name']:c for c in collection_checks(self.root,'run')}

    def test_proxy_artifacts_required(self):
        self.fixture('proxy');self.assertEqual(self.checks()['proxy_artifacts']['status'],'failed')
        for name in ['proxy_access.log','proxy_error.log','monitor_samples.jsonl','proxy_identity.json']:
            self.put('proxy_artifacts/'+name,'synthetic')
        self.put('proxy_artifacts/monitor_summary.json',dict(run_id='run',thread_alive=False,fatal_error=None))
        self.assertEqual(self.checks()['proxy_artifacts']['status'],'passed')

    def test_direct_proxy_not_applicable(self):
        self.fixture('direct');checks=self.checks()
        self.assertEqual(checks['proxy_artifacts']['status'],'not_applicable')
        self.assertTrue(all(c['status']!='failed' for c in checks.values()))

    def test_missing_essential_capture_source_or_victim_fails(self):
        self.fixture('direct')
        for name in ['traffic_capture.csv','source_inventory.json','victim_stats.jsonl','direct_artifacts/target_identity.json']:
            p=self.root/name;data=p.read_bytes();p.unlink()
            self.assertEqual(self.checks()['essential_artifacts']['status'],'failed')
            p.write_bytes(data)

    def test_capture_loss_is_failure(self):
        self.fixture('direct');p=self.root/'traffic_capture.csv.capture.json';r=json.loads(p.read_text())
        r['capture_counters']['packets_dropped_by_kernel']=1;p.write_text(json.dumps(r))
        self.assertEqual(self.checks()['capture_csv']['status'],'failed')

    def test_pcap_counts_zero_payload_and_retransmission_records(self):
        path=self.root/'test.pcap'
        header=b'\xd4\xc3\xb2\xa1'+struct.pack('<HHIIII',2,4,0,0,65535,1)
        records=[]
        for micros,payload in [(0,b''),(500000,b'abc'),(600000,b'abc')]:
            ip=bytearray(20);ip[0]=0x45;ip[2:4]=struct.pack('!H',40+len(payload));ip[9]=6
            ip[12:20]=bytes([172,20,0,3,172,20,0,2])
            tcp=bytearray(20);tcp[:8]=struct.pack('!HHI',40000,80,10);tcp[12]=0x50
            packet=bytes(14)+ip+tcp+payload
            records.append(struct.pack('<IIII',100,micros,len(packet),len(packet))+packet)
        path.write_bytes(header+b''.join(records));packets=list(pcap_packets(path))
        self.assertEqual([p['payload'] for p in packets],[0,3,3])
        self.assertEqual([p['seq'] for p in packets],[10,10,10])
        self.assertEqual(len(packets),3)
