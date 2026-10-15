"""Render transparent descriptive tables from pilot artifacts, no model selection."""
import csv
import json
from pathlib import Path
import statistics as st
from .run import OUT,ORDERS,put

DOC=Path(__file__).resolve().parents[1]/'docs/stage13-pilot'
A=OUT/'analysis'


def csvs(name):
    with (A/name).open(newline='') as f:return list(csv.DictReader(f))


def fmt(x):
    if x is None or x=='':return '—'
    return f'{float(x):.4g}'


def table(headers,rows):
    return ['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|',
            *['| '+' | '.join(str(x) for x in row)+' |' for row in rows],'']


def main():
    summary=json.loads((A/'summary.json').read_text());audit=json.loads((OUT/'audit.json').read_text())
    events=json.loads((A/'event_timing_and_counts.json').read_text())
    between=csvs('between_seeds.csv');parameters=csvs('baseline_parameter_variability.csv')
    blocks=csvs('features_by_run_block.csv');scores=csvs('scores_by_phase.csv')
    inventory=audit['inventory'];precision=csvs('repetition_precision_sensitivity.csv')
    lines=['# Resultados do piloto experimental — Etapa 13','',
        '**Piloto de desenvolvimento, não avaliação científica definitiva. Sem thresholds, decisões, ranking ou eficácia.**', '',
        '## Execução e desenho', '',
        'Plano prévio em [design.md](design.md). Operação /medium para todos os clientes, quatro sources benignas ×2 RPS, um atacante ×8 RPS durante atividade. Containers → NGINX → uma vítima, dois workers, autoscaling desligado, timeout 2 s e Δ=1 s. PRE=24 s, evento planejado=36 s, POST=24 s; total 84 s. Periódico: burst 2 s/período 6 s, duty 1/3, seis ciclos. CoV L=3/6/12 somente de desenvolvimento.', '',
        f"Concluídos {summary['runs']} runs, {summary['eligible']} elegíveis, {len(summary['failures'])} falhas/inelegíveis. Seeds 101,211,307,401,503, cada uma pareada B/C/P; ordem predeclarada e parcialmente contrabalançada. Nenhuma micrograde/intensidade adicional foi necessária após a primeira tríade.", '',
        'Todos os cenários passaram exportação Stage 8, validação Stage 9 e extração Stage 10. Config canônica só varia nos fatores previstos; IDs das imagens são iguais dentro e entre seeds e foram confrontados com backends/sources reais. Proveniência e hashes estão preservados. Isso prova comparabilidade nominal, não identidade de carga de host, timing ou chegadas realizadas.', '']
    lines+=table(['Seed','Cenário','Run ID','Status/elegível','Requests benignas/ataque','Falhas','Lifecycle (s)','Última observação (s)'],[
        [r['seed'],r['scenario'],f"`{r['run_id']}`",f"{r['status']}/sim",
         f"{next(e for e in events if e['seed']==r['seed'] and e['scenario']==r['scenario'])['benign_starts']}/{next(e for e in events if e['seed']==r['seed'] and e['scenario']==r['scenario'])['attack_starts']}",
         next(e for e in events if e['seed']==r['seed'] and e['scenario']==r['scenario'])['failures'],fmt(r['lifecycle_seconds']),fmt(r['last_observation_seconds'])] for r in inventory])
    lines+=['## Variabilidade entre seeds','',
        'A unidade desta tabela é a **média de cada run durante [24,60)**, com cinco runs por célula. Não são centenas de janelas independentes. As médias de duração são médias de médias Stage 10, sem ponderação por número de requests. CV descritivo = desvio das cinco médias dividido pela média delas; não é o detector CoV. Quantis usam interpolação linear em (n−1)q. Nulls excluídos apenas do cálculo descritivo, com suporte explícito nos CSVs, sem alterar dados.', '']
    lines+=table(['Feature','Cenário','Média entre runs','SD entre runs','Mediana','Min–max','CV descritivo'],[
        [r['feature'],r['scenario'],fmt(r['mean']),fmt(r['sd']),fmt(r['median']),f"{fmt(r['min'])}–{fmt(r['max'])}",fmt(r['descriptive_relative_sd'])]
        for r in between if r['phase']=='EVENT_POSITION'])
    lines+=['Detalhes de todas as fases, nulls, quantis e blocos PRE/POST em `analysis/features_by_run_phase.csv`, `features_by_run_block.csv` e `between_seeds.csv`. Comparações por blocos são descritivas, sem teste de significância ou descarte de startup.', '',
        '## Baselines e Z-score','',
        '25 modelos de baseline único (cinco features × cinco benignos) documentam variação de μ/σ. Scoring cross-fit usa baseline B de OUTRA seed por rotação predefinida: 101←503,211←101,307←211,401←307,503←401. É retrospectivo e exploratório, não valida treinamento cronologicamente anterior ao teste. Nenhum atacado ou próprio run serve ao seu fitting. Outro ramo ajusta cinco modelos usando apenas B101+B211 e pontua 307/401/503; todos permanecem piloto, mas essa ramificação ilustra seeds disjuntas.', '',
        'Fitting preserva todas as observações válidas da série completa, inclusive cauda; isso é o contrato existente e não foi silenciosamente substituído por um baseline recortado. A influência da cauda e do startup é uma limitação metodológica a resolver antes da campanha. μ/sigma abaixo são dos artefatos realmente usados, com ddof=1, parâmetros exatos auditáveis e nulls contados.', '']
    lines+=table(['Feature','Parâmetro','Média entre seeds','SD','Min–max','CV descritivo'],[
        [r['feature'],r['parameter'],fmt(r['mean']),fmt(r['sd']),f"{fmt(r['min'])}–{fmt(r['max'])}",fmt(r['descriptive_relative_sd'])] for r in parameters])
    lines+=['## CoV: sensibilidade temporal, sem escolha de L','',
        'Cada score usa L observações consecutivas, incluindo a atual. Null reinicia histórico; o warm-up é consequência metodológica, não negativo/zero. As médias abaixo são resumos dos cinco runs e não um ranking. O próprio objeto medido muda com L: misturar fases no histórico pode elevar ou sustentar o CoV, em vez de simplesmente suavizar. Não há método acumulativo adicional neste piloto.', '']
    tab=[]
    for feature in ['request_starts','mean_cpu_percent']:
        for scenario in 'BCP':
            for l in [3,6,12]:
                rr=[r for r in scores if r['method']=='cov' and r['feature']==feature and r['scenario']==scenario and r['lookback']==str(l) and r['phase']=='EVENT_POSITION']
                tab.append([feature,scenario,l,fmt(st.mean(float(r['mean']) for r in rr if r['mean'])),sum(int(r['unavailable']) for r in rr)])
    lines+=table(['Feature','Cenário','L dev','Média dos scores médios por run','Janelas sem score no evento'],tab)
    lines+=['## Inspeção temporal','',
        'Seed diagnóstica 307 foi escolhida por posição central na lista prévia, não por resultado. `analysis/diagnostic_seed307.csv` mostra todas as cinco features, Z-score/CoV, PRE→evento→POST, fase programada de burst/silêncio, overlap e attack_request_starts. Abertura de labels é bloqueada durante TODO fitting/scoring; esses campos são acrescentados só depois, pelo adaptador diagnóstico/evaluator. Não redefinimos attack_active nem criamos burst_active.', '',
        'O calendário programado é auxiliar e não prova emissão. Os seis bursts por seed tiveram as seguintes contagens realizadas; o evento global inclui os silêncios e seus efeitos/conclusões.', '']
    lines+=table(['Seed','Starts por burst P','Total atacante P','Total atacante C'],[
        [seed,','.join(map(str,next(e for e in events if e['seed']==seed and e['scenario']=='P')['burst_start_counts_programmed'])),
         next(e for e in events if e['seed']==seed and e['scenario']=='P')['attack_starts'],
         next(e for e in events if e['seed']==seed and e['scenario']=='C')['attack_starts']] for seed in ORDERS])
    d=csvs('diagnostic_seed307.csv')
    select=[r for r in d if r['scenario']=='P' and r['feature']=='request_starts' and
            (r['method']=='zscore_crossfit' or r['method']=='cov' and r['lookback']=='6') and
            int(r['window_index']) in [23,24,25,26,29,30,31,32,59,60,65,72,83]]
    lines+=table(['Método','L dev','Janela','Fase programada','Feature','Score','Overlap pós-hoc','Starts atacantes pós-hoc'],[
        [r['method'],r['lookback'],f"[{r['start']},{r['end']})",r['programmed_phase'],fmt(r['value']),fmt(r['score']),fmt(r['overlap_posthoc']),r['attack_request_starts_posthoc']] for r in select])
    lines+=['## Custo medido','']
    lines+=table(['Medida','Resultado'],[
        ['Tempo nominal total',f"{summary['nominal_seconds']} s ({summary['nominal_seconds']/60:.2f} min)"],
        ['Lifecycle somado',f"{summary['lifecycle_seconds']:.2f} s"],
        ['Wall somado execução + Stage 8–10',f"{summary['total_run_wall_seconds']:.2f} s"],
        ['Intervalo primeiro início→último fim (inclui pausas)',f"{summary['wall_span_seconds']:.2f} s"],
        *[[f'Armazenamento {key}',f'{value/1024**2:.2f} MiB'] for key,value in summary['bytes_by_stage'].items()],
        ['Análise de scores/estatísticas',f"{summary['analysis_wall_seconds']:.2f} s wall, {summary['analysis_cpu_seconds']:.2f} s CPU do processo"],
        ['Pico RSS da análise',f"{summary['analysis_maxrss_kib']/1024:.2f} MiB"],
        ['Armazenamento piloto antes do relatório/auditoria',f"{summary['pilot_storage_bytes']/1024**2:.2f} MiB"],
        ['Armazenamento análise antes do summary',f"{summary['analysis_storage_bytes']/1024**2:.2f} MiB"]])
    average=summary['total_run_wall_seconds']/15
    perbytes=sum(summary['bytes_by_stage'].values())/15
    lines += [f"Média observada ≈{average:.2f} s e {perbytes/1024**2:.2f} MiB por run para raw+dataset+features+validation. Uma extrapolação linear de R runs semelhantes custa ≈R×esses valores, antes de pausas, falhas, armazenamento de scores e mudanças de duração. Matriz científica normal-only training/calibration mais tríades de teste tem R=n_B+n_C+3n_T, não necessariamente todas as combinações em todas as fases. Raw e Stage 8 duplicam parte da evidência por contrato; nenhum foi apagado.", '',
        '## Repetições: sensibilidade de planejamento, não N final','',
        'As curvas 1→5 seeds estão em incremental_convergence.csv; a ordem é fixa e um aparente platô não prova convergência. A tabela abaixo usa médias benignas por run no período planejado, calcula SD entre runs e ilustra n≈(1,96·s/(r·média))² para semi-amplitudes relativas r. É uma aproximação normal otimista de planejamento, não IC garantido, recomendação final ou correção da incerteza da variância estimada com cinco seeds. A quantidade mínima algébrica exibida é duas; isso não significa que duas sejam cientificamente suficientes. Quantis t/planejamento conservador, blocos de host e um piloto normal maior podem aumentar o necessário.', '']
    lines+=table(['Feature','n ilustrativo: r=10%','r=5%','r=2%'],[[feature,*[next(r['normal_approx_n'] for r in precision if r['feature']==feature and float(r['relative_halfwidth'])==q) for q in [.1,.05,.02]]] for _,feature in __import__('pilot_stage13.analyze',fromlist=['FEATURES']).FEATURES])
    lines+=['Para fechar N é preciso escolher precisão e endpoint principal. Esses cálculos dimensionam médias, não recall de eventos, delay ou falsos alarmes raros. Estes últimos precisam eventos/exposição próprios e só poderão ser planejados após protocolo de decisão. Não se deve tratar as janelas correlacionadas ou os três cenários pareados como novas seeds. Não foi usado bootstrap/IC forte com esta amostra pequena.', '',
        '## Separação e calibração a estudar','',
        'A: runs distintos é obrigatório, mas reutilizar seed em baseline/calibration/test pode repetir o mesmo fluxo e subestimar generalização; reexecuções da mesma seed são úteis para variabilidade do sistema, não substituem seeds novas. B: preferir conjuntos de seeds disjuntos por papel, **também com runs fisicamente independentes**. A partição 101/211→307→401/503 é ilustrativa e já foi inspecionada; não será reaproveitada como teste cego. Campanha definitiva usará dados novos, baseline/calibration normais, testes B/C/P pareados dentro de cada seed de teste e ambiente compatível. A comparação de padrões deverá explicitar o efeito de duty cycle/carga média e das políticas de admissão já existentes.', '',
        'Quantis de scores benignos de calibração são viáveis como alternativa empírica, com orientação/cauda explícita e diagnóstico de dependência; média+kσ permite uma família simples, mas k não foi escolhido e caudas não são necessariamente gaussianas. Limite teórico de Z-score requer hipóteses e parâmetros estimados não geram automaticamente N(0,1); não há justificativa automática para |z|>3. CoV não tem limite universal independente de L, taxa e distribuição. Controle de FPR máximo deve ser estimado/confirmado em calibração normal independente, com intervalo e exposição suficientes; FPR/janela não equivale a episódios por hora. Uma única seed de calibração de 84 s dá cauda pobre, agravada por scores CoV sobrepostos. Os quantis em benign_calibration_score_distributions.csv são apenas descrições, não thresholds ou decisões.', '',
        '## Limitações e próximos passos','',
        'Leitura substantiva e decisões pendentes em [interpretation.md](interpretation.md). Nenhuma eficácia é inferida destas tabelas. Todas as cinco candidatas continuam justificadas por observabilidade; qualquer redução deve ser por custo/suporte/redundância e hipótese, não maximização em labels do piloto.', '',
        'Event-level: Stage 8 tem actual_start/actual_end e IDs em attack_events.csv, auditados em event_timing_and_counts.json. Stage 10 v1 só tem overlap da união e starts auxiliares; não preserva identidade/intervalos individuais para ligar cada decisão a um evento. Logo falta **o vínculo verificável do evaluator com intervalos efetivos**, não necessariamente dado bruto inexistente. Não calculamos detection delay e não alteramos Stage 10.', '',
        'Foram adicionados pilot_stage13/{__init__,run,batch,analyze,truth,audit,report}.py, tests/test_stage13_pilot.py, docs/stage13-pilot/* e experiment_results/stage13-pilot/*. Nenhum arquivo preexistente de Etapas 0–12 foi alterado. O snapshot verificou '+str(audit['protected_files_checked'])+' arquivos por SHA/mtime e '+str(audit['manifest_entries_verified'])+' entradas dos manifests novos. Uma correção técnica no helper de comparação do runner (to_json em vez de API inexistente to_dict), sem alteração de config/simulação, tem versões arquivadas e revisão registrada no plano. Nenhum run foi descartado/regerado para esconder falha. Após a coleta, foi adicionado apenas um guard de reexecução antes de qualquer escrita; o runner usado na coleta e o plano original foram preservados por hash. O código atual não retoma/estende um plano cuja identidade de runner mudou. Reproduzir em diretório de campanha novo exige novo plano, sem sobrescrever este piloto.', '',
        'A suíte final passou com 254 testes, incluindo cinco novos testes de desenho, quantis, regiões e proteção contra reexecução com overwrite. Não houve commit.']
    DOC.mkdir(parents=True,exist_ok=True);(DOC/'results.md').write_text('\n'.join(lines)+'\n')
    print(DOC/'results.md')

if __name__=='__main__':main()
