# D1 — proposta operacional de caracterização benigna

Estado: **PREPARADO, NÃO EXECUTADO**,27/10/2026. Configurações completas validadas
offline. Não é release científica. Todos os limites novos abaixo são escolhas de
engenharia de DEVELOPMENT, não capacidade medida, SLO de aplicação real ou
parâmetros finais da campanha. Nenhum comando Docker foi executado nesta tarefa.

Referências: [pendências](development_service_pending_20261027.md),
[desenho DEVELOPMENT](../experiments/protocols/development_service_plan_20261027.json),
[resumo de serviço](service_summary.md), [operações](application_operations.md),
[CPU](cpu_accounting_audit.md) e [proxy](proxy_observability.md).

## 1. Parâmetros efetivos e justificativas

| Parâmetro | Proposta concreta | Justificativa/contrato |
|---|---|---|
| Topologia | Uma vítima, proxy estático,4 sources em `/medium`, sem ataque/autoscaling | Infraestrutura min=initial=max=1; proxy ligado; sources containers; ataque disabled, attackers=rate=0 |
| Operação |100000 iterações CPU, sleep0 | `simple_server.OPERATION_WORK_UNITS`; queries/defaults legados são inertes em `/medium` |
| Oferta inicial |1 RPS/cliente,4 RPS agregados | Metade do benigno histórico4×2 em `/medium`; início conservador, sem folga presumida |
| Patamares/teto |1,2,4,8,16 RPS/cliente →4,8,16,32,64 agregados | Dobrar explora faixa ampla em5 níveis; teto é limite de exploração, não capacidade estimada |
| Pool da aplicação |2 processos | `server.process_pool_workers=2`, encaminhado ao `ProcessPoolExecutor` |
| Timeout HTTP |2s configurados | `normal_traffic.request_timeout_seconds=2`; atacante inativo também explicita2. `requests` aplica timeout de conexão/leitura, não prazo total rígido da tentativa |
| Envios |64 send workers agregados benignos,16 por origem | `worker_quotas(64,4)` em `source_manager.py`; não são RPS nem processos da vítima. Fila de tarefas sem limite explícito |
| Duração nominal |150s por run | Margem para observar tendência além dos smokes curtos, com custo limitado |
| Warmup/útil |WARMUP `[0,30)`; MEASURE `[30,150)`,120s úteis | Mantém logs completos; expectativa inicial~480 starts úteis se oferta for atingida |
| Coleta vítima |tick1s, polling1s, history30s | Campos `monitoring` explícitos; `get_averages(window_seconds=1)` usa janela do tick e fallback/cache. History30 não é média de30s nem garantia de frescor |
| Coleta proxy |poll1s, timeout2s | Constantes técnicas `PROXY_POLL_INTERVAL_SECONDS` e `PROXY_COLLECTION_TIMEOUT_SECONDS` em `simulator/config.py`; não são campos JSON novos |
| Drenagem |Timeout local30s/source, espera conjunta host35s | Limites existentes em `normal_traffic.drain`, `source_runner` e `SourceManager.stop`; fim só por registro observado |
| Repetições |2 por nível, condicionais | Exploração inicial de consistência; não dimensionamento de IC ou amostra final |
| Recuperação |cleanup verificado, mínimo60s ocioso e infraestrutura/readiness/warmup novos | Evita carregar fila da instância anterior; pausa é margem operacional, não recuperação física comprovada |

Os JSONs explicitam também campos inertes: work/sleep legados, ataque desabilitado,
thresholds/cooldown do autoscaler desligado e custo fictício0,02/instância-hora.
Esses valores não são fatores nem orçamento financeiro real. O
[manifesto](../experiments/protocols/development_d1_20261027/manifest.json) guarda
a configuração efetiva completa por entrada, arquivo/hash, ordem, seed e saídas.

Evidências usadas: Stage6 `/medium` relatou mediana HTTP30,14ms e CPU média27,77%
em ensaio técnico de condições próprias ([registro](application_operations.md));
a campanha congelada empregou4 benignos×2RPS em `/medium`
([referência](continuous_attack_proposal.md)). Isso justifica começar abaixo e
atravessar essa taxa, sem inverter30ms para anunciar capacidade. O ambiente e a
instrumentação atuais diferem do histórico. Não escolher patamares por recall,
scores ou qualquer detector; CUSUM e calibração não entram em D1.

**Processos versus CPU:** `docker_manager.start_instance`, `HttpProxy.start` e
`SourceManager.start` não explicitam quota/cpuset/shares. Pool2 não reserva dois
núcleos nem limita todo o cgroup a200%; HTTP/IPC/outros processos também consomem.
100% Docker é um núcleo lógico equivalente. Registrar imagens/versões/limites
efetivos na execução e não normalizar CPU pelo pool. Não adicionar limites CPU
sem revisão própria. Decomposição por CPU lógica não bloqueia D1.

## 2. Seeds, ordem, recuperação e orçamento

Reservadas exclusivamente como **DEVELOPMENT**:

- A: **2273943714116859802**.
- B: **3803721254044484793**.

Derivação: SHA256 UTF-8
`development-d1-benign-20261027-v1:<A ou B>:<índice>`, primeiros8bytes unsigned
big-endian; índice0 em ambos, rejeitando colisões. Seeds64bits são aceitas no
contrato ativo. A [auditoria](../experiments/protocols/development_d1_20261027/seed_audit.json)
registra401 arquivos de configuração/metadados e47 valores históricos, incluindo
partições Stage14, piloto e smoke; hashes/seeds por arquivo; **zero colisões**.
Não foram usados scores, observações ou labels para escolher seeds. Futuros planos
devem consultar esta reserva; não existe alocador global que impeça reuso externo.

| Ordem condicional | Nível | RPS/cliente | RPS agregado | Réplicas |
|---|---|---:|---:|---|
|1–2|L01|1|4|A, B|
|3–4|L02|2|8|B, A|
|5–6|L03|4|16|A, B|
|7–8|L04|8|32|B, A|
|9–10|L05|16|64|A, B|

Mesmas duas seeds entre níveis permitem comparações exploratórias pareadas, sem
transformar os10 runs em10 réplicas independentes. Mesmo RNG não reproduz tempos
iguais com outra taxa. Reversão AB/BA reduz confusão dentro do nível; progressão
crescente ainda se confunde com deriva temporal. Não afirmar efeito causal puro
ou precisão inferencial a partir de duas réplicas.

Revisar **cada run antes do seguinte**. Se houver degradação no primeiro, parar
a progressão. A segunda réplica do mesmo nível só poderá confirmar o diagnóstico
após revisão/recuperação explícitas, sem subir carga. Nível maior exige as duas
réplicas atuais aceitas para progressão. Não há retry automático nem substituição
silenciosa de seed. Preservar a tentativa; eventual repetição usa outra entrada,
saída e decisão documentada, sem repetir até passar.

Recuperação: verificar status/finais dos sources, cleanup sem erros, ausência dos
contêineres anteriores e de outra campanha, porta de serviço livre. Registrar
instantes **observados** de cleanup e próximo início, separados por≥60s. Cada run
recria vítima/proxy/fontes, passa readiness e warmup. Cleanup com erro causa STOP,
não simples espera. Remover a instância descarta sua fila; não demonstra recuperação
do serviço em produção ou do host físico. Não adicionar sondagens ao intervalo útil
nem monitoramento adicional do host.

Orçamento máximo:10×150s=1500s (**25min**) nominais;1200s úteis. Reserva de35s/run
para espera de encerramento soma5min50s;9 pausas de60s somam9min: aproximadamente
40min antes de setup/exportação/revisão. Reservar **60–75min de sessão**, assumindo
imagens disponíveis e margem para inspeção. É estimativa de engenharia: builds,
daemon/I/O lento e investigação podem excedê-la. A espera35s não é limite rígido
do wall time total. Se parar após o primeiro run, não há obrigação de consumir
as outras nove entradas.

## 3. Critérios explícitos para decidir o próximo nível

Não há SLO externo informado. Os cortes são critérios experimentais para esta
exploração, propostos antes dos dados. Igualdade aos limites é aceita. CPU alta
isoladamente não define capacidade, degradação ou causa de falha.

### Oferta, starts e gerador

MEASURE: `R_start=N_starts/120`, `aderência=R_start/(4b)`, b por cliente.
Exigir aderência agregada entre0,8 e1,2; por origem,
`starts_i/(120b)` entre0,65 e1,35. São tolerâncias amplas para ritmo exponencial
e scheduling: expectativa inicial480 agregada (SD Poisson ideal~22),120/source
(~11), sem alegar que a implementação seja Poisson ideal nem que esses cortes
sejam ICs. Não exigir igualdade exata entre oferta e starts.

Parar/investigar se houver desvio fora da faixa, fonte zerada ou starts após150s
acima de `max(4,1% dos starts totais)`. Inspecionar também quatro coortes de30s e
crescimento de drenagem. Isso sinaliza **possível insuficiência do gerador/arranjo**,
sem atribuição causal automática. Benignos não registram admissões de tarefas no
journal; não é possível medir exatamente admissão→start. Respostas lentas podem
ocupar send workers e provocar fila. Não trocar concorrência no meio do bloco nem
atribuir todo déficit à vítima ou à origem.

### Serviço e seleção das durações

Acompanhar a coorte útil até o fim observado da drenagem. Critérios de progressão:

- n≥200 sucessos2xx na coorte útil: cerca de10 observações na cauda5% em amostra
  ideal, sem garantia de precisão do p95. Menor suporte exige revisão, não aprovação.
- Sucessos2xx/starts≥99%; falhas HTTP+transporte+cliente/starts≤1%; incompletas=0;
  outras respostas abaixo de400 fora de2xx=0, pois o serviço esperado responde200.
- Vazão de sucessos2xx terminados em MEASURE dividida por4b≥0,8; critério auxiliar,
  distinto de sucesso por coorte. Conferir travessias de fronteira, que deslocam
  términos entre fases.
- p95 das durações2xx da coorte≤`max(250ms,3×p95_ref)`. No primeiro nível usar
 250ms; depois fixar `p95_ref=max(p95 das duas réplicas L01 aceitas)` e mantê-lo
  nos níveis maiores. 250ms é margem exploratória sobre a ordem de dezenas de ms
  do ensaio técnico, não SLO ou prazo total derivado do timeout.
- Comparando primeira/última coortes de30s: se vazão2xx cair≥20% **e** p95 dobrar,
  com n≥50 sucessos em ambas, parar por possível acúmulo/não estacionariedade.
  Suporte menor ou padrão irregular exige revisão, sem concluir estabilidade
  somente porque o corte não foi atingido.

**p95 baixa com falhas não aprova o nível.** Chamadas lentas podem falhar antes
de entrar na distribuição2xx. Interpretar n, falhas, incompletas, outras respostas,
média/p50/p95 e vazão conjuntamente. Não substituir timeout por duração2s nem
inventar fim para incompletas. Frações por starts em coortes abertas são parciais
e não liberam progressão.

Falhas HTTP/transporte reais ou latência alta podem ocorrer em um run tecnicamente
íntegro: são evidências de degradação, **não razões automáticas de exclusão**.
`run_status=incomplete` requer examinar a causa: drenagem esgotada sob sobrecarga
não prova corrupção, mas impede certificar coorte completa. Preservar observações
parciais e sua limitação, interrompendo progressão.

### Integridade/coleta e decisão

Conferir: configuração efetiva/IDs, quatro origens benignas, journals completos e
sequenciais, CSV reconciliado com begin/finish, quatro source_closed, identidade
fixa de vítima/proxy, captura sem queda/drops, cleanup sem erro e Stage9
`dataset_valid/analysis_eligible`. Preservar e interpretar warnings. Não criar
uma exclusão por desempenho do serviço. Ausência/truncamento/incompatibilidade de
artefatos ou captura sem suporte causa STOP/revisão técnica, sem fabricar dados.

Inspecionar suporte de recursos em≥90% dos ticks úteis das vítimas e≥90% das
tentativas de cada fonte do proxy, sem lacuna inexplicada>5s. São critérios novos
de adequação da exploração: insuficiência pausa a progressão e limita a análise
de recursos, sem apagar serviço íntegro. Nomes presentes não provam frescor da
CPU; valores repetidos não provam stale. Null/erro/stale do proxy são explícitos.
Consultas monitoring interferem nos contadores NGINX, que não substituem starts
do cliente. O código lê journals crescentes a cada tick: overhead de instrumentação
faz parte deste arranjo e pode contribuir para limitação em taxas maiores.

**Autorizar nível seguinte somente após:** duas réplicas com coortes fechadas,
critérios satisfeitos, coleta suficiente, tendências e recursos revisados, sem
problema não explicado e recuperação registrada. Qualquer falha causa STOP/revisão,
mesmo que a média do par pareça boa. No teto, parar; sem degradação até ele, relatar
apenas esse resultado condicionado ao arranjo, não “capacidade máxima=64RPS”.

## 4. Integração com o resumo e observação efetiva

[experiments/development_d1.py](../experiments/development_d1.py) possui somente
`validate-plan` e `summarize`; não tem comando para executar tráfego. Valida JSONs
completos via `ExperimentConfig`, hashes, seeds, ordem e saídas. Não importa
orquestrador/Docker e não chama detector, calibração ou TEST.

Após coleta, confere configuração/status/inventário e journals das quatro origens
contra `request_log.csv`. Resolve:
`observation_end=max(source_closed.payload.elapsed_seconds das quatro origens)`.
Gera `phases.json` e `service_summary.json`, com hashes dos journals, fechamentos,
starts por origem, starts tardios e quatro coortes de30s. Inspeção Stage9/proxy/CPU
e decisão permanecem manuais; o campo `technical_status_complete` descreve apenas
os checks de lifecycle/status implementados, não certifica todas essas inspeções.

Fim150 é nominal; tarefas podem iniciar depois. DRAIN `[150,observation_end)` é
acompanhamento observado, não fim exato da emissão ou recuperação. `source_closed`
é posterior a drain/finalização local, anterior a todo cleanup host. O maior
término HTTP pode antecedê-lo e não define o limite de observação. Sem algum
source_closed, o helper recusa inventar um fim; preservar arquivos e revisar,
sem completar para185s. Se o run fechar antes150, exposição é limitada ao corte
real e aderência por fonte fica null. Sem cauda positiva, não há DRAIN de largura
zero. Términos exatamente no limite final usam o bucket já definido no resumo,
sem epsilon. Classes, relógios e denominadores seguem o contrato existente.

Salvar revisão no caminho `outputs.review` de cada entrada: identidade/hash dos
arquivos, métricas/denominadores, p95_ref, verificações de coleta/recursos,
motivos de STOP/continuação, instantes observados de cleanup/pausa/início e
entrada seguinte permitida. Esses registros não são preenchidos antecipadamente.

## 5. Comandos exatos para o primeiro patamar

Executar somente após decisão de iniciar, a partir da raiz, com venv/dependências,
imagens, socket e captura preparados. Nesta tarefa não foi verificada sua prontidão
por Docker nem feito build. Repetir o check offline antes do primeiro run:

```bash
.venv/bin/python -B -m experiments.development_d1 validate-plan --manifest experiments/protocols/development_d1_20261027/manifest.json
```

Iniciar **somente L01/A**,1 RPS por cliente:

```bash
.venv/bin/python -B -m experiments.dataset_run --config experiments/configs/development_d1_20261027/d1_L01_A.json --output experiment_results/development-d1-20261027/raw/d1_L01_A --dataset-output experiment_results/development-d1-20261027/dataset/d1_L01_A
```

Após término, em comandos offline separados; preservar inclusive saídas incompletas.
Stage9 pode retornar erro, que exige revisão, não apagar/reexecutar o run:

```bash
.venv/bin/python -B -m experiments.validate_dataset experiment_results/development-d1-20261027/dataset/d1_L01_A --output experiment_results/development-d1-20261027/analysis/d1_L01_A-validation.json
.venv/bin/python -B -m experiments.development_d1 summarize --manifest experiments/protocols/development_d1_20261027/manifest.json --entry d1_L01_A --output experiment_results/development-d1-20261027/analysis/d1_L01_A
```

Revisar seção3 e registrar recuperação/review. **Só se A permitir prosseguimento**,
iniciar a segunda réplica do mesmo nível:

```bash
.venv/bin/python -B -m experiments.dataset_run --config experiments/configs/development_d1_20261027/d1_L01_B.json --output experiment_results/development-d1-20261027/raw/d1_L01_B --dataset-output experiment_results/development-d1-20261027/dataset/d1_L01_B
```

Revisar B separadamente; ambas aprovadas permitem fixar p95_ref e considerar
L02/B. Não há loop nem comando que rode todos os níveis. `validate-plan` exige
todas as saídas novas na preparação; depois da primeira coleta colisões são
esperadas e o gate passa a ser revisão por entrada, nunca sobrescrita ou execução
em lote para contornar o check.

## 6. Validação realizada

[offline_validation.json](../experiments/protocols/development_d1_20261027/offline_validation.json):
10/10 JSONs completos e válidos, seeds/ordem/saídas conferidas, zero colisões.
Testes sintéticos demonstram fechamento152,25s apesar do último HTTP em150,2s,
recusa de fim fictício sem source_closed, divergência journal/CSV, resumo por
coorte e run encerrado antes150 com aderência null.

```bash
python3 -B -m unittest tests.test_development_d1 tests.test_service_summary tests.test_experiment_config -q
```

**24 testes, OK**; testes de configuração usam mocks. Sem experimentos, calibração,
TEST ou alteração de artefatos congelados. Sem host adicional, RTT específico,
UDP ou autoscaling. Pendem decisão de iniciar, prontidão do ambiente real e
revisões condicionais. Evidências futuras podem motivar outro plano, sem alterar
retrospectivamente os critérios deste D1.
