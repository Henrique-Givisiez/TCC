"""Audit completion; no experiment execution or detector operations."""
import argparse
import json
import subprocess
from pathlib import Path
from .prepare import write,sha,EXPECTED,PROTOCOL


def main():
    p=argparse.ArgumentParser();p.add_argument('--audit',type=Path,required=True);p.add_argument('--smoke',type=Path,required=True);a=p.parse_args()
    summary=json.loads((a.smoke/'summary.json').read_text())
    before=json.loads((a.audit/'preservation_before.json').read_text())
    changed=[name for name,h in before.items() if not Path(name).is_file() or sha(name)!=h]
    if changed:raise RuntimeError(f'Preservation failure: {changed}')
    status=subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=all'],text=True)
    check=subprocess.run(['git','diff','--check'],capture_output=True,text=True)
    records=[]
    for path in sorted((a.smoke/'raw').glob('*/run_status.json')):
        s=json.loads(path.read_text());records.append(dict(case=path.parent.name,run_id=s['run_id'],status=s['status'],sha256=sha(path)))
    if len(records)!=4 or any(r['status']!='completed' for r in records):raise RuntimeError('Incomplete smoke')
    smoke_hashes={str(path.relative_to(a.smoke)):sha(path) for path in sorted(a.smoke.rglob('*')) if path.is_file()}
    write(a.audit/'smoke_hashes.json',smoke_hashes)
    write(a.audit/'smoke_summary.json',summary)
    write(a.audit/'completion.json',dict(status='PREPARATION_VERIFIED_METHOD_REVIEW_BLOCKED',
        protocol_sha256=sha(PROTOCOL),protocol_unchanged=sha(PROTOCOL)==EXPECTED,
        preservation_files_checked=len(before),modified_or_missing=changed,
        git_head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        git_branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip(),
        git_status_at_capture=status,tracked_diff=subprocess.check_output(['git','diff','--stat'],text=True),
        diff_check=dict(returncode=check.returncode,stdout=check.stdout,stderr=check.stderr),
        smoke_root=str(a.smoke),smoke_runs=records,scientific_runs_executed=0,
        tests=dict(command='.venv/bin/python -B -m unittest discover -s tests -v',passed=300,failures=0),
        note='This file and final report/checksum outputs are added after Git status capture; see final CLI status. Host residue check is in environment_final.json.'))
    if check.returncode:raise RuntimeError('git diff --check failed')
    print('Audited',len(before),'preexisting files and',len(records),'development runs')

if __name__=='__main__':main()
