"""Read-only deterministic replay using frozen parameters; derived outputs only here.
Run from root with .venv/bin/python -B reports/investigacao-detectores-energy-20261110/analisar.py
No fitting, threshold selection, artifact publisher or collection is called.
"""
from pathlib import Path
import os,sys,json,csv,hashlib,math
from decimal import Decimal as D,localcontext
from collections import defaultdict
import numpy as np
import pandas as pd
P=Path(__file__).resolve().parent;ROOT=P.parents[1];sys.path.insert(0,str(ROOT))
BASE=ROOT/'experiment_results/scientific-energy-powersaver-20261109'
os.environ['SCIENTIFIC_SPEC_PATH']=str(ROOT/'docs/scientific_protocol_direct_c135_o3_20261108.json')
os.environ['SCIENTIFIC_SPEC_SHA256']='c97f8ece0198af720af4781409c12332508b45073cb62234a2c105864bf28018'
from analysis.detection.contracts import Observation
from analysis.detection.detectors.zscore import ZScore,zscore_spec
from analysis.detection.detectors.cov import CoV,cov_spec
from analysis.detection.detectors.ewma import EWMA,ewma_spec
from analysis.detection.detectors.cusum_freeze import CUSUMFreeze
from analysis.detection.detectors._moments import CONTEXT,sample_moments,decimal_ratio,standard_deviation
from analysis.detection.scientific.direct_metrics import metrics
from analysis.detection.artifacts import encoded

hashes={};mismatches=[];checks=defaultdict(int)
def read(p):
    p=Path(p);b=p.read_bytes();hashes[str(p.relative_to(ROOT))]=hashlib.sha256(b).hexdigest();return b.decode()
def js(p):return json.loads(read(p))
def rows(p):return list(csv.DictReader(read(p).splitlines()))
def num(x):return None if x is None or x=='' else D(str(x))
def fl(x):return float(x) if x is not None else np.nan
def compare(a,b,context):
    checks['comparisons']+=1
    if isinstance(a,(D,)):ok=num(b)==a
    else:ok=a==b
    if not ok:mismatches.append(dict(context=context,reconstructed=str(a),persisted=str(b)))
def mmean(g,col):return g[col].mean() if len(g) else np.nan
plan=js(ROOT/'experiments/protocols/energy-powersaver-20261109/plan.json');entries=[e for e in plan['entries'] if e['partition']=='TEST']
assert len(entries)==60
spec=js(ROOT/'docs/scientific_protocol_direct_c135_o3_20261108.json')['specification'];features=spec['features'];assert len(features)==4
# Code used by replay must match the campaign freeze, not merely resemble it.
for name,digest in plan['runtime_hashes'].items():
    actual=hashlib.sha256(read(ROOT/name).encode()).hexdigest();compare(actual,digest,'code:'+name)
assert not mismatches,'Code freeze mismatch; stop interpretation'
summary=js(BASE/'analysis/summary/manifest.json')
temporal=ROOT/'reports/investigacao-temporal-energy-20261110'
op=pd.read_csv(__import__('io').StringIO(read(temporal/'recuperacao_execucao.csv'))).set_index('id')
read(temporal/'relatorio.md')
methods=['zscore','cov','ewma','cusum-freeze']
parameters=[];perrun=[];covrows=[];feature_rows=[];ewrows=[];crows=[];zrows=[];cross=[];witness=[];eligibility=[];bins=[]
for family,feature in features:
    folder=BASE/'analysis'/feature;model=js(folder/'baseline/manifest.json');cal=js(folder/'calibration/manifest.json');ver=js(folder/'verification/manifest.json');par=model['parameters']
    assert par is not None
    for method in methods:
        assert cal['pair_status'][method]['eligible'] and ver['method_accepted'][method]
        parameters.append(dict(feature=feature,family=family,detector=method,mu=par['mu'],sigma=par['sigma'],n_baseline=par['n_valid'],threshold=cal['thresholds'][method],parameters=json.dumps({'lookback':6,'ddof':1} if method=='cov' else {'alpha':'0.2','initial':0} if method=='ewma' else {'k':'0.5','initial':0,'rejected_update':'preserve_previous'} if method=='cusum-freeze' else {'direction':'upper-tail','ddof':1}),cal_a_fpr=cal['pair_status'][method]['mean_fpr'],cal_b_fpr=ver['pair_status'][method]['mean_fpr']))
    for entry in entries:
        rid=entry['id'];sc=entry['scenario'];doc=js(folder/'TEST'/rid/'manifest.json');ev=js(folder/'evaluation'/rid/'manifest.json')
        assert ev['entry']==entry and doc['source']['partition']=='TEST' and doc['source']['entry_id']==rid
        for ref,key in [(doc['baseline'],None),(doc['calibration'],None),(doc['verification'],None)]:
            compare(hashlib.sha256(read(Path(ref['path'])/'manifest.json').encode()).hexdigest(),ref['manifest_sha256'],rid+':binding')
        rawrows=rows(doc['source']['observable_path']);compare(hashes[str(Path(doc['source']['observable_path']).relative_to(ROOT))],doc['source']['observable_sha256'],rid+':observable_sha')
        truthrows=rows(ev['truth']['path']);truth={'events':truthrows};event=truthrows[0] if truthrows else None
        start=num(event['actual_start_seconds']) if event else None;end=num(event['actual_end_seconds']) if event else None
        detectors={'zscore':ZScore(),'cov':CoV(),'ewma':EWMA(),'cusum-freeze':CUSUMFreeze(h=cal['thresholds']['cusum-freeze'])}
        states={'zscore':detectors['zscore'].start_run(par,zscore_spec().config),'cov':detectors['cov'].start_run(None,cov_spec(lookback=6).config),'ewma':detectors['ewma'].start_run(par,ewma_spec().config),'cusum-freeze':detectors['cusum-freeze'].start_run(par)}
        rec={m:[] for m in methods};rr=[];last_ew=D(0);last_c=D(0)
        for i,row in enumerate(rawrows):
            assert int(row['window_index'])==i and num(row['window_start_seconds'])==i and num(row['window_end_seconds'])==i+1
            obs=Observation(doc['source']['run_id'],i,D(i),D(i+1),num(row[feature]));d=dict(id=rid,scenario=sc,feature=feature,second=i,x=fl(obs.value))
            with localcontext(CONTEXT):
                z=detectors['zscore'].update(obs,states['zscore']).score
                for method in methods:
                    checks['decision_rows']+=1
                    persisted=doc['methods'][method][i]
                    if method=='cusum-freeze':
                        tr=detectors[method].step(obs,states[method]);states[method]=tr.next_state
                        score=tr.candidate;decision=tr.decision.decision;reason=tr.score.reason
                        candidate=None if z is None else max(D(0),last_c+z-D('.5'));post=D(0) if z is None else last_c if candidate>num(cal['thresholds'][method]) else candidate
                        compare(candidate,score,rid+feature+':independent_candidate:'+str(i));compare(post,tr.posterior_state,rid+feature+':independent_posterior:'+str(i));last_c=post
                        for key in ('previous_state','residual','candidate','update_accepted','posterior_state'):
                            compare(getattr(tr,key),persisted[key],rid+feature+':'+key+':'+str(i))
                        d.update(c_previous=fl(tr.previous_state),c_candidate=fl(score),c_posterior=fl(tr.posterior_state),c_accepted=tr.update_accepted)
                    else:
                        res=detectors[method].update(obs,states[method]);score=res.score;reason=res.reason;decision=None if score is None else score>num(cal['thresholds'][method])
                        if method=='ewma':
                            independent=D(0) if z is None else D('.2')*z+D('.8')*last_ew
                            compare(None if z is None else independent,score,rid+feature+':independent_ewma:'+str(i));last_ew=independent
                        if method=='cov':
                            retained=states['cov'].values
                            if len(retained)==6:
                                mu,var=sample_moments(retained);sd=standard_deviation(var);d['local_mean']=float(decimal_ratio(mu));d['local_sd']=float(sd)
                            else:d['local_mean']=np.nan;d['local_sd']=np.nan
                    compare(score,persisted['score'],rid+feature+method+':score:'+str(i));compare(decision,persisted['decision'],rid+feature+method+':decision:'+str(i));compare(reason,persisted['unavailable_reason'],rid+feature+method+':reason:'+str(i));compare(D(i+1),persisted['available_at_seconds'],rid+':availability')
                    rec[method].append(dict(window_index=i,window_start_seconds=D(i),window_end_seconds=D(i+1),score=score,decision=decision,available_at_seconds=D(i+1),unavailable_reason=reason))
                    d[method]=fl(score);d[method+'_positive']=decision
                d['z']=fl(z)
            rr.append(d)
        f=pd.DataFrame(rr);f['end']=f.second+1
        # Per-run scientific metrics are reproduced with the original pure metric function.
        for method in methods:
            metric=metrics(rec[method],truth,True,None)
            compare(json.loads(encoded(metric)),ev['results'][method],rid+feature+method+':all_metrics')
            em=ev['results'][method]
            perrun.append(dict(id=rid,scenario=sc,block=entry['block'],feature=feature,detector=method,threshold=cal['thresholds'][method],event_detected=em['event_detected'],delay_s=fl(num(em['observed_delay_seconds'])),fpr=fl(num(em['fpr'])),pre_fpr=fl(num(em['pre_fpr'])),recall=fl(num(em['recall'])),post_positive=em['post']['positive'],post_available=em['post']['available'],post_fraction=fl(num(em['post_positive_fraction'])),post_duration_s=fl(num(em['post_positive_duration_seconds'])),post_last_alarm=fl(num(em['post_last_alarm_available_seconds'])),first_alarm=fl(num(em['first_detection_available_at_seconds'])),coverage=fl(num(em['decision_coverage'])),unavailable=em['unavailable']))
        for name,a,b in [('PRE',30,150),('ACTIVE',150,270),('ACTIVE_first10',150,160),('ACTIVE_early30',150,180),('ACTIVE_last30',240,270),('POST',270,390),('POST_final30',360,390)]:
            g=f[(f.second>=a)&(f.end<=b)]
            feature_rows.append(dict(id=rid,scenario=sc,feature=feature,phase=name,n=g.x.count(),x_mean=g.x.mean(),x_sd=g.x.std(),x_median=g.x.median(),x_min=g.x.min(),x_max=g.x.max(),z_mean=g.z.mean(),zero_x=int((g.x==0).sum())))
            covrows.append(dict(id=rid,scenario=sc,feature=feature,phase=name,available=g['cov'].count(),positive=g.cov_positive.eq(True).sum(),positive_fraction=g.cov_positive.eq(True).sum()/g['cov'].count() if g['cov'].count() else np.nan,score_mean=g['cov'].mean(),score_median=g['cov'].median(),score_max=g['cov'].max(),local_mean=g.local_mean.mean(),local_sd=g.local_sd.mean(),x_mean=g.x.mean(),threshold=float(cal['thresholds']['cov'])))
            bins.append(dict(id=rid,scenario=sc,feature=feature,phase=name,**{m+'_positive':int(g[m+'_positive'].eq(True).sum()) for m in methods}))
        if sc=='L2':continue
        marker=op.loc[rid]
        markers={'last_attack_completion':270+marker.last_attack_completion_s,'first_waiting_zero':270+marker.first_waiting_zero_s,'queue_return_start':270+marker.queue_return_start_s,'queue_return_confirm':270+marker.queue_return_confirm_s,'availability_return_start':270+marker.availability_return_start_s,'availability_return_confirm':270+marker.availability_return_confirm_s,'last_failed_start':270+marker.last_failed_post_start_s,'last_failed_end':270+marker.last_failed_post_end_s}
        returned=max(markers['queue_return_confirm'],markers['availability_return_confirm'],markers['first_waiting_zero'],markers['last_attack_completion'],markers['last_failed_end'])
        for method in methods:
            post=f[(f.second>=270)&(f.second>=float(end))&(f.end<=390)]
            selections={'ACTIVE_scheduled':f[(f.second>=150)&(f.end<=270)],'POST_official':post,'POST_before_return':post[post.end<=returned],'POST_cross_return':post[(post.second<returned)&(post.end>returned)],'POST_after_return':post[post.second>=returned],'POST_final30':post[post.second>=360]}
            for key,g in selections.items():
                available=g[method].count();positive=int(g[method+'_positive'].eq(True).sum())
                cross.append(dict(id=rid,scenario=sc,feature=feature,detector=method,segment=key,marker_return=returned,windows=len(g),available=available,positive=positive,fraction=positive/available if available else np.nan,**markers))
        # EWMA observed-state decomposition at conservative operational return.
        m=min(math.ceil(returned),390);previous=float(f.loc[f.second==m-1,'ewma'].iloc[0]) if m else 0.;memory=previous;new=0.;positive_after=0;carry_required=0;input_upper=0;reset_count=0
        for row in f[(f.second>=m)&(f.end<=390)].itertuples():
            if not np.isfinite(row.z):memory=0.;new=0.;reset_count+=1;continue
            memory*=.8;new=.2*row.z+.8*new
            assert abs(memory+new-row.ewma)<1e-9
            if row.ewma_positive:
                positive_after+=1;carry_required+=int(new<=float(cal['thresholds']['ewma']));input_upper+=int(row.z>float(cal['thresholds']['zscore']))
        active=f[(f.second>=150)&(f.end<=270)];post=f[(f.second>=270)&(f.end<=390)];late=post[post.second>=m]
        positive=post[post.ewma_positive.eq(True)]
        ewrows.append(dict(id=rid,scenario=sc,feature=feature,h=float(cal['thresholds']['ewma']),active_positive=int(active.ewma_positive.eq(True).sum()),post_scheduled_positive=len(positive),post_first_negative=float(post.loc[post.ewma_positive.eq(False),'end'].min()),post_last_positive=float(positive.end.max()),return_marker=returned,state_at_return=previous,positive_after_return=positive_after,carry_required_after_return=carry_required,positive_with_large_instant_z=input_upper,reset_after_return=reset_count,ewma_at_active_end=float(f.loc[f.second==269,'ewma'].iloc[0])))
        # Freeze is a per-step rejected update; quantify resumption rather than assume a latch.
        pos=active[active['cusum-freeze_positive'].eq(True)];first=float(pos.second.min()) if len(pos) else np.nan
        after=f[(f.second>first)&(f.end<=390)] if len(pos) else f.iloc[0:0]
        neg=after[after['cusum-freeze_positive'].eq(False)]
        crows.append(dict(id=rid,scenario=sc,feature=feature,h=float(cal['thresholds']['cusum-freeze']),first_active_positive=first+1 if len(pos) else np.nan,previous_at_first=float(pos.c_previous.iloc[0]) if len(pos) else np.nan,candidate_at_first=float(pos.c_candidate.iloc[0]) if len(pos) else np.nan,posterior_at_first=float(pos.c_posterior.iloc[0]) if len(pos) else np.nan,active_rejected=int(active.c_accepted.eq(False).sum()),active_accepted=int(active.c_accepted.eq(True).sum()),first_negative_after_crossing=float(neg.end.min()),accepted_after_crossing=int(after.c_accepted.eq(True).sum()),max_stored=float(f.c_posterior.max()),max_candidate=float(f.c_candidate.max()),post_positive=int(post['cusum-freeze_positive'].eq(True).sum()),post_late_positive=int(late['cusum-freeze_positive'].eq(True).sum()),post_final_state=float(f.loc[f.second==389,'c_posterior'].iloc[0])))
        zrows.append(dict(id=rid,scenario=sc,feature=feature,h=float(cal['thresholds']['zscore']),x_threshold=float(num(par['mu'])+num(par['sigma'])*num(cal['thresholds']['zscore'])),active_positive=int(active.zscore_positive.eq(True).sum()),active_negative_z=int((active.z<0).sum()),z_active_mean=active.z.mean(),z_active_min=active.z.min(),z_active_max=active.z.max(),post_positive=int(post.zscore_positive.eq(True).sum()),post_late_positive=int(late.zscore_positive.eq(True).sum())))
        # Compact transition witnesses fixed by a distribution-neutral rule: first crossing,
        # first resumed negative, and final POST. No convenient run is selected here.
        selected_indices=set([150,269,270,389,m])
        for method in methods:
            idx=active.loc[active[method+'_positive'].eq(True),'second'].min()
            if pd.notna(idx):selected_indices.update(range(max(0,int(idx)-1),min(int(idx)+2,len(f))))
        if len(neg):selected_indices.add(int(neg.second.iloc[0]))
        for i in sorted(selected_indices):
            if i<len(f):witness.append(f.loc[f.second==i].iloc[0].to_dict())
        print(feature,rid,'OK',flush=True)

frames={'parametros_congelados.csv':parameters,'alarmes_por_execucao.csv':perrun,'analise_cov.csv':covrows,'features_por_periodo.csv':feature_rows,'analise_ewma.csv':ewrows,'analise_cusum_freeze.csv':crows,'analise_zscore.csv':zrows,'alarmes_post_recuperacao.csv':cross,'testemunhos_transicoes.csv':witness,'positivas_periodos.csv':bins}
for name,data in frames.items():pd.DataFrame(data).to_csv(P/name,index=False)
run=pd.DataFrame(perrun);combo=[]
for par in parameters:
    feature,method=par['feature'],par['detector'];g=run[(run.feature==feature)&(run.detector==method)];d=dict(par)
    for sc in ('A3','F96','L2'):
        own=g[g.scenario==sc];key=f'{feature}/{sc}/{method}';persisted=summary['results'][key]
        compare(len(own),persisted['n_scientifically_evaluated'],key+':n')
        if sc!='L2':
            detected=int(own.event_detected.eq(True).sum());d[sc+'_detected']=detected;d[sc+'_events']=len(own);d[sc+'_delay_n']=int(own.delay_s.notna().sum());d[sc+'_delay_mean_s']=own.delay_s.mean();d[sc+'_delay_median_s']=own.delay_s.median();d[sc+'_post_positive_mean']=own.post_positive.mean();d[sc+'_post_fraction_mean']=own.post_fraction.mean();d[sc+'_recall_mean']=own.recall.mean()
            # summary detection schema is verified below from per-run metrics as well.
        else:d['L2_fpr_mean']=own.fpr.mean();d['L2_false_positive_windows']=int(round((own.fpr*360).sum()));d['L2_available_windows']=7200
        for metric,col in [('fpr','fpr'),('pre_fpr','pre_fpr'),('recall','recall'),('post_positive_fraction','post_fraction')]:
            value=own[col].mean();stored=persisted['means'][metric]
            if pd.notna(value):
                est=stored.get('estimate',stored.get('mean'))
                if est is not None:compare(abs(value-float(est))<1e-12,True,key+':aggregate_'+metric)
        # Every per-run metric in the summary must be identical to its evaluation.
        for row in persisted['per_run']:
            ownrow=next(x for x in perrun if x['id']==row['entry'] and x['feature']==feature and x['detector']==method)
            compare(ownrow['event_detected'],row['metrics']['event_detected'],key+row['entry']+':event')
            compare(ownrow['post_positive'],row['metrics']['post']['positive'],key+row['entry']+':post')
    combo.append(d)
pd.DataFrame(combo).to_csv(P/'tabela_combinacoes.csv',index=False)
# Variability across executions, never treating windows as replicates.
for name,df,groups in [('variabilidade_detectores.csv',run,['feature','detector','scenario']),('variabilidade_cov.csv',pd.DataFrame(covrows),['feature','scenario','phase']),('variabilidade_post.csv',pd.DataFrame(cross),['feature','detector','scenario','segment'])]:
    numeric=[c for c in df.select_dtypes(include='number').columns if c not in ['block']]
    df.groupby(groups)[numeric].agg(['count','mean','median','std',lambda x:x.quantile(.25),lambda x:x.quantile(.75),'min','max']).rename(columns={'<lambda_0>':'q25','<lambda_1>':'q75'}).to_csv(P/name)
changed=[name for name,h in hashes.items() if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=h]
verification=dict(derived_analysis=True,test_runs=60,features_in_scientific_matrix=features,eligible_pairs=16,total_comparisons=checks['comparisons'],decision_rows_compared=checks['decision_rows'],mismatches=mismatches,input_files=len(hashes),changed_inputs=changed,no_recalibration=True,code_matches_frozen_plan=True,ground_truth_unchanged=True)
(P/'verificacao.json').write_text(json.dumps(verification,indent=2));(P/'manifesto_entradas.json').write_text(json.dumps(hashes,indent=2))
assert not mismatches and not changed,verification
print('PASS',verification,flush=True)
