# Seleção de figuras temporais — clock r2

Executar na raiz do repositório, com o ambiente `.venv` existente. O gerador só lê resultados congelados; não importa o runtime científico, executa detectores ou produz novas estimativas.

## Opções e padrões

Todos os seletores aceitam vários valores separados por espaço. `all`, usado sozinho, seleciona todos os valores da opção.

| Opção | Valores |
|---|---|
| `--features` | `request_starts`, `mean_duration_ms`, `mean_cpu_percent`, `ingress_packet_count`, `ingress_tcp_payload_length_sum_bytes`, ou `all` |
| `--scenarios` | `C16 M16 E16`, ou `all` |
| `--blocks` | Inteiros de `1` a `12`, ou `all`; linhas e arquivos seguem ordem numérica |
| `--plots` | `temporal heatmap delay`, ou `all` |

Sem nenhum desses quatro seletores, preserva-se o pacote anterior de **12 figuras**, com os mesmos nomes: séries B01 das duas features iniciais em M16/E16, ampliações de duração, mapas B01–B12, atraso combinado e D revisada. A leitura deixou de carregar uma série de controle/duração que não era usada em nenhuma figura. Os valores científicos apresentados permanecem os mesmos.

Ao informar qualquer seletor, ativa-se a seleção personalizada: só são produzidos os tipos escolhidos e D não é incluída. Opções omitidas assumem duas features (`request_starts mean_duration_ms`), cenários `M16 E16` e os três tipos. Se `--blocks` for omitido, séries usam B01 e mapas usam B01–B12. Séries de duração mantêm a ampliação adicional identificada, além da figura integral.

**Atraso sempre usa o resumo congelado dos 12 blocos.** `--blocks` afeta somente séries e mapas; quando a seleção parcial inclui `delay`, o gerador emite aviso e registra o suporte B01–B12 na figura, tabela, índice e proveniência. Nenhum agregado do subconjunto é calculado. C16 aparece como não aplicável, sem criar eventos avaliados ou misses zero. Combinações ofensivas sem detecção não recebem atraso zero; médias sem IC continuam visíveis.

Valores desconhecidos, bloco fora de 1–12, listas vazias, repetição de valores e mistura de `all` com outros valores são rejeitados antes da leitura dos artefatos. O checkpoint TEST exige `--checkpoint-sha256`; divergências de hash ou vínculos impedem a geração.

Saídas existentes são recusadas sem `--overwrite`. Com essa opção, o gerador substitui os arquivos anteriormente registrados em `provenance.json`, retirando figuras/tabelas de seleções anteriores desse mesmo diretório. Use diretórios diferentes para manter seleções lado a lado. A apresentação anterior não foi regenerada nesta alteração.

## Comandos exatos

A função abaixo fixa as autoridades da campanha. Copie-a uma vez no Bash, na raiz do repositório:

```bash
clockfig() {
  .venv/bin/python -B reports/scientific_reduced_clock_r2_temporal_20261102/generate.py \
    --repo . \
    --plan experiments/protocols/scientific_reduced_clock_r2_20261029/plan.json \
    --checkpoint experiment_results/scientific-reduced-clock-r2-20261029/checkpoints/TEST/manifest.json \
    --checkpoint-sha256 690c7d9af50204d7170fbb08ee61dd672450d2d5dd7e8c0a1de9725669601912 \
    "$@"
}
```

CPU em E16, bloco 1:

```bash
clockfig --features mean_cpu_percent --scenarios E16 --blocks 1 --plots temporal \
  --output reports/clock_r2_cpu_E16_B01
```

Duração HTTP em M16/E16, blocos 1 e 2, com ampliações adicionais:

```bash
clockfig --features mean_duration_ms --scenarios M16 E16 --blocks 1 2 --plots temporal \
  --output reports/clock_r2_duration_M16_E16_B01_B02
```

Mapas das cinco features nos 12 blocos, incluindo o controle:

```bash
clockfig --features all --scenarios all --blocks all --plots heatmap \
  --output reports/clock_r2_maps_all
```

Atraso agregado das cinco features, incluindo controle não aplicável:

```bash
clockfig --features all --scenarios all --plots delay \
  --output reports/clock_r2_delay_all
```

Todos os valores, tipos e blocos (inclui muitas páginas individuais):

```bash
clockfig --features all --scenarios all --blocks all --plots all \
  --output reports/clock_r2_all
```

Reprodução do pacote anterior em saída nova:

```bash
clockfig --output reports/clock_r2_default_compatibility
```

Acrescente `--overwrite` somente quando quiser substituir uma saída. O comando completo normalizado fica em `reproduce.sh` e `provenance.json` de cada seleção; sua execução deve partir da raiz do repositório.

## Convenções e arquivos

- Séries: `T_<feature>_<cenário>_Bnn.{pdf,png}`; duração também recebe `_zoom`.
- Mapas: `H_<feature>_<cenário>_<blocos>.{pdf,png}`. Uma faixa contígua vira `B01-B12`; seleções descontínuas usam, por exemplo, `B01_B03`.
- Atraso: `L_<feature>_<cenário>_B01-B12.{pdf,png}`. Uma figura por combinação evita páginas excessivamente densas.

Observações ocupam `[i,i+1)`; escores e alarmes das séries ficam em `available_at_seconds`. Mapas usam a janela observada, com disponibilidade em `i+1`, e preservam limites reais em cada linha. C16 não recebe fronteiras inventadas. Ausências são lacunas ou células indisponíveis. Escores não são suavizados nem normalizados; cada método conserva sua escala adimensional. CUSUM-freeze mostra o candidato que decide o alarme e o estado posterior como linha secundária.

CPU agrega ticks registrados derivados da coleta/cache e mede a vítima inteira, podendo exceder 100%; não é CPU instantânea. Duração é atribuída pela conclusão e inclui falhas com duração registrada. Pacotes e payload ingress usam as definições preservadas da captura source→proxy; bytes TCP não são bytes HTTP únicos ou bytes físicos no enlace.

O gerador parte do checkpoint autenticado e filtra referências antes de abrir avaliações e recibos; só abre os runs/features/datasets das combinações necessárias. Seleções apenas de atraso não leem recibos, avaliações individuais nem observáveis. `sources.csv` registra os arquivos efetivamente consumidos e seus hashes; `provenance.json` guarda seleção efetiva, versões, transformações e hashes de saída. As definições dos campos são conferidas no schema vinculado e no código cujo hash consta no plano/run. O código científico é lido, nunca importado ou executado.

PDFs são vetoriais com fontes incorporadas e PNGs têm 300 dpi. Séries e mapas usam A4 retrato; atraso personalizado usa página horizontal de 8,27 × 4,8 polegadas. A inspeção de novas seleções deve considerar seu tamanho final no TCC.

Verificações desta alteração e figuras inspecionadas: [entrega da CLI](../scientific_reduced_clock_r2_temporal_cli_20261102/review.md). Testes dos seletores:

```bash
.venv/bin/python -B reports/scientific_reduced_clock_r2_temporal_20261102/test_cli.py
```
