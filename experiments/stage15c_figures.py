"""Deterministic publication artifacts: descriptive points, no inference/error CI."""
import io
import math
import os
from collections import defaultdict
from experiments.stage15c_analysis import METHODS,FEATURES,number

LABELS={'zscore':'Z','cov':'CV6','ewma':'E','cusum':'Cu'}
SHORT=dict(zip(FEATURES,('pkt','bytes','req','dur','cpu')))
NAMES=dict(zip(FEATURES,('ingress_packet_count','ingress_tcp_payload_length_sum_bytes','request_starts','mean_duration_ms','mean_cpu_percent')))
CONFIGS=[(m,f) for m in METHODS for f in FEATURES]


def render(tables,meta):
    os.environ['MPLCONFIGDIR']='/tmp/stage15c-matplotlib-config'
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    matplotlib.rcParams.update({'axes.titlepad':24,'font.family':'DejaVu Sans','font.size':9,'axes.titlesize':10,
        'svg.hashsalt':'stage15c-descriptive','axes.grid':True,'grid.alpha':.22,'savefig.facecolor':'white'})
    seeds=sorted({r['seed'] for r in tables['primary_per_run']});colors=plt.get_cmap('tab20')
    seed_color={seed:colors(i) for i,seed in enumerate(seeds)}
    seed_jitter={seed:(i-(len(seeds)-1)/2)*.019 for i,seed in enumerate(seeds)}
    payloads={}
    def finish(fig,name):
        if not name.startswith('temporal_'):
            fig.text(.99,.01,'Z=Z-score; CV6=CoV L6; E=EWMA .2; Cu=CUSUM .5; pkt/bytes/req/dur/cpu: ver relatório',ha='right',fontsize=7)
        for suffix in ('png','pdf'):
            stream=io.BytesIO()
            metadata={'Software':'Stage15C descriptive analysis'} if suffix=='png' else {'Creator':'Stage15C descriptive analysis','CreationDate':None,'ModDate':None}
            fig.savefig(stream,format=suffix,dpi=160,bbox_inches='tight',metadata=metadata)
            payloads['figures/'+name+'.'+suffix]=stream.getvalue()
        plt.close(fig)
    def layout(ax,unit='[0,1]',labels=True):
        if labels:
            ax.set_xticks(range(20),[LABELS[m]+'\n'+SHORT[f] for m,f in CONFIGS],fontsize=7)
        for pos in (4.5,9.5,14.5):ax.axvline(pos,color='.75',lw=.7)
        ax.set_ylabel(unit)
    def points(ax,rows,value,configs=CONFIGS,limits=(0,1),support=True):
        for i,(method,feature) in enumerate(configs):
            selected=[r for r in rows if r['method']==method and r['feature']==feature]
            valid=[];missing=[]
            for r in selected:
                v=r[value];seed=r['seed'];x=i+seed_jitter[seed]
                if v is None:
                    missing.append(seed)
                    ax.plot(x,-.22,marker='x',color=seed_color[seed],ms=4,transform=ax.get_xaxis_transform(),clip_on=False)
                else:
                    valid.append(float(v));ax.scatter(x,float(v),s=17,color=seed_color[seed],alpha=.85,zorder=3)
            if valid:ax.plot([i-.22,i+.22],[float(np.median(valid))]*2,color='black',lw=1.8,zorder=5)
            if support:ax.text(i,1.015,str(len(valid))+'/16',ha='center',fontsize=6,transform=ax.get_xaxis_transform())
        ax.set_ylim(*limits)
        ax.set_xlim(-.6,len(configs)-.4)
    legend=[plt.Line2D([],[],marker='o',linestyle='',color=seed_color[s],label=str(s),markersize=4) for s in seeds]
    # Core 1: identical FPR scale across methods, all B seeds.
    b=[r for r in tables['primary_per_run'] if r['scenario']=='B'];maximum=max(float(number(r['fpr'])) for r in b if r['fpr'] is not None)
    fig,axes=plt.subplots(2,2,figsize=(12,7),sharey=True)
    for ax,method in zip(axes.flat,METHODS):
        cfg=[(method,f) for f in FEATURES]
        rows=[dict(r,fpr=number(r['fpr'])) for r in b if r['method']==method]
        points(ax,rows,'fpr',cfg,limits=(0,max(.03,maximum*1.12)))
        ax.set_xticks(range(5),[SHORT[f] for f in FEATURES]);ax.set_title(method,pad=20);ax.set_ylabel('FPR B por run')
        ax.axhline(.01,ls='--',lw=.8,color='gray',label='alpha nominal .01')
    fig.suptitle('PRIMARY [48,144): FPR benign-only; barras pretas = medianas; n/16 definidos')
    fig.subplots_adjust(bottom=.20,hspace=.55,top=.83);fig.legend(handles=legend,loc='lower center',ncol=8,fontsize=7,title='Seed (cores fixas em todas as figuras)')
    finish(fig,'01_fpr_B')
    # Core 2: common [0,1] scales, conditional defined means never substitute null.
    fig,axes=plt.subplots(2,2,figsize=(18,9))
    for col,scenario in enumerate('CP'):
        for row,metric in enumerate(('recall','f1')):
            ax=axes[row,col];values=[dict(r,**{metric:number(r[metric])}) for r in tables['primary_per_run'] if r['scenario']==scenario]
            points(ax,values,metric);layout(ax,metric);ax.set_title(scenario+' — '+metric+'; n/16 definidos')
    fig.suptitle('PRIMARY: dispersão por run/seed; × abaixo do eixo = null, não zero')
    fig.subplots_adjust(hspace=.72,wspace=.15,bottom=.14,top=.86);finish(fig,'02_recall_f1_CP')
    # Core 3: event proportion with explicit counts; no B event.
    fig,axes=plt.subplots(2,1,figsize=(16,7),sharey=True)
    for ax,scenario in zip(axes,'CP'):
        rows=[r for r in tables['event_descriptive'] if r['scenario']==scenario]
        lookup={(r['method'],r['feature']):r for r in rows}
        values=[float(lookup[c]['event_detection_rate']) for c in CONFIGS]
        ax.bar(range(20),values,color=[plt.get_cmap('Set2')(METHODS.index(m)) for m,f in CONFIGS],width=.65)
        for i,c in enumerate(CONFIGS):ax.text(i,min(values[i]+.035,1.035),str(lookup[c]['events_detected'])+'/16',ha='center',fontsize=7)
        ax.set_ylim(0,1.12);layout(ax,'eventos detectados / 16');ax.set_title(scenario+'; um evento global por run')
    fig.suptitle('Event-level PRIMARY: overlap observacional, sem prazo available_at <= actual_end')
    fig.subplots_adjust(hspace=.45);finish(fig,'03_event_detection')
    # Core 4: delay distributions conditional on detection, counts/misses explicit.
    delays=[float(number(r['detection_delay_seconds'])) for r in tables['event_per_run'] if r['detection_delay_seconds'] is not None]
    fig,axes=plt.subplots(2,1,figsize=(16,8),sharey=True)
    for ax,scenario in zip(axes,'CP'):
        rows=[dict(r,detection_delay_seconds=number(r['detection_delay_seconds'])) for r in tables['event_per_run'] if r['scenario']==scenario]
        points(ax,rows,'detection_delay_seconds',limits=(0,max(delays)*1.12));layout(ax,'delay (s), somente detectados')
        ax.set_title(scenario+'; n/16 detectados, 16−n misses; × fora do eixo = evento não detectado')
    fig.suptitle('Detection delay condicionado à detecção; ler junto com a figura 03')
    fig.subplots_adjust(hspace=.72,bottom=.14,top=.86);finish(fig,'04_detection_delays')
    # Core 5: post-event separate from primary FPR.
    fig,axes=plt.subplots(2,1,figsize=(16,7),sharey=True)
    for ax,scenario in zip(axes,'CP'):
        rows=[dict(r,post_event_alarm_rate=number(r['post_event_alarm_rate'])) for r in tables['post_event_per_run'] if r['scenario']==scenario]
        points(ax,rows,'post_event_alarm_rate');layout(ax,'positivos / disponíveis');ax.set_title(scenario+'; n/16 taxas definidas')
    fig.suptitle('POST_EVENT_DIAGNOSTIC: janelas inteiras em [max(actual_end,48),144); × = null')
    fig.subplots_adjust(hspace=.72,bottom=.14,top=.86);finish(fig,'05_post_event_alarm_rate')
    # Core 6: complete matched seed differences, delay selection made explicit.
    fig,axes=plt.subplots(3,2,figsize=(18,12));metrics=('recall','f1','fpr','post_event_alarm_rate','detection_delay_seconds')
    for ax,metric in zip(axes.flat,metrics):
        rows=[r for r in tables['paired_p_minus_c']+tables['paired_delay_detected_both'] if r['metric']==metric]
        limits=(-1,1)
        if metric=='detection_delay_seconds':
            valid=[abs(float(r['p_minus_c'])) for r in rows if r['p_minus_c'] is not None];limit=max(valid,default=1)*1.12;limits=(-limit,limit)
        points(ax,rows,'p_minus_c',limits=limits);layout(ax,'P−C (s)' if metric=='detection_delay_seconds' else 'P−C')
        ax.axhline(0,color='gray',lw=.8);ax.set_title(metric+'; n/16 pares completos'+(' e detectados em ambos' if metric=='detection_delay_seconds' else ''))
    axes.flat[-1].axis('off');axes.flat[-1].legend(handles=legend,ncol=2,loc='center',fontsize=8,title='Seed; × fora do eixo = par não disponível')
    fig.suptitle('Diferenças pareadas descritivas; sem inferência; P também tem menor volume médio')
    fig.subplots_adjust(hspace=.85,wspace=.2,bottom=.10,top=.87);finish(fig,'06_paired_P_minus_C')
    # Appendix: deterministic minimum eligible seed; observations and existing scores.
    temporal=tables['temporal_example'];seed=meta['example_seed']
    for feature in FEATURES:
        fig,axes=plt.subplots(5,3,figsize=(14,12),sharex=True,sharey='row')
        for col,scenario in enumerate('BCP'):
            raw=[r for r in temporal if r['scenario']==scenario and r['feature']==feature and r['method']=='zscore']
            raw=sorted(raw,key=lambda r:r['window_index']);t=[r['window_index']+.5 for r in raw]
            values=[float(number(r['observation_value'])) if r['observation_value'] is not None else math.nan for r in raw]
            axes[0,col].plot(t,values,lw=.8,color='#2166ac');axes[0,col].set_title(scenario+' — seed '+str(seed))
            for row,method in enumerate(METHODS,1):
                records=sorted([r for r in temporal if r['scenario']==scenario and r['feature']==feature and r['method']==method],key=lambda r:r['window_index'])
                score=[math.nan if r['score'] is None else float(number(r['score'])) for r in records]
                ax=axes[row,col];ax.plot(t,score,lw=.8,color='#2166ac')
                ax.axhline(float(number(records[0]['threshold'])),color='black',ls='--',lw=.8)
                positive=[(tx,y) for tx,y,r in zip(t,score,records) if r['decision'] is True]
                if positive:ax.scatter(*zip(*positive),s=6,color='#b2182b',zorder=3)
                for tx,r in zip(t,records):
                    if r['score'] is None:ax.plot(tx,-.06,'x',ms=3,color='gray',transform=ax.get_xaxis_transform(),clip_on=False)
            for ax in axes[:,col]:
                ax.axvspan(0,48,color='gray',alpha=.10);ax.axvline(48,color='gray',lw=.7);ax.set_xlim(0,144)
                if raw[0]['actual_start'] is not None:ax.axvspan(float(number(raw[0]['actual_start'])),float(number(raw[0]['actual_end'])),color='#e69f00',alpha=.14)
            axes[-1,col].set_xlabel('tempo desde início (s)')
        axes[0,0].set_ylabel('observação\n'+SHORT[feature])
        for row,method in enumerate(METHODS,1):axes[row,0].set_ylabel(method+'\nscore congelado')
        fig.suptitle(feature+' — seed mínima pareada; mesmas escalas B/C/P por linha\nvermelho: decisão positiva; tracejado: threshold; × fora do eixo: unavailable; sombra laranja: evento global')
        fig.subplots_adjust(hspace=.30,wspace=.12,top=.91,bottom=.07)
        finish(fig,'temporal_'+SHORT[feature])
    return payloads
