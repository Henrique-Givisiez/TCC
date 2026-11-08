# C1.3.5 — Revisão prospectiva da matriz científica

## Decisão e comparação

Revisão anterior à campanha, motivada pela disponibilidade temporal insuficiente de CPU: L2/A3/F96 em [30,390): 78,89%/68,06%/40,00%; CoV potencial 109/62/65 de 360, devido às seis observações consecutivas. Não há solução simples demonstrada com garantias equivalentes de geração e disponibilidade. Não se afirma inadequação geral da CPU para detectar ataques nem melhora automática dos detectores; a seleção não usa resultados de detecção.

| Componente | C1.3.4 | C1.3.5 |
|---|---|---|
| Versão interna | 4 | 5 |
| Matriz principal | 4 métodos × 5 features | 4 métodos × 4 features |
| CPU | Candidata à detecção | Exclusivamente descritiva |
| Feature primária | service.request_starts | Preservada |
| Coleta/evidência CPU | victim-cpu-snapshots-v1 | Preservada integralmente |
| Cenários, 390 s, fases e seleção | L2/A3/F96; [30,390) | Idênticos |
| Estatística, calibração, eventos, métricas, IC | Fixados | Idênticos |
| Planejamento e substituições | 80 runs, máximo de tentativas existente | Idênticos |
| Liberação | Proibida | Continua proibida |

Matriz nova: network.ingress_packet_count, network.ingress_tcp_payload_length_sum_bytes, service.request_starts, service.mean_duration_ms; métodos zscore, cov, ewma, cusum-freeze. São 16 pares, com elegibilidade ainda individual por método × feature. Não se considera detector elegível pela existência de dados.

## Versionamento e arquivos

Anterior preservado byte a byte: `docs/scientific_protocol_direct_20261108.json`, SHA256 `be39b12ffcd09699da6311fb7a86ddab342dfba503e699b9df6833f9fed46303`.

Nova especificação: `docs/scientific_protocol_direct_c135_20261108.json`, SHA256 **`a4a5eb198be5e7ac770856e616af454c566993c6b1ef69edf0948bc9b3be1734`**, também registrado no arquivo `.sha256` correspondente. O parent aponta para C1.3.4 com hash. Não foi encontrado conflito de arquivo C1.3.5. O protocol_id da família foi mantido; versão e hash distinguem a revisão e impedem reutilização de plano antigo.

Inventário adicional:

- `analysis/detection/scientific/protocol.py`: FEATURES efetivas derivadas da especificação selecionada. Preserva o default histórico e a seleção explícita por SCIENTIFIC_SPEC_PATH + SCIENTIFIC_SPEC_SHA256.
- `direct_contract.py`: aceita versões 4/5 com inventários específicos e exige CPU descritiva na versão 5.
- `data.py`: rejeita feature fora da matriz antes de carregar evidências de calibração/detecção.
- `engine.py`: bloqueia fontes excluídas e chamadas diretas de trace, inclusive com fontes construídas pelo chamador.
- `tests/test_c135_protocol.py`: diferenças permitidas, preservação do parent e bloqueios em processo com C1.3.5 selecionado.
- Este relatório.

Nenhuma alteração no simulador, extrator, validador de datasets ou detectores genéricos. A revisão governa o fluxo científico selecionado; não proíbe análises genéricas externas feitas deliberadamente com outra autoridade.

## Dependências e preservação

Campanha, loader, engine e evaluation consomem o inventário FEATURES compartilhado. Isso reduz calibração, inventários CAL-B, decisões, resumos e exportação científica à matriz selecionada. Artefatos antigos permanecem vinculados ao caminho/hash anteriores; não são reclassificados ou reescritos.

O extrator continua produzindo mean_cpu_percent e cpu_quality, com nulls, rejeições, brackets e falhas. Coleta e validação continuam exigindo integridade das evidências e encerramento confirmado. Cobertura insuficiente de CPU limita sua descrição, mas não é suporte de baseline/decisão das quatro features principais. Erro fatal do worker, evidência adulterada/ausente ou captura com perda continua sendo falha técnica: CPU descritiva não dispensa esses controles. Nenhuma tolerância foi relaxada.

## Instrumentação operacional

`experiments/scientific_collection.py` instala `install_observer` antes da execução, sem ramo por cenário; a configuração completa de cada cenário passa pelo mesmo contrato operacional. São preservados StressManager, ProtectedCollector/SampleFreshness e Watcher. A sondagem efetiva e os checks de recursos continuam no fluxo científico.

O Watcher relê journals e grava observações, com potencial de interferência no desempenho. O F96 aprovado possuía esse observer; o D1.1 exploratório não. Portanto, D1.1 não demonstra equivalência de carga instrumental com a campanha. Não foi removido/otimizado nenhum observer. Não foi encontrada divergência de configuração da instrumentação entre os três cenários no fluxo científico comum; isto é verificação de código/configuração, não confirmação de três execuções futuras.

## Validação

**70 testes passaram em 9,826 s**:

```
.venv/bin/python -B -m unittest tests.test_c135_protocol \
  tests.test_direct_scientific_protocol tests.test_cpu_observations \
  tests.test_direct_campaign_operations tests.test_direct_scientific_evaluation
```

Incluem comparação integral dos campos preservados, inventário de quatro features, 80 slots, rejeição de CPU no loader/entrada de calibração, compatibilidade da versão anterior, exportação CPU/qualidade, corrupção/falta de evidência e preservação das outras famílias de features. `git diff --check` passou. Nenhum Docker, calibração ou experimento foi executado.

## Pendências de liberação

1. Revisão metodológica explícita desta alteração e confirmação de uso de C1.3.5.
2. Selecionar a nova especificação por caminho/hash, sem usar o default histórico por engano; não reaproveitar planos/calibrações da matriz de cinco features.
3. Freeze definitivo de código, imagens, ambiente e plano com auditoria de seeds, conforme os gates existentes. Os hashes de runtime mudaram e planos anteriores não devem ser reaproveitados.
4. Conferir no preflight das futuras execuções a instalação do observer e evidências efetivas de recursos nos três cenários.
5. Revisar tabelas/texto do TCC para separar os 16 pares principais da caracterização CPU e suas lacunas.
6. Autorização explícita de campanha após os controles existentes; esta especificação continua STRUCTURAL_ONLY_NOT_EXECUTION_RELEASED.

Nenhum commit criado, campanha liberada, artefato histórico modificado ou autorização de execução inferida.
