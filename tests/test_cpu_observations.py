"""C1.2-CPU.2: synthetic clocks/counters/files only; never Docker/network IO."""
from copy import deepcopy
from decimal import Decimal, localcontext, ROUND_UP
import csv
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from simulator.cpu_observations import CONTRACT, MARKER, SAMPLES, SUMMARY, delta, next_slot
from simulator.stats_collector import StatsCollector
from experiments.cpu_features import assign_cpu, validate_evidence
from experiments.dataset_provenance import sha256_file


def row(sequence, t, cpu=None, *, cid='victim', generation=None, error=None):
    t = Decimal(str(t))
    r = dict(schema_version=1, contract=CONTRACT, run_id='run1', sequence=sequence,
        container_id=cid, generation=generation or dict(started_at='boot1', restarts=0),
        scheduled_seconds=float(t), call_start_seconds=float(t), call_end_seconds=float(t+Decimal('.01')),
        received_seconds=float(t+Decimal('.01')), call_start_epoch=float(100+t),
        call_end_epoch=float(100+t+Decimal('.01')), delay_seconds=0,
        docker_read='1970-01-01T00:01:'+format(Decimal(40)+t+Decimal('.005'), '012.9f')+'Z',
        snapshot_received=error is None, error=error,
        counters=dict(total_usage=int(t*10**9) if cpu is None else cpu,
                      system_cpu_usage=int(t*4*10**9), online_cpus=4))
    return r


def replay(raw):
    reference = None; result = []
    for r in deepcopy(raw):
        derived, reference = delta(r, reference); r.update(derived); result.append(r)
    return result


def contract(rows):
    marker = dict(schema_version=1, contract=CONTRACT, run_id='run1', container_ids=['victim'],
                  origin_epoch=100, origin_monotonic=50, interval_seconds=1,
                  samples=SAMPLES, summary=SUMMARY)
    summary = dict(schema_version=1, contract=CONTRACT, run_id='run1', worker_finished=True,
                   fatal_error=None, attempts=len(rows), snapshots=sum(r['snapshot_received'] for r in rows),
                   missed_opportunities=0)
    status = dict(run_id='run1', experiment_start_timestamp=100, experiment_start_monotonic=50,
                  cpu_observation_contract=CONTRACT)
    return marker, summary, status


class DeltaTests(unittest.TestCase):
    def test_first_positive_zero_and_more_than_two_cores(self):
        r = replay([row(1,'.98'),row(2,'1.98'),row(3,'2.98',cpu=1980000000),row(4,'3.98',cpu=5980000000)])
        self.assertEqual([x['state'] for x in r],['first_read','valid','valid','valid'])
        self.assertEqual([None if x['cpu_percent'] is None else Decimal(x['cpu_percent']) for x in r],[None,100,0,400])
        self.assertEqual(r[1]['reference_sequence'],1)

    def test_bad_counters_regressions_and_missing_support(self):
        a = row(1,'.98')
        for field, value in [('total_usage',None),('system_cpu_usage',None),('online_cpus',0)]:
            b = row(2,'1.98'); b['counters'][field]=value
            self.assertEqual(replay([a,b])[1]['state'],'invalid_snapshot')
        for field in ('total_usage','system_cpu_usage'):
            b = row(2,'1.98'); b['counters'][field]=0
            self.assertEqual(replay([a,b])[1]['state'],'counter_reset')

    def test_repeated_regressive_and_generation(self):
        a = row(1,'.98')
        for stamp in (a['docker_read'],'1970-01-01T00:01:40.000000000Z'):
            b = row(2,'1.98'); b['docker_read']=stamp
            # An out-of-bracket timestamp is invalid too; a narrow bracket is mandatory.
            self.assertEqual(replay([a,b])[1]['state'],'invalid_timestamp')
            self.assertIsNone(replay([a,b])[1]['cpu_percent'])
        for kw in [dict(cid='other'),dict(generation=dict(started_at='boot2',restarts=1))]:
            self.assertEqual(replay([a,row(2,'1.98',**kw)])[1]['state'],'generation_changed')

    def test_failure_and_recovery_keeps_long_interval(self):
        r = replay([row(1,'.98'), row(2,'1.98',error='Timeout: API'),row(3,'3.98')])
        self.assertEqual(r[1]['state'],'acquisition_error')
        self.assertEqual(r[2]['reference_sequence'],1)
        self.assertEqual(r[2]['observed_interval_seconds'],'3.000000000')
        self.assertEqual(Decimal(r[2]['cpu_percent']),100)

    def test_agenda_skips_backlog_without_adding_call_duration(self):
        self.assertEqual(next_slot(1,1.2,1),(2,0))
        self.assertEqual(next_slot(1,4.2,1),(5,3))
        self.assertEqual(next_slot(1,2,1),(2,0))


class AssignmentTests(unittest.TestCase):
    def assign(self, raw, tolerance='.05'):
        rows = replay(raw); m,s,status = contract(rows)
        return assign_cpu(m,rows,s,status,8,tolerance)

    def test_aligned_missing_no_cache_and_cov_support(self):
        values,q = self.assign([row(1,'.98'),row(2,'1.98')])
        self.assertEqual(values,[None,Decimal(100),None,None,None,None,None,None])
        self.assertEqual(q['potential_decisions']['cov'],0)
        self.assertEqual(q['valid_windows'],1)
        self.assertTrue(q['policy']['provisional'])

    def test_misaligned_crossing_long_and_late(self):
        for raw, reason in [([row(1,'.7'),row(2,'1.7')],'insufficient_boundary_alignment'),
                            ([row(1,'.98'),row(2,'3.98')],'insufficient_boundary_alignment'),
                            ([row(1,'.98'),row(2,'2.01')],'received_after_window_closure')]:
            values,q = self.assign(raw)
            self.assertTrue(all(x is None for x in values))
            self.assertIn(reason,[x['reason'] for x in q['rejected']])

    def test_duplicates_and_stored_cpu_corruption_rejected(self):
        rows = replay([row(1,'.98'),row(2,'1.98')]);m,s,status=contract(rows)
        for corrupt in ('duplicate','cpu'):
            bad = deepcopy(rows)
            if corrupt=='duplicate':bad.append(deepcopy(bad[-1]))
            else:bad[-1]['cpu_percent']='999'
            with self.assertRaises(ValueError):assign_cpu(m,bad,s,status,8)

    def test_multiple_aligned_deltas_in_one_window_rejected_without_selection(self):
        # Two short deltas near the same boundaries cannot both cover ~1s:
        # the second receives an alignment rejection, never a duplicate allocation.
        values,q=self.assign([row(1,'.98'),row(2,'1.98'),row(3,'2.00')])
        self.assertEqual(q['valid_windows'],1)
        self.assertEqual(len(q['assignments']),1)
        self.assertIn('insufficient_boundary_alignment',[r['reason'] for r in q['rejected']])

    def test_unknown_version_fatal_and_wrong_run(self):
        rows = replay([row(1,'.98')]);m,s,status=contract(rows)
        for target,key,value in [('marker','schema_version',2),('summary','fatal_error','disk error'),('marker','run_id','other')]:
            a,b=deepcopy(m),deepcopy(s);(a if target=='marker' else b)[key]=value
            with self.assertRaises(ValueError):validate_evidence(a,rows,b,status)

    def test_policy_is_explicit_and_does_not_recover_precision(self):
        raw=[row(1,'.9'),row(2,'1.9')]
        self.assertEqual(self.assign(raw)[1]['valid_windows'],0)
        self.assertEqual(self.assign(raw,'.11')[1]['valid_windows'],1)
        self.assertEqual(self.assign(raw,'.11')[1]['policy']['boundary_tolerance_seconds'],'0.11')
        for value in ('-.01','.5','NaN'):
            with self.assertRaises(ValueError):self.assign(raw,value)

    def test_replay_context_independent_and_consecutive_support(self):
        raw=[row(i+1,Decimal('.98')+i) for i in range(7)]
        values,q=self.assign(raw)
        self.assertEqual(q['potential_decisions']['cov'],1)
        with localcontext() as ctx:
            ctx.prec=6;ctx.rounding=ROUND_UP
            self.assertEqual(self.assign(raw),(values,q))


class CollectorTests(unittest.TestCase):
    def fake(self, root, *, fail=False, repeat=False):
        from simulator.ground_truth import ExperimentClock
        clock = SimpleNamespace(now=50., monotonic_initial=50., epoch_initial=100.)
        client=MagicMock()
        c=SimpleNamespace(id='victim',name='victim',attrs=dict(State=dict(Status='running',StartedAt='boot1'),RestartCount=0))
        collector=StatsCollector(client)
        collector.update_containers([c]);collector.bind_cpu('run1',clock,root/SAMPLES)
        def wait(seconds):clock.now+=seconds
        collector._stop_evt.wait=wait
        count=[0]
        def stats(**kwargs):
            self.assertEqual(kwargs,dict(stream=False,one_shot=True))
            count[0]+=1; clock.now+=.005
            if count[0]==3:collector._stop_evt.set()
            if fail and count[0]==2:raise TimeoutError('API timeout')
            t=clock.now-50
            stamp=100+t if not repeat or count[0]==1 else 100.98
            from datetime import datetime,timezone
            read=datetime.fromtimestamp(stamp,timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')
            return dict(read=read,cpu_stats=dict(cpu_usage=dict(total_usage=int(t*1e9)),system_cpu_usage=int(t*4e9),online_cpus=4),
                        memory_stats=dict(usage=2*1024**2,stats=dict(cache=1024**2)))
        c.stats=stats;client.containers.get.return_value=c
        return collector,clock

    def run_fake(self, collector, clock):
        with patch('simulator.stats_collector.time.monotonic',lambda:clock.now), \
             patch('simulator.stats_collector.time.time',lambda:100+clock.now-50):
            collector._run()

    def test_auditable_success_failure_freshness_and_memory(self):
        for fail in (False,True):
            with tempfile.TemporaryDirectory() as t:
                root=Path(t);c,clock=self.fake(root,fail=fail)
                c._on_acquisition=MagicMock();self.run_fake(c,clock)
                rows=[json.loads(x) for x in (root/SAMPLES).read_text().splitlines()]
                self.assertEqual(len(rows),3)
                self.assertEqual(c._on_acquisition.call_count,2 if fail else 3)
                self.assertEqual(c.get_snapshot()['victim']['mem_app_mb'],1)
                self.assertEqual(rows[-1]['reference_sequence'],1 if fail else 2)
                validate_evidence(json.loads((root/MARKER).read_text()),rows,json.loads((root/SUMMARY).read_text()),contract(rows)[2])

    def test_thread_stop_and_fatal_persistence(self):
        with tempfile.TemporaryDirectory() as t:
            c,clock=self.fake(Path(t)); c._t=MagicMock();c._t.is_alive.return_value=True
            with self.assertRaisesRegex(RuntimeError,'still alive'):c.stop()
            c._t.is_alive.return_value=False;c.failure='disk'
            with self.assertRaisesRegex(RuntimeError,'disk'):c.stop()
        with tempfile.TemporaryDirectory() as t:
            c,clock=self.fake(Path(t))
            with patch('simulator.stats_collector.os.fsync',side_effect=OSError('disk')):
                self.run_fake(c,clock)
            self.assertIn('disk',c.failure)

    def test_duplicate_read_cannot_refresh_hook(self):
        with tempfile.TemporaryDirectory() as t:
            c,clock=self.fake(Path(t),repeat=True);c._on_acquisition=MagicMock()
            self.run_fake(c,clock)
            self.assertEqual(c._on_acquisition.call_count,1)
            self.assertIsNone(c.get_snapshot()['victim']['read_ts'])

    def test_real_thread_with_mock_client_closes(self):
        c=StatsCollector(MagicMock());c.update_containers([])
        c.start();c.stop(timeout=1)
        self.assertFalse(c._t.is_alive());self.assertIsNone(c.failure)

    def test_dedicated_client_and_generation_identity_errors(self):
        with tempfile.TemporaryDirectory() as t:
            c,clock=self.fake(Path(t));c.dedicated_client=True
            client=c.client
            with patch('simulator.stats_collector.docker.DockerClient',return_value=client) as factory:
                self.run_fake(c,clock)
            factory.assert_called_once_with(base_url='unix:///var/run/docker.sock',timeout=2.0)
            client.close.assert_called_once()
        for attrs in [dict(State=dict(Status='exited')),dict(State=dict(Status='running',StartedAt=''),RestartCount=0)]:
            c=StatsCollector(MagicMock());c.client.containers.get.return_value=SimpleNamespace(id='victim',attrs=attrs)
            r,_,_=c._acquire('victim',0,0)
            self.assertEqual(r['state'],'acquisition_error');self.assertTrue(r['reference_invalidated'])

    def test_slow_calls_record_skipped_opportunities_without_backlog(self):
        with tempfile.TemporaryDirectory() as t:
            c,clock=self.fake(Path(t));original=c.client.containers.get.return_value.stats
            def slow(**kwargs):
                clock.now+=2.2
                return original(**kwargs)
            c.client.containers.get.return_value.stats=slow
            self.run_fake(c,clock)
            rows=[json.loads(line) for line in (Path(t)/SAMPLES).read_text().splitlines()]
            summary=json.loads((Path(t)/SUMMARY).read_text())
            self.assertEqual(len(rows),3)
            self.assertEqual([r['missed_opportunities_before'] for r in rows],[0,2,2])
            self.assertEqual(summary['missed_opportunities'],6)
            self.assertGreater(Decimal(rows[-1]['observed_interval_seconds']),2)


class DatasetCPUTests(unittest.TestCase):
    def setUp(self):
        from tests.test_dataset_validation import ScientificValidationTests
        self.fixture=ScientificValidationTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root;self.run=self.fixture.run

    def export_new(self, raw=None):
        from experiments.export_dataset import export_run
        from experiments.validate_dataset import validate_dataset
        rows=replay(raw or [row(1,'.98'),row(2,'1.98'),row(3,'2.98')]);m,s,status=contract(rows)
        old=json.loads((self.run/'run_status.json').read_text());old.update(status)
        for name,value in [('run_status.json',old),(MARKER,m),(SUMMARY,s)]:
            (self.run/name).write_text(json.dumps(value))
        (self.run/SAMPLES).write_text(''.join(json.dumps(r)+'\n' for r in rows))
        self.dataset=self.root/'cpu-dataset';export_run(self.run,self.dataset)
        report=validate_dataset(self.dataset);self.assertTrue(report['dataset_valid'],report)
        self.report=self.root/'cpu-report.json';self.report.write_text(json.dumps(report))
        return rows

    def test_export_hashes_determinism_and_other_features_unchanged(self):
        from experiments.extract_features import extract_features
        from experiments.validate_dataset import validate_dataset
        oldreport=self.root/'old-report.json';oldreport.write_text(json.dumps(validate_dataset(self.fixture.dataset)))
        oldout=self.root/'old';extract_features(self.fixture.dataset,oldreport,oldout)
        self.export_new()
        a,b=self.root/'a',self.root/'b'
        m=extract_features(self.dataset,self.report,a);extract_features(self.dataset,self.report,b)
        self.assertEqual(m['feature_schema_version'],2)
        for path in a.rglob('*'):
            if path.is_file():self.assertEqual(path.read_bytes(),(b/path.relative_to(a)).read_bytes())
        for family in ('network','service','labels'):
            self.assertEqual((oldout/f'timeseries/{family}.csv').read_bytes(),(a/f'timeseries/{family}.csv').read_bytes())
        def csvrows(path):
            with path.open() as stream:return list(csv.DictReader(stream))
        old,new=csvrows(oldout/'timeseries/infrastructure.csv'),csvrows(a/'timeseries/infrastructure.csv')
        self.assertEqual([r['mean_memory_mib'] for r in old],[r['mean_memory_mib'] for r in new])
        self.assertEqual(new[0]['mean_cpu_percent'],'');self.assertEqual(Decimal(new[1]['mean_cpu_percent']),100)
        self.assertEqual(new[3]['mean_cpu_percent'],'')
        manifest=json.loads((self.dataset/'dataset_manifest.json').read_text())
        for entry in manifest['files']:
            self.assertEqual(sha256_file(self.dataset/entry['path']),entry['sha256'])
        self.assertIn('evidence/other/'+SAMPLES,[e['path'] for e in m['input_files']])

    def test_missing_new_artifact_does_not_fallback(self):
        from experiments.validate_dataset import validate_dataset
        self.export_new();(self.dataset/'evidence/other'/SAMPLES).unlink()
        report=validate_dataset(self.dataset)
        self.assertFalse(report['dataset_valid'])
        self.assertTrue(any(c['check_id']=='CPU_EVIDENCE_VALID' and not c['passed'] for c in report['checks']))

    def test_cpu_evidence_tampering_fails_even_before_feature_extraction(self):
        from experiments.extract_features import extract_features
        self.export_new()
        (self.dataset/'evidence/other'/SAMPLES).write_text('{}\n')
        with self.assertRaisesRegex(ValueError,'hash/size mismatch'):
            extract_features(self.dataset,self.report,self.root/'tampered-features')

    def test_new_status_without_marker_and_unknown_contract_cannot_fallback(self):
        from experiments.validate_dataset import validate_dataset
        self.export_new()
        markerpath=self.dataset/'evidence/other'/MARKER
        original=json.loads(markerpath.read_text());original['schema_version']=99
        markerpath.write_text(json.dumps(original));self.fixture.dataset=self.dataset
        self.fixture.refresh('evidence/other/'+MARKER)
        self.assertFalse(validate_dataset(self.dataset)['dataset_valid'])

    def test_schema_legacy_and_unknown(self):
        from experiments.feature_schema import feature_schema
        self.assertEqual(feature_schema()['feature_schema_version'],1)
        self.assertNotEqual(feature_schema(1),feature_schema(2))
        for version in (3,True,'2'):
            with self.assertRaises(ValueError):feature_schema(version)

    def test_scientific_loader_and_four_methods_accept_version_two(self):
        from experiments.extract_features import extract_features
        from analysis.detection.scientific import data, engine
        from analysis.detection.detectors.zscore import ZScore, zscore_spec
        self.fixture.config['duration_seconds']=390
        (self.run/'effective_config.json').write_text(json.dumps(self.fixture.config))
        self.export_new([row(1,'.98'),row(2,'1.98'),row(3,'2.98',cpu=3980000000)])
        out=self.root/'features';m=extract_features(self.dataset,self.report,out)
        receipt=dict(entry_id='fixture',run_id='run1',features=str(out),dataset=str(self.dataset),
            feature_manifest_sha256=sha256_file(out/'feature_manifest.json'),
            dataset_manifest_sha256=sha256_file(self.dataset/'dataset_manifest.json'))
        with patch.object(data,'validate_membership'):
            src=data.load_source(dict(id='fixture',partition='BASELINE',seed=42),receipt,
                                 'infrastructure','mean_cpu_percent',authority={})
        self.assertEqual(src.series.feature_schema_version,2)
        parameters=ZScore().fit((src.series,),zscore_spec().config)
        for method in ('zscore','cov','ewma','cusum-freeze'):
            trace=engine.trace(src.series,method,parameters,Decimal(1))
            self.assertEqual(len(trace),390)
            self.assertIsNone(trace[0]['decision'])
        # Rebinding feature file hashes is insufficient to forge CPU scalars.
        path=out/'timeseries/infrastructure.csv'
        with path.open() as f:rows=list(csv.DictReader(f))
        rows[1]['mean_cpu_percent']='999'
        with path.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
        for ref in m['outputs']:
            if ref['path']=='timeseries/infrastructure.csv':ref.update(sha256=sha256_file(path),bytes=path.stat().st_size)
        (out/'feature_manifest.json').write_text(json.dumps(m))
        receipt['feature_manifest_sha256']=sha256_file(out/'feature_manifest.json')
        with patch.object(data,'validate_membership'),self.assertRaisesRegex(ValueError,'CPU scalar'):
            data.load_source(dict(id='fixture',partition='BASELINE',seed=42),receipt,
                             'infrastructure','mean_cpu_percent',authority={})


class OperationalCPUTests(unittest.TestCase):
    def test_one_shot_preserves_memory_oom_restarts_identity_and_state(self):
        from simulator.exploratory_operations import Operations
        from tests.test_exploratory_operations import policy, IMAGE
        for change,reason in [({},None),({'memory':101},'container_memory'),({'oom':True},'oom_or_restart'),
                              ({'restarts':1},'oom_or_restart'),({'image':'other'},'image'),
                              ({'status':'exited'},'stopped'),({'missing_memory':True},'memory_stats')]:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as t:
                op=Operations(policy(),{'victim':IMAGE},t);op.owned={'victim':'victim'}
                c=MagicMock();c.attrs=dict(Image=change.get('image',IMAGE),
                    State=dict(Status=change.get('status','running'),OOMKilled=change.get('oom',False)),
                    RestartCount=change.get('restarts',0))
                c.stats.return_value={} if change.get('missing_memory') else dict(memory_stats=dict(usage=change.get('memory',10)))
                client=MagicMock();client.containers.get.return_value=c
                with patch('experiments.capacity_exploration.host_snapshot',return_value=dict(available_bytes=100)), \
                     patch('experiments.capacity_exploration.tree_bytes',return_value=0),patch.object(op,'persist'):
                    if reason:
                        with self.assertRaises((RuntimeError,KeyError)):op.observe(client,None)
                    else:
                        op.observe(client,None)
                        self.assertEqual(op.report['observations'][-1]['containers'][0]['memory'],10)
                        c.stats.assert_called_once_with(stream=False,one_shot=True)


if __name__=='__main__':unittest.main()
