# edos_docker_simulation/main_orchestrator.py
import time
import csv
from simulator import docker_manager
from legacy import traffic_injector
from simulator import autoscaler_logic
from simulator import cost_calculator
from simulator import config

def main():
    # Inicialização antes do loop
    previous_num_instances = 0
    attack_has_started = False

    try:
        while (time.time() - start_time) < simulation_duration:
            current_loop_time = time.time()
            elapsed_time_seconds = current_loop_time - start_time

            # Coletar detalhes das instâncias ativas
            active_instances_details = docker_manager.get_active_instances_details()
            current_num_instances = len(active_instances_details)
            target_urls_for_injector = [details['url'] for details in active_instances_details]
            
            print(f"[DEBUG Orchestrator] Loop Iteration. Current Instances: {current_num_instances}, Prev Instances: {previous_num_instances}, Attack Started: {attack_has_started}")
            print(f"[DEBUG Orchestrator] Target URLs for injector (potential): {target_urls_for_injector}")

            # Gerenciar o estado do ataque de tráfego
            should_attack_be_active = (config.ATTACK_START_TIME_SECONDS <= elapsed_time_seconds < 
                                       (config.ATTACK_START_TIME_SECONDS + config.ATTACK_DURATION_SECONDS))
            print(f"[DEBUG Orchestrator] Should attack be active? {should_attack_be_active}")

            if should_attack_be_active:
                 # Verifique se o ataque precisa ser iniciado ou reiniciado
                 # A condição crucial é se o número de instâncias mudou ENQUANTO o ataque JÁ ESTAVA ATIVO
                 # OU se o ataque deve começar e ainda não começou.
                 needs_start_or_restart = False
                 if not attack_has_started: # Se deve começar e não começou
                     needs_start_or_restart = True
                     print("[DEBUG Orchestrator] Condition: Needs to start attack (was not started).")
                 elif previous_num_instances != current_num_instances and current_num_instances > 0: # Se número mudou e já estava rodando
                     needs_start_or_restart = True
                     print(f"[DEBUG Orchestrator] Condition: Needs to restart attack (num instances changed from {previous_num_instances} to {current_num_instances}).")
            
                  
                 if target_urls_for_injector and (not attack_has_started or previous_num_instances != current_num_instances):
                    if attack_has_started:
                        print("[Orchestrator] Number of instances changed. Restarting traffic injector...")
                        traffic_injector.stop_http_flood()
                        time.sleep(1)
                        print(f"[Orchestrator] Starting/Restarting HTTP flood. Target URLs: {target_urls_for_injector}")
                        traffic_injector.start_http_flood(
                           target_urls_for_injector,
                           config.HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER,
                           config.HTTP_ATTACK_NUM_ATTACKERS)
                        attack_has_started = True  # Marcar que o ataque (re)começou
                        
                        print(f"[DEBUG Orchestrator] attack_has_started set to True. prev_instances was {previous_num_instances}, current_instances is {current_num_instances}")
                    elif not target_urls_for_injector and attack_has_started:
                        print("[Orchestrator] Attack should be active, but no targets. Stopping injector.")
                        attack_has_started = False
                    
            elif attack_has_started:
                print("[Orchestrator] Attack duration ended or outside schedule. Stopping traffic injector.")
                traffic_injector.stop_http_flood()
                attack_has_started = False
                print("[DEBUG Orchestrator] attack_has_started set to False (attack period ended).")

            previous_num_instances = current_num_instances
            time.sleep(config.SIMULATION_INTERVAL_SECONDS)
    
    except KeyboardInterrupt:
        print("\n[Orchestrator] Simulation interrupted by user (Ctrl+C). Cleaning up...")
        if traffic_injector.attack_active:
            traffic_injector.stop_http_flood()
        docker_manager.cleanup_all_simulation_instances()
        print("[Orchestrator] Cleanup complete due to interruption.")
    except Exception as e_global:
        print(f"[Orchestrator] An unexpected error occurred: {e_global}")
        import traceback
        traceback.print_exc()
        print("[Orchestrator] Attempting cleanup after unexpected error...")
        if traffic_injector.attack_active:
            traffic_injector.stop_http_flood()
        docker_manager.cleanup_all_simulation_instances()
        print("[Orchestrator] Cleanup attempt complete after error.")

    print("[Orchestrator] Initializing simulation environment...")
    autoscaler = autoscaler_logic.Autoscaler()

    if not docker_manager.build_docker_image():
        print("[Orchestrator] CRITICAL: Failed to build Docker image. Aborting.")
        return
    if not docker_manager.ensure_docker_network():
        print("[Orchestrator] CRITICAL: Failed to ensure Docker network. Aborting.")
        return

    print("[Orchestrator] Cleaning up any pre-existing simulation instances...")
    docker_manager.cleanup_all_simulation_instances()

    active_containers = []
    next_instance_numeric_id = 1 # Para dar IDs numéricos sequenciais às instâncias

    print(f"[Orchestrator] Starting initial {config.MIN_INSTANCES} instance(s)...")
    for _ in range(config.MIN_INSTANCES):
        container = docker_manager.start_instance(next_instance_numeric_id)
        if container:
            active_containers.append(container)
            next_instance_numeric_id += 1
        else:
            print(f"[Orchestrator] CRITICAL: Failed to start initial instance {next_instance_numeric_id}. Aborting.")
            # Limpar o que foi iniciado se falhar no meio
            docker_manager.cleanup_all_simulation_instances()
            return
            
    if not active_containers and config.MIN_INSTANCES > 0:
        print("[Orchestrator] CRITICAL: No initial instances were started. Aborting.")
        return

    autoscaler.set_initial_instances(len(active_containers))
    print(f"[Orchestrator] {len(active_containers)} initial instance(s) running.")

    start_time = time.time()
    simulation_duration = config.SIMULATION_DURATION_SECONDS
    
    # Para o cálculo de custo
    instance_intervals_for_cost = []

    # Para o log de métricas
    # Limpar/criar arquivo de log no início da simulação
    with open(config.METRICS_LOG_FILE, 'w', newline='') as csvfile:
        fieldnames = ['elapsed_time_s', 'num_instances', 'average_cpu_percent', 'decision', 'active_containers_names']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
    print(f"[Orchestrator] Metrics will be logged to: {config.METRICS_LOG_FILE}")

    print(f"[Orchestrator] Starting simulation main loop for {simulation_duration} seconds.")
    print(f"[Orchestrator] Monitoring interval: {config.MONITOR_INTERVAL_SECONDS}s. Cooldown: {config.SCALE_COOLDOWN_SECONDS}s.")
    print(f"[Orchestrator] CPU Thresholds: Scale Up > {config.CPU_THRESHOLD_SCALE_UP}%, Scale Down < {config.CPU_THRESHOLD_SCALE_DOWN}%")
    if config.ATTACK_DURATION_SECONDS > 0:
        print(f"[Orchestrator] Traffic injection scheduled: Start at {config.ATTACK_START_TIME_SECONDS}s, Duration {config.ATTACK_DURATION_SECONDS}s.")
    else:
        print("[Orchestrator] No traffic injection scheduled (ATTACK_DURATION_SECONDS is 0 or less).")

    main_loop_iteration = 0
    while (time.time() - start_time) < simulation_duration:
        current_loop_time = time.time()
        elapsed_time_seconds = current_loop_time - start_time
        main_loop_iteration += 1
        print(f"--- Iteration {main_loop_iteration} | Time: {elapsed_time_seconds:.1f}s / {simulation_duration}s ---")

        # 1. Coletar Métricas
        cpu_percent_total = 0.0
        current_active_container_names = []
        valid_active_containers = [] # Lista para manter apenas os contêineres que ainda existem

        for container_obj in active_containers:
            try:
                # Verificar se o contêiner ainda existe antes de obter stats
                refreshed_container = docker_manager.client.containers.get(container_obj.id)
                stats = docker_manager.get_container_stats(refreshed_container) # get_container_stats já faz reload
                if stats:
                    cpu_percent_total += stats["cpu_percent"]
                    current_active_container_names.append(refreshed_container.name)
                    valid_active_containers.append(refreshed_container)
                else:
                    print(f"[Orchestrator] Warning: Could not get stats for {container_obj.name}. It might have been removed externally.")
            except docker_manager.docker.errors.NotFound:
                print(f"[Orchestrator] Warning: Container {container_obj.name} (ID: {container_obj.id}) not found. Removing from active list.")
            except Exception as e_stats:
                print(f"[Orchestrator] Error getting stats for {container_obj.name}: {e_stats}")
        
        active_containers = valid_active_containers # Atualizar a lista de contêineres ativos

        if active_containers:
            average_cpu = cpu_percent_total / len(active_containers)
        else:
            average_cpu = 0.0
            if config.MIN_INSTANCES > 0 and elapsed_time_seconds > config.MONITOR_INTERVAL_SECONDS: # Evitar alarme se for o início e 0 instâncias for ok
                print("[Orchestrator] CRITICAL WARNING: No active instances running, but MIN_INSTANCES > 0. This might be an issue.")


        print(f"[Orchestrator] Metrics: {len(active_containers)} active instance(s), Avg CPU: {average_cpu:.2f}%")

        # 2. Decidir sobre o escalonamento
        scaling_decision = autoscaler.decide_scaling(average_cpu, len(active_containers))

        # 3. Executar ações de escalonamento
        if scaling_decision == "SCALE_UP":
            if len(active_containers) < config.MAX_INSTANCES:
                print(f"[Orchestrator] Action: Scaling UP from {len(active_containers)} instance(s). Attempting to start instance {next_instance_numeric_id}.")
                new_container = docker_manager.start_instance(next_instance_numeric_id)
                if new_container:
                    active_containers.append(new_container)
                    next_instance_numeric_id += 1
                    print(f"[Orchestrator] Successfully started {new_container.name}. Now {len(active_containers)} instance(s).")
                else:
                    print(f"[Orchestrator] Failed to start new instance for SCALE_UP.")
            else:
                print(f"[Orchestrator] SCALE_UP requested by autoscaler, but already at MAX_INSTANCES ({config.MAX_INSTANCES}). No action taken.")
        
        elif scaling_decision == "SCALE_DOWN":
            if len(active_containers) > config.MIN_INSTANCES:
                container_to_stop = active_containers.pop() # Remove o último, poderia ser mais sofisticado
                print(f"[Orchestrator] Action: Scaling DOWN from {len(active_containers)+1} instance(s). Stopping {container_to_stop.name}.")
                if docker_manager.stop_instance(container_to_stop.name):
                    print(f"[Orchestrator] Successfully stopped {container_to_stop.name}. Now {len(active_containers)} instance(s).")
                else:
                    print(f"[Orchestrator] Failed to stop {container_to_stop.name} during SCALE_DOWN. Adding it back to active list for now.")
                    active_containers.append(container_to_stop) # Adicionar de volta se a parada falhou
            else:
                 print(f"[Orchestrator] SCALE_DOWN requested by autoscaler, but already at MIN_INSTANCES ({config.MIN_INSTANCES}). No action taken.")

        # Atualizar o autoscaler com o número real de instâncias após as ações
        autoscaler.record_scale_action(len(active_containers))

        # 4. Gerenciar o injetor de tráfego
        if config.ATTACK_DURATION_SECONDS > 0: # Somente gerenciar se um ataque está configurado
            should_attack_be_active = (config.ATTACK_START_TIME_SECONDS <= elapsed_time_seconds < 
                                       (config.ATTACK_START_TIME_SECONDS + config.ATTACK_DURATION_SECONDS))

            if should_attack_be_active and not traffic_injector.attack_active:
                if active_containers:
                    print("[Orchestrator] Starting traffic injector...")
                    target_urls_for_injector = []
                    for c_obj in active_containers:
                        try:
                            c_obj.reload() # <<< IMPORTANTE: Recarregar atributos antes de acessar portas
                            port_mappings = c_obj.attrs.get('NetworkSettings', {}).get('Ports', {}).get('80/tcp')
                            if port_mappings and isinstance(port_mappings, list) and len(port_mappings) > 0:
                                host_port = port_mappings[0].get('HostPort')
                                if host_port:
                                    # Usar localhost pois o tráfego é gerado do mesmo host onde o Docker roda
                                    target_urls_for_injector.append(f"http://localhost:{host_port}")
                                else:
                                    print(f"[Orchestrator] Warning: HostPort not found for {c_obj.name} in '80/tcp' mapping: {port_mappings[0]}")
                            else:
                                print(f"[Orchestrator] Warning: No '80/tcp' mapping found for {c_obj.name}. Ports: {c_obj.attrs.get('NetworkSettings', {}).get('Ports', {})}")
                        except Exception as e_port:
                            print(f"[Orchestrator] Error reloading or getting port for container {c_obj.name} for traffic injection: {e_port}")
                    
                    if target_urls_for_injector:
                        #traffic_injector.start_http_flood(target_urls_for_injector, duration_seconds=0) # duration_seconds=0 roda até ser parado
                        traffic_injector.start_http_flood(
                            target_urls_for_injector,
                            config.HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER, # Passa o RPS por worker do config
                            config.HTTP_ATTACK_NUM_ATTACKERS                     # Passa o número de atacantes do config
        		)
                        print(f"[Orchestrator] Traffic injector started, targeting: {target_urls_for_injector}")
                    else:
                        print("[Orchestrator] No valid target URLs found for traffic injector. Injector not started.")
                else:
                    print("[Orchestrator] Attack period started, but no active containers to target. Traffic injector not started.")
            
            elif not should_attack_be_active and traffic_injector.attack_active:
                print("[Orchestrator] Attack period ended or outside schedule. Stopping traffic injector.")
                traffic_injector.stop_http_flood()

        # 5. Registrar métricas no CSV
        log_metrics_to_csv(elapsed_time_seconds, len(active_containers), average_cpu, scaling_decision, current_active_container_names)
        
        # 6. Acumular dados para cálculo de custo
        # Adiciona o número de instâncias e a duração deste intervalo de monitoramento
        instance_intervals_for_cost.append((len(active_containers), config.MONITOR_INTERVAL_SECONDS))
        
        # 7. Aguardar próximo ciclo
        time_to_sleep = config.MONITOR_INTERVAL_SECONDS - (time.time() - current_loop_time)
        if time_to_sleep > 0:
            time.sleep(time_to_sleep)
        else:
            print(f"[Orchestrator] Warning: Loop iteration took longer than MONITOR_INTERVAL_SECONDS ({ (time.time() - current_loop_time):.2f}s). Not sleeping.")


    # --- Fim do loop de simulação ---
    print("\n[Orchestrator] Simulation duration reached.")

    if traffic_injector.attack_active:
        print("[Orchestrator] Stopping any active traffic injection...")
        traffic_injector.stop_http_flood()

    print("[Orchestrator] Cleaning up all simulation instances...")
    docker_manager.cleanup_all_simulation_instances()

    # Calcular custo total
    total_simulation_cost = cost_calculator.calculate_total_cost_from_intervals(instance_intervals_for_cost)
    print(f"[Orchestrator] Simulation Complete.")
    print(f"[Orchestrator] Total Fictional Cost of Simulation: ${total_simulation_cost:.4f}")
    print(f"[Orchestrator] Metrics logged in: {config.METRICS_LOG_FILE}")


def log_metrics_to_csv(elapsed_time, num_instances, average_cpu, decision, active_container_names_list):
    """
    Log metrics to a CSV file. Appends to the file.
    Header is written once at the start of the simulation.
    """
    try:
        with open(config.METRICS_LOG_FILE, 'a', newline='') as csvfile:
            # fieldnames definido no início da simulação ao criar o cabeçalho
            writer = csv.writer(csvfile)
            # Formatar nomes dos contêineres como string única separada por vírgula se houver mais de um
            containers_str = ";".join(active_container_names_list) if active_container_names_list else "N/A"
            
            writer.writerow([
                f"{elapsed_time:.1f}",
                num_instances,
                f"{average_cpu:.2f}",
                decision,
                containers_str
            ])
    except Exception as e:
        print(f"[Orchestrator] Error writing to metrics log file: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Orchestrator] Simulation interrupted by user (Ctrl+C). Cleaning up...")
        if traffic_injector.attack_active: # Tentar parar o injetor se estiver ativo
            traffic_injector.stop_http_flood()
        docker_manager.cleanup_all_simulation_instances() # Limpar Docker
        print("[Orchestrator] Cleanup complete due to interruption.")
    except Exception as e_global:
        print(f"[Orchestrator] An unexpected error occurred: {e_global}")
        import traceback
        traceback.print_exc()
        print("[Orchestrator] Attempting cleanup after unexpected error...")
        if traffic_injector.attack_active:
            traffic_injector.stop_http_flood()
        docker_manager.cleanup_all_simulation_instances()
        print("[Orchestrator] Cleanup attempt complete after error.")
