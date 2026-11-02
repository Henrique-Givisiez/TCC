"""Verificações dirigidas de unidades, suporte, vínculos e exportação; somente leitura."""
from bisect import bisect_left
from collections import defaultdict,Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from PIL import Image

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]


def read(path):return json.loads(path.read_text())

def rows(path):
    with path.open(newline='') as stream:yield from csv.DictReader(stream)


def main():
    prov=read(ROOT/'provenance.json');checks=Counter()
    assert hashlib.sha256((ROOT/'generate.py').read_bytes()).hexdigest()==prov['generator_sha256']
    for rel,digest in prov['outputs'].items():assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==digest,rel
    cp=read(REPO/'experiment_results/scientific-reduced-clock-r2-20261029/checkpoints/TEST/manifest.json')
    refs={}
    for ref in cp['receipts']:
        doc=read(Path(ref['path'])/'manifest.json');refs[doc['entry']['id']]=doc['receipt']
    old=REPO/'reports/scientific_reduced_clock_r2_proxy_20261102'
    old_prov=read(old/'provenance.json')
    ledger=old/'tables/access_association.csv'
    assert hashlib.sha256(ledger.read_bytes()).hexdigest()==old_prov['outputs']['tables/access_association.csv']
    logs=defaultdict(list)
    for r in rows(ledger):
        if r['selection_reason']=='scientific' and r['log_seconds']:
            logs[r['entry']].append((float(r['log_seconds']),r['traffic_class'],float(r['upstream_ms']) if r['upstream_ms'] else None))
    logs={k:sorted(v) for k,v in logs.items()};times={k:[r[0] for r in v] for k,v in logs.items()}
    last_entry=None;samples=None;prior=None
    for r in rows(ROOT/'tables/native_memory_alignment.csv'):
        if r['entry']!=last_entry:
            receipt=refs[r['entry']];ds=Path(receipt['dataset']);dm=read(ds/'dataset_manifest.json')
            f=next(f for f in dm['files'] if f['path']=='evidence/proxy/monitor_samples.jsonl')
            path=ds/f['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==f['sha256']
            samples=[json.loads(line) for line in path.read_text().splitlines()]
            prior=None;last_entry=r['entry']
        sample=samples[int(r['index'])];d,z=sample['docker'],sample['status'];m=d['data']['memory_usage_bytes'];t=d['elapsed_seconds']
        assert int(r['memory_bytes'])==m and float(r['memory_mib'])==m/2**20 and m%4096==0
        assert float(r['docker_seconds'])==t
        assert (int(r['delta_bytes']) if r['delta_bytes'] else None)==(m-prior if prior is not None else None)
        if r['delta_bytes']:assert float(r['delta_mib'])==int(r['delta_bytes'])/2**20
        prior=m
        lag=t-z['elapsed_seconds'];aligned=z['success'] and 0<=lag<=.5
        assert r['status_alignment_valid']==str(aligned)
        for target,source in [('active','active_connections'),('reading','reading_connections'),('writing','writing_connections'),('waiting','waiting_connections')]:
            assert r[target]==(str(z['data'][source]) if aligned else '')
        if not z['success']:
            checks['status_failures_preserved']+=1
            assert r['status_error']=='ValueError: invalid stub_status response'
        assert float(r['operation_gap_us'])==(t-z['elapsed_seconds']-z['duration_seconds'])*1e6
        if float(r['operation_gap_us'])<0:checks['estimated_negative_gaps_retained']+=1
        assert r['monitor_log_match']=='unique' and r['monitor_access_line']
        assert float(r['engine_after_docker_start_ms'])>=0 and float(r['engine_before_docker_end_ms'])>=0
        idx0,idx1=bisect_left(times[r['entry']],t-1),bisect_left(times[r['entry']],t)
        own=logs[r['entry']][idx0:idx1]
        assert len(own)==int(r['scientific_completions_per_s'])
        assert float(r['log_window_start'])==t-1 and float(r['log_window_end'])==t
        for cls in ['benign','attack']:
            v=[x[2] for x in own if x[1]==cls and x[2] is not None]
            assert len(v)==int(r['upstream_'+cls+'_n'])
            assert sum(x[1]==cls for x in own)==int(r['completions_'+cls])
            if v:assert math.isclose(sum(v)/len(v),float(r['upstream_'+cls+'_ms']),rel_tol=1e-12)
            else:assert r['upstream_'+cls+'_ms']==''
        if r['consecutive_within_phase']=='True':
            assert 0<float(r['docker_interval_seconds'])<=1.5 and r['previous_phase']==r['phase']!='OUT'
        checks['native_records']+=1
    assert checks['native_records']==14094 and checks['status_failures_preserved']==119
    assert checks['estimated_negative_gaps_retained']==31
    previous_summary=old/'tables/per_run_phase.csv'
    reference_sha=hashlib.sha256(previous_summary.read_bytes()).hexdigest()
    assert reference_sha==old_prov['outputs']['tables/per_run_phase.csv']
    existing={(r['entry'],r['phase']):r for r in rows(previous_summary)}
    for r in rows(ROOT/'tables/run_phase_distributions.csv'):
        reference=existing[r['entry'],r['phase']]
        assert math.isclose(float(r['memory_mean']),float(reference['memory_mib_sample_mean']),rel_tol=1e-12)
        assert int(r['memory_n'])==int(reference['memory_mib_n'])
        assert int(r['positive_steps'])+int(r['negative_steps'])+int(r['repeated_adjacent'])==int(r['delta_n'])
        assert int(r['delta_gcd_bytes'])%4096==0
        checks['run_phases_same_as_previous_presentation']+=1
    assert checks['run_phases_same_as_previous_presentation']==108
    for r in rows(ROOT/'tables/within_run_associations.csv'):
        if r['undefined_reason']:assert r['spearman']==''
        else:assert int(r['n_pairs'])>=8 and -1<=float(r['spearman'])<=1
        if r['scenario']=='E16' and r['phase']=='ACTIVE' and r['predictor']=='reading':
            assert r['undefined_reason']=='constant_variable'
        checks['association_support_records']+=1
    run_support=list(rows(ROOT/'tables/run_support.csv'))
    assert len(run_support)==36 and sum(int(r['skipped_slots']) for r in run_support)==0
    assert all(r['memory_missing']=='0' and r['repeated_docker_read']=='0' for r in run_support)
    fields={r['field'] for r in rows(ROOT/'tables/saved_docker_fields.csv')}
    assert fields=={'cpu_percent','delta_state','docker_read','interfaces','memory_usage_bytes','observed_interval_seconds'}
    exports=[]
    for pdf in sorted((ROOT/'figures').glob('*.pdf')):
        fonts=subprocess.run(['pdffonts',str(pdf)],capture_output=True,text=True,check=True).stdout
        assert 'TrueType' in fonts and all(' yes ' in l for l in fonts.splitlines()[2:])
        images=subprocess.run(['pdfimages','-list',str(pdf)],capture_output=True,text=True,check=True).stdout
        assert len(images.splitlines())==2
        with tempfile.TemporaryDirectory() as temp:
            bbox=Path(temp)/'bbox.html';subprocess.run(['pdftotext','-bbox',str(pdf),str(bbox)],capture_output=True,check=True)
            doc=ET.parse(bbox).getroot();ns={'x':'http://www.w3.org/1999/xhtml'};page=doc.find('.//x:page',ns)
            w,h=float(page.get('width')),float(page.get('height'))
            for word in doc.findall('.//x:word',ns):
                assert 0<=float(word.get('xMin'))<=float(word.get('xMax'))<=w,(pdf.name,word.text)
                assert 0<=float(word.get('yMin'))<=float(word.get('yMax'))<=h,(pdf.name,word.text)
        with Image.open(pdf.with_suffix('.png')) as im:assert all(abs(d-300)<.1 for d in im.info['dpi'])
        exports.append(dict(file=pdf.name,vector_pdf=True,embedded_fonts=True,text_inside_page=True,png_dpi=300))
    test=subprocess.run([sys.executable,'-B',str(ROOT/'test_memory.py')],capture_output=True,text=True)
    assert test.returncode==0,test.stderr
    result=dict(checks=dict(checks),exports=exports,saved_proxy_memory_components=['memory_usage_bytes'],
        inferential_tests=False,unit_tests=test.stderr,generator_sha256=prov['generator_sha256'],output_hashes_verified=True,
        previous_phase_summary_sha256=reference_sha)
    (ROOT/'verification.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=='__main__':main()
