# Stage 15C — entrega para revisão científica

**Status: entregue para revisão científica; não FROZEN.**

O [relatório científico completo em português](../experiment_results/stage15c-descriptive-analysis-20261019/relatorio_cientifico.md)
contém as 20 configurações, evidências, hipóteses explicativas, limitações e tabelas
por cenário, incluindo suporte de eventos/delays e comparações pareadas.

- [Manifest de proveniência](../experiment_results/stage15c-descriptive-analysis-20261019/stage15c_analysis_manifest.json).
- [Tabelas em JSON, com null explícito](../experiment_results/stage15c-descriptive-analysis-20261019/analysis_tables.json).
- [Resumos primários](../experiment_results/stage15c-descriptive-analysis-20261019/tables/primary_descriptive.csv).
- [Pares P−C](../experiment_results/stage15c-descriptive-analysis-20261019/tables/paired_descriptive.csv).
- [Evidência de persistência por run](../experiment_results/stage15c-descriptive-analysis-20261019/tables/persistence_per_run.csv).

## Reprodução

```bash
.venv/bin/python -B -m experiments.stage15c_analysis --preflight-only
.venv/bin/python -B -m experiments.stage15c_analysis
.venv/bin/python -B -m experiments.stage15c_analysis --verify
```

As referências 15A/15B são localizadas pelo Git e conferidas pelos hashes aprovados;
os demais arquivos são resolvidos pelos manifests. O encerramento 15B deve ser
ancestral do HEAD, sem exigir igualdade. Nenhuma bridge histórica é reaberta.
Outputs existentes somente são aceitos quando idênticos; o script não altera
artefatos congelados. Não importa nem executa o pipeline de detecção/avaliação.

A unidade experimental permanece run/seed: 48 runs, 16 seeds pareadas e 20
configurações. Primary [48,144); startup [0,48) separado. Undefined permanece null;
SD amostral ddof=1, null se n<2. Q1/Q3 usam interpolação linear tipo 7:
h=(n−1)p nos valores definidos ordenados. As diferenças P−C usam pares completos;
atrasos pareados exigem detecção nos dois cenários. Nenhum teste inferencial,
p-valor, bootstrap ou intervalo de confiança foi executado.

## Achados e limites da interpretação

- Z-score apresenta alarmes pontuais: em request_starts detecta 16/16 eventos C/P,
  mas Recall médio é 0.5411/0.1750. Event-level e cobertura window-level não são equivalentes.
- CoV responde de modo distinto entre regimes: Recall médio de request_starts é
  0.0125 em C e 0.1625 em P. Isso é compatível com resposta à variabilidade local,
  sem isolar causalmente a periodicidade.
- EWMA apresenta, para request_starts, Recall C=0.9929 e pós-evento C=0.0890;
  memória temporal traz cobertura e persistência, com dependência da feature.
- CUSUM/request_starts mantém taxa pós-evento 1 nos 16 C. As observações pareadas
  e os scores congelados sustentam uma explicação compatível com memória acumulada.
  Duração e CPU também exibem resíduos observacionais: não se atribui toda
  persistência ao acumulador.

A menor seed pareada elegível, 171864802, foi escolhida deterministicamente para
os exemplos, sem usar desempenho. As cinco features e B/C/P são apresentados nas
mesmas escalas por linha comparável. Há seis figuras principais e cinco apêndices
temporais, em PNG e PDF; null não é representado como zero.

P combina duty cycle 1/3 e menor volume médio de ataque. P−C não mede um efeito
isolado de periodicidade. Overlap observacional suficiente para detectar um evento
não demonstra que o ataque causou cada alarme. Entry 29/C permanece incluída sem
exclusão, reponderação ou sensibilidade post hoc.

As conclusões são condicionadas aos parâmetros congelados, upper-tail, 16 seeds e
ambiente controlado. Não demonstram generalização para cloud real ou dano econômico
EDoS. Complexidade é discutida por inspeção do código; não houve benchmark de
latência/custo financeiro. Inferência futura exigiria um desenho separado, com
contrastes, multiplicidade e seleção dos delays detectados previamente definidos.

Nenhum ranking único, tuning, alteração de scores/decisions/thresholds/GT,
nova campanha, commit ou push foi realizado nesta etapa.
