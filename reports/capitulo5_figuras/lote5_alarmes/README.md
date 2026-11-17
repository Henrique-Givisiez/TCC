# Capítulo 5 — lote 5: alarmes temporais e POST

Este lote usa somente a campanha `energy-powersaver-20261109`. A avaliação
inclui as **60 execuções TEST**, organizadas em 20 blocos completos (L2, A3 e
F96 em cada bloco). Nenhum detector, limiar, resultado oficial ou dado bruto
foi modificado. CPU não foi adicionada à matriz de detecção.

| Entrega | Arquivos |
|---|---|
| F5.3-C, ataque computacional assimétrico | `figures/f53c_alarmes_assimetrico.pdf` e `.png` |
| F5.3-C, inundação HTTP | `figures/f53c_alarmes_flooding.pdf` e `.png` |
| F5.3-C revisada, ataque computacional assimétrico | `figures/f53c_mapa_temporal_assimetrico.pdf` e `.png` |
| F5.3-C revisada, inundação HTTP | `figures/f53c_mapa_temporal_flooding.pdf` e `.png` |
| F5.3-D, alarmes após emissão | `figures/f53d_alarmes_post.pdf` e `.png` |
| Proporções por segundo | `processed/proporcao_alarmes_por_segundo.csv` |
| POST por execução | `processed/alarmes_post_por_execucao.csv` |
| Resumo oficial de POST | `tables/alarmes_post_resumo.csv` |
| Proveniência | `processed/manifest.json` |

## Revisão visual da F5.3-C

As duas figuras de linhas originais foram preservadas para consulta ou material
complementar. Os novos mapas temporais substituem sua apresentação no corpo do
capítulo: cada faixa horizontal corresponde a uma combinação detector ×
característica, com grupos Z-Score, CoV, EWMA e CUSUM-freeze nessa ordem e,
dentro de cada grupo, requisições HTTP, pacotes TCP, payload TCP e duração HTTP.
Cada coluna corresponde exatamente a um segundo; não há suavização,
interpolação nem nova agregação. Ambos os mapas usam `cividis_r` e escala fixa
de 0% a 100%, com cores claras para poucos alarmes. Decisões ausentes seriam
mostradas em cinza, sem conversão para zero; no intervalo mostrado, todas as
20 execuções têm decisão válida em todas as células. A representação foi
alterada para revelar combinações sobrepostas nas figuras de linhas.

As linhas verticais em 150 e 270 s delimitam **Período anterior** `[30,150)`,
**Emissão ofensiva** `[150,270)` e **Período pós-ataque** `[270,390)`.
O último nome descreve o calendário após o fim programado da emissão; não
garante que requisições ou operações computacionais tenham terminado.
O rodapé da F5.3-D recebeu apenas essa nomenclatura. Seus 32 valores, a
disposição, a escala de cores e a agregação permanecem iguais.

Para reproduzir somente a revisão gráfica, sem regravar dados processados ou
as figuras antigas:

```bash
.venv/bin/python -B reports/capitulo5_figuras/lote5_alarmes/scripts/revise_visuals.py
```

Esse script lê `processed/proporcao_alarmes_por_segundo.csv` e
`tables/alarmes_post_resumo.csv`, valida 16 combinações × 360 segundos por
cenário, denominador 20 e a fórmula da proporção, e verifica que os hashes
dos dois arquivos de entrada não mudaram. As proporções representadas são
exatamente as usadas pelas figuras de linhas originais.

## Fontes e procedimento

- As decisões binárias vêm de
  `reports/scientific_campaign_visualization_20261112/processed/detectors.csv`,
  campos `entry_id`, `scenario`, `block`, `feature`, `method`, `t`, `decision`,
  `threshold` e `unavailable_reason`. Esse CSV foi produzido por
  `reports/scientific_campaign_visualization_20261112/scripts/audit.py`,
  que lê `analysis/<característica>/TEST/<execução>/manifest.json:methods`.
  O script deste lote confronta **todas as 375.360 decisões** desse CSV com
  os 240 manifests TEST oficiais, inclusive o instante de cada janela e o
  estado de ausência. Não reexecuta os detectores.
- A campanha, os IDs e os blocos vêm do
  `experiments/protocols/energy-powersaver-20261109/plan.json` e do resumo
  oficial `experiment_results/scientific-energy-powersaver-20261109/analysis/summary/manifest.json`.
  Os hashes das entradas consultadas estão em `processed/manifest.json`.
- `t` no CSV auditado é o **fim da janela** de 1 s. Para os gráficos, o
  segundo experimental é `t−1`, início do intervalo semiaberto `[t−1,t)`.
  Foram retidos `[30,390)`, ou seja, 360 segundos por execução e combinação.
  A região cinza corresponde ao calendário de emissão `[150,270)`.
- Para cada cenário, combinação e segundo, conta-se o número de decisões
  `True` e divide-se pelo número de decisões válidas (`True` ou `False`).
  Decisão ausente não seria convertida em `False` nem entraria no denominador.
  **Neste conjunto, todos os 20 valores são válidos** em cada segundo;
  `available_executions=20` e `missing_executions=0` em todas as linhas.
  Há 17.280 linhas no CSV temporal (3 cenários × 16 combinações × 360 s).
  O cenário L2 foi conservado nos dados processados e conferido contra a FPR
  oficial, mas não ganhou uma terceira figura.
- As quatro características são sempre requisições HTTP iniciadas, pacotes
  TCP ingressantes, soma de bytes de payload TCP ingressante e duração média
  HTTP. Cor e estilo de linha são fixos entre cenários e detectores. As
  proporções observadas por segundo são mostradas **sem suavização,
  interpolação ou bandas estatísticas**.

## Correspondência com as métricas oficiais

O algoritmo oficial está em
`analysis/detection/scientific/direct_metrics.py:metrics`.
Ele considera decisões válidas com disponibilidade até 390 s. Para recall,
uma janela deve estar **inteiramente contida no evento ofensivo real**, cujo
início e fim podem diferir por frações de segundo das fronteiras programadas.
Janelas de fronteira são excluídas do denominador. O script deste lote
reconstrói esses conjuntos apenas para **conferência** e verifica, nas 640
combinações execução × detector × característica dos cenários A3/F96, as
contagens de janelas e alarmes ACTIVE e POST, o recall e a proporção POST
registrados no resumo oficial. A FPR das 320 observações
combinação × execução de L2 foi também conferida com o controle oficial
`[30,390)`. Os 32 recalls e as 32 médias POST foram confrontados com
`tables/t53a_desempenho_detectores.csv`,
`processed/recalls_e_contrastes.csv` e
`tables/metricas_complementares.csv` do Lote 4; todos coincidiram.

O gráfico F5.3-C mostra os segundos **programados** `[30,390)`, incluindo
os segundos próximos de 150 e 270 que podem ser janelas de fronteira do
evento real. Portanto, a média da curva temporal durante o ACTIVE programado
não deve ser apresentada automaticamente como o recall oficial da T5.3-A
ou da F5.3-B. O arquivo `processed/alarmes_post_por_execucao.csv` conserva
`event_start_s`, `event_end_s`, os denominadores válidos e os numeradores
oficiais para permitir examinar essa diferença.

## POST e decisão editorial sobre F5.3-D

O resumo oficial de POST utiliza somente janelas que **começam após o fim
real** do evento ofensivo, com decisão válida. Por execução há 119 janelas
elegíveis em A3 e 118–119 em F96. `post_alarm_fraction` é calculada primeiro
por execução; `tables/alarmes_post_resumo.csv` usa a **média oficial entre as
20 execuções**, preservando os IC e o método oficial apenas como informação
complementar. A F5.3-D mostra esses 32 valores descritivos, arredondados a
uma casa decimal, em dois mapas com escala comum de 0% a 60%; ela **não
apresenta IC** nem realiza nova inferência.

A figura específica foi mantida porque a persistência não é uniforme nem
meramente residual: por exemplo, EWMA × duração HTTP apresenta 56,2% em A3
e 53,1% em F96, enquanto Z-Score × pacotes TCP apresenta 18,7% em A3 e
5,4% em F96. Esses padrões são difíceis de identificar exatamente nos quatro
painéis temporais superpostos, mas são compactos no mapa. A F5.3-D pode
integrar o corpo do capítulo se a discussão de persistência for central;
caso contrário, é candidata ao apêndice junto ao CSV. Os alarmes em POST
**não são rotulados como falsos positivos**.

Os gráficos temporais permitem comparar início, continuidade e redução da
proporção de execuções com alarme. Essa proporção não é a latência individual
oficial nem mostra quais execuções específicas alarmaram repetidamente. O
Lote 3 registrou operações computacionais remanescentes após 270 s. A
coincidência temporal entre filas, recursos e alarmes é descritiva e não
identifica uma causa única. O encerramento da emissão ofensiva programada
não encerra automaticamente operações ou requisições já iniciadas.

## Reprodução e validação

Da raiz do repositório:

```bash
.venv/bin/python -B reports/capitulo5_figuras/lote5_alarmes/scripts/build.py
```

O script lê apenas artefatos derivados e manifests existentes; não executa
campanhas nem detectores. Confere 60 execuções, 20 blocos, 16 combinações,
240 manifests TEST, decisões por segundo, limiares registrados, cobertura,
FPR L2, recall e POST por execução e as 32 médias oficiais de POST. Os PDFs
e PNGs foram inspecionados visualmente. As duas F5.3-C usam eixos `0–100%`
iguais; F5.3-D usa barra única compartilhada entre seus dois painéis.
