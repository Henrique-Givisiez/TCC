# C1.2-CPU.3 — Piloto legítimo de CPU

## Resultado e identificação

Uma única execução L2 de 120 s, concluída e certificada, fora da campanha.
Branch `refactor/project-organization`, commit `848a8aef0a6809a04995f8217264cf2d1ee20a7b`;
working tree inicialmente limpo. Run `927acd4b21b940aea034ec8182f25150`.
Nenhuma alteração na implementação, tolerância, agenda, detectores ou calibração.
Nenhum experimento ofensivo, repetição, commit ou push.

## Configuração e preflight

Configuração derivada da B2-L, alterando somente ID e duração para 120 s:
direta, uma vítima, dois workers, duas fontes ×8 RPS em `/medium`, timeout2 s,
concorrência legítima64, ataque desabilitado, diagnósticos ON. Publicação operacional
mantida em5 s; aquisição CPU1 s, antecipação25 ms, extração com tolerância50 ms.
Seed20261107 preservada; não é seed de campanha.

Utilizado `experiments.diagnostic_run --composition legitimate`, sem runner científico.
Política `exploratory-offensive-v1` copiada byte a byte da B2-L, aplicável também à
composição legítima: RAM mínima2 GiB, disco4 GiB, vítima1 GiB, fontes512 MiB,
artefatos512 MiB, frescor5 s, timeoutDocker3 s, prazo global240 s. Não interrompe por
degradação HTTP. Cliente independente de CPU usa seu timeout implementado de2 s.

Preflight `raw.attempt/attempt.json`: ready, imagens e arquivos/launchers conferidos,
sem contêineres/processos experimentais residuais, redes vazias, RAM disponível
9.850.228.736 bytes, disco37.196.546.048 bytes. Ambiente detalhado e versões no
dataset `metadata/run_provenance.json` e `metadata/export_provenance.json`.
Imagens imutáveis preservadas:

- Vítima: `sha256:03a186aa90eec03b874c82a887b245e7190fa45cd7256af3c077cb64943d52b0`.
- Fontes: `sha256:b94212edd4d31c34998aea870caebc4ba145c1593d1b8dfdc27fe4917719fe3e`.

Tentativas iniciais de preparar os diretórios foram recusadas pelo sandbox; um
comando de execução falhou na abertura do redirecionamento, antes de iniciar Python.
Depois da preparação autorizada houve somente uma invocação efetiva do simulador.

## Integridade e encerramento

Processo exit0; run completed, erros[], fontes drenadas e observação da vítima completa.
Certificado: cleanup_verified=true, progression_allowed=true, failures[]. Encerramento
de sources, capturas, coletor e vítima confirmado. O encerramento bem-sucedido do
coletor verifica ausência de thread remanescente. Consulta Docker posterior sem
contêineres ativos; verificação pós-limpeza da política confirmou ausência de resíduos.
Ambas capturas:10.430 pacotes, zero descartes kernel, fechamento aceito.
Dataset válido/elegível para análise estrutural; isso não é elegibilidade científica.

Exportação realizada pelo procedimento existente. Extração offline com
`--cpu-boundary-tolerance-seconds 0.05`: schema2,121 janelas. Replay dos contadores
e hashes foi executado pelo validador/extrator, sem fallback ao CSV operacional.
Arquivos brutos/exportados/features têm hashes registrados em `hashes.json`.

## Aquisição e alinhamento

| Medida | Resultado |
|---|---:|
| Tentativas / snapshots / snapshots novos |120 /120 /120|
| Deltas válidos / primeira leitura |119 /1|
| Oportunidades perdidas / erros / resets / timestamps inválidos |0 /0 /0 /0|
| Duração chamada: média / mediana / p95 / máximo |8,488 /8,155 /11,003 /20,856 ms|
| Chamadas até25 ms / acima25 ms |120 /0|
| Intervalos daemon: mínimo / média / mediana / p95 / máximo |0,995842 /1,000012 /1,000025 /1,002216 /1,005210 s|
| Atraso de agenda: média / mediana / p95 / máximo |0,259 /0,260 /0,382 /0,447 ms|

A duração registrada inclui inspeção de identidade e aquisição one-shot, não somente
tempo interno da API stats. Agenda, começo/fim, recebimento e read estão no JSONL.
Os119 pares passaram pelos brackets completos próximos das fronteiras e receberam
dados até o fechamento. Rejeições: somente first_read=1. Zero por desalinhamento,
recebimento tardio, intervalo longo, repetição/regressão, contador inválido ou reset.
`alignment.json` verifica independentemente esses predicados, sem alterar a política.

A antecipação25 ms foi compatível nesta execução: mesmo a maior duração de chamada
mais o maior atraso observado ficou abaixo desse orçamento. Não há evidência de
pressão de latência da API nem de agenda que explique perdas aqui. Isso não garante
o comportamento sob A3/F96 ou por390 s. Os intervalos continuam aproximadamente
alinhados, não integrais exatas dos segundos nominais.

## Cobertura e valores

| Intervalo | Janelas | Válidas | Ausentes | Cobertura | Z/EWMA/freeze potencial | CoV potencial |
|---|---:|---:|---:|---:|---:|---:|
| Grade completa |121|119|2|98,35%|119 (98,35%)|114 (94,21%)|
| Nominal `[0,120)` |120|119|1|99,17%|119 (99,17%)|114 (95,00%)|
| Referência `[30,120)` |90|90|0|100%|90 (100%)|90 (100%)|

Ausências: janelas0 e120 da grade; duas sequências isoladas de comprimento1, máximo1.
No nominal, só a janela0; no intervalo estabilizado, nenhuma. A primeira leitura
serve de referência e não produz delta para janela0. A janela120 é cauda da grade
por observações de serviço após120 s, sem par CPU correspondente. Não é rejeição por
latência. A extração não fabrica amostras para essas posições.

CoV precisa de seis valores consecutivos e perde também cinco posições de aquecimento.
Os números são suporte potencial, não execução/calibração dos detectores. Média zero,
baseline ou política inelegível poderiam reduzi-los em outra execução.
O indicador histórico95% é atingido no nominal e no estabilizado; na grade completa
o potencialCoV fica abaixo95% por bordas/aquecimento. Não se declara elegibilidade
definitiva por um piloto de120 s; `[30,120)` não é a fasePRE completa da campanha.

CPU válida:119 valores; mínimo23,091%, média62,565%, mediana62,548%, p95 85,877%,
máximo106,119%. Dois valores acima100%, zero valores iguais a zero. A escala é Docker,
100%≈um núcleo lógico, não percentual da capacidade do host. Não houve inconsistência
de contadores. A figura `cpu.png` apresenta pontos e ausências explícitas, sem
interpolação; marcadores de ausência na base não representam CPU zero. Há flutuação
observada de carga durante o período; não se atribui causa a cada oscilação.

## Impacto operacional

Em `[0,120)`:1.893 inícios legítimos,15,775 RPS observados versus16 nominais;
1.893 respostas2xx, nenhuma falha HTTP/transporte na coorte. Durações: média51,522 ms,
mediana42,696 ms, p95 85,213 ms, máximo126,794 ms. Conclusões seguem as requisições
originais mesmo se posteriores ao limite da coorte.
Ticks operacionais: gaps médios4,999 s, mediana5,005 s, p95 5,039 s, máximo5,051 s.
São publicação configurada em5 s; aquisições CPU são independentes e próximas de1 s.
Não se observou o padrão anterior de6–10 s. Sem erros de persistência, thread fatal,
OOM, reinício ou acionamento operacional reportado. O atendimento permaneceu funcional.
Isso não prova ausência de overhead: não houve comparação controlada sem instrumentação.
Mudanças de cadência são compatíveis com remoção das esperas antigas, sem repartir
causalmente seu efeito entre StatsCollector, Operations e condições do host.

## Respostas e recomendação

1. **Q1:** neste piloto, sim: aquisições≈1 s, chamadas≤20,856 ms e ticks≈5 s; não há
   garantia universal nem validação ofensiva.
2. **Q2:**99,17% no nominal;100% em30–120 s;98,35% na grade de121 janelas.
3. **Q3:** bordas: falta de delta inicial e janela adicional da cauda, sem perdas internas.
4. **Q4:**50 ms foi sustentável aqui, com todos os119 pares válidos alinhados.
5. **Q5:**não nesta execução: zero rejeições por recebimento após fechamento.
6. **Q6:**sim, há evidência técnica para manter CPU como candidata; não há aprovação
   definitiva de elegibilidade nem evidência de robustez sob os cenários ofensivos.
7. **Q7:**nenhum impedimento operacional novo neste piloto. As incompatibilidades de
   protocolo/runner já auditadas e a validação integrada de390 s continuam pendentes.

Recomenda-se revisão metodológica destes resultados e decisão sobre congelamento
da tolerância/disponibilidade antes da validação integrada posterior. Não há motivo
observado para aumentar tolerância, antecipação ou mudar a política nesta etapa.
Nenhum ajuste foi implementado. Não iniciar automaticamente campanha nem repetir.

## Artefatos

Raiz `experiment_results/c1-2-cpu3-20261108/`: `config.json`, `policy.json`,
`execution.log`, `raw.attempt/attempt.json`, `raw/`, `dataset/`, `features/`.
Em `raw/`: `cpu_observation_contract.json`, `victim_stats.jsonl`,
`victim_stats.summary.json`, `run_status.json`, `operational_policy.json`,
`dataset_validation.json`; em `features/`: `cpu_quality.json`, `feature_manifest.json`,
`timeseries/infrastructure.csv`. O dataset contém cópias indexadas por hash.
Neste diretório: `analyze.py`, `summary.json`, `alignment.json`, `hashes.json`, `cpu.png`.
Dados brutos/volumosos não foram adicionados ao Git.
