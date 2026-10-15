"""Read-only host/environment capture, written to a new audit file."""
import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from .prepare import write,sha,PROTOCOL,EXPECTED


def command(*args):
    result=subprocess.run(args,text=True,capture_output=True)
    return dict(command=list(args),returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)


def capture():
    commands=[['git','rev-parse','HEAD'],['git','branch','--show-current'],['git','status','--porcelain=v1','--untracked-files=all'],
        ['uname','-a'],['lscpu'],['free','-b'],[sys.executable,'--version'],[sys.executable,'-m','pip','freeze'],
        ['docker','context','show'],['docker','version'],
        ['docker','info','--format','id={{.ID}} name={{.Name}} os={{.OperatingSystem}} kernel={{.KernelVersion}} version={{.ServerVersion}} driver={{.Driver}} cgroup={{.CgroupVersion}} cpus={{.NCPU}} memory={{.MemTotal}}'],
        ['docker','ps','--no-trunc'],['docker','image','inspect','edos_target_app:latest','edos_sources:stage5','nginx:1.28.0-alpine'],
        ['ps','-eo','pid,user,comm,args']]
    paths=set()
    for root in ['simulator','analysis','experiments','docker']:
        paths.update(p for p in Path(root).rglob('*') if p.is_file() and p.suffix in ('.py','.json') and '__pycache__' not in p.parts)
    paths.update(p for p in Path('docker').rglob('*') if p.is_file())
    paths.update([Path('Dockerfile'),Path('requirements.txt'),PROTOCOL])
    return dict(captured_at_utc=datetime.now(timezone.utc).isoformat(),platform=platform.platform(),architecture=platform.machine(),
        os_release=Path('/etc/os-release').read_text(),meminfo=Path('/proc/meminfo').read_text(),
        python=sys.version,python_executable=sys.executable,load_average=os.getloadavg(),
        expected_protocol_sha256=EXPECTED,protocol_sha256=sha(PROTOCOL),
        commands=[command(*c) for c in commands],files_sha256={str(p):sha(p) for p in sorted(paths)},
        interpretation='Observed environment, not a hardware performance equivalence assertion; Git dirty details included verbatim')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();write(a.output,capture())
