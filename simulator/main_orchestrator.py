import time
import csv
import json
from simulator.ground_truth import GroundTruth, encode_event_ids
from simulator.request_logger import RequestLogger
from dataclasses import replace
from simulator.experiment_config import ExperimentConfig

from simulator import attack_summary_logger
from simulator import normal_traffic_summary_logger
from simulator import host_stats
# Importar seus outros módulos (assumindo que estão no mesmo diretório ou no PYTHONPATH)
from simulator.tcpdump_sniffer import TcpdumpSniffer
from simulator import config

from simulator import autoscaler_logic
from simulator import cost_calculator # Se você tem um módulo separado para isso
import argparse


# --- Função de Logging para CSV (pode estar aqui ou em um módulo utilitário) ---

CLI_FIELDS = {
    "rps": ("attack", "rate"), "attackers": ("attack", "attackers"),
    "duration": (None, "duration_seconds"), "work_units": ("attack", "work_units"),
    "normal_rps": ("normal_traffic", "rate"), "normal_clients": ("normal_traffic", "clients"),
    "normal_work_units": ("normal_traffic", "work_units"),
    "attack_start": ("attack", "start_seconds"), "pulse_duration": ("attack", "duration_seconds"),
    "attack_duration": ("attack", "enabled"),
}


def configuration_from_args(args):
    experiment = ExperimentConfig.load(args.config) if args.config else ExperimentConfig()
    for flag, (group, key) in CLI_FIELDS.items():
        value = getattr(args, flag)
        if value is None:
            continue
        if flag == "attack_duration":
            if value < 0:
                raise ValueError("--attack-duration must be >= 0 (0 disables; positive enables)")
            value = value > 0
        if group is None:
            experiment = replace(experiment, **{key: value})
        else:
            experiment = replace(experiment, **{group: replace(getattr(experiment, group), **{key: value})})
    return experiment.resolve_seed()


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

    parser.add_argument("--config", help="JSON experiment configuration")
    parser.add_argument("--print-config", action="store_true", help="Validate and print effective configuration without Docker")
    args = parser.parse_args()
    if args.config and any(getattr(args, name) is not None for name in CLI_FIELDS):
        parser.error("--config cannot be combined with experimental CLI flags")
    try:
        args.experiment = configuration_from_args(args)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    return args

METRICS_FIELDS = ['run_id', 'timestamp', 'elapsed_seconds', 'elapsed_time_s',
                  'num_instances', 'average_cpu_percent', 'mem_usage', 'avg_rtt_ms',
                  'decision', 'active_containers_names', 'attack_active',
                  'active_event_ids', 'host_cpu_percent']


def log_metrics_to_csv(ground_truth, num_instances, avg_cpu, mem_usage, avg_rtt,
                       decision, active_names, host_cpu_percent):
    # Observation instant is sampled immediately before writing, after tick actions.
    timestamp, elapsed = ground_truth.clock.sample()
    active, ids = ground_truth.context(elapsed)
    with open(config.METRICS_LOG_FILE, 'a', newline='') as csvfile:
        csv.DictWriter(csvfile, fieldnames=METRICS_FIELDS).writerow({
            'run_id': ground_truth.run_id, 'timestamp': timestamp,
            'elapsed_seconds': elapsed, 'elapsed_time_s': round(elapsed, 2),
            'num_instances': num_instances, 'average_cpu_percent': round(avg_cpu, 2),
            'mem_usage': round(mem_usage, 2), 'avg_rtt_ms': round(avg_rtt, 2),
            'decision': decision, 'active_containers_names': ','.join(active_names),
            'attack_active': active, 'active_event_ids': encode_event_ids(ids),
            'host_cpu_percent': round(host_cpu_percent, 2),
        })


def _shutdown(reason):
    """Stop admission, drain producers, persist logs, then stop capture and infrastructure."""
    complete = True
    errors = []
    for module, stopper in [(globals().get('traffic_injectorV0'), 'stop_http_flood'),
                            (globals().get('normal_traffic'), 'stop_http_traffic')]:
        if module is not None:
            try:
                if stopper == 'stop_http_flood':
                    module.stop_http_flood(reason)
                else:
                    module.stop_http_traffic()
            except Exception as exc:
                errors.append(str(exc))
                complete = False
    for module in [globals().get('traffic_injectorV0'), globals().get('normal_traffic')]:
        if module is not None:
            try:
                drained = module.drain()
                if not drained:
                    errors.append(f"{module.__name__}: producer drain incomplete")
                complete = drained and complete
            except Exception as exc:
                errors.append(str(exc))
                complete = False
    if request_logger is not None:
        try:
            complete = request_logger.finalize() and complete
        except Exception as exc:
            errors.append(f'request log: {exc}')
            complete = False
    producers_drained = complete
    if request_logger is not None:
        try:
            request_logger.save_rtt(config.RTT_LOG_FILE)
        except Exception as exc:
            errors.append(f'RTT export: {exc}')
            complete = False
    if ground_truth is not None:
        try:
            ground_truth.finalize(reason, complete=producers_drained)
        except Exception as exc:
            errors.append(f'event export: {exc}')
            complete = False
    if sniffer is not None:
        try:
            sniffer.stop()
        except Exception as exc:
            errors.append(str(exc))
            complete = False
    if stats_collector is not None:
        try:
            stats_collector.stop()
        except Exception as exc:
            errors.append(f'stats collector: {exc}')
            complete = False
    # Avoid stopping backends while an incomplete drain still has HTTP calls.
    if globals().get('docker_manager') is not None and producers_drained:
        try:
            docker_manager.cleanup_all_simulation_instances()
        except Exception as exc:
            errors.append(f'backend cleanup: {exc}')
            complete = False
    if ground_truth is not None:
        with open(config.RUN_STATUS_FILE, 'w') as f:
            json.dump(dict(schema_version=1, experiment_id=ground_truth.experiment_id,
                           run_id=ground_truth.run_id,
                           experiment_start_timestamp=ground_truth.clock.epoch_initial,
                           experiment_start_monotonic=ground_truth.clock.monotonic_initial,
                           status='completed' if complete and reason == 'simulation_end' else 'incomplete',
                           end_reason=reason, producers_drained=producers_drained, errors=errors), f, indent=2)
            f.write('\n')
    if not complete:
        print('[Orchestrator] Incomplete run: drain/capture failures recorded in run_status.json.')


def main(experiment=None):
    global stats_collector, sniffer, ground_truth, request_logger
    stats_collector = sniffer = ground_truth = request_logger = None
    reason = 'simulation_end'
    try:
        _run(experiment)
    except KeyboardInterrupt:
        reason = 'interrupted'
        raise
    except BaseException:
        reason = 'error'
        raise
    finally:
        _shutdown(reason)


# --- Função Principal da Simulação ---
def _run(experiment=None):

    global stats_collector, sniffer, docker_manager, normal_traffic, traffic_injectorV0, ground_truth, request_logger
    experiment = (experiment or ExperimentConfig()).resolve_seed()
    print("[Orchestrator] Effective experiment configuration:\n" + experiment.to_json())
    from simulator import docker_manager
    from simulator import traffic_injectorV0
    from simulator import normal_traffic
    from simulator.stats_collector import StatsCollector
    from simulator.normal_traffic import get_average_rtt_ms
    from simulator.traffic_injectorV0 import get_average_rtt_attack_ms

    print("[Orchestrator] Initializing simulation environment...")

    # --- CORREÇÃO AQUI: Instanciar a classe Autoscaler ---
    autoscaler = autoscaler_logic.Autoscaler(experiment.autoscaler, experiment.infrastructure) # Cria uma instância da classe Autoscaler

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
    print(f"[Orchestrator] Starting initial {experiment.infrastructure.initial_instances} instance(s)...")
    for _ in range(experiment.infrastructure.initial_instances):
        # Assumindo que start_instance retorna o objeto container ou None
        container = docker_manager.start_instance(next_instance_numeric_id, experiment.server)
        if container:
            active_containers.append(container)
            next_instance_numeric_id += 1
        else:
            print(f"[Orchestrator] CRITICAL: Failed to start initial instance {next_instance_numeric_id}. Aborting.")
            docker_manager.cleanup_all_simulation_instances() # Limpar o que foi iniciado
            return
    
    # ... após preencher active_containers ...
    stats_collector = StatsCollector(client=docker_manager.client,
                        poll_interval=experiment.monitoring.stats_poll_interval_seconds,
                        history_seconds=experiment.monitoring.history_seconds)
    stats_collector.start()
    stats_collector.update_containers(active_containers)

            
    if not active_containers and experiment.infrastructure.min_instances > 0:
        print("[Orchestrator] CRITICAL: No initial instances were started. Aborting.")
        return

    # --- CORREÇÃO AQUI: Chamar o método na instância 'autoscaler' ---
    autoscaler.set_initial_instances(len(active_containers)) # Agora chama na instância
    print(f"[Orchestrator] {len(active_containers)} initial instance(s) running.")

    #Fazendo alterações no tempo para evitar drift
    ground_truth = GroundTruth(experiment.id, config.ATTACK_EVENTS_LOG_FILE)
    request_logger = RequestLogger(ground_truth, config.REQUEST_LOG_FILE)
    if experiment.attack.enabled:
        ground_truth.plan_event('attack_001', 'event_001', experiment.attack.profile,
                                experiment.attack.start_seconds, experiment.attack.end_seconds)
    normal_traffic.configure(experiment.normal_traffic, experiment.seed,
                             ground_truth=ground_truth, request_logger=request_logger)
    traffic_injectorV0.configure(experiment.attack, experiment.seed,
                                ground_truth=ground_truth, request_logger=request_logger)
    sniffer_port_range = (config.STARTING_HOST_PORT,
                         config.STARTING_HOST_PORT + experiment.infrastructure.max_instances - 1)
    sniffer = TcpdumpSniffer(interface='any', output_csv=config.TCPDUMP_OUTPUT_CSV,
                             ground_truth=ground_truth, port_range=sniffer_port_range)
    sniffer.start()
    start_time = ground_truth.clock.monotonic_initial
    next_tick = start_time

    simulation_duration = experiment.duration_seconds
    
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
    attack_has_started = False  # operational scheduling, never ground truth
    attack_activation_requested = False
    normal_traffic_has_started = False

    # Configurar arquivo de log CSV no início
    try:
        with open(config.METRICS_LOG_FILE, 'w', newline='') as csvfile:
            fieldnames = METRICS_FIELDS
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
    print(f"[Orchestrator] Monitoring interval: {experiment.monitoring.interval_seconds}s. Cooldown: {experiment.autoscaler.cooldown_seconds}s.")
    print(f"[Orchestrator] CPU Thresholds: Scale Up > {experiment.autoscaler.scale_up_threshold}%, Scale Down < {experiment.autoscaler.scale_down_threshold}%")
    if experiment.attack.enabled:
        print(f"[Orchestrator] Traffic injection scheduled: Start at {experiment.attack.start_seconds}s, Duration {experiment.attack.duration_seconds}s.")
    else:
        print("[Orchestrator] No traffic injection scheduled (attack.enabled=false).")

    # Janela única de ataque: começa em ATTACK_START_TIME_SECONDS, dura
    # PULSE_DURATION segundos, e não se repete (sem pulsos/cooldown).
    attack_start_time = experiment.attack.start_seconds
    attack_end = attack_start_time + experiment.attack.duration_seconds


    #Começo da iteração
    main_loop_iteration = 0
    while True:
        now = time.monotonic()
        elapsed_time_seconds = now - start_time

        if elapsed_time_seconds >= simulation_duration:
            break

        main_loop_iteration += 1
        print(f"\n--- Iteration {main_loop_iteration} | Time: {elapsed_time_seconds:.1f}s / {simulation_duration}s ---")

        # 1. Validar e Coletar Métricas das Instâncias Ativas

        stats_collector.update_containers(active_containers)

        current_num_instances_actual = len(active_containers)
        avg_cpu, avg_mem_app_mb, current_active_container_names = stats_collector.get_averages(
            window_seconds=experiment.monitoring.interval_seconds
        )

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



        if current_num_instances_actual == 0 and experiment.infrastructure.min_instances > 0 and elapsed_time_seconds > experiment.monitoring.interval_seconds:
                print("[Orchestrator] CRITICAL WARNING: No active instances running, but MIN_INSTANCES > 0.")
        print(f"[Orchestrator] Metrics: {current_num_instances_actual} active instance(s), "
            f"Avg CPU: {avg_cpu:.2f}%, Avg App MEM: {avg_mem_app_mb:.2f} MB")


        # 2. Decidir sobre o escalonamento
        # --- CORREÇÃO AQUI: ChamaFr o método na instância 'autoscaler' ---
        scaling_decision = autoscaler.decide_scaling(avg_cpu, current_num_instances_actual)


        scaling_triggered = False
        # 3. Executar ações de escalonamento (atualiza 'active_containers' e 'next_instance_numeric_id')
        if scaling_decision == "SCALE_UP":
            if current_num_instances_actual < experiment.infrastructure.max_instances:
                print(f"[Orchestrator] Action: Scaling UP from {current_num_instances_actual} instance(s). Attempting to start instance {next_instance_numeric_id}.")
                new_container = docker_manager.start_instance(next_instance_numeric_id, experiment.server)
                if new_container:
                    active_containers.append(new_container)
                    stats_collector.update_containers(active_containers)
                    next_instance_numeric_id += 1
                    print(f"[Orchestrator] Successfully started {new_container.name}. Now {len(active_containers)} instance(s).")
                    scaling_triggered = True

                else:
                    print(f"[Orchestrator] Failed to start new instance for SCALE_UP.")
            else:
                print(f"[Orchestrator] SCALE_UP requested, but already at MAX_INSTANCES ({experiment.infrastructure.max_instances}). No action.")
                scaling_triggered = True


        elif scaling_decision == "SCALE_DOWN":
            if current_num_instances_actual > experiment.infrastructure.min_instances:
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
                print(f"[Orchestrator] SCALE_DOWN requested, but already at MIN_INSTANCES ({experiment.infrastructure.min_instances}). No action.")
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

        if not experiment.attack.enabled:
                print(f"[Orchestrator] Starting Normal Traffic (if not already active). Target URLs for this call: {target_urls_for_injector}")
                normal_traffic.start_http_traffic(
                        target_urls_for_injector,
                        experiment.normal_traffic.rate,
                        experiment.normal_traffic.clients
                    )
                normal_traffic_has_started = True
                # Chamado toda iteração, incondicionalmente -- barato (só
                # atualiza o load balancer, não reinicia worker nenhum, ver
                # load_balancer.py). É isso que faz uma instância nova do
                # autoscaler passar a receber tráfego normal de verdade em vez
                # de ficar ociosa o run inteiro (ver changes.txt).
                normal_traffic.update_targets(target_urls_for_injector)

        elif experiment.attack.enabled:

            # Janela única e fixa: attack_start_time/attack_end nunca mudam
            # depois de calculados antes do loop (ver acima) — sem reagendamento.
            should_attack_be_active_now = (attack_start_time <= elapsed_time_seconds < attack_end)

            print(f"[DEBUG Orchestrator] Should attack be active now? {should_attack_be_active_now} (window: {attack_start_time}s-{attack_end}s)")

            #------------------COMEÇAR AQUI A LOGICA DE TRAFEGO NORMAL --------------------------

            if not should_attack_be_active_now and not normal_traffic_has_started:
                print(f"[Orchestrator] Starting Normal Traffic. Target URLs for this call: {target_urls_for_injector}")
                normal_traffic.start_http_traffic(
                        target_urls_for_injector,
                        experiment.normal_traffic.rate,
                        experiment.normal_traffic.clients
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
                if not attack_has_started and not attack_activation_requested:
                    if target_urls_for_injector: # Somente inicie se houver alvos
                        print(f"[Orchestrator] Starting HTTP flood. Target URLs for this call: {target_urls_for_injector}")
                        attack_activation_requested = True
                        started = traffic_injectorV0.start_http_flood(
                            target_urls_for_injector,
                            experiment.attack.rate,
                            experiment.attack.attackers, event_id="event_001"
                        )
                        attack_has_started = bool(started)
                        print(f"[DEBUG Orchestrator] attack_has_started={attack_has_started}.")
                    else:
                        print("[Orchestrator] Attack should start, but no valid target URLs yet. Deferring to next iteration.")
                elif attack_has_started:
                    # Ataque já rodando: só atualiza o load balancer com a lista
                    # de instâncias atual -- substitui o antigo padrão
                    # stop_http_flood() -> sleep(1) -> start_http_flood(), que
                    # deixava ~1s sem tráfego de ataque nenhum toda vez que a
                    # topologia mudava (ver changes.txt).
                    # Mesma proteção do tráfego normal acima: só atualiza se a
                    # lista vier não-vazia. Um hiccup transitório do Docker não
                    # pode zerar os alvos do ataque -- isso pararia os workers
                    # silenciosamente (sem stop_http_flood(), sem log, sem
                    # attack_has_started=False). Mantém os últimos alvos conhecidos em vez
                    # de zerar -- se as instâncias realmente caíram, os erros de
                    # conexão aparecem no log, em vez de ficarem escondidos.
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
        log_metrics_to_csv(ground_truth, num_instances_after_scaling, avg_cpu, avg_mem_app_mb,
                           avg_rtt, scaling_decision, current_active_container_names, host_cpu_percent)
        
        # 6. Acumular dados para cálculo de custo
        instance_intervals_for_cost.append((num_instances_after_scaling, experiment.monitoring.interval_seconds))
        
        # 7. Aguardar próximo ciclo
        # Calcular tempo real da iteração e dormir apenas o necessário
        next_tick += experiment.monitoring.interval_seconds
        sleep_time = next_tick - time.monotonic()
        print(f"[DEGUG Orchestrator Loop Duration] Loop Duration = {next_tick}")
        
        if sleep_time > 0:
            # print(f"[DEBUG Orchestrator] Sleeping for {time_to_sleep:.2f}s")
            time.sleep(sleep_time)
        else:
            
            print(f"[Orchestrator] Warning: Loop iteration took longer than MONITOR_INTERVAL_SECONDS ({experiment.monitoring.interval_seconds}s). Not sleeping.")

    # --- Fim do loop de simulação ---
    print("\n[Orchestrator] Simulation duration reached.")
    if hasattr(cost_calculator, 'calculate_total_cost_from_intervals'):
        total_simulation_cost = cost_calculator.calculate_total_cost_from_intervals(instance_intervals_for_cost, experiment.infrastructure.cost_per_instance_per_hour)
        print(f"[Orchestrator] Simulation Complete. Total Fictional Cost: ${total_simulation_cost:.4f}")
    else:
        print("[Orchestrator] Simulation Complete. Cost calculation module/function not found.")
    print(f"[Orchestrator] Metrics logged in: {config.METRICS_LOG_FILE}")

# --- Bloco de Execução Principal ---
if __name__ == "__main__":
    stats_collector = None

    try:

        args = parse_args()

        if args.print_config:
            print(args.experiment.to_json(), end="")
        else:
            main(args.experiment)
    except KeyboardInterrupt:
        print("[Orchestrator] Interrupted; finalization attempted.")
    except Exception:
        import traceback
        traceback.print_exc()
        raise
