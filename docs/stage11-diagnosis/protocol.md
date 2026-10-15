# Diagnóstico e proposta científica antes da Etapa 11

Data: 15/10/2026. **Proposta para revisão, sem implementação de detectores, métricas ou políticas.** Nenhum experimento foi executado. Não se alteram contratos das Etapas 0–10. As estatísticas anexas são descritivas, não resultados de detecção. Não existe threshold final, quantidade final de seeds, normalização, imputação ou seleção pelo desempenho.

## 1. Conclusão e escopo do inventário

Recomendo **C: acervo atual como desenvolvimento/validação e nova campanha controlada para conclusões sobre detectores**. A recomendação decorre de lacunas concretas: apenas uma seed em todas as 58 execuções identificáveis; quatro benignos elegíveis distribuídos por quatro configurações; nenhum benigno independente equivalente ao cenário `/light` + quatro sources × 2 RPS em containers; horizontes de 8–30 s; infraestrutura sem suporte no começo; proveniência histórica incompleta; comparação contínuo/periódico confundida por operação e capacidade. Acrescentar apenas um benigno não resolveria repetição, independência das três fases e teste já inspecionado.

O acervo continua útil: contratos, conservação, missing data, boundaries, scores causais, resets e diagnóstico de bursts. `analysis_eligible=true` autoriza análise mínima; não certifica um desenho experimental adequado nem transforma regressão em campanha confirmatória.

O [inventário completo](inventory.md) contém os 21 datasets padronizados, os demais IDs e a tabela de nulls. [runs.csv](runs.csv) e [runs.json](runs.json) preservam os 58 IDs, configurações e aliases; [feature_statistics.csv](feature_statistics.csv) detalha cada feature; [feature_references.json](feature_references.json) registra hashes, proveniência, warnings e horizonte. Há 48 completed e dez incomplete no inventário ampliado; 16 completed inteiramente benignos. Somente quatro benignos têm a cadeia final elegível. Não são 16 baselines científicos intercambiáveis.

Na cadeia final Stage 9 há 20 runs: 18 completed/elegíveis e dois incomplete/inelegíveis, ambos dataset_valid=true. Um dataset manual adicional tem outro ID e proveniência registrada, mas não relatório final Stage 9 nem feature dataset final. Os 18 feature datasets principais usam Δ=1 s, totalizando 394 janelas; há uma extração adicional Δ=0,5 s do mesmo periodic. Cópias stage8-validation, stage10-validation e determinism não acrescentam runs. Diretórios históricos sem IDs não foram promovidos por nomes de arquivos.

As durações do inventário são planejadas; `events` em runs.json preserva início/fim efetivos, e feature_references.json distingue última observação, grid_end e padding. Exemplos: periodic efetivo [2,091676;13,507452), fresh [2,091430;13,507819). A grade de 16 s não comprova 16 s de observação. Esses tempos não devem ser substituídos pelos 2/13,5 s planejados.

## 2. Matriz de comparabilidade

Grupos: G3=stage3 A/B/C (host direto); G4=stage4 A/B/C (host + proxy); G4T=technical (duas vítimas); G5=stage5 A/B/C (containers + proxy); G6=light/medium/expensive; G7=continuous/periodic/capacity/multiple/fresh. A é benigno; B é ataque isolado, sem clientes benignos; C mistura ambos.

| Par/grupo | Baseline transferível? | Comparação defensável hoje | Bloqueio/condição |
|---|---|---|---|
| G3 A → G3 C | candidato para serviço/infra | demonstração exploratória | única seed; versão histórica desconhecida |
| G4 A → G4 C | candidato para serviço/infra | demonstração exploratória | mesmas limitações; rede indisponível |
| G5 A → G5 C | candidato nas três famílias | melhor par funcional disponível | um benigno, seed única, sem calibração normal independente |
| A → B de qualquer grupo | não para cenário normal carregado | ataque isolado como controle técnico | B tem zero sources benignas; idle não representa tráfego normal |
| G3 ↔ G4 | não automaticamente | efeito exploratório do proxy | caminho e latência mudam; médias benignas 16,09 vs 28,83 ms |
| G4 ↔ G5 | não automaticamente | efeito exploratório da execução | host/container e captura diferentes, mesmo com médias próximas |
| G4T ↔ G4 A | não | teste técnico de múltiplas vítimas | duas vítimas, 10 vs 30 s; CPU agregada diferente |
| G5 A → G6/G7 | não | somente comparação descritiva | `/` e 4×10 vs operações explícitas e 4×2 RPS |
| G6 light ↔ medium ↔ expensive | baseline separado | operação como fator explícito | carga computacional, CPU e duração muito diferentes |
| G7 periodic ↔ fresh | configuração nominal equivalente | repetição de execução e timing | mesma seed; não replicação independente de tráfego |
| G7 periodic ↔ capacity | não como réplicas | efeito da capacidade | max_concurrent_sends 64 vs 1 |
| G7 continuous ↔ periodic | não isola padrão | descrição de dois cenários | atacante `/light` vs `/expensive`, além do scheduler |
| G7 multiple ↔ periodic | não isola sources | descrição exploratória | quatro vs um atacante E `/light` vs `/expensive` |
| Δ=1 ↔ Δ=0,5 do periodic | não como réplicas | sensibilidade à resolução | mesma execução, contagens e dependência temporal diferentes |
| incomplete → qualquer teste | não | validação de recusa | falha operacional, sem features finais |

**Critério proposto:** criar uma chave de cenário normal com operação efetiva/URL e workload, fontes benignas e taxa por fonte, processo de chegadas, concorrência/timeouts, modo de execução, vítimas/recursos/pool, autoscaler, proxy/configuração/backends/conexões, serviço/imagem, coletor/poll/histórico/cache, segmento/parser da captura e Δ/alinhamento. Diferenças desconhecidas ficam desconhecidas; não presumir igualdade pela configuração parcial. Git/runtime, imagem Docker por digest, ambiente/limites e bloco de execução devem ser compatíveis ou fatores declarados.

Identidade literal de config não é necessária: seed, ID e parâmetros de ataque variam intencionalmente. Duração pode variar em análises específicas, mas estimativas de cauda, chance de falso alarme e atraso exigem exposições equivalentes ou denominadores explícitos. Histórico de execução não demonstra hardware/carga idênticos. Comparações entre detectores usam mesmos runs, feature, horizonte, budget de falso alarme e informação causal; comparação entre cenários deve ser estratificada. Não agregar todos os runs como amostras equivalentes.

## 3. Features: evidência, custo e missing data

| Feature candidata | Disponibilidade principal | Evidência descritiva | Coleta e tempo real |
|---|---|---|---|
| ingress_packet_count | 11/18 runs; 195 nulls de 394 | G5 A: 104,70±17,45 por janela normal; G5 C ataque pleno: 224,11 | parser/captura source→proxy; custo por pacote, inclui ACK/retransmissões |
| ingress_tcp_payload_length_sum_bytes | 11/18; mesmos 195 nulls | G5 A: 7876,27±1321,99 bytes; G5 C ataque pleno: 16441,11 | mesma captura; payload TCP registrado, não bytes físicos nem HTTP útil único |
| request_starts | 18/18; zero null | G5 A: 37,87±6,31; G5 C ataque pleno: 78,67. G7 periodic: 8,00±3,00 normal vs 8,50 ataque pleno | barato com instrumentação; hoje observação no cliente, exige fonte operacional equivalente em implantação |
| mean_duration_ms | 18/18 com observações; 67 nulls | G5 A: 29,32±2,76; G5 C ataque pleno: 34,81. G7 periodic: 17,35 vs 42,48 | disponível após conclusão; inclui erros/transporte/instrumentação, não apenas processamento |
| mean_cpu_percent | 18/18 com suporte parcial; 54 nulls | G5 A: 7,06±0,73; G5 C ataque pleno: 16,07. G6 expensive normal descritivo: um único sample, 203,42 | depende Docker/coletor; média de médias e cache, não CPU instantânea; pode superar 100% |

Médias normais desta seção usam janelas overlap=0 dentro do plano; nos ataques incluem pré e pós-evento, não uma amostra normal independente. Ataque pleno significa overlap=1; boundaries ficaram fora apenas desta estatística. Os valores não demonstram detectabilidade nem justificam escolher feature por F1. O baixo contraste médio do PeriodicBurst é coerente com silêncios dentro do evento global.

`unique_client_src_ips`: G5 A tem exatamente 4 em todas as 31 janelas, inclusive a cauda com packets. G5 C tem média 8 nas janelas de ataque pleno, pois IPs atacantes passam a transmitir. G7 periodic varia 2–5 no evento, média 3,8, contra 4 nas três janelas normais completas; não cresce monotonicamente. Inventário fixo não implica presença fixa por janela, especialmente com baixas taxas. Detecta também o artifício de ativar IPs novos, não necessariamente LDoS das mesmas sources. **Não incluir como candidata principal; manter diagnóstico.**

Não ampliar as cinco candidatas agora. Egress está disponível nos mesmos 11 runs, mas adiciona outra perspectiva muito dependente das respostas; completions é fortemente próximo de starts, embora útil depois para backlog; failures permanece zero nos 18 elegíveis; memória tem 54 nulls e pouca variação em benignos (G5 A: 22,134±0,084 MiB). Essas observações justificam adiar expansão, sem afirmar inutilidade universal.

Todas as candidatas são observáveis sem classe causal, mas latência/CPU têm atraso de disponibilidade. Telemetria em tempo real precisa preservar ordem de chegada/fechamento: a Etapa 10 é offline e não certifica latência de entrega online. Nenhuma feature pode incluir labels, ID de source atacante, status causal, attack_request_starts, manifest ou tempos do evento. Configuração é usada pelo orquestrador para validar comparabilidade, não como covariável oculta do detector.

**Recusa futura:** verificar hashes/schema, analysis_eligible, detector_columns e capacidade da representação. Rede não suportada → execução `(run,feature)` recusada com motivo `feature_unavailable`; não produzir score zero nem métrica artificial. Nos sete hosts isso afeta a família inteira, mesmo que o CSV exista.

Null intermitente → observação explicitamente ausente e score/decisão indisponível quando o método não puder operar. Não compactar o eixo temporal. Para CPU e duração, estimar baseline apenas dos samples observados, guardando exposição e contagens, sem afirmar missing at random. Cada método declara se pausa estado, faz apenas previsão temporal ou exige reinício após gaps; isso precisa de definição antes da implementação. Até lá, não atravessar gaps silenciosamente. Sem samples suficientes para estimar parâmetros → recusa. Nunca acrescentar epsilon ou imputar zero para fazer rodar.

Reportar cobertura por feature, fase e evento, além de métricas nas janelas válidas. Ausentes não são TN; também não devem desaparecer do relatório. Para comparações entre métodos, mostrar cobertura comum e cobertura nativa, com denominadores. Buracos/warm-up contam como falta de serviço no relatório operacional; uma análise de sensibilidade conservadora pode tratar ausência durante ataque como não detecção, identificada separadamente. Não remover janelas difíceis com base em labels.

## 4. Baseline normal

Runs benignos independentes são preferíveis à divisão automática dos primeiros X% de cada teste. Eliminam o pressuposto de que todo run começa estacionário e normal, e deixam o teste inteiro sem ajuste. Prefixo normal de teste pode futuramente servir como contexto causal de estado, mas não para ajustar média/variância, parâmetros ou threshold; uma variante adaptativa exige protocolo próprio, sem usar labels e separada da referência congelada.

Baseline é específico por **feature + representação + Δ + cenário/operação**. Não reutilizar CPU de `/light` em `/expensive`; não misturar 4×10 e 4×2 RPS. Persistir parâmetros, amostras/exposições, exclusões por suporte, estimador e referências por hash. Não concatenar finais e inícios de runs como se fossem uma sequência contínua.

Precisam de referência normal para a proposta de detecção: Z-score (μ, σ); EWMA/CUSUM (centro, escala, inicialização); Hellinger (distribuição de referência); prediction interval/Holt/Kalman (modelo/resíduos/incerteza); GLR (modelo nulo e alternativas). CoV, Shannon/Rényi, autocorrelação, FFT/DWT podem calcular estatísticas descritivas sem treino, mas precisam definir o que é desvio normal para produzir detecção comparável. Page-Hinkley pode estimar média online; ainda exige inicialização e calibração de falso alarme. Nada autoriza aprender normalidade com todo o teste.

Atualmente existem quatro benignos elegíveis: G3 A, G4 A, G4 technical e G5 A. São quatro estratos, um run por estrato, todos seed 42. Para rede há apenas G5 A; para G7 nenhum benigno equivalente. Os 16 benignos completed ampliados são desenvolvimento, sem cadeia final para a maior parte, mesma seed e ambientes distintos. Poderiam alimentar auditoria futura/piloto, mas não resolvem as lacunas atuais. **Insuficiente para baseline/calibração/teste independentes e incerteza entre seeds.**

Um único benigno aprende peculiaridades da seed, startup, scheduling e host. Precisaremos de múltiplos runs normais com seeds distintas e repetições em blocos de execução. Quantidade e duração serão determinadas pelo piloto e precisão desejada; não há número científico dedutível destes dados. Startup/estabilização deve ter regra operacional observável previamente definida, sem consultar score ou label; não importar um descarte arbitrário dos primeiros segundos. As médias recentes/cache do coletor exigem investigar estabilização e recuperação.

## 5. Calibration

Calibração recebe modelo já ajustado e dados independentes para escolher configuração permitida e política de decisão. Teste permanece inacessível para escolha. Se hiperparâmetros do detector mudarem, registrar cada candidato e sua referência de treino. Muitos candidatos sobre pouca calibração causam sobreajuste mesmo sem ataque; restringir grade e, se necessário, dividir a calibração entre escolha e confirmação normal.

| Alternativa | Papel e vantagem | Risco/condição |
|---|---|---|
| Quantil dos scores normais de calibração | threshold empírico para taxa nominal de excedência | pouco suporte de cauda, empates, dependência e drift; quantil não garante FPR futuro |
| Quantil só do baseline | possível regra pré-especificada | score in-sample pode ser otimista; preferir calibração separada ou ajuste fora de amostra no treino |
| Controle de FPR em normal independente | comparar métodos com mesmo orçamento operacional | FPR por janela não controla episódios/hora nem ARL de métodos acumulativos |
| Limite derivado do método | interpretação estatística e menor busca | hipóteses de distribuição/independência podem falhar em contagens e CPU com cache |
| Parâmetros de literatura | referência replicável | transportar valores entre escalas, Δ e processos não garante desempenho |

Proponho como campanha inicial **calibração somente normal**, com orçamento de falso alarme e unidade operacional definidos antes do teste, além de FPR window-level. Não fixar agora quantil, α, limite σ, memória, drift ou persistência. Se exposição não permitir certificar um orçamento baixo, declarar insuficiência; zero alarmes em poucos segundos não prova FPR zero. Relatar incerteza por run/bloco e duração de normal observada.

Calibração com ataques é defensável numa experiência explicitamente supervisionada/semissupervisionada: escolher threshold ou memória com ataques de desenvolvimento separados por run/seed e cenário, testar em ataques nunca usados e declarar quais famílias/intensidades foram conhecidas. Isso muda a pergunta científica e pode especializar o método nos bursts conhecidos. Não misturar esse resultado com a referência calibrada só em normal. Dados atuais já inspecionados podem ser desenvolvimento, nunca teste confirmatório retroativo.

A referência NIST descreve EWMA com informação histórica e contrasta sua memória com a decisão pontual de Shewhart; limites dependem das hipóteses do processo. Não adotar defaults como garantias para esta telemetria. [NIST EWMA](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc314.htm).

## 6. Teste, seeds e desenho da campanha

Separar conjuntos de IDs/seeds de baseline, calibração e teste; aliases/extrações do mesmo run permanecem no mesmo conjunto. Seeds por source são derivadas do seed mestre, não réplicas independentes. Reservar teste antes de coletar/analisar seus resultados; usar labels de teste apenas no evaluator. Conhecer a operação planejada é permitido; escolher parâmetros com sua resposta observada ao ataque não.

Teste deve conter benignos completos independentes, ContinuousFlood e PeriodicBurst comparáveis e, depois, famílias mais realistas. Prefixos normais dos ataques medem FPs no contexto de teste, mas não substituem benignos completos. Pós-evento mede também recuperação/backlog: pelo ground truth aprovado é normal, embora possa conter consequências do ataque; reportar FPR pré/pós e benignos completos separadamente. Não prolongar labels até a última conclusão.

**Campanha enxuta proposta:** começar com cenário fixo em containers, proxy, uma vítima, autoscaling desligado, operação benigna e carga normal fixas. Usar benigno/contínuo/periódico como fator principal. Para comparar padrões, manter operação atacante, sources, limite de capacidade e RPS por source iguais; declarar que duty cycle altera carga média. Um contraste posterior pode igualar carga média como pergunta diferente. Nenhuma taxa nominal garante inícios realizados.

Escolher primeiro uma operação com justificativa de pesquisa, antes dos resultados de detecção; `/light` oferece continuidade com os testes de padrão, mas exige benignos novos. Medium/expensive entram como extensão bloqueada por operação, cada uma com seu baseline, sem cruzar inicialmente todas as intensidades e source counts. Selecionar faixa reduzida de intensidade por piloto de carga/capacidade observável, não por maximização do F1. Variação de número de sources e capacidade entra em estudo posterior, um fator por vez ou desenho fracionado justificado. Ataques isolados são controles auxiliares, não cenário principal.

Cada run precisa de pré/durante/pós. Pré: inicialização causal e FPs; durante: múltiplos ciclos suficientes para métodos com memória/periodicidade; pós: recuperação e alarmes residuais. Duração deve considerar maior lookback previsto, Δ, periodicidade e memória do coletor, além de exposição necessária para falsos alarmes. Os dois segundos pré-ataque de G7 não bastam para baseline CPU: as duas primeiras janelas não têm suporte. Fixar uma regra de horizonte comum, sem usar scores para encerrar runs. Por ora, não inferir observação garantida de zeros ou do último timestamp; não pontuar padding como benigno certificado. Manter cauda completa no dataset e reportá-la separadamente com a política futura de elegibilidade temporal.

**Repetições:** piloto com novas seeds normais e de ataques, preservado como desenvolvimento. Medir variabilidade de chegadas realizadas, capacidade, métricas por run, atraso/misses, duração e custo total (startup/teardown/captura/armazenamento). Reexecuções da mesma seed em blocos de host/horário estimam variabilidade de sistema, separadamente da de tráfego. Não executar cenários simultaneamente no mesmo host como se fossem réplicas independentes; randomizar ordem e bloquear condições de execução.

Definir previamente endpoints principais e margem de precisão desejada. Usar dispersão do piloto para planejar repetições: para uma média, n aproximado ∝ (quantil × desvio / semi-amplitude desejada)² serve como planejamento inicial, não garantia para dados dependentes ou proporções raras. Para taxa de detecção e falsos alarmes raros, dimensionar eventos/exposição com intervalos apropriados; para atraso, considerar censura. Rever custo e viabilidade antes de congelar n na Etapa 13. Não parar opcionalmente quando surgir significância; eventual regra sequencial exige desenho próprio.

Reportar média, desvio entre runs, mediana/IQR quando assimétrico e IC. Bootstrap por run ou bloco preserva séries completas; não reamostrar janelas correlacionadas como independentes. Para comparação de detectores, usar diferenças pareadas nos mesmos testes. Em cenários pareados por seed, manter o bloco no reamostramento; compartilhar seed entre baseline/calibração/teste não é o pareamento desejado. Métricas macro por cenário/run como síntese principal; contagens micro adicionais com peso explícito. Uma seed única não permite IC da variabilidade entre seeds.

## 7. Unidade window-level e boundaries

Seja W_k=[a_k,b_k), largura Δ; G a união dos eventos efetivos; q_k=|W_k∩G|/Δ. O detector produz score s_k e decisão d_k∈{0,1} ou indisponível. Seja V o conjunto de janelas válidas pela política prévia de suporte/horizonte/warm-up; V não depende do score nem da conveniência do resultado.

Alternativas de binarização: qualquer overlap (q>0) conserva todas as fronteiras, mas cobra ataque por fração mínima; maioria (q>1/2 ou ≥1/2, desempate deve ser explícito) reduz essa cobrança, porém converte ataque parcial em normal; excluir 0<q<1 evita esse limiar, mas perde informação e pode eliminar eventos curtos; ponderar usa a fração completa sem inventar classe.

**Recomendação futura:** matriz binária principal nas janelas puras (q=0 ou 1), sem threshold de overlap. Publicar quantidade/duração excluída e usar avaliação temporal ponderada complementar para incluir boundaries. Eventos curtos sem janelas puras ficam explicitamente sem estimativa binária de recall, ainda avaliados em event-level. Comparação de sensibilidade com qualquer overlap/maioria somente se pré-registrada, sem escolher a que favorece o resultado.

Nas janelas puras válidas, y=q: TP=Σdy, FP=Σd(1−y), FN=Σ(1−d)y, TN=Σ(1−d)(1−y). Precision=TP/(TP+FP), Recall=TP/(TP+FN), F1=2TP/(2TP+FP+FN), FPR=FP/(FP+TN). Denominador zero → indefinido com motivo, não zero/um inventado. Accuracy pode ser secundária, sempre com prevalência e confusão. Não preencher todo evento como positivo porque houve um acerto.

Complemento fracionário: TP_t=Σd|W∩G|, FP_t=Σd|W\G|, FN_t=Σ(1−d)|W∩G|, TN_t=Σ(1−d)|W\G|, restrito ao horizonte válido. Unidades são segundos, não contagens binárias. Isso mede coincidência da decisão **atribuída à janela**, retrospectivamente; não afirma que o alarme estava disponível no início daquela janela.

False-positive windows por hora normal = FP/(T_normal/3600); é diferente de episódios falsos por hora. Definir episódio como sequência máxima de decisões positivas adjacentes válidas, sem unir gaps nem adicionar hysteresis. Episódio que começa antes de ataque é alarme antecipado/falso, não crédito retroativo. Reportar também duração positiva fora de eventos, para um alarme longo não parecer excelente por contar como um episódio. Alarmes que atravessam fim de evento têm extensão pós-evento reportada, mesmo sem novo episódio.

## 8. Event-level, delay e continuidade

Para evento E_j=[u_j,v_j), usar u_j=actual_start e v_j=actual_end. Score só usa observações até seu timestamp de evidência. Se a janela fecha em b_k, a decisão não está disponível em a_k: registrar `available_at` ≥ b_k e eventual custo de processamento. Offline pode assumir b_k como instante simulado de decisão, identificando que não mede latência de implantação.

Definir **decisão positiva válida** para detecção como novo resultado d_k=1 cuja janela intersecte E_j com duração positiva e cujo available_at esteja em [u_j,v_j). Assim evita creditar score inteiramente pré-ataque que só chegou depois. Primeira decisão t*_j é o mínimo desses instantes; evento detectado se esse conjunto não for vazio. Delay_j=t*_j−u_j. Nunca usar início da janela como alarme e nunca reportar atraso negativo.

Uma janela que começa antes de u e termina depois de u pode detectar, mas apenas no fechamento; a resolução impõe atraso de até Δ até o primeiro fechamento, além do lookback/processamento. Se fecha após v, classificar como reconhecimento tardio associado ao evento, separado da detecção durante evento. Isso afeta eventos menores que Δ e deve aparecer como limitação, não label reescrito.

Alarme prévio não é primeira detecção do evento. Se a política só mantém um estado alarmado desde antes, esse estado não ganha novo início em u. Para a política simples por janela, uma nova decisão após u pode ser positiva e contar, mas relatar `preexisting_alarm` e taxa de alarmes pré-evento; um detector sempre positivo terá recall alto e falsa-alarmística péssima. Análise estrita de novo episódio pós-início pode ser secundária pré-registrada; não introduzir uma regra de reset usando labels.

Nunca detectado: `detected=false`, delay ausente e tempo até fim do evento como limite de censura, não delay=0 nem exclusão silenciosa. Reportar recall de eventos, distribuição de atraso entre detectados COM número de misses e, com volume suficiente, curva de tempo até detecção com censura no fim. Não comparar apenas média dos detectados, pois isso favorece quem perde os difíceis. `drained_end` não desloca u/v.

Cobertura atribuída ao evento: C_j=Σd_k|W_k∩E_j|/|E_j|, com duração indisponível reportada separadamente e versão condicional em suporte, se usada. Continuidade: maior intervalo positivo contíguo dentro do evento, número de interrupções e maior lacuna sem decisão positiva; declarar se lacuna é negativa ou indisponível. Para cobertura **operacional**, usar os intervalos de validade após available_at, por exemplo [t_k,t_{k+1}) com decisão anterior, truncados ao evento; não retroagir a decisão para a janela usada no cálculo. Gaps invalidam a continuidade segundo contrato explícito, nunca carregamento ilimitado silencioso.

Não exigir N janelas positivas, hysteresis ou timeout de alarme nesta etapa. Persistência futura é política adicional calibrada fora do teste, com atraso próprio e comparação separada. Eventos sobrepostos preservam IDs para relato; métricas window-level usam união. Sem separação temporal não é identificável qual evento causou um alarme: avaliar cluster unido para detecção e marcar ambiguidade, evitando duplicação de créditos.

A distinção entre ponto e intervalo tem respaldo em [Tatbul et al., Precision and Recall for Time Series](https://arxiv.org/abs/1803.03639). A crítica a transformar um acerto em acerto de todo intervalo aparece em [Kim et al., Towards a Rigorous Evaluation](https://ojs.aaai.org/index.php/AAAI/article/view/20680). Aqui não se adota point adjustment.

## 9. PeriodicBurst

Ground truth principal permanece o evento global, inclusive silêncios. Não criar burst_active nem redefinir attack_active. Usar calendário configurado do scheduler apenas em análise pós-hoc, separado dos labels principais, para recortar fases programadas de emissão/silêncio; alinhar ao relógio/âncora planejados do padrão, não deslocar bursts para actual_start. Restringir cortes ao evento efetivo. Se houver journals, confrontar calendário com evidência realizada; calendário não prova que houve request em todo burst.

Reportar: trajetória e dispersão do score por fase; fração de decisões positivas nas fases programadas de emissão e silêncio; primeira detecção global; bursts programados já transcorridos até ela; cobertura/maior lacuna do evento; evolução do estado acumulado, quando exposto como diagnóstico. `attack_request_starts` serve exclusivamente para sobrepor atividade realizada pós-hoc, nunca como entrada nem para selecionar threshold ou redefinir verdade. Zero starts não prova ausência de efeito: há conclusões durante silêncio.

No exemplo periodic, [6,7) e [12,13) têm zero starts atacantes, overlap global 1 e conclusões atacantes; o score pode persistir devido ao efeito do serviço, cache ou memória do método. Distinguir essas explicações, sem presumir causalidade só pela coincidência temporal. Os 25 inícios com seed 42 não representam 10 requisições por segundo determinísticas. Capacidade=1 realiza 13; mudar capacidade muda também a carga efetiva.

Z-score pontual e CUSUM acumulativo recebem a mesma feature, relógio, suporte e dados históricos permitidos; calibração compara orçamento normal equivalente e reporta episódios/hora e FPR. Resets apenas em limites de run ou regra declarada do método; nunca no início/fim conhecido de ataques ou bursts. Não exigir que todo método mantenha alarme no silêncio como condição para receber crédito de detecção do evento; reportar separadamente detecção, continuidade e fases. Também não conceder cobertura total a um único disparo. Memória, lookback e custo/latência são características explícitas de cada método, sem dar a FFT acesso ao futuro ou apagar a memória do CUSUM a cada burst.

## 10. Requisitos dos 15 métodos

As famílias admitem variantes; esta tabela não congela uma fórmula inexistente. “Baseline” indica o papel na detecção proposta, não necessidade para calcular uma estatística isolada.

| Método | Entrada/representação mínima | Histórico/estado | Baseline possível | Calibração pendente |
|---|---|---|---|---|
| Z-score | escalar por janela | pontual na versão inicial | média/desvio da feature | cauda, orientação, threshold |
| CoV | sequência de escala de razão | buffer móvel de valores | distribuição normal do CoV por lookback | lookback, domínio próximo de zero, limiar |
| EWMA | escalar | média exponencial/estado | centro, escala, inicialização | peso e limite |
| Shannon | distribuição categórica/histograma definido | por janela; histórico opcional | distribuição normal da entropia ou referência | categorias/bins, amostra mínima, orientação |
| Rényi | distribuição explícita | similar à Shannon | referência/estatística normal | ordem α e política de desvio |
| Hellinger | distribuição atual e referência, mesmo suporte | histograma/buffer se necessário | probabilidades de referência | categorias/bins e limiar de distância |
| Adaptive Threshold / Prediction Interval | escalar | histórico/modelo causal | nível, variância ou preditor/resíduos | algoritmo de adaptação, confiança e janela |
| DES/Holt | escalar | nível e tendência | inicialização/ajuste e resíduos | pesos e intervalo/score residual |
| CUSUM | escalar ou incremento de log-verossimilhança | soma acumulada/reset declarado | hipótese normal, centro/escala | drift, mudança alvo e limite |
| Page-Hinkley | escalar | média online e soma/extremo acumulado | inicialização normal opcional | tolerância de drift e limite |
| Autocorrelação | sequência regular | buffer de lags | correlações normais, se detecção por mudança | lags/lookback/estatística de desvio |
| DFT/FFT | sequência regular | buffer causal | espectro/picos normais | lookback, banda, score; resolução espectral |
| DWT | sequência regular | buffer/estado multiescala | energia/coefs normais | wavelet, nível, bordas e score |
| Kalman | escalar observado + modelo de estado | estimativa/covariância | dinâmica e ruídos/inicialização | Q/R, inovação e política de decisão |
| GLR | escalar/sequência e modelos probabilísticos | estatísticas suficientes/buffer de changepoint | hipótese nula e parâmetros | alternativa, tamanho de busca e limiar |

FFT e wavelets não são detectores completos só por existir transformação; é preciso definir score. Filtros centrados ou DWT offline com futuro não cabem numa execução causal sem declarar atraso. Distribuição é uma representação de um atributo, não combinação implícita das cinco features. O primeiro framework implementará apenas entrada escalar; deverá declarar capacidades para recusar os métodos que ainda exigem representação não suportada.

## 11. Z-score, CoV e Shannon

**Z-score:** propor versão inicial de referência fixa, z_k=(x_k−μ_B)/σ_B. Preservar score assinado; a política escolhe cauda superior, inferior ou bilateral fora do teste, por hipótese científica. Para duas caudas, transformação |z| deve ser explícita na política, sem perder o z original. μ/σ estimados somente no baseline comparável, por feature/Δ; registrar ddof, ponderação por run e validade. σ=0 é degenerescência, não autorização para dividir por epsilon; requer recusa/sem score segundo regra documentada. Contagens discretas, assimetria, dependência e CPU com cache impedem presumir normalidade ou limite universal “3σ”. O score não implica probabilidade normal calibrada. Não implementar agora.

**CoV:** CV=s_H/mean_H é estatística de uma amostra de valores, adimensional em escala de razão. Uma única média/contagem da Etapa 10 não fornece seu próprio desvio intrajanela. Portanto propor **histórico móvel causal de valores da mesma feature**, finalizado na janela atual ou somente passado, com convenção a definir e persistir. Não confundir Δ da observação com comprimento H do histórico. Não escolher H agora.

Com mean=0 o quociente é indefinido, inclusive 0/0 de tráfego ocioso; mean≈0 causa instabilidade; H pequeno aumenta incerteza; amostras esparsas podem dar CV alto por normalidade legítima. CV também pode cair quando um flood torna o tráfego mais uniforme: não assumir “maior sempre é ataque”. Definir domínio válido por unidade/precisão e suporte normal no piloto, sem epsilon arbitrário e sem remover valores extremos. G5 B antes do ataque tem starts=0 e nenhuma duração média: não serve de baseline de CV para tráfego benigno. Persistir n, estimador e motivo de indisponibilidade. Threshold deve ser calibrado na distribuição do CV, não copiado do Z-score.

**Shannon:** H(P)=−Σ p_i log p_i requer probabilidades de categorias definidas. Um escalar x_k não é automaticamente uma distribuição; não tratar as cinco features como categorias nem usar normalização ad hoc de valores para encaixar a interface. A formulação original trata explicitamente probabilidades de símbolos: [Shannon, A Mathematical Theory of Communication](https://www.mpi.nl/publications/item2383162/mathematical-theory-communication).

Etapa 10 **não preserva** frequências por IP ou histograma de tamanhos: contagem, soma e número de IPs distintos não recuperam a distribuição. Redes com mesmo count/soma/cardinalidade podem ter entropias diferentes. Os dados brutos nos runs com segmento source_proxy permitem propor contagens de packets por IP observável, ou bins de packet_length TCP por janela, com direção aprovada e sem classe atacante. Request logs permitem histograma de atributo observável (p.ex. duração após conclusão), mas endpoints homogêneos tendem a informação pequena e source_id causal não é substituto de IP observável. Não existe ligação packet↔request comprovada para construir categorias híbridas.

Propor futuramente artefato adicional de representação: `window × category/bin × count`, atributo/unidade/direção, categorias/bordas estáveis, contagem amostral, regras para categorias novas e janela vazia, hashes e versão. Bins, se aprendidos, apenas no treino; vocabulário de IP não pode incorporar antecipadamente IPs do teste via conhecimento causal do inventário. Endereço visto no próprio packet é observável; inventário conhecido operacionalmente precisa ter escopo explícito. Zero massa total significa distribuição não estimável, não entropia zero; um único símbolo observado tem entropia zero, mas baixo suporte. Tamanho amostral afeta viés/variância e deve ser auditado.

Outra pergunta legítima seria entropia de histograma de valores escalares em histórico móvel; isso mede variabilidade temporal discretizada, não diversidade de IPs dentro da janela. Só considerar após formular hipótese, lookback e bins; não adotá-la por conveniência. **Shannon deve permanecer pendente na Etapa 12** até definição e representação aprovadas. Essa expansão seria novo produto versionado, sem editar as séries/contratos atuais. Não há conflito que exija modificar Etapas 0–10; há insuficiência de representação para algumas famílias.

## 12. Interface mínima e artefatos da Etapa 11

Fluxo recomendado: `ObservableSeries → Detector → ScoreSeries → DecisionPolicy → DecisionSeries → Evaluator`. O orquestrador resolve manifests, comparabilidade e splits; o detector recebe apenas observações e parâmetros permitidos, sem labels de teste. Chaves/timestamps alinham dados e controlam causalidade, não entram como features numéricas.

Contrato conceitual, sem código implementado:

- `requirements`: tipo de entrada (`scalar_series` inicialmente; `distribution_series` reservado), suporte histórico mínimo, causalidade/latência, política de gaps e possibilidade de fit.
- `fit(baseline_observations, detector_config) → fitted_parameters`: opcional para estatísticas sem treino; nunca recebe labels de teste.
- `start_run(fitted_parameters) → state`; `update(observation, state) → score_record`: estado causal reiniciado por run; método pontual pode ter estado vazio. Buffer pertence ao método, sem impor formato de Z-score.
- `calibrate(calibration_scores, policy_config) → decision_parameters`: fora do detector; variante supervisionada identificada, separada da referência normal.
- `decide(score_record, decision_parameters) → decision_record`; `evaluate(decisions, labels, event_intervals, evaluation_plan) → report`: apenas evaluator recebe verdade do teste.

Score record: chaves da janela, score contínuo ou ausente, status/reason (missing/warm-up/degenerate), fim da evidência e available_at. Diagnósticos opcionais de estado sem virar automaticamente features. Decision record: mesma chave, decisão ou abstinência, referência da política/threshold e tempo de disponibilidade. Threshold pode ser constante, função temporal ou banda do modelo, sempre reconstituível e registrado; não forçar todos os métodos a limite fixo escalar. Fit não é obrigatório e score não é probabilidade por definição.

Manter poucos artefatos:

1. `protocol/split_manifest`: IDs/hashes e papel train/calibration/test, chave de cenário, exclusões e motivo, critérios de suporte/horizonte/boundary, endpoints, orçamento de alarme e plano de incerteza. Teste com acesso reservado até congelamento; nenhum artefato presente foi declarado teste cego.
2. `baseline_model`: feature/representação/Δ, parâmetros/estimadores/suporte, runs/hashes de treino, versão do método e runtime. Pode registrar que não há parâmetros treinados.
3. `calibration_manifest`: candidatos autorizados, scores normais referenciados, objetivo/regra de escolha, configuração escolhida, threshold/banda/política, hipóteses e incerteza. Sem labels de teste.
4. `detector_run_manifest` + `scores.csv` + `decisions.csv`: detector/versão/config, seed se aplicável, hashes de modelo/política/dataset/schema/séries, reset/gaps, causalidade e hashes das saídas.
5. `evaluation_report`: hash do plano, labels/eventos e decisões, confusão, métricas/denominadores/cobertura/misses/atrasos e sumários por run/cenário com incerteza. Versão do evaluator e parâmetros de agregação.

Não duplicar raw datasets nem criar registry complexo. SHA256 de artefato pode ficar no manifesto consumidor, evitando auto-hash circular. Persistir seed aleatória do método separada da seed do tráfego e registrar bibliotecas/ambiente/versão efetiva, inclusive arquivos dirty por hash. Dados atuais já têm arquivos com SHA/tamanho, schema, ID, hash de manifest Stage 8, report Stage 9 e extrator/proveniência Stage 10. Falta o vínculo novo de split/modelo/calibração/execução/avaliação, não um novo sistema de exportação. Hash garante identidade, não autenticidade, hardware equivalente ou proveniência histórica retroativa.

## 13. Ameaças à validade

Interna: operação/capacidade/source count confundidos; workload efetivo depende da rota (valores de configuração não garantem custo igual); host/proxy/container mudam latência; cache de CPU e recuperação contaminam interpretação causal; captura potencialmente parcial e relógios distintos. Burst programado, request admitida/iniciada e efeito no serviço não são equivalentes.

Estatística: seed única; poucos eventos e segundos normais; autocorrelação; janelas sobrepostas de detector; pseudo-replicação de cópias; múltiplas tentativas de parâmetros/features; raridade de falso alarme; viés de calcular atraso apenas nos detectados. Não generalizar médias intrarrun para incerteza entre runs.

Construto: evento global inclui silêncio; método que percebe bursts pode ter recall temporal global baixo sem ser inútil. “Bytes” é payload TCP registrado; duração é cliente; CPU média contém histórico/cache; zeros não certificam ausência física; missingness pode depender do desenho. Não chamar score contínuo de evidência de degradação sem análise específica.

Externa/reprodutibilidade: uma infraestrutura local fixa, sources sintéticas, sem autoscaling, poucos perfis; `/expensive` pode já saturar serviço benignamente. Proveniência dos 17 históricos desconhecida; fresh dirty tem fingerprint, mas não significa versão publicada limpa. Teste já explorado não se torna cego mediante renomeação.

## 14. Decisões para congelar e pendências

**Podem ser congelados como contratos da Etapa 11:** execução univariada explícita; somente detector_columns; nenhuma label no detector; scores preservados; separação treino/calibração/teste por run; aliases agrupados; sem ajuste no teste; cenário/feature/Δ como identidade de baseline; missing explícito e recusa de feature indisponível; estados causais/reset por run; ground truth global intacto; window/event separados; disponibilidade temporal registrada; parâmetros/manifests auditáveis; nenhuma persistência implícita; Shannon condicionado à representação.

**Recomendações a ratificar na Etapa 13:** treino e calibração normais independentes; janelas puras como confusão binária principal com complemento ponderado; delay baseado no fechamento/available_at e detecção durante evento; estatística macro por cenário com comparações pareadas; campanha C com acervo atual dedicado a desenvolvimento.

**Exigem evidência/piloto:** quantidade de seeds/runs e duração/exposição; estabilização do coletor e horizonte elegível; alvo de falso alarme; direção da decisão por feature; thresholds; lookbacks e atualização/reset em gaps; baseline degenerado; ponderação de runs no fit; suporte mínimo; operação/intensidades iniciais; definição de distribuição Shannon/Rényi/Hellinger; parâmetros de modelos e critérios de continuidade operacional. Não há evidência para congelar números agora.

Sequência proposta: Etapa 11 implementa contratos/artefatos e valida recusas/causalidade sem impor algoritmo universal; Etapa 12 adiciona Z-score e CoV, Shannon apenas se resolvido; Etapa 13 fecha protocolo com piloto de desenvolvimento separado e regras prévias de precisão; Etapa 14 executa campanha congelada; Etapa 15 amplia métodos e só depois complexidade de ambiente. Nenhuma dessas execuções/implementações foi realizada neste diagnóstico.
