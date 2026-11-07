# B1.1 — Entrega 4: caracterização ofensiva offline

## Inspeção e escopo

Branch refactor/project-organization; HEAD inicial 99b35d1c325ed2dfa1a15bff97fe2a17bc7ecc4f.
O relatório reports/b11_storage_resume_20261107/report.md estava staged e foi preservado.
Inspecionados exploratory_analysis (restrito a A1/A2), summarize_diagnostics,
validate_dataset, export_dataset, diagnostics e dados do piloto. A restrição A1/A2
justifica um módulo de composição ofensiva; parsing, estatística e reconstrução
não foram duplicados: Reader/describe, validate_dataset,
identified_admission_errors e computational_state são reutilizados.

Implementados experiments/offensive_analysis.py e tests/test_offensive_analysis.py.
Coleta, formatos, políticas, geradores, detectores e calibração permanecem intactos.

## Utilização

```bash
.venv/bin/python -B -m experiments.offensive_analysis \
  --run experiment_results/b11-integrated-asymmetry-20261107-r1 \
  --output reports/b11_offensive_analysis_nova
```

Também aceita diretamente o diretório dataset exportado. A saída deve ser nova e
fora da árvore de entrada: nenhuma evidência é sobrescrita. Não há Docker ou rede
no analisador. Saídas: summary.json, report.md e timeseries.csv. O diretório
reports/b11_offensive_characterization_pilot_v1 contém a validação do piloto;
execuções preliminares de desenvolvimento usam diretórios separados, sem alterar
brutos. Não houve novo experimento.

## Entradas e integridade

Manifesto indexado e todos os arquivos conferidos por hash/tamanho; Reader registra
os hashes das entradas usadas. Paths inseguros e arquivos corrompidos são rejeitados.
O validador existente é executado, preservando checks e elegibilidade; nenhuma regra
é alterada. CSVs centrais de configuração/status/HTTP/CPU e inventário são necessários.
Diagnósticos e evidências auxiliares ausentes são registrados em missing_inputs e
limitações; não são substituídos por uma declaração de ausência de trabalho.

Certificado operacional final, quando disponível ao lado do dataset, é identificado
como evidência separada e só apresentado como vinculado se seu hash de manifesto e
run_id coincidirem. Um certificado ausente ou sem vínculo não é inventado a partir
do snapshot operacional exportado. Captura usa o resultado registrado em run_status
mais a verificação dos bytes; o analisador não recaptura nem reinterpreta o PCAP.

Admissões/resoluções são reconciliadas individualmente pelo helper existente.
Duplicações de operação/tipo e sequência descontínua do escritor são explicitadas.
IDs computacionais são associados aos IDs HTTP, com conferência de run/event/class.
Requisições sem submissão observada são listadas; timeout sem recebimento na vítima
não é automaticamente corrupção de dados.

## Indicadores e denominadores

Fases são derivadas da configuração efetiva registrada: pre=[0,S), attack=[S,E),
post=[E,T). Validador confere configuração e ground truth. Não se deduz E da última
resposta, da emissão efetiva ou de uma lacuna de eventos.

RPS ofensivo = número de inícios HTTP ofensivos em [S,E)/(E-S).
RPS legítimo = inícios legítimos em [0,T)/T. Diferença = realizado − nominal,
com nominal fontes × taxa/fonte. Também há contagens/durações por coorte de início
em cada fase e denominação explícita do intervalo. Conclusões de uma coorte podem
ocorrer depois de sua fase; não são substitutas dos inícios.

HTTP: starts_total, starts_in_window, completions, incomplete, status_codes,
outcomes, timeouts, connection_errors, duration_ms e última conclusão. Timeouts e
conexão usam o tipo de erro registrado, sem inferir causas não registradas.
Média/mediana/p95/máximo usam durações de conclusões conhecidas, inclusive resultados
adversos concluídos. Amostra vazia tem n=0 e estatísticas null. p95 usa posto mais
próximo ceil(0,95n). Incompletas não recebem duração zero. Ausência de erro não prova
que não houve degradação; a geração não é afirmada como Poisson homogêneo exato.

Computação por classe (benign/attack/unknown): eventos de submissão, início,
conclusão e falha; espera = início−submissão; duração = work_finished−work_started;
CPU/op = work_cpu_seconds. As distribuições usam somente operações com os eventos
necessários, com n próprio. Submissão recusada e falha de execução ficam distintas
nos eventos. Não se infere conclusão computacional por resposta HTTP.

Timeseries usa bins de eventos [t,t+1), preservando separadamente admissions,
submitted, task_started, http_starts, http_completions, expirações, work_submitted,
work_started, work_completed e work_failed. Há uma linha por segundo/classe.
Estados waiting/running/pending/completed são o limite esquerdo do término do bin,
não médias temporais. Bins finais são truncados em T. Eventos fora do horizonte
permanecem nas contagens/residual e nos dados originais, sem inventar bins de CPU.

Reconstrução reutiliza computational_state. Em E usa o limite esquerdo, coerente
com a divisão [S,E)/[E,T). Evento em E pertence ao pós-ataque. Pending=waiting+running;
falhas computacionais são estados terminais próprios, não sucesso. Transições
inconsistentes, perda de eventos ou fechamento ausente/incompleto produzem estado
unknown (contagens null). Contagens de eventos conhecidos continuam descritivas.

Residual: estados em E e no fechamento, conclusões em [E,horizonte], última conclusão
conhecida e diferença última−E (pode ser negativa se terminou antes de E).
Não se declara drenagem apenas porque pending observado chegou a zero: prova de
cobertura dos ingressos relevantes continua externa. Recuperação legítima não é
calculada. A interpretação global depende de victim_clock_validation.comparable,
metadata.run_id e origem monotônica registrada; sem esses vínculos, estados globais
e tempos residuais são unknown. O validador e hashes complementam a ancoragem, mas
não eliminam incerteza fina nas fronteiras nem demonstram deriva contínua nula.

CPU: ticks e coleta bruta têm cadências separadas; amostras por fase, mediana,
máximo e lista de gaps>1 s. Médias CPU/memória são médias das observações suportadas,
não médias temporais contínuas. Sem interpolação ou replicação para bins vazios.
CPU Docker pode exceder 100%; não corresponde ao percentual do pool de dois workers.

## Testes e validação real

16 testes determinísticos: zero HTTP, fronteiras S/E, conclusão HTTP tardia,
censura, residual computacional, pending no corte, observação incompleta,
duplicações, evento ausente, CPU esparsa, isolado/combinado, ausência de prova de
relógio, integração com dataset exportado sem diagnóstico e rejeição de hash alterado.
Suíte com validação/exportação/certificação ofensiva e diagnósticos: 134 testes OK.
git diff --check OK. A mediana reutilizada é p50; um erro inicial de alias no teste
foi corrigido antes da validação final.

Piloto confirmado diretamente nos artefatos:
- 62 conclusões HTTP, 62 inícios dentro de [30,60), nominal 2 RPS e realizado 2,066667.
- 62 operações computacionais correlacionadas, sem divergências de IDs.
- 2 operações em execução em E, nenhuma aguardando; 2 conclusões após E.
- Última conclusão computacional: 60,270368447 s, ou 270,368 ms após E.
- 10 operações de setup/sem classe são separadas das ofensivas.
- Snapshot íntegro, sem duplicação; estado final ofensivo pending=0.
- Dataset válido/elegível; certificado operacional vinculado e cleanup verificado.
- Ticks CPU: mediana ~5,035 s, máximo ~6,081 s. Coleta bruta: mediana ~3,014 s,
  máximo ~3,066 s. Bins de eventos de 1 s não representam CPU medida a cada segundo.

## Conclusão e limites

O analisador está preparado para caracterizar progressivamente os dois mecanismos,
isolados e combinados, desde que os artefatos centrais estejam disponíveis. Fixtures
cobrem ambos os tipos de composição; a validação real foi de baixa intensidade e
apenas assimetria. Não demonstra capacidade para intensidades altas nem substitui
uma validação futura com flooding. CPU esparsa, operações sem eventos suficientes,
censura e ausência de prova externa de ingressos limitam indicadores específicos,
sem alterar automaticamente a elegibilidade operacional do dataset.

Não houve novo experimento, alteração da coleta, seleção automática de intensidade,
ranking, detector, calibração, commit ou push nesta entrega.

## Revisão v2 — semântica, identidade, fronteiras e escala

A revisão em reports/b11_delivery4_review_20261107/report.md documenta cinco pontos.
Novos campos HTTP: attempts_started, attempts_ended_known, responses_received,
http_error_responses, attempts_without_observed_end, duration_observations,
known_end_duration_ms e response_duration_ms. completions/last_completion e
http_completions permanecem aliases históricos de tentativas encerradas, não de
respostas; status_codes e responses_received distinguem recebimento HTTP. Estatísticas
possuem n próprio; nenhuma duração é imputada a tentativas censuradas.

Classificação computacional usa evidências de todos os eventos da operação, sem
depender da ordem. Divergência de run/request/event/classe ou associação a requisição
inexistente é conflito; classe/identidade insuficiente permanece unknown. Uma única
requisição associada a múltiplas operações é apontada. Requisição sem submissão
observada pode não ter chegado; ciclos sem conclusão no horizonte não são erro por si.
Os campos conflicts, insufficient_evidence e partial_lifecycles são distintos.

state_before usa comparação estrita; state_at é inclusivo por padrão. state_at_E
continua alias do estado anterior a E, agora também denominado state_before_E;
state_after_events_at_E inclui eventos em E. final_state inclui eventos no corte.
O redutor compartilhado não mudou. A série aplica varredura incremental apenas
após validação das transições, com testes de paridade e contadores por segundo.
Benchmark reproduzível: tests/benchmark_offensive_analysis.py; comparações e saídas
finais do piloto preservadas no diretório da revisão. Nenhuma mudança na coleta.
