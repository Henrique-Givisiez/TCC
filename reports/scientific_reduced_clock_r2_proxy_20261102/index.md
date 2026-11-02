# Proxy NGINX — apresentação descritiva clock r2

36 execuções TEST, 12 blocos por cenário. Temporal: B01. Somente artefatos existentes; novas agregações estritamente descritivas, sem ICs ou testes inferenciais. Nenhum detector foi executado.

| Figura | Finalidade e legenda sugerida |
|---|---|
| [Temporal PDF](figures/P_proxy_temporal_B01.pdf) · [PNG](figures/P_proxy_temporal_B01.png) | Exemplo ilustrativo B01, uma coluna por cenário: CPU Docker, memória bruta, conexões ativas e média upstream por conclusão/log em bins de 5 s, separando legítimos/ofensivos. Escalas comuns por variável; leituras nativas com lacunas. Faixa e linhas marcam emissão real e comando quando existem. Não substitui as 12 repetições. |
| [Individuais PDF](figures/Q_proxy_individual_runs_phases.pdf) · [PNG](figures/Q_proxy_individual_runs_phases.png) | Cada ponto é uma média de uma execução/fase; linhas unem cenários do mesmo bloco. CPU e memória usam médias amostrais; upstream legítimo usa conclusões/logs na fase, não coorte por início. PRE/ACTIVE/POST separados; sem pooling, IC ou teste. |

## Resumo descritivo

A tabela abaixo mostra a mediana das 12 médias por execução, com mínimo–máximo entre essas médias. Não representa percentis das requisições ou limites de confiança.

| Fase | Cenário | CPU (%) | Memória (MiB) | Upstream legítimo (ms) |
|---|---|---:|---:|---:|
| PRE | C16 | 2,495 [2,434; 2,552] | 9,237 [9,016; 9,482] | 29,518 [28,801; 30,228] |
| PRE | M16 | 2,480 [2,436; 2,559] | 9,232 [8,882; 9,364] | 29,374 [28,687; 30,007] |
| PRE | E16 | 2,489 [2,451; 2,539] | 9,264 [8,946; 9,484] | 29,339 [28,795; 30,517] |
| ACTIVE | C16 | 2,615 [2,566; 2,646] | 8,815 [8,477; 9,057] | 29,624 [29,240; 30,322] |
| ACTIVE | M16 | 3,173 [3,087; 3,216] | 8,225 [7,939; 8,461] | 36,134 [34,811; 36,894] |
| ACTIVE | E16 | 4,289 [3,876; 4,412] | 7,665 [7,531; 7,826] | 640,664 [445,582; 899,473] |
| POST | C16 | 2,712 [2,624; 2,738] | 8,622 [8,229; 8,822] | 29,604 [28,358; 31,089] |
| POST | M16 | 2,803 [2,767; 2,866] | 8,126 [8,013; 8,270] | 30,105 [28,977; 31,321] |
| POST | E16 | 2,825 [2,801; 2,905] | 8,112 [7,773; 8,389] | 75,153 [33,168; 97,454] |

Suporte: 14094 leituras pareadas, 119 falhas de parsing de status e 36 primeiras CPU sem delta, preservadas como ausentes. Access: 277194 linhas; 262224 científicas, das quais 262224 com upstream escalar utilizável. Excluídas como auxiliares: monitoring=14094, setup=36, capture_audit=840. Contagens completas incluem PRE-aquecimento e cauda; as figuras e fases restringem-se a [30,390).

| Classe científica, em todo o arquivo | Tempos upstream válidos | Não utilizáveis |
|---|---:|---:|
| Legítima | 223656 | 0 |
| Ofensiva | 38568 | 0 |

Os motivos de ausência, marcador, upstream múltiplo, endereço ausente/múltiplo, texto malformado, negativo e não finito têm contagem explícita por run/classe na tabela de exclusões, inclusive zeros. As 14.094 consultas monitoring sem upstream não entram na população científica.

Os valores contextualizam as execuções observadas sob suas exposições reais. Não identificam capacidade máxima, saturação, overhead de monitoramento ou causa do comprometimento. As médias de E16 descrevem exposições variáveis sob a política de proteção, não dose igual.

## Tabelas, definições e reprodução

- [Por execução/fase](tables/per_run_phase.csv): médias, n válido, ocupação de bins, lacunas e tempos não utilizáveis por classe/motivo.
- [Resumo entre execuções](tables/descriptive_run_summaries.csv): cada run tem peso igual; não há pooling de amostras.
- [Leituras nativas](tables/native_monitor_reads.csv): todos os instantes, flags de sucesso, CPU nula inicial e falhas de status.
- [Access/IDs](tables/access_association.csv): linha do log, ID, classe do cliente, timestamp, tempos brutos e motivos de exclusão.
- [Suporte por execução](tables/per_run_support.csv) e [exclusões](tables/exclusions_by_reason.csv).
- [Bins ilustrativos de 5 s](tables/upstream_bins_5s.csv): n total científico, n válido, excluídos e média por classe.
- [Nota metodológica](methodology.md), [diagnóstico NGINX](nginx_limits.md), [fontes/hashes](tables/sources.csv), [proveniência](provenance.json).

Reprodução na raiz do repositório: ver [reproduce.sh](reproduce.sh), usando apenas Python/NumPy/Matplotlib locais. O SHA256 esperado do TEST é obrigatório. `--temporal-block` seleciona outro bloco; as comparações continuam incluindo os 12. Sem a opção, escolhe-se o menor bloco completo sem olhar valores. Saídas existentes exigem `--overwrite`; artefatos congelados e apresentações anteriores são protegidos.

Pendências: diagramação no TCC; não há evidência para determinar a ocupação de descritores por worker, picos entre amostras, efeito causal de componentes ou overhead isolado do monitor. A cobertura de bins não é cobertura física contínua.

## Comando exato para uma nova saída

Na raiz do repositório:

```bash
.venv/bin/python -B reports/scientific_reduced_clock_r2_proxy_20261102/generate.py --repo . --plan experiments/protocols/scientific_reduced_clock_r2_20261029/plan.json --checkpoint experiment_results/scientific-reduced-clock-r2-20261029/checkpoints/TEST/manifest.json --checkpoint-sha256 690c7d9af50204d7170fbb08ee61dd672450d2d5dd7e8c0a1de9725669601912 --temporal-block 1 --output reports/proxy_clock_r2_reproduzido
```

Conferências desta entrega: [verification.json](verification.json) e [inspeção visual](visual_review.md). O gerador não certifica automaticamente a inspeção de figuras futuras.
