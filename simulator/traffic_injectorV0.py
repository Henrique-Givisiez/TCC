# edos_docker_simulation/traffic_injector.py
import requests
import time
import threading
import random
from simulator import config # Para obter HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER, HTTP_ATTACK_NUM_ATTACKERS
import statistics
from simulator import attack_summary_logger
from simulator import load_balancer
from simulator.normal_traffic import rtt_measurements_total
from concurrent.futures import ThreadPoolExecutor
from simulator.experiment_config import AttackConfig, worker_seed
import secrets

# Variável global para controlar a execução dos threads de ataque
attack_active = False
threads = []
rtt_measurements = []
rtt_lock = threading.Lock()

# Balanceamento client-side (ver load_balancer.py), instância própria (não
# compartilha índice de rotação com normal_traffic.py).
_load_balancer = load_balancer.LoadBalancer("Attack")

# Pool compartilhado que efetivamente envia as requisições (open-loop):
# o ritmo de disparo das threads de ataque não espera essa pool terminar.
_send_pool = None
_settings = AttackConfig()
_seed = None


def configure(settings, seed):
    global _send_pool, _settings, _seed
    if attack_active:
        raise RuntimeError("Cannot reconfigure active traffic")
    if _send_pool is not None:
        _send_pool.shutdown(wait=True)
    _settings, _seed = settings, seed
    _send_pool = ThreadPoolExecutor(max_workers=settings.max_concurrent_sends)



def _send_one(session, target_url, counters, counters_lock):
    """
    Executa a requisição bloqueante de fato. Roda numa thread da _send_pool,
    desacoplada do laço de ritmo em http_request_worker.
    """
    start_time = time.monotonic()
    try:
        session.get(target_url, timeout=_settings.request_timeout_seconds)  # Timeout de 2 segundos

        rtt = (time.monotonic() - start_time) * 1000  # em milissegundos
        with rtt_lock:
            rtt_measurements.append(rtt)
            rtt_measurements_total.append({
                "timestamp": time.time(),
                "rtt": rtt
            })
        with counters_lock:
            counters["ok"] += 1
    except requests.exceptions.RequestException:
        with counters_lock:
            counters["err"] += 1


def http_request_worker(rps_per_worker, worker_index=0):
    """
    Worker thread function. Dispara requisições no ritmo de rps_per_worker, sem esperar a
    resposta de uma requisição antes de agendar a próxima (open-loop), com intervalos entre
    disparos sorteados de uma distribuição exponencial (processo de Poisson de taxa
    rps_per_worker) em vez de um intervalo fixo.

    O destino de CADA requisição é decidido na hora via load balancer (get_next_target()),
    não fixado na criação da thread -- ver load_balancer.py e changes.txt. Isso também
    elimina o buraco de ~1s sem tráfego que existia toda vez que o orquestrador reiniciava
    o injetor (stop -> sleep(1) -> start) quando o número de instâncias mudava: agora o
    worker nunca para, só passa a mandar pra URL nova no próximo envio.
    """
    global attack_active
    if rps_per_worker < 0:
        raise ValueError("rate must be >= 0")
    if rps_per_worker == 0:
        return

    rng = random.Random(worker_seed(_seed, "attack", worker_index))
    session = requests.Session() # Use session for potential connection pooling
    mean_interval = 1.0 / rps_per_worker
    worker_start_time = time.monotonic()

    print(f"  [Injector Worker {threading.get_ident()}] Started. RPS: {rps_per_worker:.2f}, Mean interval: {mean_interval:.4f}s (Poisson)")

    counters = {"ok": 0, "err": 0}
    counters_lock = threading.Lock()
    pending_futures = []

    while attack_active:
        base_url = _load_balancer.get_next_target()
        if base_url is None:
            time.sleep(0.1)
            continue
        target_url = f"{base_url}{_settings.endpoint}?work={_settings.work_units}&sleep={_settings.sleep_seconds}"

        try:
            future = _send_pool.submit(_send_one, session, target_url, counters, counters_lock)
        except RuntimeError:
            # _send_pool já foi finalizada (ex.: encerramento do interpretador) — encerra o worker.
            break
        pending_futures.append(future)
        # Descartar futures já concluídas para não acumular memória em ataques longos.
        pending_futures = [f for f in pending_futures if not f.done()]

        # Próximo intervalo sorteado independentemente (memoryless), não corrigido pelo
        # tempo de despacho — o despacho na _send_pool é rápido o bastante para não
        # distorcer a taxa alvo.
        sleep_duration = rng.expovariate(rps_per_worker)
        time.sleep(sleep_duration)

    # Esperar as requisições ainda em voo terminarem antes de contabilizar o resumo final,
    # para não subestimar total_requests/errors no CSV.
    for f in pending_futures:
        try:
            f.result(timeout=_settings.request_timeout_seconds + 1.0)  # timeout da requisição (2s) + margem de segurança
        except Exception:
            pass

    with counters_lock:
        request_count, error_count = counters["ok"], counters["err"]

    print(f"  [Injector Worker {threading.get_ident()}] Stopped. Total requests: {request_count}, Errors: {error_count}")

    attack_summary_logger.log_worker_stop(
        request_count=request_count,
        error_count=error_count,
        worker_start_time=worker_start_time,
        rps_per_worker=rps_per_worker
)

# edos_docker_simulation/traffic_injector.py

# ... (mantenha os imports e a definição de http_request_worker como está) ...

# Variável global para controlar a execução dos threads de ataque
attack_active = False
# renomeando para 'attacker_threads' para clareza e consistência
# Comente ou remova a linha 'threads = []' se ela existir e você não a estiver usando
attacker_threads = []



def get_average_rtt_attack_ms():
    global rtt_measurements
    with rtt_lock:
        if not rtt_measurements:
            return 0.0
        avg_rtt = statistics.mean(rtt_measurements)
        rtt_measurements = []
        return avg_rtt



def start_http_flood(target_urls, rps_per_worker_override, num_attackers_override):
    """
    Starts an HTTP flood attack against specified target URLs.
    This function starts worker threads and returns immediately (non-blocking).
    The attack continues until stop_http_flood() is called.

    Args:
        target_urls (list): A list of full URLs to target (e.g., ["http://localhost:8080"]).
        rps_per_worker_override (float): The Requests Per Second (RPS) each worker thread should aim for.
        num_attackers_override (int): The total number of attacker threads to launch.
    """
    global attack_active, attacker_threads
    if rps_per_worker_override < 0:
        raise ValueError("rate must be >= 0")
    if rps_per_worker_override == 0:
        return
    if _send_pool is None:
        configure(_settings, secrets.randbits(64))


    if not target_urls:
        print("[Injector] No target URLs provided. Attack not started.")
        return
    if attack_active:
        print("[Injector] Attack already in progress. Call stop_http_flood() first.")
        return

    attack_active = True
    # Limpar threads antigas é importante se o orchestrator não garante que stop_http_flood completou totalmente
    if attacker_threads:
        print(f"[Injector] Clearing {len(attacker_threads)} existing attacker threads before starting new ones.")
    attacker_threads.clear()

    _load_balancer.update_targets(target_urls)

    print(f"[Injector] Starting HTTP flood with {num_attackers_override} attackers, ~{rps_per_worker_override * num_attackers_override} RPS total, across {len(target_urls)} targets: {', '.join(target_urls)}")

    attack_summary_logger.log_attack_start(
        target_urls=target_urls,
        rps_per_worker=rps_per_worker_override,
        num_attackers=num_attackers_override
    )

    for i in range(num_attackers_override):
        # Não há mais round-robin aqui -- cada worker consulta o load balancer
        # (get_next_target()) a cada envio, não fica preso a uma URL fixa.
        thread = threading.Thread(
            target=http_request_worker,
            args=(rps_per_worker_override, i),
            daemon=True,
            name=f"InjectorWorker-{i+1}"
        )
        attacker_threads.append(thread)
        thread.start()

    print(f"[Injector] All {len(attacker_threads)} attacker threads launched.")


def update_targets(target_urls):
    """
    Chamado pelo orquestrador a cada iteração do loop, com a lista atual de
    URLs das instâncias ativas -- substitui o antigo padrão de
    stop_http_flood() -> sleep(1) -> start_http_flood() (ver changes.txt).
    Seguro de chamar sempre, mesmo com o ataque inativo.
    """
    _load_balancer.update_targets(target_urls)

# Esta é a versão revisada e mais robusta do stop_http_flood
def stop_http_flood():
    """
    Non-blocking stop of attack threads.
    """
    global attack_active, attacker_threads

    if not attack_active and not attacker_threads:
        print("[Injector] HTTP flood already stopped.")
        return

    print("[Injector] Signaling HTTP flood workers to stop...")
    attack_active = False

    threads_to_join = list(attacker_threads)
    attacker_threads.clear()

    # JOIN CURTO para evitar travar o loop
    for thread_obj in threads_to_join:
        if thread_obj.is_alive():
            thread_obj.join(timeout=0.1)  # máximo 100ms

    print("[Injector] Stop signal sent (non-blocking).")

# ... (mantenha o bloco if __name__ == "__main__": inalterado, ele serve para teste do módulo) ...

# --- Self-test section (optional, for direct testing of this module) ---
if __name__ == "__main__":
    from simulator import docker_manager # Para iniciar um servidor de teste

    print("--- Running traffic_injector.py self-test ---")

    # 1. Iniciar uma instância de teste do simple_server.py usando docker_manager
    #    Precisamos garantir que a imagem exista e a rede também.
    if not docker_manager.build_docker_image():
        print("[Self-Test] Failed to build Docker image. Aborting self-test.")
        exit(1)
    if not docker_manager.ensure_docker_network():
        print("[Self-Test] Failed to ensure Docker network. Aborting self-test.")
        exit(1)

    docker_manager.cleanup_all_simulation_instances() # Limpar antes do teste

    test_instance_id = 99 # Usar um ID alto para não colidir com simulações normais
    test_container = docker_manager.start_instance(test_instance_id)
    if not test_container:
        print("[Self-Test] Failed to start test container. Aborting self-test.")
        exit(1)

    test_container.reload() # Carregar atributos
    test_host_port = None
    try:
        # Obter a porta mapeada do host para o contêiner de teste
        port_mappings = test_container.attrs['NetworkSettings']['Ports'].get('80/tcp')
        if port_mappings and isinstance(port_mappings, list) and len(port_mappings) > 0:
            test_host_port = int(port_mappings[0].get('HostPort'))
            print(f"[Self-Test] Test container '{test_container.name}' running on host port {test_host_port}")
        else:
            raise ValueError("Could not determine host port for test container.")

        # Construir a URL de teste completa
        test_target_url = f"http://localhost:{test_host_port}" # Ou config.HTTP_ATTACK_TARGET_URL_BASE se for localhost

        # 2. Configurar o tráfego de teste (valores menores para não sobrecarregar)
        print("\n[Self-Test] Starting test HTTP flood...")
        configure(AttackConfig(rate=5, attackers=2), 0) # Sobrescrever para o teste

        start_http_flood([test_target_url], _settings.rate, _settings.attackers)
        print("[Self-Test] Flood started. Waiting 5 seconds before testing update_targets()...")
        time.sleep(5)

        print("[Self-Test] Calling update_targets() with the same single target (smoke test)...")
        update_targets([test_target_url])
        time.sleep(5)

        stop_http_flood()
        print("[Self-Test] Test HTTP flood completed.")

    except Exception as e:
        print(f"[Self-Test] An error occurred during self-test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 3. Parar e remover a instância de teste
        print("\n[Self-Test] Cleaning up test container...")
        if test_container:
            docker_manager.stop_instance(test_container.name)
        print("[Self-Test] Cleanup complete.")

    print("--- traffic_injector.py self-test complete ---")
