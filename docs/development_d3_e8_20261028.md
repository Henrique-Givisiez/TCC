# D3 — consolidação de E4-R2 e preparação de uma E8-R2

Estado: **preparado offline, não executado**. A [consolidação de E4-R2](../experiment_results/development-d3-minimal-20261028/analysis/d3_minimal_E4_R2-consolidation_20261028.md) e seu JSON são arquivos novos; a revisão e os dados históricos permanecem intactos. O replay offline reproduziu os campos científicos da revisão sem reclassificá-los.

## Resultado e encaminhamento

E4-R2 iniciou443 requisições ofensivas nos120 s ACTIVE: **3,6916667 RPS**, 92,2917% dos4 nominais, com443 admissões/begins/finishes e zero abandonos. Os legítimos tiveram1838/1959/1864 starts em PRE/ACTIVE/POST, 100%2xx e zero falhas/incompletas. CPU média da vítima:19,47%→52,39%→20,66%; proxy:1,95%→2,15%→2,14%. As quatro janelas POST passaram os critérios congelados, inclusive o primeiro recorte pós-emissão e a finalização antecipada comprovada da última coorte. Houve uma pendência transitória na fronteira360 s, concluída em360,019654693 s dentro do prazo363.

`post_compatible_no_prior_impairment` significa que POST foi compatível e ACTIVE não mostrou degradação perante o PRE principal com suporte suficiente. Não afirma ausência de qualquer efeito: a média de duração subiu de29,90 para34,29 ms e a CPU aumentou. Os critérios não foram reprovados; não se inventa evento de recuperação (`recovery_event=null`). Falta de agenda legítima continua limitando a prova de execução integral da carga programada, sem invalidar a observação das iniciadas.

**Recomenda-se um único piloto a8 RPS nominais em `/expensive`, mantendo16 RPS legítimos.** A decisão apoia-se em integridade, fechamento controlado, compatibilidade terminal e observabilidade dos geradores neste patamar, não em extrapolação linear de CPU/capacidade. Atingir8 RPS e observar degradação são perguntas futuras. O contraste com E4-R2 usará outra seed, portanto será exploratório, sem atribuição causal isolada à taxa. Sem calibração de critérios a partir do resultado.

## Autoridade e condições

Nova [autoridade própria](../experiments/protocols/development_d3_e8_20261028/manifest.json), única entrada `d3_pilot_E8_R2`, diretórios novos em `experiment_results/development-d3-e8-20261028`. A única [configuração](../experiments/configs/development_d3_e8_20261028/d3_pilot_E8_R2.json) difere da E4-R2 somente por ID, seed auditada e taxa ofensiva4→8. Permanecem quatro clientes legítimos `/medium`,16 RPS agregados; um atacante contínuo `/expensive`; uma vítima, proxy estático, autoscaling off, sources/pool2/timeout2 s/orçamentos e monitoramento inalterados.

Tempos iguais: warmup0–30, PRE30–150, ACTIVE150–270, POST270–390, nominal390 s; até30 s de drenagem e reserva60 s de repouso. **Uma tentativa, zero retries/substituições; 480 s mais600 s administrativos =18 min.** A prontidão e o start gate de orçamento são os já validados. Antes do futuro preflight, exigir evidência vinculada de E4-R2, cleanup e≥60 s de repouso. Não há batch ou continuação automática.

A revisão de E4-R2 fica vinculada pelo SHA256 **`6edd7f357efd580ee2547eb30b360b7aa7990bae0b1dee38ff21fd390b2f35fd`**, junto de sua autoridade, hashes raw e fontes validadas. O campo histórico `continued_execution_authorized=false` não é alterado nem interpretado como liberação. Esta preparação deriva da instrução atual e exige autorização futura separada para execução. A E8 da autoridade original continua bloqueada; esta é outra entrada.

Seed nova, namespace/índice e auditoria de colisões constam do manifesto e do [inventário auditado](../experiments/protocols/development_d3_e8_20261028/seed_audit.json). Incluem seeds de todos os pilotos anteriores, E4-R2 e reservas futuras MATRIX_A/B, que não são reutilizadas ou alteradas.

## Critérios reutilizados sem ajustes

O objeto `rule`, referências, margens, tempos e orçamento são copiados **sem mudança** da autoridade E4-R2. Referência principal é o PRE da futura E8; secundária é o mesmo C histórico, identificado pelos mesmos hashes, intervalo útil30–390 e limitações não contemporâneas. Nenhuma vazão de bin de C se torna requisito de atendimento.

Mantêm-se: recorte pós-emissão na grade fixa com≥95% de exposição;≥200 starts/durações para confirmação; sucesso≥99%, falhas/ausências de sucesso no prazo≤1%, margem1pp, duração p95≤1,25 das referências; limites congelados de pendências/idade/crescimento; duas janelas consecutivas e qualificação terminal separadas. Horizonte b+3 s, evidência efetivamente usada e publicação permanecem distintos. Coorte não observada/madura não é presumida concluída; fechamento íntegro antecipado é explicitado. Sem degradação demonstrada em ACTIVE, POST pode ser compatível sem evento de recuperação. Validade técnica, serviço recebido e evidência do gerador continuam eixos independentes.

[development_d3_e8.py](../experiments/development_d3_e8.py) reutiliza o pipeline E4-R2 por adaptação local ao processo, restaurando todos os bindings ao terminar/falhar; não modifica arquivos anteriores. O cálculo do serviço é **o mesmo**. A única adaptação descritiva adicional é a expectativa ofensiva de960 starts/120 s em vez de480, obtida da configuração8 RPS; essa expectativa não é prova de agenda integral. [development_d3_e8_ops.py](../experiments/development_d3_e8_ops.py) reutiliza as funções de prontidão/execução, com autoridade/base/ID novos e predecessor explícito. CLI curta; medidas, motivos, referências, limites e tempos completos no JSON.

Validação offline em [offline_validation.json](../experiments/protocols/development_d3_e8_20261028/offline_validation.json): configuração única e diferenças autorizadas, seed disjunta, hashes do predecessor, igualdade da regra e do serviço calculado, denominador ofensivo960, restauração de bindings, recusa de entradas antigas/segunda tentativa, pipeline com fixtures/exportação/dataset/revisão/publicação/CLI e recusa de sobrescrita. Fixtures não ocupam outputs reservados nem são experimentos.

Comandos offline:

```bash
.venv/bin/python -B -m experiments.development_d3_e8 validate-plan
.venv/bin/python -B -m experiments.development_d3_e8 review
```

O segundo só é aplicável futuramente, após coleta/exportação autorizadas. Para iniciar **somente o preflight**, futuramente:

```bash
.venv/bin/python -B -m experiments.development_d3_e8_ops preflight --entry d3_pilot_E8_R2
```

Esse comando consulta Docker/imagens/porta e captura de prontidão, sem carga HTTP. Foi preparado, **não executado**, nesta tarefa. Nenhum experimento, Docker, detector ou calibração foi executado/alterado aqui.
