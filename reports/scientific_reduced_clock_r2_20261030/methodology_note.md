# Nota metodológica — fronteiras e disponibilidade na campanha clock r2

Conferência offline em 31/10/2026. Complemento documental de [report.md](report.md), sem alteração das regras ou dos artefatos congelados. Foram lidos código, tabelas e decisões existentes; nenhum experimento, calibração, detector, score, decisão ou IC foi executado ou produzido novamente. As contagens de conferência estão em [methodology_checks.json](methodology_checks.json).

## Base e regras por feature

Autoridades: plano `experiments/protocols/scientific_reduced_clock_r2_20261029/plan.json` (SHA256 `6240452e214b0748b023a084edd6dcf4fd2fd0a43744ed70a37bdb88a4319bc4`) e checkpoint `experiment_results/scientific-reduced-clock-r2-20261029/checkpoints/TEST/manifest.json` (SHA256 `690c7d9af50204d7170fbb08ee61dd672450d2d5dd7e8c0a1de9725669601912`). Não foram encontrados AGENTS.md nos diretórios ancestrais nem no repositório. A restrição offline prevaleceu também na consulta à skill de escrita, sem consulta a conectores.

A grade de todas as features é de janelas não sobrepostas de 1 s, `[i,i+1)`, com origem no início do experimento. A tabela descreve a observação, não o histórico interno de cada detector.

| Feature | Intervalo representado e atribuição dos registros | Disponibilidade usada no TEST | Requisição que atravessa janelas |
|---|---|---|---|
| `request_starts` | Contagem das tentativas cujo `elapsed_seconds` de início pertence a `[i,i+1)`, sem filtro pela classe causal. | Atribuída em `i+1`; não é timestamp de execução do detector. | Conta uma vez na janela de início, mesmo se termina depois ou não termina. |
| `mean_duration_ms` | Média de `duration_ms` das tentativas concluídas cujo `end_elapsed_seconds` pertence a `[i,i+1)`, incluindo falhas. A duração individual pode começar antes de `i`. | Atribuída em `i+1`, após a janela das conclusões. | Duração inteira na janela de conclusão; não é dividida entre janelas. Sem conclusão não se inventa duração; sem conclusões a média é nula. |
| `ingress_packet_count` | Contagem dos registros de pacotes source→proxy com timestamp convertido em `elapsed_seconds` dentro de `[i,i+1)`, incluindo payload zero e retransmissões observadas. | Atribuída em `i+1`. | Cada pacote entra pela sua data, independentemente do início/fim HTTP. |
| `ingress_tcp_payload_length_sum_bytes` | Soma do campo TCP `packet_length` dos mesmos registros ingress em `[i,i+1)`; não são bytes HTTP únicos nem bytes físicos no enlace. | Atribuída em `i+1`. | Mesma regra por pacote; sem deduplicação ou transferência para a janela de início HTTP. |
| `mean_cpu_percent` | Média dos ticks suportados de `average_cpu_percent` registrados em `[i,i+1)`. Cada tick já resume amostras anteriores do coletor/cache; não mede a integral exata de CPU dessa janela. | Atribuída em `i+1`; o instante do tick é registrado, mas não se usa uma disponibilidade individual da feature/detector. | Não há atribuição por requisição. Trabalho pendente pode afetar ticks posteriores à emissão. |

CPU requer uma distinção adicional: `StatsCollector.get_averages(window_seconds=1)` seleciona o histórico recente e recorre à última leitura em cache se não houver amostra recente. A coleta assíncrona usa `stats(stream=False)` e deltas de contadores Docker. O tick recebe `elapsed_seconds` imediatamente antes da escrita, depois das ações do tick. O CSV não preserva, para cada valor agregado, os dois extremos físicos da medição Docker nem a idade completa do cache. Portanto, o suporte físico de CPU pode anteceder e atravessar a janela em que o tick foi registrado; não deve ser apresentado como CPU instantânea nem como média temporal exata daquele segundo. `ProtectedCollector` registra evidência de frescor para a proteção operacional, sem substituir essa semântica da feature.

Em todas as features, `load_source` cria observações com início/fim da grade. `engine.trace` usa o fim da janela quando `ScoreValue.available_at_seconds` não é explícito; CUSUM-freeze também atribui disponibilidade no fim. Todos os **281.520 registros existentes** dos quatro métodos nas 36 execuções e cinco features têm `available_at_seconds == window_end_seconds`. A alternativa genérica de disponibilidade explícita existe no código, mas não explica diferenças de atraso neste TEST. O manifesto de cada run declara `simulated_window_closure_not_measured_compute_latency`.

## Fronteiras e reconciliação

Seja o evento global real `[s,e)` e uma janela `[a,b)`. `scientific.evaluation.metrics` aplica:

- Só entram nas métricas por janela aquelas inteiramente contidas em `[30,390)`: `30 <= a < b <= 390`. O aquecimento `[0,30)` e a cauda a partir de 390 s ficam fora dessas métricas, mesmo havendo registros na grade.
- Sobreposição zero: janela benigna. Sobreposição igual à largura inteira: janela ofensiva. Sobreposição estritamente entre zero e a largura: janela **mista** (`boundary`), excluída de TP/FN/FP/TN e dos denominadores por janela; não é arredondada nem convertida em benigna.
- Uma decisão só é disponível para essas métricas se não for nula e sua disponibilidade for até 390 s. Indisponibilidade e fronteira são contagens distintas. Aquecimento interno de CoV e possíveis médias nulas não são preenchidos artificialmente.
- POST exige `a >= e`, dentro do horizonte por janela. POST é um **subconjunto das benignas**, não uma terceira classe disjunta. Resíduos de requisições, CPU ou alarmes após a emissão continuam em POST/benigno pela regra temporal, sem afirmar recuperação instantânea.

Cada execução oferece 360 janelas candidatas. Nas 12 M16 e nas 12 E16 os dois limites reais estão no interior de segundos distintos: há duas mistas por execução. O início fica pouco depois de 150 s; logo, PRE completo contém 120 janelas `[30,31)` a `[149,150)`.

| Cenário | Candidatas | Mistas excluídas | Ofensivas disponíveis | POST disponíveis (incluídas nas benignas) | Benignas disponíveis | Indisponíveis |
|---|---:|---:|---:|---:|---:|---:|
| C16, 12 runs | 4.320 | 0 | 0 | 0¹ | 4.320 | 0 |
| M16, 12 runs | 4.320 | 24 | 1.428 = 12×119 | 1.428 = 12×119 | 2.868 = 12×(120+119) | 0 |
| E16, 12 runs | 4.320 | 24 | 970 | 1.886 | 3.326 = 1.440+1.886 | 0 |

¹ A avaliação de detecção só marca POST quando há evento. As fases operacionais PRE/ACTIVE/POST do relatório têm outra finalidade e também são descritas para C16.

As três linhas foram conferidas **em cada uma das cinco features e em cada um dos quatro métodos**, sem diferenças de denominador ou de disponibilidade no horizonte. Sempre vale `benignas + ofensivas + mistas = 4.320`. As diferenças entre features estão nos valores e alarmes, não nessas fronteiras. Em outros dados, médias nulas ou ausência de suporte de rede poderiam reduzir disponibilidade; isso não ocorreu aqui no horizonte avaliado.

M16 tem início real `150+δ` e fim `270+ε`: `[150,151)` e `[270,271)` são mistas. Restam `[151,152)` a `[269,270)`, **119** ofensivas, e `[271,272)` a `[389,390)`, **119** POST. O nominal de 120 s não define a contagem de segundos inteiros interiores ao evento. Nem a exposição realizada precisa ser exatamente 120 s: no exemplo abaixo é ligeiramente maior.

Em E16, para os limites fracionários observados, cada execução tem `floor(e)−151` ofensivas e `389−floor(e)` POST. Por bloco 1–12, as contagens ofensivas/POST existentes são: `89/149, 119/119, 89/149, 75/163, 76/162, 103/135, 89/149, 49/189, 119/119, 50/188, 64/174, 48/190`. Somam 970/1.886. Dez encerramentos são precoces por `service_compromise`; dois são programados. Em relação a M16, 458 janelas passam de ofensivas para POST, preservando 360 candidatas e duas mistas por run. A emissão encerra antes; a observação continua até o horizonte de 390 s. O evento não é removido do denominador nem passa a ser um miss por ter sido interrompido.

## Dois exemplos reais de fronteira

Tempos em segundos desde a origem compartilhada; decimais abaixo transcritos do ground truth, sem epsilon.

| Execução | Início real `s` | Fim real de emissão `e` | Drenagem |
|---|---:|---:|---:|
| `sci56_TEST_B01_2_M16` | 150.00832267100122 | 270.008932703 | 269.94107557700045 |
| `sci56_TEST_B01_3_E16` | 150.00330454599862 | 240.568891248 | 242.4664031559987 |

| Janela ou sequência | M16 | E16 |
|---|---|---|
| `[149,150)` | Benigna PRE | Benigna PRE |
| `[150,151)` | Mista: atravessa `s` | Mista: atravessa `s` |
| Janelas inteiras seguintes | `[151,270)`: 119 ofensivas | `[151,240)`: 89 ofensivas |
| Janela contendo `e` | `[270,271)`: mista | `[240,241)`: mista |
| POST completo | `[271,390)`: 119 benignas POST | `[241,390)`: 149 benignas POST |

As sequências indicadas representam a união de janelas de 1 s, não uma janela única. A regra é igual nas cinco features. No exemplo E16, a ordem operacional de parada foi em `240.56007579199832` s; a fronteira usa **240.568891248**, quando a emissão é certificada como encerrada, e não a ordem nem a drenagem em 242.4664 s. Assim, `[241,242)` é benigna POST embora ainda possa conter conclusões ofensivas e efeitos residuais. No M16, a última requisição terminou antes do fechamento certificado da emissão, o que também não desloca `e`.

## Detecção por evento e significado do atraso

A detecção exige uma decisão `True`, sobreposição positiva da janela de observação com `[s,e)` e disponibilidade `s <= available_at_seconds <= e`. A checagem de evento ocorre **antes** do filtro de janelas `[30,390)` e da exclusão de mistas. Neste TEST os eventos estão inteiramente dentro desse horizonte; a diferença relevante é que a **mista inicial pode detectar**, enquanto não entra no recall. A mista final fecha depois de `e` e, com disponibilidade atribuída no fechamento, não detecta. Um alarme anterior sem sobreposição não detecta; alarmes disponíveis só após `e` também não detectam. POST não detecta o evento encerrado.

O denominador de detecção é **12 eventos por cenário ofensivo, por feature/método**; C16 não tem evento. O denominador do recall é `TP+FN`: 1.428 janelas ofensivas disponíveis M16 ou 970 E16 nas somas documentais. As estimativas publicadas de recall/FPR são médias por bloco, não necessariamente razões entre totais somados. Disponibilidade igual não torna detecção por evento e recall intercambiáveis.

O atraso é `min(disponibilidade dos alarmes elegíveis) − actual_start_seconds`, condicionado aos eventos detectados. `actual_start_seconds` vem do início efetivo global (mínimo dos inícios locais); `actual_end_seconds` vem do fechamento global da emissão (máximo dos fechamentos locais certificados). Não se usa 150 s nominal, primeira amostra de CPU, comando de parada ou drenagem como origem do atraso. Misses têm atraso nulo/indefinido, censura em `e` e são contados separadamente; não entram como zero na média condicional. A métrica restrita é distinta: atraso/exposição quando detectado e 1 em miss. O IC condicional só é fornecido com pelo menos oito detecções.

No M16 B01, request_starts/zscore tem primeiro alarme disponível em **151 s**, na mista `[150,151)`: atraso `0.99167732899878` s. No E16 B01 é também **151 s**, atraso `0.99669545400138` s. O valor publicado próximo de **0,994 s** resulta de alarmes nessa primeira janela, menos o início real pouco posterior a 150 s; não significa que o algoritmo gastou 0,994 s computando. As decisões zscore existentes nas 12 execuções de cada cenário e os atrasos publicados sustentam essa leitura.

No E16 B01, os quatro métodos de CPU têm decisões negativas em `[150,151)` e `[151,152)`, e positivas em `[152,153)`, disponíveis em **153 s**: atraso `2.99669545400138` s. Os ticks registrados em `150.0544454639985` e `151.046461078` s têm CPU **14,69%**; o tick em `152.11586620899834` s tem **153,2%**. O relatório publica aproximadamente **2,995 s** para os quatro métodos em E16. Essa convergência é compatível com a aquisição/cache da métrica, a resposta observada e o fechamento da janela, além da regra de decisão. Não identifica uma parcela causal exclusiva do algoritmo nem um atraso fixo de 2 s imposto à CPU pelo processamento: todas as features recebem disponibilidade no próprio fim da janela. Em M16 os métodos de CPU têm outros atrasos, conforme seus alarmes congelados.

Há três tempos distintos: **tempo observado**, registrado pelos inícios/conclusões, pacotes, ticks e eventos no experimento; **disponibilidade atribuída**, o fim da janela no processamento offline; e **tempo computacional**, duração real para extrair, calcular e publicar alarmes, não medido por esses atrasos. Não há evidência suficiente para decompor numericamente os atrasos publicados entre aquisição, cache, agregação, dinâmica da carga e detector, nem para tratá-los como latência ponta a ponta de produção.

## Redação sugerida para a metodologia

> As cinco variáveis observáveis foram organizadas em janelas de 1 s, semiabertas e alinhadas à origem do experimento. As métricas por janela consideraram o intervalo [30,390) e os limites reais de emissão ofensiva. Janelas inteiramente interiores ao evento foram classificadas como ofensivas; janelas sem sobreposição, como benignas; janelas parcialmente sobrepostas foram excluídas dessas métricas. POST correspondeu às janelas inteiramente posteriores ao encerramento real da emissão e integrou o denominador benigno, inclusive durante possíveis efeitos residuais. A interrupção antecipada reduziu a exposição e o número de janelas ofensivas, ampliando POST, sem excluir o evento da avaliação.
>
> A detecção por evento exigiu ao menos um alarme cuja janela se sobrepusesse ao evento e cuja disponibilidade ocorresse entre o início e o fim reais da emissão. Essa regra permitiu usar a janela mista inicial, excluída do recall por janela. Neste TEST, a disponibilidade de todas as decisões foi atribuída ao fechamento da respectiva janela. O atraso foi a diferença entre a primeira disponibilidade elegível e o início real, condicionado à detecção; misses permaneceram explícitos e não receberam atraso zero. Os atrasos refletem os sinais observados, a aquisição e agregação temporal e a regra de decisão, sob essa disponibilidade atribuída, sem medir o tempo computacional do detector. Em particular, CPU agrega ticks derivados de amostras anteriores e cache, enquanto durações HTTP são atribuídas pela conclusão, mesmo quando o início pertence a outra janela.

## Referências verificáveis e conclusão da conferência

Todos os caminhos abaixo são relativos à raiz do repositório. Abreviação `R = experiment_results/scientific-reduced-clock-r2-20261029`.

- `experiments/extract_features.py::extract_features` e `experiments/feature_schema.py::feature_schema`: grade, atribuição por início/conclusão/tick/pacote, nulos e unidades.
- `analysis/detection/scientific/data.py::load_source, load_truth`: vínculo de observações, relógio, identidade e limites reais dos eventos; `scientific/engine.py::trace, selected`; `analysis/detection/detectors/cusum_freeze.py::CUSUMFreeze.step`: disponibilidade.
- `analysis/detection/scientific/evaluation.py::metrics, aggregate` e `scientific/statistics.py::delay_summary`: fronteiras, POST, elegibilidade de evento, denominadores, misses e atraso condicional. O caminho científico é o aplicável; não se deve substituí-lo pelas regras de avaliação de estágios legados.
- `simulator/source_aggregate.py::reconcile`, `simulator/ground_truth.py::ExperimentClock, GroundTruth` e `simulator/source_journal.py::SharedClock, JournalGroundTruth`: relógio compartilhado e distinção entre início, fechamento de emissão e drenagem. Pacotes usam conversão de relógio de parede por âncora do experimento (`ExperimentClock.from_epoch`).
- `simulator/source_experiment.py`, `simulator/stats_collector.py::StatsCollector.get_averages, _run, _calc_cpu_percent`, `simulator/main_orchestrator.py::log_metrics_to_csv` e `experiments/scientific_collection.py::ProtectedCollector` (classe local): origem e registro dos ticks CPU/cache.
- `R/checkpoints/TEST/manifest.json` → `artifacts` e `receipts`; `R/analysis/summary/manifest.json` → `evaluations`; `R/analysis/<feature>/evaluation/<entry>/manifest.json` → `results`, `truth`, `run`; `R/analysis/<feature>/TEST/<entry>/manifest.json` → `methods`, `source`, `availability_basis`. São 180 avaliações, com as quatro decisões existentes por feature/run; suas referências foram conferidas por hash, assim como os manifests do checkpoint, recibos e arquivos observáveis usados. Os hashes de runtime do plano coincidem com o código local. Não se executaram validadores que reproduzem detectores.
- Exemplos: `R/collection/sci56_TEST_B01_2_M16/attempt-1/dataset/raw/attacks/attack_events.csv` e o caminho correspondente a `sci56_TEST_B01_3_E16`; neste último, `raw/infrastructure/simulation_metrics.csv`, `features/timeseries/infrastructure.csv` (sob `attempt-1`) e `receipt/manifest.json` → `receipt.operational.stop`. As referências exatas e os limites transcritos constam do anexo de conferência.

**Resultado:** não foi encontrada inconsistência entre as regras científicas, os denominadores citados e os registros congelados examinados. Trata-se de esclarecimento documental. Pendências: incorporar a redação ao texto e preservar as ressalvas sobre suporte temporal de CPU, efeitos residuais em POST e atraso condicional com disponibilidade atribuída. A latência computacional e uma decomposição causal do atraso não são recuperáveis destas métricas; devem permanecer não estimadas. Não há correção de código ou artefato proposta.
