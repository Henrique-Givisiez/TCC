"""Inspect immutable image files without running image code or rebuilding it."""
import hashlib
import io
from pathlib import Path
import shlex
import tarfile


def expected_files(role, repository=None):
    root = Path(repository) if repository else Path(__file__).resolve().parents[1]
    if role == 'victim':
        files = {'/app/'+str(p.relative_to(root/'simulator/app')):p
                 for p in (root/'simulator/app').rglob('*.py')}
        files['/app/diagnostics.py'] = root/'simulator/diagnostics.py'
    else:
        files = {}
        for line in (root/'docker/Dockerfile.sources').read_text().splitlines():
            parts = shlex.split(line)
            if parts and parts[0] == 'COPY':
                for source in parts[1:-1]:
                    files[parts[-1].rstrip('/')+'/'+Path(source).name if parts[-1].endswith('/') else parts[-1]] = root/source
    return {path:hashlib.sha256(p.read_bytes()).hexdigest() for path,p in files.items()}


def verify_image_code(client, images):
    evidence = {}
    for role, image in images.items():
        expected = expected_files(role)
        configuration = client.images.get(image).attrs['Config']
        if configuration.get('WorkingDir') != '/app' or (
                role == 'source' and configuration.get('Entrypoint') != ['python','-B','-m','simulator.source_runner']) or (
                role == 'victim' and (configuration.get('Entrypoint') or configuration.get('Cmd') != ['python','simple_server.py'])):
            raise RuntimeError('image launch configuration differs: '+role)
        container = client.containers.create(image, network_disabled=True, entrypoint=['/bin/true'],
                                             labels={'edos.role':'image_inspection'})
        try:
            container.reload()
            if container.attrs['Image'] != image:
                raise RuntimeError('inspection container image changed')
            chunks, _ = container.get_archive('/app')
            data = bytearray()
            for chunk in chunks:
                data.extend(chunk)
                if len(data) > 16*1024*1024:
                    raise RuntimeError('image code archive exceeds inspection budget')
            observed = {}
            with tarfile.open(fileobj=io.BytesIO(data)) as archive:
                for member in archive:
                    path = '/'+member.name.lstrip('./')
                    if path in expected or (member.isfile() and path.endswith('.py')):
                        if not member.isfile() or path in observed:
                            raise RuntimeError('ambiguous image code member: '+path)
                        observed[path] = hashlib.sha256(archive.extractfile(member).read()).hexdigest()
            if observed != expected:
                raise RuntimeError('image code differs from checkout: '+role+'; prepare new immutable image')
            evidence[role] = dict(image_id=image, files=observed, verified=True)
        finally:
            try:
                container.remove(force=True)
            except Exception as exc:
                raise RuntimeError('image inspection cleanup failed: '+container.id) from exc
    return evidence
