# B1.2 — Caracterização exploratória ofensiva isolada

## Ambiente, matriz e procedimento

Branch refactor/project-organization; HEAD adf3d42ef341449a1ed8e069a11024811339434c;
working tree inicialmente limpo. Docker Engine 29.9.3; Python 3.12.3. Disco inicial
34.081.382.400 bytes; RAM disponível inicial 9.820.229.632 bytes. Nenhum contêiner
ativo, redes experimentais vazias. Quatro contêineres externos foram preservados.

Matriz planejada: A1=2, A2=4, A3=8, A4=16 RPS no /expensive; F1=32, F2=64,
F3=128, F4=192, F5=256 RPS no /medium. A1 é o piloto anterior, originalmente de
validação de integração, e NÃO foi repetido. Foram realizadas oito execuções novas,
uma por A2–A4 e F1–F5, nessa ordem; todas terminaram completed/simulation_end e
foram certificadas. Não houve B2 ou repetições científicas.

Comuns: composição offensive, zero legítimos, duas fontes, dois workers, 150 s,
pré [0,30), emissão [30,60), pós [60,150), timeout 2 s, diagnóstico/captura ON,
concorrência agregada 64. Templates existentes, alterando somente ID e taxa/fonte
conforme matriz. Semente 20261107 preservada: não implica trajetórias independentes
ou comparações pareadas causais. Ver config.json/effective_config.json de cada run.
Política exploratory-offensive-v1 inalterada: RAM host >=2 GiB, disco >=4 GiB,
vítima <=1 GiB, fonte <=512 MiB, artefatos <=512 MiB, frescor 5 s, Docker 3 s,
limite global 240 s. CPU, fila e resultados HTTP não foram critérios de parada.

Imagens imutáveis verificadas contra o checkout, sem novo build:
- vítima sha256:03a186aa90eec03b874c82a887b245e7190fa45cd7256af3c077cb64943d52b0;
- fontes sha256:b94212edd4d31c34998aea870caebc4ba145c1593d1b8dfdc27fe4917719fe3e.
Ver image_verification*.json. Executor existente diagnostic_run, com preflight,
--previous-run, exportação e certificação; analisador offensive_analysis v2.

## Matriz efetiva e emissão

| Configuração | Nominal RPS | Iniciado RPS | Δ RPS | Admissões/submissões | Inícios | Expirações |
|---|---:|---:|---:|---:|---:|---:|
| A1-reference | 2 | 2.067 | +0.067 | 62/62 | 62 | 0 |
| A2 | 4 | 3.833 | -0.167 | 115/115 | 115 | 0 |
| A3 | 8 | 7.933 | -0.067 | 238/238 | 238 | 0 |
| A4 | 16 | 16.033 | +0.033 | 481/481 | 481 | 0 |
| F1 | 32 | 30.700 | -1.300 | 921/921 | 921 | 0 |
| F2 | 64 | 60.233 | -3.767 | 1807/1807 | 1807 | 0 |
| F3 | 128 | 66.833 | -61.167 | 3443/3443 | 2005 | 1438 |
| F4 | 192 | 65.000 | -127.000 | 4693/4693 | 1950 | 2743 |
| F5 | 256 | 63.100 | -192.900 | 5618/5618 | 1893 | 3725 |

RPS realizado = inícios HTTP em [30,60)/30. Admissão, submissão de tarefa,
início do callable, início lógico HTTP, recebimento na vítima e conclusão são
eventos distintos. Todas as janelas ofensivas foram respeitadas. Expiração é descarte
no cliente anterior ao HTTP; não é falha de atendimento da vítima.

## HTTP

| Configuração | Encerradas | Respostas | Erros HTTP | Timeouts | Conexão | Média ms | Mediana ms | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A1-reference | 62 | 62 | 0 | 0 | 0 | 248.04 | 243.09 | 305.90 |
| A2 | 115 | 115 | 0 | 0 | 0 | 286.25 | 262.64 | 439.11 |
| A3 | 238 | 200 | 0 | 38 | 0 | 1557.61 | 1681.69 | 2004.75 |
| A4 | 481 | 28 | 0 | 453 | 0 | 1954.36 | 2004.73 | 2005.80 |
| F1 | 921 | 921 | 0 | 0 | 0 | 55.61 | 45.89 | 95.89 |
| F2 | 1807 | 1807 | 0 | 0 | 0 | 843.81 | 960.97 | 1317.99 |
| F3 | 2005 | 2005 | 0 | 0 | 0 | 958.39 | 975.65 | 1068.14 |
| F4 | 1950 | 1950 | 0 | 0 | 0 | 992.97 | 1007.97 | 1139.57 |
| F5 | 1893 | 1893 | 0 | 0 | 0 | 1023.41 | 1035.43 | 1141.94 |

Durações acima incluem encerramentos conhecidos, inclusive timeouts; não descrevem
exclusivamente respostas bem-sucedidas. As distribuições somente de respostas estão
em cada summary.json. Não há durações imputadas a censura. Ausência de erro não
implica ausência de degradação: F2 apresenta duração muito maior que F1.

## Computação e persistência

| Configuração | Submetidas/iniciadas/concluídas | CPU/op ms | Espera média/p95 ms | Parede média ms | Aguardando/em execução em E− | Conclusões pós-E | Última conclusão s | Pendentes no corte |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A1-reference | 62/62/62 | 233.93 | 6.53/43.44 | 234.44 | 0/2 | 2 | 60.270368 | 0 |
| A2 | 115/115/115 | 241.36 | 37.45/178.83 | 241.41 | 0/1 | 1 | 60.163149 | 0 |
| A3 | 238/238/238 | 262.29 | 1309.33/1939.25 | 262.63 | 11/2 | 13 | 61.684606 | 0 |
| A4 | 481/481/481 | 259.47 | 16339.02/30882.52 | 259.59 | 249/2 | 252 | 92.537536 | 0 |
| F1 | 921/921/921 | 30.35 | 6.75/28.95 | 30.40 | 0/0 | 0 | 59.999024 | 0 |
| F2 | 1807/1807/1807 | 32.88 | 773.05/1227.48 | 32.88 | 22/2 | 24 | 60.355807 | 0 |
| F3 | 2005/2005/2005 | 30.81 | 884.31/991.76 | 30.79 | 59/2 | 61 | 61.233978 | 0 |
| F4 | 1950/1950/1950 | 31.72 | 917.56/1058.74 | 31.70 | 60/2 | 62 | 61.293770 | 0 |
| F5 | 1893/1893/1893 | 32.51 | 946.57/1060.27 | 32.50 | 58/2 | 61 | 61.154465 | 0 |

E− é o estado imediatamente anterior a 60 s. Há filas/esperas observáveis nas
operações, com acúmulo pronunciado em A3/A4 e F2–F5. Espera inclui fila, IPC e
agendamento; qualquer valor positivo isolado não comprova saturação do pool.
A4 mantém trabalho residual até 92,538 s (32,538 s após E). Zero pendente no snapshot
não é por si prova de impossibilidade de ingressos futuros; ingress_closed continua
condição externa. Operações de setup sem identidade permanecem unknown, separadas.

A4: 1 submissão(ões) computacional(is) em/após E, embora o início lógico HTTP estivesse dentro da janela. Isso explica por que conclusões pós-E podem exceder pendências em E−; não é violação de emissão.

F5: 1 submissão(ões) computacional(is) em/após E, embora o início lógico HTTP estivesse dentro da janela. Isso explica por que conclusões pós-E podem exceder pendências em E−; não é violação de emissão.

## Recursos e limitação dos geradores

| Configuração | CPU média/máxima % Docker | Memória máx MiB | Tick CPU mediana/máx s | Coleta bruta mediana/máx s | Pico tarefas não iniciadas/fonte | Despacho fonte média/máx ms |
|---|---:|---:|---:|---:|---:|---:|
| A1-reference | 10.18/75.93 | 43.30 | 5.035/6.081 | 3.014/3.066 | 1 | 0.53/1.60 |
| A2 | 21.71/182.41 | 31.50 | 5.035/6.051 | 3.015/3.022 | 1 | 0.51/2.46 |
| A3 | 46.20/207.70 | 31.27 | 5.036/6.044 | 3.013/3.022 | 1 | 0.42/1.44 |
| A4 | 97.39/209.52 | 49.92 | 5.037/6.049 | 3.011/3.023 | 1 | 0.41/1.87 |
| F1 | 17.02/112.42 | 32.45 | 5.033/6.076 | 3.014/3.023 | 1 | 0.44/2.06 |
| F2 | 43.78/234.95 | 37.67 | 5.072/6.111 | 3.015/3.022 | 33 | 271.56/1140.03 |
| F3 | 49.96/229.11 | 45.16 | 5.070/6.301 | 3.014/3.024 | 728 | 6353.21/12864.21 |
| F4 | 50.18/231.66 | 41.12 | 5.060/6.253 | 3.014/3.024 | 1382 | 9523.88/18314.19 |
| F5 | 42.51/230.61 | 40.87 | 5.069/6.173 | 3.013/3.039 | 1865 | 11443.47/21041.20 |

CPU/memória são médias/máximos de ticks suportados, não médias contínuas ponderadas.
A média inclui pré/pós sem carga e não mede CPU durante o ataque isoladamente.
CPU Docker >100% representa mais de um núcleo. Não houve interpolação; lacunas,
contagens por fase e amostras constam em summary.json. Não há evidência apenas de
CPU usada para afirmar saturação. O pico das fontes é a diferença observada entre
tarefas submetidas e iniciadas, não acesso à fila interna do executor. O primeiro
slot em trânsito pode produzir pico 1 sem backlog relevante. A espera de despacho
inclui tarefas que posteriormente expiraram, não só as convertidas em HTTP.

F3–F5 mostram forte acúmulo no cliente e expirações. A taxa HTTP ficou próxima de
63–67 RPS, apesar de 128–256 nominais. Há evidência direta de limitação do sistema
cliente/executor na carga entregue; a capacidade da vítima também participa do
feedback através da duração das chamadas e da concorrência. Não se atribui toda a
redução à vítima nem se identifica causalmente um único gargalo. Admissões também
ficam abaixo de nominal×30: o gerador usa esperas relativas e tem custo de despacho,
logging e manutenção de Futures. Sem perfilamento, não separar suas contribuições.

## Integridade, certificação e incidente

Todas as execuções novas: dataset válido/elegível, fechamento computacional íntegro,
sem conflitos de identidade, sem início ofensivo fora da janela e captura aceita.
Manifestos foram novamente conferidos por tamanho/SHA256, incluindo A1; resultados
em final_hash_verification.json. Verificações por run em raw/dataset_validation.json,
raw/operational_policy.json e analysis/summary.json (no diretório reports).
Todos os recursos experimentais foram removidos; redes preexistentes ficaram vazias;
quatro contêineres externos foram preservados. final_environment.json registra isso.

A2 teve um erro de invocação OFFLINE: o destino da análise estava dentro da árvore
raw/dataset do run, vedado pelo analisador. O coletor havia terminado com returncode=0
 e certificação completed. A progressão parou, o problema foi diagnosticado e somente
a análise dos mesmos dados foi executada no caminho correto de reports. Após confirmar
integridade e limpeza, a progressão continuou. Não houve repetição experimental,
alteração de código ou flexibilização. analysis.log e progress/finished.initial_stop
preservam a ocorrência; progress.json mantém a mensagem histórica mesmo com status
completed, por rastreabilidade. A tabela consolidada usa a análise válida posterior.

## Conclusões e recomendações para discussão de B2

1. Executadas A2–A4 e F1–F5; A1 reutilizada do piloto. Uma realização por intensidade.
2. Degradação HTTP manifesta por timeouts em A3 e A4. F2–F5 mostram duração/espera
   elevadas sem timeouts. Não se reduz a definição de degradação à taxa de erros.
3. A fila computacional cresce em A3 e principalmente A4; em flooding há acúmulo
   importante de F2 em diante. Valores e limites de observação estão nas tabelas.
4. Residual: A4 é o mais prolongado; nos floodings altos observa-se aproximadamente
   1,2–1,3 s após E. A4 inclui chegada/submissão tardia de tentativa iniciada na janela.
5. A taxa realizada acompanha aproximadamente o nominal em A1–A4 e F1/F2; deixa de
   acompanhar F3–F5, cujas admissões pendentes expiram ao fechar a janela.
6. Filas/atrasos e expirações no cliente sustentam limitação de geração/entrega nos
   floodings altos; não equivalem a medir a capacidade HTTP potencial da vítima.
7. Para discussão posterior: A2/A3 cobrem pressão moderada e transição com timeouts;
   A4 oferece degradação severa. F1/F2 cobrem baixa pressão e transição de espera;
   F3 pode representar uma condição limitada pela entrega. F4/F5 não demonstraram
   aumento correspondente de tráfego realizado, portanto não devem ser escolhidos
   apenas pelo nominal maior. Nenhuma configuração final de B2 foi selecionada.
8. Antes da campanha definitiva: resolver/documentar CPU esparsa; validar cobertura
   e definição de recuperação, dimensionamento/semântica do gerador nas altas taxas,
   delineamento e repetições. Somar tráfego legítimo altera a capacidade disponível;
   resultados isolados não predizem diretamente as intensidades combinadas.

Sem comparação inferencial, seleção automática, detectores ou calibração. Não foram
alterados mecanismos, kernels, workers, timeout, instrumentação ou política.

## Artefatos e IDs

- A1-reference: run `d5541220539243f0872a09dcf977bc39`, dataset `/home/henrique-givisiez/Documents/Faculdade/TCC/TCC/experiment_results/b11-integrated-asymmetry-20261107-r1/dataset`, análise `reports/b12-isolated-20261107T200251Z/A1-reference`.
- A2: run `2611cd8d55604596aab2d6b68ead4c9b`, dataset `/home/henrique-givisiez/Documents/Faculdade/TCC/TCC/experiment_results/b12-isolated-20261107T200251Z/A2/dataset`, análise `reports/b12-isolated-20261107T200251Z/A2`.
- A3: run `fd2c40d54c454ff089616115522651c1`, dataset `/home/henrique-givisiez/Documents/Faculdade/TCC/TCC/experiment_results/b12-isolated-20261107T200251Z/A3/dataset`, análise `reports/b12-isolated-20261107T200251Z/A3`.
- A4: run `757d0fa7280e40ed873ef9bdad475279`, dataset `/home/henrique-givisiez/Documents/Faculdade/TCC/TCC/experiment_results/b12-isolated-20261107T200251Z/A4/dataset`, análise `reports/b12-isolated-20261107T200251Z/A4`.
- F1: run `af2fddd5a99c487d90b2c03c21ceffeb`, dataset `/home/henrique-givisiez/Documents/Faculdade/TCC/TCC/experiment_results/b12-isolated-20261107T200251Z/F1/dataset`, análise `reports/b12-isolated-20261107T200251Z/F1`.
- F2: run `57bef61bb7ac4bdf817d7e8555acba76`, dataset `/home/henrique-givisiez/Documents/Faculdade/TCC/TCC/experiment_results/b12-isolated-20261107T200251Z/F2/dataset`, análise `reports/b12-isolated-20261107T200251Z/F2`.
- F3: run `8d96566727b144d3bba7ff5ac8ee422c`, dataset `/home/henrique-givisiez/Documents/Faculdade/TCC/TCC/experiment_results/b12-isolated-20261107T200251Z/F3/dataset`, análise `reports/b12-isolated-20261107T200251Z/F3`.
- F4: run `b5093d44ee934c0a8848a85446e1250b`, dataset `/home/henrique-givisiez/Documents/Faculdade/TCC/TCC/experiment_results/b12-isolated-20261107T200251Z/F4/dataset`, análise `reports/b12-isolated-20261107T200251Z/F4`.
- F5: run `f7db57b269ae48b6a3d6b9b94b56a750`, dataset `/home/henrique-givisiez/Documents/Faculdade/TCC/TCC/experiment_results/b12-isolated-20261107T200251Z/F5/dataset`, análise `reports/b12-isolated-20261107T200251Z/F5`.

Matriz e comandos: experiment_results/b12-isolated-20261107T200251Z/plan.json, remaining_plan.json e diretórios por intensidade.
Preflight/attempt, imagem/configuração/proveniência, journals, HTTP/RTT, CPU,
computação, PCAP/CSV, certificado e manifesto estão em cada run. comparison.csv e
progress.json registraram a progressão; consolidated.csv/json incluem também A1 e
as métricas adicionais das fontes. finished.json confirma oito execuções concluídas.
Disco livre final: 33821044736 bytes. Sem limpeza ampla, commit ou push.
