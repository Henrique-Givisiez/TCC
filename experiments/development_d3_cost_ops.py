"""Explicit one-entry D3_cost preflight/run; review required between entries."""
import argparse
from contextlib import contextmanager
import time

from experiments import development_d3_minimal_ops as operations
from experiments import development_d3_cost as cost

REVIEWED_SHA256=None


def get_plan():return cost.read(cost.DEFAULT_MANIFEST),cost.validate_plan(check_outputs=False)


def check_predecessors(plan,index):
    if not 0<=index<4:raise ValueError('Invalid entry index')
    if index==0:
        _,pilot=cost.exploratory_evidence(plan)
        idle=time.time()-pilot['operations']['cleanup']['observed_epoch']
        if idle<60:raise ValueError('At least60s idle after exploratory pilot cleanup required')
        return [dict(entry=pilot['entry_id'],role='exploratory_readiness_only',review_sha256=plan['E8_reference']['review_sha256'],idle_seconds=idle)]
    records=[]
    # Every earlier entry must remain audited; the immediate review is manually
    # selected by hash on both preflight and run, never implicitly approved.
    for previous in plan['entries'][:index]:
        r=cost.reviewed_entry(plan,previous,cost.DEFAULT_MANIFEST)
        if not cost.gate_passes(r):raise ValueError('Predecessor blocks progression: '+previous['id'])
        records.append(dict(entry=previous['id'],review_sha256=cost.base.sha(cost.ROOT/previous['outputs']['review'])))
    if REVIEWED_SHA256!=records[-1]['review_sha256']:raise ValueError('Explicit --reviewed-sha256 must select immediate predecessor review')
    cleanup=r['operations']['cleanup']['observed_epoch'];idle=time.time()-cleanup
    if idle<60:raise ValueError('At least60s idle after predecessor cleanup required')
    records[-1]['idle_seconds']=idle
    return records


def prior_snapshot(ops):
    roots=[cost.ROOT/'experiment_results'/name for name in ('development-d1-20261027','development-d2-endpoint-comparison-20261027',
        'development-d3-pilots-20261028','development-d3-minimal-20261028','development-d3-e8-20261028','development-d3-cost-20261028')]
    return {str(p.relative_to(cost.ROOT)):cost.base.sha(p) for root in roots for p in root.rglob('*') if p.is_file() and ops not in p.parents}


@contextmanager
def operations_context():
    changes=dict(ROOT=cost.ROOT,ACTIVE_MANIFEST=cost.DEFAULT_MANIFEST,
        BASE=cost.ROOT/'experiment_results/development-d3-cost-20261028',get_plan=get_plan,
        check_predecessors=check_predecessors,prior_snapshot=prior_snapshot)
    before={k:getattr(operations,k) for k in changes}
    try:
        for k,v in changes.items():setattr(operations,k,v)
        yield
    finally:
        for k,v in before.items():setattr(operations,k,v)


def main():
    global REVIEWED_SHA256
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    for action in ('preflight','run'):
        cmd=sub.add_parser(action);cmd.add_argument('--entry',choices=cost.ENTRY_IDS,required=True);cmd.add_argument('--reviewed-sha256')
        if action=='run':cmd.add_argument('--preflight-id',required=True);cmd.add_argument('--authorize-entry',required=True)
    args=p.parse_args();REVIEWED_SHA256=args.reviewed_sha256
    if args.action=='run' and args.authorize_entry!=args.entry:raise ValueError('Authorization must name exactly selected entry')
    with operations_context():
        if args.action=='preflight':operations.preflight(args.entry)
        else:operations.run_entry(args.entry,args.preflight_id)


if __name__=='__main__':main()
