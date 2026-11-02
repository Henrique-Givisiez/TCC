# Comportamento temporal dos detectores — clock r2

O gerador foi ampliado com seleção pela CLI. Consulte [opções e comandos exatos](CLI.md). As figuras, tabelas e proveniência abaixo documentam a entrega original; não foram sobrescritas. A compatibilidade e as novas seleções estão em [verificações da ampliação](../scientific_reduced_clock_r2_temporal_cli_20261102/review.md).

Apresentação offline do TEST congelado. PDFs vetoriais e PNGs a 300 dpi. B01 é o menor bloco completo, escolhido sem consultar os resultados. A D original permanece preservada.

| Figura / arquivos | Finalidade |
|---|---|
| [T_request_starts_M16](figures/T_request_starts_M16.pdf) · [PNG](figures/T_request_starts_M16.png) | Detalhar a trajetória B01 |
| [H_request_starts_M16](figures/H_request_starts_M16.pdf) · [PNG](figures/H_request_starts_M16.png) | Comparar a sinalização entre B01–B12 |
| [T_request_starts_E16](figures/T_request_starts_E16.pdf) · [PNG](figures/T_request_starts_E16.png) | Detalhar a trajetória B01 |
| [H_request_starts_E16](figures/H_request_starts_E16.pdf) · [PNG](figures/H_request_starts_E16.png) | Comparar a sinalização entre B01–B12 |
| [T_mean_duration_ms_M16](figures/T_mean_duration_ms_M16.pdf) · [PNG](figures/T_mean_duration_ms_M16.png) | Detalhar a trajetória B01 |
| [T_mean_duration_ms_M16_zoom](figures/T_mean_duration_ms_M16_zoom.pdf) · [PNG](figures/T_mean_duration_ms_M16_zoom.png) | Detalhar a trajetória B01 perto do limiar |
| [H_mean_duration_ms_M16](figures/H_mean_duration_ms_M16.pdf) · [PNG](figures/H_mean_duration_ms_M16.png) | Comparar a sinalização entre B01–B12 |
| [T_mean_duration_ms_E16](figures/T_mean_duration_ms_E16.pdf) · [PNG](figures/T_mean_duration_ms_E16.png) | Detalhar a trajetória B01 |
| [T_mean_duration_ms_E16_zoom](figures/T_mean_duration_ms_E16_zoom.pdf) · [PNG](figures/T_mean_duration_ms_E16_zoom.png) | Detalhar a trajetória B01 perto do limiar |
| [H_mean_duration_ms_E16](figures/H_mean_duration_ms_E16.pdf) · [PNG](figures/H_mean_duration_ms_E16.png) | Comparar a sinalização entre B01–B12 |
| [L_conditional_delay](figures/L_conditional_delay.pdf) · [PNG](figures/L_conditional_delay.png) | Apresentar atraso e suporte dos quatro métodos |
| [D_context_revised](figures/D_context_revised.pdf) · [PNG](figures/D_context_revised.png) | Contextualizar carga, serviço e infraestrutura |

## Legendas sugeridas

**T_request_starts_M16.** Inícios HTTP, M16, B01 (menor bloco completo, seleção independente dos resultados). Observações oficiais de 1 s, escores e limiares congelados, pontos positivos na disponibilidade; CUSUM-freeze publica o candidato, com estado posterior secundário. Eixos próprios; sem suavização ou corte de picos.

**H_request_starts_M16.** Mapa de decisões persistidas de Inícios HTTP, M16. Colunas representam janelas observadas [i,i+1), com disponibilidade em i+1; cinza = indisponível, claro = negativa, cor do método = positiva. Limites reais por execução, sem realinhamento do fim. PRE e POST permanecem visíveis; POST não representa emissão.

**T_request_starts_E16.** Inícios HTTP, E16, B01 (menor bloco completo, seleção independente dos resultados). Observações oficiais de 1 s, escores e limiares congelados, pontos positivos na disponibilidade; CUSUM-freeze publica o candidato, com estado posterior secundário. Eixos próprios; sem suavização ou corte de picos.

**H_request_starts_E16.** Mapa de decisões persistidas de Inícios HTTP, E16. Colunas representam janelas observadas [i,i+1), com disponibilidade em i+1; cinza = indisponível, claro = negativa, cor do método = positiva. Limites reais por execução, sem realinhamento do fim. PRE e POST permanecem visíveis; POST não representa emissão.

**T_mean_duration_ms_M16.** Duração HTTP, M16, B01 (menor bloco completo, seleção independente dos resultados). Observações oficiais de 1 s, escores e limiares congelados, pontos positivos na disponibilidade; CUSUM-freeze publica o candidato, com estado posterior secundário. Eixos próprios; sem suavização ou corte de picos.

**T_mean_duration_ms_M16_zoom.** Duração HTTP, M16, B01 (menor bloco completo, seleção independente dos resultados). Observações oficiais de 1 s, escores e limiares congelados, pontos positivos na disponibilidade; CUSUM-freeze publica o candidato, com estado posterior secundário. Ampliação vertical explicitamente limitada; figura integral conserva todos os picos.

**H_mean_duration_ms_M16.** Mapa de decisões persistidas de Duração HTTP, M16. Colunas representam janelas observadas [i,i+1), com disponibilidade em i+1; cinza = indisponível, claro = negativa, cor do método = positiva. Limites reais por execução, sem realinhamento do fim. PRE e POST permanecem visíveis; POST não representa emissão.

**T_mean_duration_ms_E16.** Duração HTTP, E16, B01 (menor bloco completo, seleção independente dos resultados). Observações oficiais de 1 s, escores e limiares congelados, pontos positivos na disponibilidade; CUSUM-freeze publica o candidato, com estado posterior secundário. Eixos próprios; sem suavização ou corte de picos.

**T_mean_duration_ms_E16_zoom.** Duração HTTP, E16, B01 (menor bloco completo, seleção independente dos resultados). Observações oficiais de 1 s, escores e limiares congelados, pontos positivos na disponibilidade; CUSUM-freeze publica o candidato, com estado posterior secundário. Ampliação vertical explicitamente limitada; figura integral conserva todos os picos.

**H_mean_duration_ms_E16.** Mapa de decisões persistidas de Duração HTTP, E16. Colunas representam janelas observadas [i,i+1), com disponibilidade em i+1; cinza = indisponível, claro = negativa, cor do método = positiva. Limites reais por execução, sem realinhamento do fim. PRE e POST permanecem visíveis; POST não representa emissão.

**L_conditional_delay.** Médias condicionais e IC95% transcritos do summary TEST. Detectados/avaliados e misses explícitos. Losango vazio mantém média sem IC; ausência de detecção é não aplicável. A disponibilidade é atribuída ao fechamento da janela e não mede tempo computacional.

**D_context_revised.** Bloco B01: carga realizada e duração por conclusão em bins auxiliares de 5 s; CPU em ticks suportados da vítima inteira; pendências no cliente amostradas a 1 s. Emissão e comando reais. Duração auxiliar difere da feature oficial de 1 s e da coorte operacional por início. CPU não é instantânea. O exemplo não substitui as 12 execuções.

## Escore, observação e estado

| Método | Escore efetivamente exibido e comparado | Escala / decisão |
|---|---|---|
| CoV | `score`: desvio padrão amostral / média das seis observações consecutivas, incluindo a atual; ddof=1. | Adimensional, sem multiplicar por 100; `score > h`. |
| Z-score | `score`: resíduo com sinal padronizado pela média e desvio padrão da baseline congelada. | Adimensional; cauda superior, `score > h`; não usa valor absoluto. |
| EWMA | `score`: EWMA dos resíduos padronizados, λ=0,2, estado inicial zero. | Adimensional; cauda superior, `score > h`; não é a feature em ms. |
| CUSUM-freeze | `candidate == score`: candidato da transição, max(0, estado anterior + resíduo − 0,5). | Adimensional; candidato > h sinaliza e rejeita a atualização; estado posterior preserva o anterior. |

As fórmulas descrevem o código: **não são executadas pelo gerador**. Limiares são transcritos de `run.calibration → thresholds`; o h do CUSUM-freeze também é conferido no componente da transição. Valores exatos, candidato, estado anterior/posterior, observação, decisão e disponibilidade ficam em [temporal_records.csv](tables/temporal_records.csv). Os métodos não compartilham escala numérica.

`request_starts` conta tentativas de ambas as classes iniciadas na janela [i,i+1). `mean_duration_ms` usa a duração inteira das tentativas concluídas nessa janela, incluindo falhas e requisições iniciadas antes. Ausência de conclusão implica valor ausente, não zero.

A observação ocupa [i,i+1); escores e pontos positivos das séries são desenhados em `available_at_seconds`, que neste TEST coincide com i+1. Incluem-se as observações [30,390), inclusive a última decisão disponível em 390 s. As células dos mapas ocupam a **janela observada**, não um segundo adicional de emissão ou uma duração do alarme. O estado posterior do CUSUM-freeze é interno e secundário: sozinho não representa a sinalização. Linhas entre escores ligam amostras de 1 s para leitura, sem suavizar nem criar novas observações.

Início/fim vêm do CSV de eventos vinculado por hash à avaliação e ao dataset; comando vem do recibo referenciado no checkpoint. O comando não substitui o fim certificado de emissão; E16 pode ter ambos quase sobrepostos. Valores exatos em [event_boundaries.csv](tables/event_boundaries.csv). Nas paradas programadas, o campo de comando é nulo: nenhum instante de comando é inferido a partir do fim da emissão. POST começa após o fim real e pode conter efeitos residuais.

## Uso no TCC e limitações

Corpo: D revisada como contexto, atraso condicional e mapas de request_starts M16/E16; selecionar as trajetórias B01 relevantes à discussão. Apêndice: demais mapas, quatro trajetórias integrais e ampliações de duração. Séries e mapas foram dimensionados em A4 retrato; atraso e D em A4 paisagem. Usar PDF em página inteira para manter as fontes legíveis.

As ampliações de duração são adicionais, com limites verticais explícitos [-0,3h;3h] nos escores e contagem dos valores fora da vista em cada painel; as figuras integrais mantêm todos os picos. A observação mantém amplitude integral em ambas. Não há recorte silencioso.

CoV de request_starts mantém médias condicionais sem IC (6 detectados); CoV de duração M16 tem 0/12 e atraso não aplicável. O IC só existe com suporte previsto no protocolo (≥8 detecções). Misses são contados separadamente, nunca convertidos em atraso zero. Não há medida de latência computacional nem decomposição causal do atraso; disponibilidade é atribuída ao fechamento.

Todos os campos necessários ao escopo estão persistidos, inclusive candidato e estado posterior. Não há lacunas de decisão no horizonte examinado; o gerador preserva nulos e os mapas reservam cor própria à indisponibilidade. Não são criadas métricas de duração ou persistência de alarmes. B01 é ilustrativo; os mapas preservam as 12 execuções e suas exposições. Os ICs são pontuais e condicionais ao treinamento congelado; não sustentam ranking global.

## Fontes e verificações dirigidas

Cadeia: checkpoint TEST autenticado por SHA256 exigido na CLI → summary → avaliações → runs e calibrações; checkpoint → recibos → dataset/features → observáveis e eventos. Identidades e hashes são conferidos para os arquivos consumidos. Código semântico é lido e comparado aos hashes do plano/run, sem importar o runtime científico. Não se repete a auditoria histórica da campanha, a calibração ou o processamento dos detectores.

Foram conferidas 200 séries de método (50 combinações feature/execução; 48 ofensivas e duas C16 B01), grade de 360 janelas, disponibilidade, suporte publicado, vínculo observação/candidato, identidade score/candidato e preservação do estado em alarmes. A primeira disponibilidade publicada foi localizada em decisão positiva existente. Os arrays dos mapas são confrontados com as células renderizadas; os atrasos e ICs são transcritos diretamente, sem reaplicar limiar ou reconstruir trajetórias.

[Conferências](tables/directed_checks.csv), [fontes e hashes](tables/sources.csv), [proveniência e transformações](provenance.json), [comando de reprodução](reproduce.sh), [inspeção visual](visual_review.md). Para repetir no mesmo diretório, acrescentar `--overwrite`; sem essa opção o gerador recusa saídas existentes. Artefatos científicos e a apresentação anterior são protegidos inclusive com essa opção.

Pendências: escolha editorial final e incorporação ao texto do TCC. Nenhuma inconsistência de semântica foi encontrada nas evidências consumidas; não há correção científica proposta.
