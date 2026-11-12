#!/usr/bin/env python3
"""Confere integridade das entradas e legibilidade básica das saídas A2."""
import hashlib,json,re
from pathlib import Path
from PIL import Image,ImageStat

OUT=Path(__file__).resolve().parents[1]
ROOT=OUT.parents[1]
checks=json.loads((OUT/'validation/checks.json').read_text())
manifest=json.loads((OUT/'manifest.json').read_text())
bad_hash=[]
for rel,expected in checks['inputs_sha256'].items():
    actual=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()
    if actual!=expected:bad_hash.append(rel)
assert not bad_hash,bad_hash
assert checks['figure_pairs']==14 and len(manifest['figures'])==28
bad_figure=[]
for rel in manifest['figures']:
    path=OUT/rel
    if not path.exists() or path.stat().st_size<2000:bad_figure.append(rel);continue
    if path.suffix=='.png':
        im=Image.open(path).convert('RGB')
        if min(im.size)<600 or max(ImageStat.Stat(im).stddev)<8:bad_figure.append(rel)
assert not bad_figure,bad_figure
report=(OUT/'relatorio.md').read_text()
links=re.findall(r'\]\((figures/[^)]+)\)',report)
assert len(links)==14 and all((OUT/x).exists() for x in links)
for k,x in checks['runs'].items():
    assert x['request_ids']==x['rtt_ids']==x['work_ids']==101
    assert x['source_events']['http_started']==x['source_events']['http_finished']==101
    assert x['max_running']<=2 and x['min_waiting']>=0
    assert abs(x['occupation_fraction_sum']-1)<1e-9
result={'status':'passed','input_hashes':len(checks['inputs_sha256']),'figure_pairs':checks['figure_pairs'],'report_png_links':len(links),'run_checks':list(checks['runs']),'bad_hashes':bad_hash,'bad_figures':bad_figure}
(OUT/'validation/result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
print(json.dumps(result,ensure_ascii=False))
