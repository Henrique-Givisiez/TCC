# DEVELOPMENT D3_cost — dois blocos pareados

Estado: **preparado offline, não executado**. Nova [autoridade](../experiments/protocols/development_d3_cost_20261028/manifest.json), [quatro configurações completas](../experiments/configs/development_d3_cost_20261028/) e caminhos próprios em `experiment_results/development-d3-cost-20261028`. Nenhum Docker, preflight real, experimento, detector ou calibração foi executado/alterado nesta tarefa. Pilotos/autoridades anteriores permanecem preservados.

## Matriz e constantes

| Ordem | Entrada | Bloco/seed | Endpoint ofensivo |
|---:|---|---|---|
| 1 | `d3_cost_A_medium` | A /11511824618406474759 | `/medium` |
| 2 | `d3_cost_A_expensive` | A /11511824618406474759 | `/expensive` |
| 3 | `d3_cost_B_expensive` | B /1073246794152074529 | `/expensive` |
| 4 | `d3_cost_B_medium` | B /1073246794152074529 | `/medium` |

Sempre um atacante contínuo a8 RPS nominais, quatro clientes legítimos a4 RPS cada em `/medium` (16 agregados), uma vítima, proxy estático e autoscaling off. Só mudam ID, seed do bloco e endpoint ofensivo. Pool2, timeout2 s, workers64 por classe, sources em containers, monitoramento/poll1 s e demais campos são cópia completa de E8-R2. Os parâmetros `work_units`/`sleep_seconds` permanecem inertes nos endpoints reservados.

Seeds novas derivadas de SHA256 `development-d3-cost-20261028-v1:bloco:índice`, primeiros oito bytes big endian, com rejeição de colisões. O [inventário auditado](../experiments/protocols/development_d3_cost_20261028/seed_audit.json) inclui pilotos anteriores e reservas MATRIX_A/B; essas reservas não são consumidas. A mesma seed entre endpoints permite streams aleatórios comuns, **não garante mesmos tempos ou contagens de starts**. Seeds A/B são distintas. A inversão de ordem balanceia precedência, sem eliminar período/deriva ambiental.

E4-R2/E8-R2 são referências exploratórias vinculadas por hash, **não substituem nenhuma das quatro execuções**, não entram em contagens de replicação nem estimativas pareadas. C histórico mantém apenas o papel de referência secundária de serviço já fixado em E8-R2.

## Tempos, critérios e processamento preservados

O objeto `rule`, fases e referências são idênticos aos de E8-R2, verificados offline por igualdade. Warmup0–30 s, PRE30–150, ACTIVE150–270 e POST270–390; nominal390 s, até30 s de drenagem e≥60 s de repouso depois do cleanup. PRE próprio como referência principal; mesmo C histórico aceito, hash-bound, intervalo útil30–390 como referência secundária, com compatibilidade e limitações não contemporâneas explícitas.

Sem mudança de critérios: grade POST fixa recortada pelo fim certificado de emissão;≥95% de exposição;≥200 starts/durações para confirmação; sucesso≥99%, margem1pp, falhas/ausência de sucesso no prazo≤1%; p95≤1,25 das referências; limites fixos de quantidade/idade/crescimento de pendências; duas janelas consecutivas e qualificação terminal separadas. Horizonte b+3, evidência usada, disponibilidade batch após journals completos e publicação permanecem distintos. Não presumir desfecho quando faltar evidência; finalização antecipada exige comprovação. ACTIVE pode apresentar comprometimento válido; POST compatível sem comprometimento prévio não inventa recuperação.

[development_d3_cost.py](../experiments/development_d3_cost.py) seleciona uma entrada e reutiliza o pipeline E8-R2, mantendo o hash do manifesto completo na revisão. Acrescenta apenas identidade de bloco/endpoint/seed e tempo de cleanup para o gate entre entradas. A adaptação é local ao processo serial e restaura os bindings mesmo se houver falha; não edita utilitários/autoridades históricos. Os testes comparam o objeto de serviço com o calculado diretamente pelo pipeline E8-R2 para os mesmos fixtures.

## Gates e orçamento

Preflight e run são comandos de **uma entrada**. A ordem é fixa, inclusive entre A e B. Antes da primeira entrada, exigir prontidão e≥60 s desde cleanup do piloto exploratório vinculado. Depois, cada preflight e run exige:

- todas as revisões anteriores deste manifesto presentes, íntegras e vinculadas ao ID/config/bloco/seed corretos;
- seleção explícita do SHA256 da revisão imediatamente anterior, em ambos os comandos;
- integridade técnica, dataset válido/elegível, fechamento controlado, saída0, cleanup verificado, compatibilidade das referências e duas últimas janelas POST qualificadas;
-≥60 s de repouso desde o cleanup anterior e prontidão nova.

Comprometimento de serviço em ACTIVE não reprova a coleta nem impede progressão por si só. Falha técnica, suporte/comparabilidade insuficientes, ausência de qualificação terminal ou encerramento não controlado bloqueiam o próximo run para diagnóstico. Não excluir/repetir automaticamente um endpoint para melhorar o contraste. A falta de agenda independente do gerador limita conclusões sobre carga programada, sem invalidar por si só o serviço observado. Não há comando de execução em lote.

Máximo **quatro tentativas, zero retries/substituições**. Preserva-se o envelope operacional de18 min por entrada (390 s nominal +30 s drenagem +60 s repouso +600 s administrativos). Total:1560 s nominal +120 s drenagem +240 s repouso +2400 s administrativos =**4320 s, 72 min**. Reserva inclui repouso após a última tentativa. Cada entrada consome uma tentativa ao criar `attempt.json`; falhas são preservadas. Preflights adicionais não reiniciam a reserva administrativa da entrada. Estouro não autoriza extensão, repetição ou outra condição.

## Comparação planejada

Somente após as quatro revisões, produzir JSON e Markdown novos, sem sobrescrita. Exigir quatro run IDs distintos; um piloto ou cópia não substitui uma observação. Para cada run, registrar:

- serviço legítimo PRE/ACTIVE/POST: starts/RPS,2xx/fração, falhas HTTP/transporte/cliente, incompletas, média/p50/p95, abertas e pendências nas fronteiras; diagnósticos por janela preservados incluem prazo, referência, recuperação e exposição;
- recursos por fase: CPU e memória da vítima/proxy, conexões do proxy, n e limitações de suporte/frescor;
- ataque: starts em ACTIVE, RPS efetivamente iniciados, razão perante960 starts nominais, origem/admissões e limitações da agenda; starts legítimos por fase/origem também ficam explícitos.

Contraste principal em cada bloco: **expensive−medium na mesma seed**, com taxas ofensivas observadas dos dois lados, diferença e razão. Diferenças de starts legítimos também são publicadas. Oferta nominal igual não é prova de oferta realizada igual: não normalizar silenciosamente latência por RPS, não descartar runs por diferença de chegada e não atribuir automaticamente toda diferença ao endpoint. O gerador legítimo não registra agenda independente; taxa iniciada é o observável disponível, não a oferta completa conhecida.

Separadamente, variação **B−A por endpoint**, com `same_seed=false`. Não tratar A/B como pares da mesma seed, não agregar p95 por média como se fosse um percentil combinado e não produzir inferência forte com apenas dois blocos. A inversão de ordem não remove efeitos de período. Pilotos anteriores ficam apenas em referências; `pilot_runs_in_comparison=0`.

## Comandos curtos

Validação offline:

```bash
.venv/bin/python -B -m experiments.development_d3_cost validate-plan
```

Futuro preflight **somente da primeira entrada** (preparado, não executado):

```bash
.venv/bin/python -B -m experiments.development_d3_cost_ops preflight --entry d3_cost_A_medium
```

A execução é ação separada e requer autorização específica, preflight selecionado e ID exato; nenhum destes comandos foi executado para gerar carga nesta tarefa. Após uma tentativa futuramente autorizada:

```bash
.venv/bin/python -B -m experiments.development_d3_cost review --entry d3_cost_A_medium
```

Após ler essa revisão, a próxima prontidão exige seu hash:

```bash
.venv/bin/python -B -m experiments.development_d3_cost_ops preflight --entry d3_cost_A_expensive --reviewed-sha256 SHA_DA_REVISAO_ANTERIOR
```

Repetir a mesma seleção manual na passagem para B_expensive e B_medium, respeitando a ordem; sem loop/batch. Depois das quatro revisões:

```bash
.venv/bin/python -B -m experiments.development_d3_cost compare
```

Saída curta na CLI; detalhes e contrastes completos no JSON. A [validação offline](../experiments/protocols/development_d3_cost_20261028/offline_validation.json) registra fixtures isolados, fluxo completo das quatro entradas, contraste pareado, diferenças de starts, gate manual/terminal/repouso, recusa de sobrescrita e restauração dos adaptadores. Nenhum fixture ocupa outputs operacionais reservados.
