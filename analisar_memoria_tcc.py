#!/usr/bin/env python3
"""Auditoria somente de leitura de mem_usage na campanha definitiva do TCC.

Executar na raiz do repositorio: python3 analisar_memoria_tcc.py
Saidas em ./analise_memoria_tcc/ (nunca altera dados da campanha).
Biblioteca padrao somente.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

CAMPAIGN = Path('experiment_results/scientific-energy-powersaver-20261109')
OUT = Path('analise_memoria_tcc')
SCENARIOS = ('L2', 'A3', 'F96')
# Protocolo conhecido: [0,30) warmup; [30,150) PRE; [150,270) ACTIVE; [270,390) POST
PHASE_BOUNDS = [('WARMUP', 0, 30), ('PRE', 30, 150), ('ACTIVE', 150, 270), ('POST', 270, 390)]
RUN_REGEX = re.compile(r'(ps_direct80_\d+_(?:L2|A3|F96))', re.IGNORECASE)
NAME_KEYS = ('active_containers_names', 'active_container_names', 'containers_names')
TIME_KEYS = ('elapsed_seconds', 'elapsed_sec', 'elapsed_s', 'time_seconds', 'time_s', 'seconds',
             'simulation_time', 'simulation_time_s', 'relative_time', 'relative_time_s',
             'timestamp_seconds', 'timestamp', 'time', 'elapsed')
PHASE_KEYS = ('phase', 'period', 'experiment_phase', 'stage', 'window_phase')


def val_float(x):
    try:
        s = str(x).strip().replace(',', '.')
        if not s:
            return None
        f = float(s)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def key_lookup(fields, names):
    normalized = {str(k).strip().lower(): k for k in fields}
    return next((normalized[n] for n in names if n in normalized), None)


def phase_from_string(raw):
    s = str(raw or '').strip().upper().replace('-', '_')
    if s in ('PRE', 'PRE_ATTACK', 'PREATTACK', 'BEFORE_ATTACK', 'BASELINE'):
        return 'PRE'
    if s in ('ACTIVE', 'ATTACK', 'DURING_ATTACK', 'DURING'):
        return 'ACTIVE'
    if s in ('POST', 'POST_ATTACK', 'POSTATTACK', 'AFTER_ATTACK'):
        return 'POST'
    if s in ('WARMUP', 'WARM_UP'):
        return 'WARMUP'
    return None


def phase_from_seconds(t):
    for p, start, end in PHASE_BOUNDS:
        if start <= t < end:
            return p
    return None


def canonical_names(v):
    if isinstance(v, str):
        v = v.strip()
        if not v:
            return None
        try:
            parsed = json.loads(v)
            if parsed != v:
                return canonical_names(parsed)
        except (ValueError, TypeError):
            pass
        # Lista com separador inequivoco; nao fracionar nome isolado.
        parts = re.split(r'\s*[,;|]\s*', v.strip('[](){}'))
        parts = [a.strip().strip('"\' ') for a in parts if a.strip().strip('"\' ')]
        return tuple(sorted(parts)) if parts else None
    if isinstance(v, (list, tuple, set)):
        parts = [str(a).strip() for a in v if str(a).strip()]
        return tuple(sorted(parts)) if parts else None
    return None


def inspect_json_names(folder):
    """Tentativa limitada a metadados proximos, nunca faz inferencia de identidade."""
    found = set()
    for path in list(folder.glob('*.json'))[:30] + list(folder.parent.glob('*.json'))[:30]:
        try:
            if path.stat().st_size > 2_000_000:
                continue
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError, UnicodeError):
            continue
        def walk(x, depth=0):
            if depth > 6:
                return
            if isinstance(x, dict):
                for k, v in x.items():
                    if str(k).lower() in NAME_KEYS:
                        names = canonical_names(v)
                        if names:
                            found.add(names)
                    elif isinstance(v, (dict, list)):
                        walk(v, depth + 1)
            elif isinstance(x, list):
                for v in x[:100]:
                    walk(v, depth + 1)
        walk(data)
    return found


def discover():
    # O checkpoint TEST lista os IDs oficiais das 60 execucoes, mesmo quando
    # os CSVs ficam sob collection/<run>/attempt-1/ (sem pasta chamada TEST).
    checkpoint = CAMPAIGN / 'checkpoints' / 'TEST' / 'manifest.json'
    try:
        manifest = json.loads(checkpoint.read_text(encoding='utf-8'))
        run_ids = set()
        for receipt in manifest.get('receipts', []):
            match = RUN_REGEX.search(str(receipt.get('path', '')))
            if match:
                run_ids.add(match.group(1))
    except (OSError, ValueError) as exc:
        print(f'ERRO: nao consegui ler checkpoint TEST: {exc}')
        raise SystemExit(1)
    if len(run_ids) != 60:
        print(f'AVISO: checkpoint TEST identificou {len(run_ids)} execucoes, esperado 60.')
    paths = sorted(CAMPAIGN.rglob('simulation_metrics.csv'))
    results = []
    for p in paths:
        match = RUN_REGEX.search(str(p))
        if not match:
            continue
        run = match.group(1)
        if run not in run_ids:  # impede misturar fases e runs nao oficiais
            continue
        scenario = run.rsplit('_', 1)[-1].upper()
        if scenario in SCENARIOS:
            results.append((run, scenario, p))
    return results


def read_run(run, scenario, path):
    rows = []
    notes = []
    try:
        with path.open('r', encoding='utf-8-sig', newline='') as f:
            rd = csv.DictReader(f)
            fields = rd.fieldnames or []
            mem_col = key_lookup(fields, ('mem_usage',))
            t_col = key_lookup(fields, TIME_KEYS)
            p_col = key_lookup(fields, PHASE_KEYS)
            n_col = key_lookup(fields, NAME_KEYS)
            if not mem_col:
                return [], [], [f'SEM_COLUNA_MEM_USAGE: {path} (colunas={fields})'], fields
            for row in rd:
                rows.append((val_float(row.get(mem_col)), row.get(t_col) if t_col else None,
                             row.get(p_col) if p_col else None,
                             canonical_names(row.get(n_col)) if n_col else None))
    except (OSError, csv.Error, UnicodeError) as exc:
        return [], [], [f'ERRO_LEITURA: {path}: {exc}'], []
    if not rows:
        return [], [], [f'VAZIO: {path}'], fields
    names_in_csv = {r[3] for r in rows if r[3]}
    names_metadata = inspect_json_names(path.parent) if not names_in_csv else set()
    if names_in_csv and len(names_in_csv) > 1:
        notes.append('COMPOSICAO_VARIAVEL_DENTRO_EXECUCAO')
    if not names_in_csv and len(names_metadata) == 1:
        notes.append('NOMES_OBTIDOS_METADADOS_ADJACENTES')
    elif not names_in_csv and len(names_metadata) > 1:
        notes.append('METADADOS_DIVERGENTES_COMPOSICAO_NAO_CONFIRMADA')
    elif not names_in_csv:
        notes.append('NOMES_CONTÊINERES_NAO_ENCONTRADOS')

    # Se existe coluna explicitamente rotulada com fase, usa-a.
    has_recognized_phases = any(phase_from_string(x[2]) for x in rows)
    if has_recognized_phases:
        method = 'coluna_fase'
        phases = [phase_from_string(x[2]) for x in rows]
    else:
        numeric_times = [val_float(x[1]) for x in rows]
        valid = [x for x in numeric_times if x is not None]
        if not valid:
            notes.append('SEM_FASE_OU_TEMPO_VALIDO')
            phases = [None] * len(rows)
            method = 'indisponivel'
        elif min(valid) >= -1 and max(valid) <= 450 and (min(valid) <= 10 or (min(valid) <= 150 and max(valid) >= 270)):
            phases = [phase_from_seconds(t) if t is not None else None for t in numeric_times]
            method = 'segundos_relativos'
        else:
            # Nao assumir que timestamps absolutos comecam exatamente no tempo 0.
            phases = [None] * len(rows)
            method = 'tempo_ambiguo'
            notes.append(f'TEMPO_AMBIGUO(min={min(valid):.3f},max={max(valid):.3f}): fases NAO inferidas')
    groups = defaultdict(list)
    missing = Counter()
    for (mem, _, _, _), phase in zip(rows, phases):
        if phase not in ('PRE', 'ACTIVE', 'POST'):
            continue
        if mem is None or mem < 0:
            missing[phase] += 1
        else:
            groups[phase].append(mem)
    # Se faltar a composicao por linha, permite observar metadados mas sem atestar comparabilidade.
    all_names = names_in_csv or (names_metadata if len(names_metadata) == 1 else set())
    name_repr = ' || '.join(', '.join(x) for x in sorted(all_names)) if all_names else 'DESCONHECIDA'
    stat_rows = []
    for phase in ('PRE', 'ACTIVE', 'POST'):
        values = groups[phase]
        stat_rows.append({
            'run': run, 'scenario': scenario, 'phase': phase, 'n_amostras_validas': len(values),
            'n_mem_ausente_ou_invalida': missing[phase],
            'media_mem_mb': statistics.mean(values) if values else None,
            'pico_mem_mb': max(values) if values else None,
            'composicao': name_repr, 'metodo_fase': method,
            'arquivo': str(path), 'avisos': ';'.join(notes)
        })
    return stat_rows, list(all_names), notes, fields


def write_csv(path, records, fields):
    with path.open('w', encoding='utf-8', newline='') as f:
        wr = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        wr.writeheader()
        wr.writerows(records)


def fmt(v):
    return '—' if v is None else f'{v:.2f}'


def main():
    if not CAMPAIGN.is_dir():
        print(f'ERRO: nao encontrei {CAMPAIGN}. Execute na raiz do repositorio.')
        raise SystemExit(1)
    found = discover()
    OUT.mkdir(exist_ok=True)
    details, diagnostic = [], []
    run_files = defaultdict(list)
    for run, scenario, path in found:
        run_files[run].append((scenario, path))
    for run, options in sorted(run_files.items()):
        if len(options) > 1:
            # Dois caminhos podem apontar para copias do mesmo CSV. Comparar o
            # conteudo binario ANTES de escolher, evitando dupla contagem.
            hashes = []
            for _, candidate in options:
                try:
                    h = hashlib.sha256()
                    with candidate.open('rb') as fh:
                        for block in iter(lambda: fh.read(1024 * 1024), b''):
                            h.update(block)
                    hashes.append(h.hexdigest())
                except OSError as exc:
                    diagnostic.append(f'ERRO_HASH {run}: {candidate}: {exc}')
            if len(hashes) != len(options) or len(set(hashes)) != 1:
                diagnostic.append(f'CONFLITO {run}: {len(options)} CSVs com conteudos diferentes (ou leitura falhou); ignorado por seguranca: {[str(x[1]) for x in options]}')
                continue
            diagnostic.append(f'COPIAS_IDENTICAS {run}: {len(options)} CSVs, SHA256={hashes[0][:16]}; usada uma copia: {options[0][1]}')
        scenario, path = options[0]
        part, names, notes, fields = read_run(run, scenario, path)
        details.extend(part)
        diagnostic.append(f'{run}: caminho={path}; colunas={fields}; contêineres={names or "DESCONHECIDOS"}; avisos={notes or "nenhum"}')
    if not found:
        diagnostic.append('NENHUM simulation_metrics.csv encontrado sob pasta TEST e com identificador ps_direct80_*')
    dfields = ['run','scenario','phase','n_amostras_validas','n_mem_ausente_ou_invalida',
               'media_mem_mb','pico_mem_mb','composicao','metodo_fase','arquivo','avisos']
    write_csv(OUT / 'memoria_por_execucao.csv', details, dfields)
    # Comparabilidade: mesmos nomes EXATOS em todas as 60 execucoes e disponibilidade das tres fases.
    expected = {s: 20 for s in SCENARIOS}
    active = [x for x in details if x['phase'] == 'ACTIVE' and x['n_amostras_validas'] > 0]
    totals = Counter(x['scenario'] for x in active)
    compositions = {x['composicao'] for x in active}
    all_known = len(compositions) == 1 and 'DESCONHECIDA' not in compositions
    full_coverage = all(totals.get(s, 0) == expected[s] for s in SCENARIOS)
    methods_ok = all(x['metodo_fase'] in ('coluna_fase', 'segundos_relativos') for x in details)
    # Mesmo com composicao identica, nao significa memoria exclusiva da vitima.
    comparable = full_coverage and all_known and methods_ok
    summary = []
    for s in SCENARIOS:
        sr = [x for x in details if x['scenario'] == s]
        a = [x for x in sr if x['phase'] == 'ACTIVE' and x['media_mem_mb'] is not None]
        pre = [x for x in sr if x['phase'] == 'PRE' and x['media_mem_mb'] is not None]
        post = [x for x in sr if x['phase'] == 'POST' and x['media_mem_mb'] is not None]
        summary.append({
            'cenario': s, 'n_ACTIVE': len(a), 'n_PRE': len(pre), 'n_POST': len(post),
            'media_ACTIVE_MB': statistics.mean(x['media_mem_mb'] for x in a) if a else None,
            'pico_ACTIVE_MB': max((x['pico_mem_mb'] for x in a), default=None),
            'media_PRE_MB': statistics.mean(x['media_mem_mb'] for x in pre) if pre else None,
            'media_POST_MB': statistics.mean(x['media_mem_mb'] for x in post) if post else None,
            'composicoes_distintas': len({x['composicao'] for x in a}),
        })
    write_csv(OUT/'resumo_por_cenario.csv', summary, list(summary[0]))
    lines = [
        'AUDITORIA DE MEMORIA — CAMPANHA DEFINITIVA',
        f'CSV encontrados: {len(found)}; execucoes unicas: {len(run_files)}',
        f'Execucoes com CSV processado: {len({x["run"] for x in details})}',
        f'ACTIVE valido por cenario: {dict(totals)} (esperado: 20 cada)',
        f'Composicoes detectadas em ACTIVE: {sorted(compositions)}',
        f'Composicao conhecida e identica? {"SIM" if all_known else "NAO"}',
        f'Cobertura completa (20 execucoes/cenario)? {"SIM" if full_coverage else "NAO"}',
        f'Classificacao temporal confiavel? {"SIM" if methods_ok else "NAO"}',
        f'Comparacao agregada entre cenarios autorizada automaticamente? {"SIM" if comparable else "NAO"}',
        'ATENCAO: mem_usage e memoria AGREGADA dos conteineres ativos, NAO RAM isolada da vitima nem RAM total do host.',
        'ATENCAO: ainda que nomes identicos sejam observados, verificar se o coletor usa mesma composicao/amostragem em todos cenarios.',
        'Agregacao: media temporal por execucao -> media das execucoes; pico ACTIVE = maior observacao entre execucoes.',
        '', 'Cenario | n ACTIVE | media ACTIVE (MB) | pico ACTIVE (MB) | media PRE (MB) | media POST (MB)',
    ]
    for s in summary:
        lines.append(f"{s['cenario']:>7} | {s['n_ACTIVE']:>8} | {fmt(s['media_ACTIVE_MB']):>17} | {fmt(s['pico_ACTIVE_MB']):>16} | {fmt(s['media_PRE_MB']):>14} | {fmt(s['media_POST_MB']):>15}")
    if not comparable:
        lines += ['', 'RESSALVA: tabela DESCRITIVA APENAS; NAO interpretar diferencas entre cenarios antes de resolver as pendencias de comparabilidade.']
    lines += ['', 'DIAGNOSTICO POR EXECUCAO:', *diagnostic]
    (OUT/'diagnostico_memoria.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('\n'.join(lines[:17]))
    print(f'\nArquivos gerados: {OUT / "resumo_por_cenario.csv"}, {OUT / "memoria_por_execucao.csv"}, {OUT / "diagnostico_memoria.txt"}')

if __name__ == '__main__':
    main()
