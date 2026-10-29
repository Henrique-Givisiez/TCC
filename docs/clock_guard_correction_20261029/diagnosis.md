# Correção prospectiva do diagnóstico e inspeção isolada

Nenhuma tentativa científica foi repetida. O plano, attempt/failure originais e dados permanecem intactos. [Registro por hashes](diagnosis.json) vincula os fontes anteriores arquivados, que coincidem com o freeze original, e os fontes corrigidos.

## Evidência medida

Inspeção1: [16 amostras originais](../clock-inspection-20261029T232344Z/inspection.json), quatro contêineres próprios sem rede. Confirmou zero offsets e inclusão no bracket, mas igualdade de namespace reprovada em todas. Inspeção2: [16 amostras com metadados do próprio processo host](../clock-inspection-20261029T232505Z/inspection.json). Quatro contêineres novos, também sem rede. Todos os oito foram removidos; nenhuma requisição HTTP, vítima ou experimento científico foi iniciado.

Host real: PID58047, namespace `time:[4026531834]`, namespace da thread e de filhos iguais; kernel7.0.0-38-generic e `clock_gettime(CLOCK_MONOTONIC)`. Contêineres: namespaces finais3450/3511/3572/3633. Dentro de cada contêiner, PID1, helper exec, thread e namespace de filhos coincidem. O identificador de namespace não era tomado de um processo aleatório: é realmente diferente do host. Acesso host aos links de namespace de PIDs externos foi negado; essa limitação está registrada, sem presumir leitura bem-sucedida. Os arquivos de offsets desses PIDs foram legíveis.

| Fonte temporária | Bracket observado, ms (mín–máx) | Interseção dos intervalos de offset admissível, ms |
|---|---:|---:|
|0|42,66–56,26|[−4,206;38,455]|
|1|47,25–50,72|[−4,198;42,895]|
|2|48,35–54,67|[−4,396;43,292]|
|3|44,13–54,39|[−3,972;39,662]|

As16 amostras estão dentro dos brackets. Esses intervalos descrevem incerteza de medição via exec, não offsets estimados nem prova isolada de sincronismo. Todos os arquivos `/proc/.../timens_offsets` observados declaram exatamente0 s/0 ns para monotonic e boottime. O mesmo kernel local e a implementação CLOCK_MONOTONIC, junto dos offsets zero e da identidade de namespace dos processos dentro do contêiner, sustentam origem temporal comum. Namespace distinto não implica relógio deslocado. Não há evidência de falha causada por latência nem razão para ampliar tolerância.

## Correção mínima implementada

`validate_clocks` persiste a origem e cada amostra antes de verificar/reprovar: host_before/after, epoch host após leitura, saída remota, PID, namespaces efetivos/thread/filhos/init, offsets disponíveis, kernel/implementação, checks, largura e intervalo admissível; erros de exec/parsing também ficam registrados. O ramo rejeitado não perde mais as amostras.

Proteção: exigir bracket inalterado e **mesmo namespace OU prova explícita cumulativa** de offsets monotonic/boottime exatamente zero, mesmo kernel/implementação CLOCK_MONOTONIC e namespaces efetivos coerentes entre host/thread/filhos e fonte/helper/init/thread/filhos. Namespace diferente sozinho continua reprovado. Prova incompleta, offset não zero ou bracket incompatível reprova. Não introduzimos epsilon, conversão de horários ou compensação estimada. O ramo de namespace idêntico conserva a proteção anterior; o ramo adicional é sustentado pela inspeção e não generaliza a offsets não zero. O orquestrador já exige Engine Linux local nativo antes dessa etapa.

Recuperação reconhece especificamente uma falha de relógio pré-liberação com exit não zero, status incompleto, inventário sem run binding, sem comando de liberação e sem journal. Produz `PRE_RELEASE_CLOCK_FAILURE`, sem tentar atribuir o request_log inexistente a divergência de identidade. É diagnóstico bloqueante, fora dos códigos automaticamente elegíveis a substituição. A falha histórica ainda diz `IDENTITY_JOURNAL_MISMATCH` e não foi reescrita. Quaisquer sinais de liberação impedem esse atalho; aplica-se então a reconciliação normal.

## Validação e retomada

12 testes de clocks/fontes passaram;2 testes existentes de recuperação científica E16 e controle benigno real também passaram. Fixtures rejeitam offsets não zero mesmo dentro do bracket, namespace de init inconsistente, kernel/implementação diferentes, prova ausente e relógio fora do bracket. Confirmam persistência da amostra reprovada, quatro amostras aprovadas e classificação pré-liberação sem sobrescrever arquivos. Nenhuma fixture gera HTTP.

Para retomar prospectivamente: revisar a regra documentada e congelar novos hashes de `simulator/source_manager.py` e `experiments/scientific_collection.py`; criar sucessor do plano com vínculos de código/prontidão atualizados, preservando plano e tentativa consumida anteriores. O runner atual não possui migração automática de sua raiz vinculada ao hash antigo: o handoff deve ser explícito e validado, mantendo o slot/tentativa1 consumidos e impedindo nova execução automática. Não basta editar runtime_hashes no plano antigo ou apagar binding/attempt/failure.

Depois será necessária decisão separada sobre eventual substituição técnica, dentro do orçamento original. Esta tarefa não autoriza substituição, não publica release de BASELINE nem muda os gates estatísticos. Como os dois fontes alterados são executados no host, a correção não requer mudança de conteúdo da imagem das fontes; a prontidão futura deve continuar verificando a correspondência das imagens e do código. Não atualizar agora as autoridades históricas para fazer a validação antiga passar.
