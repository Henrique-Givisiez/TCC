# Fechamento da versão experimental antes da Stage 14B

A revisão humana aprovou Stage14A/14A.1 e autorizou um único commit local, sem push nem execução científica. Este fechamento preserva os protocolos, seeds, matriz e bindings históricos e resolve somente a proveniência pós-commit.

Protocolo v1: `79b204d7d781a939de7a95ab77b8e98ccbd15b5fe250fa237e0db1d0e7fa9e13`.

Protocolo v2: `59f5311e8ee0a05523c80938b7b08ddfaacd0bf8000a077c9de1ab675803872c`.

A v2 contém uma referência congelada ao lock histórico pré-commit. Substituir esse arquivo alteraria sua referência/hash e destruiria a evidência. O executor agora aceita uma referência operacional adicional `definitive_environment_lock`, mantendo **todas** as referências científicas e históricas originais. Não há mudança de protocolo, parâmetros ou desenho.

`experiments/stage14_finalize.py`, somente após o commit e com árvore clean, registra um lock novo e binding novo em `experiment_results/stage14-finalization/<HEAD>/`. O diretório já é ignorado pelo Git, evitando um segundo commit e permitindo registrar o HEAD realmente utilizado com status clean. Os artefatos anteriores continuam nos caminhos originais. O vínculo definitivo inclui o hash do binding histórico, lock histórico, protocolo v2 inalterado, seed plan/matriz originais e novo HEAD clean. O executor verifica os dois níveis de referências e aplica o lock novo na comparação operacional; não trata o antigo como definitivo.

A transição permitida pela rotina de fechamento é o novo HEAD e as mudanças de runtime estritamente nos módulos `experiments/stage14_scientific.py` e `experiments/stage14_finalize.py`, adicionadas neste fechamento. Outros desvios de software/imagens/ambiente falham. A versão definitiva exige Git clean também nos preflights futuros. O lock de exclusão mútua de execução foi movido para o diretório já ignorado `experiment_results/`, para que sua criação não suje a árvore.

O finalizador faz apenas seis preflights BASELINE, um por linha da matriz, e nunca chama o backend de simulação. Registra role, cenário B, seed, duração 240 s, configuração/hash, protocolo, lock, HEAD e ausência de output. TEST continua bloqueado. A CLI do runner deve receber explicitamente `--binding` apontando ao binding definitivo e seu `--binding-sha256`; o default histórico permanece disponível para auditoria e falha no novo HEAD por incompatibilidade de ambiente.

Nove testes adicionais verificam transição clean, novo HEAD, preservação das referências, rejeição de drift não aprovado, sobrescrita e tampering, exigência de clean nos preflights e proteção TEST. Todos usam fixtures/mocks sem simulação. O log da suíte completa e o estado pré-commit acompanham este documento. Artefatos de verificação/fechamento pós-commit ficam no diretório ignorado para preservar Git clean.

Esta documentação não autoriza Stage14B. Após o commit e os seis preflights, é necessária autorização humana para qualquer BASELINE. Não executar CALIBRATION/TEST nem fazer push.

A checagem adicional do conteúdo staged identificou CRLF no CSV histórico `docs/stage14a/matrix.csv`. Seus bytes/hashes foram preservados. `.gitattributes` registra `-text` e `cr-at-eol` exclusivamente para esse caminho, permitindo a verificação de whitespace sem normalizar/regravar a matriz. A tentativa inicial de `git diff --cached --check` e sua correção de metadados Git estão registradas na auditoria; nenhum parâmetro ou dado foi alterado.
