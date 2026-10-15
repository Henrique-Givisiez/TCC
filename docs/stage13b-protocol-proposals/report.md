# Etapa 13B — alternativas de protocolo experimental

**Estado: proposta para decisão do usuário. Nenhuma alternativa aprovada ou executada.** Esta etapa somente conferiu evidências e calculou projeções. Não há alteração nas Etapas 0–13, nos seus outputs, em detectores ou políticas, nem commit. Os números abaixo não são parâmetros finais escolhidos para o TCC.

**Recomendação para discussão: alternativa B, equilibrada**, com 6 seeds de baseline, 12 de calibração e 16 de teste, 66 runs e aproximadamente 3,8 h de execução/processamento. O orçamento de falso alarme e as extensões mínimas de fitting/avaliação precisam ser resolvidos antes da Etapa 14. Se o objetivo incluir certificar alarmes raros por hora, essa alternativa exigirá mais exposição normal do que a matriz base oferece.

## 1. Evidências conferidas e seus limites

Foram lidos `docs/stage13-pilot/{design,results,interpretation}.md`, os custos individuais, os manifests/relatórios dos 15 runs, os sumários descritivos e `completion.json`. A conferência nesta etapa verificou **1.520 entradas de arquivos nos manifests Stage 8/10**, com SHA256/tamanho, sem divergência. Fontes e hashes em [evidence_verification.json](evidence_verification.json).

| Evidência real | Valor conferido | O que sustenta |
|---|---:|---|
| Runs/eligibilidade | 15/15 completed e elegíveis | Viabilidade funcional deste cenário |
| Requests com outcome de falha | 0 nos 15 runs | Ausência de falha observada, não degradação ausente em qualquer carga |
| Tempo nominal | 1.260 s = 21 min | 15 ×84 s |
| Execução + Stage 8–10 | 1.475,4535 s = 24,5909 min | ≈98,36 s/run nesta duração |
| Primeiro início → último fim | 1.563,5609 s = 26,0593 min | Inclui pausas; não é o mesmo custo anterior |
| Snapshot final de outputs | 125.380.671 bytes ≈119,572 MiB | Inclui derivados; não apenas datasets |
| Modelos/scores | 30 baselines e 345 score artifacts | Exercício do framework; não 345 réplicas |
| PRE de CPU, CoV L12 | 11 scores válidos | Aquecimento possível, poucos scores pré-evento |
| Média benigna entre seeds | dispersão relativa 4,47%–6,60% | Variabilidade de **médias por run no plano completo** |
| Dispersão de σ entre baselines | até 10,92% em CPU | Um benigno isolado pode alterar a escala |
| Efeito da cauda em starts | μ≈−1,15%; σ≈+3,50% | Fitting precisa de horizonte explícito |

Importante: a tabela de `results.md` referente à região [24,60) tem dispersões diferentes. O intervalo de 4,5%–6,6% vem de `analysis/between_seeds.csv`, linhas B/FULL_PLANNED. Não se deve transferir essa variabilidade para qualquer fase ou endpoint.

As cinco médias benignas no plano completo foram: packets 19,529±1,289 records/janela; payload 1607,667±72,821 bytes/janela; starts 8,202±0,372/janela; duração 33,962±1,518 ms; CPU 18,514±0,949 pontos percentuais. São médias de agregados Stage 10, não necessariamente médias ponderadas por request ou tempo de amostragem do Docker.

**Sustentado:** `/medium` funcionou sem saturação extrema observada; operação/carga nominal/imagens foram controladas; houve seis bursts realizados por periódico; POST permite ver memória; missing de CPU e cauda são materialmente relevantes; baselines variam; mesma seed não garante contagens idênticas; duração e memória mudam o que CoV mede.

**Ainda hipótese:** estacionariedade; estabilidade de caudas; eficácia contra LDoS; generalização a outras cargas/máquinas; número suficiente de seeds; FPR raro alcançável; superioridade de método/feature/L; recuperação universal em 24 s. Cinco seeds num único bloco de máquina não demonstram essas propriedades.

## 2. Pergunta e escopo da campanha inicial

Pergunta proposta: **como métodos univariados se comportam, em dados independentes, diante de eventos contínuos e periódicos controlados, sob um orçamento de falso alarme previamente declarado?** Separar detecção global, cobertura temporal, atraso, comportamento em silêncio e falsos alarmes normais. Não definir sucesso apenas por Accuracy.

Manter `/medium`, benignos 4×2 RPS, um atacante ×8 RPS durante atividade, containers, NGINX, uma vítima, pool 2, 64 send workers por classe, timeout 2 s, autoscaling desligado, monitoramento/poll configurados em 1 s e Δ=1 s. Fixar código e IDs/digests das imagens, redes, proxy, recursos e configuração de serviço; registrar kernel, carga/condições da máquina e bloco de execução. Não executar runs simultaneamente no host.

São contrastes dos **perfis existentes**: ContinuousFlood conserva fila; PeriodicBurst conserva admissão limitada e deadlines. Mesma taxa durante atividade não iguala volume médio. Não chamar qualquer diferença de efeito puro da periodicidade. Não alterar esses mecanismos para fazer uma comparação aparentemente mais limpa.

## 3. Horizonte explícito de fitting — extensão proposta, não implementada

A série Stage 10 permanece inteira, incluindo cauda. Propor um artefato de seleção observacional, consumido somente pelo fitting, com `fit_interval=[a,b)` por run e seleção de **janelas integralmente contidas**: `window_start>=a` e `window_end<=b`. Nas opções abaixo, a/b são alinhados a Δ. Não fracionar médias ou counts de janelas cortadas; se forem permitidos limites não alinhados no futuro, registrar essas janelas como excluídas por corte, sem rateio fictício.

| Possibilidade | Avaliação |
|---|---|
| Todo [0,T_planejado) de um benigno independente | Defensável se o objetivo inclui startup; exclui cauda, mas mistura transiente inicial e regime posterior |
| Somente PRE do próprio atacado | Não adotar para fitting principal: dependência do próprio teste e pouco suporte; PRE serve como contexto causal de estado |
| PRE de um benigno independente | Possível, mas desperdiça observação e concentra startup; não é a opção recomendada |
| Benigno independente com burn-in fixo e fim planejado | **Recomendado:** `[P,T_B)`; P é o PRE proposto para a opção, fixado antes dos dados, não escolhido pelo score |
| Horizonte escolhido depois por “trecho estável” | Recusar na análise principal sem regra observacional prévia; permite seleção conveniente de dados |

Intervalos recomendados de treino: A `[36,120)`; B `[48,240)`; C `[72,300)`. Cada run é inteiramente benigno. A exclusão inicial é uma definição explícita do estimando em regime posterior, não remoção de outliers. Startup é preservado e reportado separadamente. Não afirma que P segundos garantem estacionariedade.

O baseline artifact deverá registrar, por fonte: IDs/hashes originais, intervalo solicitado/realizado, regra de inclusão, lista de índices selecionados ou seu arquivo/hash, quantidade de janelas dentro/fora, n válidos/null, suporte por feature e motivo de exclusões. Registrar também feature/Δ/schema, estimador/ddof/ponderação, μ/σ, config e proveniência da seleção e do fitter. A máscara é temporal/observacional, nunca baseada em labels ou magnitude do score. Detectores/fitter não recebem ground truth.

**Cauda:** fica no dataset e em diagnósticos, mas fora de `[P,T_B)`. O scoring pode preservar toda a série; o evaluator restringe métricas principais a janelas dentro do horizonte planejado. Janelas finais com padding não entram como benigno comprovado. Conclusões após T são evidência de cauda, não justificativa para prolongar labels.

**Warm-up:** transiente físico de startup e warm-up algorítmico são coisas diferentes. Z-score ajusta somente o intervalo declarado. CoV recebe PRE para aquecer estado, sem fitting estático; janelas anteriores à disponibilidade continuam ausentes, sem zeros. Não reiniciar estado em attack_start/actual_end.

**Null:** exclusão explícita e contada no fitting, conforme método existente; não imputar. Nulos de teste/calibração mantêm razão/cobertura; CoV exige L consecutivos válidos. Não compactar o eixo temporal.

**Suporte parcial:** janela dentro do plano não prova cobertura física completa. Stage 10 aceita médias com pelo menos um sample suportado e não garante frescor de cache; spans no manifest têm completeness=not_proven. Manter essa semântica explícita, sem transformar suporte parcial em completo ou ponderação temporal inventada. Se quisermos um número mínimo de amostras por média ou garantia adicional de cobertura, será necessário outro contrato observacional verificado — não inferi-lo dos agregados atuais. Counts zero não comprovam captura completa.

**Bloqueio atual:** `fit_baseline` registra as fontes inteiras e não declara seleção temporal. Não basta substituir silenciosamente `ObservedSeries.observations` por uma fatia mantendo a referência de dataset completo. É necessária uma extensão pequena, versionada e autorizada de seleção/manifest antes do fitting científico; nenhuma foi feita nesta etapa e Stage 10 não precisa mudar.

## 4. Construção do baseline

| Abordagem | Estabilidade/generalização | Leakage e interpretação | Recomendação |
|---|---|---|---|
| Modelo por benigno | Expõe dispersão de μ/σ; pode aprender peculiaridade da seed/host | Se cada teste receber o modelo que melhor funciona, há seleção; se pareado por mesma seed, dependência | Análise de sensibilidade do treino, sem escolher “melhor baseline” no teste |
| Agrupado entre benignos independentes | Mais suporte e inclui variação entre execuções; não elimina drift | Modelo único por feature/cenário/Δ, com pesos auditáveis | **Principal nas três opções** |
| Benigno pareado da mesma seed do teste | Controla a trajetória nominal de tráfego | Seeds derivadas podem repetir padrões e tornar o teste mais fácil; é outra pergunta, condicionada à seed conhecida | Não usar como principal; eventual estudo secundário explicitamente separado |

O baseline agrupado ajusta **Z-score**. CoV mantém histórico local, sem fitting estático; seus scores normais entram apenas na calibração da política.

Recomendar pooling por observação válida com **mesma duração/intervalo nominal por run** e declaração dos n efetivos. É o estimador existente; não fazer média das sigmas. Para n_j, média m_j e desvio s_j de cada run, o agrupamento corresponde a:

`μ = Σ n_j m_j / N`

`s² = [Σ(n_j−1)s_j² + Σn_j(m_j−μ)²]/(N−1)`.

Assim a variância entre runs também entra. Missing variável muda os pesos efetivos; registrar e avaliar dominância de alguma fonte, sem descartar seeds por parâmetros inconvenientes. Usar leave-one-run-out **apenas no treino** para diagnosticar sensibilidade de μ/σ, sem escolher o modelo que recebe melhor F1. Baseline específico por feature, operação, topologia e Δ. Rejeitar n insuficiente ou σ=0 conforme Etapa 12; não aplicar epsilon.

## 5. Divisão física/lógica e ordem de acesso

Todos os IDs de seeds abaixo são **reservas propostas**, não configs executáveis criadas. São novos e disjuntos do histórico/piloto. Cada seed de treino/calibração gera somente B. Cada seed de teste gera B/C/P (e P2 apenas na opção C). Parear cenários **dentro do teste**, nunca seed de treino com teste.

Ordem proposta: aprovação deste protocolo → preparação autorizada dos contratos mínimos → coleta/ajuste baseline → coleta calibration-fit → threshold → calibration-confirm → congelamento dos artefatos exatos → **somente então gerar e liberar TEST**. Um plano de seeds não é acesso aos dados. Teste não é usado para features, L, caudas, direção, parâmetros, horizonte ou threshold.

Dentro de cada papel, distribuir seeds em blocos temporais e permutar cenários de teste de forma balanceada, com agenda e RNG de ordenação independentes dos detectores. Registrar condições do host; alterações de infraestrutura que afetem comparabilidade bloqueiam continuação. Separação cronológica treino→teste pode introduzir drift; normal de teste mede essa generalização. Não corrigir drift consultando resultados do teste.

Falhas/completude/missing excessivo têm critérios operacionais pré-definidos, independentes de score/labels de detecção. Preservar runs falhos e denominadores planejados; qualquer política de retry exige registro, limite e regra antes da coleta. Não substituir seed ou excluir run porque a detecção foi baixa. Burst com poucas requests é variabilidade realizada, não motivo automático para descartar.

## 6. Papel da calibração e políticas propostas

| Variante | Vantagem | Risco | Uso proposto |
|---|---|---|---|
| Somente normal | Comparação com mesmo orçamento de falso alarme, sem otimizar para C/P conhecidos | Pode não ser sensível a certos ataques; caudas exigem exposição | **Referência principal em A/B/C** |
| Normal + ataques conhecidos | Permite ajustar sensibilidade/latência sob restrição de FP | Especializa método, L e direção nos ataques vistos; modifica pergunta científica | Estudo supervisionado futuro separado, nunca substituir silenciosamente a referência normal |

Uma calibração mista seria defensável com seeds disjuntas de teste, famílias conhecidas declaradas, função de custo e orçamento de busca iguais por método, e teste incluindo padrão não visto. Não é evidência de detecção genérica de ataques desconhecidos. Não recomendo pagar agora essa dimensão; as quantidades/custos das opções contam calibração **somente benigna**.

Dividir calibração em **calibration-fit e calibration-confirm, com seeds disjuntas**, metade para cada. Fit estima limites normais segundo regra única pré-registrada. Confirm testa orçamento e cobertura sem reajustar limites. Se falhar, registrar insuficiência; qualquer revisão retorna a desenvolvimento e exige nova confirmação independente. Não tentar vários thresholds até “passar” na mesma confirmação e não abrir TEST como desempate.

### Estratégias para threshold

- **Z-score teórico/convenção:** serve como referência bibliográfica se hipóteses forem explicitadas; parâmetros estimados, contagens e dependência temporal não dão automaticamente N(0,1). Não adotar |z|>3 por tradição.
- **Quantis empíricos:** estimar limites da distribuição dos scores normais em calibration-fit. Preservar z assinado; política decide cauda. Para CoV, usar sua própria distribuição normal por feature/L; não compartilhar threshold com Z-score.
- **Média+kσ dos scores normais:** alternativa com k pré-especificado ou escolhido só em calibração; assimetria e caudas podem tornar limite inadequado. Não fazer concurso de famílias de threshold no teste.
- **FPR alvo:** definir antes da calibração `α*` por janela válida e, se operacionalmente necessário, `λ*` de episódios/hora. Escolher quantis conservadores e confirmar a política em normal independente; excedência empírica não é garantia futura.

**Default proposto para as três opções:** quantis normais com caudas iguais e regra determinística de empates/comparadores, calibrados por par detector-feature (e L secundário). `α*` e eventual `λ*` **não foram escolhidos nesta etapa**: exigem objetivo/aceitação do usuário e são bloqueadores do protocolo final. Não há como justificar seu valor pelos scores de ataque do piloto. Os protocolos de coleta são concretos; a autorização científica final depende desse orçamento, não de um threshold numérico inventado antes de obter calibration.

### Direção da anomalia

Z-score deve permitir upper, lower e two-sided como políticas distintas. Upper tem interpretação de aumento de volume/carga/latência; lower pode significar supressão de tráfego/serviço; two-sided pergunta sobre qualquer desvio do normal. Escolher a direção pela hipótese **antes do TEST**, preferencialmente antes da calibração. Calibração normal não revela qual direção é mais sensível ao ataque; selecionar direção com ataques de calibração é variante supervisionada.

**Proposta principal:** two-sided nas cinco features para Z-score e também dois limites empíricos para CoV, preservando os scores originais. CoV pode subir ou cair; não pressupor upper por conveniência. Equal-tail propõe repartir α* entre as duas caudas, sem impor simetria numérica no CoV. Empates/zero frequente podem impedir alcançar exatamente α* sem randomização; aceitar regra conservadora, sem ruído aleatório para “acertar” a taxa. Upper/lower podem ser análises secundárias previamente registradas, com orçamento próprio e sem selecionar a vencedora no teste.

Orçamento por par univariado não é orçamento de um sistema que alarma se **qualquer** das cinco features disparar. Não combinar decisões implicitamente. Reportar todas as cinco features; comparação inferencial múltipla requer controle ou intervalos simultâneos previamente definido.

## 7. PRE baseado em suporte

Se m janelas iniciais consecutivas estão ausentes, CoV L necessita L−1 valores válidos antes do primeiro score. Com Δ=1 s, PRE de P janelas dá `K=P−m−(L−1)` scores válidos, se não houver gaps adicionais. O piloto observou m=2 em CPU e L máximo=12, logo `P≥K+13`.

| Candidato de PRE | Critério proposto de K mínimo | CPU esperado sem novos gaps | Interpretação |
|---|---:|---:|---|
| 36 s | K≥20 | 23 | Econômico; aproximadamente dois históricos L12 de scores, ainda curto para estabilidade |
| 48 s | K≥32 | 35 | Mais observação pré-evento e margem para aquecimento |
| 72 s | K≥56 | 59 | Melhor diagnóstico de drift, maior custo por cenário |

Os alvos K são **escolhas de desenho para aprovação**, não limiares derivados de eficácia. Scores sobrepostos não viram K réplicas independentes. Em presença de gaps, usar suporte real e a política de reset do detector; a equação simples deixa de bastar. Não alongar runs dinamicamente até conseguir um score favorável. Duração permanece fixa; insuficiência de K fica registrada e exige ação operacional pré-declarada, não exclusão silenciosa.

PRE não treina Z-score nem thresholds. Ele fornece contexto causal para CoV e permite medir falsos positivos antes do evento. Startup, janela válida, suporte comum e suporte nativo devem ser apresentados separadamente.

## 8. ATTACK e POST

**ATTACK:** manter 36 s nas opções A/B. Seis ciclos já permitiram observar primeira reação, bursts posteriores e silêncios; reduzir perderia suporte temporal sem economia decisiva. Na C, 60 s permite dez ciclos do padrão original e cinco ciclos de P2; o aumento tem finalidade explícita de generalização temporal, não presumido ganho de detecção. Labels continuam pelo evento efetivo, não pelo cronograma.

**POST:** não remover. Propor 36/60/120 s em A/B/C. São 3/5/10 vezes L máximo atual, dando margem além dos 24 s do piloto. Isso é margem de desenho, não tempo de recuperação comprovado.

Não existe POST finito que garanta esquecimento para todo CUSUM/Page-Hinkley ou modelo com alarme latched. Métodos futuros precisam declarar inicialização, dinâmica de memória/reset e política de alarme. Para EWMA, por exemplo, decaimento depende do peso; Kalman depende do modelo. Não escolher pesos ou resets agora. A campanha inicial contempla Z-score/CoV; métodos stateful futuros poderão exigir bloco adicional com POST maior. Reportar censura de recuperação no fim do run em vez de forçar reset pelo ground truth.

## 9. Features propostas

| Feature | Evidência benigna / missing no piloto planejado | Interpretação e proximidade ao mecanismo | Coleta, online e limitações |
|---|---|---|---|
| ingress_packet_count | CV descritivo entre médias≈6,60%; sem null | Volume de registros source→proxy; inclui ACK/handshake/retransmissão | Captura/parser; depende do segmento e da completude; agregado causal no fechamento |
| ingress_tcp_payload_length_sum_bytes | ≈4,53%; sem null | Payload TCP registrado; mais próximo do volume de requests com operação homogênea | Mesma captura; não bytes on-wire/HTTP único; pode ser quase redundante com starts |
| request_starts | ≈4,53%; sem null | Intensidade de tentativas observadas no cliente; proximidade direta à emissão | Log de cliente no experimento; online exige observação operacional equivalente, não rótulo de source |
| mean_duration_ms | ≈4,47%; sem null no plano deste piloto | Consequência no cliente, rede/proxy/serviço; menos específica à causa | Só disponível após conclusão; médias de quantidades diferentes de requests e possíveis falhas; depende da instrumentação |
| mean_cpu_percent | ≈5,12%; dois nulls iniciais/run | Uso de recurso da vítima, mais downstream | Docker/coletor/cache; repetição de valores e resolução efetiva diferente de Δ; não é CPU instantânea independente |

**Manter as cinco** em todas as opções, separadamente. Coleta adicional de payload é pequena após pagar a captura; latência e starts compartilham log; infraestrutura acrescenta outra perspectiva. A campanha não é tão grande que cortar uma feature economize runs — o mesmo run alimenta todas. Evitar seleção por melhor resultado. Eventual campanha operacional com custo de captura impeditivo pode justificar redução posterior por custo/representação, não por labels do TEST.

## 10. CoV: um L ou hiperparâmetro

L3 representa flutuação local de 3 s; L6 agrega aproximadamente um ciclo atual; L12 mistura dois ciclos e mantém informação através de silêncio. O piloto confirmou que as estatísticas diferem, mas não determinou o L ideal.

**A priori:** uma variante principal claramente definida evita busca desigual entre métodos. **Proposta comum A/B/C:** CoV L=6 como hipótese temporal de uma janela de 6 s, não por F1 do piloto; L3 e L12 são sensibilidades secundárias, sempre reportadas e calibradas separadamente. Esta escolha é para revisão e expõe o alinhamento ao período conhecido. Não permite escolher depois qual L representará “CoV” no resultado principal.

**Calibrar L sem TEST:** possível usar apenas normal para suporte, repetibilidade e estabilidade do limite sob restrição de memória/latência. Porém pode favorecer um score quase constante e pouco sensível; estabilidade normal não prova sensibilidade. Usar ataques conhecidos para L muda a experiência para supervisionada. Se essa variante for aprovada, limitar candidatos a {3,6,12}, fixar objetivo/budget de busca por método e separar seleção de confirmação. Não adotar nesta campanha principal a seleção pelo melhor F1 de C/P.

A justa comparação não exige mesma memória entre Z-score e CoV; exige mesma informação causal disponível, orçamento de falso alarme, suporte/horizonte e exposição de limitações. Z é pontual no scoring, mas usa baseline; CoV usa histórico e não precisa do fit estático. Não agregar alarmes das três variantes nem reportar seu máximo como um único método.

## 11. Ground truth window-level e métricas

`q_k=attack_event_overlap_fraction`, `W_k=[a_k,b_k)`, `d_k∈{0,1}` quando disponível.

| Regra | Vantagem | Problema |
|---|---|---|
| q>0 | Preserva qualquer fração do evento | Cobra ataque por fração mínima e inclui evidência normal da mesma janela |
| q≥0,5 | Intuição de maioria | Corta de modo arbitrário; ≥ importa no empate; pode chamar parte atacada de normal |
| Somente q=0 ou q=1 | Evita threshold de fronteira na confusão principal | Exclui informação; eventos muito curtos podem não ter janela pura |
| Ponderação por q | Usa a informação fracionária | É estatística temporal ponderada, não matriz binária convencional nem antecipação causal de alarme |

**Proposta principal A/B/C:** confusão/Precision/Recall/F1/FPR somente em janelas puras, inteiras dentro de `[0,T_planejado)`, com decisões disponíveis. Comparações pareadas de métodos usam suporte comum, e relatório mostra também suporte nativo, janelas ausentes/warm-up, duração excluída e denominadores. Não transformar abstinência em TN nem esconder falhas de cobertura. Reportar FPR separadamente em B completo, PRE de C/P e POST de C/P; B em região estável `[P,T)` permite confronto com calibração, enquanto startup e POST permanecem resultados operacionais explícitos.

**Complemento obrigatório:** matriz temporal fracionária, com `TP_t=Σ d_k |W_k∩G|`, `FP_t=Σd_k |W_k\G|`, e equivalentes FN/TN, onde G é a união dos eventos. Unidades em segundos. Isso atribui a decisão retrospectivamente à janela de evidência; não prova que o alarme existia no início dela. Uma cobertura operacional precisa usar intervalos a partir de decision_available_time, separadamente.

Publicar tabela própria das boundaries e avaliação event-level usando também a primeira janela parcialmente atacada, sem atrasar artificialmente a primeira detecção até uma janela pura. Eventos sem janelas puras continuam avaliáveis em event-level; recall binário puro é indefinido se não há positivos elegíveis.

Métricas: TP/FP/TN/FN e Precision, Recall, F1, FPR; denominador zero→indefinido com motivo. Macro por run/cenário e micro adicional com pesos explícitos, sem deixar runs longos dominarem a interpretação. Acrescentar episódios falsos/hora normal e duração alarmada fora de eventos; episódio é sequência máxima de positivos adjacentes válidos, sem persistência/hysteresis artificial. Accuracy somente secundária. Nenhum point adjustment: um acerto não preenche o evento todo.

## 12. Menor contrato event-level

Propor um **EventTruthBinding**, acessível somente ao evaluator:

- referência/hash do feature manifest Stage 10, do manifest Stage 8 correspondente e do relatório Stage 9 elegível;
- `run_id`, versões/schema e path relativo de `raw/attacks/attack_events.csv`, SHA256/tamanho conferidos contra Stage 8;
- IDs de evento/ataque, `actual_start_seconds`, `actual_end_seconds`, status e unidade/origem monotônica; planned/drained ficam auxiliares, sem substituir os limites;
- hash do binding e do arquivo de eventos no evaluation report, com versão da política de atribuição/delay.

Conferir que o hash Stage 8 coincide com o `dataset_manifest_sha256` referenciado pelo Stage 10 e que run/clocks são os mesmos. Não resolver arquivos por caminhos externos não verificados. Não copiar/raw-reescrever eventos; não reconstruí-los de labels. Validar intervalos finitos/ordem, cruzar união de overlaps apenas para consistência e manter IDs individuais. Eventos sobrepostos sem atribuição identificável precisam política de cluster/ambiguidade explícita, sem duplicar créditos.

No evaluator, `EvaluationInput.events` passaria de None para tuple verificada e opcional; event-level é recusado se ausente, mantendo window-level possível. Resultado mínimo por evento: detectado, first_decision_available_time, delay ou motivo/limite de censura, preexisting_alarm, cobertura e referência da política. Fitter/scorer/policy continuam recebendo somente observações/scores, sem evento/labels. Não é necessária mudança no Stage 8 ou Stage 10.

## 13. Detection delay proposto

Para evento `E_j=[u_j,v_j)` e decisão de W_k com disponibilidade `A_k`, definir:

`D_j={k: d_k=1 válido, |W_k∩E_j|>0 e u_j≤A_k<v_j}`

`t*_j=min(A_k: k∈D_j)` e `delay_j=t*_j−u_j`.

- A_k não pode preceder b_k; não usar window_start como detecção. O default offline é fechamento da janela, não latência computacional medida.
- Se o evento começa no meio da janela, uma decisão positiva nesse fechamento pode contar mesmo que a boundary esteja fora da confusão binária principal. A janela pode conter evidência benigna também; registrar q_k e granularidade.
- Um positivo inteiramente pré-evento não ganha crédito; uma nova decisão por janela após início pode contar, com `preexisting_alarm` reportado. Estado alarmado apenas herdado/latch sem nova decisão não cria detecção. Não resetar pelo label para fabricar rising edge.
- Se não houver positivo válido durante o evento: detected=false, delay=null e censura em v_j−u_j; nunca delay=0. Alarmes associados ao fechamento após v_j são reconhecimentos tardios, separados do endpoint principal.
- No PeriodicBurst, positivo durante silêncio pode contar: a verdade principal é global. Calendarizar fases apenas para diagnóstico. `attack_request_starts` não entra na policy.
- Sem exigir N positivos consecutivos. Qualquer persistência futura é política separada, calibrada fora do teste e com atraso próprio.

Reportar recall de eventos, misses, delay entre detectados **junto** com misses e censura; não comparar só média dos detectados. Um detector sempre positivo teria alto recall de evento, mas viola o orçamento de FP, exposto nos controles. Pontos não disponíveis não viram negativos silenciosos: reportar cobertura do evento e sensibilidade conservadora previamente especificada.

## 14. Operação, intensidade e periodicidade

**Operação:** manter `/medium` em todas as alternativas iniciais. Variação `/light`/`/expensive` exige baseline/calibração específicos e adiciona um fator. Deixar para outra campanha; a generalização atual fica explicitamente limitada.

**Intensidade:** manter 8 RPS por atacante ativo; sem micrograde na campanha principal inicial. O piloto não saturou o serviço e não prova eficácia sob degradação. Uma segunda intensidade poderia testar generalização, mas não pode ser escolhida como “a que separa melhor os scores”. Isso requer pergunta de carga/capacidade e preflight próprios, sem TEST. Não há evidência suficiente para nomear uma taxa nova responsável nesta etapa. Uma grade ampliaria custo e dificultaria atribuição; não recomendada agora.

**Periodicidade:** A/B mantêm 2/6, duty 1/3. C acrescenta apenas P2=4 s/12 s, **mesmo duty 1/3 e RPS ativo**, para estudar escala temporal sem mudar carga média nominal. Evento de 60 s dá cinco ciclos P2 e dez P. Esse P2 não foi validado empiricamente; exige gate funcional futuro antes de multiplicar seus runs, preservando falhas e sem otimizar pelo score. Não se adiciona nova intensidade/operação simultaneamente. Mesmo P/P2 podem ter diferenças de scheduling/efeitos transitórios; generalização ainda é pequena, não universal.

## 15. Três protocolos completos para escolha

**Comuns às três propostas:** apenas Z-score/CoV atuais, ddof=1; cinco features da seção 9, univariadas; `/medium` em B/C/P, benignos 4×2 RPS e atacante 1×8 RPS ativo; mesma infraestrutura da seção 2; Δ=1 s. Baseline agrupado normal com intervalo declarado; calibração normal em duas partes independentes; Z e CoV two-sided por quantis normais, sujeitos à aprovação de α*/λ*; CoV L6 principal proposto, L3/L12 secundários sem escolha de vencedor; política binária de janelas puras + complemento ponderado; event binding/delay das seções 12–13. Nenhum ajuste no TEST.

### Alternativa A — escopo econômico e explicitamente exploratório

| Elemento | Proposta concreta |
|---|---|
| Seeds baseline | 4: **10001–10004**, um B por seed |
| Seeds calibration-fit | 3: **20001–20003**, um B por seed |
| Seeds calibration-confirm | 3: **20004–20006**, um B por seed |
| Seeds TEST | 8: **30001–30008**, cada uma B/C/P |
| Seeds totais / runs | **18 seeds / 34 runs** =4+6+8×3 |
| Duração B de treino | 120 s; fitting **[36,120)** por run |
| Duração B de calibração | 180 s; calibração/confirm steady **[36,180)** por run |
| Duração B/C/P do teste | **108 s**, PRE36, ATTACK36, POST36 |
| Evento planejado C/P | **[36,72)**; POST [72,108) |
| Padrão P | 2 s/6 s, duty1/3, **6 ciclos** |
| PRE mínimo de suporte | K≥20 scores de cada variante/feature após warm-up; esperado CPU L12=23 |
| Calibração | Benigna, 3 seeds para quantis e 3 para confirmação sem reajuste |
| Exposição confirm estável | 432 s =7,2 min, antes de eventuais indisponibilidades |
| Blocos de execução | Treino em pelo menos 2 blocos; calibração distribuída por 3; teste em 2 blocos de 4 seeds |
| Escopo/generalização | Um padrão P, uma intensidade e uma operação; 8 eventos por perfil |

Adequada se a dissertação aceitar **benchmark exploratório com grande limitação inferencial**. Reduz custo, mas não sustenta alegação forte de FPR raro nem precisão de event recall/delay. Os tamanhos são orçamento proposto, não “mínimo cientificamente suficiente”.

### Alternativa B — equilíbrio recomendado para revisão

| Elemento | Proposta concreta |
|---|---|
| Seeds baseline | 6: **11001–11006**, um B por seed |
| Seeds calibration-fit | 6: **21001–21006**, um B por seed |
| Seeds calibration-confirm | 6: **21007–21012**, um B por seed |
| Seeds TEST | 16: **31001–31016**, cada uma B/C/P |
| Seeds totais / runs | **34 seeds / 66 runs** =6+12+16×3 |
| Duração B de treino | 240 s; fitting **[48,240)** por run |
| Duração B de calibração | 360 s; calibração/confirm steady **[48,360)** por run |
| Duração B/C/P do teste | **144 s**, PRE48, ATTACK36, POST60 |
| Evento planejado C/P | **[48,84)**; POST [84,144) |
| Padrão P | 2 s/6 s, duty1/3, **6 ciclos** |
| PRE mínimo de suporte | K≥32; esperado CPU L12=35 |
| Calibração | Benigna, 6 seeds para quantis e 6 para confirmação sem reajuste |
| Exposição confirm estável | 1.872 s =31,2 min, antes de indisponibilidades |
| Blocos de execução | Treino/fit/confirm distribuídos por pelo menos 3 blocos por papel; teste em 4 blocos de 4 seeds |
| Escopo/generalização | Um P, uma intensidade, uma operação; **16 eventos por perfil** |

NB=6 ultrapassa modestamente a demonstração de cinco baselines e, sobretudo, alonga o suporte de cada benigno; não certifica estabilidade de σ. NC=12 oferece separação de escolha/confirmação com seis seeds em cada, evitando usar os mesmos dados para ambos. NT=16 dobra a opção A e melhora a caracterização entre seeds sem multiplicar fatores. A precisão ainda depende do endpoint; nenhum desses números é derivado de recall ou FPR que o piloto não mediu.

Preservar seis ciclos evita aumentar duração de ataque sem uma nova pergunta, enquanto PRE e POST ganham suporte. O ganho de rigor vem também da separação, confirmação, blocos, horizonte e auditoria, não apenas de aumentar N.

### Alternativa C — mais repetições e pequena extensão temporal

| Elemento | Proposta concreta |
|---|---|
| Seeds baseline | 10: **12001–12010**, um B por seed |
| Seeds calibration-fit | 10: **22001–22010**, um B por seed |
| Seeds calibration-confirm | 10: **22011–22020**, um B por seed |
| Seeds TEST | 32: **32001–32032**, cada uma B/C/P/P2 |
| Seeds totais / runs | **62 seeds / 158 runs** =10+20+32×4 |
| Duração B de treino | 300 s; fitting **[72,300)** por run |
| Duração B de calibração | 600 s; calibração/confirm steady **[72,600)** por run |
| Duração B/C/P/P2 de teste | **252 s**, PRE72, ATTACK60, POST120 |
| Evento planejado C/P/P2 | **[72,132)**; POST [132,252) |
| Padrão P | 2/6, duty1/3, **10 ciclos** |
| Padrão P2 | **4/12**, duty1/3, **5 ciclos**, mesmos 8 RPS ativos |
| PRE mínimo de suporte | K≥56; esperado CPU L12=59 |
| Calibração | Só B, 10 seeds para quantis e 10 para confirmação; P2 não influencia a escolha |
| Exposição confirm estável | 5.280 s =88 min, antes de indisponibilidades |
| Blocos de execução | Treino/fit/confirm distribuídos por pelo menos 5 blocos por papel; teste em 8 blocos de 4 seeds |
| Escopo/generalização | Duas escalas periódicas com duty igual; uma operação e intensidade; 32 eventos por perfil |

A robustez é **relativa às outras opções**, não garantia universal. P2 não foi executado no piloto e precisará gate de infraestrutura/timing futuro após autorização, sem consultar eficácia. Maior custo permite mais seeds, ciclos e POST, mas não demonstra generalização para outras operações/intensidades, nem transforma 32×3 eventos em 96 seeds independentes.

### Aspectos operacionais comuns

Nas três opções, B de teste tem a mesma duração que os atacados e regiões por posição temporal para controle, sem evento fictício. B de treino/calibração é mais longo por sua finalidade: essa diferença está declarada, não é réplica equivalente de teste. Verificar estabilidade ao longo dos benignos longos e usar B de teste para medir generalização normal, sem reajuste posterior.

Os K e a divisão de blocos são critérios propostos a aprovar; não foram certificados pelo piloto. Logs de integridade podem ser inspecionados por processo automático de Stage 8–10; após congelamento, nenhuma escolha metodológica poderá usar valores, scores ou labels do teste. O acesso humano ao desempenho fica bloqueado até terminar a matriz de teste. Mudança de protocolo após começar TEST exige declarar aquele conjunto como desenvolvimento e reservar outro teste, não preservar a aparência de cegamento.

## 16. Custos: duração e composição, não regra de três por run

Valores detalhados em [cost_estimates.json](cost_estimates.json). Modelo auditável:

1. `wall≈Σ duração_nominal + Σ overhead_por_cenário`. O overhead médio observado foi ≈13 s em B e ≈15 s em C/P, incluindo export/validação/features. Não multiplicamos 98,36 s por qualquer novo run sem considerar sua duração.
2. Para cada estágio de dados, normal cresce aproximadamente com tempo a 8 RPS. O excesso de bytes de C ou P sobre B é escalado pela **duração do evento**, usando contrastes pareados do piloto. Assim aumentar PRE/POST não é tratado como aumentar todo o run na carga de ataque.
3. P2 recebe provisoriamente o excesso de bytes de P por segundo de evento, pois tem mesmo duty; é hipótese não validada. Metadata/PCAP/falhas podem alterar escalabilidade.
4. Scores: custo separado de manifest e bytes/janela, medidos nos artefatos reais, para Z + CoV3/6/12 ×5 features em calibração/teste. Não multiplicam runs. Reserva de 15% para outputs auxiliares/decisões/proveniência e 50% de folga de disco; não duplicar a contagem de raw+Stage 8 novamente.
5. Reserva operacional de 20% no wall é margem de planejamento, **não IC**. Agendamento de blocos/dias e pausas podem ampliar tempo de calendário. Novas intensidades, saturação, timeouts ou mudanças de captura invalidariam a extrapolação.

| Custo | A | B | C |
|---|---:|---:|---:|
| Runs | 34 | 66 | 158 |
| Nominal | 69,2 min (1,15 h) | 211,2 min (3,52 h) | 787,6 min (13,13 h) |
| Wall estimado execução/processamento | **77,2 min (1,29 h)** | **226,7 min (3,78 h)** | **825,3 min (13,75 h)** |
| Com 20% de reserva | 1,54 h | 4,53 h | 16,51 h |
| Raw+dataset+features+validation | ≈330 MiB | ≈967 MiB | ≈3645 MiB |
| Scores estimados, sem multiplicar runs | ≈9,8 MiB | ≈27,3 MiB | ≈100,0 MiB |
| Total com 15% auxiliares | ≈391 MiB (0,38 GiB) | ≈1143 MiB (1,12 GiB) | ≈4307 MiB (4,21 GiB) |
| Orçamento de disco com folga | **≈0,57 GiB** | **≈1,68 GiB** | **≈6,31 GiB** |

Não são dezenas de GB na matriz proposta. Retenção extra de PCAP, outros detectores/representações, backup, novas operações e campanhas repetidas poderão aumentar isso. O custo de análise de scores foi pequeno no piloto (5,33 s), mas export/transformações podem crescer de modo não linear; não foi feito benchmark de longos runs de 600 s nesta etapa. Não estimar horas de energia/CPU integrada a partir do wall.

## 17. Precisão e capacidade inferencial: o que as opções compram

Usando somente como aproximação de planejamento a dispersão **das médias benignas por run** do piloto, `r≈1,96·CV_run/√N_T`, sem assumir melhora extra pela duração:

| Propriedade | A, NT8 | B, NT16 | C, NT32 |
|---|---:|---:|---:|
| Semi-amplitude relativa aproximada para médias benignas | 3,10%–4,57% | 2,19%–3,23% | 1,55%–2,29% |
| Eventos por perfil | 8 | 16 | 32 |
| Precisão de recall/delay | Não prevista pelo piloto | Não prevista pelo piloto | Não prevista pelo piloto |
| Confirmação normal estável nominal | 7,2 min | 31,2 min | 88 min |

A faixa não é promessa de IC95%, não cobre todas as fases e não é precisão de FPR ou Recall. n=5 estimou mal a dispersão; duração/host podem mudá-la, e t/efeitos de bloco ampliam intervalos. A aproximação de tamanho/intervalo de média se baseia em hipóteses descritas pelo [NIST — seleção de amostras](https://www.itl.nist.gov/div898/handbook/ppc/section3/ppc333.htm) e [limites para média](https://www.itl.nist.gov/div898/handbook/eda/section3/eda352.htm).

**FPR raro é principalmente um problema de exposição/cauda**, além de seeds. Como ilustração condicional, se episódios falsos obedecessem a Poisson homogêneo e fossem observados **zero** episódios em T horas, o limite unilateral de 95% seria `λ_upper≈−ln(0,05)/T≈3/T`. Nas confirmações propostas isso daria aproximadamente **25,0/h, 5,76/h e 2,04/h** em A/B/C. Não são taxas esperadas/observadas, nem garantias para scores dependentes. A hipótese vem do [modelo HPP do NIST](https://itl.nist.gov/div898/handbook/apr/section4/apr451.htm), não foi validada para alarmes destes métodos.

Mesmo a C não basta, por esse exemplo, para certificar <1 episódio/hora só com sua confirmação. Para tal ordem de alvo seriam necessárias ≈3 h normais independentes sem alarmes sob essa hipótese; 0,1/h requereria ≈30 h. Não há como prometer controle rigoroso de um alvo ainda não especificado. Número de janelas não resolve dependência por sobreposição/cache. Bootstrap que retorna [0,0] porque nenhum alarme ocorreu não prova FPR zero.

No teste, estimar incerteza por **seed/run ou bloco**, com C/P pareados; reportar a taxa de eventos com intervalos apropriados aos resultados observados e intervalos/dados censurados de delay. Não tratar as três variantes CoV, as cinco features ou vários bursts do mesmo evento como novas repetições independentes. Não há previsão de recall que justifique escolher NT aqui.

## 18. Crescimento incremental sem favorecer o vencedor

A/B/C têm N fixos na proposta base, favorecendo simplicidade e auditabilidade. Não recomendo “continuar TEST até a média/F1 estabilizar”. Parada por intervalos convencionais repetidamente inspecionados pode alterar sua cobertura mesmo sem escolher o método vencedor.

Uma variante incremental defensável **antes do teste**, se aprovada, seria:

- Baseline B: looks somente em **6, 10 e 14 seeds**; acrescentar blocos de quatro seeds reservadas. Monitorar médias observáveis e sensibilidade leave-one-run-out de μ/σ, nunca F1/Recall. Critérios candidatos para aprovação: semi-amplitude relativa simultânea de médias ≤5%, variação de médias do último bloco ≤5% e mudança relativa máxima leave-one-run-out de σ ≤10%. São metas de projeto discutíveis, não resultados sustentados ou gatilhos já autorizados.
- Se usar IC para parar, pré-definir correção pelos **3 looks ×5 features** (por exemplo, Bonferroni sobre IC válidos por run) ou confidence sequences com hipóteses verificadas. T não é exato para qualquer distribuição; bootstrap por run também é aproximação. Não usar janelas como iid.
- Calibration-fit: só ampliar dentro de cap previamente registrado, por incerteza do limite normal/suporte e exposição exigida por α*/λ*, sem labels de ataque. A amostra de confirmation fica separada e seu tamanho é decidido antes de abri-la. Não crescer confirmation até um threshold passar sem corrigir a inferência.
- TEST permanece **NT16 fixo** no exemplo B; o tamanho é decidido usando treino/calibração antes de liberar o teste. Não ajustar thresholds, features ou L depois. Se for realmente desejado um teste sequencial, requer desenho específico com intervalos válidos no tempo, não uma inspeção informal de convergência.
- Ao atingir o cap sem a meta, relatar que a precisão não foi alcançada e decidir nova versão de protocolo **antes de TEST**, sem escolher o que favoreceu scores.

No exemplo de teto da B, NB14 e NC20 (14 fit/6 confirm) manteriam NT16, totalizando 82 runs, ≈5,2 h base em vez de 3,8 h, antes de reservas. Esse teto não é uma quarta campanha aprovada: é um custo contingente para discutir a variante incremental. A B recomendada abaixo permanece a versão fixa de 66 runs.

A possibilidade de inferência válida com parada adaptativa está em [Howard et al., confidence sequences](https://arxiv.org/abs/1810.08240). Isso exige mais cuidado que “IC95% em cada look”; não foi implementado aqui. Para um TCC com dois métodos, o custo de complexidade pode superar a economia de poucas seeds.

## 19. Comparação das alternativas

| Critério | A — econômica | B — equilibrada | C — repetições + escala temporal |
|---|---|---|---|
| Rigor de desenho | Separação correta, suporte pequeno | Separação + mais confirmação/blocos/tempo | Maior repetição e padrão temporal não usado na calibração |
| Custo ativo com reserva | ≈1,5 h | ≈4,5 h | ≈16,5 h |
| Variabilidade coberta | 8 seeds de teste | 16 seeds de teste | 32 seeds de teste |
| Independência dos papéis | Física e seeds disjuntas | Física e seeds disjuntas | Física e seeds disjuntas |
| FPR por janela | Estimável, muita incerteza em caudas | Melhor exposição; ainda depende do alvo | Mais exposição, ainda sem garantia de FPR raro |
| Episódios raros/hora | Muito limitada | Limitada; normal extra pode ser necessário | Melhor, mas confirmação ainda <3 h |
| Recall de evento | 8 eventos/perfil, intervalos amplos | 16/perfil; não “alta precisão” garantida | 32/perfil; ainda requer IC observado |
| Detection delay | Granularidade1s; poucos eventos | Mais eventos e POST maior | Mais eventos/ciclos e POST maior |
| Generalização | Só2/6, 8RPS, medium | Mesmo escopo, melhor replicação | Acrescenta4/12 com mesmo duty; não outras intensidades/operações |
| Complexidade | Baixa | Moderada, sem nova dimensão de cenário | Maior: P2 e blocos/tempo adicionais |
| Adequação ao TCC | Boa se assumidamente exploratório | **Melhor equilíbrio proposto** | Boa se tempo e escopo comportarem a extensão |
| Risco metodológico dominante | Confundir benchmark pequeno com evidência forte | Exagerar precisão de caudas ou generalização | Chamar de robusto universal; variar escala temporal sem validar gate |

## 20. Recomendação para escolha do usuário

**Recomendo a B fixa, sujeita à sua aprovação**, porque combina independência real entre papéis, baseline agrupado, seis seeds de confirmação, 16 tríades de teste, maior PRE/POST e custo operacional próximo de quatro horas. Ela amplia evidência onde o piloto revelou fragilidade sem acrescentar simultaneamente operação, intensidade e padrão temporal. C custa mais de três vezes o wall da B e acrescenta uma pergunta; não é automaticamente melhor para o objetivo inicial do TCC.

A recomendação **não aprova α*/λ*, L principal, duração ou N como finais**, nem autoriza gerar runs. Se o objetivo principal for certificar falsos alarmes muito raros por hora, recomendo priorizar **extensão de normal de calibração/confirm/teste**, dimensionada por exposição, antes de comprar mais ataques ou escolher C por ser maior. Nesse caso, recalcular custos e aceitar uma versão B revisada antes da coleta.

Se o orçamento real for só ≈1–2 h, A é honesta como campanha exploratória com limitações declaradas. Se a pergunta central incluir generalização de escala periódica e houver ≈14–17 h ativas, C tem benefício científico explícito. Nenhuma foi executada ou convertida em configs.

## 21. Decisões propostas como congeláveis

**PODEMOS CONGELAR, mediante ratificação:**

- observações univariadas e cinco candidatas explícitas; scores separados de decisão; z assinado; ddof=1 e regras de missing das implementações atuais;
- séries Stage 10 completas/intactas; seleção de fitting separada, explícita e auditável, sem cauda não coberta;
- baseline normal independente agrupado por feature/cenário; nunca fitting no próprio atacado;
- runs e seeds disjuntos por papel; B/C/P pareados somente dentro do teste; piloto sempre desenvolvimento;
- `/medium`, infraestrutura fixa e sem mistura de operações C/P na campanha inicial; reconhecer diferenças de duty/admissão;
- score/decisão disponíveis no fechamento ou depois; sem latência inventada/persistência implícita/reset por label;
- ground truth global incluindo silêncio, window/event separados, evento original via binding verificável;
- referência de calibração normal, confirmação independente e TEST inacessível até congelar artefatos;
- registrar falhas, cobertura, cauda, proveniência e denominadores, sem transformar null em zero.

**AINDA PRECISA DE EVIDÊNCIA:**

- estabilidade de caudas, distribuição dos scores e exposições necessárias para falsos alarmes raros;
- generalização entre blocos/máquinas, operações/intensidades e outros períodos;
- suficiência de N para cada endpoint e precisão desejada; o piloto dimensiona somente aproximações para médias;
- tempo de recuperação/memória de métodos futuros; POST não garante esquecimento universal;
- comparabilidade de benignos mais longos e P2; qualidade/frescor efetivo da infraestrutura;
- orientação/operating point úteis se for escolhida uma pergunta supervisionada, distinta da referência normal.

**DEVE SER RESOLVIDO ANTES DA ETAPA 14:**

1. Usuário escolher **uma alternativa** e aceitar escopo/limitações, orçamento e endpoints/precisão. Não tratar recomendação como autorização.
2. Definir α* e, se aplicável, λ*, caudas, empates/comparadores, critério de confirmação e exposição suficiente. Nenhum threshold numérico final pode ser aprendido antes de obter calibration, mas a regra precisa estar congelada.
3. Ratificar L principal e sensibilidades, PRE/K, ATTACK, POST, intensidade/padrão, masks/horizonte de treino/calibração/avaliação e regras de missing/suporte/retry.
4. Autorizar separadamente e validar com fixtures a extensão de seleção de fitting + registro do intervalo. **O framework atual não registra essa seleção.** Não alterar Stage 10 para resolver.
5. Autorizar e validar separadamente a política de calibração/decisão e métricas/evaluator, hoje apenas contratos; ligar eventos originais Stage 8 com hash/binding e formalizar delay/censura. Sem isso, a campanha produziria apenas novos scores, não a avaliação científica solicitada.
6. Registrar protocolo versionado, seeds/ordem/blocos, dependências/imagens/ambiente, hipóteses estatísticas e plano de incerteza/múltiplas comparações. Testar gates sem usar as seeds de TEST para desenvolvimento.
7. Somente após treino/calibração/confirm aprovados, congelar os **valores efetivos** de modelo/threshold/config e liberar coleta/avaliação do TEST. Se a calibração não atende ao objetivo, parar antes do TEST e revisar com dados de desenvolvimento, não adaptar no teste.

Shannon continua fora: distribuição/representação ainda não resolvidas. Não há mudança de detector, fitting, calibração, decisão ou evaluator nesta Etapa 13B. **Parecer encerrado na recomendação; aguardamos a escolha, sem executar nenhuma alternativa.**
