# Figura consolidada das características temporais

Figura única, em quatro painéis, das execuções TEST da campanha definitiva. As fontes são `reports/scientific_campaign_visualization_20261112/processed/signals.csv` e `inventario_execucoes.csv`. O script confere as médias por execução e fase contra `reports/consolidacao_fases_tcc/caracteristicas_por_execucao_fase.csv`. Foram consultadas as definições em `reports/scientific_campaign_visualization_20261112/scripts/plots.py` e a investigação de recuperação em `reports/investigacao_recuperacao_pos_ataque_20261113/`.

Os painéis mostram pacotes TCP de entrada, bytes de payload TCP de entrada, requisições HTTP iniciadas e `mean_duration_ms`. Cada valor é de uma janela de 1 s. Para cada segundo e cenário, a curva é a média das 20 execuções e a faixa translúcida é **média ± 1 desvio padrão amostral entre execuções** (`ddof=1`), limitada a zero no desenho por se tratar de métricas não negativas. A faixa não é um intervalo de confiança. Não há suavização, interpolação ou preenchimento. Nas quatro características, todas as 20 execuções têm valor finito em cada janela exibida; a cobertura é 100%.

O eixo horizontal é o tempo relativo à execução, de 30 a 390 s: PRE [30,150), ACTIVE [150,270) e POST [270,390). As linhas pontilhadas marcam 150 s e 270 s; o fundo discreto destaca ACTIVE. O instante de 270 s encerra a emissão ofensiva, não representa recuperação completa. Os eixos verticais são independentes e indicam a unidade de cada característica.

`mean_duration_ms` é a média **por janela de conclusão** produzida pelo pipeline, incluindo tentativas encerradas por timeout; a curva não é a duração média de todas as requisições individuais. A3 e F96 diferem em mecanismo, endpoint e intensidade. A figura compara comportamentos observados, sem estabelecer equivalência de intensidade ou eficiência intrínseca.

Reproduzir na raiz do repositório (requer pandas, NumPy e Matplotlib):

```bash
python3 reports/figura_caracteristicas_temporais_20261113/gerar_figura.py
```
