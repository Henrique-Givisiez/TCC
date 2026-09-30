# edos_docker_simulation/autoscaler_logic.py
import time
from simulator.experiment_config import AutoscalerConfig, InfrastructureConfig

class Autoscaler:
    def __init__(self, settings=None, infrastructure=None):
        self.settings = settings or AutoscalerConfig()
        self.infrastructure = infrastructure or InfrastructureConfig()
        self.current_instances = 0 # O orquestrador irá definir o valor inicial
        self.cooldown_until = 0.0
        print("[Autoscaler] Initialized.")

    def set_initial_instances(self, num_instances):
        """
        Sets the initial number of running instances.
        Usually called by the orchestrator after starting initial instances.
        """
        self.current_instances = num_instances
        print(f"[Autoscaler] Initial number of instances set to: {self.current_instances}")


    def decide_scaling(self, average_cpu_percent, current_num_instances):
        """
        Decides whether to scale up, scale down, or do nothing.

        Args:
            average_cpu_percent (float): The average CPU utilization across all active instances.
            current_num_instances (int): The current number of active instances (confirmado pelo docker_manager).

        Returns:
            str: "SCALE_UP", "SCALE_DOWN", or "NO_ACTION".
        """
        self.current_instances = current_num_instances # Sincronizar com a realidade

        if not self.settings.enabled:
            return "NO_ACTION"

        # Verificar o cooldown
        current_time = time.monotonic()

        remaining = self.cooldown_until - current_time

        if remaining <= 1:
            self.cooldown_until = current_time
        
        else:
            print(f'[Autoscaler]In cooldown: {remaining}')
            return "NO_ACTION"


        action = "NO_ACTION"

        # Lógica de Scale Up
        if average_cpu_percent > self.settings.scale_up_threshold:
            if self.current_instances < self.infrastructure.max_instances:
                action = "SCALE_UP"
                print(f"[Autoscaler] Decision: SCALE_UP. Avg CPU: {average_cpu_percent:.2f}% > {self.settings.scale_up_threshold}%. Current instances: {self.current_instances}, Max: {self.infrastructure.max_instances}")
            else:
                print(f"[Autoscaler] Condition for SCALE_UP met (Avg CPU: {average_cpu_percent:.2f}%), but already at MAX_INSTANCES ({self.infrastructure.max_instances}). No action.")
        
        # Lógica de Scale Down (só considera se não for escalar para cima)
        elif average_cpu_percent < self.settings.scale_down_threshold:
            if self.current_instances > self.infrastructure.min_instances:
                action = "SCALE_DOWN"
                print(f"[Autoscaler] Decision: SCALE_DOWN. Avg CPU: {average_cpu_percent:.2f}% < {self.settings.scale_down_threshold}%. Current instances: {self.current_instances}, Min: {self.infrastructure.min_instances}")
            else:
                print(f"[Autoscaler] Condition for SCALE_DOWN met (Avg CPU: {average_cpu_percent:.2f}%), but already at MIN_INSTANCES ({self.infrastructure.min_instances}). No action.")
        
        # Nenhuma ação se estiver entre os limiares
        else:
            print(f"[Autoscaler] Decision: NO_ACTION. Avg CPU: {average_cpu_percent:.2f}% is within thresholds ({self.settings.scale_down_threshold}% - {self.settings.scale_up_threshold}%).")
            action = "NO_ACTION"

        if action != "NO_ACTION":
            self.cooldown_until = current_time + self.settings.cooldown_seconds
            # O orquestrador atualizará self.current_instances após a ação ser realmente executada
            
        return action

    def record_scale_action(self, new_instance_count):
        """
        Called by the orchestrator after a scaling action has been successfully performed
        to update the autoscaler's view of the current instance count and reset cooldown.
        """
        print(f"[Autoscaler] Scale action recorded. New instance count: {new_instance_count}. Cooldown timer reset.")
        self.current_instances = new_instance_count
        # self.last_scale_action_time = time.time() # Já definido em decide_scaling se houve ação

        # --- NOVOS MÉTODOS PARA O EDOS ---
    def is_in_cooldown(self):
        """
        Checks if the autoscaler is currently in a cooldown period.
        """
        print("[Autoscaler]In cooldown period...")
        return time.monotonic() < self.cooldown_until

    def get_cooldown_remaining(self):
        """
        Returns the remaining cooldown time in seconds.
        Returns 0 if not in cooldown or if cooldown has elapsed.
        """
        remaining = max(self.cooldown_until - time.monotonic())
        print(f"[Autoscaler]{remaining}")
        return max(0.0, remaining) # Garante que não retorne valores negativos

# --- Self-test section (optional, for direct testing of this module) ---
if __name__ == "__main__":
    print("--- Running autoscaler_logic.py self-test ---")

    autoscaler = Autoscaler(AutoscalerConfig(scale_down_threshold=20.0, cooldown_seconds=5),
                           InfrastructureConfig(max_instances=3))
    autoscaler.set_initial_instances(1) # Começa com 1 instância

    print(f"\nInitial state: {autoscaler.current_instances} instances. Min: {autoscaler.infrastructure.min_instances}, Max: {autoscaler.infrastructure.max_instances}, Cooldown: {autoscaler.settings.cooldown_seconds}s")
    print(f"Thresholds: Scale Up > {autoscaler.settings.scale_up_threshold}%, Scale Down < {autoscaler.settings.scale_down_threshold}%")

    # Teste 1: CPU alto, deve escalar para cima
    print("\nTest 1: High CPU (70%), 1 instance")
    decision = autoscaler.decide_scaling(average_cpu_percent=70.0, current_num_instances=1)
    print(f"Decision: {decision}")
    assert decision == "SCALE_UP"
    # Simular que o orquestrador escalou:
    if decision == "SCALE_UP": autoscaler.record_scale_action(2)
    print(f"Instances after action: {autoscaler.current_instances}")


    # Teste 2: CPU normal, em cooldown, não deve fazer nada
    print("\nTest 2: Normal CPU (40%), 2 instances, IN COOLDOWN")
    time.sleep(2) # Esperar menos que o cooldown
    decision = autoscaler.decide_scaling(average_cpu_percent=40.0, current_num_instances=2)
    print(f"Decision: {decision}")
    assert decision == "NO_ACTION"
    print(f"Instances after action: {autoscaler.current_instances}")

    # Teste 3: CPU baixo, esperar sair do cooldown, deve escalar para baixo
    print(f"\nTest 3: Low CPU (10%), 2 instances, waiting for cooldown ({autoscaler.settings.cooldown_seconds + 1}s total from last action)")
    time.sleep(autoscaler.settings.cooldown_seconds - 2 + 1) # Esperar o restante do cooldown + 1s
    decision = autoscaler.decide_scaling(average_cpu_percent=10.0, current_num_instances=2)
    print(f"Decision: {decision}")
    assert decision == "SCALE_DOWN"
    if decision == "SCALE_DOWN": autoscaler.record_scale_action(1)
    print(f"Instances after action: {autoscaler.current_instances}")


    # Teste 4: CPU baixo, já no mínimo, não deve fazer nada (após cooldown)
    print(f"\nTest 4: Low CPU (5%), 1 instance (already min), waiting for cooldown ({autoscaler.settings.cooldown_seconds + 1}s total from last action)")
    time.sleep(autoscaler.settings.cooldown_seconds + 1)
    decision = autoscaler.decide_scaling(average_cpu_percent=5.0, current_num_instances=1)
    print(f"Decision: {decision}")
    assert decision == "NO_ACTION" # Porque já está no mínimo
    print(f"Instances after action: {autoscaler.current_instances}")


    # Teste 5: CPU alto, tentar escalar para cima (de 1 para 2) (após cooldown)
    print(f"\nTest 5: High CPU (80%), 1 instance, waiting for cooldown ({autoscaler.settings.cooldown_seconds + 1}s total from last action)")
    time.sleep(autoscaler.settings.cooldown_seconds + 1)
    decision = autoscaler.decide_scaling(average_cpu_percent=80.0, current_num_instances=1)
    print(f"Decision: {decision}")
    assert decision == "SCALE_UP"
    if decision == "SCALE_UP": autoscaler.record_scale_action(2)
    print(f"Instances after action: {autoscaler.current_instances}")


    # Teste 6: CPU alto, tentar escalar para cima (de 2 para 3 - max) (após cooldown)
    print(f"\nTest 6: High CPU (85%), 2 instances, waiting for cooldown ({autoscaler.settings.cooldown_seconds + 1}s total from last action)")
    time.sleep(autoscaler.settings.cooldown_seconds + 1)
    decision = autoscaler.decide_scaling(average_cpu_percent=85.0, current_num_instances=2)
    print(f"Decision: {decision}")
    assert decision == "SCALE_UP"
    if decision == "SCALE_UP": autoscaler.record_scale_action(3) # Agora temos 3 instâncias
    print(f"Instances after action: {autoscaler.current_instances}")


    # Teste 7: CPU alto, já no máximo, não deve fazer nada (após cooldown)
    print(f"\nTest 7: High CPU (90%), 3 instances (already max), waiting for cooldown ({autoscaler.settings.cooldown_seconds + 1}s total from last action)")
    time.sleep(autoscaler.settings.cooldown_seconds + 1)
    decision = autoscaler.decide_scaling(average_cpu_percent=90.0, current_num_instances=3)
    print(f"Decision: {decision}")
    assert decision == "NO_ACTION" # Porque já está no máximo
    print(f"Instances after action: {autoscaler.current_instances}")
    
    print("\n--- autoscaler_logic.py self-test complete ---")
