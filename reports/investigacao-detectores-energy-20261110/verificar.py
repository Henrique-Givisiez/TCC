"""Final audit: frozen aggregate concordance, input preservation and report links."""
from pathlib import Path
import json,hashlib,re
import pandas as pd
import numpy as np
P=Path(__file__).resolve().parent;ROOT=P.parents[1]
run=pd.read_csv(P/'alarmes_por_execucao.csv');comb=pd.read_csv(P/'tabela_combinacoes.csv')
summary=json.loads((ROOT/'experiment_results/scientific-energy-powersaver-20261109/analysis/summary/manifest.json').read_text())
checks=0
for (feature,detector,sc),g in run.groupby(['feature','detector','scenario']):
    s=summary['results'][f'{feature}/{sc}/{detector}'];assert len(g)==20 and s['n_scientifically_evaluated']==20
    if sc!='L2':
        assert s['detection']['successes']==int(g.event_detected.eq(True).sum()) and s['detection']['n']==20
        assert s['delay']['detected']==int(g.delay_s.notna().sum())
        assert abs(s['delay']['mean_seconds']-g.delay_s.mean())<1e-12
        assert abs(s['delay']['median_seconds']-g.delay_s.median())<1e-12
        assert abs(float(s['post_positive_duration_seconds']['estimate'])-g.post_duration_s.mean())<1e-12
    for metric,col in [('fpr','fpr'),('pre_fpr','pre_fpr'),('recall','recall'),('post_positive_fraction','post_fraction')]:
        if g[col].notna().any():assert abs(float(s['means'][metric]['estimate'])-g[col].mean())<1e-12
    checks+=1
assert len(comb)==16 and len(run)==960 and run.unavailable.max()==0
assert summary['eligibility']['eligible']==16
cov=pd.read_csv(P/'cov_tempos_alarmes.csv')
assert (cov.positives_after_first30==0).all()
cs=pd.read_csv(P/'cusum_retomadas.csv');assert cs.resumed_negative.all() and cs.rejected_preserved.all()
paths=json.loads((P/'manifesto_entradas.json').read_text());paths.update(json.loads((P/'manifesto_complementar.json').read_text()))
assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h for name,h in paths.items())
v=json.loads((P/'verificacao.json').read_text());assert not v['mismatches'] and not v['changed_inputs']
decision_count=0
for name in paths:
    if '/analysis/' in name and '/TEST/' in name and name.endswith('/manifest.json'):
        d=json.loads((ROOT/name).read_text());decision_count+=sum(len(v) for v in d['methods'].values())
if 'decisions_compared' in v:v['total_comparisons']=v.pop('decisions_compared')
v.update(decision_rows_compared=decision_count,aggregate_groups_checked=checks,all_input_hashes_rechecked=len(paths),final_input_changes=[],cusum_all_offensive_paths_resume_negative=True)
if (P/'relatorio.md').exists():
    text=(P/'relatorio.md').read_text();broken=[x for x in re.findall(r'\]\(([^)]+)\)',text) if not (P/x.rsplit(':',1)[0]).exists()];assert not broken
    assert len(text.split('## 1. Resumo executivo')[1].split('## 2.')[0].split())<=300
    v['report_links_valid']=True
v['final_artifact_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in P.iterdir() if p.is_file() and p.name!='verificacao.json'}
(P/'verificacao.json').write_text(json.dumps(v,indent=2))
print('PASS',decision_count,'decision rows;',checks,'aggregate groups;',len(paths),'unchanged inputs; no recalibration.')
