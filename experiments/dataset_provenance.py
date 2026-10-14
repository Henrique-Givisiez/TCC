"""Scoped code/environment observations; never infer past execution provenance."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _command(args, directory):
    result = subprocess.run(args, cwd=directory, capture_output=True, timeout=10)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace').strip())
    return result.stdout


def capture_provenance(scope, repository=ROOT, docker_endpoint=None):
    repository = Path(repository).resolve()
    files = {}
    for pattern in ('simulator/**/*.py', 'experiments/**/*.py', 'Dockerfile', 'docker/*', 'requirements.txt'):
        for path in repository.glob(pattern):
            if path.is_file() and not path.is_symlink():
                files[path.relative_to(repository).as_posix()] = sha256_file(path)
    files = dict(sorted(files.items()))
    fingerprint = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    git = dict(status='unavailable', commit=None, dirty=None, changes=[])
    try:
        commit = _command(['git', 'rev-parse', 'HEAD'], repository).decode().strip()
        entries = iter(_command(['git', 'status', '--porcelain=v1', '-z', '--untracked-files=all'], repository).decode().split('\0'))
        changes = []
        for entry in entries:
            if not entry:
                continue
            item = dict(status=entry[:2], path=entry[3:])
            if 'R' in entry[:2] or 'C' in entry[:2]:
                item['original_path'] = next(entries)
            changes.append(item)
        git.update(status='recorded', commit=commit, dirty=bool(changes), changes=changes)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        git['reason'] = str(exc)
    environment = dict(python=sys.version, implementation=platform.python_implementation(),
                       platform=platform.platform(), kernel=platform.release(), machine=platform.machine())
    try:
        environment['os_release'] = platform.freedesktop_os_release()
    except OSError:
        pass
    docker = dict(status='not_queried')
    if docker_endpoint is not None:
        docker = dict(status='unavailable', endpoint=docker_endpoint)
        try:
            version = json.loads(_command(['docker', '--host', docker_endpoint, 'version', '--format', '{{json .}}'], repository))
            docker.update(status='recorded', version=version)
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            docker['reason'] = str(exc)
    return dict(schema_version=1, scope=scope, captured_at_utc=datetime.now(timezone.utc).isoformat(),
                code=dict(git=git, runtime_files_sha256=files, runtime_tree_sha256=fingerprint,
                          fingerprint_scope='simulator, experiments, Docker recipes and requirements; no source contents/diff'),
                host_environment=environment, docker=docker)
