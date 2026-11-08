# Auditoria F96 — 2026-11-08

## Diagnóstico e escopo

HEAD inicial `49921a297e88ab8e60789cc6cb36df9e1058c0e4`, branch `refactor/project-organization`, working tree inicialmente limpo. Nenhum AGENTS.md encontrado no projeto/pai. PILOT_ROOT não estava exportada no processo recebido; localização descoberta por busca e confirmada pelos contadores exatos: `/home/henrique-givisiez/tcc_c134_pilots_20261108_112324`. Todos os acessos aos pilotos foram de leitura. Nenhum piloto, campanha ou alteração de CPU/SO/especificação foi executado.

O F96 completou a duração nominal de 390 s; `end_reason=simulation_end`, produtores drenados e observação da vítima completa. A execução foi rejeitada no encerramento pela captura CSV. Não foi uma interrupção antecipada do tráfego. Os erros de cleanup/certificação repetem a falha da captura; não há evidência de uma segunda causa independente. `actions=[]`; certificação bloqueada, progressão proibida. A console registra a exceção correspondente; o código 1 foi informado pelo operador (não há registro independente do status do shell nesta auditoria).

## Comparação

| Piloto | Captura | Capturados | Recebidos pelo filtro | Descartes kernel | Retorno | Aceita |
|---|---|---:|---:|---:|---:|---|
| L2 | CSV | 32833 | 32833 | 0 | 0 | sim |
| L2 | PCAP | 32833 | 32833 | 0 | 0 | sim |
| A3 | CSV | 49743 | 49743 | 0 | 0 | sim |
| A3 | PCAP | 49743 | 49743 | 0 | 0 | sim |
| F96 | CSV | 78093 | 81288 | 3195 | 0 | não |
| F96 | PCAP | 81288 | 81288 | 0 | 0 | sim |

As contagens de linhas CSV coincidem com os capturados em cada piloto. Decodificação offline integral dos três PCAPs confirmou 32833/49743/81288 registros. O déficit CSV F96 corresponde a 3,93% dos recebidos. Os timestamps de duas capturas independentes diferem em microssegundos; não se deve fazer um join exato entre elas para localizar cada perda.

Comandos efetivos comuns aos três pilotos (caminhos de saída variam):

```
CSV: tcpdump --immediate-mode -B 4096 -i br-7e2468afd861 -l -n -tt -q 'tcp and ((dst host 172.20.0.2 and dst port 80) or (src host 172.20.0.2 and src port 80))'
PCAP: tcpdump --immediate-mode -U -i br-7e2468afd861 -n -w <piloto>/raw/source_artifacts/traffic_capture.pcap 'tcp and ((dst host 172.20.0.2 and dst port 80) or (src host 172.20.0.2 and src port 80))'
```

CSV solicita 4096 KiB. PCAP não especifica `-B`; o tamanho efetivo do buffer padrão não foi medido nem está registrado. Não presumimos que sejam iguais. Os stderr registram snapshot length 262144. Todos encerraram mediante SIGTERM solicitado, sem SIGKILL/launch_error, retorno 0. No F96 PCAP ficou pronto às 15:09:44.362722 UTC; SIGTERM 15:16:16.094187. CSV ficou pronto às 15:09:44.339630; SIGTERM 15:16:16.111314. A diferença de janelas não explica descartes reportados pelo kernel. Os detalhes completos, comandos e horários dos três pilotos estão em `pilot_comparison.json`.

## Hipóteses e evidências

A causa mais provável é insuficiente capacidade de drenagem do caminho textual/CSV durante rajadas ou pausas de escalonamento. O processo tcpdump pode ficar bloqueado na saída quando Python não consome o pipe com rapidez; seu buffer de captura então pode esgotar. O PCAP íntegro no mesmo segmento/BPF enfraquece a hipótese de perda generalizada da interface ou incapacidade global de gravação. Não isola sozinho Python de formatação tcpdump, buffering, escalonamento ou contenção.

Antes da correção, cada pacote abria, construía DictWriter, escrevia e fechava CSV. A mesma thread executa readline, regex, conversões, consulta da timeline sob lock e escrita, em série. O fechamento por pacote impede amortização do I/O. `--immediate-mode` e `-l` priorizam entrega imediata/por linha; `-U` no PCAP também tem custo. As capturas concorrem por CPU/I/O e têm buffers independentes. Nenhuma dessas opções foi alterada, evitando combinar intervenções.

Reprodução offline do leitor completo: 100000 linhas sintéticas idênticas por repetição, GroundTruth real com evento planejado, três repetições por versão, saída temporária no mesmo host. Antes: 2,697/2,703/2,629 s; depois: 1,320/1,315/1,382 s (medianas, aproximadamente 2,04 vezes mais rápido). Inclui parser/conversões/fechamento; exclui captura ao vivo, contenção real e finalização de contexto. Script e tempos anexos. Uma medição preliminar com mocks por pacote foi descartada por introduzir overhead na própria comparação. Este experimento sustenta reduzir o custo do escritor, não demonstra causalidade exclusiva nem resolução em produção.

Os 80 registros operacionais por piloto não mostram ação por falta de recursos. No F96 a memória disponível mínima foi 9.956.524.032 bytes, espaço livre mínimo 36.693.680.128 e artefatos máximos 128.939.858. Não há evidência de falta de capacidade de disco/memória. Não há perfil por processo do leitor/tcpdump, latência de disco, ocupação de pipe/ring ou instante dos descartes; CPU da vítima não mede CPU do capturador. Logo não se pode atribuir especificamente a CPU, I/O ou tamanho do buffer, nem excluir pausas transitórias entre amostras.

## Correção delimitada

Somente `simulator/tcpdump_sniffer.py`: a thread leitora passa a possuir um único arquivo/DictWriter, com buffering padrão limitado do Python. Consome stdout até EOF; o fechamento faz flush antes de terminar a thread. Abertura, leitura, escrita e fechamento estão no mesmo tratamento de exceções; `reader_error` continua propagado por check_running/stop. O stop verifica a drenagem antes de reabrir o CSV para finalizar a timeline, evitando corrida se o join exceder o prazo. Chamadas síncronas a `_write_row` preservam o comportamento anterior.

Campos, ordem, timestamps capturados, conversões e classificação temporal permanecem iguais. A timeline oficial é consultada novamente após drenagem dos produtores; nunca se usa o instante de escrita como timestamp do pacote. Não foram alterados PCAP, BPF, buffers tcpdump, detectores, features, protocolo ou critério de zero descartes. `capture_lifecycle.py` continua rejeitando descartes, estatísticas ausentes e saídas inválidas; `source_experiment.py` continua propagando falha para status/certificação. Um sidecar aceito certifica o processo tcpdump, não substitui a checagem de erros do escritor/status final.

## Testes e limites

17 testes focalizados passaram: `python -m unittest tests.test_tcpdump_writer tests.test_capture_lifecycle tests.test_source_containers`. Incluem 100000 registros, quantidade/ordem/campos, equivalência byte a byte com escrita síncrona, stop com drenagem, classificação após timeline final, falhas de abertura/leitura/escrita/fechamento, propagação ao stop e rejeição CSV/PCAP com descartes/estatísticas ausentes/retorno inválido.

A execução ampliada inicial teve 29 testes, 28 aprovados e uma falha preexistente: `tests.test_ground_truth.GroundTruthTests.test_e_tcpdump_timestamp_unknown_and_final_timeline`. A mesma falha foi reproduzida carregando o módulo original via `git show HEAD:simulator/tcpdump_sniffer.py`: chama stop sem iniciar processo, cujo retorno antecipado não finaliza contexto. Não foi alterado esse contrato fora do escopo; registro em `baseline_failure.log`. Um novo teste com finalização explícita confirma a timeline após fechamento do leitor. Não há alegação de suíte completa verde.

Riscos: o buffering amplia a cauda ainda não gravada em caso de morte abrupta do host/processo; flush normal não equivale a fsync/durabilidade em falha elétrica (também não existia antes). O prazo de drenagem continua 5 s e seu vencimento é erro explícito. Parsing textual e contenção permanecem; linhas não reconhecidas continuam com a política existente. Não houve aumento de buffer nem mudança arquitetural. O diagnóstico permanece provável, não uma prova de causa exclusiva.

## Validação recomendada (não executada)

1. Manter a tentativa original F96 inelegível e preservar seus arquivos/hashes. Criar diretório novo exclusivo, registrar commit/configuração/imagens e mesma política/configuração científica F96.
2. Executar uma única tentativa controlada autorizada, sem iniciar campanha. Não alterar simultaneamente CPU, BPF, buffers ou taxas; registrar condição do host e, se disponível sem interferência material, observação externa do capturador.
3. Exigir zero descartes em AMBAS as capturas, estatísticas completas, retornos válidos, ausência de erro do leitor, drenagem/cleanup completos e certificação aprovada.
4. Conferir contagem CSV, decodificação PCAP, janelas de captura, timestamps/ordem e classificação temporal, exportação/validação e contratos de features existentes. Contagens entre processos precisam considerar janelas diferentes, sem aceitar drops.
5. Se reaparecer perda, preservar a nova tentativa e medir CPU do capturador, bloqueio no pipe e latência de I/O antes de propor aumento de buffer ou arquitetura PCAP única com derivação offline. Essas mudanças exigem análise própria.

A correção está testada offline; o problema F96 só poderá ser considerado validado após essa execução controlada.
