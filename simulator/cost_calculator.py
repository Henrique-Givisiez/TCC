# edos_docker_simulation/cost_calculator.py
from simulator import config

def calculate_instance_cost(num_instances, active_duration_seconds):
    """
    Calculates the fictional cost based on the number of instances and their active duration.

    Args:
        num_instances (int): The number of active instances.
        active_duration_seconds (float): The duration in seconds these instances were active.

    Returns:
        float: The calculated fictional cost.
    """
    if num_instances <= 0 or active_duration_seconds <= 0:
        return 0.0

    # Converter a duração para horas, pois o custo é por hora
    active_duration_hours = active_duration_seconds / 3600.0
    
    cost = num_instances * config.COST_PER_INSTANCE_PER_HOUR * active_duration_hours
    return cost

# No futuro, poderíamos adicionar mais granularidade, por exemplo,
# se cada instância tivesse um custo diferente ou se quiséssemos
# calcular o custo incrementalmente durante a simulação.
# Por enquanto, esta função pode ser chamada no final da simulação
# ou periodicamente para obter um custo acumulado.

# Para um custo acumulado, o orquestrador precisaria manter o controle
# do tempo de atividade de cada configuração de número de instâncias.
# Exemplo:
# total_cost = 0
# N instâncias ativas por T1 segundos: total_cost += calculate_instance_cost(N, T1)
# M instâncias ativas por T2 segundos: total_cost += calculate_instance_cost(M, T2)

def calculate_total_cost_from_intervals(instance_intervals):
    """
    Calculates the total fictional cost from a list of intervals where
    a certain number of instances were active.

    Args:
        instance_intervals (list of tuples): 
            A list where each tuple is (num_instances, duration_seconds_for_this_num_instances).
            Example: [(1, 60), (2, 120), (1, 30)] 
                     means 1 instance ran for 60s, then 2 for 120s, then 1 for 30s.
    
    Returns:
        float: The total calculated fictional cost.
    """
    total_cost = 0.0
    for num_instances, duration_seconds in instance_intervals:
        total_cost += calculate_instance_cost(num_instances, duration_seconds)
    return total_cost


# --- Self-test section (optional, for direct testing of this module) ---
if __name__ == "__main__":
    print("--- Running cost_calculator.py self-test ---")

    # Cenário 1: 2 instâncias ativas por 1 hora (3600 segundos)
    cost1 = calculate_instance_cost(num_instances=2, active_duration_seconds=3600)
    expected_cost1 = 2 * config.COST_PER_INSTANCE_PER_HOUR * 1
    print(f"\nTest 1: 2 instances for 1 hour")
    print(f"Configured cost per instance per hour: ${config.COST_PER_INSTANCE_PER_HOUR:.2f}")
    print(f"Calculated cost: ${cost1:.4f}")
    print(f"Expected cost: ${expected_cost1:.4f}")
    assert abs(cost1 - expected_cost1) < 0.0001 # Comparação de floats

    # Cenário 2: 3 instâncias ativas por 30 minutos (1800 segundos)
    cost2 = calculate_instance_cost(num_instances=3, active_duration_seconds=1800)
    expected_cost2 = 3 * config.COST_PER_INSTANCE_PER_HOUR * 0.5
    print(f"\nTest 2: 3 instances for 30 minutes")
    print(f"Calculated cost: ${cost2:.4f}")
    print(f"Expected cost: ${expected_cost2:.4f}")
    assert abs(cost2 - expected_cost2) < 0.0001

    # Cenário 3: Sem instâncias ou sem tempo
    cost3_1 = calculate_instance_cost(num_instances=0, active_duration_seconds=3600)
    cost3_2 = calculate_instance_cost(num_instances=2, active_duration_seconds=0)
    print(f"\nTest 3: No instances or no time")
    print(f"Cost with 0 instances: ${cost3_1:.4f}")
    print(f"Cost with 0 seconds: ${cost3_2:.4f}")
    assert cost3_1 == 0.0
    assert cost3_2 == 0.0

    # Cenário 4: Teste com calculate_total_cost_from_intervals
    intervals = [
        (1, 3600),       # 1 instância por 1 hora
        (3, 1800),       # 3 instâncias por 0.5 horas
        (2, 7200)        # 2 instâncias por 2 horas
    ]
    total_cost_intervals = calculate_total_cost_from_intervals(intervals)
    
    expected_cost_interval1 = 1 * config.COST_PER_INSTANCE_PER_HOUR * 1.0
    expected_cost_interval2 = 3 * config.COST_PER_INSTANCE_PER_HOUR * 0.5
    expected_cost_interval3 = 2 * config.COST_PER_INSTANCE_PER_HOUR * 2.0
    expected_total_cost_intervals = expected_cost_interval1 + expected_cost_interval2 + expected_cost_interval3

    print(f"\nTest 4: Using calculate_total_cost_from_intervals")
    print(f"Intervals: {intervals}")
    print(f"Calculated total cost: ${total_cost_intervals:.4f}")
    print(f"Expected total cost: ${expected_total_cost_intervals:.4f}")
    assert abs(total_cost_intervals - expected_total_cost_intervals) < 0.0001

    print("\n--- cost_calculator.py self-test complete ---")
