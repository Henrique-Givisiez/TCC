# edos_docker_simulation/traffic_injector.py
import requests
import time
import threading
import random
import statistics
import csv
from simulator import normal_traffic_summary_logger
from simulator.service_destination import validate_endpoint, validate_request_url
from concurrent.futures import ThreadPoolExecutor
from simulator.experiment_config import NormalTrafficConfig, worker_seed
import secrets

_ground_truth = None
_request_logger = None
_stop_event = threading.Event()
_futures = set()
_futures_lock = threading.Lock()
_send_failures = []


# Variável global para controlar a execução dos threads de ataque
traffic_active = False
threads = []
rtt_measurements = []
rtt_measurements_total = []
rtt_lock = threading.Lock()

# Somente no modo histórico: balanceamento client-side (ver load_balancer.py) -- plano de controle só,
# nunca fica no caminho da requisição HTTP em si (não afeta o RTT medido).
_load_balancer = None
_service_endpoint = None

# Pool compartilhado que efetivamente envia as requisições (open-loop), no mesmo
# padrão do injetor de ataque (traffic_injectorV0.py): o ritmo de disparo não
# espera essa pool terminar, e os intervalos entre disparos são independentes
# uns dos outros (necessário para que os sorteios de Poisson façam sentido).
_send_pool = None
_settings = NormalTrafficConfig()
_seed = None


def configure(settings, seed, ground_truth=None, request_logger=None, service_endpoint=None):
    global _send_pool, _settings, _seed, _ground_truth, _request_logger, _service_endpoint, _load_balancer
    if traffic_active:
        raise RuntimeError("Cannot reconfigure active traffic")
    if _send_pool is not None:
        _send_pool.shutdown(wait=True)
    _service_endpoint = validate_endpoint(service_endpoint) if service_endpoint is not None else None
    if _service_endpoint is not None:
        _load_balancer = None
    else:
        from simulator.load_balancer import LoadBalancer
        _load_balancer = LoadBalancer("Normal")
    _ground_truth, _request_logger = ground_truth, request_logger
    _stop_event.clear()
    _send_failures.clear()
    with _futures_lock:
        _futures.clear()
    with rtt_lock:
        rtt_measurements.clear()
    rtt_measurements_total.clear()
    _settings, _seed = settings, seed
    _send_pool = ThreadPoolExecutor(max_workers=settings.max_concurrent_sends)



def _send_one_normal(session, target_url, counters, counters_lock, worker_id=0, event_id=None):
    """HTTP call begins here, never at executor submission."""
    attempt = (_request_logger.begin('normal', worker_id, target_url, event_id)
               if _request_logger else None)
    start_time = time.monotonic()
    response, error = None, None
    try:
        if _service_endpoint is not None:
            validate_request_url(target_url, _service_endpoint)
            response = session.get(target_url, timeout=_settings.request_timeout_seconds,
                                   allow_redirects=False,
                                   headers={'X-Edos-Request-Id': attempt['request_id'] if attempt else ''})
        else:
            response = session.get(target_url, timeout=_settings.request_timeout_seconds)
    except requests.exceptions.RequestException as exc:
        error = exc
    except Exception as exc:
        error = exc
        raise
    finally:
        # Capture completion before counters, locks and disk persistence.
        end_sample = _ground_truth.clock.sample() if attempt else None
        duration_ms = (time.monotonic() - start_time) * 1000
        if attempt:
            _request_logger.finish(attempt, response, error, end_sample=end_sample)
        with counters_lock:
            if error is None:
                counters['ok'] += 1  # preserve HTTP response counters, including error statuses
            elif isinstance(error, requests.exceptions.RequestException):
                counters['err'] += 1
        if error is None:
            with rtt_lock:
                rtt_measurements.append(duration_ms)
                rtt_measurements_total.append({"timestamp": time.time(), "rtt": duration_ms})


def _track_future(future):
    if _ground_truth is None:
        return
    with _futures_lock:
        _futures.add(future)
    def finished(done):
        with _futures_lock:
            _futures.discard(done)
            if done.cancelled() or done.exception() is not None:
                _send_failures.append('send_failed')
    future.add_done_callback(finished)


def drain(timeout=30.0):
    """Bounded final drain; returns False rather than claiming complete data."""
    deadline = time.monotonic() + timeout
    for thread in list(client_threads):
        thread.join(timeout=max(0.0, deadline - time.monotonic()))
    producers_done = all(not thread.is_alive() for thread in client_threads)
    if _send_pool is not None:
        _send_pool.shutdown(wait=False)  # already submitted calls remain admitted
    while time.monotonic() < deadline:
        with _futures_lock:
            if not _futures:
                break
        time.sleep(0.01)
    with _futures_lock:
        complete = producers_done and not _futures and not _send_failures
    if complete:
        client_threads.clear()
    return complete


def normal_http_request_worker(rps_per_worker, worker_index=0):
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
    if rps_per_worker < 0:
        raise ValueError("rate must be >= 0")
    if rps_per_worker == 0:
        return

    rng = random.Random(worker_seed(_seed, "normal", worker_index))
    session = requests.Session() # Preserve the existing shared worker session/pool.
    if _service_endpoint is not None:
        session.trust_env = False
    mean_interval = 1.0 / rps_per_worker
    worker_start_time = time.monotonic()

    print(f"  [Normal_Injector Worker {threading.get_ident()}] Started. RPS: {rps_per_worker:.2f}, Mean interval: {mean_interval:.4f}s (Poisson)")

    counters = {"ok": 0, "err": 0}
    counters_lock = threading.Lock()
    pending_futures = []

    while traffic_active:
        base_url = _service_endpoint if _service_endpoint is not None else _load_balancer.get_next_target()
        if base_url is None:
            # Ainda sem nenhuma instância registrada (ex.: chamado antes do primeiro
            # update_targets()) -- espera um pouco e tenta de novo, sem contar como erro.
            time.sleep(0.1)
            continue
        target_url = f"{base_url}{_settings.endpoint}?work={_settings.work_units}&sleep={_settings.sleep_seconds}"

        try:
            future = _send_pool.submit(_send_one_normal, session, target_url, counters, counters_lock, worker_index)
        except RuntimeError:
            # _send_pool já foi finalizada (ex.: encerramento do interpretador) — encerra o worker.
            break
        _track_future(future)
        pending_futures.append(future)
        # Descartar futures já concluídas para não acumular memória em execuções longas.
        pending_futures = [f for f in pending_futures if not f.done()]

        # Próximo intervalo sorteado independentemente (memoryless), não corrigido pelo
        # tempo de despacho — o despacho na _send_pool é rápido o bastante para não
        # distorcer a taxa alvo.
        sleep_duration = rng.expovariate(rps_per_worker)
        if _ground_truth is None:
            time.sleep(sleep_duration)
        else:
            _stop_event.wait(sleep_duration)

    # Esperar as requisições ainda em voo terminarem antes de contabilizar o resumo final.
    for f in pending_futures:
        try:
            f.result(timeout=_settings.request_timeout_seconds + 1.0)  # timeout da requisição (2s) + margem de segurança
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
        from simulator.config import RTT_LOG_FILE
        filename = RTT_LOG_FILE
    if _request_logger is not None:
        _request_logger.save_rtt(filename)
        return
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



def start_service_traffic(service_endpoint, rate, clients):
    """Proxy API: a single immutable service endpoint, never a backend list."""
    if _service_endpoint != validate_endpoint(service_endpoint):
        raise RuntimeError('configure proxy service endpoint before starting traffic')
    return start_http_traffic(service_endpoint, rate, clients)


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
    if _service_endpoint is not None and target_urls != _service_endpoint:
        raise ValueError('proxy mode requires the configured service_endpoint')
    if rps_per_worker_override < 0:
        raise ValueError("rate must be >= 0")


    if rps_per_worker_override <= 0 or num_clients_override <= 0:
        # Antes, rps=0 caía no fallback de normal_http_request_worker
        # (sleep_duration=1.0s fixo), o que ainda gerava ~1 req/s por
        # cliente em vez de desligar de vez o tráfego normal -- usado
        # para isolar ataque puro (changes.txt, tarefa "só-ataque").
        print(f"[Normal_Injector] rps_per_worker={rps_per_worker_override} ou "
              f"num_clients={num_clients_override} <= 0 -- tráfego normal desligado de propósito, não iniciado.")
        return
    if _send_pool is None:
        configure(_settings, secrets.randbits(64))

    if not target_urls:
        print("[Normal_Injector] No target URLs provided. Attack not started.")
        return
    if traffic_active:
        print("[Normal_Injector] Normal traffic already in progress. Call stop_http_traffic() first.")
        return

    _stop_event.clear()
    traffic_active = True
    # Limpar threads antigas é importante se o orchestrator não garante que stop_http_flood completou totalmente
    if client_threads:
        print(f"[Normal_Injector] Clearing {len(client_threads)} existing attacker threads before starting new ones.")
    client_threads.clear()

    if _service_endpoint is None:
        update_targets(target_urls)

    print(f"[Normal_Injector] Starting HTTP flood with {num_clients_override} attackers, ~{rps_per_worker_override * num_clients_override} RPS total, destination: {target_urls}")

    normal_traffic_summary_logger.log_traffic_start(
        target_urls=[_service_endpoint] if _service_endpoint is not None else target_urls,
        rps_per_worker=rps_per_worker_override,
        num_clients=num_clients_override,
    )

    for i in range(num_clients_override):
        # Não há mais round-robin aqui -- cada worker consulta o load balancer
        # (get_next_target()) a cada envio, não fica preso a uma URL fixa.
        thread = threading.Thread(
            target=normal_http_request_worker,
            args=(rps_per_worker_override, i),
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
    global _load_balancer
    if _service_endpoint is not None:
        raise RuntimeError("cannot update backend targets in proxy mode")
    if _load_balancer is None:
        from simulator.load_balancer import LoadBalancer
        _load_balancer = LoadBalancer("Normal")
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
    _stop_event.set()

    threads_to_join = list(client_threads)

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
        configure(NormalTrafficConfig(rate=5, clients=2), 0) # Sobrescrever para o teste

        start_http_traffic([test_target_url], _settings.rate, _settings.clients)
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
