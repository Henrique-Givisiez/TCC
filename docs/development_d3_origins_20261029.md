# Preparação operacional D3_origins — DEVELOPMENT

Desenho aprovado, materializado sem executar Docker, preflight ou experimentos. Autoridade própria: [manifesto](../experiments/protocols/development_d3_origins_20261029/manifest.json). A [proposta histórica](../experiments/protocols/development_d3_origins_proposal_20261028/proposal.json) permanece como registro anterior à aprovação.

| Ordem | Entrada | Atacantes × RPS | Workers ofensivos | Seed |
|---:|---|---|---|---:|
| 1 | d3_origins_A_N1 | 1 × 8 | 64 | 10653172235677825147 |
| 2 | d3_origins_A_N2 | 2 × 4 | 32 + 32 | 10653172235677825147 |
| 3 | d3_origins_B_N2 | 2 × 4 | 32 + 32 | 853084928833962924 |
| 4 | d3_origins_B_N1 | 1 × 8 | 64 | 853084928833962924 |

Ataque contínuo em `/expensive`, 8 RPS agregados. Quatro clientes legítimos a 4 RPS em `/medium`, 16 RPS e 64 workers legítimos agregados. Uma vítima, autoscaling off, proxy estático, pool 2, timeout HTTP 2 s e monitoramento 1 s. Warmup 0–30, PRE 30–150, ACTIVE 150–270 e POST 270–390 s. ACTIVE tem expectativa nominal de 960 starts ofensivos: 960 por origem N1 e 480 por origem N2. Workers não multiplicam essa expectativa.

Duas seeds derivadas de SHA-256 de `development-d3-origins-20261029-v1:bloco:índice`, índice zero nos dois blocos, auditadas contra configurações, protocolos, reservas e resultados anteriores. O [inventário de seeds](../experiments/protocols/development_d3_origins_20261029/seed_audit.json) registra caminhos, hashes e valores. Mesma seed dentro do bloco não garante chegadas iguais quando a distribuição em fontes muda.

São quatro tentativas, sem retry/substituição ou progressão automática. Envelope de 72 minutos: 1560 s nominais, 120 s de drenagem, 240 s de repouso e 2400 s administrativos, 18 minutos por entrada. A criação de `attempt.json` consome a tentativa; falha não autoriza outra. Os adaptadores reutilizam a operação unitária existente, com diretório próprio `experiment_results/development-d3-origins-20261029/{raw,dataset,analysis,operations}` e paths individuais reservados no manifesto.

O primeiro preflight exige fechamento terminal de D3_cost vinculado por hash. Entre entradas, todas as revisões anteriores devem continuar válidas, e o hash da revisão imediatamente anterior deve ser selecionado explicitamente com `--reviewed-sha256`, tanto no preflight quanto na execução futura. São necessários cleanup verificado, pelo menos 60 s de repouso e preflight novo. A execução requer autorização específica da entrada; esta preparação não a concede. Integridade técnica, dataset, fechamento controlado, compatibilidade das referências e duas últimas janelas POST qualificadas condicionam progressão. Comprometimento ACTIVE tecnicamente válido, isoladamente, não bloqueia.

Os critérios, fases e referências são os de E8-R2: PRE próprio principal e C histórico hash-bound secundário. Os módulos históricos permanecem preservados. O adaptador de processamento adapta inventário e quotas ao número de origens, reconcilia todos os CSV/journals/fechamentos, confere certificados locais e reproduz o agregador de ground truth existente. O fim global de emissão depende do certificado da última origem, separado da drenagem de respostas. A avaliação de serviço e suas regras de exposição, suporte, prazo, duração, pendências e confirmação são reutilizadas integralmente.

A comparação publica N2−N1 dentro de cada bloco e B−A separadamente por condição. JSON inclui serviço legítimo PRE/ACTIVE/POST, recursos vítima/proxy, conexões, pendências, recuperação, taxas ofensivas agregadas e por origem, admissões, atraso disponível e amplitude das contagens entre origens. Markdown inclui taxas agregadas e por origem. Diferenças de carga observada acompanham os contrastes. Processos, sessões e divisão dos workers integram o efeito operacional; não atribuir tudo a IP isoladamente, nem presumir equivalência da agenda realizada. `full_scheduled_load_verified=false` permanece explícito.

A [validação offline](../experiments/protocols/development_d3_origins_20261029/offline_validation.json) registra o fluxo de quatro fixtures com exportação, revisão e comparação, duas origens com encerramentos distintos, quotas 32+32 e expectativas 480+480. Casos negativos rejeitam inventário incompleto, quotas alteradas, journal sem fechamento, fechamento global antecipado e revisão com identidade incorreta. O agregador de produção é exercitado com o certificado da segunda origem ausente e depois presente. Fixtures usam diretórios temporários e não ocupam os outputs operacionais.

Validação local:

```bash
.venv/bin/python -B -m experiments.development_d3_origins validate-plan
.venv/bin/python -B -m unittest tests.test_development_d3_origins -v
```

Primeiro preflight, preparado e ainda não executado:

```bash
.venv/bin/python -B -m experiments.development_d3_origins_ops preflight --entry d3_origins_A_N1
```

Após cada execução futuramente autorizada, revisar individualmente com `experiments.development_d3_origins review --entry ID`. Após as quatro revisões, `experiments.development_d3_origins compare` publica arquivos novos, sem sobrescrita. Pendência operacional: verificar prontidão real no primeiro preflight e obter autorização específica antes de gerar carga. Não há resultado empírico N1/N2 nesta preparação.
