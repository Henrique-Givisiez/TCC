# Stage 15B — Frozen TEST Evaluation

Stage 15B FROZEN — ready for Stage 15C. Stage 15C permanece não autorizada e não foi iniciada.
Este relatório apresenta resultados descritivos de todas as 20 configurações primárias,
sem ordenação por desempenho, ranking, seleção de método/feature ou interpretação comparativa.

## Autoridades

Collection authority HEAD: `f27a5ae6117667f980f6de0217222d25da0e6e42`.
Stage 15A commit e execution HEAD/base da Stage 15B:
`0edd677d57dccb0bc0c2f513f039b68c21300c16`.
O código novo de avaliação é identificado por seus hashes exatos no manifesto.
O commit administrativo posterior e Git clean são registrados separadamente em
`experiment_results/stage15b-test-evaluation-20261019/administrative_finalization.json`.
Esse commit não substitui a autoridade histórica da coleta ou a autoria Stage15A.

| Autoridade | SHA256 |
|---|---|
| evaluation_protocol | `c2e1ab6314ab67c984b6b0e8f505982d72ea4de2f463e8607488e73c2764ef20` |
| four_method_freeze | `898e79394ac48a86a734100d324d0b6b966412166a0eac105dbdeccb2bd236f5` |
| provenance_bridge | `9c361e6b873dc39eb7d1d51de4c2b3476260aa25f4959ea126e0e07dd115c7a7` |
| stage15a_manifest | `089a25681dd13810a94a92def805aa9a7e314955ebdcca671d625d959ae3a9d5` |
| test_collection_freeze | `8d784758ff7b751f68dc595d434a65bae1d764d5a21312b0e3d96a5f6613327d` |
| test_inventory | `10ab05b24e9896d41e944192909f79b366e8cbbe7e08eb24f695b5d2ad1c2b47` |

Stage15B manifest SHA256:
`2b36134d60f9dd5a4dc5bd721f4c5df194cc8ad695ab5d71c73156b5bb5863ca`.
Stage15B freeze SHA256:
`8232ce397022963dd8741d7e14746630a822cdf74cda4f4a113d7ca5a974f2c2`.

## Cardinalidade e contratos

48 runs: 16 B, 16 C, 16 P; 16 seeds pareadas; 20 configurações primárias.
960 avaliações primárias run/configuração; 960 startup; 640 event-level C/P
(320 C e 320 P); 640 pós-evento. Sem duplicatas, ausências ou configurações extras.
Alpha=0.01; CoV L=6; EWMA lambda=0.2; CUSUM k=0.5.
Unidade experimental: run/seed. Janelas não são réplicas inferenciais independentes.

Avaliação primária [48,144), startup [0,48), somente janelas inteiras. Nenhum scoring
ou estado causal foi reiniciado/reexecutado. Boundary 0<overlap<1 fica fora da matriz;
unavailable fica fora dos denominadores e é contado por grupo de GT.
eligible_attack_windows e eligible_benign_windows contam decisões disponíveis em
janelas puras; attack_windows/benign_windows também registram o suporte GT original.
Boundary unavailable aparece em ambos os contadores diagnósticos, com contagem
separada por grupo para evitar dupla contagem na reconciliação do suporte.

Precision=TP/(TP+FP), Recall=TP/(TP+FN), FPR=FP/(FP+TN).
F1 segue a fórmula explícita do protocolo pré-TEST: 2TP/(2TP+FP+FN).
Cada métrica tem seu próprio denominador; null só quando ele é zero.
Assim, F1 pode ser zero pela fórmula de contagens mesmo quando Precision ou Recall
separadamente são undefined. Isso não é substituição de null por zero.
Em B, Recall é sempre null; não há evento/delay fictício.

A aritmética de contagens, razões e sumários usa frações exatas; a serialização e
raiz quadrada usam Decimal com 50 dígitos, ROUND_HALF_EVEN. CSV usa célula vazia
para null e colunas de motivo; evaluation_results.json preserva null explicitamente.
Nenhum arredondamento intermediário de métricas antecede os sumários.

## Leitura das tabelas

As células abaixo mostram **média ± SD amostral; n definido/16**. Undefined_n é
16−n e os arquivos machine-readable também identificam cada seed definida/undefined.
Arredondamento a quatro casas ocorre somente neste relatório. Mediana, mínimo,
máximo e valores completos estão em run_level_descriptive_summary.csv.
A ordem dos métodos/features é fixa e não depende de qualquer resultado.

Abreviações de feature: packets = ingress_packet_count; payload bytes =
ingress_tcp_payload_length_sum_bytes; request starts = request_starts;
duration ms = mean_duration_ms; CPU % = mean_cpu_percent.

## PRIMARY — B, benign-only

FPR é a métrica primária de B. Os valores individuais dos 16 runs por configuração,
com FP, TN e unavailable, estão em [FPR B por seed](stage15b_B_fpr_by_seed.md)
e window_metrics_per_run.csv. Precision/F1 são mostrados por completude contratual;
Recall permanece null.

| Configuração | Precision | Recall | F1 | FPR |
|---|---|---|---|---|
| Z-score / packets | 0.0000 ± 0.0000; 12/16 | null ± null; 0/16 | 0.0000 ± 0.0000; 12/16 | 0.0111 ± 0.0089; 16/16 |
| Z-score / payload bytes | 0.0000 ± 0.0000; 10/16 | null ± null; 0/16 | 0.0000 ± 0.0000; 10/16 | 0.0091 ± 0.0092; 16/16 |
| Z-score / request starts | 0.0000 ± 0.0000; 10/16 | null ± null; 0/16 | 0.0000 ± 0.0000; 10/16 | 0.0091 ± 0.0092; 16/16 |
| Z-score / duration ms | 0.0000 ± 0.0000; 10/16 | null ± null; 0/16 | 0.0000 ± 0.0000; 10/16 | 0.0104 ± 0.0101; 16/16 |
| Z-score / CPU % | 0.0000 ± 0.0000; 4/16 | null ± null; 0/16 | 0.0000 ± 0.0000; 4/16 | 0.0052 ± 0.0093; 16/16 |
| CoV L6 / packets | 0.0000 ± 0.0000; 10/16 | null ± null; 0/16 | 0.0000 ± 0.0000; 10/16 | 0.0195 ± 0.0204; 16/16 |
| CoV L6 / payload bytes | 0.0000 ± 0.0000; 9/16 | null ± null; 0/16 | 0.0000 ± 0.0000; 9/16 | 0.0189 ± 0.0219; 16/16 |
| CoV L6 / request starts | 0.0000 ± 0.0000; 9/16 | null ± null; 0/16 | 0.0000 ± 0.0000; 9/16 | 0.0189 ± 0.0219; 16/16 |
| CoV L6 / duration ms | 0.0000 ± 0.0000; 9/16 | null ± null; 0/16 | 0.0000 ± 0.0000; 9/16 | 0.0163 ± 0.0205; 16/16 |
| CoV L6 / CPU % | 0.0000 ± 0.0000; 3/16 | null ± null; 0/16 | 0.0000 ± 0.0000; 3/16 | 0.0046 ± 0.0114; 16/16 |
| EWMA .2 / packets | 0.0000 ± 0.0000; 8/16 | null ± null; 0/16 | 0.0000 ± 0.0000; 8/16 | 0.0143 ± 0.0211; 16/16 |
| EWMA .2 / payload bytes | 0.0000 ± 0.0000; 8/16 | null ± null; 0/16 | 0.0000 ± 0.0000; 8/16 | 0.0137 ± 0.0243; 16/16 |
| EWMA .2 / request starts | 0.0000 ± 0.0000; 7/16 | null ± null; 0/16 | 0.0000 ± 0.0000; 7/16 | 0.0137 ± 0.0246; 16/16 |
| EWMA .2 / duration ms | 0.0000 ± 0.0000; 5/16 | null ± null; 0/16 | 0.0000 ± 0.0000; 5/16 | 0.0052 ± 0.0093; 16/16 |
| EWMA .2 / CPU % | 0.0000 ± null; 1/16 | null ± null; 0/16 | 0.0000 ± null; 1/16 | 0.0007 ± 0.0026; 16/16 |
| CUSUM .5 / packets | 0.0000 ± 0.0000; 3/16 | null ± null; 0/16 | 0.0000 ± 0.0000; 3/16 | 0.0176 ± 0.0475; 16/16 |
| CUSUM .5 / payload bytes | 0.0000 ± 0.0000; 4/16 | null ± null; 0/16 | 0.0000 ± 0.0000; 4/16 | 0.0182 ± 0.0451; 16/16 |
| CUSUM .5 / request starts | 0.0000 ± 0.0000; 4/16 | null ± null; 0/16 | 0.0000 ± 0.0000; 4/16 | 0.0176 ± 0.0450; 16/16 |
| CUSUM .5 / duration ms | 0.0000 ± 0.0000; 3/16 | null ± null; 0/16 | 0.0000 ± 0.0000; 3/16 | 0.0065 ± 0.0152; 16/16 |
| CUSUM .5 / CPU % | null ± null; 0/16 | null ± null; 0/16 | null ± null; 0/16 | 0.0000 ± 0.0000; 16/16 |

## PRIMARY — C window-level

| Configuração | Precision | Recall | F1 | FPR |
|---|---|---|---|---|
| Z-score / packets | 0.9822 ± 0.0282; 15/16 | 0.5750 ± 0.1742; 16/16 | 0.7049 ± 0.1983; 16/16 | 0.0064 ± 0.0105; 16/16 |
| Z-score / payload bytes | 0.9880 ± 0.0207; 15/16 | 0.5089 ± 0.1610; 16/16 | 0.6526 ± 0.1880; 16/16 | 0.0042 ± 0.0076; 16/16 |
| Z-score / request starts | 0.9887 ± 0.0202; 16/16 | 0.5411 ± 0.0870; 16/16 | 0.6950 ± 0.0712; 16/16 | 0.0042 ± 0.0076; 16/16 |
| Z-score / duration ms | 0.7292 ± 0.3911; 12/16 | 0.0286 ± 0.0295; 16/16 | 0.0536 ± 0.0542; 16/16 | 0.0053 ± 0.0081; 16/16 |
| Z-score / CPU % | 0.9640 ± 0.0458; 16/16 | 0.4107 ± 0.1822; 16/16 | 0.5550 ± 0.1812; 16/16 | 0.0085 ± 0.0107; 16/16 |
| CoV L6 / packets | 0.2667 ± 0.3667; 9/16 | 0.0171 ± 0.0302; 15/16 | 0.0307 ± 0.0544; 15/16 | 0.0215 ± 0.0252; 15/16 |
| CoV L6 / payload bytes | 0.1759 ± 0.2550; 9/16 | 0.0133 ± 0.0262; 15/16 | 0.0236 ± 0.0464; 15/16 | 0.0282 ± 0.0305; 15/16 |
| CoV L6 / request starts | 0.1583 ± 0.2467; 10/16 | 0.0125 ± 0.0255; 16/16 | 0.0221 ± 0.0452; 16/16 | 0.0286 ± 0.0295; 16/16 |
| CoV L6 / duration ms | 0.1000 ± 0.2236; 5/16 | 0.0036 ± 0.0143; 16/16 | 0.0064 ± 0.0256; 16/16 | 0.0095 ± 0.0163; 16/16 |
| CoV L6 / CPU % | 0.5000 ± 0.5000; 3/16 | 0.0071 ± 0.0221; 16/16 | 0.0132 ± 0.0409; 16/16 | 0.0053 ± 0.0172; 16/16 |
| EWMA .2 / packets | 0.8668 ± 0.0424; 15/16 | 0.9357 ± 0.2496; 16/16 | 0.8693 ± 0.2329; 16/16 | 0.0869 ± 0.0405; 16/16 |
| EWMA .2 / payload bytes | 0.8776 ± 0.0402; 15/16 | 0.9321 ± 0.2491; 16/16 | 0.8735 ± 0.2341; 16/16 | 0.0784 ± 0.0365; 16/16 |
| EWMA .2 / request starts | 0.8710 ± 0.0468; 16/16 | 0.9929 ± 0.0165; 16/16 | 0.9273 ± 0.0292; 16/16 | 0.0890 ± 0.0369; 16/16 |
| EWMA .2 / duration ms | 0.9451 ± 0.0946; 16/16 | 0.5429 ± 0.2606; 16/16 | 0.6426 ± 0.2334; 16/16 | 0.0328 ± 0.0872; 16/16 |
| EWMA .2 / CPU % | 0.8904 ± 0.0417; 16/16 | 0.8482 ± 0.0846; 16/16 | 0.8659 ± 0.0490; 16/16 | 0.0636 ± 0.0306; 16/16 |
| CUSUM .5 / packets | 0.3710 ± 0.0028; 15/16 | 0.9321 ± 0.2488; 16/16 | 0.5066 ± 0.1352; 16/16 | 0.9375 ± 0.2500; 16/16 |
| CUSUM .5 / payload bytes | 0.3701 ± 0.0033; 15/16 | 0.9286 ± 0.2480; 16/16 | 0.5052 ± 0.1348; 16/16 | 0.9375 ± 0.2500; 16/16 |
| CUSUM .5 / request starts | 0.3702 ± 0.0032; 16/16 | 0.9911 ± 0.0137; 16/16 | 0.5391 ± 0.0055; 16/16 | 1.0000 ± 0.0000; 16/16 |
| CUSUM .5 / duration ms | 0.6462 ± 0.1740; 14/16 | 0.6107 ± 0.3345; 16/16 | 0.5431 ± 0.2462; 16/16 | 0.2775 ± 0.3200; 16/16 |
| CUSUM .5 / CPU % | 0.3190 ± 0.0210; 16/16 | 0.7679 ± 0.0884; 16/16 | 0.4502 ± 0.0342; 16/16 | 0.9703 ± 0.0723; 16/16 |

## PRIMARY — P window-level

| Configuração | Precision | Recall | F1 | FPR |
|---|---|---|---|---|
| Z-score / packets | 0.9493 ± 0.0719; 16/16 | 0.1946 ± 0.0628; 16/16 | 0.3186 ± 0.0901; 16/16 | 0.0064 ± 0.0085; 16/16 |
| Z-score / payload bytes | 0.9566 ± 0.0678; 16/16 | 0.1768 ± 0.0544; 16/16 | 0.2947 ± 0.0794; 16/16 | 0.0053 ± 0.0081; 16/16 |
| Z-score / request starts | 0.9566 ± 0.0678; 16/16 | 0.1750 ± 0.0551; 16/16 | 0.2921 ± 0.0802; 16/16 | 0.0053 ± 0.0081; 16/16 |
| Z-score / duration ms | 0.7778 ± 0.4410; 9/16 | 0.0179 ± 0.0253; 16/16 | 0.0340 ± 0.0473; 16/16 | 0.0042 ± 0.0116; 16/16 |
| Z-score / CPU % | 0.9700 ± 0.0797; 15/16 | 0.1786 ± 0.0805; 16/16 | 0.2932 ± 0.1246; 16/16 | 0.0042 ± 0.0116; 16/16 |
| CoV L6 / packets | 0.8593 ± 0.2904; 14/16 | 0.1518 ± 0.1224; 16/16 | 0.2400 ± 0.1726; 16/16 | 0.0138 ± 0.0285; 16/16 |
| CoV L6 / payload bytes | 0.8250 ± 0.3015; 14/16 | 0.1625 ± 0.1285; 16/16 | 0.2529 ± 0.1841; 16/16 | 0.0159 ± 0.0251; 16/16 |
| CoV L6 / request starts | 0.8250 ± 0.3015; 14/16 | 0.1625 ± 0.1285; 16/16 | 0.2529 ± 0.1841; 16/16 | 0.0159 ± 0.0251; 16/16 |
| CoV L6 / duration ms | 0.3810 ± 0.4880; 7/16 | 0.0107 ± 0.0230; 16/16 | 0.0201 ± 0.0432; 16/16 | 0.0085 ± 0.0175; 16/16 |
| CoV L6 / CPU % | 0.8182 ± 0.3686; 11/16 | 0.0804 ± 0.0796; 16/16 | 0.1386 ± 0.1349; 16/16 | 0.0085 ± 0.0223; 16/16 |
| EWMA .2 / packets | 0.9592 ± 0.0528; 16/16 | 0.6304 ± 0.1722; 16/16 | 0.7467 ± 0.1375; 16/16 | 0.0169 ± 0.0232; 16/16 |
| EWMA .2 / payload bytes | 0.9611 ± 0.0671; 16/16 | 0.5821 ± 0.1785; 16/16 | 0.7090 ± 0.1439; 16/16 | 0.0159 ± 0.0280; 16/16 |
| EWMA .2 / request starts | 0.9611 ± 0.0671; 16/16 | 0.5821 ± 0.1785; 16/16 | 0.7090 ± 0.1439; 16/16 | 0.0159 ± 0.0280; 16/16 |
| EWMA .2 / duration ms | 0.7667 ± 0.4172; 10/16 | 0.0393 ± 0.0520; 16/16 | 0.0711 ± 0.0915; 16/16 | 0.0064 ± 0.0174; 16/16 |
| EWMA .2 / CPU % | 0.9724 ± 0.0891; 14/16 | 0.1786 ± 0.1703; 16/16 | 0.2714 ± 0.2264; 16/16 | 0.0021 ± 0.0058; 16/16 |
| CUSUM .5 / packets | 0.4753 ± 0.1315; 16/16 | 0.8714 ± 0.1736; 16/16 | 0.6054 ± 0.1242; 16/16 | 0.6091 ± 0.2376; 16/16 |
| CUSUM .5 / payload bytes | 0.5405 ± 0.1464; 16/16 | 0.8750 ± 0.1666; 16/16 | 0.6570 ± 0.1316; 16/16 | 0.4831 ± 0.2374; 16/16 |
| CUSUM .5 / request starts | 0.5406 ± 0.1463; 16/16 | 0.8768 ± 0.1678; 16/16 | 0.6574 ± 0.1314; 16/16 | 0.4841 ± 0.2388; 16/16 |
| CUSUM .5 / duration ms | 0.8000 ± 0.4472; 5/16 | 0.0429 ± 0.0995; 16/16 | 0.0688 ± 0.1506; 16/16 | 0.0032 ± 0.0127; 16/16 |
| CUSUM .5 / CPU % | 0.7346 ± 0.2501; 8/16 | 0.1893 ± 0.2625; 16/16 | 0.2015 ± 0.2625; 16/16 | 0.0858 ± 0.1538; 16/16 |

## PRIMARY — event-level, C e P

Um único evento global por run C/P: [actual_start,actual_end), incluindo os silêncios
periódicos de P. drained_end não define o fim. Decisão positiva primária é elegível
por overlap da janela; available_at pode exceder actual_end. Detection time é o menor
available_at elegível; delay é detection_time−actual_start. Misses têm tempo/delay null.

Taxa = detected/16. Delay abaixo é média ± SD somente dos detectados, em segundos;
o número de detectados e de misses é explícito. Mediana/min/max e seeds estão em
event_descriptive_summary.csv; todos os tempos individuais, em event_metrics_per_run.csv.

| Configuração | C detectados | C misses | C taxa | C delay s | P detectados | P misses | P taxa | P delay s |
|---|---|---|---|---|---|---|---|---|
| Z-score / packets | 15/16 | 1 | 0.9375 | 1.2587 ± 0.5942 | 16/16 | 0 | 1.0000 | 2.1812 ± 3.4937 |
| Z-score / payload bytes | 15/16 | 1 | 0.9375 | 1.5254 ± 0.9154 | 16/16 | 0 | 1.0000 | 2.4312 ± 3.4135 |
| Z-score / request starts | 16/16 | 0 | 1.0000 | 1.6169 ± 0.9572 | 16/16 | 0 | 1.0000 | 2.4312 ± 3.4135 |
| Z-score / duration ms | 10/16 | 6 | 0.6250 | 19.2907 ± 12.7374 | 7/16 | 9 | 0.4375 | 18.0406 ± 14.1551 |
| Z-score / CPU % | 16/16 | 0 | 1.0000 | 6.0544 ± 3.7862 | 15/16 | 1 | 0.9375 | 10.4669 ± 8.9791 |
| CoV L6 / packets | 4/16 | 12 | 0.2500 | 1.2419 ± 0.5012 | 13/16 | 3 | 0.8125 | 9.1711 ± 8.8427 |
| CoV L6 / payload bytes | 4/16 | 12 | 0.2500 | 1.2419 ± 0.5012 | 13/16 | 3 | 0.8125 | 8.3250 ± 7.3152 |
| CoV L6 / request starts | 4/16 | 12 | 0.2500 | 1.2419 ± 0.5012 | 13/16 | 3 | 0.8125 | 8.3250 ± 7.3152 |
| CoV L6 / duration ms | 1/16 | 15 | 0.0625 | 0.9933 ± null | 3/16 | 13 | 0.1875 | 1.8560 ± 0.9548 |
| CoV L6 / CPU % | 2/16 | 14 | 0.1250 | 2.4904 ± 0.7046 | 11/16 | 5 | 0.6875 | 16.1277 ± 12.1075 |
| EWMA .2 / packets | 15/16 | 1 | 0.9375 | 1.7254 ± 0.5930 | 16/16 | 0 | 1.0000 | 2.3062 ± 2.0486 |
| EWMA .2 / payload bytes | 15/16 | 1 | 0.9375 | 1.9254 ± 0.7988 | 16/16 | 0 | 1.0000 | 2.3687 ± 2.0200 |
| EWMA .2 / request starts | 16/16 | 0 | 1.0000 | 1.9919 ± 0.8163 | 16/16 | 0 | 1.0000 | 2.3687 ± 2.0200 |
| EWMA .2 / duration ms | 16/16 | 0 | 1.0000 | 8.9919 ± 5.4403 | 8/16 | 8 | 0.5000 | 14.7709 ± 12.2053 |
| EWMA .2 / CPU % | 16/16 | 0 | 1.0000 | 6.3669 ± 2.0628 | 14/16 | 2 | 0.8750 | 16.3600 ± 8.4258 |
| CUSUM .5 / packets | 15/16 | 1 | 0.9375 | 2.0587 ± 0.5939 | 16/16 | 0 | 1.0000 | 3.5562 ± 2.8569 |
| CUSUM .5 / payload bytes | 15/16 | 1 | 0.9375 | 2.0587 ± 0.7996 | 16/16 | 0 | 1.0000 | 4.3062 ± 3.6932 |
| CUSUM .5 / request starts | 16/16 | 0 | 1.0000 | 2.0544 ± 0.7721 | 16/16 | 0 | 1.0000 | 4.2437 ± 3.7459 |
| CUSUM .5 / duration ms | 14/16 | 2 | 0.8750 | 10.4202 ± 7.6827 | 4/16 | 12 | 0.2500 | 13.1060 ± 13.9804 |
| CUSUM .5 / CPU % | 16/16 | 0 | 1.0000 | 10.1169 ± 3.0970 | 8/16 | 8 | 0.5000 | 21.6470 ± 8.5056 |

## POST_EVENT_DIAGNOSTIC — separado do FPR primário

Somente janelas inteiras em [max(actual_end,48),144). Alarm rate = positivos/decisões
disponíveis; unavailable é registrado separadamente e denominador zero gera null.
Não se usa drained_end. Cada run permanece identificado em post_event_metrics_per_run.csv.

| Configuração | C post-event alarm rate | P post-event alarm rate |
|---|---|---|
| Z-score / packets | 0.0064 ± 0.0105; 16/16 | 0.0064 ± 0.0085; 16/16 |
| Z-score / payload bytes | 0.0042 ± 0.0076; 16/16 | 0.0053 ± 0.0081; 16/16 |
| Z-score / request starts | 0.0042 ± 0.0076; 16/16 | 0.0053 ± 0.0081; 16/16 |
| Z-score / duration ms | 0.0053 ± 0.0081; 16/16 | 0.0042 ± 0.0116; 16/16 |
| Z-score / CPU % | 0.0085 ± 0.0107; 16/16 | 0.0042 ± 0.0116; 16/16 |
| CoV L6 / packets | 0.0215 ± 0.0252; 15/16 | 0.0138 ± 0.0285; 16/16 |
| CoV L6 / payload bytes | 0.0282 ± 0.0305; 15/16 | 0.0159 ± 0.0251; 16/16 |
| CoV L6 / request starts | 0.0286 ± 0.0295; 16/16 | 0.0159 ± 0.0251; 16/16 |
| CoV L6 / duration ms | 0.0095 ± 0.0163; 16/16 | 0.0085 ± 0.0175; 16/16 |
| CoV L6 / CPU % | 0.0053 ± 0.0172; 16/16 | 0.0085 ± 0.0223; 16/16 |
| EWMA .2 / packets | 0.0869 ± 0.0405; 16/16 | 0.0169 ± 0.0232; 16/16 |
| EWMA .2 / payload bytes | 0.0784 ± 0.0365; 16/16 | 0.0159 ± 0.0280; 16/16 |
| EWMA .2 / request starts | 0.0890 ± 0.0369; 16/16 | 0.0159 ± 0.0280; 16/16 |
| EWMA .2 / duration ms | 0.0328 ± 0.0872; 16/16 | 0.0064 ± 0.0174; 16/16 |
| EWMA .2 / CPU % | 0.0636 ± 0.0306; 16/16 | 0.0021 ± 0.0058; 16/16 |
| CUSUM .5 / packets | 0.9375 ± 0.2500; 16/16 | 0.6091 ± 0.2376; 16/16 |
| CUSUM .5 / payload bytes | 0.9375 ± 0.2500; 16/16 | 0.4831 ± 0.2374; 16/16 |
| CUSUM .5 / request starts | 1.0000 ± 0.0000; 16/16 | 0.4841 ± 0.2388; 16/16 |
| CUSUM .5 / duration ms | 0.2775 ± 0.3200; 16/16 | 0.0032 ± 0.0127; 16/16 |
| CUSUM .5 / CPU % | 0.9703 ± 0.0723; 16/16 | 0.0858 ± 0.1538; 16/16 |

## STARTUP_DIAGNOSTIC — separado, [0,48)

A tabela mostra FPR por run resumido. Contagens TP/FP/TN/FN, boundary, unavailable e
outras métricas de startup estão exclusivamente nos arquivos startup_diagnostic_per_run.csv
e startup_descriptive_summary.csv. Startup não foi somado ou misturado ao PRIMARY.

| Configuração | B startup FPR | C startup FPR | P startup FPR |
|---|---|---|---|
| Z-score / packets | 0.0195 ± 0.0246; 16/16 | 0.0143 ± 0.0147; 16/16 | 0.0169 ± 0.0190; 16/16 |
| Z-score / payload bytes | 0.0078 ± 0.0129; 16/16 | 0.0065 ± 0.0100; 16/16 | 0.0091 ± 0.0152; 16/16 |
| Z-score / request starts | 0.0078 ± 0.0129; 16/16 | 0.0065 ± 0.0100; 16/16 | 0.0091 ± 0.0152; 16/16 |
| Z-score / duration ms | 0.0026 ± 0.0071; 16/16 | 0.0066 ± 0.0101; 16/16 | 0.0130 ± 0.0168; 16/16 |
| Z-score / CPU % | 0.0027 ± 0.0109; 16/16 | 0.0000 ± 0.0000; 16/16 | 0.0027 ± 0.0109; 16/16 |
| CoV L6 / packets | 0.0145 ± 0.0280; 16/16 | 0.0258 ± 0.0644; 16/16 | 0.0087 ± 0.0167; 16/16 |
| CoV L6 / payload bytes | 0.0087 ± 0.0206; 16/16 | 0.0229 ± 0.0633; 16/16 | 0.0073 ± 0.0184; 16/16 |
| CoV L6 / request starts | 0.0087 ± 0.0206; 16/16 | 0.0174 ± 0.0429; 16/16 | 0.0073 ± 0.0184; 16/16 |
| CoV L6 / duration ms | 0.0196 ± 0.0394; 16/16 | 0.0163 ± 0.0316; 16/16 | 0.0132 ± 0.0240; 16/16 |
| CoV L6 / CPU % | 0.0030 ± 0.0122; 16/16 | 0.0091 ± 0.0216; 16/16 | 0.0076 ± 0.0247; 16/16 |
| EWMA .2 / packets | 0.0208 ± 0.0340; 16/16 | 0.0169 ± 0.0316; 16/16 | 0.0130 ± 0.0227; 16/16 |
| EWMA .2 / payload bytes | 0.0052 ± 0.0120; 16/16 | 0.0052 ± 0.0120; 16/16 | 0.0065 ± 0.0165; 16/16 |
| EWMA .2 / request starts | 0.0052 ± 0.0120; 16/16 | 0.0052 ± 0.0120; 16/16 | 0.0065 ± 0.0165; 16/16 |
| EWMA .2 / duration ms | 0.0052 ± 0.0121; 16/16 | 0.0331 ± 0.1162; 16/16 | 0.0013 ± 0.0052; 16/16 |
| EWMA .2 / CPU % | 0.0027 ± 0.0074; 16/16 | 0.0000 ± 0.0000; 16/16 | 0.0000 ± 0.0000; 16/16 |
| CUSUM .5 / packets | 0.0026 ± 0.0071; 16/16 | 0.0039 ± 0.0113; 16/16 | 0.0039 ± 0.0113; 16/16 |
| CUSUM .5 / payload bytes | 0.0000 ± 0.0000; 16/16 | 0.0000 ± 0.0000; 16/16 | 0.0000 ± 0.0000; 16/16 |
| CUSUM .5 / request starts | 0.0000 ± 0.0000; 16/16 | 0.0000 ± 0.0000; 16/16 | 0.0000 ± 0.0000; 16/16 |
| CUSUM .5 / duration ms | 0.0065 ± 0.0182; 16/16 | 0.0347 ± 0.1389; 16/16 | 0.0000 ± 0.0000; 16/16 |
| CUSUM .5 / CPU % | 0.0000 ± 0.0000; 16/16 | 0.0000 ± 0.0000; 16/16 | 0.0000 ± 0.0000; 16/16 |

## SUPPLEMENTARY_POOLED_WINDOWS

As tabelas seguintes somam primeiro TP/FP/TN/FN e só então calculam métricas.
Não são médias por run e não tratam janelas como réplicas independentes.
Resultados C e P permanecem separados.


### Pooled B — suplementar

| Configuração | TP | FP | TN | FN | Precision | Recall | F1 | FPR |
|---|---|---|---|---|---|---|---|---|
| Z-score / packets | 0 | 17 | 1519 | 0 | 0.0000 | null | 0.0000 | 0.0111 |
| Z-score / payload bytes | 0 | 14 | 1522 | 0 | 0.0000 | null | 0.0000 | 0.0091 |
| Z-score / request starts | 0 | 14 | 1522 | 0 | 0.0000 | null | 0.0000 | 0.0091 |
| Z-score / duration ms | 0 | 16 | 1520 | 0 | 0.0000 | null | 0.0000 | 0.0104 |
| Z-score / CPU % | 0 | 8 | 1528 | 0 | 0.0000 | null | 0.0000 | 0.0052 |
| CoV L6 / packets | 0 | 30 | 1506 | 0 | 0.0000 | null | 0.0000 | 0.0195 |
| CoV L6 / payload bytes | 0 | 29 | 1507 | 0 | 0.0000 | null | 0.0000 | 0.0189 |
| CoV L6 / request starts | 0 | 29 | 1507 | 0 | 0.0000 | null | 0.0000 | 0.0189 |
| CoV L6 / duration ms | 0 | 25 | 1511 | 0 | 0.0000 | null | 0.0000 | 0.0163 |
| CoV L6 / CPU % | 0 | 7 | 1529 | 0 | 0.0000 | null | 0.0000 | 0.0046 |
| EWMA .2 / packets | 0 | 22 | 1514 | 0 | 0.0000 | null | 0.0000 | 0.0143 |
| EWMA .2 / payload bytes | 0 | 21 | 1515 | 0 | 0.0000 | null | 0.0000 | 0.0137 |
| EWMA .2 / request starts | 0 | 21 | 1515 | 0 | 0.0000 | null | 0.0000 | 0.0137 |
| EWMA .2 / duration ms | 0 | 8 | 1528 | 0 | 0.0000 | null | 0.0000 | 0.0052 |
| EWMA .2 / CPU % | 0 | 1 | 1535 | 0 | 0.0000 | null | 0.0000 | 0.0007 |
| CUSUM .5 / packets | 0 | 27 | 1509 | 0 | 0.0000 | null | 0.0000 | 0.0176 |
| CUSUM .5 / payload bytes | 0 | 28 | 1508 | 0 | 0.0000 | null | 0.0000 | 0.0182 |
| CUSUM .5 / request starts | 0 | 27 | 1509 | 0 | 0.0000 | null | 0.0000 | 0.0176 |
| CUSUM .5 / duration ms | 0 | 10 | 1526 | 0 | 0.0000 | null | 0.0000 | 0.0065 |
| CUSUM .5 / CPU % | 0 | 0 | 1536 | 0 | null | null | null | 0.0000 |

### Pooled C — suplementar

| Configuração | TP | FP | TN | FN | Precision | Recall | F1 | FPR |
|---|---|---|---|---|---|---|---|---|
| Z-score / packets | 322 | 6 | 938 | 238 | 0.9817 | 0.5750 | 0.7252 | 0.0064 |
| Z-score / payload bytes | 285 | 4 | 940 | 275 | 0.9862 | 0.5089 | 0.6714 | 0.0042 |
| Z-score / request starts | 303 | 4 | 940 | 257 | 0.9870 | 0.5411 | 0.6990 | 0.0042 |
| Z-score / duration ms | 16 | 5 | 939 | 544 | 0.7619 | 0.0286 | 0.0551 | 0.0053 |
| Z-score / CPU % | 230 | 8 | 936 | 330 | 0.9664 | 0.4107 | 0.5764 | 0.0085 |
| CoV L6 / packets | 9 | 19 | 866 | 516 | 0.3214 | 0.0171 | 0.0325 | 0.0215 |
| CoV L6 / payload bytes | 7 | 25 | 860 | 518 | 0.2188 | 0.0133 | 0.0251 | 0.0282 |
| CoV L6 / request starts | 7 | 27 | 917 | 553 | 0.2059 | 0.0125 | 0.0236 | 0.0286 |
| CoV L6 / duration ms | 2 | 9 | 935 | 558 | 0.1818 | 0.0036 | 0.0070 | 0.0095 |
| CoV L6 / CPU % | 4 | 5 | 939 | 556 | 0.4444 | 0.0071 | 0.0141 | 0.0053 |
| EWMA .2 / packets | 524 | 82 | 862 | 36 | 0.8647 | 0.9357 | 0.8988 | 0.0869 |
| EWMA .2 / payload bytes | 522 | 74 | 870 | 38 | 0.8758 | 0.9321 | 0.9031 | 0.0784 |
| EWMA .2 / request starts | 556 | 84 | 860 | 4 | 0.8688 | 0.9929 | 0.9267 | 0.0890 |
| EWMA .2 / duration ms | 304 | 31 | 913 | 256 | 0.9075 | 0.5429 | 0.6793 | 0.0328 |
| EWMA .2 / CPU % | 475 | 60 | 884 | 85 | 0.8879 | 0.8482 | 0.8676 | 0.0636 |
| CUSUM .5 / packets | 522 | 885 | 59 | 38 | 0.3710 | 0.9321 | 0.5308 | 0.9375 |
| CUSUM .5 / payload bytes | 520 | 885 | 59 | 40 | 0.3701 | 0.9286 | 0.5293 | 0.9375 |
| CUSUM .5 / request starts | 555 | 944 | 0 | 5 | 0.3702 | 0.9911 | 0.5391 | 1.0000 |
| CUSUM .5 / duration ms | 342 | 262 | 682 | 218 | 0.5662 | 0.6107 | 0.5876 | 0.2775 |
| CUSUM .5 / CPU % | 430 | 916 | 28 | 130 | 0.3195 | 0.7679 | 0.4512 | 0.9703 |

### Pooled P — suplementar

| Configuração | TP | FP | TN | FN | Precision | Recall | F1 | FPR |
|---|---|---|---|---|---|---|---|---|
| Z-score / packets | 109 | 6 | 938 | 451 | 0.9478 | 0.1946 | 0.3230 | 0.0064 |
| Z-score / payload bytes | 99 | 5 | 939 | 461 | 0.9519 | 0.1768 | 0.2982 | 0.0053 |
| Z-score / request starts | 98 | 5 | 939 | 462 | 0.9515 | 0.1750 | 0.2956 | 0.0053 |
| Z-score / duration ms | 10 | 4 | 939 | 550 | 0.7143 | 0.0179 | 0.0348 | 0.0042 |
| Z-score / CPU % | 100 | 4 | 940 | 460 | 0.9615 | 0.1786 | 0.3012 | 0.0042 |
| CoV L6 / packets | 85 | 13 | 931 | 475 | 0.8673 | 0.1518 | 0.2584 | 0.0138 |
| CoV L6 / payload bytes | 91 | 15 | 929 | 469 | 0.8585 | 0.1625 | 0.2733 | 0.0159 |
| CoV L6 / request starts | 91 | 15 | 929 | 469 | 0.8585 | 0.1625 | 0.2733 | 0.0159 |
| CoV L6 / duration ms | 6 | 8 | 930 | 554 | 0.4286 | 0.0107 | 0.0209 | 0.0085 |
| CoV L6 / CPU % | 45 | 8 | 936 | 515 | 0.8491 | 0.0804 | 0.1468 | 0.0085 |
| EWMA .2 / packets | 353 | 16 | 928 | 207 | 0.9566 | 0.6304 | 0.7600 | 0.0169 |
| EWMA .2 / payload bytes | 326 | 15 | 929 | 234 | 0.9560 | 0.5821 | 0.7236 | 0.0159 |
| EWMA .2 / request starts | 326 | 15 | 929 | 234 | 0.9560 | 0.5821 | 0.7236 | 0.0159 |
| EWMA .2 / duration ms | 22 | 6 | 937 | 538 | 0.7857 | 0.0393 | 0.0748 | 0.0064 |
| EWMA .2 / CPU % | 100 | 2 | 942 | 460 | 0.9804 | 0.1786 | 0.3021 | 0.0021 |
| CUSUM .5 / packets | 488 | 575 | 369 | 72 | 0.4591 | 0.8714 | 0.6014 | 0.6091 |
| CUSUM .5 / payload bytes | 490 | 456 | 488 | 70 | 0.5180 | 0.8750 | 0.6507 | 0.4831 |
| CUSUM .5 / request starts | 491 | 457 | 487 | 69 | 0.5179 | 0.8768 | 0.6512 | 0.4841 |
| CUSUM .5 / duration ms | 24 | 3 | 940 | 536 | 0.8889 | 0.0429 | 0.0818 | 0.0032 |
| CUSUM .5 / CPU % | 106 | 81 | 863 | 454 | 0.5668 | 0.1893 | 0.2838 | 0.0858 |

## Integridade, reprodução e isolamento

Todos os hashes das autoridades, dos 960 outputs Stage15A e dos arquivos TEST/GT
foram verificados antes e depois da avaliação. Overlap Stage10 foi reconciliado
exatamente com os eventos originais Stage8, sem reconstruir ou alterar o dataset.
Os relógios e o vínculo Stage8→Stage9→Stage10 foram conferidos.

A segunda implementação não chama window_metrics, event_metrics, post_event_metrics,
aggregate ou describe da implementação publicadora. Usa conjuntos para a matriz,
deriva overlap do evento original e usa outra fórmula exata da variância. As duas
produziram todas as tabelas canônicas idênticas antes da publicação; uma passagem
posterior reproduziu os arquivos publicados, manifesto e freeze byte a byte.
As funções de detector, scorer, fitting, calibrator e decision policy são proibidas
por guard durante a avaliação. Somente os valores bool/null congelados entram no evaluator.

Suíte completa pré-avaliação: 540 testes, 539 passaram e 1 pós-publicação ainda não
aplicável. Depois da publicação, os 18 testes específicos passaram, incluindo esse
check antes não aplicável. Os logs ficam em experiment_results/stage15b-preflight-20261019.
Nenhum detector foi reexecutado sobre TEST; testes de regressão de detectores usaram fixtures sintéticas.

Entry 29/C permanece incluída nas 20 configurações, com dataset_valid=true e
analysis_eligible=true, sem alteração, exclusão, reponderação ou sensibilidade.
REQUEST_FAILURES_OBSERVED e EXPECTED_PHASE_OBSERVATIONS são metadata preservada.
Undefined não foi eliminado silenciosamente dos sumários.

Scores changed = NO; decisions changed = NO; thresholds changed = NO.
TEST fitting = NO; TEST calibration = NO; post-TEST tuning = NO.
GT consumed by scorer = NO; GT consumed by decision policy = NO;
GT consumed by evaluator = YES.
Ranking = NO; scientific interpretation = NO; hypothesis testing = NO.
Nenhuma feature/método foi selecionado e nenhuma matriz/seed/parâmetro foi alterado.

## Artefatos

Diretório: experiment_results/stage15b-test-evaluation-20261019/.

- `window_metrics_per_run.csv` — SHA256 `9597398f5ac8fa51369426314f9d03fa37c4a705f52d94b40e9885ddeeafbc61`.
- `event_metrics_per_run.csv` — SHA256 `e3c1401b0e0c737ae68684b0e3a2be5f85b681625033a5f409bcbe5b5717bd2a`.
- `post_event_metrics_per_run.csv` — SHA256 `d25c77ed8698b3229aeeedf8d4017a99a8595bcee09b82821c67267f8e17ddaf`.
- `startup_diagnostic_per_run.csv` — SHA256 `00242fb3ca2a681eabdfeb7a2912872ed43d92505102fb3b1b360ca9adfecfe9`.
- `window_metrics_pooled.csv` — SHA256 `1d8c9c664b88725013d8753f0a846413b3f751021011b605e4a3f18fa044ef75`.
- `run_level_descriptive_summary.csv` — SHA256 `83191265c06db6e0bc2725be0d60806a65536e00fa8a3a59da58774b8f3cddf4`.
- `event_descriptive_summary.csv` — SHA256 `7c8ec3c14bdf52c821b2634d5f5f179c08d67fc2dea23cf87e4d8bcb0c45c5de`.
- `startup_descriptive_summary.csv` — SHA256 `8f0bddb9eb648e5eed4f7649536c1717d502e0aeb920eac166d66f2e3abe9e0b`.
- `evaluation_results.json` — SHA256 `dbf190cd1d68e6ebed9acc71f9db44f598ba8637d58c90b3b9602c11a1bdb7c3`.
- `evaluation_inventory.json` — SHA256 `b9c325e9c8c0d7a3943797f7841579925cef6225c1a415eae61fd82bf6ce413b`.

O manifesto referencia esses outputs e as autoridades; o freeze referencia o
manifesto, inventory, semântica, código e hash do conjunto. Seus próprios hashes
ficam registrados externamente para evitar dependência circular.
O sidecar administrativo pós-commit não altera os artefatos científicos congelados.

Um único commit local: stage15: freeze primary test evaluation.
Push = NO. Stage 15C não iniciada. Parar para revisão humana.

## Respostas obrigatórias

| # | Verificação | Resultado |
|---|---|---|
| 1 | TEST collection freeze conferiu? | SIM |
| 2 | Stage 15A manifest conferiu? | SIM |
| 3 | Todos os 960 outputs Stage15A conferiram? | SIM |
| 4 | Evaluation protocol conferiu? | SIM |
| 5 | Scores alterados? | NÃO |
| 6 | Decisions alteradas? | NÃO |
| 7 | Thresholds alterados? | NÃO |
| 8 | Detector reexecutado sobre TEST? | NÃO |
| 9 | Decision policy reexecutada sobre TEST? | NÃO |
| 10 | GT entrou somente no evaluator? | SIM |
| 11 | Primary horizon [48,144)? | SIM |
| 12 | Startup [0,48)? | SIM |
| 13 | Boundary excluídas? | SIM |
| 14 | Unavailable preservado? | SIM |
| 15 | 960 combinações avaliadas? | SIM |
| 16 | B com 16 runs? | SIM |
| 17 | C com 16 runs? | SIM |
| 18 | P com 16 runs? | SIM |
| 19 | 16 seeds pareadas preservadas? | SIM |
| 20 | TP/FP/TN/FN calculados? | SIM |
| 21 | Precision quando definida? | SIM |
| 22 | Recall quando definido? | SIM |
| 23 | F1 quando definido pelo protocolo? | SIM |
| 24 | FPR quando definido? | SIM |
| 25 | Undefined permaneceu null? | SIM |
| 26 | B benign-only? | SIM |
| 27 | Eventos limitados a C/P? | SIM |
| 28 | Exatamente 640 avaliações event-level? | SIM |
| 29 | Event end = actual_end? | SIM |
| 30 | drained_end excluído da definição? | SIM |
| 31 | available_at posterior ao fim permitido com overlap? | SIM |
| 32 | Delay correto? | SIM |
| 33 | Missed event delay null? | SIM |
| 34 | P usou evento global incluindo silêncios? | SIM |
| 35 | Post-event separado? | SIM |
| 36 | Entry 29/C incluída? | SIM |
| 37 | Entry 29/C alterada? | NÃO |
| 38 | Pooled rotulado suplementar? | SIM |
| 39 | Unidade run/seed? | SIM |
| 40 | Ranking? | NÃO |
| 41 | Interpretação de melhor método? | NÃO |
| 42 | Teste de hipótese? | NÃO |
| 43 | Tuning pós-TEST? | NÃO |
| 44 | Recalibração? | NÃO |
| 45 | Alteração da matrix? | NÃO |
| 46 | Reprodução independente passou? | SIM |
| 47 | Manifest FROZEN? | SIM |
| 48 | Freeze materializado? | SIM |
| 49 | Git clean? | Registrado no sidecar pós-commit |
| 50 | Push? | NÃO |
| 51 | Pronto para Stage15C? | SIM; execução ainda não autorizada |
