# Diagnóstico offline da memória bruta do proxy — clock r2

Escopo restrito às quatro verificações solicitadas: valores/saltos; monitoramento; conexões/atendimento; composição salva. 36 execuções TEST, fontes vinculadas por hash. Nenhum Docker, experimento, coleta ou detector foi executado.

## 1. Observações confirmadas: distribuição e saltos

Não foi escolhido limiar alto/baixo. Usam-se distribuições completas e quantis com posições fixas, diferenças assinadas/absolutas e contagens de sinal. A tabela informa a mediana entre 12 resumos por execução; quantis de cada run são descritivos, não ICs nem percentis de uma mistura dos 12 runs.

| Cenário/fase | Média (MiB) | q10 | Mediana | q75 | q90 | q90 de abs(Δmemória) (MiB) |
|---|---:|---:|---:|---:|---:|---:|
| C16/PRE | 9,237 | 6,513 | 9,792 | 10,109 | 10,370 | 3,630 |
| C16/ACTIVE | 8,815 | 6,714 | 9,061 | 10,519 | 10,822 | 3,968 |
| C16/POST | 8,622 | 7,070 | 7,742 | 10,919 | 11,398 | 3,882 |
| M16/PRE | 9,232 | 6,546 | 9,810 | 10,103 | 10,344 | 3,627 |
| M16/ACTIVE | 8,225 | 6,736 | 7,522 | 10,035 | 10,746 | 3,843 |
| M16/POST | 8,126 | 7,572 | 8,039 | 8,286 | 8,547 | 0,765 |
| E16/PRE | 9,264 | 6,507 | 9,813 | 10,109 | 10,391 | 3,714 |
| E16/ACTIVE | 7,665 | 6,659 | 7,409 | 7,988 | 8,742 | 3,314 |
| E16/POST | 8,112 | 7,376 | 7,935 | 8,193 | 8,497 | 2,886 |

Em ACTIVE, diferença E16−C16 pareada por bloco: mediana das diferenças das médias = -1,091 MiB; q10 = -0,058; mediana = -1,565; q90 = -2,076 MiB. A queda da média descreve uma redistribuição das leituras, sobretudo afastamento da parte superior; não demonstra queda equivalente da memória do worker.

Os picos não desaparecem: máximo observado em E16/ACTIVE=12,691 MiB, em C16/ACTIVE=11,598 MiB. A queda da média não é uma queda uniforme de toda a distribuição.

Todas as leituras de memória estão em múltiplos de 4096 bytes; isso é compatível com quantização em páginas de 4 KiB, mas não identifica o componente que ganhou/perdeu páginas. Valores repetidos, GCD dos incrementos, sinais, amplitude e variação total estão por run/fase no CSV. As oscilações já ocorrem em C16/PRE; não dependem de emissão ofensiva.

Para distinguir passagem do tempo de emissão, o CSV de janelas fixas usa todos os intervalos consecutivos de 30 s, sem realinhar ataques. Em particular, [150,180) tem a mesma idade experimental nos três cenários; a comparação integral ACTIVE também é preservada, com duração variável E16.

| Cenário | Média em [120,150), mediana entre runs | Média em [150,180), mediana entre runs |
|---|---:|---:|
| C16 | 9,303 | 9,397 |
| M16 | 9,166 | 9,020 |
| E16 | 9,295 | 7,724 |

Essa comparação torna insuficiente uma explicação baseada apenas na idade da execução: o deslocamento E16 já aparece no intervalo inicial de ACTIVE. Ao mesmo tempo, tendências e oscilações em C16 e POST mostram que não se deve atribuir toda mudança à emissão. Não é uma estimativa causal.

## 2. Associações com o monitoramento

O código confirma status por `exec_run(wget)` → retorno/exit_code/parsing → `stats(one_shot=True)`. Em sucesso normal, o comando bloqueante retornou antes da chamada Docker. As falhas existentes são de parsing, não evidência de timeout de wget em execução. Não há timestamp dedicado de término de cada processo ou liberação do cgroup.

| Cenário/fase | Variável | Mediana ρ em níveis | Mediana ρ em diferenças | Runs com ρ(Δ) negativo / definido |
|---|---|---:|---:|---:|
| C16/PRE | status_duration_ms | -0,247 | -0,379 | 12/12 |
| C16/PRE | docker_duration_ms | -0,162 | -0,232 | 12/12 |
| C16/ACTIVE | status_duration_ms | -0,455 | -0,402 | 12/12 |
| C16/ACTIVE | docker_duration_ms | -0,502 | -0,369 | 12/12 |
| E16/ACTIVE | status_duration_ms | 0,034 | -0,264 | 12/12 |
| E16/ACTIVE | docker_duration_ms | 0,020 | -0,230 | 12/12 |

Há associação repetida entre a variação de memória e a duração das operações de observação, inclusive em controle/PRE. Ela é compatível com sensibilidade ao momento de amostragem, contabilização/liberação de memória transitória ou atividade auxiliar; não identifica wget como causa. Consultas status/Docker, runtime e NGINX podem responder à carga compartilhada. Diferenças consecutivas reduzem a contribuição de tendência lenta, mas não removem confundimento, autocorrelação ou seleção temporal.

Slots pulados registrados pela diferença de scheduled_elapsed_seconds: 0. Logs HTTP de monitoring pareados univocamente: 14094; sem candidato=0, ambíguos=0, reutilizados=0. Cadência, atraso e duração estão preservados por leitura; nenhum slot ausente foi preenchido.

A distância entre começo Docker e fim estimado de status pode ser ligeiramente negativa: `started` antecede `clock.sample()` e a duração inclui esse intervalo. Logo, começo+duration não é um fim exato; diferenças de microssegundos não provam sobreposição ou inversão da ordem. `docker_read` é preservado separadamente; o fim HTTP do log de monitoring também não é o fim do processo wget.

Gaps estimados negativos: 31 de 14094, faixa global -17,524 a 79,710 μs. docker_read após fim estimado de status: 0,386 a 136,299 ms; fora do intervalo aproximado da chamada Docker: 0. Maior atraso de agendamento registrado: 97,323 ms. Esses marcadores não sincronizam a leitura de memória com a liberação de um processo.

Falhas de parsing aparecem em 49 estratos run/fase, com 1 a 6 falhas por estrato não vazio. A comparação sucesso/falha é apenas descritiva, com n pequeno/irregular; a duração da operação é observada mesmo quando o gauge falha.

## 3. Relação com conexões e atendimento

Reading/Writing/Waiting/active usam somente status bem-sucedido do mesmo ciclo, separado da leitura Docker por no máximo 0,5 s. As 119 falhas permanecem ausentes; não se busca o último sucesso. Upstream e volume científicos usam logs associados a IDs no mesmo run, na janela passada [t−1,t), com suporte por classe; janelas vazias dão média upstream ausente e volume observado zero. Monitoring/setup/capture_audit são excluídos das estatísticas de logs científicos e mantidos no controle de suporte. Os gauges de conexões são globais, incluem monitoring e não permitem separação por classe via request_id; não se subtrai uma conexão presumida por consulta.

O CSV de associações inclui níveis e primeiras diferenças por execução/fase para as variáveis pré-especificadas, com n de pares e motivo de indefinição. Variáveis constantes (por exemplo Reading) não geram correlação zero artificial. A figura mostra duração de status, conexões ativas e upstream legítimo. Relações de nível com conexões/atendimento podem compartilhar tendência no tempo; sua persistência ou ausência nas diferenças deve ser lida junto ao suporte. Não há teste de independência das milhares de leituras nem p-valores ou ICs exploratórios.

| E16/ACTIVE | ρ níveis, mediana entre runs | ρ diferenças, mediana | Definidos nível/Δ | Pares nível / Δ, faixa entre runs |
|---|---:|---:|---:|---:|
| reading | indefinido | indefinido | 0/12; 0/12 | 50–120 / 49–119 |
| writing | 0,307 | 0,025 | 12/12; 12/12 | 50–120 / 49–119 |
| waiting | -0,006 | -0,001 | 12/12; 12/12 | 50–120 / 49–119 |
| active | 0,388 | 0,023 | 12/12; 12/12 | 50–120 / 49–119 |
| upstream_benign_ms | 0,351 | -0,026 | 12/12; 12/12 | 49–119 / 48–118 |
| upstream_attack_ms | 0,354 | 0,042 | 12/12; 12/12 | 49–119 / 48–118 |
| scientific_completions_per_s | -0,076 | -0,023 | 12/12; 12/12 | 49–119 / 48–118 |

Reading é constante em E16/ACTIVE; por isso o coeficiente é indefinido, apesar dos pares observados. Writing, conexões ativas e upstream têm associação positiva de nível, mas mediana dos coeficientes em diferenças próxima de zero. O padrão de saltos não acompanha essas variações de atendimento de modo tão repetido quanto a duração das operações de observação. Isso limita explicações simples baseadas somente em número de conexões ou upstream; não exclui efeitos atrasados, indiretos ou carga compartilhada.

No horizonte, status alinhado em 12841 leituras; falha=119; sucesso fora da distância permitida=0. Suporte por preditor e modo está no CSV, inclusive médias upstream ausentes quando nenhuma conclusão válida ocorreu na janela passada.

## 4. Composição efetivamente salva e identificação

`resources` recebe a resposta stats Docker, mas salva da memória apenas `memory_stats.usage` como `memory_usage_bytes`. As chaves de docker.data foram inventariadas nas 14.094 leituras. Anon/RSS, cache de arquivos, sockets/kernel, PID/RSS/PSS por processo e eventos de alocação/liberação não estão nos registros do proxy. A API pode oferecer outros campos dependendo da versão/cgroup; isso não os torna retroativamente disponíveis. `raw/infrastructure` e `mem_usage` do schema descrevem vítimas, não decomposição do proxy.

**Hipóteses compatíveis:** variação transitória/contabilização do cgroup e efeito do momento de amostragem em relação às operações auxiliares; resposta compartilhada à carga, incluindo atendimento e custos das consultas. **Não verificável com os registros atuais:** qual componente físico mudou, quanto pertence ao worker/master/wget, se houve queda de RSS do NGINX, liberação de cache, memória de sockets ou retenção/liberação pós-processo. Não se estima nenhuma parcela por subtração.

Faltam séries sincronizadas de anon/RSS/cache/kernel/sockets do cgroup; memória e vida dos PIDs do worker, master e auxiliares; instantes de spawn/exit e liberação de contabilização; e evidência que separe a variação do monitor da carga compartilhada. Estes itens delimitam a identificação ausente; nenhum novo experimento foi preparado ou executado.

## Arquivos e legendas

- [A: 36 séries](figures/A_native_memory_all_runs.pdf) · [PNG](figures/A_native_memory_all_runs.png): memória bruta nativa por bin de 1 s contendo uma leitura; fronteiras reais por linha, sem corte de amplitude ou interpolação.
- [B: distribuições](figures/B_memory_ecdf_by_run_phase.pdf) · [PNG](figures/B_memory_ecdf_by_run_phase.png): ECDF separada de cada run/fase; redistribuição sem limiar alto/baixo.
- [C: associações](figures/C_within_run_associations.pdf) · [PNG](figures/C_within_run_associations.png): um coeficiente descritivo por execução/fase, em níveis e diferenças; indefinidos não viram zero.
- [Leituras/alinhamentos](tables/native_memory_alignment.csv), [distribuições/saltos](tables/run_phase_distributions.csv), [associações e n](tables/within_run_associations.csv), [status sucesso/falha](tables/status_success_conditions.csv).
- [Janelas de 30 s](tables/fixed_windows_30s.csv), [diferenças de quantis pareadas](tables/paired_quantile_differences.csv), [suporte por run](tables/run_support.csv), [inventário de composição](tables/composition_inventory.csv), [chaves efetivas](tables/saved_docker_fields.csv).
- [Metodologia/alinhamento](methodology.md), [fontes e hashes](tables/sources.csv), [proveniência](provenance.json), [comando exato](reproduce.sh).
