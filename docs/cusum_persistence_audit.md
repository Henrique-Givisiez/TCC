# Auditoria do CUSUM e da persistência pós-evento

23/10/2026. Escopo: implementação atual, testes sintéticos e diagnóstico separado
dos scores/decisões/observações **já existentes**. Não houve fitting, calibração,
scoring ou avaliação nova sobre TEST, nem alteração do detector, limiares,
resultados congelados, campanhas, commit ou push. Os trabalhos anteriores de
HTTP permanecem separados. Não há AGENTS.md na cadeia de diretórios do checkout.

**Conclusão:** a implementação corresponde ao CUSUM superior padronizado declarado.
Na seed ilustrativa contínua, a persistência é compatível quantitativamente com
acúmulo muito superior ao limiar, sem reset após alarme. A feature pós-evento não
fica elevada em média frente à BASELINE ou ao B pareado; flutuações ainda produzem
incrementos positivos em algumas janelas. Não há starts atacantes tardios nesse
run. A recuperação abaixo do limiar não foi observada antes do fim do horizonte.

## Implementação e contratos atuais

```text
z_t = (x_t − μ_B) / σ_B
C_inicial = 0
C_t = max(0, C_anterior + z_t − k), k = 0.5
alarme_t = (C_t > h)      # decisão separada; empate é negativo
```

| Item | Constatação no checkout |
|---|---|
| Fórmula/direção | `analysis/detection/detectors/cusum.py`, CUSUM.update: superior unilateral; sem valor absoluto, teto ou componente inferior. Score adimensional. |
| Padronização | `_standardized.StandardizedUpperTail` delega a `ZScore.start_run/update`, usando baseline congelada da mesma feature/representação/janela. Não estima média ou sigma com TEST; CUSUM não possui fit. |
| Média/variância | `zscore.ZScore.fit` agrupa observações válidas dos runs BASELINE, pesos iguais por observação; média e variância amostral exatas em Fraction, ddof=1. Null é excluído e contado. Não é média de médias dos runs. |
| Precisão | `_moments`: Decimal privado, 50 dígitos, ROUND_HALF_EVEN; subtrai a média racional exata antes do arredondamento. Não depende do contexto Decimal global. |
| Sigma zero/insuficiente | Baseline com menos de duas observações ou variância zero é rejeitada. Leitura valida sigma positivo/finito e consistência com os momentos exatos. Não substitui zero por epsilon. |
| Sigma pequeno positivo | Não há piso/floor ou regularização específica: um sigma positivo representável e consistente é aceito. Pode amplificar resíduos. O sigma do caso real é 2,760545, não próximo de zero. Valores fora da faixa representável do contexto não têm garantia de aceitação. |
| k/início | Configuração canônica única k="0.5", initial_state="0". start_run cria estado dinâmico novo, mesmo reutilizando objeto detector/modelo. |
| Separação de runs | Reuso do mesmo estado com outro run, janelas fora de ordem, salto de índice ou fronteira descontínua causa ContractError. Um run novo exige start_run. |
| Observação ausente | Retorna score=None e motivo missing_observation_reset, **zera** o acumulador. Próximo dado válido recomeça do zero. Não imputa z=0, não conserva estado através da lacuna. O missing="preserve" do componente exige preservar o registro ausente, não sua memória dinâmica. |
| Regra de decisão | `empirical.StrictUpperTail.decide`: score > threshold; sem confirmação, histerese ou latch. Ausente → decisão=None. A política não altera o acumulador do scorer. |
| Origem de h | `EmpiricalUpperTail`: quantil empírico higher dos scores CALIBRATION benignos, índice zero-based ceil((N−1)(1−alpha)), alpha=0.01. Não deriva h de TEST e não ajusta a FPR após observar TEST. |
| Reset após alarme | **Ausente.** Há inicialização entre runs, reset por ausência e reflexão natural em zero; não há reset por decisão positiva, t=48, início/fim de ataque ou drenagem. |
| Horizonte | Scoring congelado processou [0,144), em ordem, e só depois se avaliou primary [48,144). A memória anterior a 48 não foi apagada. Disponibilidade é o fechamento da janela, sem benchmark de latência do detector. |

A padronização usa o desvio-padrão das **observações da feature por janela de 1 s**,
não o erro-padrão da média de todas as 1152 observações. Dividir sigma por sqrt(N)
neste ponto mudaria o método.

## Score, alarme e detecção de evento

- **Score:** estado numérico retornado por CUSUM.update, sem ler limiar ou GT.
- **Alarme:** decisão bool/None, por janela, comparando score com h congelado.
  Score alto não é uma probabilidade de ataque, nem decisão latched.
- **Detecção de evento:** avaliação separada com GT original: exige alarme em
  janela cuja observação sobrepõe o evento efetivo e disponibilidade não anterior
  ao começo. A política V2 admite disponibilidade após o fim do evento se a janela
  observada o sobrepõe. Alarme inteiramente posterior não detecta aquele evento.

No caso real, o resultado **já publicado** em 15B é event_detected=true, primeira
disponibilidade de detecção em t=50 s e delay 1,990413039 s. Isso é um evento
detectado; as 59 janelas pós-evento positivas não são 59 novos ataques detectados.

## Verificação sintética manual

Novo `tests/test_cusum_persistence_audit.py`: somente dados sintéticos. Baseline
manual [8,10,12], μ=10, sigma amostral=2; não se chama fitter para construí-la.
O h=2 abaixo é **apenas um limiar sintético** para testar a decisão estrita.

| Sequência x | z e incremento | Scores esperados/conferidos |
|---|---|---|
| 10 repetido, estado inicial zero | z=0, z−k=−0.5 | 0 em todas as janelas. |
| 14,14,14; depois 10×9 | Aumento: z=2, +1.5; retorno: z=0, −0.5 | 1.5,3,4.5; 4,3.5,3,2.5,2,1.5,1,0.5,0. Com h=2, quinta janela de retorno desliga o alarme no empate. |
| 14,14; recuperação 13,12,11,10,9,10×6 | Recuperação z=1.5,1,0.5,0,−0.5,0…; contribuições +1,+0.5,0,−0.5,−1,−0.5… | 1.5,3; 4,4.5,4.5,4,3,2.5,2,1.5,1,0.5,0. O sinal pode cair e o acumulador ainda crescer/ficar estável. |
| 14,None,10,14 | Ausência não é z=0 | 1.5,None,0,1.5; estado explicitamente zerado na ausência. |
| Estado de run A reutilizado no B | Proibido | ContractError; start_run novo + x=10 → 0. |
| sigma=0 / sigma=1e−12 | Zero rejeitado; pequeno positivo consistente sem piso | Com μ=10 e x=11: z=10^12 e score=999999999999.5. |

Também se verificou que decidir um alarme não modifica estado: scores 1.5,3,4.5
produzem decisões false,true,true sem reset intermediário. No teste de evento
sintético [48,51), há primeira detecção em 50 e quatro alarmes depois do evento;
um alarme somente na janela [51,52) não o detecta. Essa chamada pura do avaliador
recebe exclusivamente decisões sintéticas, sem carregar fontes/manifest/pipeline.

**91 testes passaram**: 8 novos e 83 existentes sobre EWMA/CUSUM, scores e política
empírica. Saída integral: `experiment_results/cusum-persistence-audit-20261023/tests.log`.

## Identidade e encadeamento das evidências reais

Não foi escolhida uma seed por desempenho. O manifest 15C e sua documentação
já definem a menor seed pareada elegível, **171864802**; o auditor confere que é
a mínima do inventário. 15C é entrega descritiva, **não FROZEN**; as autoridades dos
scores/decisões e métricas são 15A/15B FROZEN.

O script novo `experiments/audit_cusum_persistence.py` resolve referências por
manifests e verifica SHA256/tamanho, identidade run/seed/scenario/feature,
configuração, baseline e threshold. Não importa módulos do pipeline de detecção.
Verifica novamente os hashes dos 17 arquivos consumidos antes de publicar apenas
um diagnóstico novo em diretório separado. Confere também cada um dos 144
request_starts armazenados com a tabela Stage10 e a contagem dos starts do CSV
original. Os 320 request_begin atacantes do journal coincidem com os IDs e
instantes das linhas originais. Não conta conclusões como inícios.

| Autoridade/artefato | Identidade verificada |
|---|---|
| 15A scoring manifest | `089a25681dd13810a94a92def805aa9a7e314955ebdcca671d625d959ae3a9d5` |
| 15B evaluation manifest | `2b36134d60f9dd5a4dc5bd721f4c5df194cc8ad695ab5d71c73156b5bb5863ca` |
| 15B freeze manifest | `8232ce397022963dd8741d7e14746630a822cdf74cda4f4a113d7ca5a974f2c2` |
| Four-method calibration freeze | `898e79394ac48a86a734100d324d0b6b966412166a0eac105dbdeccb2bd236f5` |
| Exemplo C | Entry 20; run_id `667624953df540e9aa3f3258d96960dd`; seed 171864802 |
| Score/decisão | `experiment_results/stage15a-test-scoring-20261019/runs/20/cusum/request_starts.json`, SHA `380c9fc3a46aef802ddca337968f57c6ff892f54a1c7d170b92925bc5acb44cd` |
| Baseline manifest | SHA `b2a58d67502bb4263527e52e147423e49246413a52e986073b9de5b04fb2e1e2` |
| Threshold manifest | SHA `48bc05a116e2e844eb4b871baf708a9223fc34dfc8267ea3344ac06909883481` |

Paths completos, hashes/tamanhos dos demais arquivos e parâmetros sem
arredondamento estão em `verified/diagnostic.json`. O run foi localizado por
`test_inventory.entries → output_path/artifacts`, não pelo nome adivinhado de CSV.
O B pareado é entry 19, lido pela mesma cadeia 15A/inventário e respectivas refs.

### Baseline e limiar deste caso

- μ_B exata = 2279/288 = **7,913194444444…** starts/janela.
- Variância amostral exata = 631535/82872; sigma_B = **2,760544816542451…**.
- Seis runs BASELINE; 192 observações válidas/run em [48,240): **1152 válidas,
  zero ausentes**. Média/sigma não vieram do B pareado nem deste TEST C.
- h = **4,902172084049390…**, alpha=0.01, índice 3706 de N=3744 scores válidos
  de 12 runs CALIBRATION, seleções [48,360), preservando história causal anterior.
  Há 37 scores acima do limiar na calibração: FPR descritiva 37/3744≈0,98825%.
  Essa taxa nominal de janela não é probabilidade de falso alarme de uma sequência
  inteira/ARL e não foi ajustada neste diagnóstico.

## Fim nominal, emissão, drenagem e score disponível

| Marco no run C | Segundos desde início |
|---|---:|
| Começo efetivo | 48,00958696099951 |
| Fim nominal | 84 |
| Último início atacante | 83,95601908900062 |
| Stop solicitado | 84,00743231399974 |
| Fechamento efetivo da emissão | 84,0074367090001 |
| Última conclusão atacante / drained_end | 84,0164188029994 |

**Backlog tardio não foi demonstrado neste run:** zero starts atacantes ≥84 e
zero ≥84,007436709. Existem 320 admissions, 320 request_begin e 320 request_finish
no journal atacante, sem abandoned_admission. Uma conclusão ocorre após o fim
efetivo; ela não é um request_start e a drenagem termina cerca de 8,982 ms depois
do fechamento. Os 464 starts observados após o fechamento, incluindo a janela de
fronteira e o restante do run, são benignos. Nas 59 janelas completas [85,144)
são 456 starts, também benignos. Capacidade de backlog do gerador contínuo não
prova backlog específico: aqui não explica a persistência por quase 60 s.

Não existe um score novo calculado exatamente em t=84,007436709. O último score
**disponível** é o da janela [83,84), disponível em 84:
**106,382765614276626…**, contra h=4,902172084… .
A janela [84,85) cruza o fim do evento: x=8, score=105,914210695347354…,
mas só está disponível em 85; não deve ser antecipada para o fim efetivo.
A primeira janela completamente pós-evento [85,86) tem x=9,
score=105,807903110352870… disponível em 86.

## Decomposição quantitativa do pós-evento

Consideram-se somente as **59 janelas completas** [85,144). Os scores/decisões
são os oficiais, e os z/incrementos abaixo são diagnóstico aritmético separado.

| x (starts/janela) | Janelas | z_t | z_t − 0,5 |
|---:|---:|---:|---:|
| 4 | 4 | −1,417544 | −1,917544 |
| 5 | 6 | −1,055297 | −1,555297 |
| 6 | 10 | −0,693050 | −1,193050 |
| 7 | 9 | −0,330802 | −0,830802 |
| 8 | 8 | 0,031445 | −0,468555 |
| 9 | 10 | 0,393692 | −0,106308 |
| 10 | 3 | 0,755940 | 0,255940 |
| 11 | 6 | 1,118187 | 0,618187 |
| 12 | 2 | 1,480434 | 0,980434 |
| 13 | 1 | 1,842682 | 1,342682 |

O ponto de equilíbrio é x=μ_B+k·sigma_B≈**9,293467**. Portanto x=8 ou 9 está
acima da média baseline, mas **reduz** o score: z positivo não basta para crescer.

- Feature pós: média **7,7288135593**, mínimo 4, máximo 13. O B pareado nas mesmas
  janelas tem média **7,7288135593**, mínimo 4, máximo 12. Não se conclui igualdade
  de distribuições apenas por médias iguais.
- z médio **−0,0667914841**, intervalo [−1,4175442547; 1,8426817507].
- Incremento médio **−0,5667914841**; 47 janelas reduzem e 12 aumentam o score;
  nenhuma é exatamente neutra. Das 59 positivas, 29 têm x≤μ_B.
- Soma dos incrementos positivos **+7,7804923284**; negativos **−41,2211898882**;
  saldo **−33,4406975598**. Equivale a soma(z)=−3,9406975598 menos 59·0,5=29,5.
- O score anterior às 59 atualizações é o da janela de fronteira: **105,9142106953**.
  Após todas elas: **72,4735131356**. O estado não chega a zero; não há clipping
  inferior ativo nesse trecho. Um pico pós de **107,5561567740**, disponível em
  t=90, é explicado pelos incrementos ainda positivos, não por erro de reset.
- Todas as **59/59 decisões** nas janelas completas são positivas: 59 s de
  exposição observacional completa. A última disponibilidade em 144 fica
  **59,992563291 s** após o fim efetivo, ainda acima de h. Esse intervalo entre
  disponibilidades não certifica um monitor físico contínuo entre amostras.

**Memória acumulada:** o estado herdado (~106) é muito maior que h (~4,9).
**Observações elevadas:** há flutuações individuais, mas sem elevação da média
pós frente à baseline/B; 12 incrementos positivos retardam a queda e 47 negativos
a dominam. **Backlog:** sem starts atacantes tardios demonstrados.
**Conclusões/drenagem:** uma conclusão tardia, encerrada em 84,0164, não sustenta
59 janelas de request_starts. Não se atribuiu toda persistência de outras features
como CPU/duração a esse mesmo mecanismo: suas observações e populações diferem.

### Conferência da recorrência e limite da previsão ideal

O arquivo `verified/window_arithmetic_DIAGNOSTIC.csv` contém, por janela, x, z,
z−k, score anterior **oficial**, score atual oficial, decisão oficial e valor
esperado de **um passo**, identificado como diagnóstico. Não encadeia um novo
pipeline de scores. Reproduz a subtração racional e o arredondamento em 50 dígitos:
**144 passos verificados, zero discrepâncias**, erro máximo 0. Nenhum score,
decisão ou artefato oficial foi substituído. As 144 contagens observadas também
coincidem com a contagem dos inícios brutos, sem reextrair features.

Se, a partir de um estado S>h, toda observação válida seguinte fosse exatamente
μ_B, então z_t=0 e

```text
C_após_n = max(0, S − n·0.5)
n_para_desligar_alarme = ceil((S−h)/0.5)   # empate já desliga
n_para_zero = ceil(S/0.5)
```

Com S=106,3827656143, seriam **203 atualizações ideais** para score≤h e 213
para zero. Isso parte do último estado disponível no fim efetivo, não redefine
a posição das janelas posteriores. Com o estado final observado 72,4735131356,
seriam **136 atualizações ideais adicionais** para score≤h. Como as janelas são
1 s, esses números corresponderiam a segundos apenas sob a hipótese de dados
válidos consecutivos e exatamente z=0; não são prazos reais garantidos.

Ruído pode elevar ou reduzir o estado, mudança residual pode mantê-lo alto e
uma ausência aplica o reset declarado. Média zero em distribuição não significa
z_t=0 em cada janela. Não se estimou tempo médio de recuperação, ARL ou intervalo
de confiança a partir dessa extrapolação. O scoring congelado termina em 144 s
antes da recuperação: **recuperação censurada à direita**. A tabela Stage10
possui cauda adicional; ela não autoriza prolongar os scores oficiais nesta etapa.

## Literatura e interpretação

O [manual SAS/QC, fórmula CUSUM unilateral](https://support.sas.com/documentation/cdl/en/qcug/68161/HTML/default/qcug_cusum_sect024.htm)
apresenta a mesma recorrência padronizada com S0=0, k positivo e sinal ao exceder h.
O [NIST, CUSUM Control Charts](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm)
explica a forma tabular, os papéis de k/h e os ciclos sequenciais. O
[NIST, CUSUM ARL](https://www.itl.nist.gov/div898/software/dataplot/refman2/auxillar/cusumarl.htm)
distingue número esperado até sinal e inicialização; k=0,5 é um exemplo comum
para mudança alvo de um sigma. Essas referências não transformam o limiar
empírico do projeto em uma garantia teórica de ARL ou de recuperação.

[Lau e Gandy (2012), Optimality of Non-Restarting CUSUM charts](https://arxiv.org/abs/1205.1937)
distinguem restart após sinal e monitoramento sem restart em cenários de mudanças
múltiplas. Seu estudo considera também fronteira superior: não é prova de
optimalidade desta implementação **sem teto**, nem autorização para introduzi-lo
em TEST. A política depois de um alarme faz parte do método e do objetivo; não
existe exigência universal de reset imediato só porque a curva persiste.

A recuperação ideal descrita acima é uma dedução direta da recorrência, não um
prazo prometido pela literatura. O método detecta desvio acumulado; não estima
a probabilidade instantânea de ataque nem certifica automaticamente seu término.

## Recomendação

**Manter a configuração e os artefatos atuais.** Não foi demonstrado defeito de
fórmula, normalização ou estado; os testes manuais e o diagnóstico dos dados
congelados concordam com o método declarado. Explicar a persistência e reportar
separadamente detecção de evento, alarmes pós, trajetória de recuperação e censura.

Se a finalidade futura for segmentar episódios ou detectar recuperação rápida,
propor **variante separada**, com regra de rearmamento/restart explicitamente
definida antes dos dados, população/limiar próprios e avaliação independente de
falsos alarmes, detecção repetida e recuperação. Não escolher reset, vazamento,
cooldown ou teto para melhorar esta figura; não usar o fim conhecido pelo GT em
runtime. Um reset após alarme mudaria recorrências e a distribuição dos scores,
inutilizando o mesmo limiar empírico como calibração demonstrada para a variante.
Também não seria comparável às decisões históricas sem declarar versão/desenho.
Nenhuma variante foi implementada ou calibrada nesta etapa.

## Arquivos, evidências e execução

- `tests/test_cusum_persistence_audit.py`: 8 testes sintéticos novos.
- `experiments/audit_cusum_persistence.py`: leitura verificada e aritmética separada;
  sem imports de scoring/fitting/calibração/avaliação no diagnóstico de TEST.
- `docs/cusum_persistence_audit.md`: este relatório.
- `experiment_results/cusum-persistence-audit-20261023/verified/`: JSON e CSV finais.
- Mesmo diretório pai: tests.log, plot.py, cusum_persistence.png e PDF. A figura usa
  observações/scores oficiais e incrementos diagnósticos, com x no fechamento da
  janela; região vermelha é o evento efetivo. A curva em degraus mantém o último
score disponível até a próxima disponibilidade, sem interpolar score em actual_end.

Comandos executados (destino novo obrigatório para repetir o auditor):

```bash
.venv/bin/python -B -m unittest tests.test_cusum_persistence_audit tests.test_ewma_cusum tests.test_statistical_scores tests.test_empirical_policy -v
.venv/bin/python -B -m experiments.audit_cusum_persistence --output experiment_results/cusum-persistence-audit-20261023/verified
MPLCONFIGDIR=/tmp/cusum-audit-mpl .venv/bin/python -B experiment_results/cusum-persistence-audit-20261023/plot.py
```

Referências principais no código: CUSUM.update (cusum.py:20),
StandardizedUpperTail.start_run/residual (_standardized.py:44/:51),
ZScore.fit/start_run/update (zscore.py:39/:62/:82), sample_moments (_moments.py:21),
EmpiricalUpperTail.calibrate e StrictUpperTail.decide (empirical.py:97/:178),
score_run (pipeline.py:107), avaliação de evento V2 (evaluation/events.py:121),
contagem de request_starts (experiments/extract_features.py:226), reconciliação
source (simulator/source_aggregate.py:26) e fechamento de emissão
(simulator/ground_truth.py:140). As implementações e resultados originais foram
somente lidos. Testes anteriores de auditoria HTTP não foram alterados.

**Resposta curta — “O CUSUM está correto? Por que persiste? Devemos mantê-lo?”**
Sim, para a definição implementada e congelada. Persiste porque acumula evidência
sem reset após alarme: o estado chega a ~106 para um limiar ~4,9 e ainda vale
~72,5 ao fim do acompanhamento, embora a média de request_starts já tenha voltado
ao nível benigno. Devemos mantê-lo nesta avaliação; uma política de recuperação
ou reinicialização diferente exige variante, calibração e avaliação próprias.
