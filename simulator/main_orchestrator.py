import time
import csv
import docker # Certifique-se de que 'docker' SDK está instalado (pip install docker)

from simulator import attack_summary_logger
from simulator import normal_traffic_summary_logger
from simulator import host_stats
# Importar seus outros módulos (assumindo que estão no mesmo diretório ou no PYTHONPATH)
from simulator.tcpdump_sniffer import TcpdumpSniffer
from simulator import config
from simulator import docker_manager
from simulator import autoscaler_logic
from simulator import traffic_injectorV0
from simulator import normal_traffic
from simulator import cost_calculator # Se você tem um módulo separado para isso
import argparse
from simulator.stats_collector import StatsCollector
from simulator.normal_traffic import get_average_rtt_ms, save_rtt_log
from simulator.traffic_injectorV0 import get_average_rtt_attack_ms


# --- Função de Logging para CSV (pode estar aqui ou em um módulo utilitário) ---

def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument("--rps", type=float, default=None)
    parser.add_argument("--attackers", type=int, default=None)
    parser.add_argument("--duration", type=int, default=None)
    parser.add_argument("--work-units", type=int, default=None)
    parser.add_argument("--attack-duration", type=int, default=None)
    parser.add_argument("--normal-rps", type=float, default=None)
    parser.add_argument("--normal-clients", type=int, default=None)
    parser.add_argument("--normal-work-units", type=int, default=None)
    parser.add_argument("--attack-start", type=int, default=None)
    parser.add_argument("--pulse-duration", type=int, default=None)

    return parser.parse_args()

def log_metrics_to_csv(elapsed_time, num_instances, avg_cpu, mem_usage,avg_rtt, decision, active_names, label, host_cpu_percent):
    try:
        with open(config.METRICS_LOG_FILE, 'a', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=['elapsed_time_s', 'num_instances', 'average_cpu_percent', 'mem_usage', 'avg_rtt_ms', 'decision', 'active_containers_names', 'label', 'host_cpu_percent'])
            writer.writerow({
                'elapsed_time_s': round(elapsed_time, 2),
                'num_instances': num_instances,
                'average_cpu_percent': round(avg_cpu, 2),
                'mem_usage': round(mem_usage,2),
                'avg_rtt_ms': round(avg_rtt,2),
                'decision': decision,
                'active_containers_names': ','.join(active_names) if active_names else '',
                'label': label,
                'host_cpu_percent': round(host_cpu_percent, 2),
            })
    except Exception as e:
        print(f"[Orchestrator] Error logging metrics to CSV: {e}")


# --- Função Principal da Simulação ---
def main():

    global stats_collector,sniffer

    print("[Orchestrator] Initializing simulation environment...")

    ##Packet Sniffer
    simulation_start_time = time.time()
    sniffer_port_range = (config.STARTING_HOST_PORT, config.STARTING_HOST_PORT + config.MAX_INSTANCES - 1)
    sniffer = TcpdumpSniffer(interface="any", output_csv=config.TCPDUMP_OUTPUT_CSV,
                              simulation_start_time=simulation_start_time,
                              port_range=sniffer_port_range)
    sniffer.start()
    sniffer.set_label("benign")

    
    # --- CORREÇÃO AQUI: Instanciar a classe Autoscaler ---
    autoscaler = autoscaler_logic.Autoscaler() # Cria uma instância da classe Autoscaler

    if not docker_manager.build_docker_image(): # Usando diretamente se são funções
        print("[Orchestrator] CRITICAL: Failed to build Docker image. Aborting.")
        return
    if not docker_manager.ensure_docker_network():
        print("[Orchestrator] CRITICAL: Failed to ensure Docker network. Aborting.")
        return

    print("[Orchestrator] Cleaning up any pre-existing simulation instances...")
    docker_manager.cleanup_all_simulation_instances()

    active_containers = [] # Lista de objetos container do Docker SDK
    next_instance_numeric_id = 1
    print(f"[Orchestrator] Starting initial {config.MIN_INSTANCES} instance(s)...")
    for _ in range(config.MIN_INSTANCES):
        # Assumindo que start_instance retorna o objeto container ou None
        container = docker_manager.start_instance(next_instance_numeric_id)
        if container:
            active_containers.append(container)
            next_instance_numeric_id += 1
        else:
            print(f"[Orchestrator] CRITICAL: Failed to start initial instance {next_instance_numeric_id}. Aborting.")
            docker_manager.cleanup_all_simulation_instances() # Limpar o que foi iniciado
            return
    
    # ... após preencher active_containers ...
    stats_collector = StatsCollector(client=docker_manager.client,
                        poll_interval=getattr(config, "DOCKER_STATS_POLL_INTERVAL_SECONDS", 1.0))
    stats_collector.start()
    stats_collector.update_containers(active_containers)

            
    if not active_containers and config.MIN_INSTANCES > 0:
        print("[Orchestrator] CRITICAL: No initial instances were started. Aborting.")
        return

    # --- CORREÇÃO AQUI: Chamar o método na instância 'autoscaler' ---
    autoscaler.set_initial_instances(len(active_containers)) # Agora chama na instância
    print(f"[Orchestrator] {len(active_containers)} initial instance(s) running.")

    #Fazendo alterações no tempo para evitar drift
    start_time = time.monotonic()
    next_tick = start_time

    simulation_duration = config.SIMULATION_DURATION_SECONDS
    
    instance_intervals_for_cost = [] # Para cálculo de custo

    # --- Inicialização da flag de ataque do injetor ---
    # Garante que o injetor comece limpo. (traffic_injector.py foi alterado para usar attacker_threads)
    traffic_injectorV0.attack_active = False 
    traffic_injectorV0.attacker_threads = [] 

    # --- Variáveis de estado do injetor ---
    # previous_num_instances_for_injector_logic foi removida: com o load balancer
    # client-side (load_balancer.py), não é mais preciso detectar "mudou o número
    # de instâncias?" pra decidir se reinicia o injetor -- update_targets() é
    # chamado toda iteração, incondicionalmente, sem custo de parar/recriar
    # worker nenhum. Ver changes.txt.
    attack_has_started = False  # Se o injetor foi iniciado pelo menos uma vez
    normal_traffic_has_started = False

    # Configurar arquivo de log CSV no início
    try:
        with open(config.METRICS_LOG_FILE, 'w', newline='') as csvfile:
            fieldnames = ['elapsed_time_s', 'num_instances', 'average_cpu_percent', 'mem_usage','avg_rtt_ms',
                  'decision', 'active_containers_names', 'label', 'host_cpu_percent']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
        print(f"[Orchestrator] Metrics will be logged to: {config.METRICS_LOG_FILE}")
    
        # NOVO: inicializa o CSV de resumo do ataque
        attack_summary_logger.init_attack_summary_log()
        print(f"[Orchestrator] Attack summary will be logged to: {config.ATTACK_SUMMARY_LOG_FILE}")

        # NOVO: idem para o tráfego normal (antes só existia o resumo do
        # ataque -- taxa de erro do tráfego normal era invisível, ver
        # normal_traffic_summary_logger.py e changes.txt).
        normal_traffic_summary_logger.init_normal_traffic_summary_log()
        print(f"[Orchestrator] Normal traffic summary will be logged to: {config.NORMAL_TRAFFIC_SUMMARY_LOG_FILE}")

    except Exception as e_csv_init:
        print(f"[Orchestrator] CRITICAL: Failed to initialize metrics log file {config.METRICS_LOG_FILE}. Error: {e_csv_init}. Aborting.")
        docker_manager.cleanup_all_simulation_instances()
        return

    #Inicializando simulação
    print(f"[Orchestrator] Starting simulation main loop for {simulation_duration} seconds.")
    print(f"[Orchestrator] Monitoring interval: {config.MONITOR_INTERVAL_SECONDS}s. Cooldown: {config.SCALE_COOLDOWN_SECONDS}s.")
    print(f"[Orchestrator] CPU Thresholds: Scale Up > {config.CPU_THRESHOLD_SCALE_UP}%, Scale Down < {config.CPU_THRESHOLD_SCALE_DOWN}%")
    if config.ATTACK_DURATION_SECONDS > 0:
        print(f"[Orchestrator] Traffic injection scheduled: Start at {config.ATTACK_START_TIME_SECONDS}s, Duration {config.PULSE_DURATION}s.")
    else:
        print("[Orchestrator] No traffic injection scheduled (ATTACK_DURATION_SECONDS is 0 or less).")

    # Janela única de ataque: começa em ATTACK_START_TIME_SECONDS, dura
    # PULSE_DURATION segundos, e não se repete (sem pulsos/cooldown).
    attack_start_time = config.ATTACK_START_TIME_SECONDS
    attack_end = attack_start_time + config.PULSE_DURATION


    #Começo da iteração
    main_loop_iteration = 0
    while True:
        now = time.monotonic()
        elapsed_time_seconds = now - start_time

        if elapsed_time_seconds >= simulation_duration:
            break

        main_loop_iteration += 1
        sniffer.set_label("benign")
        print(f"\n--- Iteration {main_loop_iteration} | Time: {elapsed_time_seconds:.1f}s / {simulation_duration}s ---")

        # 1. Validar e Coletar Métricas das Instâncias Ativas

        stats_collector.update_containers(active_containers)

        current_num_instances_actual = len(active_containers)
        avg_cpu, avg_mem_app_mb, current_active_container_names = stats_collector.get_averages(
            window_seconds=config.MONITOR_INTERVAL_SECONDS
        )

        # O rótulo do CSV de métricas reflete se o ataque estava ativo durante a
        # janela que avg_cpu ACABOU de medir (estado herdado da decisão da
        # iteração ANTERIOR), não a decisão de start/stop tomada mais abaixo
        # nesta mesma iteração — assim label e average_cpu_percent sempre
        # descrevem a mesma janela de tempo.
        label = 'attack' if attack_has_started else 'normal'

        #Pegando os RTTs
        # get_average_rtt_ms() é chamado TODA iteração, mesmo durante o
        # ataque, para drenar normal_traffic.rtt_measurements continuamente.
        # Tráfego normal nunca para durante o ataque, então sem isso essa
        # lista fica acumulando sem ser lida pela janela de ataque inteira
        # (até ~140s) — a primeira chamada depois que o ataque termina então
        # despeja uma média sobre esse período todo numa única linha, em vez
        # do snapshot de 5s que as outras linhas do CSV representam.
        normal_avg_rtt = get_average_rtt_ms()
        if attack_has_started:
            avg_rtt = get_average_rtt_attack_ms()
            print(f"[Orchestrator]RTT = {avg_rtt}")

        else :
            avg_rtt = normal_avg_rtt
            print(f"[Orchestrator]RTT = {avg_rtt}")



        if current_num_instances_actual == 0 and config.MIN_INSTANCES > 0 and elapsed_time_seconds > config.MONITOR_INTERVAL_SECONDS:
                print("[Orchestrator] CRITICAL WARNING: No active instances running, but MIN_INSTANCES > 0.")
        print(f"[Orchestrator] Metrics: {current_num_instances_actual} active instance(s), "
            f"Avg CPU: {avg_cpu:.2f}%, Avg App MEM: {avg_mem_app_mb:.2f} MB")


        # 2. Decidir sobre o escalonamento
        # --- CORREÇÃO AQUI: ChamaFr o método na instância 'autoscaler' ---
        scaling_decision = autoscaler.decide_scaling(avg_cpu, current_num_instances_actual)


        scaling_triggered = False
        # 3. Executar ações de escalonamento (atualiza 'active_containers' e 'next_instance_numeric_id')
        if scaling_decision == "SCALE_UP":
            if current_num_instances_actual < config.MAX_INSTANCES:
                print(f"[Orchestrator] Action: Scaling UP from {current_num_instances_actual} instance(s). Attempting to start instance {next_instance_numeric_id}.")
                new_container = docker_manager.start_instance(next_instance_numeric_id)
                if new_container:
                    active_containers.append(new_container)
                    stats_collector.update_containers(active_containers)
                    next_instance_numeric_id += 1
                    print(f"[Orchestrator] Successfully started {new_container.name}. Now {len(active_containers)} instance(s).")
                    scaling_triggered = True

                else:
                    print(f"[Orchestrator] Failed to start new instance for SCALE_UP.")
            else:
                print(f"[Orchestrator] SCALE_UP requested, but already at MAX_INSTANCES ({config.MAX_INSTANCES}). No action.")
                scaling_triggered = True


        elif scaling_decision == "SCALE_DOWN":
            if current_num_instances_actual > config.MIN_INSTANCES:
                # Simples: para o último da lista. Poderia ser mais sofisticado.
                container_to_stop = active_containers.pop()
                stats_collector.update_containers(active_containers)
                print(f"[Orchestrator] Action: Scaling DOWN from {current_num_instances_actual} instance(s). Stopping {container_to_stop.name}.")
                if docker_manager.stop_instance(container_to_stop.name): # stop_instance deve retornar True/False
                    print(f"[Orchestrator] Successfully stopped {container_to_stop.name}. Now {len(active_containers)} instance(s).")
                    scaling_triggered = True

                else:
                    print(f"[Orchestrator] Failed to stop {container_to_stop.name}. Adding back to active list (caution).")
                    active_containers.append(container_to_stop) # Adicionar de volta se a parada falhou
            else:
                print(f"[Orchestrator] SCALE_DOWN requested, but already at MIN_INSTANCES ({config.MIN_INSTANCES}). No action.")
                scaling_triggered = True

        if scaling_triggered:
            autoscaler.record_scale_action(len(active_containers))
                
        num_instances_after_scaling = len(active_containers)

        # 4. Gerenciar o injetor de tráfego (COM LÓGICA DE REINÍCIO E LOGS)
        target_urls_for_injector = []
        if active_containers: # Somente tente obter URLs se houver contêineres ativos
            for c_obj in active_containers:
                try:
                    c_obj.reload() # Essencial para obter os atributos mais recentes, incluindo portas
                    port_mappings = c_obj.attrs.get('NetworkSettings', {}).get('Ports', {}).get(f'{config.APP_CONTAINER_PORT}/tcp')
                    if port_mappings and isinstance(port_mappings, list) and len(port_mappings) > 0:
                        host_port = port_mappings[0].get('HostPort')
                        if host_port:
                            target_urls_for_injector.append(f"http://localhost:{host_port}")
                        else:
                            print(f"[Orchestrator] Warning: HostPort not found for {c_obj.name} in '{config.APP_CONTAINER_PORT}/tcp' mapping: {port_mappings[0]}")
                    else:
                        print(f"[Orchestrator] Warning: No '{config.APP_CONTAINER_PORT}/tcp' mapping found or empty for {c_obj.name}. Ports: {c_obj.attrs.get('NetworkSettings', {}).get('Ports', {})}")
                except Exception as e_port:
                    print(f"[Orchestrator] Error reloading or getting port for container {c_obj.name} for traffic injection: {e_port}")


        print(f"[DEBUG Orchestrator] Iteration Start. Instances Before Injector Logic: {num_instances_after_scaling}, Attack Started Flag: {attack_has_started}, Normal Traffic Started Flag: {normal_traffic_has_started}")
        print(f"[DEBUG Orchestrator] URLs derived for injector (if active): {target_urls_for_injector}")

        if config.ATTACK_DURATION_SECONDS == 0:
                print(f"[Orchestrator] Starting Normal Traffic (if not already active). Target URLs for this call: {target_urls_for_injector}")
                normal_traffic.start_http_traffic(
                        target_urls_for_injector,
                        config.HTTP_NORMAL_RPS_PER_CLIENT,
                        config.HTTP_NORMAL_NUM_CLIENTS
                    )
                normal_traffic_has_started = True
                # Chamado toda iteração, incondicionalmente -- barato (só
                # atualiza o load balancer, não reinicia worker nenhum, ver
                # load_balancer.py). É isso que faz uma instância nova do
                # autoscaler passar a receber tráfego normal de verdade em vez
                # de ficar ociosa o run inteiro (ver changes.txt).
                normal_traffic.update_targets(target_urls_for_injector)

        elif config.ATTACK_DURATION_SECONDS > 0:
            sniffer.set_label("benign")

            # Janela única e fixa: attack_start_time/attack_end nunca mudam
            # depois de calculados antes do loop (ver acima) — sem reagendamento.
            should_attack_be_active_now = (attack_start_time <= elapsed_time_seconds < attack_end)

            print(f"[DEBUG Orchestrator] Should attack be active now? {should_attack_be_active_now} (window: {attack_start_time}s-{attack_end}s)")

            #------------------COMEÇAR AQUI A LOGICA DE TRAFEGO NORMAL --------------------------

            if not should_attack_be_active_now and not normal_traffic_has_started:
                print(f"[Orchestrator] Starting Normal Traffic. Target URLs for this call: {target_urls_for_injector}")
                normal_traffic.start_http_traffic(
                        target_urls_for_injector,
                        config.HTTP_NORMAL_RPS_PER_CLIENT,
                        config.HTTP_NORMAL_NUM_CLIENTS
                    )
                normal_traffic_has_started = True

            # Atualiza o load balancer do tráfego normal toda iteração em que já
            # estiver ativo (inclusive durante a janela de ataque -- tráfego
            # normal nunca para, ver changes.txt) -- sem parar/recriar worker.
            # Só atualiza se a lista vier não-vazia: um hiccup transitório do
            # Docker (reload() falhando pra todos os containers numa única
            # iteração, sem mudança real de topologia -- ver changes.txt)
            # não pode zerar os alvos do load balancer, senão os workers
            # ficam girando em espera silenciosamente até o próximo alvo
            # válido, mascarando o hiccup como "sem tráfego configurado" no
            # normal_traffic_summary_log.csv. Se a lista realmente ficou vazia
            # (todas as instâncias caíram de verdade, não só um glitch de
            # leitura), os workers continuam tentando os últimos alvos
            # conhecidos e os erros de conexão aparecem no log -- visível,
            # em vez de silenciosamente escondido.
            if normal_traffic_has_started:
                if target_urls_for_injector:
                    normal_traffic.update_targets(target_urls_for_injector)
                else:
                    print("[Orchestrator] Warning: target_urls_for_injector veio vazio nesta iteração "
                          "(possível hiccup transitório do Docker) -- mantendo os últimos alvos "
                          "conhecidos do tráfego normal em vez de zerar.")

            if should_attack_be_active_now:
                if not attack_has_started: # Se o ataque deve começar e ainda não começou
                    if target_urls_for_injector: # Somente inicie se houver alvos
                        print(f"[Orchestrator] Starting HTTP flood. Target URLs for this call: {target_urls_for_injector}")
                        traffic_injectorV0.start_http_flood(
                            target_urls_for_injector,
                            config.HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER,
                            config.HTTP_ATTACK_NUM_ATTACKERS
                        )
                        sniffer.set_label("attack")
                        attack_has_started = True
                        print(f"[DEBUG Orchestrator] attack_has_started flag set to TRUE.")
                    else:
                        print("[Orchestrator] Attack should start, but no valid target URLs yet. Deferring to next iteration.")
                else:
                    # Ataque já rodando: só atualiza o load balancer com a lista
                    # de instâncias atual -- substitui o antigo padrão
                    # stop_http_flood() -> sleep(1) -> start_http_flood(), que
                    # deixava ~1s sem tráfego de ataque nenhum toda vez que a
                    # topologia mudava (ver changes.txt).
                    # Mesma proteção do tráfego normal acima: só atualiza se a
                    # lista vier não-vazia. Um hiccup transitório do Docker não
                    # pode zerar os alvos do ataque -- isso pararia os workers
                    # silenciosamente (sem stop_http_flood(), sem log, sem
                    # attack_has_started=False) e o rótulo 'attack' continuaria
                    # sendo gravado numa janela sem nenhum pacote de ataque de
                    # verdade saindo. Mantém os últimos alvos conhecidos em vez
                    # de zerar -- se as instâncias realmente caíram, os erros de
                    # conexão aparecem no log, em vez de ficarem escondidos.
                    sniffer.set_label("attack")
                    if target_urls_for_injector:
                        traffic_injectorV0.update_targets(target_urls_for_injector)
                    else:
                        print("[Orchestrator] Warning: target_urls_for_injector veio vazio nesta "
                              "iteração (possível hiccup transitório do Docker) -- mantendo os "
                              "últimos alvos conhecidos do ataque em vez de zerar.")
            elif attack_has_started: # Se o período de ataque terminou
                print("[Orchestrator] Attack duration ended or outside schedule. Stopping HTTP flood.")
                traffic_injectorV0.stop_http_flood()
                attack_has_started = False
                print("[DEBUG Orchestrator] attack_has_started flag set to FALSE (attack period ended).")

        # 5. Registrar métricas no CSV
        host_cpu_percent = host_stats.get_host_cpu_percent()
        log_metrics_to_csv(elapsed_time_seconds, num_instances_after_scaling, avg_cpu, avg_mem_app_mb,avg_rtt, scaling_decision, current_active_container_names,label, host_cpu_percent)
        
        # 6. Acumular dados para cálculo de custo
        instance_intervals_for_cost.append((num_instances_after_scaling, config.MONITOR_INTERVAL_SECONDS))
        
        # 7. Aguardar próximo ciclo
        # Calcular tempo real da iteração e dormir apenas o necessário
        next_tick += config.MONITOR_INTERVAL_SECONDS
        sleep_time = next_tick - time.monotonic()
        print(f"[DEGUG Orchestrator Loop Duration] Loop Duration = {next_tick}")
        
        if sleep_time > 0:
            # print(f"[DEBUG Orchestrator] Sleeping for {time_to_sleep:.2f}s")
            time.sleep(sleep_time)
        else:
            
            print(f"[Orchestrator] Warning: Loop iteration took longer than MONITOR_INTERVAL_SECONDS ({config.MONITOR_INTERVAL_SECONDS}s). Not sleeping.")

    # --- Fim do loop de simulação ---
    print("\n[Orchestrator] Simulation duration reached.")
    print("[Orchestrator] Saving RTT log...")
    save_rtt_log()

    try:
        sniffer.stop()
    except Exception as e:
        print(f"[Sniffer] Error stopping tcpdump: {e}")

    if traffic_injectorV0.attack_active: # Verifica o estado real no módulo traffic_injector
        print("[Orchestrator] Stopping any active traffic injection at end of simulation...")
        traffic_injectorV0.stop_http_flood()

    # O tráfego normal roda a simulação inteira por design e nunca é parado
    # dentro do loop — precisa ser parado explicitamente aqui, senão os
    # workers (daemon threads) continuam vivos até o interpretador encerrar,
    # o que corre risco de tentar agendar em _send_pool já finalizada.
    print("[Orchestrator] Stopping normal traffic...")
    normal_traffic.stop_http_traffic()

    print("[Orchestrator] Cleaning up all simulation instances...")
    docker_manager.cleanup_all_simulation_instances()

    try:
        print("[Stats_Collector] Stopping stats collector thread...")
        stats_collector.stop()
    except Exception:
        pass

    if hasattr(cost_calculator, 'calculate_total_cost_from_intervals'):
        total_simulation_cost = cost_calculator.calculate_total_cost_from_intervals(instance_intervals_for_cost)
        print(f"[Orchestrator] Simulation Complete. Total Fictional Cost: ${total_simulation_cost:.4f}")
    else:
        print("[Orchestrator] Simulation Complete. Cost calculation module/function not found.")
    print(f"[Orchestrator] Metrics logged in: {config.METRICS_LOG_FILE}")

# --- Bloco de Execução Principal ---
if __name__ == "__main__":
    stats_collector = None

    try:

        args = parse_args()

        if args.rps is not None:
            config.HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER = args.rps
            print(f"Attacker RPS set to: {config.HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER}")


        if args.attackers is not None:
            config.HTTP_ATTACK_NUM_ATTACKERS = args.attackers
            print(f"Number of attackers set to: {config.HTTP_ATTACK_NUM_ATTACKERS}")


        if args.duration is not None:
            config.SIMULATION_DURATION_SECONDS = args.duration
            print(f"Simulation duration set to: {config.SIMULATION_DURATION_SECONDS}")

        if args.work_units is not None:
            config.ATTACK_WORK_UNITS = args.work_units
            print(f"Attack work units set to: {config.ATTACK_WORK_UNITS}")

        if args.attack_duration is not None:
            config.ATTACK_DURATION_SECONDS = args.attack_duration
            print(f"Attack duration set to: {config.ATTACK_DURATION_SECONDS}")

        if args.normal_rps is not None:
            config.HTTP_NORMAL_RPS_PER_CLIENT = args.normal_rps
            print(f"Normal traffic RPS per client set to: {config.HTTP_NORMAL_RPS_PER_CLIENT}")

        if args.normal_clients is not None:
            config.HTTP_NORMAL_NUM_CLIENTS = args.normal_clients
            print(f"Normal traffic number of clients set to: {config.HTTP_NORMAL_NUM_CLIENTS}")

        if args.normal_work_units is not None:
            config.NORMAL_WORK_UNITS = args.normal_work_units
            print(f"Normal traffic work units set to: {config.NORMAL_WORK_UNITS}")

        if args.attack_start is not None:
            config.ATTACK_START_TIME_SECONDS = args.attack_start
            print(f"Attack start time set to: {config.ATTACK_START_TIME_SECONDS}")

        if args.pulse_duration is not None:
            config.PULSE_DURATION = args.pulse_duration
            print(f"Attack window duration set to: {config.PULSE_DURATION}")

        main()
    except KeyboardInterrupt:
        print("\n[Orchestrator] Simulation interrupted by user (Ctrl+C). Attempting cleanup...")
        print("[Orchestrator] Saving RTT log...")
        save_rtt_log()
        if hasattr(traffic_injectorV0, 'attack_active') and traffic_injectorV0.attack_active:
            print("[Orchestrator] Stopping traffic injector due to interruption...")
            traffic_injectorV0.stop_http_flood()
            normal_traffic.stop_http_traffic()

        try:
            if 'sniffer' in globals():
                sniffer.stop()
        except Exception:
            pass

        # pare a thread de stats se existir
        try:
            if stats_collector is not None:
                print("[Stats_Collector] Stopping stats collector thread...")
                stats_collector.stop()
        except Exception:
            pass

        if hasattr(docker_manager, 'cleanup_all_simulation_instances'):
            print("[Orchestrator] Cleaning up Docker instances due to interruption...")
            docker_manager.cleanup_all_simulation_instances()

        print("[Orchestrator] Cleanup attempt complete due to interruption.")
    except Exception as e_global:
        print(f"[Orchestrator] An UNEXPECTED GLOBAL ERROR occurred: {e_global}")
        import traceback
        traceback.print_exc()
        print("[Orchestrator] Attempting cleanup after unexpected global error...")
        if hasattr(traffic_injectorV0, 'attack_active') and traffic_injectorV0.attack_active:
            print("[Orchestrator] Stopping traffic injector due to error...")
            traffic_injectorV0.stop_http_flood()
            normal_traffic.stop_http_traffic()

        try:
            if 'sniffer' in globals():
                sniffer.stop()
        except Exception:
            pass
        
        # pare a thread de stats se existir
        try:
            if stats_collector is not None:
                print("[Stats_Collector] Stopping stats collector thread...")
                stats_collector.stop()
        except Exception:
            pass

        if hasattr(docker_manager, 'cleanup_all_simulation_instances'):
            print("[Orchestrator] Cleaning up Docker instances due to error...")
            docker_manager.cleanup_all_simulation_instances()
        print("[Orchestrator] Cleanup attempt complete after error.")
