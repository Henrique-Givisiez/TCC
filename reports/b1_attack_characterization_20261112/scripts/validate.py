#!/usr/bin/env python3
"""Validação independente dos resumos e saídas B1."""
import hashlib,json,re
from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image,ImageStat

OUT=Path(__file__).resolve().parents[1];ROOT=OUT.parents[1]
M=json.loads((OUT/'manifest.json').read_text());C=json.loads((OUT/'validation/checks.json').read_text());S=pd.read_csv(OUT/'processed/summary.csv').set_index('id');I=pd.read_csv(OUT/'inventario_execucoes.csv')
assert len(M['source_runs'])==len(S)==9 and len(I)==15
assert set(I.classification)=={'principal','complementar','excluído do processamento B1'}
assert I.classification.value_counts().to_dict()=={'principal':8,'excluído do processamento B1':6,'complementar':1}
bad_hash=[]
for rel,expected in C['input_sha256'].items():
    if hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()!=expected:bad_hash.append(rel)
assert not bad_hash,bad_hash
for k,rel in M['source_runs'].items():
    raw=ROOT/rel/'raw';q=pd.read_csv(raw/'request_log.csv');cfg=json.loads((raw/'effective_config.json').read_text());stat=json.loads((raw/'run_status.json').read_text());s=S.loc[k];c=C['runs'][k]
    assert stat['status']=='completed' and stat['run_id']==c['run_id']
    assert len(q)==s.http_started==c['request_ids']==c['work_ids']
    assert np.isclose(s.rps_started,len(q)/30) and s.nominal_rps==cfg['attack']['attackers']*cfg['attack']['rate']
    assert s.http_success==((q.outcome=='response')&(q.http_status==200)).sum()
    assert s.timeouts==q.error_type.fillna('').str.contains('Timeout',case=False).sum()
    assert s.http_success+s.http_error+s.timeouts+s.connection_fail+s.other_outcome==len(q)
    assert s.submitted==c['source_counts']['submitted'] and s.not_http_started==s.submitted-len(q)==c['journal_counts'].get('abandoned_admission',0)
    assert c['max_running']<=2 and c['min_waiting']>=0 and c['max_source_concurrency']<=64
    assert np.isclose(c['worker_fractions_sum'],1) and np.isclose(s.workers_0_fraction+s.workers_1_fraction+s.workers_2_fraction,1)
    assert c['clock'][0]=='CLOCK_MONOTONIC' and c['active_stats_n']>0
    p=OUT/'processed'/('assimetria' if k.startswith('A') else 'flooding')
    w=pd.read_csv(p/f'{k}_workers.csv');assert w.executando.max()<=2 and w.aguardando.min()>=0
    assert np.isclose(w.executando.max(),s.running_max) and np.isclose(w.aguardando.max(),s.waiting_max)
    ops=pd.read_csv(p/f'{k}_operacoes.csv');assert len(ops)==len(q) and set(ops.request_id)==set(q.request_id)
    assert ((ops.start>=ops.submit)&(ops.finish>=ops.start)&(ops.cpu_ms>=0)&(ops.wait_ms>=0)).all()
figs=M['figures'];assert len(figs)==2*C['figure_pairs'] and len(figs)==len(set(figs))
bad_fig=[]
for rel in figs:
    p=OUT/rel
    if not p.exists() or p.stat().st_size<2000:bad_fig.append(rel);continue
    if p.suffix=='.png':
        im=Image.open(p).convert('RGB')
        if min(im.size)<600 or max(ImageStat.Stat(im).stddev)<7:bad_fig.append(rel)
assert not bad_fig,bad_fig
report=(OUT/'relatorio.md').read_text();links=re.findall(r'\]\((figures/[^)]+)\)',report)
assert len(links)==C['figure_pairs'] and all((OUT/x).exists() for x in links)
result={'status':'passed','runs_processed':len(S),'inventory_rows':len(I),'source_hashes':len(C['input_sha256']),'figures':C['figure_pairs'],'report_figure_links':len(links),'hash_mismatch':bad_hash,'bad_figures':bad_fig}
(OUT/'validation/result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
print(json.dumps(result,ensure_ascii=False))
