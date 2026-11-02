"""Conferência dirigida da apresentação existente; sem runtime científico."""
import csv
from collections import Counter,defaultdict
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


def rows(name):
    with (ROOT/'tables'/name).open(newline='') as stream:
        yield from csv.DictReader(stream)


def phase(t,end):
    if t is None or t<30 or t>=390:return ''
    return 'PRE' if t<150 else 'ACTIVE' if t<end else 'POST'


def main():
    prov=json.loads((ROOT/'provenance.json').read_text())
    assert hashlib.sha256((ROOT/'generate.py').read_bytes()).hexdigest()==prov['generator_sha256']
    for name,digest in prov['outputs'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    support={r['entry']:r for r in rows('per_run_support.csv')}
    phases={(r['entry'],r['phase']):r for r in rows('per_run_phase.csv')}
    assert len(support)==36 and len(phases)==108
    exposureends={eid:float(r['event_end_seconds']) if r['event_end_seconds'] else 270. for eid,r in support.items()}
    native_counts=Counter();status_errors=Counter();phase_values=defaultdict(list)
    for r in rows('native_monitor_reads.csv'):
        if r['status_success']=='False':
            assert r['active_connections']==''
            status_errors[r['status_error']]+=1
        if r['delta_state']=='first_read':
            assert r['cpu_percent']==''
            native_counts['first_cpu_missing']+=1
        assert math.isclose(float(r['memory_mib']),int(r['memory_bytes'])/2**20,rel_tol=1e-15)
        for metric,tkey in [('cpu_percent','docker_seconds'),('memory_mib','docker_seconds'),('active_connections','status_seconds')]:
            name=phase(float(r[tkey]),exposureends[r['entry']])
            if name and r[metric]!='':phase_values[r['entry'],name,metric].append(float(r[metric]))
        native_counts['records']+=1
    assert status_errors=={'ValueError: invalid stub_status response':119},status_errors
    assert native_counts=={'records':14094,'first_cpu_missing':36},native_counts
    for (eid,name,metric),values in phase_values.items():
        summary=phases[eid,name]
        assert len(values)==int(summary[metric+'_n'])
        assert math.isclose(sum(values)/len(values),float(summary[metric+'_sample_mean']),rel_tol=1e-12)
    totals=Counter();ids=set();log_values=defaultdict(list);access_counts=Counter()
    for r in rows('access_association.csv'):
        totals['all']+=1
        if r['selection_reason']=='scientific':
            assert r['traffic_class'] in {'benign','attack'} and r['request_id']
            assert r['log_phase']==''
            key=r['run_id'],r['request_id']
            assert key not in ids,key
            ids.add(key)
            totals['scientific_'+r['traffic_class']]+=1
        else:
            assert r['selection_reason'] in {'aux_monitoring','aux_setup','aux_capture_audit'}
            totals[r['selection_reason']]+=1
            assert r['upstream_ms']==''
        if r['log_seconds']:
            assigned=phase(float(r['log_seconds']),exposureends[r['entry']])
            assert r['operational_phase']==assigned
            if assigned:access_counts[r['entry'],assigned]+=1
            if r['final_reason']=='valid_scientific_upstream':
                assert math.isclose(float(r['upstream_ms']),float(r['raw_upstream_time'])*1000,rel_tol=1e-15,abs_tol=1e-12)
                if assigned:log_values[r['entry'],assigned,r['traffic_class']].append(float(r['upstream_ms']))
    assert totals=={'all':277194,'scientific_benign':223656,'scientific_attack':38568,
                   'aux_monitoring':14094,'aux_setup':36,'aux_capture_audit':840},totals
    for key,r in phases.items():
        assert int(r['access_records'])==access_counts[key]
        assert float(r['start_seconds'])==(30. if key[1]=='PRE' else 150. if key[1]=='ACTIVE' else exposureends[key[0]])
        assert float(r['end_seconds'])==(150. if key[1]=='PRE' else exposureends[key[0]] if key[1]=='ACTIVE' else 390.)
        for cls in ['benign','attack']:
            values=log_values[*key,cls]
            assert len(values)==int(r['upstream_'+cls+'_valid'])
            if values:
                assert math.isclose(sum(values)/len(values),float(r['upstream_'+cls+'_mean_ms']),rel_tol=1e-12)
            else:assert r['upstream_'+cls+'_mean_ms']==''
        assert int(r['upstream_benign_unusable'])==int(r['upstream_attack_unusable'])==0
    bins=list(rows('upstream_bins_5s.csv'))
    assert len(bins)==432
    for r in bins:
        assert float(r['end_seconds'])-float(r['start_seconds'])==5
        assert int(r['valid_upstream'])+int(r['excluded_upstream'])==int(r['scientific_records'])
        if not int(r['valid_upstream']):assert r['mean_upstream_ms']==''
        if r['scenario']=='C16' and r['traffic_class']=='attack':
            assert r['mean_upstream_ms']=='' and r['valid_upstream']=='0'
    diagnostic=list(rows('nginx_limits_by_run.csv'))
    assert all(r['configured_worker_connections']=='4096' and r['configured_workers']=='1' and
        r['startup_nofile_soft']=='1024' and r['startup_nofile_hard']=='524288' and
        r['worker_rlimit_nofile_directive']=='False' and r['upstream_keepalive']=='32' and
        r['proxy_next_upstream_off']=='True' and r['upstream_tries']=='1' for r in diagnostic)
    assert all(r['proxy_error.log_exhaustion_messages']==r['container_output.log_exhaustion_messages']=='0' for r in diagnostic)
    assert max(int(r['observed_active_max_30_390']) for r in diagnostic)==92
    export=[]
    for pdf in sorted((ROOT/'figures').glob('*.pdf')):
        fonts=subprocess.run(['pdffonts',str(pdf)],capture_output=True,text=True,check=True).stdout
        assert 'TrueType' in fonts and all(' yes ' in l for l in fonts.splitlines()[2:])
        images=subprocess.run(['pdfimages','-list',str(pdf)],capture_output=True,text=True,check=True).stdout
        assert len(images.splitlines())==2
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bbox.html'
            subprocess.run(['pdftotext','-bbox',str(pdf),str(p)],check=True,capture_output=True)
            doc=ET.parse(p).getroot();ns={'x':'http://www.w3.org/1999/xhtml'}
            page=doc.find('.//x:page',ns);w,h=float(page.get('width')),float(page.get('height'))
            for word in doc.findall('.//x:word',ns):
                assert 0<=float(word.get('xMin'))<=float(word.get('xMax'))<=w,(pdf,word.text)
                assert 0<=float(word.get('yMin'))<=float(word.get('yMax'))<=h,(pdf,word.text)
        with Image.open(pdf.with_suffix('.png')) as im:
            assert all(abs(d-300)<.1 for d in im.info['dpi'])
        export.append(dict(file=pdf.name,embedded_fonts=True,raster_images=0,text_inside_page=True,png_dpi=300))
    test=subprocess.run([sys.executable,'-B',str(ROOT/'test_proxy.py')],capture_output=True,text=True)
    assert test.returncode==0,test.stderr
    result=dict(native_counts=dict(native_counts),status_errors=dict(status_errors),access_totals=dict(totals),
        phases_checked=108,upstream_bins_checked=432,run_local_ids_checked=len(ids),
        warning_diagnostic_runs_checked=36,observed_active_max=92,explicit_exhaustion_messages=0,
        exports=export,unit_tests=test.stderr,generator_sha256=prov['generator_sha256'],output_hashes_verified=True)
    (ROOT/'verification.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=='__main__':main()
