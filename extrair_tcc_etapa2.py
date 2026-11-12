#!/usr/bin/env python3
"""Prepara um pacote pequeno e somente de leitura com JSONs da campanha definitiva.

Uso (a partir da raiz do repositorio):
    python3 /caminho/para/extrair_tcc_etapa2.py

Nao acessa datasets brutos, nao depende de bibliotecas externas e nao altera
nenhum arquivo dentro de experiment_results.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

EXPECTED_CAMPAIGN = 'scientific-energy-powersaver-20261109'
PARTITIONS = ('BASELINE', 'CAL_A', 'CAL_B', 'TEST')
FEATURES = (
    'ingress_packet_count',
    'ingress_tcp_payload_length_sum_bytes',
    'request_starts',
    'mean_duration_ms',
)
MAX_FILE_SIZE = 20 * 1024 * 1024   # limite preventivo por JSON
MAX_TOTAL_SIZE = 50 * 1024 * 1024  # nao embalar um volume grande por acidente


def short_shape(value):
    if isinstance(value, dict):
        keys = list(value)
        return f'dict[{len(value)}] keys={keys[:12]}' + (' ...' if len(keys) > 12 else '')
    if isinstance(value, list):
        return f'list[{len(value)}]'
    if isinstance(value, str):
        return f'str: {value[:110]!r}'
    return repr(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--root', type=Path,
        default=Path('experiment_results') / EXPECTED_CAMPAIGN,
        help='Caminho da campanha definitiva (relativo ou absoluto)',
    )
    parser.add_argument(
        '--saida', type=Path,
        default=Path('pacote_tcc_etapa2.zip'),
        help='ZIP de saida, fora da pasta experiment_results',
    )
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.saida.resolve()

    if root.name != EXPECTED_CAMPAIGN:
        print('ERRO: pasta selecionada nao e a campanha definitiva:', root, file=sys.stderr)
        return 2
    if not root.is_dir():
        print('ERRO: pasta nao encontrada:', root, file=sys.stderr)
        print('Execute na raiz do repositorio ou use --root /caminho/completo/...', file=sys.stderr)
        return 2
    if root == output or root in output.parents:
        print('ERRO: o ZIP de saida deve ficar fora da pasta da campanha.', file=sys.stderr)
        return 2

    candidates = set(root.glob('*.json'))  # inclui binding.json e outros JSONs de raiz
    candidates.add(root / 'analysis' / 'summary' / 'manifest.json')
    for part in PARTITIONS:
        candidates.add(root / 'checkpoints' / part / 'manifest.json')
    for feature in FEATURES:
        for phase in ('calibration', 'verification'):
            candidates.add(root / 'analysis' / feature / phase / 'manifest.json')

    selected, missing, too_large, invalid = [], [], [], []
    total = 0
    for path in sorted(candidates):
        rel = path.relative_to(root)
        if not path.is_file():
            missing.append(str(rel))
            continue
        size = path.stat().st_size
        if size > MAX_FILE_SIZE or total + size > MAX_TOTAL_SIZE:
            too_large.append((str(rel), size))
            continue
        try:
            # Confirma se o arquivo e realmente JSON valido sem carregar dados brutos.
            with path.open('r', encoding='utf-8') as fh:
                json.load(fh)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            invalid.append((str(rel), str(exc)[:160]))
            continue
        selected.append((path, size))
        total += size

    summary = root / 'analysis' / 'summary' / 'manifest.json'
    lines = [
        'DIAGNOSTICO ETAPA 2 — TCC',
        'Campanha: ' + EXPECTED_CAMPAIGN,
        'Pasta de origem: ' + str(root),
        'Arquivos JSON selecionados: ' + str(len(selected)),
        'Volume total nao comprimido: ' + f'{total / (1024 * 1024):.2f} MiB',
        '',
        'ARQUIVOS INCLUIDOS:',
    ]
    lines += [f'- {p.relative_to(root)} ({s} bytes)' for p, s in selected]
    if missing:
        lines += ['', 'CAMINHOS OPCIONAIS NAO ENCONTRADOS:'] + ['- ' + p for p in missing]
    if too_large:
        lines += ['', 'ARQUIVOS NAO INCLUIDOS POR TAMANHO:'] + [f'- {p} ({s} bytes)' for p, s in too_large]
    if invalid:
        lines += ['', 'ARQUIVOS INVALIDOS/ILEGIVEIS:'] + [f'- {p}: {err}' for p, err in invalid]

    if summary in [p for p, _ in selected]:
        with summary.open('r', encoding='utf-8') as fh:
            data = json.load(fh)
        lines += ['', 'ESTRUTURA DO RESUMO CIENTIFICO:']
        if isinstance(data, dict):
            for key, value in data.items():
                lines.append(f'- {key}: {short_shape(value)}')
                if key in ('results', 'paired', 'eligibility') and isinstance(value, dict):
                    sample_key = next(iter(value), None)
                    if sample_key is not None:
                        lines.append(f'  Exemplo {key}[{sample_key!r}]: {short_shape(value[sample_key])}')
                        sample = value[sample_key]
                        if isinstance(sample, dict):
                            for inner_key, inner_val in list(sample.items())[:8]:
                                lines.append(f'    {inner_key}: {short_shape(inner_val)}')
        else:
            lines.append('- Raiz do JSON: ' + short_shape(data))
    else:
        lines += ['', 'ATENCAO: analysis/summary/manifest.json nao foi incluido.']

    lines += [
        '',
        'OBSERVACAO: dados extraidos apenas dos JSONs listados.',
        'Nenhum CSV, PCAP, log de requisicao ou dataset bruto foi copiado.',
        'Os numeros da campanha anterior nao foram acessados.',
    ]
    report = '\n'.join(lines) + '\n'

    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', compression=ZIP_DEFLATED, compresslevel=8) as archive:
        for path, _ in selected:
            arcname = str(Path(EXPECTED_CAMPAIGN) / path.relative_to(root))
            archive.write(path, arcname=arcname)
        archive.writestr('diagnostico_etapa2.txt', report)

    print('Campanha correta:', root.name)
    print('Arquivos incluidos:', len(selected))
    print('ZIP gerado:', output)
    print('Tamanho do ZIP:', f'{output.stat().st_size / (1024 * 1024):.2f} MiB')
    print('Resumo encontrado:', 'sim' if summary in [p for p, _ in selected] else 'NAO')
    if missing:
        print(f'Caminhos opcionais ausentes: {len(missing)} (listados no diagnostico do ZIP)')
    if too_large or invalid:
        print(f'ATENCAO: {len(too_large)} excederam limite e {len(invalid)} nao puderam ser lidos.')
    print('Envie este arquivo ZIP na conversa. Os arquivos originais nao foram alterados.')
    return 0 if summary in [p for p, _ in selected] else 1


if __name__ == '__main__':
    raise SystemExit(main())
