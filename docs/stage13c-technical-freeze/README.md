# Etapa 13C — preparação técnica e congelamento do desenho

Esta etapa não executa a campanha, não calibra policies e não acrescenta detectores. O protocolo B aprovado está em `experiments/protocols/stage14_protocol.json`, com SHA256 dos bytes em `stage14_protocol.sha256`. O estado é `FROZEN_DESIGN_PENDING_RELEASE`: desenho congelado, mas ainda sem autorização técnica para analisar TEST.

## Fitting temporal e baseline agrupado

`fit_baseline` agora exige limites explícitos, comuns a todas as fontes:

```python
fit_baseline(sources, ZScore(), zscore_spec(), new_destination,
             fit_start_seconds=48, fit_end_seconds=240)
```

Ou intervalos individuais explícitos: `fit_intervals={run_id: (start, end), ...}`. Não combinar as duas formas. Cada fonte deve ter role `baseline`; duplicatas e representações incompatíveis são recusadas. No caminho vinculado à campanha, o intervalo deve coincidir com o congelado `[48,240)`.

Semântica: para F=[a,b) e W=[s,e), incluir W se e somente se **a ≤ s e e ≤ b**. Limites finitos, não negativos, alinhados à grade Stage 10, com b>a e dentro do horizonte da série. Não há seleção por valor/label nem ponderação por overlap. Não há cópia ou corte do dataset. [47,48) fica fora, [48,49) entra, [239,240) entra e [240,241) fica fora. Intervalo inválido/vazio/fora da série falha antes do fitter.

O novo `fitting_contract_version=2` registra `fit_selections` por fonte: limites, regra, horizonte completo e duração planejada quando disponível, índices selecionados, janelas candidatas/excluídas, observações válidas e nulls excluídos. `sources` conserva referências/hashes originais, feature/schema/Δ; `parameters` preserva μ, σ, ddof, suporte total e por run; `provenance` identifica código efetivo e componente. O horizonte completo permanece distinto do intervalo de fitting.

Z-score recebe as observações selecionadas de todos os benignos, exclui null explicitamente e calcula momentos agrupados com pesos iguais por observação e ddof=1. Não agrega médias/desvios dos runs. Suporte insuficiente ou variância zero continuam sendo erros explícitos. `missing=reject`, em outros fitters, verifica somente a seleção efetivamente utilizada. Não há imputação. Nenhum dado posterior a b influencia o ajuste.

A seleção não atesta completude física: uma média Stage 10 pode ter suporte parcial e o dataset preserva essa limitação. Não inferimos cobertura completa nem criamos pesos temporais. Warm-up físico excluído por desenho não é warm-up algorítmico; o CoV continua sem fitting estático e conserva suas indisponibilidades.

A API antiga sem intervalo passa a falhar deliberadamente. Scripts históricos `pilot_stage13/analyze.py` e `analysis/detection/validate_stage12a.py` não foram modificados nem reexecutados: para reexecução futura, seus chamadores precisam declarar intervalos. Artefatos históricos permanecem legíveis e intactos; a nova obrigação aplica-se a novos ajustes. Isso é a extensão solicitada do contrato de fitting, sem mudança na Etapa 10.

## Ground truth original e event-level

Somente `analysis/detection/evaluation/events.py` carrega eventos. `load_event_truth(feature_dataset, score_source_reference, stage8_dataset=original_root)` segue o vínculo content-addressed da Etapa 10. A raiz Stage 8 é **localizador**, não autorização para fornecer CSV arbitrário: Stage 10 não armazena a localização absoluta do original. O loader verifica manifest Stage 10, evidência Stage 9 elegível, SHA256 e run ID do manifest Stage 8, hashes/tamanhos do status e eventos em ambos os manifests e âncoras temporais concordantes. Revalida depois da leitura. Caminhos usam a proteção de travessia/symlinks existente.

Os campos originais são `scheduled_start_seconds`/`scheduled_end_seconds` (expostos como planned), `actual_start_seconds`, `actual_end_seconds`, `drained_end_seconds`, `run_id`, `event_id` e `profile` diagnóstico. Cada marco de término é validado independentemente em relação a actual_start; **actual_end não precisa ser menor que drained_end**. Eventos sem limites efetivos completos são recusados, não reconstruídos. Benignos com tabela vazia retornam zero eventos.

`VerifiedEvents.verify()` relê o vínculo original e compara eventos/referências. `evaluate(..., event_truth=verified, event_policy=...)` persiste a referência verificada, policy e resultados event-level no evaluation artifact. `evaluate_events` aceita somente decisões persistidas/verificadas e verdade vinculada à mesma fonte. Detectores, fitters, calibradores e policies continuam recebendo apenas observações/parâmetros/scores, nunca esse envelope ou seus eventos.

Policy explícita: `global_overlap_and_availability_within_event_v1`. O evento primário é E=[actual_start,actual_end), incluindo silêncios de PeriodicBurst. Uma decisão é elegível se positiva e disponível, sua janela intercepta E com duração positiva e seu instante de disponibilidade pertence a **[actual_start,actual_end]**. O prazo final inclusivo permite contar a janela que fecha exatamente no fim do evento; não cria tolerância após o evento. Evidência completamente anterior, mesmo entregue depois, não conta. Não há persistência/hysteresis. Atribuição não reinicia estado do detector nos limites do evento.

Primeira detecção é o menor instante elegível. **delay=first_detection_available_time−actual_start**. Exemplos: início10.4, janela[10,11), decisão11 →0.6s; início10, mesma janela →1s. Falsos positivos anteriores não produzem delay negativo. Sem decisão elegível: detected=false, primeira detecção=null e delay=null; censura administrativa em actual_end. Não substituímos por zero/infinito/duração. O prazo explícito limita esta avaliação a reconhecimento durante o evento; reconhecimento tardio poderá ser análise separada, mediante outra policy.

## Window-level

`pure_window_groups` separa overlap=0 (benigno), overlap=1 (ataque) e 0<overlap<1 (boundary). Boundary não entra na métrica binária principal. O overlap contínuo fica preservado para análise complementar, sem arredondar nem adotar corte0.5. Não foram implementadas novas métricas ou inferência estatística. Na campanha, métricas principais também deverão restringir-se a janelas integralmente contidas no horizonte planejado, sem converter cauda/padding em normal comprovado.

## Protocolo B materializado

| Partição | Seeds | Cenários | Duração nominal por run | Runs |
|---|---:|---|---:|---:|
| BASELINE |6|B|240s; fitting[48,240)|6|
| CALIBRATION |12|B|360s|12|
| TEST |16|B/C/P pareados por seed|144s|48|
| Total |34 disjuntas| | |66|

FROZEN: /medium; containers, uma vítima e proxy NGINX; autoscaling desligado; 4 benignos×2RPS; 1 atacante×8RPS durante atividade; C contínuo36s; P burst2s/período6s/duty1/3; PRE48/ATTACK36/POST60; Δ1s; cinco features aprovadas; Z-score assinado/ddof1/baseline agrupado; CoV principalL6, L3/L12 somente sensibilidade; missing consecutivo; fitting[48,240); calibração exclusivamente benigna; política pure-window e evento global; isolamento de TEST. Total nominal da matriz:12672s=3.52h, sem executar nem projetar nova precisão estatística.

UNRESOLVED explícitos, cada um com status e value=null: thresholds numéricos, direções de decisão, orçamento operacional de falso positivo, detalhes de incerteza e lock exato de imagens/ambiente. Não há threshold científico implementado nem seleção por ataques. Os relatórios futuros devem acompanhar FPR/alarmes por tempo com exposição benigna, número de janelas/FP e incerteza apropriada, sem prometer “menos de um alarme/hora”.

As seeds ficam **DEFERRED**: ainda não são necessárias à infraestrutura e não existe TEST. O gerador puro usa namespace `stage14-balanced-v1-seeds`, SHA256(namespace:partition:index), primeiros32bits, rejeição de colisões e das seeds piloto101/211/307/401/503, em ordem baseline/calibration/test. Não consulta resultados. A materialização futura exige nova revisão versionada/hash, preservando o arquivo original; terá6/12/16 seeds disjuntas.

`validate_protocol` é o schema/validador executável do desenho aprovado, com campos obrigatórios e comparação estrita dos FROZEN. `load_protocol(expected_hash=...)` verifica bytes; `write_protocol` publica somente em arquivo novo, exige incremento sequencial e hash predecessor para revisão e recusa alterar a versão inicial aprovada sem nova versão. Mudança de desenho FROZEN exige também revisão explícita do validador; não há alteração silenciosa por configuração. O hash é externo ao JSON para evitar autorreferência. Referências consumidas devem sempre trazer hash esperado; não são assinatura criptográfica contra um agente malicioso com acesso irrestrito ao repositório.

`run_protocol_reference` fornece aos futuros run manifests protocol_id/version/hash, partição, seed e cenário, sem executar run ou abrir dados. `load_campaign_series`/`bind_source` vinculam séries à partição e protocol reference. Esse vínculo deve ser usado pelo futuro executor Stage14, que ainda não foi implementado nesta etapa; validar o cenário físico efetivo continua responsabilidade do pipeline de geração/validação.

## Isolamento de TEST

Qualquer `load_series(role='test')` falha **antes de abrir inputs**. Gates de referências e verificação de envelopes também recusam TEST em fitting, scoring, calibração, parameter selection e avaliação, inclusive replay de referências. Roles do envelope e referência devem concordar. Fitting aceita baseline e calibração aceita somente calibration. O caminho da campanha exige seeds materializadas e impede troca de partição; callbacks nunca recebem o envelope de campanha.

Nesta etapa não existe bypass de release: o desbloqueio final exigirá extensão revisada que vincule modelos, features, parâmetros e policies efetivamente congelados. Essa restrição conservadora permite preparar/gerar futuramente manifests de TEST sem abri-lo para análise. Fixtures e runs históricos são development, não TEST científico. Não é uma sandbox de segurança contra código Python deliberadamente malicioso ou relabeling externo; é proteção estrutural contra uso acidental pelos contratos.

## Validação e limites restantes

Testes em `tests/test_stage13c.py`: intervalos/boundaries/cauda/null/múltiplos runs e pesos, determinismo e mutação, ground truth original e hashes/run incorretos, prazo causal/delay/misses/silêncios, integração persistida scores→decisions→event evaluation com fakes, ausência de IO de truth antes de avaliação, valores obrigatórios do protocolo, seeds disjuntas, versionamento/hash, isolamento TEST e pure-window.

`historical_validation.json` registra leitura verificada de75 séries e15 vínculos de eventos do piloto. Para testar seleção em séries históricas de84s foi usado [24,60) explicitamente **como fixture de desenvolvimento**, sem fitting/modelos/scores/calibração; não substitui [48,240) futuro. A validação principal das novas regras é sintética, com contas manuais.

Pendências antes da análise científica: materializar seeds em nova versão; lock do ambiente; executar benignos e calibrar sem TEST; congelar directions/thresholds/policies e detalhes de reporting; implementar release auditável de TEST; integrar protocol reference ao executor futuro e aplicar horizonte planejado/denominadores na avaliação completa. Shannon e outros detectores continuam fora. Implementação correta não é evidência de eficácia contra LDoS.

O arquivo `audit.json` registra resultado final dos testes e comparação SHA256 dos17.968 arquivos de outputs existentes antes da alteração. Nenhum run Stage14 foi executado e nenhum commit foi feito.
