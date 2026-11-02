# Inspeção visual e verificações da apresentação

Inspeção em 02/11/2026 das 12 figuras finais. As páginas foram examinadas em prévias proporcionais ao A4; atraso, contexto e uma trajetória também foram ampliados para conferir rótulos, unidades e notas. Ajustes concluídos: quebra do rótulo de contagem, títulos de ampliação em duas linhas e margem adicional nos eixos de atraso, para preservar pontos e barras próximos ao extremo direito.

| Figuras inspecionadas | Conferência visual |
|---|---|
| `T_request_starts_M16`, `T_request_starts_E16` | Cinco painéis; observação de 1 s; escores próprios; limiares e pontos positivos; candidato e estado posterior distinguíveis. |
| `T_mean_duration_ms_M16`, `T_mean_duration_ms_E16` | Amplitude integral, incluindo os picos E16; limiares presentes; ausência de detecção CoV M16 compatível com os registros. |
| `T_mean_duration_ms_M16_zoom`, `T_mean_duration_ms_E16_zoom` | Ampliações adicionais identificadas; contagens de valores fora da vista; observação permanece integral. O título não invade o painel anterior. |
| `H_request_starts_M16`, `H_request_starts_E16` | B01–B12 legíveis e em ordem; decisões negativas/positivas/indisponíveis definidas; limites por linha, sem realinhamento do fim. |
| `H_mean_duration_ms_M16`, `H_mean_duration_ms_E16` | Mesma convenção; emissão E16 e alarmes residuais POST distinguíveis pelas fronteiras reais. |
| `L_conditional_delay` | Quatro métodos, duas features, dois cenários; médias e ICs numéricos, suporte e misses legíveis. CoV/request_starts mantém losango sem IC. CoV/duração M16 aparece sem ponto em zero. ICs E16 de duração são muito estreitos na escala integral; seus valores também estão escritos ao lado dos pontos. |
| `D_context_revised` | Quatro linhas operacionais, três cenários, sem painel de alarmes; legendas e unidades legíveis em A4 paisagem. |

As figuras de séries e mapas destinam-se a página A4 retrato inteira. D e atraso usam A4 paisagem. A inspeção não pressupõe legibilidade ao reduzir todas a uma coluna estreita do TCC. Nos mapas, comando e fim real podem estar visualmente sobrepostos; os valores exatos permanecem na tabela de fronteiras. O comando está ausente nos recibos das paradas programadas e não foi inventado.

As verificações estruturais finais estão em [verification.json](verification.json): 12 PDFs sem imagens raster internas, fontes TrueType incorporadas, texto dentro das páginas e PNGs com metadados de 300 dpi. Os hashes das saídas e do gerador correspondem à proveniência. Os testes negativos confirmaram a recusa de checkpoint com SHA incorreto e de sobrescrita sem opção explícita.

A conferência dirigida do gerador cobriu 200 séries de método × 360 janelas, sem reproduzir detectores ou decisões. Foram comparados, adicionalmente, 3.030 valores auxiliares da D revisada com as tabelas da D anterior: carga, duração e pendências coincidem. CPU vem dos mesmos ticks nativos vinculados. As tabelas anteriores foram apenas lidas nesta verificação; a figura original foi preservada.

Não foi encontrada inconsistência de semântica no escopo consumido. Não houve execução de Docker, experimentos, calibração ou detectores; não houve recálculo de scores, decisões, limiares ou ICs. Pendência editorial: selecionar as figuras para o corpo e incorporar as legendas ao TCC, conforme o [índice](index.md).
