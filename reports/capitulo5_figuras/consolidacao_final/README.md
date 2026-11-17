# Consolidação do Capítulo 5 para Overleaf

Esta pasta contém cópias das versões atuais de **11 figuras** (`figures/`,
PDF e PNG) e **2 tabelas** (`tables/`, TeX e CSV). Os originais dos cinco
lotes permanecem em seus diretórios. Nenhum dado bruto, resultado científico
oficial ou script gerador foi alterado nesta consolidação.

- `inventario.csv`: uma linha por visualização selecionada, com status,
  estatística, fonte experimental e script gerador.
- `manifesto_copias.csv`: origem, destino, tamanho e SHA256 das 26 cópias;
  os hashes foram comparados após a cópia.
- `auditoria.md`: proveniência, definições, revisão visual, sobreposições e
  pendências por prioridade.
- `ordem_sugerida.md`: sequência editorial e pergunta de cada item.

## Uso no Overleaf

Copiar `figures/*.pdf` e `tables/*.tex` para o projeto; os PNG servem para
revisão. Incluir `\usepackage{booktabs}` no preâmbulo e inserir as tabelas
TeX por `\input{...}`. As tabelas já possuem `table`, `caption` e `label`;
evitar envolvê-las em outro ambiente `table`. Compilar no projeto para
conferir larguras, especialmente F5.1-D/E e F5.3-C. Os arquivos nesta pasta
não foram recompilados ou modificados para ajustar a diagramação.

A F5.3-C consolidada é a versão binária mais recente, preservando as 20
execuções em cada uma das 16 combinações. Sua seleção final está pendente:
as versões divididas por detector, mais legíveis para blocos individuais,
estão em `../lote5_alarmes/figures/f53c_binario_*.pdf`/`.png`. As versões
percentuais e de linhas permanecem no Lote 5 como histórico e material de
conferência. A F5.3-D aprovada foi copiada sem qualquer alteração.

Não tratar o status `Revisar` ou `Pendente` do inventário como erro numérico.
Ele identifica a necessidade de aprovação editorial da versão e de verificar
as legendas e o tamanho final no Overleaf. A auditoria não identificou
bloqueio científico P0.
