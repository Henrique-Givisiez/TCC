# Capítulo 5 — lote 2: atendimento legítimo na campanha definitiva

Figuras descritivas da partição TEST da campanha
`energy-powersaver-20261109`. São 60 execuções, 20 por cenário, em 20 blocos
completos. BASELINE, CAL_A e CAL_B não entram nos cálculos.

| Figura | PDF | PNG | Dados derivados |
|---|---|---|---|
| F5.2-A original, preservada | `figures/f52a_duracao_http_legitima.pdf` | `figures/f52a_duracao_http_legitima.png` | `processed/f52a_duracao_por_segundo.csv` |
| F5.2-A alternativa | `figures/f52a_duracao_http_timeouts_alternativa.pdf` | `figures/f52a_duracao_http_timeouts_alternativa.png` | `processed/f52a_duracao_por_segundo.csv`, `processed/f52a_timeouts_5s_por_execucao.csv`, `processed/f52a_timeouts_5s_resumo.csv` |
| F5.2-C | `figures/f52c_sucesso_timeouts.pdf` | `figures/f52c_sucesso_timeouts.png` | `processed/f52c_desfechos_por_execucao.csv` |

## Entradas e definições

O gerador `scripts/generate.py` lê o plano
`experiments/protocols/energy-powersaver-20261109/plan.json`, o inventário e
os `processed/http_phases.csv`, `processed/http_<execução>.csv` e
`processed/official_availability.csv` de
`reports/scientific_campaign_visualization_20261112/`, além de
`reports/investigacao-temporal-energy-20261110/series_1s.csv`. Os manifestos
das duas análises, bem como as 60 configurações efetivas, verificam a
proveniência. `processed/manifest.json` registra hashes SHA256 das entradas e
contagens de validação. Os CSV e PDFs deste lote são novos derivados; nenhum
artefato oficial foi regravado.

O processamento auditado da visualização científica
(`reports/scientific_campaign_visualization_20261112/scripts/audit.py`, funções
`cls`, `phase` e `main`) extrai `elapsed_seconds` (início HTTP),
`end_elapsed_seconds` (fim), `duration_ms` e `category` do log do cliente.
`http_2xx` corresponde a uma resposta HTTP 2xx; `timeout` é identificado no
`error_type`; respostas não 2xx, falhas de conexão e outras falhas permanecem
categorias distintas. A duração medida no cliente é, com tolerância de
arredondamento, `(end_elapsed_seconds − elapsed_seconds) × 1000`. O timeout
configurado nas 60 execuções TEST é **2 segundos**, tanto para fontes legítimas
como ofensivas. Uma resposta 2xx que termina depois de ACTIVE permanece na
coorte do segundo em que começou.

### F5.2-A

`series_1s.csv` contém uma linha para cada execução e segundo experimental.
Seu campo `benign_duration_2xx_ms` é a **média** das durações das respostas
legítimas 2xx cujos inícios HTTP caem no segundo `[t,t+1)`, conforme
`reports/investigacao-temporal-energy-20261110/analisar.py` (cálculo de
`benign_duration_2xx_ms`). Para cada cenário e segundo `[30,390)`, o gerador
calcula a mediana, Q1 e Q3 das médias de execução disponíveis. A banda Q1–Q3
é dispersão descritiva, não intervalo de confiança. Segundos sem resposta
2xx válida ficam ausentes; a linha tem lacunas. O painel inferior mostra
quantas das 20 execuções contribuíram em cada segundo. A escala vertical da
duração é logarítmica para manter visíveis tanto valores em torno de 40 ms
como valores próximos de 2.000 ms; a unidade continua milissegundos.

Cobertura de respostas 2xx por execução–segundo durante ACTIVE: L2,
2.400/2.400; A3, 242/2.400; F96, 909/2.400. Em 93 segundos de ACTIVE em A3
e 48 em F96, nenhuma execução forneceu duração 2xx. Portanto, a duração
observada durante o ataque é fortemente condicionada aos sucessos restantes;
esta figura deve ser lida junto de F5.2-C.

#### Diagnóstico da revisão

Nas 60 execuções TEST, em `[30,390)`, a maior duração **individual** de uma
resposta legítima 2xx foi **2.044,390466 ms**; 322 respostas 2xx ultrapassaram
2.000 ms. A maior média de execução em um segundo foi **2.034,168525 ms**.
A mediana temporal e Q3 máximos entre execuções foram, respectivamente,
**1.998,500343 ms** e **1.998,871948 ms**. O eixo da figura original terminava
em 2.500 ms; portanto, não houve truncamento das estatísticas desenhadas.
O limite de espera configurado nas 60 execuções foi de 2 s, mas as durações
observadas não possuem limite matemático rígido de 2.000 ms. A alternativa
marca essa referência com uma linha discreta e mantém o eixo até pelo menos
2.500 ms.

Mediana, Q1 e Q3 usam exatamente as mesmas médias válidas das execuções em
cada segundo. O gerador verifica que todos estão ausentes juntos. A banda
laranja aparentemente isolada perto de 300 s não corresponde a um cálculo
inconsistente: em 300 s havia apenas **5 execuções** com 2xx válido, mediana
de **816,7 ms**, Q1 de **82,1 ms** e Q3 de **1.273,4 ms**. Em 302 s, 8 execuções
produziram mediana de 82,5 ms e Q3 de 1.670,4 ms. A mistura de respostas
rápidas e demoradas produz uma banda alta com mediana próxima da base;
a linha tracejada, interrompida nos segundos sem 2xx, pode parecer ausente
em escala reduzida. A alternativa reduz a opacidade da banda e aumenta a
espessura da mediana, sempre desenhada acima das bandas.

Na **alternativa**, o painel inferior mostra timeouts legítimos em janelas
sem sobreposição de 5 s, alinhadas a 30, 150 e 270 s. Para cada execução,
`timeouts / benign_http_start × 100` soma as contagens por **instante de
início HTTP** de `series_1s.csv` dentro da janela; o desfecho pode ocorrer
depois. São 52 a 107 tentativas por execução e janela, sem denominadores
zero; as 72 janelas de cada execução permanecem dentro de uma única fase.
A mediana e Q1–Q3 são calculados entre as 20 proporções de execução; nenhuma
requisição individual é tratada como repetição experimental. As somas das
24 janelas ACTIVE foram verificadas contra `http_phases.csv` em cada execução.
O painel superior continua em janelas de 1 s. A cobertura original está
preservada em `f52a_duracao_por_segundo.csv`, campo `valid_executions`.
Segundos sem 2xx seguem ausentes e os segmentos não são ligados através
dessas lacunas.

### F5.2-C

`http_phases.csv` contém as coortes legítimas por **início HTTP** durante
ACTIVE `[150,270)`: `started`, `http_2xx_cohort`, `timeout_cohort`,
`other_cohort`, `entry_id`, `scenario` e `block`. Cada proporção é calculada
**dentro da execução**: `http_2xx_cohort / started` ou
`timeout_cohort / started`. Cada ponto representa uma execução; linhas cinzas
ligam as três execuções do mesmo bloco; traços escuros marcam a mediana entre
as 20 execuções do cenário. Não há teste inferencial nem IC. As categorias
são exclusivas e somam `started`; em ACTIVE, `other_cohort = 0` nas 60
execuções. Contagens totais por cenário (inícios / 2xx / timeout):

| Cenário | Inícios | 2xx | Timeout |
|---|---:|---:|---:|
| Tráfego legítimo | 37.914 | 37.914 | 0 |
| Ataque computacional assimétrico | 37.929 | 3.511 | 34.418 |
| Inundação HTTP | 37.933 | 13.304 | 24.629 |

O indicador operacional oficial em `official_availability.csv` usa
`timely_2xx / starts`, com base nos journals reconciliados. O numerador 2xx
coincide com a coorte deste lote, mas o denominador difere em 22 execuções:
2 de A3 e 20 de F96. Esta figura apresenta **sucesso eventual da coorte de
início**, não o sucesso dentro do prazo do indicador operacional. Os dois
estimadores não devem ser identificados como iguais.

Na revisão da F5.2-C, os traços escuros receberam os valores das medianas
calculadas entre execuções: 2xx de 100%, 7,7% e 35,1%; timeouts de 0%,
92,3% e 64,9%, na ordem dos três cenários. Os pontos, blocos, proporções e
denominadores permaneceram inalterados. O rodapé foi reduzido.

## Reprodução e verificações

Na raiz do repositório:

```bash
.venv/bin/python -B reports/capitulo5_figuras/lote2_atendimento_legitimo/scripts/generate.py
```

O script verifica os 20 blocos completos, a configuração das 60 execuções,
o timeout de 2 segundos, as somas exclusivas de desfechos, a igualdade das
contagens ACTIVE entre as duas análises e, para cada segundo válido de
`[30,390)`, a concordância da média de duração com os CSV HTTP auditados.
Foram conferidos **17.137** pares execução–segundo válidos nesse intervalo.
Na revisão, o gerador compara os CSV derivados originais antes de produzir
saídas e verifica os hashes do PDF e PNG originais da F5.2-A antes e depois;
esses arquivos são preservados. O script escreve a alternativa, atualiza
apenas a figura F5.2-C e cria os novos CSV de timeout e o manifesto deste
lote. Os PDFs são vetoriais; os PNGs são exportados a 240 dpi.

**Uso editorial:** a alternativa é preferível no corpo do capítulo para
mostrar em conjunto a duração observada e a evolução dos timeouts. A figura
original evidencia melhor quantas execuções contribuíram para cada mediana;
deve permanecer acessível como material de apoio ou apêndice. A legenda
LaTeX da alternativa deve mencionar a forte perda de cobertura 2xx durante
ACTIVE e a resolução diferente dos painéis. F5.2-C continua útil no corpo
do capítulo por mostrar a distribuição e o pareamento dos 20 blocos.
