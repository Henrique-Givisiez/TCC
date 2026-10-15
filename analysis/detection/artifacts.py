"""Deterministic, new-directory-only artifacts; no raw datasets copied."""
import csv
from dataclasses import dataclass
from decimal import Decimal
import inspect
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

from .inputs import ContractError, digest, read_json, safe_file


def plain(value):
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ContractError('Nonfinite artifact value')
        return str(value)
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise ContractError('Artifact keys must be strings')
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ContractError('Artifact parameters must be JSON data')


def encoded(value):
    return json.dumps(plain(value), sort_keys=True, indent=2, allow_nan=False) + '\n'


def component(spec):
    if not spec.name or not spec.version or spec.missing not in ('reject', 'preserve'):
        raise ContractError('Invalid component identity/missing policy')
    return json.loads(encoded(dict(name=spec.name, version=spec.version,
                                  config=dict(spec.config), missing=spec.missing)))


def provenance(implementation):
    base = Path(__file__).resolve().parent
    files = {str(p.relative_to(base)): digest(p) for p in sorted(base.rglob('*.py'))}
    try:
        source = inspect.getsourcefile(type(implementation))
        if source is None:
            raise ContractError('Component implementation needs inspectable source provenance')
        impl = dict(qualified_class=f'{type(implementation).__module__}.{type(implementation).__qualname__}',
                    source_path=str(Path(source).resolve()), source_sha256=digest(source))
    except TypeError as exc:
        raise ContractError('Component source unavailable') from exc
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=base,
                                         stderr=subprocess.DEVNULL, timeout=5).decode().strip()
    except (OSError, subprocess.SubprocessError):
        commit = None
    return dict(scope='stage11_framework_and_component', framework_files_sha256=files,
                component=impl, git_commit=commit, effective_sources_recorded_by_hash=True,
                python=platform.python_version(), platform=platform.platform())


@dataclass(frozen=True)
class Artifact:
    root: Path
    manifest_sha256: str

    def read(self, kind=None):
        p = safe_file(self.root, 'manifest.json')
        if digest(p) != self.manifest_sha256:
            raise ContractError('Artifact manifest changed')
        m = read_json(p)
        if m.get('schema_version') != 1 or (kind and m.get('kind') != kind):
            raise ContractError('Wrong artifact kind/schema')
        for out in m['outputs']:
            path = safe_file(self.root, out['path'])
            if digest(path) != out['sha256'] or path.stat().st_size != out['bytes']:
                raise ContractError('Artifact output changed')
        return m

    @property
    def reference(self):
        self.read()
        return dict(path=str(self.root), manifest_sha256=self.manifest_sha256)


def open_artifact(reference, kind=None):
    a = Artifact(Path(reference['path']).resolve(), reference['manifest_sha256'])
    a.read(kind)
    return a


def publish(destination, kind, metadata, *, table=None, protected=()):
    raw = Path(destination).absolute()
    target = raw.resolve()
    if any(p.is_symlink() for p in (raw, *raw.parents)):
        raise ContractError('Symlink output refused')
    for root in protected:
        root = Path(root).resolve()
        if target == root or root in target.parents or target in root.parents:
            raise ContractError('Output overlaps an input')
    if target.exists():
        raise ContractError('Destination must be new (no overwrite)')
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.stage11-', dir=target.parent))
    try:
        outputs = []
        if table is not None:
            name, columns, rows = table
            with (temp / name).open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n')
                writer.writeheader()
                writer.writerows(rows)
            p = temp / name
            outputs.append(dict(path=name, sha256=digest(p), bytes=p.stat().st_size))
        manifest = dict(schema_version=1, kind=kind, **metadata, outputs=outputs)
        (temp / 'manifest.json').write_text(encoded(manifest))
        # No replace: an existing destination (even empty) is never overwritten.
        os.mkdir(target)
        try:
            for p in temp.iterdir():
                os.rename(p, target / p.name)
        except BaseException:
            shutil.rmtree(target)
            raise
    finally:
        shutil.rmtree(temp)
    return Artifact(target, digest(target / 'manifest.json'))
