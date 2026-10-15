# Interpretação metodológica e decisões após o piloto

Estes resultados são **evidência de planejamento** para o ambiente fixo estudado. Não há decisão attack/normal, threshold, F1, ranking ou conclusão de eficácia. Tabelas completas e proveniência em [results.md](results.md); configuração prévia em [design.md](design.md).

## Respostas às questões do piloto

1. **Comparabilidade:** sim, nominalmente. Mesma operação `/medium` para todo tráfego, quatro benign sources ×2 RPS, um atacante ×8 RPS de atividade, infraestrutura/pool/proxy/timeout/janela fixos; imagens verificadas iguais nas 15 execuções. Diferenças intencionais são enabled/profile/burst. C e P não confundem operação com perfil. Porém P usa duty 1/3, portanto tem menor carga média; o contínuo possui fila e o periódico descarta oportunidades sem capacidade/revalida deadline. É um contraste controlado de perfis existentes, não uma prova de que somente a periodicidade determina qualquer mudança. Comparar carga média igualada seria outra pergunta, ainda não executada.

2. **Variabilidade entre seeds:** existe e é mensurável. As médias benignas por run no período planejado têm os seguintes valores entre cinco seeds:

| Feature | Média das médias | SD entre seeds | Faixa | Desvio relativo entre seeds |
|---|---:|---:|---:|---:|
| ingress_packet_count | 19,529 records/janela | 1,289 | 17,631–20,821 | 6,60% |
| ingress_tcp_payload_length_sum_bytes | 1607,667 bytes/janela | 72,821 | 1500,333–1698,667 | 4,53% |
| request_starts | 8,202 starts/janela | 0,372 | 7,655–8,667 | 4,53% |
| mean_duration_ms | 33,962 ms | 1,518 | 31,546–35,765 | 4,47% |
| mean_cpu_percent | 18,514% | 0,949 ponto percentual | 16,966–19,298 | 5,12% |

Esse coeficiente descritivo entre médias não é o score CoV móvel. Cinco seeds não estabelecem a distribuição real ou limites de extremos. Pareamento usa mesma seed/configuração, mas chegadas efetivamente realizadas não são idênticas: deadlines e scheduling podem mudar uma tentativa.

3. **Estabilidade benigna:** as médias globais são relativamente próximas neste piloto, mas não são constantes. Há flutuação intrarrun substancial (Poisson, rede, coleta/cache) e drift entre blocos: até o controle B teve mudanças PRE_LATE→POST_LATE. Para CPU, por exemplo, essas mudanças por seed variaram aproximadamente de −14% a +28%. Isso impede atribuir automaticamente toda diferença pré/pós ao ataque ou tratar janelas como independentes. Não foi demonstrada estacionariedade nem estabilidade de caudas raras.

4. **Baselines Z-score:** μ variou entre seeds com desvio relativo de 4,47%–6,60%; σ teve variação relativa de aproximadamente 5,02% (starts), 5,76% (payload), 6,26% (packets), 9,81% (duração) e 10,92% (CPU). Logo um único run benigno pode mover o centro/escala de forma relevante. Recomendo treinar com vários benignos comparáveis, verificar normal independente e guardar suporte/ponderação. Isso não determina quantos runs bastam. Os 25 modelos individuais e o ramo de cinco modelos combinando B101+B211 usam apenas benignos; todo scoring usa baseline de outras seeds.

5. **Ordem de repetições:** para **médias por run**, a sensibilidade de planejamento é:

| Feature | n aproximado para semi-amplitude 5% | para 2% |
|---|---:|---:|
| packets | 7 | 42 |
| payload | 4 | 20 |
| starts | 4 | 20 |
| duração | 4 | 20 |
| CPU | 5 | 26 |

É a conta normal aproximada n≈(1,96·CV_descritivo/r)², com arredondamento para cima. Não são garantias, recomendações finais ou IC calculado. Cinco seeds estimam mal o próprio SD; quantil t, planejamento conservador e blocos de infraestrutura aumentam a necessidade. **A ordem pode ser unidades/dezena para precisão mais frouxa de médias e dezenas para 2%; não há N único do TCC derivável daqui.** Se o objetivo forem diferenças pequenas, variância, caudas, falsos alarmes ou detecção de eventos, será necessário dimensionamento próprio. Antes de congelar N: escolher endpoints e precisão, ampliar confirmação benigna em novos blocos se a incerteza do SD continuar dominando e separar exposição de calibração daquela usada no teste. As curvas 1→5 mostram flutuação; aparente estabilização não é regra de parada.

6. **Duração total/evento:** 84 s foi suficiente para o mecanismo: seis ciclos, score após warm-up e inspeção de recuperação. Não é suficiente para certificar baixos falsos alarmes nem incerteza final. Os seis bursts foram realizados em todas as seeds, com contagens P 102/97/91/127/91; C realizou 293/278/263/348/281. Isso confirma variabilidade e que taxa nominal não determina contagem. Nenhuma request teve outcome de falha, e CPU não entrou em saturação extrema nos ensaios iniciais. O piloto representa perturbação controlada moderada, não valida degradação/sustentabilidade ou LDoS realista.

7. **PRE:** 24 s permite iniciar os três lookbacks antes do ataque. Para L=12, há somente 13 scores PRE de starts e 11 de CPU, pois CPU tem dois nulls iniciais. É suficiente para aquecer estado neste cenário, **curto para afirmar estabilidade**. Para uma campanha que exija m blocos completos de diagnóstico já aquecido, usar como restrição de desenho `T_PRE ≥ startup_observado + (L_max−1)·Δ + m·L_max·Δ`, ajustada à dependência e ao objetivo; não fixei m ou segundos finais. Baseline continua independente e não será substituído por PRE.

8. **POST:** deve ser mantido. O CoV carrega histórico após cessar emissão e a instrumentação pode carregar cache. Diferenças C−B na fase POST inteira foram pequenas frente às diferenças da região de evento (starts +0,008/janela, duração +0,746 ms, CPU +0,879 ponto percentual), mas não exatamente zero, e controles também variam. Os 24 s cobrem duas vezes L máximo; servem ao diagnóstico local. Não demonstram tempo universal de recuperação; ambiente com autoscaling, filas persistentes ou outra intensidade exigirá mais observação. Pós-ataque não vira baseline automaticamente.

9. **CoV/interpretabilidade:** L=3/6/12 não mede exatamente a mesma distribuição temporal. Para starts em P, a média dos scores por fases programadas foi: L3 burst≈0,472/silêncio≈0,396; L6≈0,500/0,504; L12≈0,497/0,500. L6/L12 retêm ciclos anteriores e o score não desaparece no silêncio. Isso é memória de janela, **não detecção nem evidência acumulativa de um novo método**. No contínuo o CV pode diminuir porque o aumento de volume reduz variabilidade relativa, coerentemente com a definição. Não escolher “melhor L” dessas médias; comparar futuramente suporte, atraso inerente, finalidade temporal e orçamento de falso alarme em normal independente.

10. **Features para seguir:** manter provisoriamente as cinco candidatas. Rede e starts estavam disponíveis em todas as janelas planejadas; duração também teve suporte em todas elas neste piloto. CPU tem dois nulls de startup por run e cache/repetições que restringem sua resolução efetiva. A diversidade de famílias continua útil. Payload/starts podem ser redundantes em operação homogênea, mas compartilham coleta e o piloto não justifica exclusão por desempenho. Nenhuma feature foi escolhida por labels/F1. Não expandir o conjunto agora.

11. **Calibração:** levar adiante principalmente quantis de scores benignos independentes e controle de orçamento de falso alarme em normal. Média+kσ é alternativa comparativa, com k pré-especificado/calibrado fora do teste e diagnóstico de caudas. Limites teóricos exigem hipóteses; z com μ/σ estimados não implica automaticamente N(0,1). CoV depende de L/distribuição e não tem threshold universal. Uma única seed de calibração com 84 s oferece poucas observações de cauda, menos ainda efetivamente independentes em CoV. Precisaremos de **exposição normal mais longa e variada**, dimensionada pelo orçamento operacional. Nenhum quantil deste piloto foi promovido a threshold e nenhuma decisão foi gerada.

12. **Custo:** 21 min nominais; lifecycle somado ≈24,54 min; runs + Stage 8–10 ≈24,59 min; intervalo total observado ≈26,06 min incluindo inspeções. Raw ≈54,71 MiB, datasets ≈55,90 MiB, features ≈1,20 MiB e validações ≈0,51 MiB. Média ≈98,36 s e ≈7,49 MiB por run nessas quatro fases. Scores/estatísticas consumiram ≈5,33 s wall, 4,63 s CPU de processo, ≈41 MiB de pico RSS e ≈5,85 MiB de artefatos antes do summary. O processo de execução teve pico RSS próximo de 418 MiB; isso não é memória de todo o host/containers. Não medimos energia nem consumo CPU integrado de todos os processos. Custo de build cacheado ficou fora dos timers por run; não houve exclusão de raw/datasets para reduzir números. Extrapolação só é válida para duração/carga semelhantes.

## Baseline / calibration / test propostos

Preferir **runs independentes com seeds particionadas**. Dois critérios complementares: IDs diferentes separam execução; seeds distintas evitam compartilhar a mesma trajetória pseudoaleatória. Operação, topologia, carga benigna, coleta e infraestrutura precisam permanecer comparáveis. No teste, B/C/P continuam pareados por seed de teste; baseline e calibração usam outras seeds, só normais na referência inicial.

A partição piloto {101,211}→{307}→{401,503} serve apenas para exercitar esse fluxo; todos os dados foram inspecionados e não são teste cego. O ramo de modelos por seed para medir variação de μ/σ é outra análise exploratória, não ajuste do modelo do ramo reservado a partir de seus scores. Campanha científica terá dados novos e treino/calibração anteriores ao teste em protocolo congelado, sem reaproveitar esse piloto como validação final.

Não fixamos quantidades por papel: dimensões de baseline/caudas normais e incerteza dos resultados finais podem exigir tamanhos diferentes. Uma estimativa de N baseada em médias não deve determinar automaticamente a quantidade de seeds de calibração ou o número de eventos de teste.

## Limitação adicional evidenciada: horizonte e cauda

As séries têm 85 janelas por run de 84 s, por política intacta da Etapa 10. O fitting da Etapa 12 usa todas as observações válidas disponíveis. No piloto, usar a série inteira alterou μ de starts em média ≈−1,15% e σ em ≈+3,50% em relação ao recorte descritivo dentro do plano. Duração média teve efeito menor mas não necessariamente zero quando houve conclusão de cauda.

Isso não foi corrigido cortando “outliers” ou regravando inputs. `baseline_horizon_diagnostic.csv` documenta os dois resumos, mas **somente o modelo de série inteira foi usado no scoring**. Antes da campanha é necessário definir horizonte científico e eventual seleção temporal auditável de fitting, incluindo o que conta como cobertura observável. Não implementei extensão dos contratos 0–12. Zero count em padding não prova inatividade normal; a confirmação de eventos/ausência de eventos também não prova completude da captura.

## Event-level e dados disponíveis

Os limites e IDs efetivos existem no Stage 8 `attack_events.csv`, preservados com hash no diagnóstico. O problema encontrado na Etapa 11 continua sendo que o Stage 10 v1 não fornece sozinho a identidade/intervalos individuais, apenas overlap da união. Falta vincular esses eventos verificáveis ao evaluator para atribuição e delay com timestamps de disponibilidade; **não faltam necessariamente os registros brutos**. Nenhum delay ou métrica event-level foi calculado, e o Stage 10 não foi alterado.

## Ameaças à validade

- Cinco seeds, uma máquina, um bloco temporal de coleta, ordem parcialmente contrabalançada. Tráfego e carga/temperatura/frequência do host podem se confundir. Mesmo seed não implica mesma execução realizada.
- Mesma operação/carga leve-moderada, sem autoscaling, sem saturação extrema, atacante simples. Não generalizar para LDoS com degradação, filas extensas, outros endpoints ou cenários reais.
- Duty cycle muda volume médio; políticas de admissão contínua/periódica diferem por contrato. Phase-lock de Δ=1 s, burst=2 s/período=6 s e lookbacks múltiplos pode favorecer interpretação simples; não demonstra robustez a outras fases/períodos.
- CPU é média/cache do coletor, não amostra instantânea independente a cada segundo; clocks de packets e serviço diferem e captura completa não é provada. Janela parcial de evento permanece fracionária.
- μ/σ estimados, missingness e cauda influenciam scores; CoV sobreposto induz dependência. Nenhuma normalidade, estacionariedade ou precisão de cauda foi provada.
- Proveniência registra árvore dirty por arquivos novos não commitados (`EXECUTION_WORKTREE_CLEAN` é o warning científico em todos os runs), mas hashes de código, imagens, configs, datasets e fontes do piloto foram preservados. Não equivale a versão publicada limpa.

## O que podemos encaminhar e o que falta congelar

Encaminhar: `/medium` é operacionalmente viável para cenário inicial controlado; controle de operação C/P funcionou; manter POST, baseline independente e cinco features como candidatas; separar seeds por papel; calibrar apenas com normal na referência inicial; preservar scores assinados e abstenção por missing; all pilot = desenvolvimento.

Ainda dependem de decisão/evidência: precisão/endpoints principais; N por papel; exposição de calibração e alvo de falso alarme; lookback final; duração PRE/ATTACK/POST definitiva; horizonte/cauda auditável; estabilidade em novos blocos da máquina; definição de decisão e avaliação/eventos; necessidade de outras intensidades/periodicidades antes da campanha. Não executei extensão de campanha nem fechei valores finais.

Shannon permanece fora: falta definir a distribuição categórica e representação apropriada. Nenhum detector novo foi implementado e nenhum commit foi feito.
