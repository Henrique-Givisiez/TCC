"""Unreleased recovery-rule proposal: synthetic traces only, no historical re-scoring.

This module is not imported by operational D3 tools or any detector/calibration.
"""
from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True)
class Request:
    start: float
    end: float | None
    outcome: str = 'success'
    origin: int = 0


@dataclass(frozen=True)
class Opportunity:
    time: float
    origin: int = 0


PARAMETERS = dict(nominal_post_start=270, nominal_post_end=390, window_seconds=30,
    minimum_exposure_fraction=.95, grace_seconds=3, minimum_starts=200,
    minimum_success_duration_support=200, minimum_success_fraction=.99,
    maximum_failure_or_deadline_miss_fraction=.01, reference_success_tolerance=.01,
    maximum_p95_ratio=1.25, nominal_rps=16, nominal_offer_ratio=[.8,1.2],
    minimum_start_per_real_opportunity=.95, maximum_start_per_real_opportunity=1.05,
    minimum_origin_start_per_real_opportunity=.95, maximum_origin_start_per_real_opportunity=1.05,
    pending_floor=4, pending_reference_factor=1.25, maximum_pending_growth_per_window=2,
    maximum_pending_growth_over_confirmation=2, consecutive_windows=2)


def p95(values):
    """Empirical linear type-7; retain n separately."""
    if not values:
        return None
    values=sorted(values)
    x=(len(values)-1)*.95; i=int(x)
    return values[i]+(values[min(i+1,len(values)-1)]-values[i])*(x-i)


def pending(requests, boundary):
    # Left limit: begins and terminal events exactly at boundary belong to the
    # next [a,b) window. This convention makes conservation exact.
    return [r for r in requests if r.start < boundary and (r.end is None or r.end >= boundary)]


def measure(requests, a, b, *, cutoff, grace=3):
    if b <= a:
        return None
    cohort=[r for r in requests if a <= r.start < b]
    deadline=b+grace
    mature=cutoff >= b and (cutoff >= deadline or all(r.end is not None and r.end <= cutoff for r in cohort))
    known=[r for r in cohort if r.end is not None and r.end <= min(deadline,cutoff)]
    successes=[r for r in known if r.outcome=='success']
    durations=[1000*(r.end-r.start) for r in successes]
    terminals=[r for r in requests if r.end is not None and a <= r.end < b]
    terminal_successes=[r for r in terminals if r.outcome=='success']
    pa,pb=pending(requests,a),pending(requests,b)
    if len(pb)-len(pa) != len(cohort)-len(terminals):
        raise ValueError('Begin/end/pending conservation failed')
    n=len(cohort)
    return dict(a=a,b=b,exposure=b-a,cohort_mature=mature,deadline=deadline,
        starts=n,terminal_ends=len(terminals),terminal_successes=len(terminal_successes),
        start_rps=n/(b-a),terminal_rps=len(terminals)/(b-a),terminal_2xx_rps=len(terminal_successes)/(b-a),
        success_fraction=len(successes)/n if n else None,
        known_terminal_fraction=len(known)/n if n else None,
        failure_or_deadline_miss_fraction=(n-len(successes))/n if n else None,
        duration_2xx_n=len(durations),p95_ms=p95(durations),
        pending_at_start=len(pa),pending_at_end=len(pb),pending_change=len(pb)-len(pa),
        aged_pending_at_end=sum(b-r.start > grace for r in pb),
        starts_by_origin={i:sum(r.origin==i for r in cohort) for i in range(4)},
        conservation_pass=True)


def make_reference(requests, a, b, *, cutoff):
    m=measure(requests,a,b,cutoff=cutoff)
    m['pending_p95']=p95([len(pending(requests,t)) for t in range(ceil(a),ceil(b))])
    return m


def evaluate(requests, opportunities, references, *, emission_end, cutoff=420,
             attack_requests=(), prior_supported_impairment=False, collection_ok=True):
    """Pure candidate evaluator for constructed traces, not a pilot reviewer.

    The prototype assumes opportunity evidence is independently reconciled with
    dispatcher logs; it cannot prove that provenance from aggregate counts.
    """
    result=dict(proposal_only=True,operational_authority=False,windows=[],recovery_confirmed_by=None,
        last_two_qualified=False,loss_of_qualification_after_confirmation=False,
        reasons_after_confirmation=[],right_censored=False,post_horizon=390,
        prior_supported_impairment=prior_supported_impairment)
    if not collection_ok or emission_end is None:
        result.update(state='unassessable_collection_or_emission',progression_eligible=False)
        return result
    reference_ok=all(r['cohort_mature'] and r['starts']>=200 and r['duration_2xx_n']>=200
        and r['success_fraction']>=.99 and r['failure_or_deadline_miss_fraction']<=.01
        and r['p95_ms'] is not None for r in references)
    if not reference_ok or len(references)!=2:
        result.update(state='insufficient_reference',progression_eligible=False)
        return result
    p95_limit=1.25*min(r['p95_ms'] for r in references)
    success_limit=max(.99,max(r['success_fraction']-.01 for r in references))
    pending_limit=max(4,ceil(1.25*max(r['pending_p95'] for r in references)))
    streak=[]; confirmed=None
    for i in range(4):
        nominal_a, b=270+30*i,300+30*i
        a=max(nominal_a,270,emission_end)
        if a>=b:
            result['windows'].append(dict(index=i+1,nominal_interval=[nominal_a,b],effective_interval=None,
                qualified=False,reason='no_effective_post_emission_exposure'))
            streak=[]
            continue
        m=measure(requests,a,b,cutoff=cutoff)
        coverage=(b-a)/30
        support=(coverage>=.95 and m['cohort_mature'] and m['starts']>=200 and m['duration_2xx_n']>=200)
        service_checks=dict(success=m['success_fraction'] is not None and m['success_fraction']>=success_limit,
            failures_and_deadline_misses=m['failure_or_deadline_miss_fraction'] is not None and m['failure_or_deadline_miss_fraction']<=.01,
            latency=m['p95_ms'] is not None and m['p95_ms']<=p95_limit,
            bounded_pending=m['pending_at_end']<=pending_limit,
            no_aged_pending=m['aged_pending_at_end']==0,
            no_persistent_pending_growth=m['pending_change']<=2,
            offensive_client_pending_cleared=len(pending(attack_requests,b))==0)
        # A high failure fraction remains an impairment signal even when the
        # success-duration sample becomes too small for latency confirmation.
        impairment_observable=coverage>=.95 and m['cohort_mature'] and m['starts']>=200
        impaired=impairment_observable and any(not value for key,value in service_checks.items() if key!='offensive_client_pending_cleared')
        if opportunities is None:
            arrival=dict(status='unknown_real_offer',adequate=False,nominal_expected=16*(b-a))
        else:
            own=[o for o in opportunities if a<=o.time<b]
            per_origin={i:sum(o.origin==i for o in own) for i in range(4)}
            offer_ratio=len(own)/(16*(b-a))
            start_ratio=m['starts']/len(own) if own else None
            origin_ratios={i:m['starts_by_origin'][i]/n if n else None for i,n in per_origin.items()}
            adequate=(.8<=offer_ratio<=1.2 and start_ratio is not None and .95<=start_ratio<=1.05
                and all(x is not None and .95<=x<=1.05 for x in origin_ratios.values()))
            arrival=dict(status='adequate' if adequate else 'insufficient_or_generator_limited',adequate=adequate,
                nominal_expected=16*(b-a),real_opportunities=len(own),real_offer_over_nominal=offer_ratio,
                starts_per_real_opportunity=start_ratio,per_origin_start_ratios=origin_ratios)
        qualified=support and arrival['adequate'] and all(service_checks.values())
        state=('compatible' if qualified else 'service_impaired' if impaired and arrival['adequate'] else
               'service_impaired_with_arrival_ambiguity' if impaired else
               'arrival_unknown_or_inadequate' if not arrival['adequate'] else
               'offensive_client_drain_pending' if not service_checks['offensive_client_pending_cleared'] else 'insufficient_support')
        w=dict(index=i+1,nominal_interval=[nominal_a,b],effective_interval=[a,b],coverage=coverage,
            measurements=m,arrival=arrival,service_checks=service_checks,
            limits=dict(success_fraction_min=success_limit,p95_ms_max=p95_limit,pending_max=pending_limit),
            qualified=qualified,state=state)
        result['windows'].append(w)
        streak=(streak+[w]) if qualified else []
        if len(streak)>=2:
            growth=streak[-1]['measurements']['pending_at_end']-streak[-2]['measurements']['pending_at_start']
            if growth>2:
                w.update(qualified=False,state='pending_growth_over_confirmation');streak=[]
            elif confirmed is None:
                confirmed=b
        if confirmed is not None and b>confirmed and not w['qualified']:
            result['reasons_after_confirmation'].append(dict(window=i+1,state=w['state']))
    result['first_post_compatibility_confirmed_by']=confirmed
    result['recovery_confirmed_by']=confirmed if prior_supported_impairment else None
    result['last_two_qualified']=len(streak)>=2
    result['loss_of_qualification_after_confirmation']=bool(result['reasons_after_confirmation'])
    result['right_censored']=confirmed is None
    result['censor_at']=min(390,cutoff) if confirmed is None else None
    result['state']=('recovery_observed' if prior_supported_impairment else 'post_compatible_no_prior_impairment') if confirmed else 'not_confirmed'
    result['progression_eligible']=False  # A synthetic proposal never authorizes execution.
    return result


def trace(a,b,n,*,duration=.05,failure_every=None):
    """Construct records mathematically; does not execute a traffic generator."""
    records=[]
    for i in range(n):
        start=a+.1+(b-a-.2)*(i+.5)/n
        fail=failure_every is not None and i%failure_every==0
        records.append(Request(start,start+(2 if fail else duration),'transport_error' if fail else 'success',i%4))
    return records


def synthetic_cases():
    # These are fabricated counts/timings, not data from C/E4 or fitted seeds.
    pre=trace(30,150,1920)
    control=trace(30,390,5760)
    refs=[make_reference(pre,30,150,cutoff=420),make_reference(control,30,390,cutoff=420)]
    cases={}
    for name, counts, durations, failures, prior, emission in (
        ('benign_arrival_variation',[440,520,450,510],[.05]*4,[None]*4,False,270.0015),
        ('persistent_degradation',[480]*4,[.5]*4,[5]*4,True,270.0015),
        ('real_recovery',[480]*4,[.5,.05,.05,.05],[5,None,None,None],True,270.0015)):
        active=trace(150,270,1920,duration=.5 if prior else .05,failure_every=5 if prior else None)
        requests=list(pre)+active
        active_metrics=measure(requests,150,270,cutoff=420)
        demonstrated_impairment=(active_metrics['success_fraction']<.99 or active_metrics['p95_ms']>1.25*min(r['p95_ms'] for r in refs))
        assert demonstrated_impairment == prior
        for i,n in enumerate(counts):
            a=max(270+i*30,emission)
            requests+=trace(a,300+i*30,n,duration=durations[i],failure_every=failures[i])
        opportunities=[Opportunity(r.start-.001,r.origin) for r in requests]
        cases[name]=evaluate(requests,opportunities,refs,emission_end=emission,prior_supported_impairment=demonstrated_impairment)
        cases[name]['active_metrics']=active_metrics
        cases[name]['prior_impairment_verified_from_synthetic_active']=demonstrated_impairment
    healthy=list(pre)+[r for i in range(4) for r in trace(270+30*i,300+30*i,480)]
    cases['unknown_real_offer']=evaluate(healthy,None,refs,emission_end=270)
    offers=[Opportunity(r.start-.001,r.origin) for r in healthy]
    sparse=list(pre)+[r for i in range(4) for r in trace(270+30*i,300+30*i,240)]
    cases['generator_shortfall']=evaluate(sparse,offers,refs,emission_end=270)
    cases['old_pending_despite_new_success']=evaluate(healthy+[Request(260+i*.01,None,origin=i%4) for i in range(12)],offers,refs,emission_end=270,prior_supported_impairment=True)
    cases['collection_failure']=evaluate(healthy,offers,refs,emission_end=270,collection_ok=False)
    cases['large_certification_delay']=evaluate(healthy,offers,refs,emission_end=272)
    return cases
