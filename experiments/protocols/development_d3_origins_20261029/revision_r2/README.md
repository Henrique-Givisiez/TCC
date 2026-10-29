# Correção de processamento D3_origins R2

A revisão original, manifesto, configurações, seed audit, raw, dataset e attempt de A_N1 permanecem preservados. A única alteração no código anteriormente vinculado é a validação do certificado em `experiments/development_d3_origins_processing.py`; os bytes anteriores foram arquivados em `source_before/development_d3_origins_processing.py`, com o hash exigido pelo manifesto original.

O certificado fixa identidade e todos os marcos de emissão. O CSV final deve coincidir integralmente com o último snapshot. Após o certificado, os snapshots só podem conservar esses invariantes e evoluir conforme o estado permitido; `emission_ended` exige drenagem nula, `completed` exige drenagem final consistente. São rejeitados certificados prematuros de conclusão, regressões, inconsistências de identidade/tempo e ausência de certificados. A drenagem final continua conferida contra os términos reais e o fechamento de cada origem. Regras de serviço não foram alteradas.

`manifest_r2.json` conserva condições, seeds, taxas, workers, quatro tentativas, zero retries, orçamento, ordem, raw/dataset e diretórios de operações. Apenas processamento e saídas analíticas/revisões/comparações recebem vínculos R2. Não existe novo orçamento nem tentativa para A_N1. O reprocessamento verifica o preflight e o attempt originais sob sua autoridade original, consultando os bytes arquivados para o código histórico alterado; a nova revisão registra separadamente o código efetivamente usado na análise R2.

A revisão corrigida é `experiment_results/development-d3-origins-20261029/analysis/d3_origins_A_N1-review-r2.json`, mesma execução `26c7db45b9c549a89673078c0712fc2a`. A revisão original reprovada não é sobrescrita. Os hashes de todos os 105 arquivos raw continuam iguais. A proveniência R2 vincula manifesto novo, revisão original, código de processamento e autoridade histórica de execução.

`handoff.json` vincula manifesto R2, revisão corrigida, run ID e tentativa consumida. O módulo prospectivo `experiments.development_d3_origins_revision_ops` valida esse vínculo antes de reutilizar as operações unitárias existentes. O gate exige seleção explícita da revisão correta, compatibilidade de referências, duas últimas janelas POST qualificadas, cleanup e repouso. O hash da revisão antiga reprovada, handoff alterado e retry de N1 são rejeitados. Um preflight futuro registra os hashes corrigidos, sem modificar o preflight original.

As quatro fixtures passam por exportação, revisão e comparação; N1 e N2 têm términos ofensivos posteriores ao fim da emissão e mantêm 960 starts agregados, 480 por origem N2 e quotas 32+32. Casos inválidos e controles anteriores permanecem exercitados. A validação está em `offline_validation.json`. O verificador de handoff é somente leitura: `PYTHONPATH=. .venv/bin/python -B experiments/protocols/development_d3_origins_20261029/revision_r2/verify_handoff.py`.

A revisão corrigida permite solicitar prontidão de A_N2. Ainda faltam prontidão real, seleção manual do hash e autorização específica antes de gerar carga. O aviso histórico de worktree não limpo continua registrado. Nenhum Docker, preflight real ou experimento foi executado nesta correção.

Próximo preflight preparado:

```bash
.venv/bin/python -B -m experiments.development_d3_origins_revision_ops preflight --entry d3_origins_A_N2 --reviewed-sha256 33e0da30446c7eb86a2697aff9a20af7aad0a5e4eb92e875a390e2fde706dc62
```
