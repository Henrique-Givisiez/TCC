"""Offline only. Run from repository root with PYTHONPATH=. .venv/bin/python -B <this file>."""
import csv
import hashlib
import json
import math
import statistics as st
from collections import defaultdict
from pathlib import Path
import subprocess

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from experiments.capacity_analysis import interval_sweep

OUT = Path(__file__).resolve().parent
BASE = Path('experiment_results/capacity-exploration-20261104')
hashes = {}
def data(path, kind='json'):
    path = Path(path)
    content = path.read_bytes()
    hashes[str(path)] = hashlib.sha256(content).hexdigest()
    if kind == 'csv':
        return list(csv.DictReader(content.decode().splitlines()))
    if kind == 'jsonl':
        return [json.loads(x) for x in content.splitlines() if x.strip()]
    return json.loads(content)

def write(name, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with (OUT/name).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader(); w.writerows(rows)

def stats(vals):
    v = sorted(float(x) for x in vals if x is not None)
    return dict(n=len(v), mean=st.mean(v) if v else None,
        sample_sd=st.stdev(v) if len(v)>1 else None,
        median=st.median(v) if v else None,
        p95=v[max(0, math.ceil(.95*len(v))-1)] if v else None,
        minimum=min(v) if v else None, maximum=max(v) if v else None)

inventory=[]; per=[]; timelines=[]; sources=[]; facts={}
for folder in sorted(BASE.iterdir()):
    if not (folder/'capacity_summary.json').exists(): continue
    raw=folder/'raw'; name=folder.name
    cfg=data(raw/'effective_config.json'); status=data(raw/'run_status.json')
    summary=data(folder/'capacity_summary.json'); verification=data(folder/'verification/verification.json')
    cleanup=data(folder/'cleanup.json'); audits=data(folder/'container_audits.json')
    requests=data(raw/'request_log.csv','csv'); metrics=data(raw/'simulation_metrics.csv','csv')
    duration=cfg['duration_seconds']; origin=status['experiment_start_monotonic']
    assert not cfg['attack']['enabled'] and cfg['topology']['mode']=='direct'
    assert cfg['normal_traffic']['endpoint']=='/medium' and cfg['server']['process_pool_workers']==2
    assert cfg['infrastructure']['initial_instances']==cfg['infrastructure']['max_instances']==1
    assert not cfg['autoscaler']['enabled'] and not cfg['load_balancer']['enabled']
    assert verification['accepted'] and not summary['reliability_errors']
    inv=data(raw/'source_inventory.json')
    closures=[]
    for source in inv:
        journal=data(raw/'source_artifacts'/source['source_id']/'output/journal.jsonl','jsonl')
        closures.extend(e['payload']['elapsed_seconds'] for e in journal if e['kind']=='source_closed')
    n=cfg['normal_traffic']['clients']; rate=cfg['normal_traffic']['rate']; nominal=n*rate
    mode='ON' if summary['diagnostics_enabled'] else 'OFF'
    group=f'N{n}_rate{rate:g}_T{duration}_{mode}'
    vals={}; intervals={}; delay_bins=defaultdict(list)
    def add(metric, samples, unit, missing=0, basis='observations'):
        vals[metric]=stats(samples)
        per.append(dict(name=name,configuration=group,metric=metric,unit=unit,basis=basis,
                        missing=missing,**vals[metric]))
    starts=[float(r['elapsed_seconds']) for r in requests]
    ends=[float(r['end_elapsed_seconds']) for r in requests if r['end_elapsed_seconds']]
    add('http_duration', [float(r['duration_ms']) for r in requests if r['duration_ms']], 'ms',sum(not r['duration_ms'] for r in requests))
    supported=[r for r in metrics if r['active_containers_names']]
    add('cpu_docker',[float(r['average_cpu_percent']) for r in supported],'% Docker',len(metrics)-len(supported))
    add('starts_1s',[sum(i<=x<i+1 for x in starts) for i in range(duration)],'req/s',basis='1s generation windows')
    if mode=='ON':
        assert data(raw/'source_artifacts/clock_validation.json')['comparable']
        assert data(raw/'diagnostics/victim_clock_validation.json')['comparable']
        ids={r['request_id'] for r in requests}
        events=[e for e in data(raw/'diagnostics/victim/events.jsonl','jsonl') if e['kind']=='handler_finished' and e.get('request_id') in ids]
        assert len(events)==len(requests)
        for label,a,b in [('worker_wait','work_submitted_at','work_started_at'),('work_wall','work_started_at','work_finished_at')]:
            add(label,[(e[b]-e[a])*1000 for e in events],'ms')
        add('work_cpu',[e['work_cpu_seconds']*1000 for e in events],'ms')
        intervals['workers']=[(e['work_started_at']-origin,e['work_finished_at']-origin) for e in events]
        intervals['victim_pending']=[(e['work_submitted_at']-origin,e['work_started_at']-origin) for e in events]
        intervals['handlers']=[(e['handler_started_at']-origin,e['handler_finished_at']-origin) for e in events]
        source_pending=[]; delays=defaultdict(list)
        for source in inv:
            sid=source['source_id']; ev=data(raw/'source_artifacts'/sid/'output/diagnostics/events.jsonl','jsonl')
            grouped=defaultdict(dict)
            for e in ev:
                if e.get('attempt_id'): grouped[e['attempt_id']][e['kind']]=e
            own_delays=[]; pending=[]
            for own in grouped.values():
                if 'submitted' in own and 'task_started' in own:
                    pending.append((own['submitted']['at']-origin,own['task_started']['at']-origin))
                for label,a,b in [('plan_submit','planned','submitted'),('submit_task','submitted','task_started'),('task_http','task_started','http_started'),('submit_http','submitted','http_started')]:
                    if a not in own or b not in own: continue
                    at=own[a]['planned_at'] if a=='planned' else own[a]['at']
                    delta=(own[b]['at']-at)*1000
                    assert delta>=0
                    delays[label].append(delta)
                    sec=math.floor(own[b]['at']-origin)
                    delay_bins[(label,sec)].append(delta)
                    if label=='submit_task':own_delays.append(delta)
            source_pending.extend(pending)
            sources.append(dict(name=name,source_id=sid,threads=source['send_workers'],
                pending_peak=interval_sweep(pending,0,duration)['peak'],**stats(own_delays)))
        intervals['source_pending']=source_pending
        for label,v in delays.items(): add(label,v,'ms')
        for label,ints in intervals.items():
            v=interval_sweep(ints,0,duration)
            per.append(dict(name=name,configuration=group,metric=label,unit='operations',basis='time-weighted generation overlap',missing=0,n=len(ints),mean=v['mean_occupancy'],maximum=v['peak']))
            vals[label]=dict(mean=v['mean_occupancy'],maximum=v['peak'])
    for i in range(duration):
        b=dict(name=name,configuration=group,second=i,starts=sum(i<=x<i+1 for x in starts),completions=sum(i<=x<i+1 for x in ends))
        for label,samples in [('http_ms',[float(r['duration_ms']) for r in requests if r['end_elapsed_seconds'] and i<=float(r['end_elapsed_seconds'])<i+1 and r['duration_ms']]),('cpu_docker',[float(r['average_cpu_percent']) for r in supported if i<=float(r['elapsed_seconds'])<i+1])]:
            b.update({label+'_'+k:v for k,v in stats(samples).items() if k in ('n','mean','p95')})
        if mode=='ON':
            for label,ints in intervals.items():
                v=interval_sweep(ints,i,i+1);b[label+'_mean']=v['mean_occupancy'];b[label+'_peak']=v['peak']
            # Wait assigned at submission, CPU/wall at computation start.
            for label,samples in [('wait_ms',[(e['work_started_at']-e['work_submitted_at'])*1000 for e in events if i<=e['work_submitted_at']-origin<i+1]),('cpu_operation_ms',[e['work_cpu_seconds']*1000 for e in events if i<=e['work_started_at']-origin<i+1]),('source_wait_ms',delay_bins[('submit_task',i)])]:
                b.update({label+'_'+k:v for k,v in stats(samples).items() if k in ('n','mean','p95')})
        timelines.append(b)
    victim=next(v for v in audits.values() if v['role']=='victim')
    captures=[data(raw/'traffic_capture.csv.capture.json'),data(raw/'source_artifacts/traffic_capture.pcap.capture.json')]
    f=dict(name=name,configuration=group,run_id=status['run_id'],path=str(folder),campaign='2026-11-04',
        execution_commit='not recorded in inspected run metadata; see campaign_report.md for documentary reference',
        topology=cfg['topology']['mode'],endpoint=cfg['normal_traffic']['endpoint'],workers=2,sources=n,rps_per_source=rate,nominal_rps=nominal,
        thread_budget=cfg['normal_traffic']['max_concurrent_sends'],threads_per_source=';'.join(str(s['send_workers']) for s in inv),mode=mode,
        planned_seconds=duration,first_start_seconds=min(starts),last_completion_seconds=max(ends),
        last_source_closed_seconds=max(closures) if closures else None,last_metric_seconds=max(float(r['elapsed_seconds']) for r in metrics),
        seed=cfg['seed'],status=data(folder/'execution_result.json')['status'],
        feature_validation=verification['accepted'],capture_kernel_drops=sum(c['capture_counters']['packets_dropped_by_kernel'] for c in captures),
        reliability_errors=len(summary['reliability_errors']),victim_image=victim['image_id'],victim_limits=json.dumps(victim['limits'],sort_keys=True),
        starts_total=len(requests),starts_generation=sum(0<=x<duration for x in starts),completions_generation=sum(0<=x<duration for x in ends),
        unfinished=len(requests)-len(ends),failures=sum(r['outcome'] in ('transport_error','client_error','http_error') for r in requests),
        cancelled=summary['generators']['cancelled'] if summary['generators'] else None,rejected=summary['generators']['rejected'] if summary['generators'] else None,
        unresolved=summary['generators']['unresolved'] if summary['generators'] else None,
        diagnostic_metrics='present' if mode=='ON' else 'unavailable',cleanup_record=str(folder/'cleanup.json'))
    f['effective_rps']=f['starts_generation']/duration;f['rps_relative_error_pct']=100*(f['effective_rps']/nominal-1)
    f['completion_rps_generation']=f['completions_generation']/duration
    facts[name]=dict(inventory=f,stats=vals)
    inventory.append(f)

counts=defaultdict(int)
for r in inventory:counts[r['configuration']]+=1
for r in inventory:r['comparison_group']='A' if counts[r['configuration']]>1 else 'B';r['comparison_note']='equivalent repetitions within configuration; other configurations contrast only'
config=[]
groups=defaultdict(list)
for r in per:groups[(r['configuration'],r['metric'])].append(r)
for (cfg,metric),rr in groups.items():
    for key in ('mean','sample_sd','median','p95','maximum'):
        values=[r[key] for r in rr if r.get(key) is not None]
        if values:config.append(dict(configuration=cfg,metric=metric,statistic=key,runs=len(rr),valid_runs=len(values),mean_across_runs=st.mean(values),sd_between_runs=st.stdev(values) if len(values)>1 else None,minimum_run=min(values),maximum_run=max(values)))
write('runs_inventory.csv',inventory);write('per_run_statistics.csv',per);write('configuration_summary.csv',config);write('timeline_1s.csv',timelines);write('source_statistics.csv',sources)
(OUT/'figures').mkdir(exist_ok=True)
panels=[('starts','Inícios HTTP (req/s)'),('cpu_docker_mean','CPU vítima (% Docker)'),('http_ms_mean','Duração HTTP média (ms)'),('wait_ms_mean','Espera worker média (ms)'),('victim_pending_mean','Pendentes vítima (média temporal)'),('source_wait_ms_mean','Espera executor fonte (ms)')]
for filename,names,title in [('rate_progression',['P1_8rps','P2_32rps','P3_64rps','P4_96rps','P5_128rps'],'Pilotos ON: 2 fontes, 32 threads/fonte, 12 s'),('sources',['C2_ON_r1','C4_ON_r1','C3_ON_r1','C5_ON_r1'],'Contrastes ON: 2/4 fontes, 32/16 threads/fonte, 20 s')]:
    fig,axes=plt.subplots(3,2,figsize=(13,10),constrained_layout=True)
    for name in names:
        rr=[r for r in timelines if r['name']==name];info=facts[name]['inventory']
        label=f'{name}: N={info["sources"]}, {info["nominal_rps"]:g} RPS'
        for ax,(key,ylabel) in zip(axes.flat,panels):
            ax.plot([r['second']+.5 for r in rr],[r.get(key) if r.get(key) is not None else float('nan') for r in rr],label=label,lw=1.2)
            ax.set(xlabel='Tempo desde origem (s)',ylabel=ylabel);ax.grid(alpha=.25)
    axes[0,0].legend(fontsize=7);fig.suptitle(title+'; bins de 1 s')
    fig.savefig(OUT/'figures'/f'{filename}.png',dpi=160);plt.close(fig)
fig,axes=plt.subplots(1,3,figsize=(12,4),constrained_layout=True)
for ax,key,label in zip(axes,['effective_rps','http_duration','cpu_docker'],['Δ RPS ON−OFF','Δ HTTP médio (ms)','Δ CPU Docker (pp)']):
    for x,(a,b) in enumerate([('C2_ON_r1','C2_OFF_r1'),('C2_ON_r2','C2_OFF_r2'),('C3_ON_r1','C3_OFF_r1')]):
        value=lambda name:facts[name]['inventory']['effective_rps'] if key=='effective_rps' else facts[name]['stats'][key]['mean']
        ax.scatter(x,value(a)-value(b));ax.set_xticks([0,1,2],['64 r1','64 r2','128 r1']);ax.axhline(0,color='grey',lw=.8);ax.set_ylabel(label)
fig.suptitle('Contrastes pareados de instrumentação; 2 fontes, 20 s')
fig.savefig(OUT/'figures/instrumentation.png',dpi=160);plt.close(fig)
(OUT/'analysis_manifest.json').write_text(json.dumps(dict(head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),inputs_sha256=hashes,percentile='nearest rank ceil(.95*n)',intervals='half-open; means time weighted; generation only',no_confidence_intervals=True),indent=2)+'\n')
for r in inventory:
    v=facts[r['name']]['stats']
    print(r['name'], 'rps',round(r['effective_rps'],2), 'HTTP',round(v['http_duration']['mean'],2),
          'wait',v.get('worker_wait',{}).get('mean'), 'pending',v.get('victim_pending'),
          'source wait',v.get('submit_task',{}).get('p95'))

def fmt(v):
    return '—' if v is None else f'{v:.2f}' if isinstance(v,(float,int)) else str(v)
def table(headers, rows):
    return '| '+' | '.join(headers)+' |\n|'+'|'.join('---' for _ in headers)+'|\n'+'\n'.join('| '+' | '.join(fmt(v) for v in row)+' |' for row in rows)+'\n'
invtable=table(['Execução','N × RPS/fonte','s','Seed','Grupo','Última conclusão (s)'],[
    [r['name'],f"{r['sources']} × {r['rps_per_source']:g}",r['planned_seconds'],str(r['seed']),r['comparison_group'],r['last_completion_seconds']] for r in inventory])
stattable=table(['Execução','RPS efetivo','n HTTP','HTTP média ± DP (ms)','Mediana/p95 (ms)','CPU Docker %','Espera média/p95 (ms)'],[
    [r['name'],r['effective_rps'],str(facts[r['name']]['stats']['http_duration']['n']),
     fmt(facts[r['name']]['stats']['http_duration']['mean'])+' ± '+fmt(facts[r['name']]['stats']['http_duration']['sample_sd']),
     fmt(facts[r['name']]['stats']['http_duration']['median'])+' / '+fmt(facts[r['name']]['stats']['http_duration']['p95']),
     facts[r['name']]['stats']['cpu_docker']['mean'],
     fmt(facts[r['name']]['stats'].get('worker_wait',{}).get('mean'))+' / '+fmt(facts[r['name']]['stats'].get('worker_wait',{}).get('p95'))] for r in inventory])
reptable=table(['Configuração (N, taxa/fonte, duração, modo)','n','Indicador','Média entre runs','DP entre runs'],[
    [r['configuration'],r['valid_runs'],r['metric']+'/'+r['statistic'],r['mean_across_runs'],r['sd_between_runs']] for r in config
    if r['valid_runs']>1 and r['metric'] in ('http_duration','worker_wait','cpu_docker','starts_1s') and r['statistic']=='mean'])
(OUT/'report.md').write_text('''# Caracterização operacional offline do tráfego legítimo

## A. Resumo executivo

Foram reanalisadas 16 execuções recentes da campanha de 04/11/2026: cinco pilotos de 12 s e onze execuções principais de 20 s. Configurações efetivas, IDs, inventários de fontes, imagem/limites da vítima, requisições, métricas e eventos foram lidos diretamente. Todas utilizam direct, uma vítima, `/medium`, dois workers, capacidade fixa, sem autoscaling/balanceamento e orçamento agregado de 64 threads. Nenhuma carga definitiva é selecionada.

Até 64 RPS há evidência favorável de operação regular no intervalo observado. O piloto de 96 RPS também não apresentou degradação importante, mas não tem repetição. A condição de 128 RPS com duas fontes teve maior espera, ainda sem falhas; com quatro fontes houve acúmulo prolongado de trabalho, alta duração HTTP e atraso secundário nos geradores. Isso não mede capacidade máxima nem demonstra saturação permanente.

Todos os logs de requisições das 16 execuções terminaram sem falhas e sem tentativas abertas. Os relatórios de captura registram zero perdas de kernel e as verificações preservadas aceitam as cinco features. Essas verificações foram inspecionadas, não reexecutadas. Diagnóstico OFF não é preenchido com zero.

## B. Inventário das execuções

'''+invtable+'''
O inventário completo está em [runs_inventory.csv](runs_inventory.csv), incluindo run_id, caminho original, configuração, threads, seed, encerramento, perdas de captura, imagem e limites. Todos os caminhos referem-se a `experiment_results/capacity-exploration-20261104/<execução>/`.

Grupo A: repetições equivalentes dentro da mesma chave de configuração: C1 ON, C2 ON, C2 OFF e C4 ON, duas cada. Grupo B: pilotos e condições de uma única repetição; permitem contrastes descritivos, sem DP entre repetições. Mesmo nos grupos A, contrastar fontes, duração ou modo exige ressalvas. Grupo C: campanhas históricas com proxy e outras cargas, como scientific-reduced-clock-r2, permanecem apenas contexto e não foram reunidas aos dados recentes. O inventário não pretende catalogar toda execução legítima de arquiteturas antigas.

Os cinco pilotos usam seeds 44112001–44112005, em ordem crescente de taxa; as principais r1/r2 usam 44112101/44112102. Mesmo seed não garante sequência efetiva idêntica entre diferentes distribuições. C3_ON_r2, C3_OFF_r2 e C5_ON_r2 não foram executados após o gate exploratório; não são repetições ausentes por falha HTTP. O relatório histórico registra HEAD 74d70b9 no contexto da campanha; não foi localizado vínculo inequívoco de commit por execução nos metadados inspecionados, e esse valor não foi inventado no inventário. O HEAD da análise consta no manifesto novo.

## C. Estatísticas por execução

'''+stattable+'''
Valores completos em [per_run_statistics.csv](per_run_statistics.csv): n válido, média, DP amostral, mediana, p95, extremos e ausências quando definíveis. HTTP inclui todas as tentativas com duração registrada, inclusive cauda. RPS considera starts em `[0,T)`; conclusões/s na mesma janela e última conclusão ficam no inventário. A diferença entre starts e conclusões dentro da janela pode ser drenagem, não perda.

CPU Docker é média dos ticks com suporte, incluindo ticks observados fora da geração quando presentes. Não é média temporal exata. Pendências, handlers e workers usam médias ponderadas pelo tempo apenas em `[0,T)`. Percentil: posto mais próximo `ceil(0,95n)`; DP amostral usa n−1. Os números de observações são contagens reais, não valores escalados junto com unidades.

## D. Estatísticas entre repetições

'''+reptable+'''
O arquivo [configuration_summary.csv](configuration_summary.csv) resume cada estatística por execução. Uma média de p95 por execução é rotulada como tal; não é p95 de amostras reunidas. Duas repetições permitem calcular DP entre runs, mas não caracterizar bem sua distribuição. Para n=1 o DP entre runs permanece ausente.

## E. Comparação entre configurações

### Taxa agregada

Os pilotos controlam N=2, 32 threads/fonte e duração de 12 s. À medida que a taxa nominal passa por 8, 32, 64, 96 e 128 RPS, CPU e ocupação crescem. Os starts efetivos são aproximadamente 7,33; 33,42; 63,92; 96,83 e 127,50/s. São realizações curtas com seeds distintas, não uma curva de capacidade replicada. O desvio relativo maior em 8 RPS é compatível com pequena contagem; não comprova limitação do executor.

### Mesma taxa, duas/quatro fontes

A 64 RPS, C2 ON versus C4 ON representa 2×32 com 32 threads/fonte versus 4×16 com 16 threads/fonte. As médias HTTP são cerca de 36–38 versus 32 ms, mas os p95 ficam próximos de 59–60 ms. Espera p95 aumenta modestamente de ~9,8 para ~11,3 ms; CPU/op também difere (~11,9–12,2 versus ~12,5–12,7 ms). A amostra não permite atribuir esses contrastes exclusivamente ao número de fontes.

A 128 RPS, C3 ON versus C5 ON muda 2×64 para 4×32 e reduz a quota por fonte. HTTP médio passa de ~46,5 para ~206,5 ms e espera média de ~6,9 para ~166,8 ms. CPU/op passa de ~11,37 para ~14,65 ms. O contraste é entre configurações completas, uma execução de cada; fontes, quotas e estado operacional não foram isolados.

### ON/OFF

A 64 RPS, ON−OFF aumenta HTTP médio em ~0,78 e ~0,62 ms e CPU Docker em ~3,64 e ~1,79 pontos percentuais. As diferenças de RPS são pequenas. A 128 RPS o OFF tem HTTP médio maior em ~32,1 ms que o ON; uma repetição não identifica overhead. Não há estimativa causal de instrumentação nem prova de overhead nulo.

![Contrastes ON/OFF](figures/instrumentation.png)

## F. Análise temporal

![Progressão das taxas nos pilotos](figures/rate_progression.png)

![Contrastes de fontes e taxa](figures/sources.png)

As linhas são bins descritivos de 1 s; não repetições. HTTP é atribuído à conclusão, espera worker à submissão, CPU/op ao início computacional e atraso da fonte ao início da tarefa. Os relógios diagnósticos são utilizados somente após verificar os certificados de comparabilidade existentes. Brackets previamente auditados de até ~50–62 ms limitam ordenação fina perto de fronteiras.

Nas condições de 64 RPS não se observa a tendência prolongada de crescimento de filas que caracteriza C5. Em C5, a espera e as pendências aumentam aproximadamente entre 7–9 s, chegam ao máximo por volta de 14–16 s e recuam parcialmente antes do fim. O pico não representa uma divergência indefinida: todas as tentativas drenam. O fim da janela de geração não é o fim de toda atividade.

## G. Interpretação operacional

O gerador faz primeiro despacho imediato e depois esperas exponenciais relativas. Planejar o próximo despacho, submetê-lo, obter thread, iniciar HTTP e concluir são eventos distintos. Bookkeeping, espera e agendamento não são compensados por uma agenda absoluta. Portanto, o processo efetivo não foi certificado como Poisson homogêneo exato.

Nos runs ON regulares, o p95 submit→task é submilissegundo. C5 apresenta média ~17,36 ms e p95 ~145,68 ms, embora a taxa total permaneça próxima da nominal. Há fila antes do HTTP; cumprir o total agregado não garante cumprir os instantes planejados. O atraso de fontes cresce tardiamente na execução, depois da elevação de espera na vítima observada anteriormente. Isso é compatível com tarefas HTTP longas ocupando threads, sem provar direção causal. [source_statistics.csv](source_statistics.csv) preserva diferenças por fonte; picos simultâneos agregados são reconstruídos por intervalos, não pela soma de máximos não coincidentes.

Espera worker é submit→início e inclui fila, IPC e agendamento; não é CPU. CPU/op mede process_time no worker; duração de parede mede início→fim. CPU Docker usa `ΔCPU_contêiner/ΔCPU_sistema × CPUs_online ×100`; 80% representa cerca de 0,8 núcleo equivalente. Não representa 80% do pool de dois workers. O host tinha 12 CPUs lógicas segundo a evidência anterior; limites registrados da vítima são sem quota/cpuset. CPU do contêiner inclui outros custos além das operações.

Em C3/C5, a ocupação média estimada é ~1,46/~1,87 de dois workers. C5 mantém ambos quase continuamente ocupados no período de maior fila e chega a dezenas de operações aguardando início. A diferença de HTTP acompanha principalmente a espera; CPU/op também aumenta, mas em escala muito menor. Nenhuma dessas associações determina por que o custo mudou ou demonstra que quatro fontes causaram a degradação.

## H. Considerações estatísticas

DP das durações descreve heterogeneidade entre tentativas. DP dos starts de 1 s descreve variabilidade temporal. DP entre runs descreve repetição da configuração. Esses denominadores não são intercambiáveis. Médias de ocupação são integrais de sobreposição divididas pelo tempo, sem DP fictício entre operações.

Não foram calculados ICs. Futuros ICs poderiam acrescentar valor para HTTP médio, espera média e diferenças ON/OFF ou N=2/N=4, usando execuções como unidades e pareamento quando justificado. As condições C1/C2/C4 têm somente n=2 equivalentes: suficientes para DP descritivo, frágeis para IC útil. Os pilotos e condições de 128 têm n=1 por configuração e não sustentam incerteza entre repetições. Média/DP/amplitude são suficientes para esta exploração.

Com novas repetições independentes e premissas razoáveis, IC t para média por execução ou para diferenças pareadas seria uma opção simples. Normalidade aproximada das médias/diferenças, independência e amostra devem ser justificadas; janelas consecutivas não aumentam artificialmente n. Não se propõe bootstrap ou método avançado. Essa questão é distinta dos ICs da avaliação dos detectores.

## I. Lacunas identificadas

32 e 96 RPS têm apenas um piloto; 128 tem uma execução por distribuição/modo. Nenhuma execução recente dura vários minutos. OFF não permite reconstruir espera ou CPU/op e os contadores diagnósticos ausentes não são zero. A mudança N=2→4 altera a quota local. Não há identificação causal de frequência/escalonamento/interferência. O vínculo por execução com commit é incompleto na evidência inspecionada. A integridade publicada não foi recertificada integralmente por hashes de todos os datasets; o novo manifesto identifica os inputs efetivamente lidos.

## J. Proposta de complementação

**Necessário agora:** nenhum experimento para sustentar as conclusões exploratórias acima. A análise existente basta para manter candidatas e identificar limitações.

**Antes da campanha científica, dependente do desenho final (prioridade alta):** confirmar estabilidade da configuração legítima escolhida no horizonte científico. Proposta preliminar: três execuções legítimas independentes da única configuração finalista, com duração nominal igual à futura execução científica e drenagem até o limite previamente definido; 390 s apenas se esse horizonte histórico for mantido. Coletar logs científicos, captura, recursos, estados finais e diagnóstico suficiente para fila/espera. Isso responde à estabilidade sustentada que 12–20 s não avaliam. Três é uma verificação mínima preliminar, não tamanho amostral definitivo para inferência. Pode integrar os primeiros controles/baseline se critérios forem definidos antes da coleta.

**Opcional:** se a decisão continuar especificamente entre 32 e 64 RPS, três execuções equivalentes por carga, mesmo N e quota, no horizonte aprovado. Pode adiar até a escolha dos ataques; executar somente se a decisão não puder ser resolvida pela validação da finalista. Não há justificativa para repetir toda a matriz 8–128 ou aprofundar C5 agora.

## K. Contribuição para o protocolo científico

8–64 RPS têm evidências favoráveis de operação regular no intervalo observado; 32 tem menos evidências de repetibilidade que 64. 96 e 128×duas fontes permanecem evidência limitada. 128×quatro fontes exige tratar a fila observada como parte da condição, não como referência legítima estável presumida. A escolha final depende de representatividade, folga e mecanismos ofensivos; nenhum número de fontes ou taxa é fixado aqui.

### Rastreabilidade e reprodução

Script [analyze.py](analyze.py); comando a partir da raiz: `PYTHONPATH=. .venv/bin/python -B reports/legitimate_characterization_20261105/analyze.py`. Ele lê apenas a campanha recente e grava exclusivamente neste diretório. [analysis_manifest.json](analysis_manifest.json) registra HEAD e SHA-256 dos arquivos lidos. [timeline_1s.csv](timeline_1s.csv) permite reproduzir as figuras e examinar amostras vazias. Inputs são logs e configurações originais, não tabelas históricas agregadas. Não houve experimento, tráfego, inicialização Docker, alteração de features, detector, autoridade, dataset ou arquivo histórico.
''')
