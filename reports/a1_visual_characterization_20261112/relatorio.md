# Relatório das visualizações legítimas A1

## Delimitação e auditoria

Somente a caracterização de 06/11/2026 em `experiment_results/legitimate-characterization-a1-20261106T202205Z/` foi processada. `raw/effective_config.json` e `raw/run_status.json` confirmam L2 (2×8), L6 (4×4), L3 (2×16), L7 (4×8), `/medium`, 150 s, topologia direta, uma vítima, dois workers, concorrência legítima agregada 64 e ausência de ataque. `report.md` da A1 confirma o intervalo principal [30,150); a análise o aplica como intervalo semiaberto relativo ao início monotônico efetivo do status. Há uma execução por célula. O inventário anterior foi consultado apenas para localização.

Os timestamps HTTP de `request_log.csv` trazem época e `elapsed_seconds` relativo à execução. CPU e memória usam `monotonic` de `victim_stats.jsonl` menos `experiment_start_monotonic`. Os registros da vítima trazem `work_submitted_at`, `work_started_at` e `work_finished_at` dentro de `handler_finished`; os workers declararam `CLOCK_MONOTONIC` no mesmo namespace. Assim, a reconstrução é retrospectiva, por operação, e as séries são alinháveis. Registros `capture_audit` anteriores à execução foram excluídos. Planejamento, submissão e início HTTP dos geradores constam dos eventos `planned`, `submitted`, `task_started` e `http_started`, mas as taxas desta análise usam o início de `request_log.csv`. Entrada no handler é outro evento; conclusão HTTP é `end_elapsed_seconds`, posterior ao início. A fila HTTP pré-handler não foi medida diretamente.

As quatro execuções terminaram `completed/simulation_end`, com `producers_drained=true` e `errors=[]`. Há `request_log.csv`, `rtt_log.csv`, `victim_stats.jsonl`, `simulation_metrics.csv`, eventos da vítima, eventos e journals das fontes, `console.log`, relatórios individuais e análise comparativa A1. `rtt_log.csv` tem os mesmos IDs e totais do log HTTP; `simulation_metrics.csv` é uma série de ticks mais esparsa e não alimenta as figuras de recursos. `normal_traffic_summary_log.csv` registra a configuração e o resumo das fontes. Não foram encontrados erros ou timeouts HTTP nas quatro execuções. O `run_status.json` confirma encerramento normal, e a verificação dos eventos confirma ciclos computacionais completos.

### Síntese numérica do intervalo principal

| Configuração | Inícios / RPS | CPU média / mediana / máximo (%) | Memória média / mediana / máximo (MiB) | Espera mediana / p95 / máximo (ms) | HTTP mediana / média / p95 / máximo (ms) |
|---|---:|---:|---:|---:|---:|
| L2 | 1912 / 15.933 | 48.6 / 48.8 / 80.8 | 26.57 / 26.65 / 28.03 | 1.11 / 14.14 / 48.3 | 36.88 / 45.38 / 77.65 / 101.5 |
| L6 | 1930 / 16.083 | 55.0 / 54.1 / 89.1 | 26.85 / 26.92 / 28.01 | 1.12 / 11.98 / 40.4 | 35.56 / 41.03 / 74.92 / 104.2 |
| L3 | 3766 / 31.383 | 94.2 / 94.0 / 137.8 | 28.39 / 28.51 / 30.06 | 1.13 / 28.86 / 69.0 | 42.99 / 52.29 / 86.48 / 135.0 |
| L7 | 3819 / 31.825 | 118.7 / 118.7 / 191.1 | 28.35 / 28.15 / 30.43 | 1.23 / 52.71 / 267.8 | 48.83 / 59.26 / 113.70 / 318.7 |

CPU e memória têm 40 observações no principal em L2/L6/L3 e 41 em L7. Espera e duração têm respectivamente 1912, 1930, 3766 e 3819 operações/respostas válidas; zero ciclos faltantes. CPU Docker pode exceder 100%. A cadência bruta de CPU/memória teve mediana aproximada de 3,015 s, apesar do polling configurado em 1 s. A memória mudou entre primeira e última amostra em +0,79, +0,78, +3,62 e +2,31 MiB para L2, L6, L3 e L7. A comparação inicial/final é uma diferença entre duas observações, não uma tendência estimada.

## Catálogo comentado

### A1 — RPS nominal versus efetivo

**Pergunta:** P1, P8. **Arquivos PNG:** [A1_rps_nominal_efetivo.png](figures/A_geracao/A1_rps_nominal_efetivo.png). Cada PNG tem PDF vetorial homônimo.

**Fonte:** `effective_config.json`; `request_log.csv`. **Métrica:** RPS nominal = fontes × taxa/fonte; efetivo = inícios HTTP / 120 s. **Intervalo:** [30,150); coorte pelo início HTTP. **Agregação:** Contagem de início dividida por 120 s.

**Observação:** As taxas observadas ficaram próximas às nominais. **Limitação/qualidade:** Uma realização por configuração; plano não equivale a início.

### A2 — Evolução temporal do RPS

**Pergunta:** P1, P7. **Arquivos PNG:** [A2_rps_temporal_L2.png](figures/A_geracao/A2_rps_temporal_L2.png), [A2_rps_temporal_L6.png](figures/A_geracao/A2_rps_temporal_L6.png), [A2_rps_temporal_L3.png](figures/A_geracao/A2_rps_temporal_L3.png), [A2_rps_temporal_L7.png](figures/A_geracao/A2_rps_temporal_L7.png), [A2_rps_temporal_comparativo.png](figures/A_geracao/A2_rps_temporal_comparativo.png). Cada PNG tem PDF vetorial homônimo.

**Fonte:** `request_log.csv`. **Métrica:** Inícios HTTP por janela de 1 s. **Intervalo:** [0,150); principal sombreado. **Agregação:** Bins semiabertos de 1 s.

**Observação:** Há oscilações de segundo a segundo sem queda sustentada no recorte principal. **Limitação/qualidade:** A contagem por bin não informa planejamento ou duração.

### B1 — Utilização de CPU

**Pergunta:** P2, P3, P8. **Arquivos PNG:** [B1_cpu_comparativo.png](figures/B_recursos/B1_cpu_comparativo.png). Cada PNG tem PDF vetorial homônimo.

**Fonte:** `victim_stats.jsonl`. **Métrica:** `metrics.cpu_percent`: CPU Docker do contêiner `target_instance_1`; 100% ≈ um núcleo lógico. **Intervalo:** [30,150). **Agregação:** Amostras reais; caixa, mediana, média e extremos.

**Observação:** As médias amostradas foram maiores em 32 RPS. **Limitação/qualidade:** Sem ponderação temporal nem intervalo de confiança; amostras autocorrelacionadas.

### B2 — Evolução temporal da CPU

**Pergunta:** P2, P7. **Arquivos PNG:** [B2_cpu_temporal_L2.png](figures/B_recursos/B2_cpu_temporal_L2.png), [B2_cpu_temporal_L6.png](figures/B_recursos/B2_cpu_temporal_L6.png), [B2_cpu_temporal_L3.png](figures/B_recursos/B2_cpu_temporal_L3.png), [B2_cpu_temporal_L7.png](figures/B_recursos/B2_cpu_temporal_L7.png), [B2_cpu_temporal_comparativo.png](figures/B_recursos/B2_cpu_temporal_comparativo.png), [B2_cpu_temporal_matriz.png](figures/B_recursos/B2_cpu_temporal_matriz.png). Cada PNG tem PDF vetorial homônimo.

**Fonte:** `victim_stats.jsonl`. **Métrica:** CPU Docker da vítima (%). **Intervalo:** [0,150); principal sombreado. **Agregação:** Timestamps monotônicos reais; linhas ligam amostras.

**Observação:** L3 e L7 exibem níveis e oscilações de CPU superiores aos de L2 e L6. **Limitação/qualidade:** Amostragem de cerca de 3 s; os trechos entre pontos não são observações.

### B3 — Utilização de memória

**Pergunta:** P6. **Arquivos PNG:** [B3_mem_comparativo.png](figures/B_recursos/B3_mem_comparativo.png). Cada PNG tem PDF vetorial homônimo.

**Fonte:** `victim_stats.jsonl`. **Métrica:** `raw_mem_usage` / 2²⁰: MiB do contêiner da vítima. **Intervalo:** [30,150). **Agregação:** Amostras reais; caixa, mediana, média e extremos.

**Observação:** As médias foram próximas, com valores um pouco maiores em 32 RPS. **Limitação/qualidade:** Inclui memória do contêiner, não RAM do host nem RSS isolado do Python.

### B4 — Evolução temporal da memória

**Pergunta:** P6, P7. **Arquivos PNG:** [B4_mem_temporal_L2.png](figures/B_recursos/B4_mem_temporal_L2.png), [B4_mem_temporal_L6.png](figures/B_recursos/B4_mem_temporal_L6.png), [B4_mem_temporal_L3.png](figures/B_recursos/B4_mem_temporal_L3.png), [B4_mem_temporal_L7.png](figures/B_recursos/B4_mem_temporal_L7.png), [B4_mem_temporal_comparativo.png](figures/B_recursos/B4_mem_temporal_comparativo.png), [B4_mem_temporal_matriz.png](figures/B_recursos/B4_mem_temporal_matriz.png). Cada PNG tem PDF vetorial homônimo.

**Fonte:** `victim_stats.jsonl`. **Métrica:** `raw_mem_usage` / 2²⁰ em MiB. **Intervalo:** [0,150); principal sombreado. **Agregação:** Timestamps monotônicos reais.

**Observação:** Há aumento líquido entre a primeira e última amostra nas quatro execuções. **Limitação/qualidade:** Eixo vertical ampliado para mostrar mudanças de poucos MiB; as séries não explicam alocação ou liberação internas.

### C1 — Ocupação dos workers

**Pergunta:** P4, P7. **Arquivos PNG:** [C1_ocupacao_workers_L2.png](figures/C_workers/C1_ocupacao_workers_L2.png), [C1_ocupacao_workers_L6.png](figures/C_workers/C1_ocupacao_workers_L6.png), [C1_ocupacao_workers_L3.png](figures/C_workers/C1_ocupacao_workers_L3.png), [C1_ocupacao_workers_L7.png](figures/C_workers/C1_ocupacao_workers_L7.png), [C1_ocupacao_workers_matriz.png](figures/C_workers/C1_ocupacao_workers_matriz.png), [C1_fracao_ocupacao.png](figures/C_workers/C1_fracao_ocupacao.png). Cada PNG tem PDF vetorial homônimo.

**Fonte:** `diagnostics/victim/events.jsonl`. **Métrica:** Operações entre `work_started_at` e `work_finished_at`. **Intervalo:** [0,150); frações em [30,150). **Agregação:** Reconstrução retrospectiva orientada a eventos.

**Observação:** Dois workers ocupados ocorreram em todas as execuções, mais tempo em L3/L7. **Limitação/qualidade:** Não representa handlers HTTP ativos; oscilações rápidas se adensam visualmente.

### C2 — Operações computacionais pendentes

**Pergunta:** P4, P7. **Arquivos PNG:** [C2_operacoes_aguardando_L2.png](figures/C_workers/C2_operacoes_aguardando_L2.png), [C2_operacoes_aguardando_L6.png](figures/C_workers/C2_operacoes_aguardando_L6.png), [C2_operacoes_aguardando_L3.png](figures/C_workers/C2_operacoes_aguardando_L3.png), [C2_operacoes_aguardando_L7.png](figures/C_workers/C2_operacoes_aguardando_L7.png), [C2_operacoes_aguardando_matriz.png](figures/C_workers/C2_operacoes_aguardando_matriz.png). Cada PNG tem PDF vetorial homônimo.

**Fonte:** `diagnostics/victim/events.jsonl`. **Métrica:** Aguardando = submetida e ainda não iniciada; em execução = iniciada e ainda não concluída. **Intervalo:** [0,150); máximos do recorte completo. **Agregação:** Reconstrução orientada a eventos.

**Observação:** Picos de aguardando: L2 4, L6 3, L3 9, L7 12. **Limitação/qualidade:** Não é a profundidade interna exata do executor.

### C3 — Espera por worker

**Pergunta:** P4, P8. **Arquivos PNG:** [C3_wait_ms_boxplot.png](figures/C_workers/C3_wait_ms_boxplot.png), [C3_wait_ms_ecdf.png](figures/C_workers/C3_wait_ms_ecdf.png). Cada PNG tem PDF vetorial homônimo.

**Fonte:** `diagnostics/victim/events.jsonl`; `request_log.csv`. **Métrica:** `(work_started_at − work_submitted_at) × 1000` ms. **Intervalo:** Coorte de início HTTP [30,150). **Agregação:** Boxplot p5–p95, ECDF e tabela.

**Observação:** O p95 foi maior em L3/L7, especialmente L7. **Limitação/qualidade:** Inclui IPC e escalonamento; não corresponde à espera HTTP total.

### C4 — Acúmulo e espera

**Pergunta:** P4. **Arquivos PNG:** [C4_acumulo_espera_dispersao.png](figures/C_workers/C4_acumulo_espera_dispersao.png). Cada PNG tem PDF vetorial homônimo.

**Fonte:** `diagnostics/victim/events.jsonl`; `request_log.csv`. **Métrica:** Operações aguardando imediatamente antes da submissão versus espera subsequente da mesma operação. **Intervalo:** Coorte de início HTTP [30,150). **Agregação:** Dispersão individual; estado antes do evento corrente.

**Observação:** Em L7, esperas longas coincidiram com maiores quantidades aguardando. **Limitação/qualidade:** Associação descritiva; sobreposição de pontos e sem identificação causal.

### D1 — Distribuição da duração HTTP

**Pergunta:** P5, P8. **Arquivos PNG:** [D1_duration_ms_boxplot.png](figures/D_http/D1_duration_ms_boxplot.png), [D1_duration_ms_ecdf.png](figures/D_http/D1_duration_ms_ecdf.png). Cada PNG tem PDF vetorial homônimo.

**Fonte:** `request_log.csv`; `rtt_log.csv` para conferência. **Métrica:** `duration_ms` no cliente; somente respostas HTTP 2xx. **Intervalo:** Coorte de início HTTP [30,150). **Agregação:** Boxplot p5–p95 e ECDF.

**Observação:** Duração média e p95 foram maiores em 32 RPS; L7 teve a cauda mais longa. **Limitação/qualidade:** Inclui rede, espera e processamento; não mede só tempo de serviço.

### D2 — Duração HTTP ao longo do tempo

**Pergunta:** P5, P7. **Arquivos PNG:** [D2_duracao_temporal_L2.png](figures/D_http/D2_duracao_temporal_L2.png), [D2_duracao_temporal_L6.png](figures/D_http/D2_duracao_temporal_L6.png), [D2_duracao_temporal_L3.png](figures/D_http/D2_duracao_temporal_L3.png), [D2_duracao_temporal_L7.png](figures/D_http/D2_duracao_temporal_L7.png), [D2_duracao_temporal_matriz.png](figures/D_http/D2_duracao_temporal_matriz.png), [D2_duracao_temporal_comparativo.png](figures/D_http/D2_duracao_temporal_comparativo.png). Cada PNG tem PDF vetorial homônimo.

**Fonte:** `request_log.csv`. **Métrica:** Mediana e p95 de `duration_ms` de respostas HTTP 2xx. **Intervalo:** Início HTTP em bins de 10 s em [0,150). **Agregação:** p95 apenas com n≥20 por bin; contagens em `processed/http_10s_*.csv`.

**Observação:** L7 teve um episódio de maior p95 por volta de 50–80 s. **Limitação/qualidade:** Valores por janela descrevem esta execução; linha entre bins não é dado medido.

### D4 — Respostas, erros e timeouts

**Pergunta:** P1, P8. **Arquivos PNG:** [D4_desfechos_http.png](figures/D_http/D4_desfechos_http.png). Cada PNG tem PDF vetorial homônimo.

**Fonte:** `request_log.csv`. **Métrica:** Desfecho por `outcome`, `http_status`, `error_type`; denominador = inícios em [30,150). **Intervalo:** Coorte de início HTTP [30,150). **Agregação:** Contagens e proporções por configuração.

**Observação:** Todas as tentativas da coorte tiveram resposta HTTP 200. **Limitação/qualidade:** Conclusões podem ocorrer após o limite da coorte; nenhum timeout foi confundido com resposta.

### E1 — Painel temporal completo

**Pergunta:** P1–P8. **Arquivos PNG:** [E1_painel_integrado_L2.png](figures/E_integradas/E1_painel_integrado_L2.png), [E1_painel_integrado_L6.png](figures/E_integradas/E1_painel_integrado_L6.png), [E1_painel_integrado_L3.png](figures/E_integradas/E1_painel_integrado_L3.png), [E1_painel_integrado_L7.png](figures/E_integradas/E1_painel_integrado_L7.png). Cada PNG tem PDF vetorial homônimo.

**Fonte:** `request_log.csv`; `victim_stats.jsonl`; eventos da vítima. **Métrica:** Seis faixas: inícios/s, CPU, memória, workers ocupados, operações aguardando, duração HTTP. **Intervalo:** [0,150); principal sombreado. **Agregação:** Bins de 1 s e 10 s, amostras reais e estados por evento.

**Observação:** L7 reúne maior CPU, mais acúmulo e episódio de duração elevada. **Limitação/qualidade:** Painel alinha relógios; resolução e significado diferem por faixa.

### E2 — Matrizes comparativas

**Pergunta:** P2, P3, P7, P8. **Arquivos PNG:** [E2_rps_matriz.png](figures/E_integradas/E2_rps_matriz.png), [E2_cpu_matriz.png](figures/E_integradas/E2_cpu_matriz.png), [E2_mem_matriz.png](figures/E_integradas/E2_mem_matriz.png), [E2_ocupacao_workers_matriz.png](figures/E_integradas/E2_ocupacao_workers_matriz.png), [E2_operacoes_aguardando_matriz.png](figures/E_integradas/E2_operacoes_aguardando_matriz.png), [E2_duracao_http_matriz.png](figures/E_integradas/E2_duracao_http_matriz.png). Cada PNG tem PDF vetorial homônimo.

**Fonte:** Mesmos registros das famílias A–D. **Métrica:** Seis métricas em matriz: linhas 2/4 fontes; colunas 16/32 RPS. **Intervalo:** [0,150); principal sombreado. **Agregação:** Escala vertical comum por métrica.

**Observação:** Comparações entre colunas evidenciam maiores recursos e duração em 32 RPS. **Limitação/qualidade:** Uma realização por célula; diferenças não são efeitos causais.

## Comparações descritivas

- **L2 → L3, duas fontes:** RPS 15.933 → 31.383; CPU média 48.6% → 94.2%; HTTP médio 45.4 → 52.3 ms; espera p95 14.1 → 28.9 ms.
- **L6 → L7, quatro fontes:** RPS 16.083 → 31.825; CPU média 55.0% → 118.7%; HTTP médio 41.0 → 59.3 ms; espera p95 12.0 → 52.7 ms.
- **L2 → L6, 16 RPS:** RPS 15.933 → 16.083; CPU média 48.6% → 55.0%; HTTP médio 45.4 → 41.0 ms; espera p95 14.1 → 12.0 ms.
- **L3 → L7, 32 RPS:** RPS 31.383 → 31.825; CPU média 94.2% → 118.7%; HTTP médio 52.3 → 59.3 ms; espera p95 28.9 → 52.7 ms.

L2 sustentou aproximadamente 16 RPS, teve respostas integrais, CPU média amostrada abaixo das configurações de 32 RPS e pico de quatro operações aguardando. Esses registros tornam a escolha de L2 como referência operacionalmente compreensível nesta execução. L6 também sustentou 16 RPS e apresentou algumas medidas de latência menores; os dados não estabelecem superioridade estatística de L2. As diferenças entre células são observações de realizações únicas, sem inferência causal ou testes de significância.

## Validação e limites

- 53 figuras, cada uma em PNG de 300 dpi e PDF vetorial. Fontes, identificadores, eixos, unidades e sobreposições foram inspecionados nas figuras de distribuição, desfechos, matriz CPU, dispersão C4 e painel E1.
- Contagens de `request_log.csv`, `rtt_log.csv`, inícios e fins HTTP nas fontes e ciclos da vítima coincidem por execução. IDs de requisição são únicos. Durações são não negativas e coerentes com os timestamps de início/fim.
- A reconstrução não produziu estados negativos nem mais de dois workers em execução. Eventos simultâneos seguem a ordem submissão, início e fim; os ciclos têm instantes estritamente ordenados. Frações de ocupação em [30,150) somam 1.
- Os hashes SHA-256 das entradas utilizadas estão em `validation/checks.json`; o gerador somente lê as entradas. O comando de reprodução abaixo pode confirmar a persistência desses hashes após execução.
- Não houve imputação de CPU ou memória nem interpolação de pontos ausentes. As linhas entre amostras servem somente à leitura visual. As séries de estados por evento podem formar áreas visualmente densas.
- Limites: não há medição direta da fila pré-handler; espera por worker inclui IPC/escalonamento; operações aguardando não são profundidade privada do executor; duração HTTP do cliente abrange mais do que serviço; não separamos causas das diferenças; nenhuma figura obrigatória foi omitida.

## Reprodução

Na raiz do repositório, com Python 3, `numpy`, `pandas` e `matplotlib`:

```bash
python3 reports/a1_visual_characterization_20261112/scripts/generate.py
python3 reports/a1_visual_characterization_20261112/scripts/write_report.py
```

Entradas: exclusivamente a pasta A1 acima. Parâmetros: 150 s, principal [30,150), RPS em 1 s, duração em 10 s com p95 somente para n≥20. Saídas: `figures/`, `processed/`, `manifest.json`, `validation/checks.json` e este relatório. Código: scripts locais desta entrega; proveniência da coleta em `raw/run_provenance.json` de cada configuração.

Versão dos scripts (SHA-256): `generate.py` d0b1a55829c3e830a9e55774e5a71d0aa37f60cf4544c70fd8e1b0b148da5997; `write_report.py` d4a306152a7cb7a078343447c7f37e806a48f6010fe4c17ed5b70ec6926728fb.
