# Consolidação descritiva da campanha científica reduzida — clock r2

Data: 30/10/2026. Consolidação de resultados já congelados. Nenhum experimento, ajuste, score, decisão ou intervalo foi produzido novamente. As tabelas transcrevem estimativas e ICs existentes; somas de denominadores servem apenas à descrição.

## Proveniência e integridade

Plano: `experiments/protocols/scientific_reduced_clock_r2_20261029/plan.json`; SHA256 `6240452e214b0748b023a084edd6dcf4fd2fd0a43744ed70a37bdb88a4319bc4`. TEST: `690c7d9af50204d7170fbb08ee61dd672450d2d5dd7e8c0a1de9725669601912`.
- BASELINE: `389a6676d9966a2ec0c93269d0926081b16009a469877dc0a92bd83aee850118`; slots esperados 4, recibos 4; predecessor None.
- CAL_A: `2b0fbb2bed70548705d3d4f188e416e3ff6c104d4773556ee12a05a00d07654e`; slots esperados 8, recibos 8; predecessor {'manifest_sha256': '389a6676d9966a2ec0c93269d0926081b16009a469877dc0a92bd83aee850118', 'path': '/home/henrique-givisiez/Documents/Faculdade/TCC/TCC/experiment_results/scientific-reduced-clock-r2-20261029/checkpoints/BASELINE'}.
- CAL_B: `f0c343a50fa1283d12a0768ccb1b647a044daf128dbb8950d3e1bb5f98774330`; slots esperados 8, recibos 8; predecessor {'manifest_sha256': '2b0fbb2bed70548705d3d4f188e416e3ff6c104d4773556ee12a05a00d07654e', 'path': '/home/henrique-givisiez/Documents/Faculdade/TCC/TCC/experiment_results/scientific-reduced-clock-r2-20261029/checkpoints/CAL_A'}.
- TEST: `690c7d9af50204d7170fbb08ee61dd672450d2d5dd7e8c0a1de9725669601912`; slots esperados 36, recibos 36; predecessor {'manifest_sha256': 'f0c343a50fa1283d12a0768ccb1b647a044daf128dbb8950d3e1bb5f98774330', 'path': '/home/henrique-givisiez/Documents/Faculdade/TCC/TCC/experiment_results/scientific-reduced-clock-r2-20261029/checkpoints/CAL_B'}.

Grafo conferido por SHA256: 531 manifests e 12507 arquivos referenciados (incluindo saídas, autoridades e evidências com hash). A conferência não executa o runtime nem revalida o ambiente Docker atual.

## Execuções, substituições e atrição

56 slots científicos: BASELINE 4/4, CAL-A 8/8, CAL-B 8/8 e TEST 36/36. TEST contém 12 blocos com C16/M16/E16: 12 trios completos e 12 pares por contraste de cenários. Ausências e atrição TEST no resumo: nenhuma. O histórico anterior à revisão r2 contém uma tentativa BASELINE consumida por falha técnica de relógio (PRE_RELEASE_CLOCK_FAILURE), preservada pelo handoff; não é um evento TEST nem um miss.

Contagem dos registros do diário: `{"HANDOFF_IMPORTED": 1, "TECHNICAL_FAILURE": 1, "REPLACEMENT_APPROVED": 1, "ATTEMPT_CONSUMED": 56, "COLLECTION_ACCEPTED": 56, "IDLE_WAIT": 55, "PARTITION_COMPLETE": 4}`.

## Limiares e aprovação

CAL-A e CAL-B usaram oito execuções C16 cada. Todas as cinco features foram elegíveis e os quatro métodos foram aceitos em CAL-B (20/20). Valores exatos e diagnósticos constam em calibration.json, anexo descritivo.

| Feature | Método | Limiar congelado | CAL-A elegível | CAL-B aceito |
|---|---|---:|---|---|
| ingress_packet_count | cov | 0.46079985260600100079608569657859004721894552405793 | True | True |
| ingress_packet_count | cusum-freeze | 4.7534135521051310484084293190426037846466912313418 | True | True |
| ingress_packet_count | ewma | 0.86399411324763987844351295623461228962136549040651 | True | True |
| ingress_packet_count | zscore | 2.5438355886237048130356729816607110859730634016742 | True | True |
| ingress_tcp_payload_length_sum_bytes | cov | 0.44020197384584474143454651345384011981622158951588 | True | True |
| ingress_tcp_payload_length_sum_bytes | cusum-freeze | 4.1810379417364068702144906215998435444777211908531 | True | True |
| ingress_tcp_payload_length_sum_bytes | ewma | 0.82466447268624497843620278070622583381989337165747 | True | True |
| ingress_tcp_payload_length_sum_bytes | zscore | 2.4933522219970410043797923314800316362849086359313 | True | True |
| mean_cpu_percent | cov | 0.47630396497758366193134151234160175807132760720142 | True | True |
| mean_cpu_percent | cusum-freeze | 11.466426774939642531856782455506907938976350209928 | True | True |
| mean_cpu_percent | ewma | 1.3501093932566738364805615359642204654611732717045 | True | True |
| mean_cpu_percent | zscore | 2.5216858495483782033932651178999064813134306404073 | True | True |
| mean_duration_ms | cov | 0.29368628522741678887284617825734779536663446046100 | True | True |
| mean_duration_ms | cusum-freeze | 4.0477809223542414988356195108189451497931266422899 | True | True |
| mean_duration_ms | ewma | 0.82485080672580389434373034538984648535796274525796 | True | True |
| mean_duration_ms | zscore | 2.1094783961845080703403979673909053506528569394976 | True | True |
| request_starts | cov | 0.44020197384584474143454651345384011981622158951587 | True | True |
| request_starts | cusum-freeze | 4.1861698462144926396433648224771135026908928724107 | True | True |
| request_starts | ewma | 0.82184252009581843527280039729381922348026907952272 | True | True |
| request_starts | zscore | 2.4942020900355666831699134911877789299516876780782 | True | True |

## Feature primária: request_starts

Detecção é a presença de ao menos um alarme disponível dentro do horizonte do evento; seu denominador é o número de eventos avaliados. FPR é FP/(FP+TN) em janelas benignas disponíveis, agregada como média por bloco. A fração de execuções com qualquer falso alarme tem denominador de execuções, não de janelas. Recall é TP/(TP+FN) por janela ofensiva, não probabilidade de detectar o evento. C16 não contém evento ofensivo: detecção, misses e atraso não se aplicam. Atraso condiciona à detecção e exige ao menos oito detecções para IC.

| Cenário/método | Eventos detectados / avaliados; misses | Detecção [IC95%] | FPR por janela [IC95%] | Execuções com falso alarme [IC95%] | Atraso condicional s [IC95%] | Recall por janela [IC95%] |
|---|---|---|---|---|---|---|
| C16/cov | não aplicável; não aplicável | não avaliado | 0.0106481 [0.00717593, 0.0173611]; n=12 | 0.916667 [0.64612, 0.985135]; n=12 | indefinido [IC indisponível]; n=0 | indefinido [IC indisponível]; n=0 |
| C16/cusum-freeze | não aplicável; não aplicável | não avaliado | 0.00578704 [0.00300926, 0.00856481]; n=12 | 0.75 [0.467695, 0.911058]; n=12 | indefinido [IC indisponível]; n=0 | indefinido [IC indisponível]; n=0 |
| C16/ewma | não aplicável; não aplicável | não avaliado | 0.0111111 [0.00717593, 0.0155093]; n=12 | 1 [0.735352, 1]; n=12 | indefinido [IC indisponível]; n=0 | indefinido [IC indisponível]; n=0 |
| C16/zscore | não aplicável; não aplicável | não avaliado | 0.00740741 [0.00486111, 0.00972222]; n=12 | 0.916667 [0.64612, 0.985135]; n=12 | indefinido [IC indisponível]; n=0 | indefinido [IC indisponível]; n=0 |
| E16/cov | 6/12; 6 | 0.5 [0.253782, 0.746218]; n=12 | 0.0154158 [0.0121627, 0.0226826]; n=12 | 1 [0.735352, 1]; n=12 | 1.32815 [IC indisponível]; n=6 | 0.014539 [0.00638513, 0.0251579]; n=12 |
| E16/cusum-freeze | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.00900207 [0.00529778, 0.0135335]; n=12 | 0.833333 [0.551969, 0.953035]; n=12 | 1.41127 [1.16108, 1.66297]; n=12 | 0.97205 [0.965873, 0.978312]; n=12 |
| E16/ewma | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0340536 [0.0278698, 0.0403971]; n=12 | 1 [0.735352, 1]; n=12 | 1.4946 [1.24311, 1.74571]; n=12 | 1 [0.60795, 1]; n=12 |
| E16/zscore | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.00849716 [0.00493103, 0.0121176]; n=12 | 0.75 [0.467695, 0.911058]; n=12 | 0.994603 [0.992932, 0.995961]; n=12 | 0.828471 [0.794576, 0.857634]; n=12 |
| M16/cov | 6/12; 6 | 0.5 [0.253782, 0.746218]; n=12 | 0.0212692 [0.014993, 0.0303347]; n=12 | 0.916667 [0.64612, 0.985135]; n=12 | 1.32737 [IC indisponível]; n=6 | 0.00770308 [0.0035014, 0.0140056]; n=12 |
| M16/cusum-freeze | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.00767085 [0.00348675, 0.013947]; n=12 | 0.666667 [0.390622, 0.86188]; n=12 | 1.41027 [1.15996, 1.7422]; n=12 | 0.978291 [0.973389, 0.983193]; n=12 |
| M16/ewma | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0383543 [0.0306834, 0.0460251]; n=12 | 1 [0.735352, 1]; n=12 | 1.4936 [1.24245, 1.74489]; n=12 | 1 [0.60795, 1]; n=12 |
| M16/zscore | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0104603 [0.00627615, 0.0146444]; n=12 | 0.833333 [0.551969, 0.953035]; n=12 | 0.993603 [0.992023, 0.995354]; n=12 | 0.822129 [0.786415, 0.845238]; n=12 |

Denominadores e contagens por janela, somados apenas para documentação (não substituem as médias por bloco):

| Cenário/método | FP / benignas disponíveis | TP / ofensivas disponíveis | POST positivas / disponíveis | Indisponíveis |
|---|---|---|---|---|
| C16/cov | 46 / 4320 | 0 / 0 | 0 / 0 | 0 |
| C16/cusum-freeze | 25 / 4320 | 0 / 0 | 0 / 0 | 0 |
| C16/ewma | 48 / 4320 | 0 / 0 | 0 / 0 | 0 |
| C16/zscore | 32 / 4320 | 0 / 0 | 0 / 0 | 0 |
| M16/cov | 61 / 2868 | 11 / 1428 | 31 / 1428 | 0 |
| M16/cusum-freeze | 22 / 2868 | 1397 / 1428 | 10 / 1428 | 0 |
| M16/ewma | 110 / 2868 | 1428 / 1428 | 85 / 1428 | 0 |
| M16/zscore | 30 / 2868 | 1174 / 1428 | 13 / 1428 | 0 |
| E16/cov | 51 / 3326 | 12 / 970 | 30 / 1886 | 0 |
| E16/cusum-freeze | 30 / 3326 | 944 / 970 | 18 / 1886 | 0 |
| E16/ewma | 114 / 3326 | 970 / 970 | 90 / 1886 | 0 |
| E16/zscore | 29 / 3326 | 795 / 970 | 16 / 1886 | 0 |

CUSUM-freeze, EWMA e z-score detectaram todos os 12 eventos de cada cenário ofensivo na feature primária; CoV perdeu seis em cada cenário. O IC de atraso de CoV não está disponível, pois há apenas seis detecções.

## Outras quatro features

As combinações são apresentadas por dimensão e cenário, sem ranking conjunto. Detecção completa não implica baixo FPR, alta cobertura por janela ou baixo atraso.

### ingress_packet_count

| Cenário/método | Eventos detectados / avaliados; misses | Detecção [IC95%] | FPR por janela [IC95%] | Execuções com falso alarme [IC95%] | Atraso condicional s [IC95%] | Recall por janela [IC95%] |
|---|---|---|---|---|---|---|
| C16/cov | não aplicável; não aplicável | não avaliado | 0.0162037 [0.0104167, 0.0240741]; n=12 | 1 [0.735352, 1]; n=12 | indefinido [IC indisponível]; n=0 | indefinido [IC indisponível]; n=0 |
| C16/cusum-freeze | não aplicável; não aplicável | não avaliado | 0.00462963 [0.0025463, 0.00671296]; n=12 | 0.75 [0.467695, 0.911058]; n=12 | indefinido [IC indisponível]; n=0 | indefinido [IC indisponível]; n=0 |
| C16/ewma | não aplicável; não aplicável | não avaliado | 0.00925926 [0.00578704, 0.0138889]; n=12 | 0.916667 [0.64612, 0.985135]; n=12 | indefinido [IC indisponível]; n=0 | indefinido [IC indisponível]; n=0 |
| C16/zscore | não aplicável; não aplicável | não avaliado | 0.00856481 [0.00601852, 0.0111111]; n=12 | 0.916667 [0.64612, 0.985135]; n=12 | indefinido [IC indisponível]; n=0 | indefinido [IC indisponível]; n=0 |
| E16/cov | 10/12; 2 | 0.833333 [0.551969, 0.953035]; n=12 | 0.0260921 [0.0222847, 0.0342867]; n=12 | 1 [0.735352, 1]; n=12 | 1.29421 [1.09376, 1.59472]; n=10 | 0.0171092 [0.00933489, 0.0250263]; n=12 |
| E16/cusum-freeze | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0158189 [0.0131244, 0.0190982]; n=12 | 1 [0.735352, 1]; n=12 | 1.4946 [1.24449, 1.74494]; n=12 | 0.979408 [0.969828, 0.987283]; n=12 |
| E16/ewma | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.054723 [0.0491892, 0.0615228]; n=12 | 1 [0.735352, 1]; n=12 | 1.57794 [1.24526, 1.99483]; n=12 | 0.999064 [0.995318, 1]; n=12 |
| E16/zscore | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0181754 [0.0134651, 0.0235611]; n=12 | 1 [0.735352, 1]; n=12 | 0.994603 [0.992932, 0.995961]; n=12 | 0.911056 [0.888425, 0.934565]; n=12 |
| M16/cov | 7/12; 5 | 0.583333 [0.319511, 0.80674]; n=12 | 0.0254533 [0.0188285, 0.0369596]; n=12 | 1 [0.735352, 1]; n=12 | 1.13623 [IC indisponível]; n=7 | 0.00840336 [0.0035014, 0.0140056]; n=12 |
| M16/cusum-freeze | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.00627615 [0.00313808, 0.011855]; n=12 | 0.666667 [0.390622, 0.86188]; n=12 | 1.32694 [1.07723, 1.6601]; n=12 | 0.977591 [0.971989, 0.981793]; n=12 |
| M16/ewma | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0366109 [0.0282427, 0.0460251]; n=12 | 1 [0.735352, 1]; n=12 | 1.4936 [1.16085, 1.91077]; n=12 | 0.9993 [0.996499, 1]; n=12 |
| M16/zscore | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0097629 [0.00592748, 0.0142957]; n=12 | 0.833333 [0.551969, 0.953035]; n=12 | 0.993603 [0.992023, 0.995354]; n=12 | 0.834734 [0.79902, 0.859244]; n=12 |

### ingress_tcp_payload_length_sum_bytes

| Cenário/método | Eventos detectados / avaliados; misses | Detecção [IC95%] | FPR por janela [IC95%] | Execuções com falso alarme [IC95%] | Atraso condicional s [IC95%] | Recall por janela [IC95%] |
|---|---|---|---|---|---|---|
| C16/cov | não aplicável; não aplicável | não avaliado | 0.0108796 [0.00740741, 0.0178241]; n=12 | 0.916667 [0.64612, 0.985135]; n=12 | indefinido [IC indisponível]; n=0 | indefinido [IC indisponível]; n=0 |
| C16/cusum-freeze | não aplicável; não aplicável | não avaliado | 0.00578704 [0.00300926, 0.00856481]; n=12 | 0.75 [0.467695, 0.911058]; n=12 | indefinido [IC indisponível]; n=0 | indefinido [IC indisponível]; n=0 |
| C16/ewma | não aplicável; não aplicável | não avaliado | 0.0104167 [0.00694444, 0.0145833]; n=12 | 1 [0.735352, 1]; n=12 | indefinido [IC indisponível]; n=0 | indefinido [IC indisponível]; n=0 |
| C16/zscore | não aplicável; não aplicável | não avaliado | 0.00740741 [0.00486111, 0.00972222]; n=12 | 0.916667 [0.64612, 0.985135]; n=12 | indefinido [IC indisponível]; n=0 | indefinido [IC indisponível]; n=0 |
| E16/cov | 6/12; 6 | 0.5 [0.253782, 0.746218]; n=12 | 0.0151213 [0.0120442, 0.0212916]; n=12 | 1 [0.735352, 1]; n=12 | 1.32815 [IC indisponível]; n=6 | 0.014539 [0.00638513, 0.0251579]; n=12 |
| E16/cusum-freeze | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.00834847 [0.00506364, 0.0126456]; n=12 | 0.833333 [0.551969, 0.953035]; n=12 | 1.41127 [1.16108, 1.66297]; n=12 | 0.97356 [0.966777, 0.979292]; n=12 |
| E16/ewma | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0346589 [0.0287232, 0.041089]; n=12 | 1 [0.735352, 1]; n=12 | 1.4946 [1.24311, 1.74571]; n=12 | 1 [0.60795, 1]; n=12 |
| E16/zscore | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.00849716 [0.00493103, 0.0121176]; n=12 | 0.75 [0.467695, 0.911058]; n=12 | 0.994603 [0.992932, 0.995961]; n=12 | 0.882446 [0.857572, 0.906718]; n=12 |
| M16/cov | 6/12; 6 | 0.5 [0.253782, 0.746218]; n=12 | 0.0212692 [0.014993, 0.0303347]; n=12 | 0.916667 [0.64612, 0.985135]; n=12 | 1.32737 [IC indisponível]; n=6 | 0.00770308 [0.0035014, 0.0140056]; n=12 |
| M16/cusum-freeze | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.00767085 [0.00348675, 0.013947]; n=12 | 0.666667 [0.390622, 0.86188]; n=12 | 1.41027 [1.15996, 1.7422]; n=12 | 0.978992 [0.97409, 0.983894]; n=12 |
| M16/ewma | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0373082 [0.0292887, 0.0453278]; n=12 | 1 [0.735352, 1]; n=12 | 1.4936 [1.24245, 1.74489]; n=12 | 1 [0.60795, 1]; n=12 |
| M16/zscore | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0104603 [0.00627615, 0.0146444]; n=12 | 0.833333 [0.551969, 0.953035]; n=12 | 0.993603 [0.992023, 0.995354]; n=12 | 0.820728 [0.782913, 0.843838]; n=12 |

### mean_cpu_percent

| Cenário/método | Eventos detectados / avaliados; misses | Detecção [IC95%] | FPR por janela [IC95%] | Execuções com falso alarme [IC95%] | Atraso condicional s [IC95%] | Recall por janela [IC95%] |
|---|---|---|---|---|---|---|
| C16/cov | não aplicável; não aplicável | não avaliado | 0.0166667 [0.0111111, 0.0222222]; n=12 | 0.916667 [0.64612, 0.985135]; n=12 | indefinido [IC indisponível]; n=0 | indefinido [IC indisponível]; n=0 |
| C16/cusum-freeze | não aplicável; não aplicável | não avaliado | 0.00138889 [0.000231481, 0.00462963]; n=12 | 0.25 [0.0889417, 0.532305]; n=12 | indefinido [IC indisponível]; n=0 | indefinido [IC indisponível]; n=0 |
| C16/ewma | não aplicável; não aplicável | não avaliado | 0.00462963 [0.00138889, 0.0133328]; n=12 | 0.333333 [0.13812, 0.609378]; n=12 | indefinido [IC indisponível]; n=0 | indefinido [IC indisponível]; n=0 |
| C16/zscore | não aplicável; não aplicável | não avaliado | 0.00972222 [0.00648148, 0.0134259]; n=12 | 0.916667 [0.64612, 0.985135]; n=12 | indefinido [IC indisponível]; n=0 | indefinido [IC indisponível]; n=0 |
| E16/cov | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0246878 [0.0209627, 0.0324645]; n=12 | 1 [0.735352, 1]; n=12 | 2.9946 [2.99293, 2.99596]; n=12 | 0.0553361 [0.0471592, 0.0668519]; n=12 |
| E16/cusum-freeze | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0187935 [0.0157354, 0.0244001]; n=12 | 1 [0.735352, 1]; n=12 | 2.9946 [2.99293, 2.99596]; n=12 | 0.985257 [0.98133, 0.987917]; n=12 |
| E16/ewma | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0703805 [0.0647, 0.0751756]; n=12 | 1 [0.735352, 1]; n=12 | 2.9946 [2.99293, 2.99596]; n=12 | 0.986368 [0.983425, 0.988471]; n=12 |
| E16/zscore | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0261602 [0.021257, 0.0315]; n=12 | 1 [0.735352, 1]; n=12 | 2.9946 [2.99293, 2.99596]; n=12 | 0.986368 [0.983425, 0.988471]; n=12 |
| M16/cov | 4/12; 8 | 0.333333 [0.13812, 0.609378]; n=12 | 0.0264993 [0.0153417, 0.0460251]; n=12 | 0.833333 [0.551969, 0.953035]; n=12 | 2.99361 [IC indisponível]; n=4 | 0.00490196 [0.00140056, 0.0112045]; n=12 |
| M16/cusum-freeze | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0142957 [0.00871688, 0.0233612]; n=12 | 0.916667 [0.64612, 0.985135]; n=12 | 6.9936 [6.32535, 8.16041]; n=12 | 0.942577 [0.933473, 0.95028]; n=12 |
| M16/ewma | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0303347 [0.0254533, 0.0414923]; n=12 | 1 [0.735352, 1]; n=12 | 5.41027 [4.82612, 6.82588]; n=12 | 0.969188 [0.958683, 0.97479]; n=12 |
| M16/zscore | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0122036 [0.0069735, 0.0174338]; n=12 | 0.75 [0.467695, 0.911058]; n=12 | 4.16027 [3.32703, 5.65921]; n=12 | 0.808824 [0.782913, 0.837535]; n=12 |

### mean_duration_ms

| Cenário/método | Eventos detectados / avaliados; misses | Detecção [IC95%] | FPR por janela [IC95%] | Execuções com falso alarme [IC95%] | Atraso condicional s [IC95%] | Recall por janela [IC95%] |
|---|---|---|---|---|---|---|
| C16/cov | não aplicável; não aplicável | não avaliado | 0.0150463 [0.0099537, 0.0196759]; n=12 | 0.916667 [0.64612, 0.985135]; n=12 | indefinido [IC indisponível]; n=0 | indefinido [IC indisponível]; n=0 |
| C16/cusum-freeze | não aplicável; não aplicável | não avaliado | 0.00439815 [0.00300926, 0.00648148]; n=12 | 0.833333 [0.551969, 0.953035]; n=12 | indefinido [IC indisponível]; n=0 | indefinido [IC indisponível]; n=0 |
| C16/ewma | não aplicável; não aplicável | não avaliado | 0.00740741 [0.00509259, 0.0099537]; n=12 | 0.916667 [0.64612, 0.985135]; n=12 | indefinido [IC indisponível]; n=0 | indefinido [IC indisponível]; n=0 |
| C16/zscore | não aplicável; não aplicável | não avaliado | 0.0108796 [0.00787037, 0.0141204]; n=12 | 1 [0.735352, 1]; n=12 | indefinido [IC indisponível]; n=0 | indefinido [IC indisponível]; n=0 |
| E16/cov | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0360744 [0.0285104, 0.0439859]; n=12 | 1 [0.735352, 1]; n=12 | 0.994603 [0.992932, 0.995961]; n=12 | 0.528629 [0.472375, 0.595446]; n=12 |
| E16/cusum-freeze | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0119005 [0.00859769, 0.0141613]; n=12 | 0.916667 [0.64612, 0.985135]; n=12 | 0.994603 [0.992932, 0.995961]; n=12 | 1 [0.60795, 1]; n=12 |
| E16/ewma | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.117528 [0.106916, 0.128447]; n=12 | 1 [0.735352, 1]; n=12 | 0.994603 [0.992932, 0.995961]; n=12 | 1 [0.60795, 1]; n=12 |
| E16/zscore | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0227594 [0.0171887, 0.0279935]; n=12 | 1 [0.735352, 1]; n=12 | 0.994603 [0.992932, 0.995961]; n=12 | 1 [0.60795, 1]; n=12 |
| M16/cov | 0/12; 12 | 0 [0, 0.264648]; n=12 | 0.0163877 [0.0115063, 0.0247559]; n=12 | 1 [0.735352, 1]; n=12 | indefinido [IC indisponível]; n=0 | 0 [0, 0.39205]; n=12 |
| M16/cusum-freeze | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0083682 [0.0041841, 0.0177824]; n=12 | 0.666667 [0.390622, 0.86188]; n=12 | 5.32694 [4.32868, 6.5773]; n=12 | 0.752101 [0.706583, 0.784314]; n=12 |
| M16/ewma | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0219665 [0.0132497, 0.0373082]; n=12 | 0.833333 [0.551969, 0.953035]; n=12 | 5.66027 [4.24312, 7.94754]; n=12 | 0.95098 [0.919468, 0.969888]; n=12 |
| M16/zscore | 12/12; 0 | 1 [0.735352, 1]; n=12 | 0.0135983 [0.0097629, 0.0167364]; n=12 | 1 [0.735352, 1]; n=12 | 10.0769 [6.07622, 15.9935]; n=12 | 0.114846 [0.10084, 0.126751]; n=12 |

## Serviço e infraestrutura

Médias e IC95% já existentes por bloco TEST; CPU usa a escala Docker e pode exceder 100%. Sucesso e timeouts usam coortes de requisições, enquanto taxas terminais contam conclusões no intervalo. Duração inclui separadamente todas as conclusões e apenas 2xx. PRE, ACTIVE e POST são mantidos separados. Percentis p50/p95 são individuais e estão no anexo individual_runs.json, sem média ou IC de percentis.

| Cenário | Fase/métrica | Estimativa [IC95%]; denominador em blocos |
|---|---|---|
| C16 | ACTIVE/aged_pending_at_end | 0 [IC indisponível]; n=12 |
| C16 | ACTIVE/failure_or_deadline_miss_fraction | 0 [0, 0.39205]; n=12 |
| C16 | ACTIVE/mean_2xx_ms | 30.6238 [30.431, 30.8362]; n=12 |
| C16 | ACTIVE/mean_all_ms | 30.6238 [30.431, 30.8362]; n=12 |
| C16 | ACTIVE/mean_cpu_docker_percent | 20.6352 [20.2043, 21.058]; n=12 |
| C16 | ACTIVE/pending_at_end | 0.416667 [0.166667, 0.916667]; n=12 |
| C16 | ACTIVE/start_rps | 15.8618 [15.6639, 16.0549]; n=12 |
| C16 | ACTIVE/success_fraction | 1 [0.60795, 1]; n=12 |
| C16 | ACTIVE/terminal_2xx_rps | 15.8604 [15.6625, 16.0521]; n=12 |
| C16 | ACTIVE/terminal_rps | 15.8604 [15.6625, 16.0521]; n=12 |
| C16 | ACTIVE/timeout_fraction | 0 [0, 0.39205]; n=12 |
| C16 | POST/aged_pending_at_end | 0 [IC indisponível]; n=12 |
| C16 | POST/failure_or_deadline_miss_fraction | 0 [0, 0.39205]; n=12 |
| C16 | POST/mean_2xx_ms | 30.5403 [30.1805, 30.95]; n=12 |
| C16 | POST/mean_all_ms | 30.5403 [30.1805, 30.95]; n=12 |
| C16 | POST/mean_cpu_docker_percent | 20.746 [20.1744, 21.4323]; n=12 |
| C16 | POST/pending_at_end | 0.333333 [0.0833333, 0.833333]; n=12 |
| C16 | POST/start_rps | 15.9785 [15.6736, 16.1597]; n=12 |
| C16 | POST/success_fraction | 1 [0.60795, 1]; n=12 |
| C16 | POST/terminal_2xx_rps | 15.9792 [15.6764, 16.1583]; n=12 |
| C16 | POST/terminal_rps | 15.9792 [15.6764, 16.1583]; n=12 |
| C16 | POST/timeout_fraction | 0 [0, 0.39205]; n=12 |
| C16 | PRE/aged_pending_at_end | 0 [IC indisponível]; n=12 |
| C16 | PRE/failure_or_deadline_miss_fraction | 0 [0, 0.39205]; n=12 |
| C16 | PRE/mean_2xx_ms | 30.5156 [30.2631, 30.7671]; n=12 |
| C16 | PRE/mean_all_ms | 30.5156 [30.2631, 30.7671]; n=12 |
| C16 | PRE/mean_cpu_docker_percent | 21.1358 [20.7829, 21.4426]; n=12 |
| C16 | PRE/pending_at_end | 0.25 [0.0833333, 0.583333]; n=12 |
| C16 | PRE/start_rps | 15.9167 [15.7194, 16.1229]; n=12 |
| C16 | PRE/success_fraction | 1 [0.60795, 1]; n=12 |
| C16 | PRE/terminal_2xx_rps | 15.9188 [15.7243, 16.1236]; n=12 |
| C16 | PRE/terminal_rps | 15.9188 [15.7243, 16.1236]; n=12 |
| C16 | PRE/timeout_fraction | 0 [0, 0.39205]; n=12 |
| C16 | emission_end_seconds | indefinido [IC indisponível]; n=0 |
| C16 | exposure_seconds | indefinido [IC indisponível]; n=0 |
| C16 | offensive_start_rps | indefinido [IC indisponível]; n=0 |
| C16 | stop_command_seconds | indefinido [IC indisponível]; n=0 |

C16: paradas precoces indefinido [IC indisponível]; n=0; motivos `{}`; recuperação indefinido [IC indisponível]; n=0; dados operacionais 12/12; ausentes `0`.

| E16 | ACTIVE/aged_pending_at_end | 0 [IC indisponível]; n=12 |
| E16 | ACTIVE/failure_or_deadline_miss_fraction | 0.0656566 [0.0455634, 0.0825245]; n=12 |
| E16 | ACTIVE/mean_2xx_ms | 546.449 [465.816, 634.24]; n=12 |
| E16 | ACTIVE/mean_all_ms | 643.791 [577.896, 727.47]; n=12 |
| E16 | ACTIVE/mean_cpu_docker_percent | 184.588 [179.929, 187.509]; n=12 |
| E16 | ACTIVE/pending_at_end | 29.5 [23.5833, 32.5]; n=12 |
| E16 | ACTIVE/start_rps | 15.8353 [15.679, 15.9875]; n=12 |
| E16 | ACTIVE/success_fraction | 0.934343 [0.917476, 0.95444]; n=12 |
| E16 | ACTIVE/terminal_2xx_rps | 14.7621 [14.4768, 15.0072]; n=12 |
| E16 | ACTIVE/terminal_rps | 15.4379 [15.2866, 15.5823]; n=12 |
| E16 | ACTIVE/timeout_fraction | 0.0656566 [0.0455634, 0.0825245]; n=12 |
| E16 | POST/aged_pending_at_end | 0 [IC indisponível]; n=12 |
| E16 | POST/failure_or_deadline_miss_fraction | 0.00462204 [0.00285454, 0.00656821]; n=12 |
| E16 | POST/mean_2xx_ms | 43.6485 [40.111, 46.7835]; n=12 |
| E16 | POST/mean_all_ms | 52.6927 [46.0521, 58.7934]; n=12 |
| E16 | POST/mean_cpu_docker_percent | 26.501 [25.7098, 27.6542]; n=12 |
| E16 | POST/pending_at_end | 0.333333 [0.0833333, 0.666667]; n=12 |
| E16 | POST/start_rps | 15.9724 [15.6936, 16.1214]; n=12 |
| E16 | POST/success_fraction | 0.995378 [0.993432, 0.997145]; n=12 |
| E16 | POST/terminal_2xx_rps | 15.9203 [15.6057, 16.0795]; n=12 |
| E16 | POST/terminal_rps | 16.1593 [15.8949, 16.3078]; n=12 |
| E16 | POST/timeout_fraction | 0.00462204 [0.00285454, 0.00656821]; n=12 |
| E16 | PRE/aged_pending_at_end | 0 [IC indisponível]; n=12 |
| E16 | PRE/failure_or_deadline_miss_fraction | 0 [0, 0.39205]; n=12 |
| E16 | PRE/mean_2xx_ms | 30.3281 [30.0992, 30.6493]; n=12 |
| E16 | PRE/mean_all_ms | 30.3281 [30.0992, 30.6493]; n=12 |
| E16 | PRE/mean_cpu_docker_percent | 21.1243 [20.6911, 21.5843]; n=12 |
| E16 | PRE/pending_at_end | 0.166667 [0, 0.5]; n=12 |
| E16 | PRE/start_rps | 15.916 [15.7192, 16.1222]; n=12 |
| E16 | PRE/success_fraction | 1 [0.60795, 1]; n=12 |
| E16 | PRE/terminal_2xx_rps | 15.9167 [15.7208, 16.1228]; n=12 |
| E16 | PRE/terminal_rps | 15.9167 [15.7208, 16.1228]; n=12 |
| E16 | PRE/timeout_fraction | 0 [0, 0.39205]; n=12 |
| E16 | emission_end_seconds | 232.415 [218.703, 245.82]; n=12 |
| E16 | exposure_seconds | 82.4097 [68.6983, 95.8145]; n=12 |
| E16 | offensive_start_rps | 15.981 [15.6606, 16.2586]; n=12 |
| E16 | stop_command_seconds | 224.892 [213.117, 236.67]; n=10 |

E16: paradas precoces 0.833333 [0.551969, 0.953035]; n=12; motivos `{'service_compromise': 10}`; recuperação 1 [0.735352, 1]; n=12; dados operacionais 12/12; ausentes `0`.

| M16 | ACTIVE/aged_pending_at_end | 0 [IC indisponível]; n=12 |
| M16 | ACTIVE/failure_or_deadline_miss_fraction | 0 [0, 0.39205]; n=12 |
| M16 | ACTIVE/mean_2xx_ms | 36.7425 [36.3599, 37.089]; n=12 |
| M16 | ACTIVE/mean_all_ms | 36.7425 [36.3599, 37.089]; n=12 |
| M16 | ACTIVE/mean_cpu_docker_percent | 40.6428 [39.998, 41.3721]; n=12 |
| M16 | ACTIVE/pending_at_end | 0.666667 [0.333333, 1.16667]; n=12 |
| M16 | ACTIVE/start_rps | 15.8633 [15.6647, 16.0576]; n=12 |
| M16 | ACTIVE/success_fraction | 1 [0.60795, 1]; n=12 |
| M16 | ACTIVE/terminal_2xx_rps | 15.8626 [15.6662, 16.0563]; n=12 |
| M16 | ACTIVE/terminal_rps | 15.8626 [15.6662, 16.0563]; n=12 |
| M16 | ACTIVE/timeout_fraction | 0 [0, 0.39205]; n=12 |
| M16 | POST/aged_pending_at_end | 0 [IC indisponível]; n=12 |
| M16 | POST/failure_or_deadline_miss_fraction | 0 [0, 0.39205]; n=12 |
| M16 | POST/mean_2xx_ms | 30.9865 [30.7035, 31.3073]; n=12 |
| M16 | POST/mean_all_ms | 30.9865 [30.7035, 31.3073]; n=12 |
| M16 | POST/mean_cpu_docker_percent | 21.9427 [21.3734, 22.3957]; n=12 |
| M16 | POST/pending_at_end | 0.5 [0.166667, 0.916667]; n=12 |
| M16 | POST/start_rps | 15.9798 [15.678, 16.1586]; n=12 |
| M16 | POST/success_fraction | 1 [0.60795, 1]; n=12 |
| M16 | POST/terminal_2xx_rps | 15.9812 [15.6804, 16.1576]; n=12 |
| M16 | POST/terminal_rps | 15.9812 [15.6804, 16.1576]; n=12 |
| M16 | POST/timeout_fraction | 0 [0, 0.39205]; n=12 |
| M16 | PRE/aged_pending_at_end | 0 [IC indisponível]; n=12 |
| M16 | PRE/failure_or_deadline_miss_fraction | 0 [0, 0.39205]; n=12 |
| M16 | PRE/mean_2xx_ms | 30.2847 [30.0708, 30.5056]; n=12 |
| M16 | PRE/mean_all_ms | 30.2847 [30.0708, 30.5056]; n=12 |
| M16 | PRE/mean_cpu_docker_percent | 21.1965 [20.8675, 21.5955]; n=12 |
| M16 | PRE/pending_at_end | 0.583333 [0.25, 1.08333]; n=12 |
| M16 | PRE/start_rps | 15.9174 [15.7208, 16.1243]; n=12 |
| M16 | PRE/success_fraction | 1 [0.60795, 1]; n=12 |
| M16 | PRE/terminal_2xx_rps | 15.9139 [15.7181, 16.121]; n=12 |
| M16 | PRE/terminal_rps | 15.9139 [15.7181, 16.121]; n=12 |
| M16 | PRE/timeout_fraction | 0 [0, 0.39205]; n=12 |
| M16 | emission_end_seconds | 270.005 [270.003, 270.007]; n=12 |
| M16 | exposure_seconds | 119.998 [119.996, 120]; n=12 |
| M16 | offensive_start_rps | 15.8842 [15.6009, 16.133]; n=12 |
| M16 | stop_command_seconds | indefinido [IC indisponível]; n=0 |

M16: paradas precoces 0 [0, 0.264648]; n=12; motivos `{}`; recuperação 1 [0.735352, 1]; n=12; dados operacionais 12/12; ausentes `0`.


## Contrastes pareados e incerteza

Diferenças são calculadas antes da reamostragem, apenas em pares completos. Comparações operacionais E16−M16 descrevem a política sob a exposição realizada: não representam dose igual nem isolam efeito causal da intensidade. Os ICs são pontuais, condicionais ao treinamento congelado; não sustentam superioridade global. BCa usa 10.000 reamostragens de blocos; casos degenerados limitados usam Hoeffding. Contrastes de eventos usam discordâncias pareadas com intervalos exatos de 97,5% e Bonferroni para compor IC95%. Valores indefinidos não significam zero.

| Contraste operacional E16−M16 | Diferença [IC95%] |
|---|---|
| ACTIVE/aged_pending_at_end | 0 [IC indisponível]; n=12 |
| ACTIVE/failure_or_deadline_miss_fraction | 0.0656566 [0.0455634, 0.0825245]; n=12 |
| ACTIVE/mean_2xx_ms | 509.706 [428.936, 597.452]; n=12 |
| ACTIVE/mean_all_ms | 607.049 [541.088, 690.718]; n=12 |
| ACTIVE/mean_cpu_docker_percent | 143.945 [139.322, 146.811]; n=12 |
| ACTIVE/pending_at_end | 28.8333 [23.1219, 31.9167]; n=12 |
| ACTIVE/start_rps | -0.027915 [-0.117985, 0.0585166]; n=12 |
| ACTIVE/success_fraction | -0.0656566 [-0.0825245, -0.0455634]; n=12 |
| ACTIVE/terminal_2xx_rps | -1.10043 [-1.41041, -0.796312]; n=12 |
| ACTIVE/terminal_rps | -0.424699 [-0.578886, -0.302791]; n=12 |
| ACTIVE/timeout_fraction | 0.0656566 [0.0455634, 0.0825245]; n=12 |
| POST/aged_pending_at_end | 0 [IC indisponível]; n=12 |
| POST/failure_or_deadline_miss_fraction | 0.00462204 [0.00285454, 0.00656821]; n=12 |
| POST/mean_2xx_ms | 12.662 [9.09464, 15.7936]; n=12 |
| POST/mean_all_ms | 21.7062 [15.0087, 27.8861]; n=12 |
| POST/mean_cpu_docker_percent | 4.55836 [3.64553, 5.58548]; n=12 |
| POST/pending_at_end | -0.166667 [-0.5, 0]; n=12 |
| POST/start_rps | -0.00736091 [-0.100023, 0.0951396]; n=12 |
| POST/success_fraction | -0.00462204 [-0.00656826, -0.00285462]; n=12 |
| POST/terminal_2xx_rps | -0.0609245 [-0.170144, 0.0391419]; n=12 |
| POST/terminal_rps | 0.178096 [0.0801494, 0.275671]; n=12 |
| POST/timeout_fraction | 0.00462204 [0.00285454, 0.00656821]; n=12 |
| PRE/aged_pending_at_end | 0 [IC indisponível]; n=12 |
| PRE/failure_or_deadline_miss_fraction | 0 [IC indisponível]; n=12 |
| PRE/mean_2xx_ms | 0.0433336 [-0.237937, 0.274929]; n=12 |
| PRE/mean_all_ms | 0.0433336 [-0.237937, 0.274929]; n=12 |
| PRE/mean_cpu_docker_percent | -0.0721667 [-0.380321, 0.259889]; n=12 |
| PRE/pending_at_end | -0.416667 [-0.916667, -0.166667]; n=12 |
| PRE/start_rps | -0.00138889 [-0.00416667, 0]; n=12 |
| PRE/success_fraction | 0 [IC indisponível]; n=12 |
| PRE/terminal_2xx_rps | 0.00277778 [0.000694444, 0.00694444]; n=12 |
| PRE/terminal_rps | 0.00277778 [0.000694444, 0.00694444]; n=12 |
| PRE/timeout_fraction | 0 [IC indisponível]; n=12 |
| emission_end_seconds | -37.5897 [-51.3007, -24.1824]; n=12 |
| exposure_seconds | -37.5887 [-51.2991, -24.1844]; n=12 |
| offensive_start_rps | 0.0967093 [0.0165855, 0.186955]; n=12 |
| stop_command_seconds | indefinido [IC indisponível]; n=0 |

| Contraste de detecção E16−M16 | Diferença [IC95%] | Discordantes n10/n01 |
|---|---|---|
| ingress_packet_count/cov/E16-M16 | 0.25 [-0.263608, 0.610698]; n=12 | 3/0 |
| ingress_packet_count/cusum-freeze/E16-M16 | 0 [-0.305921, 0.305921]; n=12 | 0/0 |
| ingress_packet_count/ewma/E16-M16 | 0 [-0.305921, 0.305921]; n=12 | 0/0 |
| ingress_packet_count/zscore/E16-M16 | 0 [-0.305921, 0.305921]; n=12 | 0/0 |
| ingress_tcp_payload_length_sum_bytes/cov/E16-M16 | 0 [-0.305921, 0.305921]; n=12 | 0/0 |
| ingress_tcp_payload_length_sum_bytes/cusum-freeze/E16-M16 | 0 [-0.305921, 0.305921]; n=12 | 0/0 |
| ingress_tcp_payload_length_sum_bytes/ewma/E16-M16 | 0 [-0.305921, 0.305921]; n=12 | 0/0 |
| ingress_tcp_payload_length_sum_bytes/zscore/E16-M16 | 0 [-0.305921, 0.305921]; n=12 | 0/0 |
| mean_cpu_percent/cov/E16-M16 | 0.666667 [0.00700389, 0.919074]; n=12 | 8/0 |
| mean_cpu_percent/cusum-freeze/E16-M16 | 0 [-0.305921, 0.305921]; n=12 | 0/0 |
| mean_cpu_percent/ewma/E16-M16 | 0 [-0.305921, 0.305921]; n=12 | 0/0 |
| mean_cpu_percent/zscore/E16-M16 | 0 [-0.305921, 0.305921]; n=12 | 0/0 |
| mean_duration_ms/cov/E16-M16 | 1 [0.388159, 1]; n=12 | 12/0 |
| mean_duration_ms/cusum-freeze/E16-M16 | 0 [-0.305921, 0.305921]; n=12 | 0/0 |
| mean_duration_ms/ewma/E16-M16 | 0 [-0.305921, 0.305921]; n=12 | 0/0 |
| mean_duration_ms/zscore/E16-M16 | 0 [-0.305921, 0.305921]; n=12 | 0/0 |
| request_starts/cov/E16-M16 | 0 [-0.305921, 0.305921]; n=12 | 0/0 |
| request_starts/cusum-freeze/E16-M16 | 0 [-0.305921, 0.305921]; n=12 | 0/0 |
| request_starts/ewma/E16-M16 | 0 [-0.305921, 0.305921]; n=12 | 0/0 |
| request_starts/zscore/E16-M16 | 0 [-0.305921, 0.305921]; n=12 | 0/0 |

Contrastes entre métodos da feature primária (primeiro menos segundo):

| Cenário/contraste | Métrica | Diferença [IC95%] | Pares com detecção conjunta |
|---|---|---|---|
| request_starts/C16/cov-cusum-freeze | f1 | 0 [-0.960323, 0.960323]; n=8 | 0 |
| request_starts/C16/cov-cusum-freeze | fpr | 0.00486111 [-0.000231481, 0.0131944]; n=12 | 0 |
| request_starts/C16/cov-cusum-freeze | recall | indefinido [IC indisponível]; n=0 | 0 |
| request_starts/C16/cov-cusum-freeze | restricted | indefinido [IC indisponível]; n=0 | 0 |
| request_starts/C16/cov-ewma | f1 | 0 [-0.818966, 0.818966]; n=11 | 0 |
| request_starts/C16/cov-ewma | fpr | -0.000462963 [-0.00694444, 0.00787037]; n=12 | 0 |
| request_starts/C16/cov-ewma | recall | indefinido [IC indisponível]; n=0 | 0 |
| request_starts/C16/cov-ewma | restricted | indefinido [IC indisponível]; n=0 | 0 |
| request_starts/C16/cusum-freeze-ewma | f1 | 0 [-0.905401, 0.905401]; n=9 | 0 |
| request_starts/C16/cusum-freeze-ewma | fpr | -0.00532407 [-0.00902778, -0.00277778]; n=12 | 0 |
| request_starts/C16/cusum-freeze-ewma | recall | indefinido [IC indisponível]; n=0 | 0 |
| request_starts/C16/cusum-freeze-ewma | restricted | indefinido [IC indisponível]; n=0 | 0 |
| request_starts/C16/zscore-cov | f1 | 0 [-0.858939, 0.858939]; n=10 | 0 |
| request_starts/C16/zscore-cov | fpr | -0.00324074 [-0.00925926, 0.000925926]; n=12 | 0 |
| request_starts/C16/zscore-cov | recall | indefinido [IC indisponível]; n=0 | 0 |
| request_starts/C16/zscore-cov | restricted | indefinido [IC indisponível]; n=0 | 0 |
| request_starts/C16/zscore-cusum-freeze | f1 | 0 [-0.905401, 0.905401]; n=9 | 0 |
| request_starts/C16/zscore-cusum-freeze | fpr | 0.00162037 [-0.00115741, 0.00462963]; n=12 | 0 |
| request_starts/C16/zscore-cusum-freeze | recall | indefinido [IC indisponível]; n=0 | 0 |
| request_starts/C16/zscore-cusum-freeze | restricted | indefinido [IC indisponível]; n=0 | 0 |
| request_starts/C16/zscore-ewma | f1 | 0 [-0.818966, 0.818966]; n=11 | 0 |
| request_starts/C16/zscore-ewma | fpr | -0.0037037 [-0.00648148, -0.000462963]; n=12 | 0 |
| request_starts/C16/zscore-ewma | recall | indefinido [IC indisponível]; n=0 | 0 |
| request_starts/C16/zscore-ewma | restricted | indefinido [IC indisponível]; n=0 | 0 |
| request_starts/E16/cov-cusum-freeze | detection | -0.5 [-0.817324, 0.123244]; n=12 | 6 |
| request_starts/E16/cov-cusum-freeze | f1 | -0.942187 [-0.958438, -0.914911]; n=12 | 6 |
| request_starts/E16/cov-cusum-freeze | fpr | 0.0064137 [-0.000407428, 0.0143845]; n=12 | 6 |
| request_starts/E16/cov-cusum-freeze | recall | -0.957511 [-0.968155, -0.9428]; n=12 | 6 |
| request_starts/E16/cov-cusum-freeze | restricted | 0.490899 [0.242058, 0.739372]; n=12 | 6 |
| request_starts/E16/cov-ewma | detection | -0.5 [-0.817324, 0.123244]; n=12 | 6 |
| request_starts/E16/cov-ewma | f1 | -0.910423 [-0.935627, -0.863297]; n=12 | 6 |
| request_starts/E16/cov-ewma | fpr | -0.0186379 [-0.0273194, -0.00841656]; n=12 | 6 |
| request_starts/E16/cov-ewma | recall | -0.985461 [-0.993615, -0.975015]; n=12 | 6 |
| request_starts/E16/cov-ewma | restricted | 0.489225 [0.238447, 0.73879]; n=12 | 6 |
| request_starts/E16/cusum-freeze-ewma | detection | 0 [-0.305921, 0.305921]; n=12 | 12 |
| request_starts/E16/cusum-freeze-ewma | f1 | 0.0317634 [0.0208197, 0.0505993]; n=12 | 12 |
| request_starts/E16/cusum-freeze-ewma | fpr | -0.0250516 [-0.0300951, -0.0213259]; n=12 | 12 |
| request_starts/E16/cusum-freeze-ewma | recall | -0.0279496 [-0.0341285, -0.0216876]; n=12 | 12 |
| request_starts/E16/cusum-freeze-ewma | restricted | -0.00167412 [-0.0083706, 0]; n=12 | 12 |
| request_starts/E16/zscore-cov | detection | 0.5 [-0.123244, 0.817324]; n=12 | 6 |
| request_starts/E16/zscore-cov | f1 | 0.860726 [0.842577, 0.875589]; n=12 | 6 |
| request_starts/E16/zscore-cov | fpr | -0.00691861 [-0.0134615, -0.00108112]; n=12 | 6 |
| request_starts/E16/zscore-cov | recall | 0.813932 [0.783877, 0.834711]; n=12 | 6 |
| request_starts/E16/zscore-cov | restricted | -0.496443 [-0.744246, -0.248371]; n=12 | 6 |
| request_starts/E16/zscore-cusum-freeze | detection | 0 [-0.305921, 0.305921]; n=12 | 12 |
| request_starts/E16/zscore-cusum-freeze | f1 | -0.0814607 [-0.104004, -0.0669823]; n=12 | 12 |
| request_starts/E16/zscore-cusum-freeze | fpr | -0.000504907 [-0.00452528, 0.00267705]; n=12 | 12 |
| request_starts/E16/zscore-cusum-freeze | recall | -0.14358 [-0.177577, -0.111202]; n=12 | 12 |
| request_starts/E16/zscore-cusum-freeze | restricted | -0.00554421 [-0.0103979, -0.0021856]; n=12 | 12 |
| request_starts/E16/zscore-ewma | detection | 0 [-0.305921, 0.305921]; n=12 | 12 |
| request_starts/E16/zscore-ewma | f1 | -0.0496973 [-0.0743443, -0.0208089]; n=12 | 12 |
| request_starts/E16/zscore-ewma | fpr | -0.0255565 [-0.0291713, -0.0213669]; n=12 | 12 |
| request_starts/E16/zscore-ewma | recall | -0.171529 [-0.205422, -0.142363]; n=12 | 12 |
| request_starts/E16/zscore-ewma | restricted | -0.00721833 [-0.0122473, -0.00328213]; n=12 | 12 |
| request_starts/M16/cov-cusum-freeze | detection | -0.5 [-0.817324, 0.123244]; n=12 | 6 |
| request_starts/M16/cov-cusum-freeze | f1 | -0.966898 [-0.974778, -0.957118]; n=12 | 6 |
| request_starts/M16/cov-cusum-freeze | fpr | 0.0135983 [0.00313808, 0.0251046]; n=12 | 6 |
| request_starts/M16/cov-cusum-freeze | recall | -0.970588 [-0.976891, -0.964286]; n=12 | 6 |
| request_starts/M16/cov-cusum-freeze | restricted | 0.493778 [0.245146, 0.742412]; n=12 | 6 |
| request_starts/M16/cov-ewma | detection | -0.5 [-0.817324, 0.123244]; n=12 | 6 |
| request_starts/M16/cov-ewma | f1 | -0.948537 [-0.958564, -0.934496]; n=12 | 6 |
| request_starts/M16/cov-ewma | fpr | -0.0170851 [-0.0282427, -0.00209205]; n=12 | 6 |
| request_starts/M16/cov-ewma | recall | -0.992297 [-0.996499, -0.986695]; n=12 | 6 |
| request_starts/M16/cov-ewma | restricted | 0.493084 [0.243758, 0.742403]; n=12 | 6 |
| request_starts/M16/cusum-freeze-ewma | detection | 0 [-0.305921, 0.305921]; n=12 | 12 |
| request_starts/M16/cusum-freeze-ewma | f1 | 0.018361 [0.0132761, 0.0246079]; n=12 | 12 |
| request_starts/M16/cusum-freeze-ewma | fpr | -0.0306834 [-0.0373082, -0.025802]; n=12 | 12 |
| request_starts/M16/cusum-freeze-ewma | recall | -0.0217087 [-0.0266106, -0.0168067]; n=12 | 12 |
| request_starts/M16/cusum-freeze-ewma | restricted | -0.000694467 [-0.00347233, 0]; n=12 | 12 |
| request_starts/M16/zscore-cov | detection | 0.5 [-0.123244, 0.817324]; n=12 | 6 |
| request_starts/M16/zscore-cov | f1 | 0.876744 [0.859997, 0.889979]; n=12 | 6 |
| request_starts/M16/zscore-cov | fpr | -0.0108089 [-0.0181311, -0.0027894]; n=12 | 6 |
| request_starts/M16/zscore-cov | recall | 0.814426 [0.781513, 0.835434]; n=12 | 6 |
| request_starts/M16/zscore-cov | restricted | -0.497251 [-0.745188, -0.248632]; n=12 | 6 |
| request_starts/M16/zscore-cusum-freeze | detection | 0 [-0.305921, 0.305921]; n=12 | 12 |
| request_starts/M16/zscore-cusum-freeze | f1 | -0.0901534 [-0.106903, -0.075899]; n=12 | 12 |
| request_starts/M16/zscore-cusum-freeze | fpr | 0.0027894 [-0.00244073, 0.00871688]; n=12 | 12 |
| request_starts/M16/zscore-cusum-freeze | recall | -0.156162 [-0.187675, -0.134454]; n=12 | 12 |
| request_starts/M16/zscore-cusum-freeze | restricted | -0.00347222 [-0.0062499, -0.00138887]; n=12 | 12 |
| request_starts/M16/zscore-ewma | detection | 0 [-0.305921, 0.305921]; n=12 | 12 |
| request_starts/M16/zscore-ewma | f1 | -0.0717924 [-0.091893, -0.0559825]; n=12 | 12 |
| request_starts/M16/zscore-ewma | fpr | -0.027894 [-0.0331241, -0.0184798]; n=12 | 12 |
| request_starts/M16/zscore-ewma | recall | -0.177871 [-0.213585, -0.154762]; n=12 | 12 |
| request_starts/M16/zscore-ewma | restricted | -0.00416668 [-0.0062501, -0.00208327]; n=12 | 12 |

## Limitações e pendências

Apenas 12 blocos TEST; ICs marginais/pontuais e dependência temporal dentro das execuções. A disponibilidade de detecção reflete fechamento simulado ou disponibilidade registrada, não medição de tempo de processamento em produção. Atrasos são condicionais aos eventos detectados; misses e eventos não avaliados permanecem explícitos. C16 não permite avaliar detecção de ataque. IC indisponível por degeneração ou suporte insuficiente permanece indisponível. A recuperação segue o critério operacional congelado e não significa ausência de todo efeito residual.

Pendências são de interpretação e documentação: explicitar a validade externa restrita ao ambiente e às cargas congeladas, distinguir exposição nominal e realizada e incorporar esta consolidação ao texto científico. Nenhuma combinação foi selecionada e nenhum ajuste ou coleta é proposto com base em TEST.

Anexos: integrity.json (hashes verificados); calibration.json (calibração/verificação); individual_runs.json (percentis e observações de cada execução); frozen_summary_extract.json (resultados e contrastes existentes, sem recálculo). Fonte central: experiment_results/scientific-reduced-clock-r2-20261029/analysis/summary/manifest.json.
