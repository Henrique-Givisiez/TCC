# Capítulo 5 — lote 1: caracterização exploratória

Três figuras descritivas para a Seção 5.1. Os dados vêm exclusivamente das etapas
exploratórias A2, B1 e B2. Nenhum dado da campanha definitiva
`scientific-energy-powersaver-20261109` foi empregado.

## Arquivos

| Figura | PDF para Overleaf | PNG para revisão | Base tabular |
|---|---|---|---|
| F5.1-B | `figures/F5.1-B_custo_endpoints.pdf` | `figures/F5.1-B_custo_endpoints.png` | `processed/f51b_endpoints.csv` |
| F5.1-D | `figures/F5.1-D_limite_geracao_flooding.pdf` | `figures/F5.1-D_limite_geracao_flooding.png` | `processed/f51d_flooding.csv` |
| F5.1-E | `figures/F5.1-E_atendimento_legitimo_combinado.pdf` | `figures/F5.1-E_atendimento_legitimo_combinado.png` | `processed/f51e_atendimento_combinado.csv` |

`processed/manifest.json` registra os hashes SHA256 dos nove artefatos de entrada,
do script da geração inicial e as verificações numéricas principais. Esta revisão
alterou somente apresentação: o manifesto e os CSV em `processed/` foram
preservados. O gerador atual confere seus dados e hashes antes de exportar as
figuras; por isso `script_sha256` no manifesto identifica a versão inicial,
não a revisão visual. Os CSV desta pasta são cópias
compactas dos indicadores usados nas figuras, criadas a partir das fontes listadas
abaixo. Não substituem os resultados originais.

## Fontes e definições

**F5.1-B — A2.** Fonte:
`reports/a2_endpoint_characterization_20261112/processed/summary.csv` e seu
`manifest.json`. M_A/M_B usam `/medium`; E_A/E_B usam `/expensive`. Janela `[0,60)`
s; 2×1 RPS nominais em cada execução; 101 inícios e 101 HTTP 200 por execução.
Cada ponto é a **média de CPU por operação dentro de uma execução**
(`cpu_worker_mean_ms`). No processamento A2, esta grandeza é a média de
`work_cpu_seconds × 1000` dos ciclos computacionais observados, medida no processo
worker (`reports/a2_endpoint_characterization_20261112/scripts/generate.py`,
linhas 47 e 163). A linha curta e seu rótulo são a média aritmética das duas
médias de execução do endpoint. Não é CPU Docker nem duração HTTP; não há IC.

**F5.1-D — B1.2.** Fonte:
`reports/b1_attack_characterization_20261112/processed/summary.csv`,
`inventario_execucoes.csv`, `manifest.json` e `relatorio.md`. F1–F5 são cinco execuções independentes de
flooding isolado, uma por taxa nominal, com duas fontes, `/medium` e concorrência
ofensiva configurada em 64. Janela `[30,60)` s. Painel A:
`rps_started = http_started / 30`; a linha tracejada é a identidade nominal =
iniciado. Painel B: `abandoned_admission`, confirmado igual a
`submitted − http_started` e `not_http_started` nas cinco linhas. O painel B mede
admissões expiradas **antes de abrir HTTP**, não timeouts de uma requisição
iniciada. `rps_finished_within` é preservado no CSV derivado para evitar confundir
início com conclusão; não é representado no gráfico. O painel não isola a causa
do limite observado nem fundamenta sozinho a concorrência 96.

**F5.1-E — B2.** Fontes:
`reports/b2_combined_characterization_20261112/inventario_execucoes.csv`,
`processed/phase_summary.csv`, `processed/summary.csv` e `manifest.json`.
Uma execução por condição: B2-L, B2-A, B2-F e B2-F96. Tráfego legítimo idêntico
na configuração: duas fontes, 16 RPS nominais agregados, `/medium`. ACTIVE
`[30,60)` s. Painel A: `success_median_ms`, mediana das durações HTTP das
requisições legítimas 2xx **iniciadas em ACTIVE**, com `n` igual a
`http_2xx_start_cohort`. É duração observada pelo cliente, condicionada ao
sucesso; exclui timeouts. Painel B: `http_2xx_start_cohort`,
`timeout_start_cohort` e `other_start_cohort`, cada um dividido por `started` da
mesma coorte. As três categorias são mutuamente exclusivas e totalizam os
inícios em cada execução. O script valida essa igualdade. As quatro linhas
apresentaram zero em “outros”. Resultados eventualmente concluídos depois de
ACTIVE permanecem na coorte do **início**. Essas proporções não são a métrica
operacional distinta de 2xx recebidos dentro do prazo da fase.

Em B2-F e B2-F96, a taxa ofensiva nominal foi igualmente 64 RPS; as
concorrências configuradas foram 64 e 96. O CSV derivado preserva
`rps_started_active` da classe `attack`, isto é,
`started_active / 30`: 54,1 e 49,9 RPS, respectivamente. Essas taxas são
discutidas no texto e não aparecem no rodapé da figura. A taxa com 96 foi
**menor**, enquanto os timeouts legítimos foram 416/514, contra 0/514 com
concorrência 64. Isso sustenta a *motivação exploratória informada pelo autor*
de investigar e selecionar a condição com maior degradação legítima observada;
uma execução por condição não demonstra superioridade geral nem efeito causal
isolado da concorrência.

## Reprodução

Na raiz do repositório:

```bash
.venv/bin/python -B reports/capitulo5_figuras/lote1_exploratoria/scripts/generate.py
```

O script lê os nove arquivos de entrada acima e escreve somente os seis PDF/PNG
desta pasta. Usa Matplotlib para exportar PDF vetorial e PNG a 240 dpi. Verifica IDs,
janelas, configurações de tráfego, denominadores e igualdades entre submissões,
inícios e expirações; compara os valores derivados com os CSV e o manifesto
preservados, sem regravá-los. Números experimentais são lidos dos CSV; o código contém
apenas identificadores esperados, definições de janela e constantes de estilo.

## Validação e uso editorial

- F5.1-B: quatro execuções e duas por endpoint; médias de execução de 28,82 e
  226,79 ms/operação. Recomendada para o corpo do capítulo, em formato compacto.
- F5.1-D: cinco intensidades; inícios de 30,7; 60,2; 66,8; 65,0; 63,1 RPS;
  expirações 0; 0; 1.438; 2.743; 3.725. Recomendada para o corpo do capítulo.
- F5.1-E: 2xx/timeouts legítimos em ACTIVE de 515/0 (B2-L), 43/471 (B2-A),
  514/0 (B2-F) e 98/416 (B2-F96). Recomendada como figura principal da seção;
  manter o painel de desfechos sempre que o painel de duração for utilizado.

As três etapas são exploratórias, em ambiente e cronologia próprios. As figuras
não estimam variabilidade entre execuções para B1/B2, não contêm intervalos de
confiança e não estabelecem causalidade isolada. Códigos internos são referências
secundárias; os rótulos principais usam nomes de condições e unidades explícitas.
