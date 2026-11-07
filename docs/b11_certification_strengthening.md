# B1.1 — Fortalecimento pontual da certificação

Referência: bd3c95988fefa6d58218d0128fc78df847000564; working tree inicial limpo.

## Janela programada

CONTINUOUS_SCHEDULED_START_WINDOW verifica os elapsed_seconds dos inícios HTTP
registrados contra scheduled_start_seconds <= início < scheduled_end_seconds.
Não usa actual_end_seconds nem limita o término das requisições.

Execuções futuras de fontes em contêineres declaram no run_status.json o campo
aditivo offensive_start_contract = scheduled-half-open-v1. O status exportado
já pertence ao manifesto com hash. Valores explicitamente desconhecidos falham.
Para datasets da Entrega 1 sem esse marcador, a presença de admission_id em uma
admission do journal ofensivo contínuo ativa a mesma verificação para todos os
inícios HTTP registrados daquela fonte, não apenas para os identificados.
Datasets sem ambas as evidências mantêm as verificações temporais históricas;
a certificação da janela programada não é afirmada nesses casos. Não é possível
reconhecer retroativamente o contrato de um dataset sem qualquer evidência dele.
Não houve reescrita de datasets ou mudança nos rótulos/fechamento efetivo.

## Reconciliação

identified_admission_errors agora associa abandoned_admission individualmente
por (source_id, admission_id). Exige abandono único para descarte, motivo igual
à decisão, event_id consistente e ausência de abandono para started. Abandonos
órfãos e duplicados são erros explícitos. Continuam obrigatórias resolução única
e correspondência individual dos starts. Journals sem IDs preservam os checks
históricos. Os gates de execução/drenagem incompleta permanecem inalterados.
O hash de source_aggregate.py passa a constar nas dependências do validador.

## Verificação

14 testes novos passaram em tests.test_offensive_certification, incluindo exportação
sintética, verificação de hashes e execução do validador real. Fronteiras S/E,
conclusão após E, compatibilidade histórica, identificação pelo journal e vínculos
individuais corrompidos foram cobertos.

Regressão: 146 testes em test_continuous_deadline, test_ground_truth,
test_attack_patterns, test_diagnostics, test_dataset_validation,
test_dataset_export e test_source_containers: 145 passaram, 1 falhou.
GroundTruthTests.test_e_tcpdump_timestamp_unknown_and_final_timeline apresentou
unknown/0 em vez de unknown/1; a mesma falha foi reproduzida isoladamente em uma
cópia temporária do commit de referência. Nenhuma correção fora do escopo.

Sem alterações de geradores, detectores, CSVs científicos ou política de expiração.
Sem Docker, campanhas, drenagem computacional, executor B1.2/B2 ou push.
