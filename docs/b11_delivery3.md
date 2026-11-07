# B1.1 — Entrega 3: executor protegido

## Estado e arquitetura inspecionada

Branch refactor/project-organization; HEAD inicial
05f1534ef703c8c150c3b961cc6db7aa9cc741c8; working tree limpo.
Foram inspecionados diagnostic_run, dataset_run, source_experiment, modelos,
exploratory_operations, Dockerfiles, testes e evidências A1. A1 executou I1 com
imagens SHA imutáveis, fontes legítimas e encadeamento por certificado anterior.
Não foi criada outra implementação de coleta: continua diagnostic_run ->
run_recorded -> main_orchestrator -> source_experiment -> export -> certify.

## Configuração

Nova política exploratory-offensive-v1, com os mesmos campos numéricos da I1.
O CLI exige --composition legitimate, offensive ou combined nessa versão.
AttackConfig.mechanism aceita computational_asymmetry associado a /expensive e
http_request_flooding associado a /medium, sempre continuous. O campo vazio é
omitido na serialização histórica. A política nova exige mecanismo explícito,
fontes/taxa/duração ofensivas positivas, uma vítima com dois workers, topologia
direta, diagnóstico ON, fontes em contêineres e autoscaling desabilitado.

Somente legítimo: fontes positivas, sem fontes ofensivas; endpoint configurável.
Somente ofensivo: normal_traffic.clients=0, sem cliente legítimo artificial.
Combinado: fontes de ambos os grupos; legítimos obrigatoriamente em /medium.
Fontes desabilitadas não são criadas. Nenhum fallback ofensivo para / é aceito.
Zero fontes em ambos os grupos, composição divergente e janela inválida falham.
Não há teto nominal de 128 RPS; configurar não significa realizar essa taxa.

Templates em experiments/configs/protected_compositions/: cinco cenários
(legítimo, assimetria/flooding isolados e combinados), mais policy.json.
Todos duram 150 s, com ataque [30,60) quando habilitado. Legítimos: 2x8 RPS;
assimetria inicial: 2x1; flooding inicial: 2x16. São exemplos não executados,
não uma matriz definitiva. Fontes, taxa/fonte, concorrência, timeout, seed,
monitoramento, duração e janela continuam configuráveis nos modelos existentes.

Exemplo de invocação futura (NÃO executado):

```bash
.venv/bin/python -B -m experiments.diagnostic_run \
  --config experiments/configs/protected_compositions/pilot-offensive-http_request_flooding.json \
  --composition offensive \
  --operational-policy experiments/configs/protected_compositions/policy.json \
  --victim-image sha256:ID_COMPLETO_DA_VITIMA \
  --source-image sha256:ID_COMPLETO_DAS_FONTES \
  --output experiment_results/PILOTO/raw \
  --dataset-output experiment_results/PILOTO/dataset
```

## Preflight, attempt e imagens

Antes das fontes: validação, diretório raw.attempt novo (sem reutilização), preflight
operacional e inspeção de arquivos das imagens. attempt.json registra composição,
configuração com seed resolvida, hash, fases, política, IDs e hashes dos arquivos
embarcados. Preflight e attempt são copiados para raw e exportados com manifesto.
Falha de preflight conserva o attempt no diretório irmão; não cria run científico.
--previous-run continua verificando certificado final e hash do status anterior.

Apenas image.id não comprovava correspondência com o checkout. Agora o CLI compara
SHA256 dos arquivos /app das imagens com os arquivos atuais e verifica WorkingDir,
ENTRYPOINT/CMD relevantes. Usa contêineres PARADOS com rede desabilitada, nunca os
inicia, limita o arquivo de inspeção a 16 MiB e remove-os em finally. Resíduos têm
label edos.role=image_inspection e bloqueiam novo preflight. Falha de remoção inclui
ID no erro. Nenhum build/pull automático. I1 no CLI também recebe essa verificação:
configurações antigas continuam aceitas, mas imagens antigas precisam ser preparadas
novamente se seu código diferir do checkout; datasets anteriores não são alterados.
O caminho legado sem política continua exclusivamente legítimo, sem alegar proteção.

Para preparar imagens uma vez fora do executor, usar os Dockerfiles existentes:
Dockerfile da vítima e docker/Dockerfile.sources. Registrar IDs completos após o
build e fornecê-los ao executor protegido. Não foi realizado nenhum build nesta
entrega. A comparação cobre código/requirements embarcados e launcher; o ambiente
completo das dependências continua identificado pelo ID da imagem, não revalidado
arquivo a arquivo. Uma alteração no checkout após preflight é rejeitada antes da
invocação de run_recorded.

## Proteções e encerramento

Preservados RAM host, disco, memória por contêiner, OOM/restarts, tamanho dos
artefatos, aquisição/persistência recente de stats, timeout Docker e timer global.
O tempo do novo preflight é descontado do orçamento global do run. Os valores do
template são os da A1: 2 GiB disponíveis, 4 GiB disco, vítima 1 GiB, fonte 512 MiB,
artefatos 512 MiB, frescor 5 s, Docker 3 s, global 240 s. São limites observados,
não quotas impostas ao Docker. A coleta permanece com cadência efetiva dependente
de chamadas síncronas; não se afirma resolução CPU de 1 s.

CPU, fila/ocupação dos workers, latência, timeouts HTTP, erros HTTP, taxa realizada
inferior à nominal e ausência de recuperação não são gatilhos de parada. Sem
limitação nova de admissões, alteração de esperas, expiração ou contrato [S,E).

Ordem real preservada: parar/drenar fontes (30/35 s), agregar registros, fechar
capturas/stats, remover fontes, fechar observação computacional (até 3 s), remover
vítima (timeout Docker 5 s) e redes, verificar limpeza, persistir status final,
exportar e certificar. Não se espera o pool computacional ficar vazio. Resumo da
vítima ausente/incompleto é falha técnica explícita; pending>0 não é erro por si.
A ausência de ingressos tardios não é inferida do término do gerador.

A exportação final fica após a limpeza para incluir run_status definitivo e
resultado da limpeza. Exportar antes e depois sobrescrever status invalidaria os
hashes; não foi criado um segundo dataset provisório. Evidências são fechadas no
bind mount antes da remoção da vítima. O timer ativo é desarmado no finally antes
da limpeza, como no fluxo anterior; limpeza/exportação têm seus limites próprios,
sem afirmar que todo o teardown/export está coberto por um único deadline rígido.

## Certificação e evidências

I1 mantém seu certificado histórico. A política nova executa validate_dataset e
escreve dataset_validation.json antes de permitir progressão. Violações temporais,
perda de integridade ou falha de captura bloqueiam; não há calibração/detectores.
O certificado distingue completed_integral, completed_with_http_degradation,
operational_interruption e technical_failure. Ele não certifica recuperação nem
drenagem ofensiva. Gate de diagnóstico exige resumo íntegro, não pool vazio.

O relatório final inclui taxas nominais e RPS de inícios na janela apropriada por
grupo, contagens totais de inícios/conclusões e indicador de degradação HTTP. Logs
individuais/journals/diagnóstico continuam preservando submissões, filas e expirações.
O relatório pós-exportação vincula o manifesto por hash, conforme o fluxo histórico;
o snapshot operacional exportado não é reescrito para fingir conter o certificado
posterior. A configuração, inventários, ground truth, HTTP/RTT, PCAP/CSV, CPU,
diagnóstico computacional, preflight/attempt, proveniência e hashes são preservados.

## Testes e pendências

16 testes novos em test_protected_compositions: composições, mecanismos, falta de
fontes legítimas, erros de configuração, proteções, orçamento global, attempt sem
overwrite, código/launcher de imagem, rejeição de imagem antiga, gates de validação,
timeout HTTP válido, pendência computacional, integração preflight->run e templates.
Regressão ampla: 219 testes, 217 passaram. Permanecem as duas falhas previamente
reproduzidas: contexto temporal tcpdump e mock antigo de submit sem admission_id.
Depois da consulta adicional de resíduos, o mock de inventário em
 test_exploratory_certification foi adaptado à quarta consulta (sem enfraquecer a
asserção de não remover contêineres externos); 139 testes afetados passaram.
git diff --check passou. Testes de Docker usaram fakes; testes de vítima usaram
apenas pool/HTTP local de teste, sem campanha.

Piloto ainda deve validar imagens realmente preparadas, get_archive no Engine,
permissões tcpdump, certificados dos relógios, duração disponível, saturação IPC,
fechamento/exportação e condição do host. O aviso Python 3.12 sobre fork com threads
continua sendo limitação previamente registrada. Sem piloto não se afirma capacidade
para intensidades altas. Executor pronto para essa validação; B1.2/B2 e analisador
da Entrega 4 não foram executados/implementados. Nenhum push.
