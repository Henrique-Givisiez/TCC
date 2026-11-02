# Verificação da seleção pela CLI — clock r2

Ampliação offline em 02/11/2026 do [gerador existente](../scientific_reduced_clock_r2_temporal_20261102/generate.py). [Opções, padrões e comandos prontos](../scientific_reduced_clock_r2_temporal_20261102/CLI.md). As figuras e tabelas da apresentação anterior foram preservadas; sua proveniência documenta a versão anterior do gerador.

| Seleção exercitada | Figuras PDF + PNG | Séries feature/execução lidas | Arquivos consumidos | Índice |
|---|---:|---:|---:|---|
| CPU, E16, B01, temporal | 1 | 1 | 25 | [CPU](cpu/index.md) |
| Pacotes ingress, C16/E16, B01/B02, temporal e mapas | 6 | 4 | 49 | [Rede e controle](network/index.md) |
| Duração HTTP, M16/E16, B01/B02, temporal e ampliações | 8 | 4 | 49 | [Duração](duration/index.md) |
| Cinco features, C16/M16/E16, atraso congelado | 15 | 0 | 16 | [Atraso](delay/index.md) |
| Cinco features, C16/M16/E16, mapas B01–B12 | 15 | 180 | 669 | [Mapas completos](maps/index.md) |
| Payload TCP ingress, C16, B12, temporal e mapa de uma linha | 2 | 1 | 25 | [Bloco único](single/index.md) |
| Sem seletores: compatibilidade com pacote anterior | 12 | 49 | 272 | [Padrão anterior](legacy/index.md) |

São 47 figuras de seleções novas e 12 de compatibilidade. Cada seleção registra comando completo, fontes/hashes, versões, seleção efetiva e transformações. As tabelas são transcrições; não foram produzidos novos scores, decisões, limiares, ICs ou agregados científicos.

## Verificações dirigidas

- Sete testes automatizados dos seletores passaram, incluindo 14 casos de argumentos inválidos: nomes desconhecidos, blocos fora da faixa, listas vazias, repetição e mistura de `all` com valores específicos. A ordem dos blocos é numérica e os nomes distinguem conjuntos contíguos e descontínuos.
- A seleção apenas de atraso foi executada propositalmente com `--blocks 1`: emitiu aviso, permaneceu no suporte B01–B12 e não leu recibos, avaliações individuais ou observáveis. C16 tem detecções/avaliados e misses não aplicáveis, sem pontos em zero. A tabela transcreve o suporte de 12 runs preservado no summary, distinguindo-o de eventos avaliados.
- Foram comparadas 76 células de resumo de atraso (60 nas seleções novas e 16 no pacote padrão) com os campos congelados: média, mediana, limites, suporte, motivos de ausência de IC e misses. Nenhum intervalo foi calculado.
- Em CPU, rede, controle, duração e bloco único, 14.400 registros foram confrontados com score, candidato, estado, decisão, disponibilidade e limiar dos manifests referenciados. A numeração da janela seleciona o registro existente; nenhum detector ou comparador de decisão é reaplicado.
- A reprodução do pacote padrão manteve os nomes das 12 figuras. Seus 70.560 registros temporais consumidos são idênticos aos correspondentes da entrega anterior; contexto D e resumo de atraso mantêm os campos científicos anteriores. Deixou-se de ler apenas uma série C16/duração não usada nas figuras.
- Os 59 PDFs foram verificados: sem imagens raster internas, fontes TrueType incorporadas e texto dentro da página. Os 59 PNGs têm metadados de 300 dpi. Hashes de todas as saídas registradas correspondem à proveniência de cada seleção e ao gerador final.

Resultados estruturados: [verification.json](verification.json). A verificação pode ser repetida sem gerar scores ou figuras:

```bash
.venv/bin/python -B reports/scientific_reduced_clock_r2_temporal_cli_20261102/verify_exports.py
```

## Inspeção visual

As 47 figuras novas foram examinadas em folhas de contato proporcionais às páginas. CPU/E16/B01, payload/C16/B12, mapa com uma linha e os atrasos de duração/M16 e controle também foram examinados individualmente em tamanho de página. Um PDF de payload/C16 foi rasterizado apenas em `/tmp` para conferir a exportação vetorial, sem alterar os arquivos entregues.

As legendas distinguem observação e disponibilidade; limites ofensivos só aparecem quando há evento. Os mapas de uma, duas e doze linhas mantêm os blocos e as exposições reais. As cores dos métodos são as anteriores. CPU informa coleta/cache e vítima inteira; duração explicita conclusão e falhas com duração registrada; a rede conserva registros/payload em unidades próprias. O candidato CUSUM-freeze é a curva principal e o estado posterior é secundário. Picos permanecem integrais; ampliações de duração são identificadas e contam os valores fora da vista.

As figuras de atraso personalizado são horizontais, com suporte B01–B12 no título e valores numéricos ao lado dos pontos. ICs muito estreitos podem ficar visualmente pequenos, permanecendo legíveis nos rótulos. Médias sem IC usam losango vazio. C16 e ausência de detecção não recebem ponto em atraso zero.

Não foi encontrada inconsistência de semântica nas fontes consumidas. Não houve Docker, experimentos, calibração, execução de detectores ou alteração das regras de avaliação. Pendência apenas editorial: selecionar as páginas para o corpo/apêndice e manter o tamanho de leitura previsto na diagramação.
