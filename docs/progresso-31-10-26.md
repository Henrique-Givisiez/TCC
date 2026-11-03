**Relatório de progresso — 31/10/2026**

Este registro cobre o avanço desde o último complemento de definições metodológicas: planejamento da apresentação dos resultados, geração das figuras, inventário do proxy e revisão do commit `46c108bccce0b350a8ab4b87ac86756f632104e7`.

**1. Organização da análise dos resultados**

Definimos três frentes de análise:

- **Detectores:** detecção por evento, misses, falsos alarmes, atraso condicional, recall por janela e alarmes após a emissão.
- **Vítima e atendimento legítimo:** duração HTTP, sucesso, timeouts, CPU, pendências, recuperação e exposição ofensiva realizada.
- **Proxy:** consumo de recursos, tráfego, conexões, requisições e tempos upstream, conforme o suporte dos registros existentes.

A decisão foi aproveitar os artefatos congelados da campanha. Não foram solicitadas novas coletas nem alterações nos detectores ou na calibração.

**2. Produção do primeiro conjunto de figuras**

O Codex criou o pacote:

`reports/scientific_reduced_clock_r2_figures_20261031/`

Foram produzidas quatro figuras:

| Figura | Conteúdo | Finalidade |
|---|---|---|
| A — Detecção | Quatro métodos, cinco features e cenários M16/E16, com ICs e misses | Comparar a detecção por evento |
| B — Falsos alarmes | FPR de `request_starts` em C16/M16/E16, com ICs | Comparar falsos alarmes nas condições avaliadas |
| C — Impacto pareado | CPU da vítima, duração HTTP e timeouts, com os 12 pares M16/E16 | Mostrar impacto e variabilidade entre blocos |
| D — Evolução temporal | Carga, duração, CPU, pendências e alarmes do bloco B01 | Ilustrar a evolução do experimento |

As figuras foram exportadas em **PDF vetorial e PNG a 300 dpi**. Também foram preparados:

- script reutilizável `generate.py`;
- tabelas CSV;
- contrastes em Markdown e LaTeX;
- legendas sugeridas;
- inventário das fontes e de seus hashes;
- registro das transformações e das pendências.

Segundo a validação do Codex, as quatro figuras foram inspecionadas visualmente, e os PDFs possuem fontes incorporadas.

O bloco B01 foi escolhido por ser o bloco completo de menor identificador. Esse critério independe dos resultados e evita selecionar uma execução pela aparência das curvas.

**3. Definições esclarecidas durante a preparação**

A documentação passou a distinguir explicitamente as populações usadas nas figuras C e D:

- **Figura C:** duração e timeouts pertencem à coorte de requisições legítimas iniciadas em ACTIVE, incluindo conclusões posteriores à fase. A fração de timeouts usa os concluídos dessa coorte como denominador.
- **Figura D:** a duração é agregada pela janela de conclusão, em intervalos ilustrativos de cinco segundos.
- **CPU:** corresponde à vítima inteira, sob ambas as classes de tráfego. Não é atribuída exclusivamente aos clientes legítimos.
- **Pendências:** representam tentativas ainda abertas no cliente, não a fila interna do servidor ou do proxy.

Também foi documentado que a fase operacional ACTIVE começa em **150 segundos nominais**, enquanto a exposição ofensiva usa o início real certificado. Essa pequena diferença é preservada.

Os gráficos mantêm a ressalva de que E16 e M16 tiveram exposições diferentes devido à proteção operacional. As figuras temporais não substituem a análise das 12 repetições.

**4. Inventário do proxy**

O Codex confirmou a presença dos arquivos esperados nas **36 execuções TEST**, com vínculos por execução e contêiner.

| Item | Resultado da conferência |
|---|---|
| Amostras de monitoramento | 14.094 |
| Leituras Docker bem-sucedidas | 14.094 |
| Valores de CPU disponíveis | 14.058; primeira leitura ausente em cada execução |
| Leituras de status NGINX bem-sucedidas | 13.975 |
| Falhas de parsing de `stub_status` | 119, entre 1 e 8 por execução |
| Cobertura Docker em `[30,390)` | 360/360 intervalos de um segundo por execução |
| Cobertura de status NGINX | 352–359 dos 360 intervalos por execução |

As falhas de `stub_status` foram preservadas como lacunas, sem preenchimento por zero. Elas não representam automaticamente falhas nas requisições de cliente.

Os access logs contêm **277.194 registros**, distribuídos entre carga científica, monitoramento, auditoria de captura e setup. Todos os IDs de requisições de cliente foram encontrados, sem IDs extras não vazios ou duplicatas, segundo a conferência apresentada.

O inventário também esclareceu que:

- memória do proxy está registrada em bytes brutos;
- tráfego deve ser analisado por interface, evitando contar os dois segmentos como tráfego HTTP único;
- consultas de monitoramento influenciam os contadores observados;
- tempos upstream ausentes não devem receber zero;
- os dados do proxy ainda não possuem consolidação científica de efeitos e ICs no resumo principal.

**5. Aviso de configuração do NGINX**

Foi identificado nos logs o aviso de que `worker_connections=4096` excede o limite de arquivos abertos de 1024.

Esse registro **não demonstra que o proxy tenha limitado os experimentos**, mas impede tratar 4096 como capacidade efetiva comprovada. Ficou pendente confrontar a configuração, os limites registrados e as conexões observadas.

Nenhuma configuração histórica foi modificada.

**6. Persistência dos alarmes**

A inspeção confirmou que o caminho científico atual possui:

- contagem de janelas positivas em POST;
- quantidade de janelas POST disponíveis;
- frações de alarmes POST, incluindo resumos com IC.

Não foi localizada uma métrica temporal específica, como tempo até o último alarme ou até cessação estável. Decidimos utilizar as definições existentes, mantendo separadas a recuperação do serviço e a cessação dos alarmes.

**7. Revisão do commit**

Foi analisado o [commit `46c108b`](https://github.com/Henrique-Givisiez/TCC/commit/46c108bccce0b350a8ab4b87ac86756f632104e7), com foco no gerador, nas fontes e na documentação.

A revisão confirmou que o script:

- utiliza resultados e ICs congelados;
- verifica referências dos arquivos consumidos;
- não importa o runtime científico;
- preserva valores ausentes nas tabelas;
- documenta as agregações auxiliares.

Minha revisão foi do código e da documentação; não reproduzi a geração nem fiz uma segunda inspeção visual dos PDFs.

Foram sugeridos dois aperfeiçoamentos locais, ainda não confirmados como implementados:

1. Exigir o hash esperado do checkpoint TEST na execução do gerador.
2. Exigir autorização explícita para sobrescrever uma pasta de apresentação existente, ou usar uma saída nova.

Não foi identificado, nessa revisão, um motivo para repetir a campanha.

**8. Estado atual e próximos passos**

A campanha principal continua concluída: **56 coletas aceitas, 12 trios TEST completos e resultados congelados**. Neste período, não houve novos experimentos, recalibração, scores, decisões ou ICs científicos.

O avanço foi transformar os resultados existentes em um pacote de apresentação reproduzível e identificar o suporte disponível para analisar o proxy.

Próximas atividades:

- incorporar as figuras e tabelas selecionadas ao capítulo de resultados;
- consolidar descritivamente o proxy, preservando lacunas e distinguindo as classes de registros;
- investigar offline o aviso de conexões e arquivos abertos;
- completar as pendências documentais da metodologia, sobretudo ambiente e formulação dos detectores;
- avaliar os dois ajustes sugeridos no gerador de apresentação.

Autoscaling, ataques periódicos e novos cenários permanecem como extensões opcionais, fora do escopo principal consolidado.