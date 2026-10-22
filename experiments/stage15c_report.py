"""Portuguese scientific review draft, generated from frozen per-run evidence."""
from decimal import Decimal
from experiments.stage15c_analysis import METHODS,FEATURES,number,text

NAMES={'zscore':'Z-score','cov':'CoV L6','ewma':'EWMA .2','cusum':'CUSUM .5'}
SHORT=dict(zip(FEATURES,('pacotes','bytes TCP','inícios req.','duração ms','CPU %')))
CONFIGS=[(m,f) for m in METHODS for f in FEATURES]


def fmt(v,n=4):return 'null' if v is None else f'{Decimal(str(text(v))):.{n}f}'
def table(headers,rows):return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|',*['| '+' | '.join(map(str,r))+' |' for r in rows]])+'\n'
def label(m,f):return NAMES[m]+' / '+SHORT[f]
def cell(s):return f"{fmt(s['mean'])} ± {fmt(s['sample_sd'])}; {fmt(s['median'])} [{fmt(s['q1'])}; {fmt(s['q3'])}]; n={s['defined_n']}/{s['runs_n']}"


def report(data,meta,bundle):
    primary={(r['scenario'],r['method'],r['feature'],r['metric']):r for r in data['primary_descriptive']}
    post={(r['scenario'],r['method'],r['feature'],r['metric']):r for r in data['post_event_descriptive']}
    events={(r['scenario'],r['method'],r['feature']):r for r in data['event_descriptive']}
    pairs={(r['method'],r['feature'],r['metric']):r for r in data['paired_descriptive']}
    mech={(r['scenario'],r['method'],r['feature']):r for r in data['persistence_mechanism_summary']}
    per={ (r['seed'],r['scenario'],r['method'],r['feature']):r for r in data['primary_per_run']}
    same=sum(per[r['seed'],r['scenario'],r['method'],r['feature']]['fpr']==r['post_event_alarm_rate'] for r in data['post_event_per_run'])
    defined=sum(r['post_event_alarm_rate'] is not None for r in data['post_event_per_run'])
    parts=[f'''# Stage 15C — análise descritiva e interpretação científica

**ENTREGUE PARA REVISÃO CIENTÍFICA — NÃO FROZEN.**
Não foi feito ranking único, teste de hipótese, bootstrap, intervalo de confiança,
seleção de método/feature ou ajuste de parâmetro. Nenhum detector, scorer, decision
policy ou evaluator foi reexecutado. Scores, decisions, thresholds, GT e métricas
congeladas permaneceram intactos. Esta etapa interpreta o experimento existente.

## 1. Proveniência e escopo

Não foi encontrado AGENTS.md no repositório nem nos ancestrais consultados.
Foram lidos o protocolo pré-TEST, contratos de avaliação, manifests, freezes e
encerramentos 15A/15B. A bridge foi verificada como referência imutável, sem reabrir
a revisão de equivalência histórica já aprovada.

O commit 15B `3735225a5ba14d7e6eb279af73913e0e78320dea` é ancestral do HEAD de execução;
não foi exigida igualdade do HEAD. Hashes, arquivos referenciados e schemas foram
verificados antes e depois. A fonte das métricas é a tabela por run da 15B; pooled
não substitui médias por seed. A proveniência completa está em stage15c_analysis_manifest.json.

''']
    parts.append(table(['Input','SHA256'],[[k,'`'+v['sha256']+'`'] for k,v in bundle['inputs'].items()]))
    parts.append(f'''
São 48 runs: 16 B, 16 C, 16 P, com 16 seeds pareadas. Há 960 avaliações primárias,
960 de startup, 640 event-level e 640 pós-evento. Todas as 20 configurações são
mostradas na ordem fixa método/feature, independentemente do resultado.
Alpha=.01; Z-score signed upper-tail; CoV L=6/ddof=1; EWMA lambda=.2; CUSUM k=.5.

As cinco features são ingress_packet_count (pacotes),
ingress_tcp_payload_length_sum_bytes (bytes TCP), request_starts (inícios req.),
mean_duration_ms (duração ms) e mean_cpu_percent (CPU %).
A unidade é **run/seed**; janelas sucessivas não são réplicas independentes.

## 2. Contratos, null e estatística descritiva

O scoring ocorreu causalmente em [0,144), sem reset em 48. PRIMARY usa [48,144);
STARTUP_DIAGNOSTIC usa [0,48), separadamente. Boundary 0<overlap<1 e decisões
unavailable ficam fora de TP/FP/TN/FN, com contagens próprias e por grupo de GT.
Elegibilidade técnica não equivale a prova de cobertura observacional ininterrupta.
Zero de uma feature observada não prova ausência física de tráfego.

Undefined permanece null; médias e quantis usam só valores definidos, com n definido,
n undefined e seeds explícitos. SD amostral usa ddof=1 e é null se n<2.
Q1/Q3: tipo 7, h=(n−1)p, interpolação linear nos valores definidos ordenados;
mediana usa a mesma convenção, p=.5. Não são intervalos de confiança.
As razões exatas são recuperadas dos próprios numeradores/denominadores congelados
15B, após verificar igualdade da métrica serializada, evitando arredondar antes do
sumário. Não se reclassifica GT nem se recria decisão.
F1 é resumido por run, nunca calculado a partir das médias de Precision e Recall.
O contrato fixa F1=2TP/(2TP+FP+FN); sua definição é independente dos denominadores
de Precision/Recall. Em B Recall é null, não zero.

Os {len(data['reconciliation'])} resumos correspondentes da 15B reconciliaram exatamente
média, mediana, SD, mínimo e máximo, com o mesmo suporte. Os novos quartis são
acréscimos descritivos, sem modificar a 15B. Valores abaixo são arredondados só
para leitura; CSV/JSON preservam 50 dígitos e null.

## 3. Resultados primários por run/seed

### B: falsos positivos benign-only e estabilidade

''')
    parts.append(table(['Configuração','Runs','n def./undef.','Média FPR','SD','Mediana','Q1','Q3','Min','Max'],
        [[label(m,f),16,str(primary['B',m,f,'fpr']['defined_n'])+'/'+str(primary['B',m,f,'fpr']['undefined_n']),*[fmt(primary['B',m,f,'fpr'][k]) for k in ('mean','sample_sd','median','q1','q3','min','max')]] for m,f in CONFIGS]))
    parts.append('''
**Evidência:** FPR médio em B não descreve sozinho a dispersão. Em request_starts,
CUSUM tem média 0.0176, mediana 0, SD 0.0450 e máximo 0.1667; Z-score tem média
0.0091, mediana 0.0104, SD 0.0092 e máximo 0.0313. A leitura por seed mostra regimes
de poucos runs com alarmes e vários sem alarmes, sem inferir diferença populacional.
Alpha=.01 é o alvo nominal da calibração benigna, não garantia de FPR=.01 em cada run.
FPR=0 observado, como em CUSUM/CPU nos 16 B, não garante ausência de alarmes em
outros regimes, após um ataque ou numa população externa.

Todas as contagens TP/FP/TN/FN, unavailable e boundary têm os mesmos nove sumários
em tables/primary_descriptive.csv. A tabela por run preserva os 16 valores de B
por configuração; nenhum resultado com poucos positivos foi omitido.

Nas tabelas C/P, cada célula é: **média ± SD; mediana [Q1; Q3]; n definido/16**.
Mínimos/máximos e seeds estão nas tabelas machine-readable.

''')
    for scenario in 'CP':
        parts.append('\n### '+scenario+' — window-level PRIMARY\n\n')
        parts.append(table(['Configuração','Precision','Recall','F1','FPR'],[[label(m,f),*[cell(primary[scenario,m,f,k]) for k in ('precision','recall','f1','fpr')]] for m,f in CONFIGS]))
    parts.append('''
### Regimes de comportamento: evidência e interpretação

**Z-score — evidência:** request_starts registra Recall médio C=0.5411 e P=0.1750,
com FPR B=0.0091 e FPR C/P=0.0042/0.0053. A detecção de eventos ocorre em 16/16 de
ambos os cenários. Duração tem Recall C=0.0286 e P=0.0179, com somente 10/16 e 7/16
eventos detectados. Logo, detectar ao menos uma janela e cobrir o intervalo global
são objetivos diferentes, e a feature modifica ambos.
**Interpretação:** para contagens/bytes neste experimento, o Z-score combina
falsos positivos relativamente contidos com alarmes pontuais; isso sustenta a
hipótese de conservadorismo no sentido de cobertura temporal, não uma garantia
universal de especificidade. A implementação é stateless após o baseline congelado.
**Limitação:** não detecta quedas lower-tail, nem depende de dano econômico para alarmar.

**CoV — evidência:** request_starts passa de Recall C=0.0125 para P=0.1625;
eventos detectados são 4/16 em C e 13/16 em P. O FPR B é 0.0189 e os F1 médios
C/P são 0.0221/0.2529. Duração tem 1/16 eventos em C e 3/16 em P.
**Hipótese explicativa:** um quociente SD/média local pode responder a alternância
relativa, mas não necessariamente a um patamar elevado e estável. Isso é compatível
com o aumento observado de resposta a P, sem demonstrar que a periodicidade foi a
única causa. L=6 coincide nominalmente com o período de 6s, mas não se testou um
mecanismo de ressonância nem outros L nesta análise primária.
**Interpretação:** CoV isolado não apresenta cobertura ampla do evento global neste
conjunto; continua útil para caracterizar resposta à variabilidade. Não se propõe
descartar o método ou mudar a janela usando TEST.

**EWMA — evidência:** request_starts apresenta Recall C=0.9929, F1 C=0.9273 e
16/16 eventos em C; em P, Recall=0.5821 e 16/16 eventos. Seus alarmes pós-evento
médios são 0.0890 em C e 0.0159 em P, frente a FPR B=0.0137.
**Hipótese explicativa:** suavização temporal sustenta evidência moderada e também
transporta parte dela após o evento. As séries e o código são compatíveis com esse
mecanismo de memória que decai, sem isolar causalmente sua contribuição.
**Interpretação:** há um trade-off entre cobertura/sensibilidade e custo de
persistência; ele depende da feature. Para duração, por exemplo, Recall P=0.0393 e
8/16 eventos demonstram que memória não elimina a dependência da observação.

**CUSUM — evidência:** request_starts tem Recall C=0.9911 e eventos 16/16, mas FPR
C=1.0000, Precision C=0.3702 e F1 C=0.5391. Em P, Recall=0.8768 e F1=0.6574,
com 16/16 eventos e FPR=0.4841. Para CPU, C detecta 16/16 eventos, P 8/16; os
alarmes pós-evento médios são 0.9703/0.0858.
**Interpretação:** a configuração é sensível a evidência acumulada e apresenta um
problema observado de recuperação no horizonte de coleta para certas features.
Isso não constitui ranking global: o resultado combina cobertura, precisão,
controle benigno, atraso e recuperação, com pesos de aplicação ainda não definidos.
**Limitação:** os resultados dizem respeito a k=.5, thresholds e política sem reset
por alarme congelados, não a todas as variantes possíveis de CUSUM.

## 4. Eventos e atrasos: suporte e atribuição

A tabela refere-se ao evento global [actual_start,actual_end), sem drained_end.
Em P, os silêncios entre bursts pertencem a esse evento. Cada run C/P tem um evento;
640 são avaliações evento/configuração, não 640 eventos experimentais independentes.
Uma janela positiva que sobrepõe o evento pode atender à definição de detecção
mesmo se available_at>actual_end. **Overlap isolado não prova que o ataque causou
esse alarme**: uma decisão benigna coincidente também pode cumprir a regra.

Misses não recebem atraso zero. Distribuições de atraso são condicionais aos
eventos detectados, sempre acompanhadas da taxa e do suporte. Não se pode comparar
apenas os atrasos dos métodos ignorando a proporção de eventos perdida.

''')
    parts.append(table(['Cenário','Configuração','Detectados/avaliados','Misses','Taxa','Delay média','SD','Mediana','Q1','Q3','Min','Max','n delay'],
        [[s,label(m,f),str(events[s,m,f]['events_detected'])+'/16',events[s,m,f]['events_missed'],fmt(events[s,m,f]['event_detection_rate']),
          *[fmt(events[s,m,f][k]) for k in ('mean','sample_sd','median','q1','q3','min','max')],events[s,m,f]['defined_n']] for s in 'CP' for m,f in CONFIGS]))
    parts.append('''
**Evidência de seleção:** CoV/duração não tem nenhum par C/P detectado em ambos;
CUSUM/CPU tem 8/16 pares e Z-score/duração apenas 4/16. A comparação condicional
desses atrasos não representa todos os 16 pares. Em request_starts, Z-score tem
16/16 pares de atraso, com P−C médio 0.8144s e mediana −0.0360s; a diferença entre
média e mediana mostra por que a dispersão importa. Não se conclui que P é mais
rápido a partir da mediana, nem que essas diferenças são estatisticamente estabelecidas.

## 5. Persistência após o evento e feature observada

Pós-evento é [max(actual_end,48),144), com janelas inteiras. A taxa tem denominador
**decisões disponíveis**, enquanto a contagem candidata e os unavailable são
registrados à parte. As distribuições abaixo usam runs, não janelas, como unidade.

''')
    parts.append(table(['Cenário','Configuração','Taxa: média ± SD; mediana [Q1;Q3]; n','Min','Max','Denominador disponível min–max'],
        [[s,label(m,f),cell(post[s,m,f,'post_event_alarm_rate']),fmt(post[s,m,f,'post_event_alarm_rate']['min']),fmt(post[s,m,f,'post_event_alarm_rate']['max']),
          str(int(post[s,m,f,'post_event_eligible_windows']['min']))+'–'+str(int(post[s,m,f,'post_event_eligible_windows']['max']))] for s in 'CP' for m,f in CONFIGS]))
    parts.append(f'''
**Relação com FPR:** nas {same} linhas C/P, FPR primário e post_event_alarm_rate
coincidem, incluindo {len(data['post_event_per_run'])-defined} pares null; há {defined}
comparações numéricas definidas. Isso decorre do recorte e das janelas benignas
selecionadas nesta coleção: não são duas confirmações independentes de persistência.
Comparar com B é relevante porque B não passou pelo evento atacante.

**Evidência entre seeds:** em CUSUM/request_starts, todos os 16 runs C têm taxa
pós-evento 1, SD=0, mediana e IQR=1; em P a média é 0.4841, SD=0.2388 e
mediana 0.3983. Para CUSUM/pacotes C há 15 runs ainda positivos na última janela;
para request_starts são 16; para CPU, 12. Uma taxa alta durante o pós-evento e um
alarme na última janela são evidências distintas e ambas estão tabuladas.

Para examinar o mecanismo, persistence_per_run.csv confronta os scores congelados,
observações pós-evento e o B da mesma seed/mesmas janelas. Não foi calculado novo
score ou aplicada nova política de decisão. Comparar a observação com a média
BASELINE congelada é um diagnóstico auxiliar, não um novo detector.

''')
    parts.append(table(['Cenário','CUSUM / feature','Alarme na última janela (runs/16)','Alarmes pós com observação ≤ média BASELINE / alarmes','Média por run: feature pós − B pareado'],
        [[s,SHORT[f],str(mech[s,'cusum',f]['runs_last_primary_decision_positive'])+'/16',
          str(mech[s,'cusum',f]['post_positive_at_or_below_baseline_mean_n'])+'/'+str(mech[s,'cusum',f]['post_positive_observation_n']),
          fmt(mech[s,'cusum',f]['raw_post_minus_matched_B_run_mean']['mean'])] for s in 'CP' for f in FEATURES]))
    parts.append(f'''
**Evidência que sustenta memória:** em C/request_starts, 470 de 944 janelas positivas
pós-evento têm observação ≤ média BASELINE; a média entre runs de feature pós menos
B pareado é −0.0011 inícios/janela. Essas contagens pooled são descritivas, não
944 réplicas independentes. A proximidade da feature ao controle enfraquece a
explicação de que todo alarme persistente exigiria elevação sustentada da feature.

Na seed determinística {meta['example_seed']}, a média pós-evento de request_starts em
C e no B pareado é a mesma, 7.7288. O score CUSUM existente cai de 105.8079 para
72.4735 no pós-evento, ainda acima do threshold 4.9022 até a última janela.
Em P dessa mesma seed, a feature também tem média 7.7288, enquanto o score cai
de 30.4605 para 0. **Interpretação:** é evidência concreta compatível com carga
acumulada e recuperação lenta em C, não apenas uma inferência a partir da fórmula.

**Explicação alternativa ainda presente:** nessa seed, duração pós C=26.9929ms
contra B=23.9160ms, e CPU C=12.3478% contra B=11.2410%. Esses resíduos da própria
feature podem contribuir para os scores. Entre os 16 C, as diferenças médias
CPU−B variam de −0.7156 a +1.1068 pontos percentuais; duração−B varia de −1.6864
a +3.0769ms. Portanto não se atribui toda persistência ao acumulador. Médias
semelhantes também não demonstram igualdade das distribuições temporais.
Não houve contrafactual de reset, ablação de memória ou intervenção na carga;
atribuição causal exclusiva não foi demonstrada.

## 6. Comparações pareadas P−C e estabilidade

Cada diferença usa a mesma seed. Null em qualquer lado elimina apenas aquela
diferença, nunca o run da coleção. n e seeds completos/incompletos são registrados.
Para delay, a seleção é DETECTED_IN_BOTH_SCENARIOS, com n explicitamente indicado.
Não se calculou p-valor, teste, bootstrap ou intervalo de confiança.

P tem duty cycle nominal 1/3 e menor volume médio de ataque que C, além da
alternância temporal. Portanto P−C representa diferença de regime composto,
não efeito isolado da periodicidade. Recall global em P também conta os silêncios
do evento como GT positivo; Recall menor não equivale automaticamente a falhar
em detectar cada burst. Não foi executada análise burst-level.

''')
    parts.append(table(['Configuração','Δ Recall média; mediana; n','Δ F1 média; mediana; n','Δ FPR média; mediana; n','Δ pós média; mediana; n','Δ delay média; mediana; n detectados ambos'],
        [[label(m,f),*[f"{fmt(pairs[m,f,k]['mean'])}; {fmt(pairs[m,f,k]['median'])}; n={pairs[m,f,k]['defined_n']}" for k in ('recall','f1','fpr','post_event_alarm_rate','detection_delay_seconds')]] for m,f in CONFIGS]))
    parts.append('''
**Evidência e interpretação:** em request_starts, ΔRecall médio P−C é −0.3661
(Z-score), +0.1500 (CoV), −0.4107 (EWMA) e −0.1143 (CUSUM), todos com 16 pares.
Isso é compatível com resposta pontual, variabilidade e memória interagindo com
regimes diferentes. CUSUM pode ter F1 maior em P ao mesmo tempo que Recall menor,
porque a taxa de falsos positivos pós-evento também difere; não é evidência de
superioridade global. Nas features de rede CoV há somente 15 pares definidos para
algumas métricas, devido aos nulls preservados. Não se substituem esses nulls por zero.

A entry 29/C mantém seus 20 resultados, dataset_valid=true e analysis_eligible=true.
REQUEST_FAILURES_OBSERVED e EXPECTED_PHASE_OBSERVATIONS são limites históricos de
qualidade/cobertura, não autorização para exclusão ou reponderação. Não foi feita
sensibilidade removendo essa entrada. Os suportes n=15 ou métricas zero decorrem
dos contratos congelados, e devem acompanhar a interpretação.

## 7. Figuras e exemplos temporais

Os seis painéis principais combinam pontos por seed, medianas e suportes; não
contêm barras de confiança. As cores de seed são fixas. Nulls são cruzes fora
do eixo de valores, ou lacunas temporais, nunca pontos em zero.

''')
    for name,caption in [('01_fpr_B','FPR B: mesma escala entre métodos; alpha nominal como referência, não garantia.'),
                         ('02_recall_f1_CP','Recall/F1 C/P em [0,1], com n definido/16.'),
                         ('03_event_detection','Proporção e contagem de eventos detectados; denominador 16.'),
                         ('04_detection_delays','Delays definidos, com n detectado e misses; interpretar junto com figura 03.'),
                         ('05_post_event_alarm_rate','Pós-evento, sem misturar com startup.'),
                         ('06_paired_P_minus_C','Diferenças pareadas e n completo; delay apenas nos detectados em ambos.')]:
        parts.append(f'![{caption}](figures/{name}.png)\n\n{caption} Versão vetorial: [PDF](figures/{name}.pdf).\n\n')
    parts.append(f'''Os exemplos temporais são um apêndice, escolhido antes da inspeção de desempenho:
menor seed comum elegível ({meta['example_seed']}). Todos os B/C/P dessa seed e todas
as cinco features são mostrados. As escalas são compartilhadas entre B/C/P por linha
comparável; features com unidades diferentes não são forçadas a uma escala comum.
Os plots usam só observações e scores já presentes na 15A, conferidos com Stage10.
Não foram usados novos Z-scores, thresholds ou decisões. Sombra do evento é global;
tracejado é o threshold congelado; vermelho são decisões positivas existentes.

''')
    for f in FEATURES:
        short={'ingress_packet_count':'pkt','ingress_tcp_payload_length_sum_bytes':'bytes','request_starts':'req','mean_duration_ms':'dur','mean_cpu_percent':'cpu'}[f]
        parts.append(f'![Série temporal {f}](figures/temporal_{short}.png)\n\n[PDF vetorial](figures/temporal_{short}.pdf).\n\n')
    parts.append('''## 8. Limitações, custo computacional e alcance

**Sensibilidade à feature:** contagens/bytes representam atividade de entrada e
inícios de requisição; duração/CPU representam respostas do serviço/infraestrutura.
Não há razão contratual para que todos apresentem o mesmo efeito ou o mesmo
suporte observacional. Volume TCP registrado não é uma medição universal de bytes
na rede, de solicitações únicas ou de custo financeiro. A mesma configuração pode
ter baixa FPR em B e persistência após evento, como mostram os resultados CUSUM.

**Upper-tail e parâmetros:** só desvios superiores são considerados. Quedas de
tráfego, oscilação abaixo do baseline ou regimes de média zero podem resultar em
scores negativos/unavailable ou ausência de alarme. Não se conclui ausência de
ataque desses resultados. Mu/sigma, L, lambda, k, alpha e thresholds são específicos
do BASELINE/CALIBRATION e workload congelados; não se escolheu variante usando TEST.
Nenhuma sensibilidade L3/L12 ou alpha alternativo entrou nos resultados primários.

**Generalização:** 16 seeds pareadas, endpoint/workload e ambiente controlado,
uma infraestrutura limitada e autoscaling desabilitado não reproduzem a diversidade
de uma cloud real. Repetições dependem do mesmo ambiente; a amplitude de cenários,
workloads, escalabilidade e evolução temporal externa permanece não amostrada.
Variação entre seeds não cobre toda a incerteza operacional.
Detectar tráfego/processamento associado ao ataque não demonstra dano econômico
EDoS: não foram medidos billing real, incremento de despesas cloud ou sustentabilidade
financeira. Tampouco se demonstrou causalidade do ataque para cada alarme.

**Custo computacional — inspeção, sem benchmark:** Z-score usa quantidade constante
de operações aritméticas e estado BASELINE por observação. EWMA/CUSUM acrescentam
estado escalar e atualização constante, sem guardar a série no detector. CoV mantém
L observações e recomputa momentos em O(L) operações por janela, O(TL) no run;
com L=6 fixo, o custo cresce linearmente com T e a memória do detector é O(L).
Aritmética Fraction/Decimal depende do tamanho das representações; a precisão
congelada e o parsing/serialização do pipeline também têm custo. Essas propriedades
não são medições de latência, throughput, CPU, energia ou custo monetário.
Não se afirma que algum método tenha menor custo financeiro medido.

**Inferência futura, não executada:** seria necessária para generalizar contrastes
para além destas 16 seeds. Antes disso, devem ser fixados os contrastes de interesse,
a unidade pareada, o controle de multiplicidade entre métodos/features/métricas e
o tratamento de massas em zero, undefined, disponibilidade e misses. Delays dos
detectados não representam uma amostra incondicional de todos os eventos. Não se
seleciona agora um teste ou um vencedor e não se calculam p-valores/ICs.

## 9. Entregáveis e verificação

- analysis_tables.json preserva nulls explícitos e todas as tabelas.
- tables/primary_per_run.csv e startup_per_run.csv copiam as métricas congeladas.
- primary_descriptive/startup_descriptive incluem contagens e suporte além das razões.
- event_descriptive contém detectados/avaliados, misses e distribuição condicional.
- post_event_descriptive e persistence_per_run registram taxas, denominadores e evidência observacional.
- paired_p_minus_c, paired_delay_detected_both e paired_descriptive preservam seeds e seleção.
- reconciliation.csv registra os 560 resumos da 15B conferidos exatamente.
- figures/ contém seis figuras principais e cinco apêndices temporais, em PNG/PDF.
- stage15c_analysis_manifest.json vincula inputs/outputs, código, quantis e exemplo.

Script: python -B -m experiments.stage15c_analysis.
Reprodução: python -B -m experiments.stage15c_analysis --verify.
Os outputs existentes só são aceitos se byte-idênticos; nenhuma autoridade científica
congelada é sobrescrita. O guard impede chamadas à cadeia de scoring/evaluation.

Esta entrega constitui análise descritiva e interpretação para revisão científica.
Não constitui freeze da Stage15C, aprovação inferencial, tuning ou ranking global.
Não foi feito commit nem push nesta etapa.
''')
    return ''.join(parts)
