"""Direct-80 metrics: control FPR, complementary PRE, event, and POST persistence."""
from decimal import Decimal as D
from ..inputs import number,ContractError
from .engine import exact


@exact
def metrics(rows,truth,evaluated=True,reason=None):
    event=truth['events'][0] if truth['events'] else None
    start,end=(number(event['actual_start_seconds']),number(event['actual_end_seconds'])) if event else (None,None)
    def bucket(a,b):
        return dict(start=a,end=b,expected=0,available=0,positive=0,negative=0,unavailable=0,coverage=None,positive_fraction=None)
    control=bucket(30,390);pre=bucket(30,150);attack=bucket(150,270);post=bucket(270,390)
    first=None;positive_duration=D(0);post_last=None;boundary=0;still_offensive=0
    for row in rows:
        a,b,t=map(number,(row['window_start_seconds'],row['window_end_seconds'],row['available_at_seconds']))
        decision=row['decision']
        if t<b or (decision is not None and type(decision) is not bool):raise ContractError('Invalid decision availability/type')
        # Drain never participates, including event detections.
        if not 30<=a<b<=390:continue
        valid=evaluated and decision is not None and t<=390
        overlap=max(D(0),min(b,end)-max(a,start)) if event else D(0)
        if event and valid and decision is True and overlap>0 and start<=t<=end:
            first=t if first is None else min(first,t)
        selected=[]
        if not event:selected.append(control)
        else:
            if 30<=a<b<=150:selected.append(pre)
            if overlap==b-a:selected.append(attack)
            elif overlap>0:boundary+=1
            if a>=270:
                if a>=end:selected.append(post)
                elif overlap>0:still_offensive+=1
        for item in selected:
            item['expected']+=1
            if valid:
                item['available']+=1;item['positive']+=int(decision);item['negative']+=int(not decision)
                if item is post and decision:
                    positive_duration+=b-a;post_last=t
            else:item['unavailable']+=1
    for item in (control,pre,attack,post):
        item['coverage']=D(item['available'])/item['expected'] if item['expected'] else None
        item['positive_fraction']=D(item['positive'])/item['available'] if item['available'] and evaluated else None
    benign=pre if event else control
    tp,fn=attack['positive'],attack['negative'];fp,tn=benign['positive'],benign['negative']
    ratio=lambda x,y:D(x)/y if y and evaluated else None
    delay=None if first is None else first-start
    return dict(scientifically_evaluated=evaluated,reason=reason if not evaluated else None,
        control=control,pre=pre,attack=attack,post=post,post_still_offensive_windows=still_offensive,boundary=boundary,
        fp=fp if evaluated else None,tn=tn if evaluated else None,tp=tp if evaluated else None,fn=fn if evaluated else None,
        fpr=control['positive_fraction'] if not event else None,pre_fpr=pre['positive_fraction'] if event else None,
        recall=ratio(tp,tp+fn),precision=ratio(tp,tp+fp),f1=ratio(2*tp,2*tp+fp+fn),
        event_detected=None if not event or not evaluated else first is not None,
        observed_delay_seconds=delay if evaluated else None,first_detection_available_at_seconds=first if evaluated else None,
        restricted_undetected_fraction=None if not event or not evaluated else (delay/(end-start) if delay is not None else D(1)),
        post_positive_fraction=post['positive_fraction'],post_positive_duration_seconds=positive_duration if evaluated and event else None,
        post_last_alarm_available_seconds=post_last,post_persistence_since_emission_seconds=post_last-end if post_last is not None else None,
        post_duration_semantics='sum_of_supported_positive_window_durations_not_continuous_alarm_duration',
        benign_available=benign['available'],benign_windows=benign['expected'],unavailable=benign['unavailable']+attack['unavailable']+post['unavailable'],
        decision_coverage=ratio(benign['available']+attack['available']+post['available'],benign['expected']+attack['expected']+post['expected']),
        exposure_seconds=end-start if event else None,event_deadline_seconds=end,
        censor_at_seconds=end if event and evaluated and first is None else None,
        availability_basis='simulated_window_closure_or_explicit_recorded_availability_not_measured_processing')
