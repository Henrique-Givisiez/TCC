"""Verificação dirigida das exportações existentes; nunca executa runtime científico."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from PIL import Image

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
ORIGINAL = REPO / 'reports/scientific_reduced_clock_r2_temporal_20261102'
GENERATOR = ORIGINAL / 'generate.py'


def read(path):
    return json.loads(path.read_text())


def rows(path):
    with path.open(newline='') as stream:
        yield from csv.DictReader(stream)


def main():
    result = dict(selections={}, pdf_checks=[], frozen_delay_cells=0, directed_records=0)
    cp = read(REPO / 'experiment_results/scientific-reduced-clock-r2-20261029/checkpoints/TEST/manifest.json')
    summary = read(Path(cp['artifacts']['summary']['path']) / 'manifest.json')
    generator_hash = hashlib.sha256(GENERATOR.read_bytes()).hexdigest()
    for directory in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        prov = read(directory / 'provenance.json')
        assert prov['generator_sha256'] == generator_hash, directory
        for name, digest in prov['outputs'].items():
            assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest, name
        sources = list(rows(directory / 'tables/sources.csv'))
        if directory.name == 'delay':
            assert prov['evaluated_series'] == 0
            assert prov['selection']['delay_blocks'] == list(range(1, 13))
            assert all('/collection/' not in r['path'] and '/evaluation/' not in r['path'] for r in sources)
        if directory.name in ('cpu', 'single'):
            eid = 'sci56_TEST_B01_3_E16' if directory.name == 'cpu' else 'sci56_TEST_B12_3_C16'
            assert all(eid in r['path'] for r in sources if '/collection/' in r['path'])
        delay_table = directory / 'tables/conditional_delay_frozen.csv'
        if delay_table.exists():
            for r in rows(delay_table):
                official = summary['results'][f"{r['feature']}/{r['scenario']}/{r['method']}"]
                for field, value in official['delay'].items():
                    expected = '' if value is None else str(value)
                    assert r[field] == expected, (field, r, expected)
                assert r['support_blocks'] == 'B01–B12' and r['support_runs'] == '12'
                assert r['evaluated'] == (str(official['detection']['n']) if official['detection'] else '')
                assert r['misses'] == (str(official['misses']) if official['misses'] is not None else '')
                result['frozen_delay_cells'] += 1
        if directory.name in ('cpu', 'network', 'single', 'duration'):
            last = None
            for r in rows(directory / 'tables/temporal_records.csv'):
                key = r['feature'], r['entry']
                if key != last:
                    refs = [ref for ref in summary['evaluations'] if all(v in Path(ref['path']).parts for v in key)]
                    assert len(refs) == 1
                    ev = read(Path(refs[0]['path']) / 'manifest.json')
                    run = read(Path(ev['run']['path']) / 'manifest.json')
                    cal = read(Path(run['calibration']['path']) / 'manifest.json')
                    last = key
                official = run['methods'][r['method']][int(r['window_index'])]
                for field, value in official.items():
                    assert r[field] == ('' if value is None else str(value)), (key, field)
                assert r['threshold'] == cal['thresholds'][r['method']]
                result['directed_records'] += 1
            for boundary in rows(directory / 'tables/event_boundaries.csv'):
                if boundary['scenario'] == 'C16':
                    assert boundary['actual_start_seconds'] == boundary['actual_end_seconds'] == ''
        result['selections'][directory.name] = dict(selection=prov['selection'],
            evaluated_series=prov['evaluated_series'], source_files=prov['source_files'],
            figures=len(list((directory / 'figures').glob('*.pdf'))))
        for pdf in sorted((directory / 'figures').glob('*.pdf')):
            with tempfile.TemporaryDirectory() as temp:
                bbox = Path(temp) / 'bbox.html'
                subprocess.run(['pdftotext', '-bbox', str(pdf), str(bbox)], check=True, capture_output=True)
                doc = ET.parse(bbox).getroot()
                ns = {'x': 'http://www.w3.org/1999/xhtml'}
                page = doc.find('.//x:page', ns)
                width, height = float(page.get('width')), float(page.get('height'))
                words = doc.findall('.//x:word', ns)
                assert words
                for word in words:
                    assert 0 <= float(word.get('xMin')) < float(word.get('xMax')) <= width, (pdf, word.text)
                    assert 0 <= float(word.get('yMin')) < float(word.get('yMax')) <= height, (pdf, word.text)
            fonts = subprocess.run(['pdffonts', str(pdf)], capture_output=True, text=True, check=True).stdout
            assert 'TrueType' in fonts and all(' yes ' in line for line in fonts.splitlines()[2:])
            images = subprocess.run(['pdfimages', '-list', str(pdf)], capture_output=True, text=True, check=True).stdout
            assert len(images.splitlines()) == 2, pdf
            with Image.open(pdf.with_suffix('.png')) as im:
                assert all(abs(d-300) < .1 for d in im.info['dpi'])
            result['pdf_checks'].append(dict(file=str(pdf.relative_to(ROOT)), page_points=[width, height],
                raster_images=0, embedded_fonts=True, text_inside_page=True, png_dpi=300))
    previous = {tuple(r[k] for k in ('entry','feature','method','window_index')): r
                for r in rows(ORIGINAL / 'tables/temporal_records.csv')}
    compatibility = 0
    for r in rows(ROOT / 'legacy/tables/temporal_records.csv'):
        old = previous[tuple(r[k] for k in ('entry','feature','method','window_index'))]
        assert old == r
        compatibility += 1
    old_figures = {p.name for p in (ORIGINAL / 'figures').iterdir()}
    assert {p.name for p in (ROOT / 'legacy/figures').iterdir()} == old_figures
    for name in ('D_context_display.csv', 'conditional_delay_frozen.csv'):
        old_rows, new_rows = list(rows(ORIGINAL/'tables'/name)), list(rows(ROOT/'legacy/tables'/name))
        assert len(old_rows) == len(new_rows)
        for a, b in zip(old_rows, new_rows):
            assert all(b[k] == v for k,v in a.items()), name
    result['compatibility_records_identical'] = compatibility
    result['legacy_figure_names_identical'] = True
    result['generator_sha256'] = generator_hash
    test = subprocess.run([sys.executable, '-B', str(ORIGINAL/'test_cli.py')], capture_output=True, text=True)
    assert test.returncode == 0, test.stderr
    result['cli_tests'] = test.stderr
    (ROOT/'verification.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('pdf_checks','selections','cli_tests')}, indent=2))
    print('PDFs verificados:', len(result['pdf_checks']))


if __name__ == '__main__':
    main()
