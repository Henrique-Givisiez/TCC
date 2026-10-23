"""Technical settings and paths. Experimental defaults live in experiment_config.

Deprecated read-only aliases below support historical imports; active components
receive structured configuration. Assigning aliases does not configure a run.
"""
from simulator.experiment_config import ExperimentConfig

DOCKER_IMAGE_NAME = "edos_target_app:latest"
BASE_CONTAINER_NAME = "target_instance"
DOCKER_NETWORK_NAME = "edos_network"
STARTING_HOST_PORT = 8080
PCAP_FILE_NORMAL_TRAFFIC = "pcaps/normal_traffic.pcap"
TCPREPLAY_INTERFACE = "docker0"
HTTP_ATTACK_TARGET_URL_BASE = "http://localhost"
METRICS_LOG_FILE = "simulation_metrics.csv"
RTT_LOG_FILE = "rtt_log.csv"
HTTP_REQUEST_TIMEOUT_SECONDS = 10.0
APP_CONTAINER_PORT = 80
TCPDUMP_OUTPUT_CSV = "traffic_capture.csv"
INPUT_FILE = "traffic_capture.csv"
WINDOW_SIZE = 5
BINS = 10
CPU_SAMPLING_INTERVAL_SECONDS = 1.0
ATTACK_SUMMARY_LOG_FILE = "attack_summary_log.csv"
NORMAL_TRAFFIC_SUMMARY_LOG_FILE = "normal_traffic_summary_log.csv"

_LEGACY_FIELDS = {'ATTACK_SLEEP': 'attack.sleep_seconds',
 'ATTACK_START_TIME_SECONDS': 'attack.start_seconds',
 'ATTACK_WORK_UNITS': 'attack.work_units',
 'COST_PER_INSTANCE_PER_HOUR': 'infrastructure.cost_per_instance_per_hour',
 'CPU_THRESHOLD_SCALE_DOWN': 'autoscaler.scale_down_threshold',
 'CPU_THRESHOLD_SCALE_UP': 'autoscaler.scale_up_threshold',
 'HTTP_ATTACK_MAX_CONCURRENT_SENDS': 'attack.max_concurrent_sends',
 'HTTP_ATTACK_NUM_ATTACKERS': 'attack.attackers',
 'HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER': 'attack.rate',
 'HTTP_NORMAL_MAX_CONCURRENT_SENDS': 'normal_traffic.max_concurrent_sends',
 'HTTP_NORMAL_NUM_CLIENTS': 'normal_traffic.clients',
 'HTTP_NORMAL_RPS_PER_CLIENT': 'normal_traffic.rate',
 'INSTANCE_MAX_CONCURRENT_REQUESTS': 'server.process_pool_workers',
 'MAX_INSTANCES': 'infrastructure.max_instances',
 'MIN_INSTANCES': 'infrastructure.min_instances',
 'MONITOR_INTERVAL_SECONDS': 'monitoring.interval_seconds',
 'NORMAL_SLEEP': 'normal_traffic.sleep_seconds',
 'NORMAL_WORK_UNITS': 'normal_traffic.work_units',
 'PULSE_DURATION': 'attack.duration_seconds',
 'SCALE_COOLDOWN_SECONDS': 'autoscaler.cooldown_seconds',
 'SIMULATION_DURATION_SECONDS': 'duration_seconds'}

def __getattr__(name):
    if name == "ATTACK_DURATION_SECONDS":
        return 90  # Historical enable sentinel, never a duration in the active flow.
    if name in _LEGACY_FIELDS:
        value = ExperimentConfig()
        for part in _LEGACY_FIELDS[name].split("."):
            value = getattr(value, part)
        return value
    raise AttributeError(name)

ATTACK_EVENTS_LOG_FILE = "attack_events.csv"
REQUEST_LOG_FILE = "request_log.csv"
RUN_STATUS_FILE = "run_status.json"

# Native Ubuntu Engine only; no context-dependent Desktop selection.
DOCKER_ENGINE_SOCKET = "unix:///var/run/docker.sock"
PROXY_IMAGE = "nginx:1.28.0-alpine"
PROXY_IMAGE_DIGEST = "sha256:30f1c0d78e0ad60901648be663a710bdadf19e4c10ac6782c235200619158284"
PROXY_HOST_PORT = 8080
PROXY_ARTIFACT_DIR = "proxy_artifacts"
SERVICE_ENDPOINT = "http://127.0.0.1:8080"
PROXY_CAPTURE_INTERFACE = "lo"
PROXY_CAPTURE_FILTER = "tcp and host 127.0.0.1 and port 8080"

SOURCE_NETWORK_NAME = "edos_sources"
SOURCE_SERVICE_ENDPOINT = "http://edos_service:80"
SOURCE_ARTIFACT_DIR = "source_artifacts"
SOURCE_INVENTORY_FILE = "source_inventory.json"
SOURCE_IMAGE = "edos_sources:stage5"

# Independent proxy observability; no scientific feature/detector inputs.
PROXY_POLL_INTERVAL_SECONDS = 1.0
PROXY_COLLECTION_TIMEOUT_SECONDS = 2.0
