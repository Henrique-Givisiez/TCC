# Contrato auditado antes da interpretação

Fonte: implementações `analysis/detection/detectors/*.py`, engine científico e métricas direct, vinculadas pelo plano energy-powersaver-20261109. Esta investigação não chama fit, calibrate, publish, evaluate, aggregate ou coletores; lê parâmetros e decisões persistidos e executa somente cálculos em memória. Toda reconstrução é derivada e será confrontada com o original.

## Observações e tempo

Janelas fixas de 1 s [i,i+1); disponibilidade simulada no fechamento, não latência de processamento medida. O estado começa no índice 0 e atravessa WARMUP; somente avaliação usa [30,390]. Não reiniciar em PRE/ACTIVE/POST. Features científicas: ingress_packet_count (registros de pacote ingress, incluindo retransmissões e payload zero), ingress_tcp_payload_length_sum_bytes (soma packet_length TCP observado, não bytes únicos HTTP), request_starts (todos os inícios HTTP, legítimos e ofensivos), mean_duration_ms (média de todas as terminações HTTP por segundo de término, incluindo timeouts e ambas as classes). CPU é a quinta feature disponível, mas descritiva e excluída do contrato direct desta campanha. Nenhuma transformação logarítmica ou imputação.

## Z-Score

z=(x−mu)/sigma, com média exata racional e desvio amostral ddof=1 de BASELINE independente (4 execuções, janelas [30,390), pesos iguais por observação). Referência congelada, sem atualização online, sem valor absoluto. Score ausente se x ausente. sigma=0 rejeita baseline; não há epsilon. Alarme z>h, empate negativo. h vem de CAL_A, não é o número clássico fixo 3.

## CoV

s/m em seis observações consecutivas incluindo a atual; média aritmética e desvio amostral ddof=1. Sem baseline estática e sem valor absoluto. Média exatamente zero torna score indisponível; média positiva pequena não recebe epsilon. Ausência limpa a janela e exige novamente seis valores consecutivos. Alarme CoV>h; reduções de variabilidade relativa não alarmam. Em patamar constante alto, CoV pode ser baixo. Transições só afetam os seis pontos retidos, salvo flutuações posteriores.

## EWMA

z usa a mesma baseline congelada. Inicialização S=0 no índice 0; S_t=0,2 z_t+0,8 S_(t−1), score assinado. Alarme S_t>h. Alarme não reseta nem congela o estado; todas as observações válidas atualizam. Ausência gera decisão indisponível e reseta S=0. Memória do estado anterior decai por fator 0,8 por observação válida; não há regra de retorno, histerese ou confirmação adicional. A referência mu/sigma não aprende o ataque.

## CUSUM-freeze

k=0,5, S_0=0. Candidato C_t=max(0,S_(t−1)+z_t−0,5). Decisão C_t>h. Se C_t<=h, aceita atualização S_t=C_t; se C_t>h, rejeita atualização e S_t=S_(t−1). O score publicado é o **candidato**, não o estado armazenado. Logo S sempre fica em [0,h], mas candidato pode exceder h. Cada próxima janela calcula novo candidato com o estado preservado; continua emitindo decisões, inclusive negativas quando o novo candidato não cruza h. Não há latch permanente, flag independente frozen, reset automático ao alarmar ou suspensão de observações. Ausência torna score/decisão indisponíveis e S_t=0. Empate aceita estado, sem alarme. h integra a transição, e não pode ser trocado apenas ao limiarizar uma trajetória já pronta. A auditoria deve conferir candidato, anterior, aceitação, posterior, decisão e retomada.

## Calibração e elegibilidade

Z/CoV/EWMA: quantil empírico superior CAL_A de 1%, índice ceil((N−1)×0,99), comparação estrita >. CUSUM-freeze: seleção persistida do menor h elegível na grade vinculada ao CUSUM-reference; somente ler essa seleção, sem reconstruir variante contrafactual. CAL_A exige cobertura >=95%, FPR médio <=1%, máximo por run <=5%; CAL_B confirma com FPR médio <=2%, máximo <=5%, sem nova seleção. Parâmetros de normalização são compartilhados entre Z/EWMA/CUSUM por feature. Os 16 pares desta campanha são elegíveis.

## Métricas oficiais

Ground truth usa actual_start_seconds/actual_end_seconds dos eventos persistidos. Detecção de evento: ao menos uma decisão positiva disponível durante o evento e de janela com sobreposição positiva; latência = primeiro instante de disponibilidade−actual_start, condicional aos eventos detectados. Recall por janela usa somente janelas integralmente ofensivas. Janelas parciais de fronteira não entram em TP/FN. FPR primário usa L2 [30,390): positivas/disponíveis, primeiro por execução, depois média de 20 execuções. PRE ofensivo tem pre_fpr separado. POST oficial exige janela com início >=270 e >=actual_end; é relatado separadamente, sem incorporar POST ao FPR primário L2. Duração positiva POST soma janelas positivas suportadas, não duração contínua de um alarme.

## Cruzamento operacional derivado

Preservar os rótulos oficiais. Para contexto, cruzar janelas com marcadores de 270 s, último fim computacional ofensivo, primeira fila aguardando vazia, retorno de pendências e disponibilidade (início e confirmação), última coorte POST com falha. Retorno operacional descritivo conservador = máximo das confirmações de 15 s, primeira fila vazia, último fim ofensivo e último término de falha. Só janelas inteiramente anteriores/posteriores são classificadas; janela que contém o marcador é categoria de fronteira. Isso não certifica equivalência a PRE nem ausência de anomalia da feature. Decompor EWMA no marcador: S_t=0,8^k S_m+contribuições reais posteriores, respeitando resets; essa identidade descreve memória, sem recalibrar ou simular outro detector. Não reconstruir CUSUM clássico.
