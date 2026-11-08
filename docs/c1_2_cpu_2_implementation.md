# C1.2-CPU.2 — CPU da vítima: implementação e testes determinísticos

## Escopo e estado inicial

Branch `refactor/project-organization`; HEAD anterior `43940b409204fe7a8fcffbf2d145d5bb103d3d7b`.
Working tree inicialmente limpo. Nenhuma mudança posterior à auditoria CPU.1 estava
presente no checkout. Foram reutilizados `cpu_accounting_audit.md`,
`proxy_observability.md`, a fórmula Docker e os conceitos do ProxyMonitor.

L2, A3, F96, vítima de dois workers, topologia direta, 390 s + 30 s de drenagem e
80 execuções (4/8/8/60, 20 blocos TEST) são premissas aprovadas e não foram alteradas.
O contrato antigo da campanha e sua política de bloqueio por calibração continuam
preservados; sua adaptação é outra atividade. Não houve Docker real, tráfego,
piloto, coleta, calibração, alteração de detector, commit de dados ou push.

## Problema original

`stats(stream=False)` sem one-shot obtinha frames implícitos; o coletor aguardava
o retorno e depois mais um intervalo. Cache sem expiração podia ser publicado
repetidamente. O CSV arredondava/agregava CPU por tick, e a extração atribuía sua
média ao segundo do tick. Isso não certificava aquisição nova nem intervalo de 1 s.
`Operations.observe()` também fazia consultas de stats sequenciais bloqueantes.

## Implementação e interfaces

| Arquivo | Responsabilidade |
|---|---|
| `simulator/cpu_observations.py` (novo) | Parser RFC3339 com frações, deltas puros e agenda sem backlog. |
| `simulator/stats_collector.py` | Snapshots one-shot, referência por vítima/geração, evidência, erros, cliente dedicado e encerramento. |
| `simulator/source_experiment.py` | `bind_cpu(run_id, clock, path)` antes de iniciar; declaração do contrato no status. |
| `simulator/exploratory_operations.py` | One-shot para memória; falha explícita se memória indisponível; preserva identidade, estado, OOM, reinícios e limites. |
| `experiments/stress_runtime.py`, `scientific_collection.py` | Hook `_on_acquisition(container, stats, received_monotonic)` em lugar de interceptar cálculo de métricas. |
| `experiments/cpu_features.py` (novo) | Replay da evidência, atribuição conservadora e diagnósticos. |
| `experiments/validate_dataset.py` | Verifica evidência declarada e hashes, sem criar gate de cobertura. |
| `experiments/extract_features.py`, `feature_schema.py` | CPU prospectiva por evidência; schema de features 2. |
| `analysis/detection/scientific/data.py` | Reconhece schemas 1/2 e reconstitui CPU/qualidade dos inputs vinculados. |
| `analysis/detection/scientific/engine.py` | Recusa mistura de versões entre fontes e baseline/calibração/avaliação. Critérios numéricos inalterados. |
| `analysis/detection/cusum_freeze_run.py` | Validador de entrada reconhece schema 2; nenhuma transição/decisão foi alterada. |
| `tests/test_cpu_observations.py` (novo) | Testes de contadores, tempo, thread, proteção, exportação, extração e loaders. |
| `tests/test_cpu_accounting_audit.py` | Mantém verificações históricas dos helpers e atualiza três expectativas do coletor ativo corrigido. |
| `tests/test_experiment_config.py` | Corrige somente assinatura de fake `submit`, aceitando kwargs já enviados pelo gerador (`admission_id`). Não altera gerador. |

`get_snapshot()`, `get_averages()`, cache/histórico operacional, cálculo de memória,
CSV operacional e custo continuam disponíveis. CPU inválida no snapshot é `None`;
a média operacional ignora esses valores. Seu fallback operacional não é utilizado
pela CPU científica. `_calc_cpu_percent()` permanece como helper histórico para
testes de auditoria, sem uso na aquisição ativa. Memória mantém a convenção histórica
`max(usage-cache,0)/1024²`; sua cadência passa a acompanhar as novas aquisições.

Os adaptadores de frescor recebem apenas timestamps Docker novos e válidos, com o
monotônico real de recebimento. Uma linha de erro persistida não renova aquisição.
`Operations.observe()` continua verificando persistência e idade da última aquisição.
Não se mudou `SampleFreshness`, a regra de degradação, nem o observador científico.

No caminho de fontes em contêineres, o coletor usa cliente Docker próprio, timeout
de 2 s e agenda ancorada no relógio experimental. A chamada é programada 25 ms antes
da próxima fronteira; isso é uma escolha técnica para testar disponibilidade até
o fechamento, não uma garantia de precisão. O intervalo configurado continua
explícito no marker; as configurações da campanha não foram editadas.
Slots perdidos não geram chamadas retroativas: aparecem no resumo e na tentativa
seguinte. `stop()` exige thread terminada e ausência de falha fatal; seu prazo
padrão reserva duas operações com timeout e margem. Não promete interromper uma
operação remota travada no daemon. Encerramento não confirmado gera erro.

## Contrato científico prospectivo

### Fórmula e unidade

Para snapshots consecutivos válidos da mesma execução:

```
U = cpu_stats.cpu_usage.total_usage      # ns, Docker
S = cpu_stats.system_cpu_usage          # ns, sistema
n = cpu_stats.online_cpus               # ou tamanho do percpu_usage disponível
CPU% = 100 * (U_atual-U_anterior)/(S_atual-S_anterior) * n
```

Não se usa `precpu_stats` implícito. Não se converte novamente ns para us.
`n` é multiplicador da convenção Docker, não divisor de normalização da capacidade
do host. 100% ≈ um núcleo lógico; 200% não é teto do pool; não há clipping.
Sem suporte para `n`, o novo contrato não assume uma CPU. Mudança de `n` invalida
o delta e estabelece nova referência. A fórmula conserva a escala histórica;
é uma razão de contadores do intervalo, não CPU instantânea.

Fundamentação reutilizada: [Docker SDK, stats](https://docker-py.readthedocs.io/en/stable/api.html#docker.api.container.ContainerApiMixin.stats),
[Moby 28.0.4, ContainerStats](https://raw.githubusercontent.com/moby/moby/v28.0.4/daemon/stats.go),
[Docker CLI 28.0.4, fórmula Linux](https://raw.githubusercontent.com/docker/cli/v28.0.4/cli/command/container/stats_helpers.go).
São fundamentos da interface/convenção; não constituem medição do Engine atual.
A disponibilidade efetiva dos campos será conferida na CPU.3.

Primeira leitura, contador ausente/reset, timestamp inválido e troca de geração
produzem CPU ausente. Delta de CPU zero com sistema/tempo avançando produz zero
válido. Timestamp repetido/regressivo não renova referência/frescor. Falha de API
preserva referência válida, salvo perda de identidade; a recuperação pode produzir
um intervalo longo real. Reset/contador inválido reestabelecem referência conforme
o estado registrado. Um intervalo longo nunca é dividido em vários segundos.

### Artefatos e proveniência

Contrato de aquisição `victim-cpu-snapshots-v1`, schema de evidência 1:

- `cpu_observation_contract.json`: run, vítima, âncoras monotônica/epoch, intervalo,
  antecipação da agenda e nomes dos artefatos.
- `victim_stats.jsonl`: uma linha por tentativa, sequência, geração (`StartedAt`,
  `RestartCount`), agenda, início/fim/recebimento, timestamps epoch, `read`, contadores,
  erro, estado, frescor, referência e limites do intervalo. Conserva `monotonic` e
  `cpu_stats` para inspeção bruta; não alega o schema antigo do JSONL.
- `victim_stats.summary.json`: tentativas, snapshots, oportunidades perdidas,
  conclusão do worker e falha fatal.

Arquivos são criados sem sobrescrita. Cada linha é descarregada e recebe fsync;
isso tem custo a medir. Falha de escrita/fechamento é fatal. Truncamento, duplicação
de sequência, referência/CPU derivada adulterada e resumo incompatível são recusados.
SIGKILL não possui garantia de finalização: resumo ausente impede aceitação.

A exportação recursiva existente os copia para `evidence/other/`, com bytes e hashes
no manifesto. Não foi necessário modificar `export_dataset.py` nem schema Stage8.
O validador verifica o novo contrato somente quando declarado/presente. Baixa
cobertura isolada não invalida o dataset e não exclui execuções ofensivas.
`cpu_features.py` e `cpu_observations.py` entram na proveniência do runtime e nas
dependências vinculadas do validador.

Feature schema 1 conserva o significado histórico dos ticks; schema 2 altera
explicitamente somente a origem/semântica da CPU, preservando as outras colunas.
Dados históricos não são reescritos. Status/marker/primeira linha versionada impedem
fallback silencioso para CPU histórica quando faltam evidências novas. Loaders
históricos que suportam apenas schema 1 continuam recusando schema 2.

### Tempo, incerteza, atribuição e disponibilidade

`read` é tempo do daemon; início/fim e recebimento são tempos do host. A aceitação
exige `read` dentro do bracket epoch da chamada e cronologia monotônica válida.
Não se trata o recebimento como instante de medição. Para cada extremidade do
delta, preserva-se todo o bracket monotônico da aquisição, como incerteza temporal
conservadora. Isso não prova atomicidade da contabilidade interna do kernel/daemon.

Para uma janela nominal `[k,k+1)`, exige-se:

1. Bracket inteiro da leitura anterior dentro de `k ± tolerância`.
2. Bracket inteiro da leitura atual dentro de `(k+1) ± tolerância`.
3. Recebimento atual até `k+1`, inclusive.
4. Uma única medição candidata: ambiguidades são recusadas, sem escolher a melhor.

A candidata é associada pelo limite inicial aproximadamente alinhado, nunca pelo
recebimento. O delta completo é usado uma única vez, sem rateio, interpolação,
repetição, média sobre cache ou preenchimento por zero. O valor descreve um intervalo
aproximado, não a integral exata de CPU no segundo nominal. Nem mesmo 50 ms limita
o erro de amplitude a 5%; bursts junto à fronteira podem produzir diferenças maiores.

Parâmetro `cpu_boundary_tolerance_seconds`, CLI `--cpu-boundary-tolerance-seconds`,
default experimental `0.05`; intervalo permitido `[0,0.5)`. Seu valor é gravado no
manifesto e em `cpu_quality.json`, com `provisional=true`. Não há ajuste automático.
**Tolerância de 50 ms e política de disponibilidade permanecem provisórias para
aprovação metodológica antes do freeze.** A implementação aplica conservadoramente
recebimento até fechamento; leituras tardias permanecem evidência, mas não alimentam
a janela. Não se modificou a semântica temporal dos detectores.

## Diagnósticos e elegibilidade

`cpu_quality.json`, vinculado por hash no manifesto de features, publica tentativas,
snapshots novos, deltas, falhas/categorias, intervalos, atrasos, oportunidades perdidas,
atribuições/rejeições, janelas ausentes, sequências de ausência e cobertura por
WARMUP/PRE/ATTACK/POST. Cobertura de aquisição usa snapshots realmente novos sobre
tentativas mais oportunidades perdidas. Duplicatas não contam como aquisição nova.

Disponibilidade potencial é um limite superior sem baseline/limiar: Z/EWMA/freeze
dependem do valor presente; CoV exige seis valores consecutivos, inclusive histórico
anterior à fase. Média CoV zero e rejeição de calibração ainda podem reduzir esse
suporte. Null continua reiniciando estados conforme o algoritmo existente.
Os gates históricos (95%, 342/360, FPR etc.) não foram alterados. Diagnóstico por
fase não cria gate por fase, nem faz exclusão global do TEST por ausência de CPU.

## Testes e resultados

Somente fixtures temporárias, relógios controlados, snapshots sintéticos e clientes
Docker mocks. Há teste de start/stop de thread real sem IDs e com cliente falso;
não se inicia contêiner. Mensagens históricas de build/start produzidas pelos testes
referem-se a MagicMock, não a operações Docker reais.

Execuções intermediárias:

- Primeiros 17 testes novos: três diferenças de representação Decimal (`100.00`
  versus `100`) foram corrigidas nas expectativas, sem arredondar a CPU.
- Primeira regressão de 261 testes: três expectativas antigas do coletor e uma
  fixture de kwargs desatualizada falharam; foram atualizadas conforme descrito.
- Regressão de 277 testes, incluindo `test_scientific_campaign`: OK.
- Regressão ampliada sem a campanha: 268 testes, OK.
- Após remover todo uso ativo de precpu e ajustar encerramento: 38 testes focados,
  OK. A execução final abaixo incorpora todas as mudanças.

Comando da regressão final: `.venv/bin/python -B /tmp/cpu2_run_tests.py`.
Esse runner temporário carrega os módulos abaixo com bloqueio explícito de conexões
reais, negociação real de Engine e execução de CLI Docker/curl/wget/tcpdump.
Ele só permite testes locais; seu log está em `/tmp/cpu2-tests-final.log`.

```
tests.test_cpu_observations tests.test_cpu_accounting_audit
tests.test_feature_extraction tests.test_dataset_export tests.test_dataset_validation
tests.test_exploratory_operations tests.test_stress_pilot tests.test_experiment_config
tests.test_source_containers tests.test_single_victim tests.test_proxy_monitor
tests.test_cusum_freeze tests.test_scientific_campaign
```

Resultado final: **284 testes aprovados em 253,679 s**, sem falhas ou erros,
com bloqueio de acesso real a Docker/rede ativo. Log: `/tmp/cpu2-tests-final.log`.
Depois foi acrescentado somente um teste de chamada lenta/slots perdidos;
`.venv/bin/python -B -m unittest tests.test_cpu_observations -q` aprovou os **25
testes novos em 1,301 s**, incluindo esse caso adicional. Assim, 285 testes distintos
foram verificados; os testes de CPU se sobrepõem à regressão. Nenhuma falha permanece.
`git diff --check` também passou. Nenhum teste foi pulado dentro dos módulos listados.

Para reprodução, esses mesmos módulos podem ser passados a
`.venv/bin/python -B -m unittest ... -v`; todos os acessos externos desses testes
são mocks. O runner com bloqueio acrescenta uma verificação defensiva durante esta
entrega. Os testes incluem exportação/hashes, alteração independente de CPU sem
alterar rede/serviço/labels/memória, leitura tardia, delta longo, duplicação, versão
desconhecida, corrupção, replay no loader científico e os quatro métodos.
Não foram executados smokes, scripts de integração reais, Docker, piloto legítimo
de 120 s ou validação ofensiva de 390 s: pertencem a etapas autorizadas separadamente.

## Riscos e próxima decisão

Esforço da correção: médio. Não se demonstrou empiricamente resolução dos gaps de
6–10 s. One-shot remove o mecanismo de espera identificado, mas latência da API,
fsync, inspeções, journals e scheduler continuam existindo. Um timestamp novo também
não comprova atualização atômica dos contadores internos do daemon.

O bracket estrito e recebimento até fechamento podem reduzir fortemente cobertura;
isso deve aparecer como null, nunca motivar relaxamento automático. A geração
usa inspeção do contêiner antes do snapshot; existe uma corrida residual entre
inspeção e reinício. As verificações existentes e detecção de regressão continuam
ativas, sem alegação de monitoramento atômico de reinícios.

O contrato prospectivo cobre a vítima única no caminho de fontes em contêineres.
O ramo host legado continua operacional, sem ser promovido a nova autoridade
científica. A compatibilidade temporal deve ser avaliada no caminho exato da CPU.3.

**Recomendação:** após revisão desta implementação e das duas políticas provisórias,
é tecnicamente viável autorizar C1.2-CPU.3 para medir cadência, alinhamento, cobertura,
falhas e impacto com legítimos. Não há autorização implícita para executá-la aqui.
Se os limites não forem sustentados, declarar CPU não avaliável nessa resolução ou
submeter nova decisão metodológica; não fabricar suporte e não abrir automaticamente
uma implementação de cgroup direto. A campanha e os gates aprovados permanecem
fora desta validação determinística.
