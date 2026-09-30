# edos_docker_simulationc
import requests
import time
import threading
from simulator import config # Para obter HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER, HTTP_ATTACK_NUM_ATTACKERS
import random # Para uma alternativa de balanceamento
import statistics

# Variável global para controlar a execução dos threads de ataque
attack_active = False
attacker_threads = []
threads = []
rtt_measurements = []
rtt_lock = threading.Lock()

def http_request_worker(target_url, rps_per_this_worker):
    """
    Worker thread function. Sends requests to target_url at a specified RPS.
    Controlado pela flag global 'attack_active'.
    """
    # Contadores locais para este worker específico
    worker_request_count = 0
    worker_error_count = 0

    # Usar uma sessão pode ser benéfico para keep-alive se o servidor suportar
    # e para reutilizar conexões TCP, reduzindo a sobrecarga.
    session = requests.Session() 
    
    # Calcular o intervalo de sono necessário para atingir o RPS alvo.
    # Se rps_per_this_worker for 0 ou negativo, o worker não enviará requisições ativamente,
    # mas precisa permanecer no loop para ser parado corretamente por 'attack_active'.
    # Definimos um sleep_interval padrão para evitar divisão por zero se rps_per_this_worker <= 0.
    if rps_per_this_worker > 0:
        sleep_interval_seconds = 1.0 / rps_per_this_worker
    else:
        sleep_interval_seconds = 1.0 # Worker irá "dormir" por 1s se RPS for 0

    # print(f"  [Injector Worker {threading.get_ident()}] Started. Target: {target_url}, Configured RPS: {rps_per_this_worker:.2f}, Target Interval: {sleep_interval_seconds:.4f}s")

    while attack_active: # Loop é controlado pela flag global 'attack_active'
        start_time = time.monotonic()
        # Se RPS for 0, apenas dorme e continua checando 'attack_active'
        if rps_per_this_worker <= 0:
            time.sleep(0.1) # Dorme um pouco para não consumir CPU em idle e checa 'attack_active'
            continue

        # Registra o tempo de início desta iteração para calcular o tempo de sono necessário
        iteration_start_time = time.monotonic()
        
        try:
            # Faz a requisição HTTP GET com o timeout configurado
            response = session.get(target_url, timeout=config.HTTP_REQUEST_TIMEOUT_SECONDS) 
            
            if response.status_code == 200:
                end_time = time.monotonic()
                rtt = (end_time - start_time) * 1000  # em milissegundos
                with rtt_lock:
                    rtt_measurements.append(rtt)

                worker_request_count += 1
            else:
                # Logar status code diferente de 200 como um erro ou apenas uma observação
                # print(f"  [Injector Worker {threading.get_ident()}] Target: {target_url}, Status: {response.status_code}")
                worker_error_count += 1 # Considerar outros status codes como erro por enquanto
        except requests.exceptions.Timeout:
            # print(f"  [Injector Worker {threading.get_ident()}] Target: {target_url}, Timeout error during request.")
            worker_error_count += 1
        except requests.exceptions.RequestException as e:
            # Lidar com outras exceções de requisição (ex: ConnectionError)
            # print(f"  [Injector Worker {threading.get_ident()}] Target: {target_url}, Request error: {e}")
            worker_error_count += 1
        
        # Calcular o tempo gasto na iteração (requisição + processamento)
        iteration_time_taken = time.monotonic() - iteration_start_time
        
        # O tempo de sono é o intervalo desejado menos o tempo que a iteração já levou
        time_to_sleep = sleep_interval_seconds - iteration_time_taken
        
        if time_to_sleep > 0:
            # Dorme pelo tempo calculado para tentar manter o RPS.
            # É importante que o time.sleep() não seja interrompido prematuramente
            # se 'attack_active' mudar durante o sono. Para este modelo mais simples,
            # ele completará o sono atual. Se uma parada imediata fosse crítica,
            # o evento de parada precisaria ser checado em sleeps menores.
            time.sleep(time_to_sleep)
        # Se time_to_sleep <= 0, significa que o worker está atrasado
        # (a requisição demorou mais que o intervalo alvo). Ele prosseguirá
        # para a próxima iteração imediatamente para tentar recuperar o atraso.

    # Loop terminou porque 'attack_active' tornou-se False
    print(f"  [Injector Worker {threading.get_ident()}] Stopped. Requests by this worker: {worker_request_count}, Errors: {worker_error_count}")

    # Opcional: Atualizar contadores globais de resumo (requereria um lock)
    # with global_stats_lock:
    #     global_total_requests_summary += worker_request_count
    #     global_total_errors_summary += worker_error_count

def get_average_rtt_attack_ms():
    with rtt_lock:
        if not rtt_measurements:
            return 0.0
        return statistics.mean(rtt_measurements)


def start_http_flood(target_urls, rps_per_worker, num_attackers):
    global attack_active, attacker_threads
    print(f"[DEBUG Injector start_http_flood] Received target_urls: {target_urls}") # LOG
    print(f"[DEBUG Injector start_http_flood] Received rps_per_worker: {rps_per_worker}, num_attackers: {num_attackers}") # LOG
    if not target_urls:
        print("[Injector] No target URLs provided. Attack not started.")
        return
    if attack_active:
        print("[Injector] Attack already in progress.")
        return

    attack_active = True
    # Limpar threads antigas é importante se o orchestrator não garante que stop_http_flood completou totalmente
    # No entanto, com o stop_http_flood no orchestrator, isso pode ser redundante ou até problemático se as threads não pararam.
    # Se você tem `attacker_threads.clear()` em `stop_http_flood`, pode não precisar aqui.
    # Por segurança, vamos manter o clear aqui por enquanto.
    if attacker_threads:
        print(f"[DEBUG Injector start_http_flood] Clearing {len(attacker_threads)} existing attacker threads before starting new ones.")
        # Certifique-se que as threads antigas pararam se você vai limpar.
        # A lógica de stop/start no orchestrator deveria cuidar disso.
    attacker_threads.clear()

    num_targets = len(target_urls)
    print(f"[Injector] Starting HTTP flood with {num_attackers} attackers, ~{rps_per_worker * num_attackers} RPS total, across {num_targets} targets: {', '.join(target_urls)}")
    print(f"[DEBUG Injector start_http_flood] num_targets calculated as: {num_targets}") # LOG

    for i in range(num_attackers):
        # Distribuição Round Robin dos workers pelas URLs de destino
        if num_targets == 0: # Segurança caso target_urls se torne vazia inesperadamente
            print("[DEBUG Injector start_http_flood] No targets available for worker assignment. Breaking loop.")
            break
        target_url_for_this_worker = target_urls[i % num_targets] # <--- ALTERAÇÃO CHAVE
        
        print(f"[DEBUG Injector start_http_flood] Worker {i+1}: Assigning to target_url: {target_url_for_this_worker} (index {i % num_targets} from {num_targets} targets)") # LOG

        thread = threading.Thread(
            target=http_request_worker,
            args=(target_url_for_this_worker, rps_per_worker), # Cada thread pode ter uma URL diferente
            daemon=True,
            name=f"InjectorWorker-{i+1}"
        )
        attacker_threads.append(thread)
        thread.start()
        print(f"[DEBUG Injector start_http_flood] {len(attacker_threads)} attacker threads started.")
        print(f"[Injector] Worker {i+1} assigned to target: {target_url_for_this_worker}")


def start_http_flood_old(target_urls, duration_seconds=0, rps_per_worker=config.HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER, num_attackers=config.HTTP_ATTACK_NUM_ATTACKERS):
    global attacker_threads, attack_active
    # global global_total_requests_summary, global_total_errors_summary # Se for usar contadores globais

    if not target_urls:
        print("[Injector] No target URLs provided. Attack not started.")
        return

    if attack_active:
        print("[Injector] Attack is already in progress. Call stop_http_flood() first.")
        return

    print("[Injector] Initializing HTTP flood sequence...")
    attack_active = True # Seta a flag global para permitir que os workers iniciem/continuem seus loops

    # Resetar contadores globais de resumo se for usá-los para esta nova "campanha"
    # with global_stats_lock: # Proteger reset se acessado por múltiplas threads (improvável aqui)
    #    global_total_requests_summary = 0
    #    global_total_errors_summary = 0
    
    attacker_threads = [] # Limpa a lista de threads de um ataque anterior
    
    # Para simplificar, todos os atacantes mirarão na primeira URL da lista
    # Uma lógica mais complexa poderia distribuir os atacantes entre múltiplas URLs.
    effective_target_url = target_urls[0] 
    
    print(f"[Injector] Configuring {num_attackers} attacker threads to target: {effective_target_url}")
    print(f"[Injector] Each worker will aim for approximately {rps_per_worker:.2f} RPS.")

    for i in range(num_attackers):
        # Cria e inicia cada thread worker
        thread = threading.Thread(target=http_request_worker, args=(effective_target_url, rps_per_worker))
        attacker_threads.append(thread)
        thread.start()
    
    total_rps_aim = num_attackers * rps_per_worker
    print(f"[Injector] All {len(attacker_threads)} attacker threads have been launched. Aiming for a total of ~{total_rps_aim:.2f} RPS.")
    # Nota: O 'duration_seconds' é agora gerenciado pelo 'main_orchestrator.py',
    # que é responsável por chamar 'stop_http_flood' no momento apropriado.


def stop_http_flood_Old():
    global attacker_threads, attack_active
    # global global_total_requests_summary, global_total_errors_summary # Se for imprimir totais globais

    # Verifica se há um ataque ativo ou threads para parar
    if not attack_active and not attacker_threads:
        # print("[Injector] No attack currently active to stop, or threads already cleaned up.")
        return

    print("[Injector] Signaling HTTP flood workers to stop...")
    attack_active = False # Sinaliza aos workers para terminarem seus loops 'while attack_active:'

    # Esperar que todas as threads terminem sua iteração atual e saiam do loop.
    # O timeout para join é importante para não bloquear indefinidamente o chamador (main_orchestrator).
    # Deve ser suficiente para permitir que a última requisição e o print final do worker ocorram.
    # Um valor um pouco maior que o HTTP_REQUEST_TIMEOUT_SECONDS é uma boa heurística.
    thread_join_timeout = config.HTTP_REQUEST_TIMEOUT_SECONDS + 5.0 # Ex: timeout da req + alguns segundos de margem

    for thread_index, thread_obj in enumerate(attacker_threads):
        thread_obj.join(timeout=thread_join_timeout)
        if thread_obj.is_alive():
            # Se a thread ainda estiver viva após o timeout do join, algo pode estar errado (ex: presa em uma operação de bloqueio)
            print(f"  [Injector] Warning: Worker thread {thread_obj.ident} (index {thread_index}) did not terminate within the {thread_join_timeout}s timeout.")

    print(f"[Injector] All {len(attacker_threads)} attacker threads have been joined or timed out.")
    
    # Opcional: Imprimir um resumo global aqui, se os contadores globais foram implementados e atualizados.
    # print(f"[Injector] Overall Attack Summary: Total successful requests: {global_total_requests_summary}, Total errors: {global_total_errors_summary}")

    attacker_threads = [] # Limpa a lista de threads para a próxima chamada de start_http_flood
    # 'attack_active' já está False.



def http_request_worker_OLD(target_url, rps_per_worker):
    """
    Worker thread function. Sends requests to target_url at a specified RPS.
    """
    global attack_active
    session = requests.Session() # Use session for potential connection pooling
    sleep_interval = 1.0 / rps_per_worker if rps_per_worker > 0 else 1.0
    reqs_done = 0  # <<< ADICIONE ESTA LINHA
    errors = 0     # <<< ADICIONE ESTA LINHA

    print(f"  [Injector Worker {threading.get_ident()}] Started. Target: {target_url}, RPS: {rps_per_worker:.2f}, Interval: {sleep_interval:.4f}s")
    
    request_count = 0
    error_count = 0

    while attack_active:
        start_time = time.monotonic()
        try:
            # Adicionado timeout usando a configuração
            response = requests.get(target_url, timeout=config.HTTP_REQUEST_TIMEOUT_SECONDS) 
            if response.status_code == 200:
                reqs_done += 1
            else:
                # Você pode querer logar o status code aqui se não for 200
                print(f"  [Injector Worker {threading.get_ident()}] Target: {target_url}, Status: {response.status_code}")
                errors += 1
        except requests.exceptions.Timeout:
            print(f"  [Injector Worker {threading.get_ident()}] Target: {target_url}, Timeout error") # Descomente para depurar timeouts
            errors += 1
        except requests.exceptions.Timeout:
            print(f"  [Injector Worker {threading.get_ident()}] Target: {target_url}, Timeout error")  # Descomente para depurar timeouts
            errors += 1

            
 # OLD STUFF           
 #           response = session.get(target_url, timeout=2) # Timeout de 2 segundos
 #           # Você pode verificar response.status_code se precisar
 #           # if response.status_code == 200:
 #           #     pass
 #           request_count +=1
 #       except requests.exceptions.RequestException as e:
 #           # print(f"  [Injector Worker {threading.get_ident()}] Request error: {e}")
 #           error_count += 1
        
        # Calcular o tempo gasto e ajustar o sono para manter o RPS
        time_taken = time.monotonic() - start_time
        sleep_duration = sleep_interval - time_taken
        if sleep_duration > 0:
            time.sleep(sleep_duration)
        # Se time_taken > sleep_interval, o worker está atrasado (não consegue manter o RPS)
        # Não há muito o que fazer aqui além de registrar ou ajustar o RPS se for um problema.

    print(f"  [Injector Worker {threading.get_ident()}] Stopped. Total requests: {request_count}, Errors: {error_count}")



def stop_http_flood():
    global attack_active, attacker_threads # Garante que estamos modificando as globais

    print(f"[DEBUG Injector stop_http_flood] Called. Current attack_active: {attack_active}. Number of threads in global list: {len(attacker_threads)}")

    if not attack_active and not attacker_threads:
        print("[DEBUG Injector stop_http_flood] Attack already signaled as inactive AND no threads in list. Assuming already stopped.")
        # Mesmo se attack_active for False, ainda pode haver threads para join se stop_http_flood falhou antes
        # ou se os workers demoraram a verificar a flag. Por isso, não retornamos imediatamente só com attack_active=False.
        # Retornamos se AMBAS as condições são verdadeiras.
        return

    # 1. Sinalizar para todas as threads worker pararem seus loops
    attack_active = False
    print("[DEBUG Injector stop_http_flood] attack_active flag set to False.")

    # 2. Fazer uma cópia da lista de threads para dar join.
    # Isso é importante porque vamos limpar a lista global 'attacker_threads'
    # e não queremos modificar a lista sobre a qual estamos iterando para o join.
    threads_to_join = list(attacker_threads) # Cria uma cópia

    if not threads_to_join:
        print("[DEBUG Injector stop_http_flood] No threads were in the attacker_threads list to join (list was empty).")
        attacker_threads.clear() # Garante que está limpa se por acaso não estava
        return # Se não há threads, não há mais nada a fazer.

    print(f"[Injector] Attempting to stop and join {len(threads_to_join)} HTTP flood worker(s)...")

    # 3. Limpar a lista global de threads.
    # Novas chamadas a start_http_flood não devem ver estas threads que estão sendo paradas.
    # É feito antes do join para que, se o join demorar, o estado do injetor (lista de threads) já reflita "vazio".
    attacker_threads.clear()
    print("[DEBUG Injector stop_http_flood] Global attacker_threads list cleared.")

    # 4. Aguardar cada thread finalizar (join)
    for i, thread_obj in enumerate(threads_to_join):
        thread_name = thread_obj.name if hasattr(thread_obj, 'name') else f"Thread-{thread_obj.ident}"
        print(f"[DEBUG Injector stop_http_flood] Attempting to join thread: {thread_name} (Alive: {thread_obj.is_alive()})")

        if thread_obj.is_alive():
            # O timeout do join deve ser um pouco maior que o timeout da requisição HTTP,
            # para dar tempo à thread de finalizar sua última requisição e o loop.
            join_timeout = (config.HTTP_REQUEST_TIMEOUT_SECONDS if hasattr(config, 'HTTP_REQUEST_TIMEOUT_SECONDS') else 2) + 2.0 # Adiciona 2s de margem
            thread_obj.join(timeout=join_timeout)

            if thread_obj.is_alive():
                print(f"[Injector] Warning: Worker thread {thread_name} did not stop in time after {join_timeout}s timeout.")
            else:
                print(f"[DEBUG Injector stop_http_flood] Thread {thread_name} joined successfully.")
        else:
            print(f"[DEBUG Injector stop_http_flood] Thread {thread_name} was already not alive before join attempt.")

    print("[Injector] All active HTTP flood workers have been processed for stopping.")



def start_http_flood_OLD(target_host_port_pairs, duration_seconds):
    """
    Starts an HTTP flood attack against one or more target host:port pairs.
    target_host_port_pairs: A list of (host, port) tuples or a list of full URLs.
                            Example: [("localhost", 8080), ("localhost", 8081)]
                            Or: ["http://localhost:8080", "http://localhost:8081"]
    duration_seconds: How long the flood should last.
    """
    global attack_active, threads
    
    if not target_host_port_pairs:
        print("[Injector] No targets specified. Stopping flood.")
        return

    # Limpar threads de uma execução anterior, se houver
    if threads:
        print("[Injector] Warning: Previous threads found. Attempting to join them (should not happen if stop_http_flood was called).")
        attack_active = False # Garantir que threads antigos parem
        for t in threads:
            if t.is_alive():
                t.join(timeout=1.0) # Dar um pequeno timeout para threads antigos finalizarem
        threads = []


    attack_active = True
    threads = [] # Reiniciar a lista de threads

    num_attackers_per_target = config.HTTP_ATTACK_NUM_ATTACKERS
    rps_per_attacker = config.HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER
    
    total_rps_configured = 0

    print(f"[Injector] Starting HTTP flood for {duration_seconds} seconds.")
    print(f"[Injector] Configuration: Attackers per target = {num_attackers_per_target}, RPS per attacker = {rps_per_attacker}")

    for target_spec in target_host_port_pairs:
        target_url = ""
        if isinstance(target_spec, tuple) and len(target_spec) == 2:
            host, port = target_spec
            # Construir a URL baseada na configuração, assumindo HTTP por enquanto
            target_url = f"{config.HTTP_ATTACK_TARGET_URL_BASE}:{port}"
        elif isinstance(target_spec, str):
            target_url = target_spec # Assume a URL completa foi passada
        else:
            print(f"[Injector] Invalid target specification: {target_spec}. Skipping.")
            continue

        print(f"[Injector] Targeting URL: {target_url}")
        for i in range(num_attackers_per_target):
            thread = threading.Thread(target=http_request_worker, args=(target_url, rps_per_attacker), daemon=True)
            threads.append(thread)
            thread.start()
            total_rps_configured += rps_per_attacker
            
    print(f"[Injector] All {len(threads)} attacker threads started. Total configured RPS: {total_rps_configured:.2f}")

    if duration_seconds > 0:
        time.sleep(duration_seconds)
        print(f"[Injector] Flood duration ({duration_seconds}s) elapsed.")
        stop_http_flood()
    # Se duration_seconds <= 0, o flood continuará até stop_http_flood() ser chamado externamente.

def stop_http_flood():
    """
    Stops all active HTTP flood worker threads.
    """
    global attack_active, threads
    print(f"[DEBUG Injector stop_http_flood] Called. Current attack_active: {attack_active}. Number of threads: {len(attacker_threads)}")
    
    if not attack_active and not threads:
        print("[Injector] HTTP flood already stopped or not started.")
        print("[DEBUG Injector stop_http_flood] Already stopped or no threads to stop.")
        return

    print("[Injector] Stopping HTTP flood...")
    attack_active = False
    
    # Aguardar os threads finalizarem
    for t in threads:
        if t.is_alive():
            t.join(timeout=5.0) # Timeout para cada thread finalizar
            if t.is_alive():
                print(f"[Injector] Warning: Thread {t.ident} did not stop in time.")
    
    threads = [] # Limpar a lista de threads
    print("[Injector] All HTTP flood threads stopped.")


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
        config.HTTP_ATTACK_NUM_ATTACKERS = 2 # Sobrescrever para o teste
        config.HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER = 5 # Sobrescrever para o teste
        
        # O self-test pode usar uma URL completa diretamente ou a tupla (host, port)
        # start_http_flood([("localhost", test_host_port)], duration_seconds=10)
        start_http_flood([test_target_url], duration_seconds=10) # Inicia por 10s e para automaticamente

        # Se quiséssemos testar start/stop manualmente:
        # start_http_flood([test_target_url], duration_seconds=0) # Inicia e continua
        # print("[Self-Test] Flood started. Waiting 10 seconds before manual stop...")
        # time.sleep(10)
        # stop_http_flood()

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
