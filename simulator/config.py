# edos_docker_simulation/config.py

# --- Configurações da Simulação ---
SIMULATION_DURATION_SECONDS = 180  # Total duration of the simulation
ATTACK_START_TIME_SECONDS = 20     # When the attack begins

# Duração TOTAL do ataque: uma única janela, sem repetição/pulsos.
# O ataque roda de ATTACK_START_TIME_SECONDS até ATTACK_START_TIME_SECONDS + PULSE_DURATION,
# uma vez só, e depois disso a simulação continua só com tráfego normal.
PULSE_DURATION = 140

# Liga/desliga o agendamento do ataque nesta simulação: 0 = nenhum ataque
# (tráfego normal o tempo todo, usado por --attack-duration 0). Qualquer valor
# > 0 habilita o ataque; o valor numérico em si não tem mais efeito sobre a
# duração do ataque (isso agora é controlado só por PULSE_DURATION acima).
ATTACK_DURATION_SECONDS = 90


# --- Configurações do Docker ---
DOCKER_IMAGE_NAME = "edos_target_app:latest" # Matches the image you built
BASE_CONTAINER_NAME = "target_instance"    # Base name for your containers (e.g., target_instance_1)
DOCKER_NETWORK_NAME = "edos_network"       # Matches the network you created
STARTING_HOST_PORT = 8080 # Host port for the first container instance (8080 -> 80, 8081 -> 80, etc.)
# For app/simple_server.py to be configurable (optional, already defaults to 80 internally)
# CONTAINER_APP_PORT = 80

# --- Configurações do Autoescalonamento ---
MIN_INSTANCES = 1
MAX_INSTANCES = 4  # Start small for local testing on your VM
# For CPU % (real or simulated), use values between 0 and 100
CPU_THRESHOLD_SCALE_UP = 60.0   # % CPU average to trigger scale up
CPU_THRESHOLD_SCALE_DOWN = 25.0 # % CPU average to trigger scale down
SCALE_COOLDOWN_SECONDS = 20     # Cooldown period between scaling actions
MONITOR_INTERVAL_SECONDS = 5    # How often to check metrics and consider scaling

# --- Configurações de Tráfego ---
# For tcpreplay (if you get to it)
PCAP_FILE_NORMAL_TRAFFIC = "pcaps/normal_traffic.pcap" # You'll need to create/find this
TCPREPLAY_INTERFACE = "docker0" # Or the interface for your edos_network bridge (e.g., br-xxxx)

# HTTP Flood Attack Config
HTTP_ATTACK_TARGET_URL_BASE = "http://localhost" # The orchestrator will add the host port
HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER = 10 # RPS per attacking thread --- 5 foi um valor incial com bom resultado
HTTP_ATTACK_NUM_ATTACKERS = 4 # Number of concurrent attacking threads/processes  -- 2 foi um valor incial com bom resultado

# --- Configurações de Custo (Fictício) ---
COST_PER_INSTANCE_PER_HOUR = 0.02 # Example cost
# EGRESS_TRAFFIC_COST_PER_GB = 0.09 # Can add later if you measure egress

# --- Nomes de arquivos de Log ---
METRICS_LOG_FILE = "simulation_metrics.csv"
RTT_LOG_FILE = "rtt_log.csv"

# ... outras configurações ...
HTTP_REQUEST_TIMEOUT_SECONDS = 10.0 # Timeout para cada requisição HTTP individual (em segundos)
APP_CONTAINER_PORT = 80

#Normal traffic metrics

HTTP_NORMAL_RPS_PER_CLIENT = 10
HTTP_NORMAL_NUM_CLIENTS = 4


#SIMPLE SERVER ATTACK PARAMETERS

ATTACK_WORK_UNITS = 5000
ATTACK_SLEEP = 0.00

#SIMPLE SERVER NORMAL TRAFFIC PARAMETERS

NORMAL_WORK_UNITS = 10
NORMAL_SLEEP =0.0
# --- TCPDUMP SNIFFER CONFIG ---
# Sem TCPDUMP_INTERFACE aqui de propósito: era um nome de bridge Docker
# gerado dinamicamente (br-xxxx, muda se a rede for recriada) e nunca era
# realmente usado pelo sniffer (main_orchestrator.py sempre chamava com
# interface="any" na prática) — removido em vez de mantido como config
# morta. O escopo da captura agora é limitado por porta
# (STARTING_HOST_PORT..STARTING_HOST_PORT+MAX_INSTANCES-1), não por
# interface — ver tcpdump_sniffer.py.
TCPDUMP_OUTPUT_CSV = "traffic_capture.csv"


#---------ANALYZE TRAFFIC CONFIGURATIONS -----------
INPUT_FILE = "traffic_capture.csv"
WINDOW_SIZE = 5  # segundos
BINS = 10



CPU_SAMPLING_INTERVAL_SECONDS = 1.0


ATTACK_SUMMARY_LOG_FILE = "attack_summary_log.csv"

# Log irmão do attack_summary_log.csv, mas para os workers de TRÁFEGO NORMAL
# (normal_traffic.py). Antes desta correção, os contadores request_count/
# error_count de cada worker de tráfego normal só eram impressos no console
# (nunca gravados em CSV) -- taxa de erro do baseline normal era invisível
# para qualquer análise pós-execução, mesmo quando alta (achado real: ~16-27%
# de erro em execuções de auditoria com normal_rps agregado=300/WU=10,
# nunca detectado antes por falta deste log). Ver changes.txt.
NORMAL_TRAFFIC_SUMMARY_LOG_FILE = "normal_traffic_summary_log.csv"

# --- Configurações de Capacidade da Instância (A3) ---
# Tamanho do pool de processos persistente (criado uma única vez no startup do
# simple_server.py) usado para executar o trabalho de CPU de cada requisição.
# Substitui o teto acidental do GIL por um valor explícito e reprodutível, sem
# pagar o custo de criar um processo novo a cada requisição (fork-per-request).
#
# Diagnóstico real (sessão 12/08 tarde, ver changes.txt): com work=10
# (trivial) e tráfego sustentado, o teto de vazão por instância fica em torno
# de ~150 req/s mesmo com o pool maior -- testado 2, 4 e 8 workers contra o
# MESMO tráfego sustentado (300 req/s, container isolado): taxa de erro ficou
# ~28%, ~31%, ~36% respectivamente (igual ou pior, nunca melhor). Ou seja, NÃO
# é o nº de processos-trabalhadores que limita -- é provavelmente um gargalo
# estrutural (a thread única de gerenciamento de resultados do
# ProcessPoolExecutor, ou contenção de GIL no processo do servidor,
# competindo com as threads do ThreadingHTTPServer), que mais processos não
# resolvem. Mantido em 2 (valor original) por decisão do usuário: aumentar
# não ajuda o teto e quebraria a comparabilidade com todo o dataset histórico
# (normal_baseline/wu_calibration/combined_sweep, todos coletados com 2). O
# teto de ~150 req/s/instância fica documentado como característica
# conhecida do simulador, não "consertado" por este parâmetro.
INSTANCE_MAX_CONCURRENT_REQUESTS = 2

# --- Configurações do Injetor Open-Loop (B2) ---
# Tamanho do pool de threads que efetivamente envia as requisições do ataque,
# desacoplando o ritmo de envio do tempo de resposta do alvo.
HTTP_ATTACK_MAX_CONCURRENT_SENDS = 64

# Mesma ideia para o tráfego normal (ver normal_traffic.py).
HTTP_NORMAL_MAX_CONCURRENT_SENDS = 64