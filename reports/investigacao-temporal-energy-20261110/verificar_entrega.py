"""Read-only assertions and provenance; outputs only a derived validation manifest."""
from pathlib import Path
import json,hashlib,re
import numpy as np
import pandas as pd
P=Path(__file__).resolve().parent;ROOT=P.parents[1]
ph=pd.read_csv(P/'metricas_periodo_execucao.csv');r=pd.read_csv(P/'recuperacao_execucao.csv');s=pd.read_csv(P/'series_1s.csv')
assert r.scenario.value_counts().to_dict()=={'L2':20,'F96':20,'A3':20}
assert (ph.benign_http_start==ph.benign_ok+ph.benign_timeout).all()
assert np.allclose(s.pending,s.waiting+s.running)
assert s.running.max()<=2
off=r[r.scenario!='L2'];assert (off.attack_started_post>0).all() and (off.computed_after_timeout>0).all()
assert set(off[off.operational_recovery==False].id)=={'ps_direct80_043_A3','ps_direct80_075_F96'}
assert (s.query('second>=270').attack_http_start==0).all()
assert off.queue_return_start_s.notna().all() and off.availability_return_start_s.notna().all()
text=(P/'relatorio.md').read_text()
assert len(text.split('## 1. Resumo executivo')[1].split('## 2.')[0].split())<=300
assert not [x for x in re.findall(r'\]\(([^)]+)\)',text) if not (P/x.rsplit(':',1)[0]).exists()]
inputs=json.loads((P/'manifesto_entradas.json').read_text())['inputs_sha256']
assert all(hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==v for k,v in inputs.items())
files={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in P.iterdir() if x.is_file() and x.name!='validacao_entrega.json'}
(P/'validacao_entrega.json').write_text(json.dumps(dict(status='PASS',test_runs=60,input_files_unchanged=len(inputs),http_conservation=True,queue_conservation=True,maximum_workers=2,no_attack_http_starts_post=True,report_links_valid=True,artifact_sha256=files,note='Final script and figure hashes are recorded here; manifesto_entradas preserves the initial analysis execution provenance.'),indent=2))
print('PASS: 60 TEST; HTTP and queue conservation; 1261 unchanged inputs; report links and figures present.')
