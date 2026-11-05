# Evolução temporal do custo de CPU em C3 e C5

Análise offline dos eventos diagnósticos já preservados. Os bins usam a âncora monotônica validada e os mesmos intervalos de um segundo da análise anterior. O custo de CPU é `work_cpu_seconds` medido no processo worker por operação; espera submit→início, tempo de parede e duração HTTP são métricas distintas.

## Achados

- **C5 já começa acima de C3.** Nos segundos 0–5, a média dos seis bins foi 12,45 ms/op em C5 (mediana dos bins 12,57 ms) e 11,42 ms/op em C3 (mediana 11,41 ms). Nesse começo, espera média por bin ficou aproximadamente entre 4–23 ms em C5 e 5–11 ms em C3; pendências médias eram baixas (menos de 4 em cada bin). Portanto, a diferença de CPU aparece antes da elevação acentuada do trabalho aguardando início.
- **C5 aumenta durante a execução, sem trajetória monotônica.** A média por bin ficou em cerca de 11–13 ms nos primeiros segundos, começou a subir em alguns bins já entre 2–6 s, chegou a 15–19 ms em vários bins entre 8–14 s e oscilou depois. Entre os segundos 8–13, a média das médias por bin foi 16,27 ms em C5 contra 11,44 ms em C3. O pico isolado de 22 ms no segundo 13 é sensível à composição daquele bin e não caracteriza sozinho uma mudança permanente.
- **Espera e pendências crescem mais tarde e em paralelo com parte da elevação de CPU.** Na série de 1 s, C5 mostra crescimento claro da espera e das operações submetidas ainda não iniciadas por volta de 7–9 s; a média de pendências alcança dezenas nos segundos 10–15, enquanto os workers permanecem quase sempre ocupados. A elevação de CPU começa antes disso em alguns bins e continua durante o acúmulo. A resolução de 1 s e os brackets de observação (~50–62 ms) não permitem ordenar eventos próximos dentro de cada bin.
- **Os dois workers participam; os picos variam entre eles.** As médias por PID mostram ambos acima do nível de C3 em vários bins de C5. Um PID tem valores altos em alguns segundos (por exemplo, cerca de 22 ms no segundo 13), enquanto o outro atinge seus maiores valores em outros (por exemplo, cerca de 18 ms nos segundos 15 e 17). Não há evidência de que toda a diferença esteja concentrada num único worker; a amostra por segundo varia e os picos não coincidem perfeitamente.
- **CPU e parede acompanham-se em boa parte, mas não são intercambiáveis.** O artefato anterior registra médias globais de CPU e parede de 14,65 e 14,68 ms/op em C5, e 11,37 e 11,39 ms/op em C3. Nos bins, as séries são próximas, porém há divergências em bins específicos. A duração HTTP contém ainda espera pelo worker, handler e outras etapas; não deve ser usada como medida de execução computacional.

## Respostas e limites

1. **Sim:** C5 já tem CPU/op maior nos segundos iniciais, antes do backlog expressivo.
2. **Sim, com oscilação:** a série de C5 sobe em vários intervalos, não de forma progressiva uniforme.
3. O crescimento sustentado da CPU começa antes ou perto do começo do acúmulo (aprox. 6–9 s) e continua durante a espera elevada. A resolução não estabelece precedência fina dentro dessa transição.
4. Ambos os workers mostram aumento/variabilidade; nenhum PID explica sozinho o comportamento. A diferença de picos por segundo não sustenta inferência sobre afinidade ou causa.
5. O custo maior ajuda quantitativamente a explicar menor folga: a análise anterior estimou demanda média de CPU do pool em ~1,88 de 2 cores em C5 versus ~1,46 em C3, em concordância com maior ocupação observada. Isso é compatível com aproximação da capacidade de processamento, não uma medida de capacidade máxima.
6. Os dados fortalecem a descrição de serviço mais custoso/variável em C5 e de alta ocupação acompanhada por backlog. Não identificam a origem do custo extra. Número/distribuição de fontes, escalonamento, frequência, variação operacional e outros fatores não foram isolados; há uma execução por condição.

Não se conclui causalidade entre CPU maior, número de fontes e fila. A comparação de workers usa `worker_clock.pid` presente nos eventos concluídos, atribuindo a operação ao bin do `work_started_at`; contagens pequenas e limites dos bins afetam estatísticas de cauda. Os CSVs incluem quantidade de operações e estatísticas de CPU agregadas e por PID, além de espera, pendências e ocupação dos workers. A pendência continua sendo reconstruída de submitted→worker-start, e não leitura direta da fila privada.

## Artefatos

- [Tabela temporal agregada (1 s)](cpu_timing_1s.csv)
- [CPU temporal por processo worker (1 s)](worker_cpu_1s.csv)
- [Gráfico CPU, espera e pendências](cpu_timing_backlog.png) ([SVG](cpu_timing_backlog.svg))
- Script reprodutível: [generate.py](generate.py)

O gráfico mostra média de CPU por bin, espera média e média temporal de operações pendentes. Linhas horizontais na primeira faixa marcam as médias globais anteriores; a linha vertical pontilhada marca o início aproximado da elevação sustentada de espera/pendências. A análise não leu nem modificou os dados brutos e não executou experimentos.
