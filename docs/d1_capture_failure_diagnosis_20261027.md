# D1 — diagnóstico da captura em L04/B

**Estado:** diagnóstico e proposta somente. Nenhuma captura ou experimento foi iniciado para este documento. L04/B e os artefatos anteriores permanecem inalterados.

## Evidência relevante

O run foi iniciado em 32 RPS agregados e encerrou com `status=incomplete`. O motivo persistido em `run_status.json` é `capture: scientific CSV capture kernel drops or missing statistics`. A revisão [d1_L04_B-review.json](../experiment_results/development-d1-20261027/analysis/d1_L04_B-review.json) classifica o problema como técnico/de coleta; os critérios de serviço e gerador passaram. Os 3.875 starts úteis tiveram 3.875 respostas 2xx conhecidas, nenhuma falha/incompleta e p95 de 58,679 ms. Isso não torna o run elegível.

O `stderr` completo salvo em `raw/d1_L04_B/source_artifacts/traffic_capture.stderr` é:

```text
tcpdump: verbose output suppressed, use -v[v]... for full protocol decode
listening on br-7e2468afd861, link-type EN10MB (Ethernet), snapshot length 262144 bytes
21177 packets captured
21179 packets received by filter
2 packets dropped by kernel
```

`traffic_capture.csv` contém 21.177 linhas de dados. O PCAP tem 3.672.546 bytes e pode ser decodificado sem erro: a leitura offline encontrou 21.179 registros. O tamanho dos PCAPs aceitos de L03/A e L03/B é 1.763.676 e 1.735.864 bytes; ambos decodificam 9.804 e 9.588 registros, respectivamente. Nos dois, `stderr` informa que todos os pacotes recebidos pelo filtro foram capturados e zero foram descartados. Interface, filtro BPF e snapshot reportado são iguais nos três runs. O volume em L04/B é aproximadamente 2,1 vezes o de cada captura L03, compatível com a carga nominal dobrada, mas isso não identifica a causa dos descartes.

O teste de rede prévio selecionou a bridge `br-7e2468afd861` e o filtro:

```text
tcp and ((dst host 172.20.0.2 and dst port 80) or (src host 172.20.0.2 and src port 80))
```

O mesmo ponto e filtro aparecem nos audits de L03/A, L03/B e L04/B. Os quatro sources de L04/B fecharam normalmente, sem término forçado; o journal reconcilia com o CSV sem divergências. A coleta de serviço retornou 2xx em todas as requisições úteis. Essas evidências não indicam perda de rede ou falha de serviço.

## Comandos e ciclo de vida observados

Em [tcpdump_sniffer.py](../simulator/tcpdump_sniffer.py#L81), a captura científica que alimenta o CSV executa, em forma expandida:

```text
tcpdump --immediate-mode -i br-7e2468afd861 -l -n -tt -q 'tcp and ((dst host 172.20.0.2 and dst port 80) or (src host 172.20.0.2 and src port 80))'
```

Ela não especifica `-B`; `-l` controla o buffer de linhas na saída textual, não declara o tamanho do buffer de captura do kernel. A saída passa por pipe para um thread que interpreta cada linha e acrescenta uma linha CSV.

Separadamente, [capture_evidence.py](../simulator/capture_evidence.py#L8) executa:

```text
tcpdump --immediate-mode -U -i br-7e2468afd861 -n -w traffic_capture.pcap 'tcp and ((dst host 172.20.0.2 and dst port 80) or (src host 172.20.0.2 and src port 80))'
```

Também não especifica `-B`. `-U` pede flush dos pacotes para o arquivo; os dois processos usam o mesmo ponto e filtro, mas não compartilham uma captura nem um identificador que permita parear cada pacote.

Em [source_experiment.py](../simulator/source_experiment.py#L73), o sniffer CSV e depois o gravador PCAP iniciam antes da liberação dos sources. Ambos são verificados durante a execução. No encerramento, o código drena os sources, agrega os registros e só então chama `stop()` primeiro no PCAP e depois no sniffer CSV ([linhas 171–186](../simulator/source_experiment.py#L171)). Ambos usam `terminate()`/`wait()`; o sniffer CSV ainda drena o thread de leitura. O código não persiste timestamp de início/fim de cada captura. Portanto, a ordem relativa é conhecida, mas não há horário efetivo separado para o encerramento dos processos.

O critério implementado exige que o resumo do sniffer CSV contenha estatística de drops e que o número seja zero; caso contrário, marca o experimento incompleto. O erro observado veio exatamente desse critério.

## O que se pode concluir sobre os dois pacotes

- **Perda na captura:** confirmada para o processo da captura científica CSV pelo próprio contador do kernel (`2 packets dropped by kernel`). As 21.179 entradas decodificáveis no PCAP e as 21.177 linhas CSV são numericamente compatíveis com essa diferença. Como os processos de captura são independentes, não existe pareamento por ID; não é possível provar quais pacotes faltam em cada artefato.
- **Perda de rede:** não demonstrada. O contador de drops do `tcpdump` reporta perda da cópia entregue à captura; não é um contador de pacotes perdidos no caminho entre clientes, proxy e vítima.
- **Falha do serviço:** não observada neste run: as requisições úteis registradas terminaram em HTTP 2xx, com todos os starts reconciliados. Isso não reabilita a integridade da captura.
- **Causa dos drops:** indeterminada. O tamanho do buffer efetivo, ocupação, escalonamento, uso de CPU, escrita em disco e duração exata do encerramento não foram registrados. Não atribuir os drops a nenhum desses fatores.

Há também uma lacuna de preservação: `RawCapture` usa `traffic_capture.stderr` como diagnóstico do PCAP ([capture_evidence.py, linha 11](../simulator/capture_evidence.py#L11)); depois `source_experiment` grava nesse mesmo caminho o diagnóstico CSV ([linha 177](../simulator/source_experiment.py#L177)). Assim, o arquivo final preserva o `stderr` CSV e sobrescreve o `stderr` do PCAP. O `stop()` do PCAP verifica seus próprios contadores antes da sobrescrita, e a ausência de erro `raw_capture` em `run_status.errors` indica que essa verificação não falhou; contudo, os contadores originais do PCAP não ficaram disponíveis para auditoria independente.

## Correção recomendada

Manter interface, filtro, snapshot, modo textual e ciclo de início/fim atuais. Não afrouxar o critério de zero drops. Fazer uma alteração pequena e mensurável:

1. Acrescentar somente ao `TcpdumpSniffer` CSV uma solicitação explícita de buffer, inicialmente `-B 4096` (4.096 KiB), registrando o valor solicitado e o limite de buffer do host disponível no preflight. O valor efetivo atual não foi registrado, então não afirmar que 4.096 KiB é maior que ele. Isso trata a camada que reportou os drops; é uma mitigação a validar, não uma causa comprovada nem garantia de sucesso. Não mudar o buffer da captura PCAP sem evidência de que ela descartou pacotes.
2. Dar ao PCAP um caminho de diagnóstico próprio, por exemplo `traffic_capture.pcap.stderr`, preservando `traffic_capture.stderr` para o CSV. Persistir o início e o encerramento observados de cada captura em um sidecar pequeno, com horário UTC e elapsed monotônico, sem inferir o horário a partir do fim dos sources.
3. Manter a exigência de estatística de encerramento presente e zero para ambas as capturas. Se faltar estatística ou houver qualquer drop, registrar falha técnica e manter o run inelegível.

O buffer explícito não altera clientes, taxa, endpoint, vítima ou proxy; por isso, não muda a oferta experimental de serviço. Pode alterar a coleta e usar memória adicional para captura. Os artefatos de captura posteriores devem ser identificados como produzidos com essa versão de instrumentação; não os misturar como se tivessem as mesmas condições de captura dos runs anteriores. As métricas de requisição continuam comparáveis descritivamente, sob as limitações já registradas.

## Validação e retomada

1. Implementar a mudança separadamente, sem editar `d1_L04_B`, o manifesto original, a configuração ou seus hashes. Atualizar os testes do comando construído, caminhos distintos de `stderr`, persistência dos horários, parser dos contadores e classificação: zero passa; contador ausente ou positivo reprova.
2. Rodar validações offline com fixtures sintéticas e `py_compile`. Fazer apenas uma verificação operacional curta de prontidão/captura fora do experimento científico se ela não gerar tráfego de cenário. Não considerar isso evidência de capacidade a 32 RPS.
3. Preservar `d1_L04_B` como tentativa técnica malsucedida e criar uma entrada substituta versionada, com ID e caminhos raw/dataset/analysis/review/operations novos. Não reutilizar os caminhos existentes.
4. Recomendo manter para a substituição a seed B já reservada (`3803721254044484793`), com as mesmas quatro origens em `/medium`, 8 RPS por origem e 32 RPS agregados. Declarar `replacement_of=d1_L04_B`: a tentativa antiga não é uma repetição científica válida nem entra na comparação; apenas a substituição elegível representa B no par L04. A seed A permanece `2273943714116859802`.
5. Registrar a substituição em uma nova versão do protocolo/manifesto, apontando o hash do manifesto pai e justificando o run técnico adicional. O plano original tem teto de 10 entradas; substituir a tentativa e executar ainda L04/A e L05/A+B requer 11 tentativas no total. A nova versão deve resolver esse orçamento explicitamente (recomendo teto 11 para completar os pares planejados), sem reescrever o manifesto anterior nem modificar hashes como contorno de integridade.
6. A primeira execução após a correção deve ser somente a substituição B, antes de L04/A ou L05. Revisar sua execução, reconciliação e os dois `stderr`; só se todos os critérios atuais passarem, com zero drops em ambos, permitir L04/A. Depois, o par L04 A/B precisa passar antes de L05. Qualquer drop, estatística ausente, inconsistência ou resultado que exija interpretação interrompe novamente a progressão.

Não foram atualizados código, configuração, manifesto ou hashes nesta tarefa. O plano original, o run L04/B e as revisões anteriores permanecem preservados.
