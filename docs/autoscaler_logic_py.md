> Nota da Etapa 0: documentação histórica; algumas descrições são de versões anteriores. O núcleo atual está em `simulator/`, o entrypoint é `python3 -m simulator.main_orchestrator` (na raiz) e o injetor ativo é `simulator/traffic_injectorV0.py`. Consulte o [README](../README.md).

# Documentação: autoscaler_logic.py

## Objetivo Principal

O `autoscaler_logic.py` contém a inteligência central para tomar decisões de autoscaling. Sua principal função é analisar o estado atual do sistema (uso médio de CPU, número de instâncias) e, com base em limiares e regras predefinidas, decidir se é necessário escalar para cima (`SCALE_UP`), escalar para baixo (`SCALE_DOWN`), ou não fazer nada (`NO_ACTION`).

## Estrutura e Lógica

### Constantes de Ação
*   `SCALE_UP = "SCALE_UP"`
*   `SCALE_DOWN = "SCALE_DOWN"`
*   `NO_ACTION = "NO_ACTION"`

Estas constantes são usadas para representar as possíveis decisões do autoscaler.

### Função `get_scaling_decision(current_cpu_avg, num_current_instances, min_instances, max_instances, cpu_scale_up_threshold, cpu_scale_down_threshold, last_action_time, current_time, cooldown_seconds, instances_to_add, instances_to_remove)`

Esta é a função principal do módulo.

*   **Parâmetros:**
    *   `current_cpu_avg`: O percentual médio de uso de CPU de todas as instâncias ativas.
    *   `num_current_instances`: O número atual de instâncias da aplicação em execução.
    *   `min_instances`: O número mínimo de instâncias permitido (de `config.py`).
    *   `max_instances`: O número máximo de instâncias permitido (de `config.py`).
    *   `cpu_scale_up_threshold`: Limiar de CPU para `SCALE_UP` (de `config.py`).
    *   `cpu_scale_down_threshold`: Limiar de CPU para `SCALE_DOWN` (de `config.py`).
    *   `last_action_time`: Timestamp da última ação de scaling realizada. Usado para implementar o cooldown.
    *   `current_time`: Timestamp atual.
    *   `cooldown_seconds`: Duração do período de cooldown (de `config.py`).
    *   `instances_to_add`: Número de instâncias a adicionar em um `SCALE_UP` (de `config.py`).
    *   `instances_to_remove`: Número de instâncias a remover em um `SCALE_DOWN` (de `config.py`).

*   **Lógica de Decisão:**

    1.  **Verificação de Cooldown:**
        *   Primeiro, verifica se o período de `cooldown_seconds` já passou desde a `last_action_time`.
        *   Se o cooldown ainda estiver ativo (`(current_time - last_action_time).total_seconds() < cooldown_seconds`), retorna `NO_ACTION` e o `num_current_instances` (nenhuma mudança), independentemente das outras condições. Isso previne ações de scaling muito frequentes.

    2.  **Decisão de `SCALE_UP`:**
        *   Se `current_cpu_avg > cpu_scale_up_threshold` (CPU média acima do limiar de scale-up)
        *   E `num_current_instances < max_instances` (ainda não atingiu o número máximo de instâncias)
        *   **Ação:** Decide `SCALE_UP`.
        *   **Número Desejado de Instâncias:** Calcula `desired_instances = min(num_current_instances + instances_to_add, max_instances)`. Garante que não exceda `max_instances`.
        *   Retorna `SCALE_UP` e `desired_instances`.

    3.  **Decisão de `SCALE_DOWN`:**
        *   Se `current_cpu_avg < cpu_scale_down_threshold` (CPU média abaixo do limiar de scale-down)
        *   E `num_current_instances > min_instances` (ainda não atingiu o número mínimo de instâncias)
        *   **Ação:** Decide `SCALE_DOWN`.
        *   **Número Desejado de Instâncias:** Calcula `desired_instances = max(num_current_instances - instances_to_remove, min_instances)`. Garante que não caia abaixo de `min_instances`.
        *   Retorna `SCALE_DOWN` e `desired_instances`.

    4.  **`NO_ACTION`:**
        *   Se nenhuma das condições acima para `SCALE_UP` ou `SCALE_DOWN` for atendida (ou se o cooldown estiver ativo, como verificado no início),
        *   **Ação:** Decide `NO_ACTION`.
        *   **Número Desejado de Instâncias:** Mantém `num_current_instances`.
        *   Retorna `NO_ACTION` e `num_current_instances`.

*   **Retorno:**
    *   A função retorna uma tupla: `(action_taken, desired_num_instances)`.
        *   `action_taken`: Uma das strings `SCALE_UP`, `SCALE_DOWN`, ou `NO_ACTION`.
        *   `desired_num_instances`: O número total de instâncias que o sistema deveria ter após a ação.

## Como Interage

*   É chamado pelo `main_orchestrator.py` em cada ciclo de simulação.
*   Recebe métricas atuais (CPU, número de instâncias) e parâmetros de configuração (limiares, min/max instâncias, cooldown) do `main_orchestrator.py` (que por sua vez os lê de `config.py`).
*   A decisão retornada por `get_scaling_decision` é usada pelo `main_orchestrator.py` para instruir o `docker_manager.py` a iniciar ou parar instâncias.