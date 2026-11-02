# Inspeção visual e conferências dirigidas

Entrega offline em 02/11/2026. Foram inspecionadas as duas figuras em prévias proporcionais ao A4 paisagem, com 1.403 pixels de largura, preservando proporções e posições das páginas. Eixos, unidades, títulos, legendas e notas permanecem legíveis em página inteira; não se recomenda reduzir a figura temporal a uma coluna estreita do TCC.

| Figura | Conferência visual |
|---|---|
| `P_proxy_temporal_B01` | Três cenários e quatro variáveis, escalas comuns por variável, pontos nativos e lacunas preservadas; CPU/memória/status claramente distintos; upstream legítimo e ofensivo por conclusão/log em bins de 5 s. C16 não recebe faixa de ataque nem valores ofensivos artificiais. Emissão real e comando E16 estão quase sobrepostos; seus tempos exatos ficam em `per_run_phase.csv` e `per_run_support.csv`. |
| `Q_proxy_individual_runs_phases` | Nove painéis, três fases; cada ponto representa uma execução, com cor de bloco e linhas entre cenários. As médias amostrais são rotuladas; upstream legítimo está em ms. A legenda B01–B12 e as definições de fase cabem na página. Não há barras inferenciais ou pooling de observações. |

Os PNGs finais são visualmente idênticos às prévias inspecionadas após os ajustes documentais finais. PDFs: elementos vetoriais, fontes TrueType incorporadas, nenhuma imagem raster interna e nenhum texto fora da página. PNGs: 300 dpi. Os hashes finais das figuras/tabelas/documentos registrados correspondem à proveniência.

Conferências documentadas em [verification.json](verification.json):

- 14.094 leituras nativas: as 119 falhas são `ValueError: invalid stub_status response`, todas com conexões ausentes; as 36 primeiras CPU sem delta permanecem vazias. Memória foi conferida como bytes / 2²⁰, sem remoção de cache.
- 277.194 linhas de access log: 223.656 requisições legítimas e 38.568 ofensivas, associadas por `(run_id, request_id)`, sem duplicatas; 14.094 monitoring, 36 setup e 840 capture_audit foram excluídas das estatísticas científicas. Todos os 262.224 tempos upstream científicos são escalares utilizáveis. Nenhuma consulta monitoring sem upstream virou duração zero.
- As 108 fases respeitam os limites operacionais congelados. Médias e contagens por fase correspondem às leituras/linhas atribuídas por seus timestamps próprios. Requisições não são transferidas para a fase de início do cliente. Os 432 bins ilustrativos preservam campos vazios quando não há tempos válidos; toda a classe ofensiva C16 permanece sem duração.
- Os 36 registros documentais de configuração/limites coincidem: um worker, 4096 worker_connections, keepalive upstream 32, retries off/uma tentativa, nenhuma diretiva worker_rlimit_nofile; soft/hard registrados na inicialização são 1024/524288. Máximo amostrado de conexões ativas em [30,390): 92. A busca documentada não encontrou mensagens explícitas de esgotamento.
- Seis testes unitários passaram: parsing escalar/listas/marcadores, fronteiras semiabertas, âncora epoch, unidades/médias amostrais, interrupção de linhas e suporte de bins. Testes sintéticos não executam detectores nem alteram dados da campanha.
- Cinco verificações da CLI passaram: SHA incorreto, saída existente sem opção explícita, bloco inválido, tentativa de gravar em raiz científica protegida e geração do bloco temporal B02 em diretório temporário. Esta última manteve B01–B12 na comparação e foi removida com a área temporária; não substituiu B01 da entrega. Ver [cli_checks.json](cli_checks.json).

Para repetir somente as conferências, na raiz do repositório:

```bash
.venv/bin/python -B reports/scientific_reduced_clock_r2_proxy_20261102/test_proxy.py
.venv/bin/python -B reports/scientific_reduced_clock_r2_proxy_20261102/verify_outputs.py
```

Nenhum experimento, Docker, calibração ou detector foi executado. A verificação se restringiu aos arquivos usados nesta apresentação; não repetiu a auditoria histórica de detecção. Não foram encontrados conflitos de semântica que exigissem correção dos artefatos. O comportamento observado não identifica causalidade, capacidade máxima, overhead de monitoramento, picos contínuos ou ocupação dos descritores do worker.
