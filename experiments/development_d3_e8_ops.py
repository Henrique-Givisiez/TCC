"""Single E8 readiness/run adapter. No Docker access at import or --help."""
import argparse
from contextlib import contextmanager
import time

from experiments import development_d3_minimal_ops as operations
from experiments import development_d3_e8 as e8



def get_plan():
    return e8.base.read(e8.DEFAULT_MANIFEST),e8.validate_plan(check_outputs=False)


def check_predecessors(plan,index):
    if index!=0 or len(plan['entries'])!=1 or plan['entries'][0]['id']!=e8.ENTRY_ID:
        raise ValueError('Only the prospective E8-R2 belongs here')
    previous=e8.predecessor(plan)
    cleanup=previous['operations']['cleanup']['observed_epoch']
    elapsed=time.time()-cleanup
    if elapsed<60:raise ValueError('At least 60 seconds idle after E4-R2 cleanup required')
    return [dict(entry=previous['entry_id'],review_sha256=plan['predecessor']['review_sha256'],idle_seconds=elapsed)]


def prior_snapshot(ops):
    roots=[e8.ROOT/'experiment_results'/name for name in (
        'development-d1-20261027','development-d2-endpoint-comparison-20261027',
        'development-d3-pilots-20261028','development-d3-minimal-20261028','development-d3-e8-20261028')]
    return {str(p.relative_to(e8.ROOT)):e8.base.sha(p) for root in roots for p in root.rglob('*') if p.is_file() and ops not in p.parents}


@contextmanager
def operations_context():
    changes=dict(ROOT=e8.ROOT,ACTIVE_MANIFEST=e8.DEFAULT_MANIFEST,ENTRY_ID=e8.ENTRY_ID,
        BASE=e8.ROOT/'experiment_results/development-d3-e8-20261028',get_plan=get_plan,
        check_predecessors=check_predecessors,prior_snapshot=prior_snapshot)
    before={k:getattr(operations,k) for k in changes}
    try:
        for key,value in changes.items():setattr(operations,key,value)
        yield
    finally:
        for key,value in before.items():setattr(operations,key,value)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    for action in ('preflight','run'):
        cmd=sub.add_parser(action);cmd.add_argument('--entry',choices=(e8.ENTRY_ID,),required=True)
        if action=='run':
            cmd.add_argument('--preflight-id',required=True);cmd.add_argument('--authorize-entry',required=True)
    args=p.parse_args()
    if args.action=='run' and args.authorize_entry!=e8.ENTRY_ID:raise ValueError('Authorization must name exactly the E8-R2 entry')
    with operations_context():
        if args.action=='preflight':operations.preflight(args.entry)
        else:operations.run_entry(args.entry,args.preflight_id)


if __name__=='__main__':main()
