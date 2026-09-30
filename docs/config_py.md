> Nota da Etapa 0: documentação histórica; algumas descrições são de versões anteriores. O núcleo atual está em `simulator/`, o entrypoint é `python3 -m simulator.main_orchestrator` (na raiz) e o injetor ativo é `simulator/traffic_injectorV0.py`. Consulte o [README](../README.md).

# Documentação: config.py

## Objetivo Principal

O arquivo `config.py` serve como um centro de configuração para toda a simulação de autoscaling. Ele permite ao usuário ajustar facilmente diversos parâmetros que controlam o comportamento da simulação, da aplicação alvo, do ataque de tráfego e da lógica do autoscaler, sem a necessidade de modificar o código principal dos outros módulos.

## Estrutura e Parâmetros

O arquivo define uma série de variáveis globais que são importadas e utilizadas pelos outros scripts da simulação.

### Configurações Gerais da Simulação
*   `SIMULATION_DURATION_SECONDS`: Duração total em segundos que a simulação principal (no `main_orchestrator.py`) deve rodar.
*   `SIMULATION_INTERVAL_SECONDS`: Intervalo em segundos entre cada ciclo de monitoramento e decisão do autoscaler.

### Configurações da Aplicação Alvo (Docker)
*   `TARGET_APP_IMAGE_NAME`: Nome da imagem Docker a ser usada para as instâncias da aplicação alvo (ex: `"edos_target_app"`).
*   `TARGET_APP_INTERNAL_PORT`: Porta na qual a aplicação dentro do contêiner escuta (ex: `80`).
*   `TARGET_APP_BASE_HOST_PORT`: Porta base no host Docker a ser usada para mapear a porta interna da primeira instância. As instâncias subsequentes terão portas incrementadas a partir deste valor (ex: `8080`).
*   `DOCKER_NETWORK_NAME`: Nome da rede Docker customizada a ser usada, permitindo que os contêineres se comuniquem e que o orquestrador os encontre (ex: `"edos_network"`).

### Configurações do Autoscaler
*   `CPU_THRESHOLD_SCALE_UP`: Limiar de percentual médio de CPU. Se o uso médio de CPU das instâncias ativas exceder este valor, uma ação de `SCALE_UP` será considerada.
*   `CPU_THRESHOLD_SCALE_DOWN`: Limiar de percentual médio de CPU. Se o uso médio de CPU cair abaixo deste valor (e o número de instâncias for maior que `MIN_INSTANCES`), uma ação de `SCALE_DOWN` será considerada.
*   `MIN_INSTANCES`: Número mínimo de instâncias da aplicação que devem estar sempre em execução.
*   `MAX_INSTANCES`: Número máximo de instâncias da aplicação que podem ser executadas simultaneamente.
*   `SCALE_COOLDOWN_SECONDS`: Período em segundos após uma ação de scaling (`SCALE_UP` ou `SCALE_DOWN`) durante o qual nenhuma outra ação de scaling será tomada. Isso previne oscilações rápidas.
*   `INSTANCES_TO_ADD_ON_SCALE_UP`: Quantas instâncias adicionar por vez quando uma decisão de `SCALE_UP` é tomada.
*   `INSTANCES_TO_REMOVE_ON_SCALE_DOWN`: Quantas instâncias remover por vez quando uma decisão de `SCALE_DOWN` é tomada.

### Configurações do Ataque de Tráfego (HTTP Flood)
*   `ATTACK_START_TIME_SECONDS`: Tempo em segundos desde o início da simulação após o qual o ataque de tráfego deve começar.
*   `ATTACK_DURATION_SECONDS`: Duração total em segundos do ataque de tráfego.
*   `HTTP_ATTACK_NUM_ATTACKERS`: Número de threads "atacantes" (workers) a serem usadas pelo `traffic_injector.py` para gerar carga.
*   `HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER`: Número de requisições HTTP GET por segundo que cada thread atacante tentará enviar.
*   `HTTP_REQUEST_TIMEOUT_SECONDS`: Timeout em segundos para cada requisição HTTP individual feita pelo injetor de tráfego.

### Configurações de Logging e Métricas
*   `METRICS_CSV_FILE`: Nome do arquivo CSV onde as métricas da simulação (tempo, número de instâncias, CPU média, decisão do autoscaler, nomes dos contêineres ativos) serão registradas.

## Como Usar

Antes de executar a simulação (`main_orchestrator.py`), o usuário deve revisar e ajustar os valores neste arquivo para definir o cenário de teste desejado. Por exemplo, para testar um scale-up mais agressivo, pode-se diminuir o `CPU_THRESHOLD_SCALE_UP` ou aumentar `INSTANCES_TO_ADD_ON_SCALE_UP`. Para simular uma aplicação mais "pesada" ou "leve", o comportamento da `app/simple_server.py` pode ser ajustado, e os parâmetros de ataque aqui podem ser configurados para sobrecarregá-la adequadamente.