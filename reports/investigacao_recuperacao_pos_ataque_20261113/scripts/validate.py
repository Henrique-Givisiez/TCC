#!/usr/bin/env python3
"""Confere desenho, cobertura, estatísticas, figuras e imutabilidade das fontes."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'reports/investigacao_recuperacao_pos_ataque_20261113'
P=OUT/'processed'
SRC=ROOT/'reports/scientific_campaign_visualization_20261112'

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
    return h.hexdigest()

def main():
    inv=pd.read_csv(SRC/'inventario_execucoes.csv');inv=inv[inv.partition.eq('TEST')]
    assert len(inv)==60 and inv.block.nunique()==20 and set(inv.scenario)=={'L2','A3','F96'}
    assert inv.groupby(['block','scenario']).size().eq(1).all()
    per=pd.read_csv(P/'post_por_execucao.csv');http=pd.read_csv(P/'http_por_execucao.csv')
    assert len(per)==240 and len(http)==480
    assert per.groupby(['entry_id','interval']).size().eq(1).all()
    assert set(per.interval)=={'POST-1','POST-2','POST-3','POST-4'}
    assert per.groupby(['interval','scenario']).size().eq(20).all()
    for col in ('ingress_packet_count','ingress_tcp_payload_length_sum_bytes','request_starts',
                'mean_duration_ms','waiting_mean','workers_two_fraction'):
        assert per[col].notna().all(),col
    assert per.mean_duration_ms_valid_windows.eq(30).all()
    assert per.cpu_feature_mean_valid_windows.between(0,30).all()
    summary=pd.read_csv(P/'post_resumo.csv')
    for x in summary.itertuples():
        z=per[(per.scenario==x.scenario)&(per.interval==x.interval)][x.metric].dropna()
        assert len(z)==x.n_valid and np.isclose(z.mean(),x.mean,rtol=1e-7,atol=1e-7)
        assert np.isclose(z.std(ddof=1),x.sd,rtol=1e-7,atol=1e-7)
    pairs=pd.read_csv(P/'contrastes_por_bloco.csv');contrasts=pd.read_csv(P/'contrastes_pareados.csv')
    assert len(contrasts)==156
    for x in contrasts.itertuples():
        z=pairs[(pairs.interval==x.interval)&(pairs.metric==x.metric)&(pairs.contrast==x.contrast)]
        assert len(z)==x.n and np.isclose(z.difference.mean(),x.mean,rtol=1e-7,atol=1e-7)
    assert (http.groupby(['scenario','interval','traffic_class']).size()==20).all()
    for path,expected in json.loads((P/'input_hashes.json').read_text()).items():
        assert digest(ROOT/path)==expected,path
    trace=pd.read_csv(P/'tracos_5s_por_execucao.csv')
    assert trace.groupby(['scenario','t']).size().eq(20).all()
    assert trace[['mean_duration_ms','waiting_mean','workers_two_fraction','benign_median_ms']].notna().all().all()
    cpu=pd.read_csv(P/'cpu_cobertura_por_execucao_fase.csv')
    assert len(cpu)==240 and cpu.groupby(['scenario','phase']).size().eq(20).all()
    for stem in ('b1_a_recuperacao','b1_b_legitimo','b2_cpu_cobertura'):
        for ext in ('png','pdf'):
            path=OUT/'figures'/f'{stem}.{ext}'
            assert path.stat().st_size>1000,path
    print('OK: 60 TEST, 20 blocos, três cenários, 240 intervalos, contrastes, fontes SHA-256 e seis figuras')

if __name__=='__main__':main()
