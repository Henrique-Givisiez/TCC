"""Synthetic offline inputs: no Docker, capture or generators."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from experiments.exploratory_analysis import analyze, analyze_run, digest, ratio
from experiments.summarize_diagnostics import csv_rows
from experiments.export_dataset import placement


def dump(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v)+'\n')


def csvfile(p,rows,fields):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)


def fixture(root,mode='a2',role='M_A',n=2,rate=8,cpu=.01):
    from tests.test_exploratory_operations import cfg
    from simulator.request_logger import REQUEST_FIELDS
    if mode=='a2':n=2;rate=1
    duration=60 if mode=='a2' else 150
    endpoint='/expensive' if role.startswith('E') else '/medium'
    c=json.loads(cfg(n,4 if mode=='a2' else 64,duration,endpoint,rate).to_json());c['id']='fixture'
    dump(root/'effective_config.json',c)
    dump(root/'run_status.json',dict(run_id=role,experiment_id='fixture',status='completed',end_reason='simulation_end',producers_drained=True,errors=[],experiment_start_monotonic=100))
    dump(root/'run_provenance.json',dict(run_id=role))
    dump(root/'operational_policy.json',dict(certification='completed',procedure_completed=True,execution={'sha256':digest(root/'run_status.json')},images={'victim':'image','source':'source'}))
    dump(root/'diagnostics/metadata.json',dict(run_id=role,origin_monotonic=100,victim_image_id='image',source_image='source',source_sha256={}))
    dump(root/'diagnostics/victim_clock_validation.json',dict(comparable=True))
    dump(root/'source_artifacts/clock_validation.json',dict(comparable=True))
    for p in ['traffic_capture.csv.capture.json','source_artifacts/traffic_capture.pcap.capture.json']:
        dump(root/p,dict(accepted=True,capture_counters={'packets_dropped_by_kernel':0}))
    times=[0,29.9,30,149.9,150] if mode=='a1' else [0,9.9,10,59.9]
    rows=[];events=[];own={i:[] for i in range(n)}
    for i,t in enumerate(times):
        key='request'+str(i);idx=i%n
        r=dict.fromkeys(REQUEST_FIELDS,'');r.update(run_id=role,request_id=key,generator='normal',traffic_class='benign',worker_id=idx,target_url='http://edos_service:80'+endpoint,elapsed_seconds=t,end_elapsed_seconds=t+.1,duration_ms=100,http_status=200,outcome='response')
        rows.append(r);own[idx].append(r)
        events.extend([dict(kind='handler_started',request_id=key,endpoint=endpoint),
                       dict(kind='handler_finished',request_id=key,endpoint=endpoint,work_cpu_seconds=cpu,work_submitted_at=100+t,work_started_at=100+t+.001,work_finished_at=100+t+.01,worker_clock={'time_namespace':'ns','pid':1})])
    p=root/'diagnostics/victim/events.jsonl';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(''.join(json.dumps(e)+'\n' for e in events))
    dump(root/'diagnostics/victim/events.summary.json',dict(complete=True,written=len(events),clock={'time_namespace':'ns'}))
    inventory=[]
    for i in range(n):
        sid='normal_'+str(i+1);inventory.append(dict(source_id=sid,run_id=role,source_type='normal',worker_index=i))
        base=root/'source_artifacts'/sid/'output';items=[]
        for r in own[i]:
            items.extend([dict(kind='request_begin',payload=r),dict(kind='request_finish',payload=r)])
        items.append(dict(kind='source_closed',payload={'elapsed_seconds':duration+.2}))
        for seq,item in enumerate(items,1):item.update(sequence=seq,run_id=role,source_id=sid)
        base.mkdir(parents=True,exist_ok=True);(base/'journal.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in items))
        dump(base/'diagnostics/events.summary.json',dict(complete=True))
        dump(base/'final_status.json',dict(run_id=role,drained=True,logger_complete=True))
    dump(root/'source_inventory.json',inventory)
    csvfile(root/'request_log.csv',rows,REQUEST_FIELDS)
    csvfile(root/'simulation_metrics.csv',[dict(run_id=role,elapsed_seconds=t,average_cpu_percent=40,active_containers_names='victim') for t in times],['run_id','elapsed_seconds','average_cpu_percent','active_containers_names'])
    return dict(path=str(root),role=role)


def mutate_events(root,fn):
    p=root/'diagnostics/victim/events.jsonl';rows=[json.loads(l) for l in p.read_text().splitlines()];fn(rows)
    p.write_text(''.join(json.dumps(x)+'\n' for x in rows))
    dump(root/'diagnostics/victim/events.summary.json',dict(complete=True,written=len(rows),clock={'time_namespace':'ns'}))


class AnalysisTests(unittest.TestCase):
    def test_a2_ratios_bins_and_reproducibility(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);specs=[fixture(root/r,role=r,cpu=.1 if r.startswith('E') else .01) for r in ['M_A','E_A','E_B','M_B']]
            before={str(p):digest(p) for p in root.rglob('*') if p.is_file()}
            a=analyze('a2',specs,root/'out1');self.assertTrue(all(r['eligible'] for r in a['runs']),a)
            analyze('a2',specs,root/'out2')
            x=json.loads((root/'out1/ratios.json').read_text());self.assertAlmostEqual(x['global_ratio'],10)
            self.assertAlmostEqual(x['E_A_over_M_A'],10);self.assertAlmostEqual(x['E_B_over_M_B'],10)
            for p in (root/'out1').iterdir():self.assertEqual(p.read_bytes(),(root/'out2'/p.name).read_bytes())
            self.assertTrue(all(digest(p)==v for p,v in before.items()))
            with self.assertRaises(FileExistsError):analyze('a2',specs,root/'out1')
            self.assertEqual(a['runs'][0]['temporal'][2]['n'],0)

    def test_a2_bad_cpu_and_zero(self):
        for value in [-1,float('nan'),float('inf'),'bad',None,0]:
            with self.subTest(value=value),tempfile.TemporaryDirectory() as t:
                root=Path(t);spec=fixture(root,cpu=value);r=analyze_run(spec,'a2')
                if value==0:
                    self.assertTrue(r['eligible'],r);self.assertEqual(r['counts']['cpu_zero'],4)
                else:self.assertFalse(r['eligible']);self.assertEqual(r['counts']['operations_invalid'],4)
        self.assertIsNone(ratio(1,0));self.assertIsNone(ratio(None,1))

    def test_missing_duplicate_orphan_endpoint_and_clock(self):
        mutations=[lambda e:e[1].pop('work_cpu_seconds'),lambda e:e.append(dict(e[1])),
                   lambda e:e[1].update(request_id='orphan'),lambda e:e[1].update(endpoint='/light'),
                   lambda e:e[1].update(run_id='foreign'),lambda e:e[1].update(worker_clock={})]
        for fn in mutations:
            with self.subTest(fn=fn),tempfile.TemporaryDirectory() as t:
                root=Path(t);spec=fixture(root);mutate_events(root,fn)
                self.assertFalse(analyze_run(spec,'a2')['eligible'])

    def test_a1_boundaries_metrics_and_shapes(self):
        for n,rate in [(2,8),(4,4),(2,16),(4,8)]:
            with tempfile.TemporaryDirectory() as t:
                spec=fixture(Path(t),mode='a1',n=n,rate=rate);r=analyze_run(spec,'a1')
                self.assertTrue(r['eligible'],r)
                warm,main=r['phases'];self.assertEqual(warm['starts'],2);self.assertEqual(main['starts'],2)
                self.assertEqual(main['started_rps'],2/120);self.assertEqual(main['cpu_docker_percent']['mean'],40)
                self.assertAlmostEqual(main['http_seconds']['mean'],.1)
                self.assertAlmostEqual(main['worker_wait_seconds']['mean'],.001)
                self.assertEqual(main['success_fraction_per_started'],1)
                self.assertEqual(main['completions_after_boundary'],1)
                self.assertEqual(main['work_started'],2);self.assertIsNotNone(main['pending_peak_reconstructed'])

    def test_incomplete_config_missing_file_and_no_metrics(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);spec=fixture(root,mode='a1')
            c=json.loads((root/'effective_config.json').read_text());c['duration_seconds']=20;dump(root/'effective_config.json',c)
            self.assertFalse(analyze_run(spec,'a1')['eligible'])
            (root/'effective_config.json').unlink()
            result=analyze('a1',[spec],root.parent/(root.name+'-analysis'))
            self.assertFalse(result['runs'][0]['eligible'])
            import shutil;shutil.rmtree(root.parent/(root.name+'-analysis'))
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);spec=fixture(root,mode='a1')
            csvfile(root/'simulation_metrics.csv',[],['run_id','elapsed_seconds','average_cpu_percent','active_containers_names'])
            r=analyze_run(spec,'a1');self.assertIsNone(r['phases'][1]['cpu_docker_percent']['mean'])

    def test_exported_reader_and_hash_tampering(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);spec=fixture(root/'raw');raw=root/'raw';dest=root/'dataset';dest.mkdir();files=[]
            for p in raw.rglob('*'):
                if not p.is_file():continue
                name=placement(p.relative_to(raw))[0];q=dest/name;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes())
                files.append(dict(path=name,bytes=q.stat().st_size,sha256=digest(q)))
            dump(dest/'dataset_manifest.json',dict(run_id='M_A',files=files))
            # Bind a final raw certificate to the exported snapshot, as I1.1 specifies.
            cert=json.loads((raw/'operational_policy.json').read_text());cert['export']={'sha256':digest(dest/'dataset_manifest.json')};dump(root/'final.json',cert)
            dspec=dict(path=str(dest),role='M_A',certification=str(root/'final.json'))
            self.assertTrue(analyze_run(dspec,'a2')['eligible'])
            (dest/'raw/service/request_log.csv').write_text('changed')
            self.assertFalse(analyze_run(dspec,'a2')['eligible'])

    def test_requests_missing_end_duplicate_and_foreign(self):
        from simulator.request_logger import REQUEST_FIELDS
        changes=[lambda r:r.update(end_elapsed_seconds='',outcome='incomplete',http_status=''),
                 lambda r:r.update(run_id='wrong'),lambda r:r.update(target_url='http://edos_service:80/light'),
                 lambda r:r.update(worker_id=10)]
        for fn in changes:
            with tempfile.TemporaryDirectory() as t:
                root=Path(t);spec=fixture(root);rows=csv_rows(root/'request_log.csv');fn(rows[0]);csvfile(root/'request_log.csv',rows,REQUEST_FIELDS)
                self.assertFalse(analyze_run(spec,'a2')['eligible'])
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);spec=fixture(root);rows=csv_rows(root/'request_log.csv');rows.append(rows[0]);csvfile(root/'request_log.csv',rows,REQUEST_FIELDS)
            r=analyze_run(spec,'a2');self.assertFalse(r['eligible']);self.assertEqual(r['counts']['duplicate_request'],1)

    def test_a1_errors_unfinished_and_incomplete_diagnostic_only(self):
        from simulator.request_logger import REQUEST_FIELDS
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);spec=fixture(root,mode='a1');rows=csv_rows(root/'request_log.csv')
            rows[2].update(http_status='500',outcome='http_error')
            rows[3].update(http_status='',outcome='transport_error',error_type='ConnectionError')
            csvfile(root/'request_log.csv',rows,REQUEST_FIELDS)
            r=analyze_run(spec,'a1');p=r['phases'][1]
            self.assertEqual(p['http_errors'],1);self.assertEqual(p['transport_errors'],1);self.assertEqual(p['connection_errors'],1)
            self.assertEqual(p['success_fraction_per_started'],0)
            rows[3].update(end_elapsed_seconds='',outcome='incomplete');csvfile(root/'request_log.csv',rows,REQUEST_FIELDS)
            status=json.loads((root/'run_status.json').read_text());status['status']='incomplete';dump(root/'run_status.json',status)
            out=analyze('a1',[spec],root.parent/(root.name+'-out'))
            self.assertFalse(out['runs'][0]['eligible']);self.assertEqual(out['runs'][0]['phases'][1]['unfinished'],1)
            self.assertEqual(len(csv_rows(root.parent/(root.name+'-out')/'comparison.csv')),0)
            import shutil;shutil.rmtree(root.parent/(root.name+'-out'))

    def test_zero_denominator_and_incompatible_images(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);specs=[fixture(root/r,role=r,cpu=0 if r.startswith('M') else .1) for r in ['M_A','E_A','E_B','M_B']]
            analyze('a2',specs,root/'out')
            ratios=json.loads((root/'out/ratios.json').read_text());self.assertIsNone(ratios['global_ratio']);self.assertIsNone(ratios['E_A_over_M_A'])
            p=root/'E_A/diagnostics/metadata.json';meta=json.loads(p.read_text());meta['victim_image_id']='other';dump(p,meta)
            analyze('a2',specs,root/'other')
            self.assertFalse(json.loads((root/'other/ratios.json').read_text())['defined'])

    def test_no_valid_cpu_no_ratio(self):
        from experiments.exploratory_analysis import a2_ratios
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);specs=[fixture(root/r,role=r,cpu=None) for r in ['M_A','E_A','E_B','M_B']]
            runs=[analyze_run(s,'a2') for s in specs];self.assertIsNone(a2_ratios(runs)['global_ratio'])

    def test_a2_ratios_require_distinct_run_ids_standalone(self):
        from experiments.exploratory_analysis import a2_ratios
        runs=[dict(role=role,run_id=role,eligible=True,cpu_seconds={'mean':1})
              for role in ['M_A','E_A','E_B','M_B']]
        self.assertEqual(a2_ratios(runs)['global_ratio'],1)
        runs[3]['run_id']=runs[0]['run_id']
        self.assertFalse(a2_ratios(runs)['defined'])
        runs[3].pop('run_id')
        self.assertFalse(a2_ratios(runs)['defined'])

    def test_a1_missing_stages_are_not_automatically_corruption(self):
        from simulator.request_logger import REQUEST_FIELDS
        for outcome in ['transport_error','incomplete']:
            with self.subTest(outcome=outcome),tempfile.TemporaryDirectory() as t:
                root=Path(t);spec=fixture(root,mode='a1');rows=csv_rows(root/'request_log.csv')
                rows[2].update(outcome=outcome,http_status='',error_type='ReadTimeout')
                if outcome=='incomplete':rows[2]['end_elapsed_seconds']=''
                csvfile(root/'request_log.csv',rows,REQUEST_FIELDS)
                # Keep the independent client journal consistent with the outcome.
                for p in root.glob('source_artifacts/*/output/journal.jsonl'):
                    items=[json.loads(x) for x in p.read_text().splitlines()]
                    items=[x for x in items if not (x['kind']=='request_finish' and x['payload'].get('request_id')=='request2' and outcome=='incomplete')]
                    for i,x in enumerate(items,1):
                        x['sequence']=i
                        if x['payload'].get('request_id')=='request2':x['payload']=rows[2]
                    p.write_text(''.join(json.dumps(x)+'\n' for x in items))
                mutate_events(root,lambda events:events.__setitem__(slice(None),[e for e in events if e.get('request_id')!='request2']))
                r=analyze_run(spec,'a1');self.assertTrue(r['eligible'],r)
                main=r['phases'][1];self.assertEqual(main['starts'],2)
                self.assertEqual(main['unfinished'],int(outcome=='incomplete'))
                self.assertIsNone(main['pending_peak_reconstructed'])
                self.assertIsNone(main['submitted'])
                self.assertEqual(main['worker_wait_seconds']['n'],1)
                self.assertTrue(r['warnings']);self.assertFalse(r['operations'][2]['integrity_reasons'])
                # An incomplete HTTP operation can still have a valid CPU record.
                if outcome=='incomplete':
                    def restore(events):
                        events.extend([dict(kind='handler_started',request_id='request2',endpoint='/medium'),
                                       dict(kind='handler_finished',request_id='request2',endpoint='/medium',work_cpu_seconds=.01,
                                            work_submitted_at=130,work_started_at=130.001,work_finished_at=130.01,
                                            worker_clock={'time_namespace':'ns','pid':1})])
                    mutate_events(root,restore)
                    r=analyze_run(spec,'a1');self.assertTrue(r['eligible'],r)
                    self.assertEqual(r['cpu_seconds']['n'],5)

    def test_a1_keeps_strict_integrity_for_obligatory_or_corrupt_records(self):
        mutations=[lambda events:events[1].pop('work_cpu_seconds'),
                   lambda events:events.append(dict(events[1])),
                   lambda events:events.pop(0),
                   lambda events:events[1].update(work_cpu_seconds=-1),
                   lambda events:events[1].update(work_started_at=99),
                   lambda events:events[1].pop('work_started_at'),
                   lambda events:events[1].update(worker_clock={})]
        for mutation in mutations:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as t:
                root=Path(t);spec=fixture(root,mode='a1');mutate_events(root,mutation)
                self.assertFalse(analyze_run(spec,'a1')['eligible'])

    def test_a1_cpu_coverage_gaps_and_report(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);spec=fixture(root/'raw',mode='a1')
            out=analyze('a1',[spec],root/'out');main=out['runs'][0]['phases'][1]
            c=main['cpu_coverage'];self.assertEqual(c['samples'],2)
            self.assertEqual(c['first'],30);self.assertEqual(c['last'],149.9)
            self.assertAlmostEqual(c['max_gap_seconds'],119.9)
            self.assertEqual(c['empty_10_second_intervals'],[[x,x+10] for x in range(40,140,10)])
            report=(root/'out/report.md').read_text()
            self.assertIn('Maior intervalo consecutivo',report)
            self.assertIn('não sustentam conclusões',report)

    def test_a1_absent_cpu_is_unavailable_not_run_corruption(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);spec=fixture(root,mode='a1')
            # A row with no monitored container is not a supported CPU sample.
            csvfile(root/'simulation_metrics.csv',[dict(run_id='M_A',elapsed_seconds=30,average_cpu_percent=0,active_containers_names='')],
                    ['run_id','elapsed_seconds','average_cpu_percent','active_containers_names'])
            r=analyze_run(spec,'a1');self.assertTrue(r['eligible'],r)
            c=r['phases'][1]['cpu_coverage'];self.assertEqual(c['samples'],0)
            self.assertIsNone(c['first']);self.assertIsNone(c['last']);self.assertIsNone(c['max_gap_seconds'])
            self.assertEqual(len(c['empty_10_second_intervals']),12)
            self.assertIsNone(r['phases'][1]['cpu_docker_percent']['mean'])
            self.assertTrue(r['warnings'])
