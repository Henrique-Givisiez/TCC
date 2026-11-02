# Comportamento temporal dos detectores — clock r2

Apresentação offline do TEST congelado. PDFs vetoriais e PNGs a 300 dpi. Sem seletores, preserva-se o pacote anterior de 12 figuras; seleções explícitas não geram D. As apresentações anteriores permanecem preservadas.

Seleção: features=['mean_duration_ms']; cenários=['M16', 'E16']; tipos=['temporal']. Temporal: [1, 2]; mapas: []; atraso: sempre suporte completo B01–B12, independentemente de --blocks.

| Figura / arquivos | Finalidade |
|---|---|
| [T_mean_duration_ms_M16_B01](figures/T_mean_duration_ms_M16_B01.pdf) · [PNG](figures/T_mean_duration_ms_M16_B01.png) | Detalhar a trajetória B01 |
| [T_mean_duration_ms_M16_B01_zoom](figures/T_mean_duration_ms_M16_B01_zoom.pdf) · [PNG](figures/T_mean_duration_ms_M16_B01_zoom.png) | Detalhar a trajetória B01 perto do limiar |
| [T_mean_duration_ms_M16_B02](figures/T_mean_duration_ms_M16_B02.pdf) · [PNG](figures/T_mean_duration_ms_M16_B02.png) | Detalhar a trajetória B02 |
| [T_mean_duration_ms_M16_B02_zoom](figures/T_mean_duration_ms_M16_B02_zoom.pdf) · [PNG](figures/T_mean_duration_ms_M16_B02_zoom.png) | Detalhar a trajetória B02 perto do limiar |
| [T_mean_duration_ms_E16_B01](figures/T_mean_duration_ms_E16_B01.pdf) · [PNG](figures/T_mean_duration_ms_E16_B01.png) | Detalhar a trajetória B01 |
| [T_mean_duration_ms_E16_B01_zoom](figures/T_mean_duration_ms_E16_B01_zoom.pdf) · [PNG](figures/T_mean_duration_ms_E16_B01_zoom.png) | Detalhar a trajetória B01 perto do limiar |
| [T_mean_duration_ms_E16_B02](figures/T_mean_duration_ms_E16_B02.pdf) · [PNG](figures/T_mean_duration_ms_E16_B02.png) | Detalhar a trajetória B02 |
| [T_mean_duration_ms_E16_B02_zoom](figures/T_mean_duration_ms_E16_B02_zoom.pdf) · [PNG](figures/T_mean_duration_ms_E16_B02_zoom.png) | Detalhar a trajetória B02 perto do limiar |

## Legendas sugeridas

**T_mean_duration_ms_M16_B01.** Duração HTTP, M16, B01. Duração inteira atribuída pela conclusão; inclui falhas com duração registrada. Observações oficiais de 1 s, escores e limiares congelados, pontos positivos na disponibilidade; CUSUM-freeze publica o candidato, com estado posterior secundário. Eixos próprios; sem suavização ou corte de picos.

**T_mean_duration_ms_M16_B01_zoom.** Duração HTTP, M16, B01. Duração inteira atribuída pela conclusão; inclui falhas com duração registrada. Observações oficiais de 1 s, escores e limiares congelados, pontos positivos na disponibilidade; CUSUM-freeze publica o candidato, com estado posterior secundário. Ampliação vertical explicitamente limitada; figura integral conserva todos os picos.

**T_mean_duration_ms_M16_B02.** Duração HTTP, M16, B02. Duração inteira atribuída pela conclusão; inclui falhas com duração registrada. Observações oficiais de 1 s, escores e limiares congelados, pontos positivos na disponibilidade; CUSUM-freeze publica o candidato, com estado posterior secundário. Eixos próprios; sem suavização ou corte de picos.

**T_mean_duration_ms_M16_B02_zoom.** Duração HTTP, M16, B02. Duração inteira atribuída pela conclusão; inclui falhas com duração registrada. Observações oficiais de 1 s, escores e limiares congelados, pontos positivos na disponibilidade; CUSUM-freeze publica o candidato, com estado posterior secundário. Ampliação vertical explicitamente limitada; figura integral conserva todos os picos.

**T_mean_duration_ms_E16_B01.** Duração HTTP, E16, B01. Duração inteira atribuída pela conclusão; inclui falhas com duração registrada. Observações oficiais de 1 s, escores e limiares congelados, pontos positivos na disponibilidade; CUSUM-freeze publica o candidato, com estado posterior secundário. Eixos próprios; sem suavização ou corte de picos.

**T_mean_duration_ms_E16_B01_zoom.** Duração HTTP, E16, B01. Duração inteira atribuída pela conclusão; inclui falhas com duração registrada. Observações oficiais de 1 s, escores e limiares congelados, pontos positivos na disponibilidade; CUSUM-freeze publica o candidato, com estado posterior secundário. Ampliação vertical explicitamente limitada; figura integral conserva todos os picos.

**T_mean_duration_ms_E16_B02.** Duração HTTP, E16, B02. Duração inteira atribuída pela conclusão; inclui falhas com duração registrada. Observações oficiais de 1 s, escores e limiares congelados, pontos positivos na disponibilidade; CUSUM-freeze publica o candidato, com estado posterior secundário. Eixos próprios; sem suavização ou corte de picos.

**T_mean_duration_ms_E16_B02_zoom.** Duração HTTP, E16, B02. Duração inteira atribuída pela conclusão; inclui falhas com duração registrada. Observações oficiais de 1 s, escores e limiares congelados, pontos positivos na disponibilidade; CUSUM-freeze publica o candidato, com estado posterior secundário. Ampliação vertical explicitamente limitada; figura integral conserva todos os picos.

## Escore, observação e estado

| Método | Escore efetivamente exibido e comparado | Escala / decisão |
|---|---|---|
| CoV | `score`: desvio padrão amostral / média das seis observações consecutivas, incluindo a atual; ddof=1. | Adimensional, sem multiplicar por 100; `score > h`. |
| Z-score | `score`: resíduo com sinal padronizado pela média e desvio padrão da baseline congelada. | Adimensional; cauda superior, `score > h`; não usa valor absoluto. |
| EWMA | `score`: EWMA dos resíduos padronizados, λ=0,2, estado inicial zero. | Adimensional; cauda superior, `score > h`; não é a feature em ms. |
| CUSUM-freeze | `candidate == score`: candidato da transição, max(0, estado anterior + resíduo − 0,5). | Adimensional; candidato > h sinaliza e rejeita a atualização; estado posterior preserva o anterior. |

As fórmulas descrevem o código: **não são executadas pelo gerador**. Limiares são transcritos de `run.calibration → thresholds`; o h do CUSUM-freeze também é conferido no componente da transição. Quando há séries ou mapas, valores exatos, candidato, estado anterior/posterior, observação, decisão e disponibilidade ficam em tables/temporal_records.csv. Os métodos não compartilham escala numérica.

`request_starts` conta tentativas de ambas as classes iniciadas na janela [i,i+1). `mean_duration_ms` usa a duração inteira das tentativas concluídas nessa janela, incluindo falhas com duração registrada e requisições iniciadas antes. Ausência de conclusão implica valor ausente, não zero.

CPU: média dos ticks registrados em cada janela, derivados de coleta/cache e referentes à vítima inteira; não é CPU instantânea, média temporal exata ou carga exclusivamente legítima. Pacotes ingress: registros source→proxy, incluindo payload zero e retransmissões. Payload TCP: soma do campo preservado; não são bytes físicos ou bytes HTTP únicos. Ausência de suporte de rede permanece ausente.

A observação ocupa [i,i+1); escores e pontos positivos das séries são desenhados em `available_at_seconds`, que neste TEST coincide com i+1. Incluem-se as observações [30,390), inclusive a última decisão disponível em 390 s. As células dos mapas ocupam a **janela observada**, não um segundo adicional de emissão ou uma duração do alarme. O estado posterior do CUSUM-freeze é interno e secundário: sozinho não representa a sinalização. Linhas entre escores ligam amostras de 1 s para leitura, sem suavizar nem criar novas observações.

Início/fim vêm do CSV de eventos vinculado por hash à avaliação e ao dataset; comando vem do recibo referenciado no checkpoint. O comando não substitui o fim certificado de emissão; E16 pode ter ambos quase sobrepostos. Valores exatos em tables/event_boundaries.csv quando há séries/mapas. Nas paradas programadas, o campo de comando é nulo: nenhum instante de comando é inferido a partir do fim da emissão. POST começa após o fim real e pode conter efeitos residuais.

## Uso no TCC e limitações

Corpo: D anterior como contexto, atraso condicional e mapas de request_starts M16/E16; selecionar as trajetórias relevantes à discussão. Apêndice: demais mapas, trajetórias integrais e ampliações de duração. Séries e mapas foram dimensionados em A4 retrato; atraso e D em paisagem. Usar PDF em página inteira para manter as fontes legíveis.

As ampliações de duração são adicionais, com limites verticais explícitos [-0,3h;3h] nos escores e contagem dos valores fora da vista em cada painel; as figuras integrais mantêm todos os picos. A observação mantém amplitude integral em ambas. Não há recorte silencioso.

CoV de request_starts mantém médias condicionais sem IC (6 detectados); CoV de duração M16 tem 0/12 e atraso não aplicável. O IC só existe com suporte previsto no protocolo (≥8 detecções). Misses são contados separadamente, nunca convertidos em atraso zero. Não há medida de latência computacional nem decomposição causal do atraso; disponibilidade é atribuída ao fechamento.

As séries consumidas preservam candidato e estado posterior. A disponibilidade examinada é registrada em tables/directed_checks.csv; o gerador preserva nulos e os mapas reservam cor própria à indisponibilidade. Não são criadas métricas de duração ou persistência de alarmes. Trajetórias individuais são ilustrativas; os mapas preservam os blocos selecionados e suas exposições. Os ICs são pontuais e condicionais ao treinamento congelado; não sustentam ranking global.

## Fontes e verificações dirigidas

Cadeia: checkpoint TEST autenticado por SHA256 exigido na CLI → summary → avaliações → runs e calibrações; checkpoint → recibos → dataset/features → observáveis e eventos. Identidades e hashes são conferidos para os arquivos consumidos. Código semântico é lido e comparado aos hashes do plano/run, sem importar o runtime científico. Não se repete a auditoria histórica da campanha, a calibração ou o processamento dos detectores.

Foram conferidas 16 séries de método selecionadas, grade de 360 janelas, disponibilidade, suporte publicado, vínculo observação/candidato, identidade score/candidato e preservação do estado em alarmes. A primeira disponibilidade publicada foi localizada em decisão positiva existente. Os arrays dos mapas são confrontados com as células renderizadas; os atrasos e ICs são transcritos diretamente, sem reaplicar limiar ou reconstruir trajetórias.

Conferências em tables/directed_checks.csv quando houver séries individuais/mapas; [fontes e hashes](tables/sources.csv), [proveniência e transformações](provenance.json), [comando de reprodução](reproduce.sh), Inspeção visual deve acompanhar cada seleção exportada. Para repetir no mesmo diretório, acrescentar `--overwrite`; sem essa opção o gerador recusa saídas existentes. Artefatos científicos e a apresentação anterior são protegidos inclusive com essa opção.

Pendências: escolha editorial final e incorporação ao texto do TCC. Nenhuma inconsistência de semântica foi encontrada nas evidências consumidas; não há correção científica proposta.
