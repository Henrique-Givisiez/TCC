# Resultados

- `graficos/` e `graficos_apresentacao/`: gráficos e tabelas derivados.
- `ml_dataset/`: dataset de features preservado e rastreado.
- `logs/`: logs históricos da raiz e de `scratchpad/`.
- Arquivos soltos: capturas PCAP e saídas CSV/XLSX/PNG preservadas da raiz.

O histórico de 6.469 arquivos em `../experiment_results/` foi mantido no caminho original nesta etapa. Os runners continuam usando esse diretório e os CSVs transitórios da raiz; não há migração automática nem combinação de árvores de resultados.

Novas saídas automáticas nos diretórios de gráficos, logs e `experiment_results/` são ignoradas. Artefatos já rastreados permanecem versionados. A inclusão deliberada de uma saída ignorada pode ser feita com `git add -f <arquivo>`.
