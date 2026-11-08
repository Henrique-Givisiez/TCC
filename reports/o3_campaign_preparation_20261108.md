# O3 — Preparação final C1.3.5

## Resultado

Referência inicial `ec8e94c80f51b6d1091bd02c2d8f300115e41793`, árvore inicialmente limpa. Preparação concluída como **candidato para revisão final e autorização de execução**, sem iniciar qualquer tentativa científica e sem commit.

36 testes offline essenciais passaram em 9,005 s: `tests.test_o3_release`, `tests.test_o2_safety`, `tests.test_direct_campaign_operations`, `tests.test_c135_protocol`. Incluem release vinculado, preservação das regras, guards, backend de falhas, substituições, checkpoints e retomada. `git diff --check` passou. Não se repetiram pilotos; a validação integrada utilizada foi offline, apoiada nas execuções e testes anteriores.

## Docker e recursos

Daemon acessível, Docker 29.9.3/API 1.56. Nenhum contêiner em execução na consulta. Imagens originais presentes e IDs confirmados, sem rebuild:

- vítima `sha256:03a186aa90eec03b874c82a887b245e7190fa45cd7256af3c077cb64943d52b0`;
- fonte `sha256:b94212edd4d31c34998aea870caebc4ba145c1593d1b8dfdc27fe4917719fe3e`.

Disco disponível observado: 35.795.783.680 bytes (~33,34 GiB). RAM disponível: 10.963.533.824 bytes (~10,21 GiB), swap sem uso na consulta. Estes valores são uma observação, não reserva; preflight e guards continuam obrigatórios em cada tentativa. Não houve inicialização de contêiner nesta etapa.

## Plano e freeze

Diretório: `experiments/protocols/c135_final_20261108/`.

- `plan.json`: **83774ad310ed99216859eac40660d12fdb70f798e2bfda59bcb1b9f578cb62bc**.
- `configs/`: 80 configurações canônicas, cada qual com hash vinculado no plano.
- `seed_audit.json`: 7516 fontes históricas, com hashes e sementes; 40 grupos novos, sem colisões, sementes compartilhadas somente dentro dos blocos TEST previstos.
- `environment.json`: daemon/kernel/Python/pacotes/imagens, com hash vinculado no plano.
- `freeze_manifest.json`: inventário completo dos hashes runtime e vínculos de plano/ambiente/sementes; referência ao commit inicial e indicação de ausência de autorização de execução.
- `release_proposal.json`: revisão e autorização explícita pendentes.

`load_plan` e o comando público `validate` aprovaram o plano: BASELINE=4, CAL_A=8, CAL_B=8, TEST=60; máximo=82 tentativas. Ordem, configurações e dependências permanecem as do protocolo. `status` é somente leitura e permite confirmar que nenhum slot foi consumido. O result root planejado é `experiment_results/scientific-c135-final-20261108`.

Este freeze é por conteúdo: há mudanças não commitadas autorizadas nesta preparação. Qualquer alteração futura em runtime, configuração, imagem, ambiente ou inventário de sementes precisa nova revisão/atualização dos vínculos; não editar o plano após consumo de tentativa.

## Autoridade de liberação

Original preservado: `docs/scientific_protocol_direct_c135_20261108.json`, SHA256 `a4a5eb198be5e7ac770856e616af454c566993c6b1ef69edf0948bc9b3be1734`, com allowed=false.

Candidato O3 separado: `docs/scientific_protocol_direct_c135_o3_20261108.json`, SHA256 **c97f8ece0198af720af4781409c12332508b45073cb62234a2c105864bf28018**.

Somente a autoridade de execução muda no corpo specification: allowed=true, referência/hash da base imutável, revisão O3 e exigência de autorização explícita por comando. O validador aceita esse perfil somente se todos os outros campos forem exatamente iguais ao C1.3.5 original. Não há liberação genérica por editar uma flag. Os hashes do plano e do runtime continuam obrigatórios.

Alterações mínimas: `direct_contract.py` reconhece a autoridade O3 vinculada; `experiments/c135_o3.py` seleciona exclusivamente seu caminho/hash, reutilizando o controlador. O launcher anterior continua selecionando a especificação estrutural fechada. Os guards de slot, controlador, backend e entrypoint consultam a mesma SPEC herdada por ambiente. O perfil O3 é tecnicamente executável mediante o comando explícito abaixo; **não deve ser usado para coleta antes de revisão e autorização do usuário**.

## Comandos após revisão e autorização

Da raiz do repositório:

```bash
CMD=(.venv/bin/python -B -m experiments.c135_o3
     --plan experiments/protocols/c135_final_20261108/plan.json
     --plan-sha256 83774ad310ed99216859eac40660d12fdb70f798e2bfda59bcb1b9f578cb62bc)
"${CMD[@]}" validate
"${CMD[@]}" status
```

Iniciar ou retomar somente BASELINE, **após autorização explícita**:

```bash
"${CMD[@]}" run --partition BASELINE --authorize-partition BASELINE
```

Para continuar automaticamente CAL_A, CAL_B e TEST depois da BASELINE, somente se houver autorização para esse conjunto:

```bash
(
  set -euo pipefail
  for PART in CAL_A CAL_B TEST; do
    PREVIOUS=$(case "$PART" in CAL_A) printf BASELINE;; CAL_B) printf CAL_A;; TEST) printf CAL_B;; esac)
    HASH=$("${CMD[@]}" status | .venv/bin/python -c \
      'import json,sys; print(json.load(sys.stdin)["checkpoints"][sys.argv[1]]["manifest_sha256"])' "$PREVIOUS")
    "${CMD[@]}" run --partition "$PART" --authorize-partition "$PART" --checkpoint-sha256 "$HASH"
  done
)
```

Reexecutar o comando da mesma partição retoma pelos checkpoints/intents, sem repetir coleta consumida. Não usar loop de retry que ignore código não zero. Alternativa, com autorização explícita das quatro partições: `"${CMD[@]}" sequence --authorize-sequence ALL_PARTITIONS`; também retoma. Rodar em terminal persistente, manter logs externos e não mudar o checkout durante a campanha.

Misses, falsos alarmes, menor degradação e ausência de recuperação HTTP são preservados. Falha técnica não gera substituição automática. Os comandos existentes de aprovação por hash e attrition TEST exigem decisão separada; cleanup/preflight/identidade/hashes continuam bloqueantes.

## Capacidade e pendências

Nominal: 8 h 40 min; com duas tentativas extras, 8 h 53 min. Incluindo idle/preflight/exportação/análise, reservar aproximadamente um dia de janela operacional; 82 envelopes de 18 min correspondem a 24 h 36 min, sem garantir teto global das análises.

Extrapolação dos três pilotos para a composição científica: ~11,3 GiB para raw/dataset/features disponíveis, antes de candidatos, preflights e análises. Os 33,34 GiB livres dão margem ao perfil observado, mas não garantem o pior caso; guards de reserva e acompanhamento de disco devem permanecer ativos. Não excluir evidências para obter espaço.

Pendências impeditivas antes da primeira tentativa: revisão desta autoridade O3 e dos arquivos materializados; aprovação explícita do usuário; preflight real por tentativa. A disponibilidade futura de recursos não foi demonstrada por uma consulta pontual. Nenhuma autorização foi inferida de validate/status, e nenhuma tentativa foi iniciada.
