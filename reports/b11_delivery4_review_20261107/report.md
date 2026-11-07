# B1.1 Entrega 4 — revisão dos cinco aspectos

## Estado inicial
Branch refactor/project-organization, HEAD 8f7efe39cdb6263de205023bee7d069d4439a01c.
Working tree inicialmente limpo. Sem coleta/Docker, alterações de datasets ou push.

## Diagnóstico e correções

| Aspecto | Resultado da auditoria | Tratamento |
|---|---|---|
| Encerramento HTTP | Ambiguidade confirmada: RequestLogger.finish registra end_elapsed_seconds também em transporte/timeout; não é recebimento de resposta | Campos separados para tentativas iniciadas/encerradas, respostas recebidas, respostas HTTP de erro e censuradas. Duração conhecida e duração das respostas com n próprios; aliases históricos documentados |
| Classe computacional | Dependência da primeira linha confirmada; real instrumento repete identidade, mas eventos conflitantes/parciais não eram seguros | Consenso dos identificadores declarados em todos os eventos; conflitos ou identidade insuficiente => unknown; correlação não inventa classe |
| Fronteiras | nextafter era correto para representar estado anterior em floats; fechamento usava avanço e recuo compensatórios pouco explícitos | Filtros < e <= no helper local; E−, E inclusivo e fechamento inclusivo separados. Redutor compartilhado intacto |
| Correlação | Falta de detecção de vários operation_id para um request_id confirmada, além de evidências parciais não distinguidas | Conflicts, insufficient_evidence e partial_lifecycles separados; órfãos, múltiplas operações, IDs HTTP duplicados e identidades divergentes identificados. Ausência de submissão HTTP não vira corrupção automaticamente |
| Desempenho | Gargalo medido nas revarreduras e sorts por segundo/classe | Contadores por bin e varredura incremental; o redutor existente continua validando transições antes dos snapshots |

## Arquivos
- experiments/offensive_analysis.py: semântica v2, classificação/correlação determinística, fronteiras explícitas, índices e snapshots.
- tests/test_offensive_analysis.py: 11 testes novos de revisão, além dos 16 existentes.
- tests/benchmark_offensive_analysis.py: fixture reproduzível sem Docker.
- docs/b11_delivery4.md: complemento de contrato.
- Este diretório: benchmarks, relatório e nova saída piloto_final; evidências anteriores preservadas.

## Validação
145 testes aprovados (27 do analisador e suítes de validação/exportação,
certificação ofensiva e diagnósticos). Nenhuma falha preexistente apareceu nesse
recorte; não foram corrigidos componentes externos. git diff --check aprovado.
Testes incluem respostas 200/503, timeout/conexão, censura, conflitos de classe/run/
event/request, múltiplas operações, identidade ausente, pendência válida, transições
ausentes, operação sem ID, fronteiras exatas S/E/fechamento e paridade do sweep com
o redutor. O esquema de coleta e o redutor compartilhado não foram alterados.

## Regressão do piloto

| Indicador | Antes | Depois |
|---|---:|---:|
| Inícios HTTP [S,E) | 62 | 62 |
| Operações correlacionadas | 62 | 62 |
| Executando antes de E | 2 | 2 |
| Conclusões computacionais após E | 2 | 2 |
| Última conclusão menos E (s) | 0.27036844699978246 | 0.27036844699978246 |

62 tentativas encerradas e 62 respostas recebidas; nenhum timeout ou erro no piloto.
Conflitos comprovados: []. As 10 operações de setup sem
identidade confiável permanecem unknown e aparecem como evidência insuficiente,
não corrupção. Dataset válido: True; elegível:
True; certificado vinculado:
True, status
completed.

## Desempenho

Fixture: 8000 requisições, 40001 eventos computacionais,
56000 registros de journal; 150 s representados e 450 linhas
segundo/classe. Volume corresponde aproximadamente a 256 RPS por 30 s.
Tempo anterior: 22.898 s; final: 0.492 s;
redução aproximada: 46.5 vezes.
RSS antes da chamada: VmRSS:	   87224 kB; após: VmRSS:	   93960 kB.
Pico de RSS do processo final: 113.55 MiB. Inclui fixture,
imports, temporários e analisador; não é apenas memória incremental da função.
As primeiras medições de ru_maxrss incluíram um pico de ambiente herdado e não
são usadas para afirmar redução de memória. Execuções únicas, sem garantia de
latência em qualquer host. Hashing/exported parsing não está incluído no benchmark
charaterize; integridade foi testada separadamente na execução offline real.

Reprodução: PYTHONPATH=. .venv/bin/python -B tests/benchmark_offensive_analysis.py CAMINHO_JSON_NOVO.
A referência anterior foi medida antes das alterações, usando a mesma fixture.

## Conclusão
A Entrega 4 pode ser encerrada para caracterização progressiva B1.2/B2: não foi
identificado impedimento técnico remanescente nesse escopo para milhares de
registros. A análise não certifica drenagem sem prova externa de ingressos,
nem recuperação legítima. Campos desconhecidos e ausência de eventos permanecem
explicitamente limitados. A cadência esparsa de CPU permanece pendência metodológica
separada antes da campanha definitiva. Nenhum novo experimento executado.
