# edos_docker_simulation/traffic_injector.py
import requests
import time
import threading
import random
from simulator import config # Para obter HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER, HTTP_ATTACK_NUM_ATTACKERS
import statistics
import csv
from simulator import normal_traffic_summary_logger
from simulator import load_balancer
from concurrent.futures import ThreadPoolExecutor


# Variável global para controlar a execução dos threads de ataque
traffic_active = False
threads = []
rtt_measurements = []
rtt_measurements_total = []
rtt_lock = threading.Lock()

# Balanceamento client-side (ver load_balancer.py) -- plano de controle só,
# nunca fica no caminho da requisição HTTP em si (não afeta o RTT medido).
_load_balancer = load_balancer.LoadBalancer("Normal")

# Pool compartilhado que efetivamente envia as requisições (open-loop), no mesmo
# padrão do injetor de ataque (traffic_injectorV0.py): o ritmo de disparo não
# espera essa pool terminar, e os intervalos entre disparos são independentes
# uns dos outros (necessário para que os sorteios de Poisson façam sentido).
_send_pool = ThreadPoolExecutor(max_workers=config.HTTP_NORMAL_MAX_CONCURRENT_SENDS)


def _send_one_normal(session, target_url, counters, counters_lock):
    """
    Executa a requisição bloqueante de fato. Roda numa thread da _send_pool,
    desacoplada do laço de ritmo em normal_http_request_worker.
    """
    start_time = time.monotonic()
    try:
        session.get(target_url, timeout=2)  # Timeout de 2 segundos

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


def normal_http_request_worker(rps_per_worker):
    """
    Worker thread function. Dispara requisições no ritmo de rps_per_worker, sem esperar a
    resposta de uma requisição antes de agendar a próxima (open-loop), com intervalos entre
    disparos sorteados de uma distribuição exponencial (processo de Poisson de taxa
    rps_per_worker) em vez de um intervalo fixo — modela clientes independentes, como
    assumido em Sotelo Monge et al.

    O destino de CADA requisição é decidido na hora, consultando o load balancer
    (get_next_target()) -- não é mais fixado na criação da thread. Isso é o que permite a
    instância nova receber tráfego assim que o orquestrador chamar update_targets(), sem
    precisar parar/recriar este worker.
    """
    global traffic_active
    session = requests.Session() # Use session for potential connection pooling
    mean_interval = 1.0 / rps_per_worker if rps_per_worker > 0 else 1.0
    worker_start_time = time.monotonic()

    print(f"  [Normal_Injector Worker {threading.get_ident()}] Started. RPS: {rps_per_worker:.2f}, Mean interval: {mean_interval:.4f}s (Poisson)")

    counters = {"ok": 0, "err": 0}
    counters_lock = threading.Lock()
    pending_futures = []

    while traffic_active:
        base_url = _load_balancer.get_next_target()
        if base_url is None:
            # Ainda sem nenhuma instância registrada (ex.: chamado antes do primeiro
            # update_targets()) -- espera um pouco e tenta de novo, sem contar como erro.
            time.sleep(0.1)
            continue
        target_url = f"{base_url}?work={config.NORMAL_WORK_UNITS}&sleep={config.NORMAL_SLEEP}"

        try:
            future = _send_pool.submit(_send_one_normal, session, target_url, counters, counters_lock)
        except RuntimeError:
            # _send_pool já foi finalizada (ex.: encerramento do interpretador) — encerra o worker.
            break
        pending_futures.append(future)
        # Descartar futures já concluídas para não acumular memória em execuções longas.
        pending_futures = [f for f in pending_futures if not f.done()]

        # Próximo intervalo sorteado independentemente (memoryless), não corrigido pelo
        # tempo de despacho — o despacho na _send_pool é rápido o bastante para não
        # distorcer a taxa alvo.
        sleep_duration = random.expovariate(rps_per_worker) if rps_per_worker > 0 else 1.0
        time.sleep(sleep_duration)

    # Esperar as requisições ainda em voo terminarem antes de contabilizar o resumo final.
    for f in pending_futures:
        try:
            f.result(timeout=3)  # timeout da requisição (2s) + margem de segurança
        except Exception:
            pass

    with counters_lock:
        request_count, error_count = counters["ok"], counters["err"]

    print(f"  [Normal_Injector Worker {threading.get_ident()}] Stopped. Total requests: {request_count}, Errors: {error_count}")

    normal_traffic_summary_logger.log_worker_stop(
        request_count=request_count,
        error_count=error_count,
        worker_start_time=worker_start_time,
        rps_per_worker=rps_per_worker,
    )

def save_rtt_log(filename=None):
    if filename is None:
        filename = config.RTT_LOG_FILE
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "rtt"])

        for entry in rtt_measurements_total:
            writer.writerow([entry["timestamp"], entry["rtt"]])



# edos_docker_simulation/traffic_injector.py

# ... (mantenha os imports e a definição de http_request_worker como está) ...

# Variável global para controlar a execução dos threads de ataque
traffic_active = False
# renomeando para 'attacker_threads' para clareza e consistência
# Comente ou remova a linha 'threads = []' se ela existir e você não a estiver usando
client_threads = [] 


def get_average_rtt_ms():
    global rtt_measurements
    with rtt_lock:
        if not rtt_measurements:
            return 0.0
        avg_rtt = statistics.mean(rtt_measurements)
        rtt_measurements = []
        return avg_rtt



def start_http_traffic(target_urls, rps_per_worker_override, num_clients_override):
    """
    Starts an HTTP flood attack against specified target URLs.
    This function starts worker threads and returns immediately (non-blocking).
    The attack continues until stop_http_flood() is called.

    Args:
        target_urls (list): A list of full URLs to target (e.g., ["http://localhost:8080"]).
        rps_per_worker_override (float): The Requests Per Second (RPS) each worker thread should aim for.
        num_attackers_override (int): The total number of attacker threads to launch.
    """
    global traffic_active, client_threads

    if rps_per_worker_override <= 0 or num_clients_override <= 0:
        # Antes, rps=0 caía no fallback de normal_http_request_worker
        # (sleep_duration=1.0s fixo), o que ainda gerava ~1 req/s por
        # cliente em vez de desligar de vez o tráfego normal -- usado
        # para isolar ataque puro (changes.txt, tarefa "só-ataque").
        print(f"[Normal_Injector] rps_per_worker={rps_per_worker_override} ou "
              f"num_clients={num_clients_override} <= 0 -- tráfego normal desligado de propósito, não iniciado.")
        return
    if not target_urls:
        print("[Normal_Injector] No target URLs provided. Attack not started.")
        return
    if traffic_active:
        print("[Normal_Injector] Normal traffic already in progress. Call stop_http_traffic() first.")
        return

    traffic_active = True
    # Limpar threads antigas é importante se o orchestrator não garante que stop_http_flood completou totalmente
    if client_threads:
        print(f"[Normal_Injector] Clearing {len(client_threads)} existing attacker threads before starting new ones.")
    client_threads.clear()

    _load_balancer.update_targets(target_urls)

    print(f"[Normal_Injector] Starting HTTP flood with {num_clients_override} attackers, ~{rps_per_worker_override * num_clients_override} RPS total, across {len(target_urls)} targets: {', '.join(target_urls)}")

    normal_traffic_summary_logger.log_traffic_start(
        target_urls=target_urls,
        rps_per_worker=rps_per_worker_override,
        num_clients=num_clients_override,
    )

    for i in range(num_clients_override):
        # Não há mais round-robin aqui -- cada worker consulta o load balancer
        # (get_next_target()) a cada envio, não fica preso a uma URL fixa.
        thread = threading.Thread(
            target=normal_http_request_worker,
            args=(rps_per_worker_override,),
            daemon=True,
            name=f"InjectorWorker-{i+1}"
        )
        client_threads.append(thread)
        thread.start()

    print(f"[Normal_Injector] All {len(client_threads)} attacker threads launched.")


def update_targets(target_urls):
    """
    Chamado pelo orquestrador a cada iteração do loop, com a lista atual de
    URLs das instâncias ativas -- seguro de chamar sempre, mesmo antes de
    start_http_traffic() ou depois de stop_http_traffic() (só atualiza o
    estado do load balancer, não depende dos workers estarem rodando).
    Substitui o antigo comportamento de "decidir a URL uma vez, na
    criação das threads" (ver changes.txt) -- é isso que faz uma instância
    nova, criada pelo autoscaler no meio do run, passar a receber tráfego
    normal de verdade.
    """
    _load_balancer.update_targets(target_urls)


def stop_http_traffic():
    """
    Non-blocking stop.
    Signals workers to stop but does NOT block the orchestrator loop.
    """
    global traffic_active, client_threads

    if not traffic_active and not client_threads:
        print("[Normal_Injector] HTTP normal traffic already stopped.")
        return

    print("[Normal_Injector] Signaling workers to stop...")
    traffic_active = False

    threads_to_join = list(client_threads)
    client_threads.clear()

    # JOIN CURTO E NÃO BLOQUEANTE
    for thread_obj in threads_to_join:
        if thread_obj.is_alive():
            thread_obj.join(timeout=0.1)  # máximo 100ms

    print("[Normal_Injector] Stop signal sent (non-blocking).")

# ... (mantenha o bloco if __name__ == "__main__": inalterado, ele serve para teste do módulo) ...

# --- Self-test section (optional, for direct testing of this module) ---
if __name__ == "__main__":
    from simulator import docker_manager # Para iniciar um servidor de teste

    print("--- Running normal_traffic.py self-test ---")

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
        config.HTTP_NORMAL_NUM_CLIENTS = 2 # Sobrescrever para o teste
        config.HTTP_NORMAL_RPS_PER_CLIENT = 5 # Sobrescrever para o teste

        start_http_traffic([test_target_url], config.HTTP_NORMAL_RPS_PER_CLIENT, config.HTTP_NORMAL_NUM_CLIENTS)
        print("[Self-Test] Flood started. Waiting 5 seconds before testing update_targets()...")
        time.sleep(5)

        # Testa o ponto central da mudança: update_targets() com uma lista de alvos
        # diferente não deve travar nem exigir parar/recriar os workers -- os próximos
        # envios já devem ir pra URL nova.
        print("[Self-Test] Calling update_targets() with the same single target (smoke test)...")
        update_targets([test_target_url])
        time.sleep(5)

        stop_http_traffic()
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

    print("--- normal_traffic.py self-test complete ---")
