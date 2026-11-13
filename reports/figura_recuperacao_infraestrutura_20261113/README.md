# Recuperação da infraestrutura após o ataque

Figura de dois painéis adaptada visualmente da B1-A, para acompanhar a figura consolidada das características temporais na seção 5.3. Usa apenas `reports/investigacao_recuperacao_pos_ataque_20261113/processed/tracos_5s_por_execucao.csv`; a validação confere o inventário TEST e `processed/post_por_execucao.csv` da mesma investigação. A paleta, estilos de linha, tipografia, grade e transparência seguem `reports/figura_caracteristicas_temporais_20261113/gerar_figura.py`.

Cada ponto representa um bloco de cinco segundos, posicionado no centro do intervalo. A curva é a média de 20 execuções TEST por cenário; a faixa é **média ± 1 desvio padrão amostral entre execuções** (`ddof=1`), não um intervalo de confiança. A faixa da fila é limitada inferiormente a zero; a da ocupação é limitada a [0%,100%]. Não há suavização ou interpolação. A ocupação é a fração temporal com ambos os workers ocupados, multiplicada por 100; não representa uso de CPU.

O eixo horizontal mostra [240,390) s: os últimos 30 s de ACTIVE e toda a fase POST. A marca em 270 s indica o **fim da emissão ofensiva**, sem implicar recuperação imediata. `waiting_mean` mede operações internas aguardando processamento, que não devem ser automaticamente equiparadas a requisições HTTP distintas. A coincidência temporal das curvas não demonstra causalidade isoladamente. Tempos de recuperação segundo o critério operacional da investigação B1 permanecem no relatório, sem marcadores nesta figura.

Reprodução, a partir da raiz do repositório (Python 3, pandas, NumPy e Matplotlib):

```bash
python3 reports/figura_recuperacao_infraestrutura_20261113/gerar_figura.py
```
