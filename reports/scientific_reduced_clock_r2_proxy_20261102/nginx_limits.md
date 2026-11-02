# Aviso de limite de conexões — diagnóstico documental

Conferência somente offline dos 36 datasets vinculados ao checkpoint TEST, sem consultar limites atuais do host/container ou alterar a configuração histórica.

| Dimensão | Evidência e limite da interpretação |
|---|---|
| Configuração | Um worker e `worker_connections 4096`; keepalive upstream 32; retries off/uma tentativa; sem diretiva `worker_rlimit_nofile` nos arquivos preservados. Conferência por run em [nginx_limits_by_run.csv](tables/nginx_limits_by_run.csv). |
| Limite comprovado na inicialização | Logs `getrlimit(RLIMIT_NOFILE)` registram soft=[1024], hard=[524288]. O aviso compara 4096 com soft=1024. Trata-se do processo de inicialização do NGINX; não é leitura contínua de `/proc/<worker>/limits` ou do uso de FDs de cada worker. Sem diretiva de alteração, a herança é compatível com esse soft, mas a evidência não comprova o limite de cada worker durante toda a campanha. |
| Uso observado | Máximo amostrado de conexões ativas em [30,390): **92**. Esse gauge é de conexões de clientes do stub_status, inclui monitoring e não conta todos os descritores/upstreams. Não se divide seu valor por 1024/4096 para obter utilização de FDs ou capacidade. |
| Esgotamento explícito | 0 mensagens encontradas nos error logs e container outputs para os padrões documentados abaixo. Ausência de correspondência não comprova ausência de gargalo, picos, falhas não registradas ou limitação por outro recurso. |

Foram encontradas 72 linhas do aviso nos error logs (config test e inicialização podem emitir mensagens semelhantes); os container outputs contêm cópias/avisos adicionais e não devem ser somados como incidentes distintos. As linhas e posições preservadas estão em [nginx_documentary_lines.csv](tables/nginx_documentary_lines.csv). Há também mensagens de ciclo de vida; não são falhas HTTP.

A busca registrou `worker_connections [are] not enough`, `too many open files`, EMFILE/ENFILE, `cannot allocate memory`, `accept/accept4() ... failed` e `socket() ... failed`, com expressão exata no gerador. Outros erros/warnings explícitos são preservados no ledger documental. Os access logs mantêm status HTTP em seu ledger, mas status de erro por si só não identifica esgotamento de FDs.

`worker_connections` é um teto configurado de conexões do worker, abrangendo clientes e conexões com servidores upstream. Não equivale ao número de clientes atendíveis: sockets backend/keepalive, descritores de logs e outros usos competem com o limite de arquivos. Não existe nesta evidência uma série de FDs abertos, contagem completa dos sockets upstream, backlog, perdas antes do NGINX ou pico contínuo. O stub_status é amostrado aproximadamente a cada segundo e tem 119 falhas de parsing preservadas; o pico observado é apenas um valor registrado, não o pico real garantido.

A CPU observada e a busca sem mensagens explícitas não demonstram ausência de gargalo. Tampouco o aviso isolado demonstra saturação ou que o comprometimento do serviço foi causado pelo proxy. Não se estima capacidade máxima, overhead isolado de monitoramento ou efeito causal de configuração.
