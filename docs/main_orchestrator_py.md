> Nota da Etapa 0: documentação histórica; algumas descrições são de versões anteriores. O núcleo atual está em `simulator/`, o entrypoint é `python3 -m simulator.main_orchestrator` (na raiz) e o injetor ativo é `simulator/traffic_injectorV0.py`. Consulte o [README](../README.md).

# Documentação: main_orchestrator.py

## Objetivo Principal

O `main_orchestrator.py` é o script de controle central da simulação de autoscaling. Ele coordena as interações entre todos os outros módulos: `docker_manager`, `autoscaler_logic`, `traffic_injector`, e `config`. Sua função é executar o loop principal da simulação, coletar métricas, tomar decisões de scaling e aplicar essas decisões, além de gerenciar o ciclo de vida do ataque de tráfego.

## Estrutura e Lógica

### Importações
*   Módulos do projeto: `docker_manager`, `autoscaler_logic`, `traffic_injector`, `config`.
*   Bibliotecas padrão: `time`, `datetime`, `csv`, `statistics`.

### Função `run_simulation()`

Esta é a função principal que executa toda a lógica da simulação.

1.  **Inicialização:**
    *   Cria uma instância de `docker_manager.DockerManager` com as configurações apropriadas de `config.py`.
    *   Inicializa variáveis de estado:
        *   `active_instances_details`: Lista para armazenar detalhes das instâncias ativas.
        *   `last_scaling_action_time`: Timestamp da última ação de scaling, inicializado para permitir uma ação imediata se necessário.
        *   `metrics_data`: Lista para armazenar os dados a serem gravados no CSV.
        *   `simulation_start_time`: Timestamp do início da simulação.
        *   `attack_has_started`: Flag para controlar se o `traffic_injector.start_http_flood()` já foi chamado.
        *   `attack_has_stopped`: Flag para controlar se o `traffic_injector.stop_http_flood()` já foi chamado.

2.  **Garantia de Instâncias Mínimas:**
    *   Um loop inicial garante que o número `config.MIN_INSTANCES` de contêineres da aplicação alvo seja iniciado pelo `docker_manager` antes do início do loop principal da simulação.

3.  **Loop Principal da Simulação:**
    *   O loop continua enquanto `(datetime.datetime.now() - simulation_start_time).total_seconds() < config.SIMULATION_DURATION_SECONDS`.
    *   `current_loop_time`: Tempo decorrido desde o início da simulação.

    4.  **Gerenciamento do Ataque de Tráfego:**
        *   **Iniciar Ataque:** Se `current_loop_time >= config.ATTACK_START_TIME_SECONDS` e o ataque ainda não começou (`not attack_has_started`):
            *   Obtém as URLs das instâncias ativas do `docker_manager`.
            *   Se houver URLs válidas, chama `traffic_injector.start_http_flood()`.
            *   Define `attack_has_started = True`.
        *   **Parar Ataque:** Se `current_loop_time >= (config.ATTACK_START_TIME_SECONDS + config.ATTACK_DURATION_SECONDS)` e o ataque começou mas ainda não parou (`attack_has_started and not attack_has_stopped`):
            *   Chama `traffic_injector.stop_http_flood()`.
            *   Define `attack_has_stopped = True`.

    5.  **Coleta de Métricas:**
        *   Obtém a lista de detalhes das instâncias ativas (`active_instances_details`) do `docker_manager`.
        *   `num_current_instances = len(active_instances_details)`.
        *   Coleta o uso de CPU para cada instância ativa usando `docker_manager.get_container_cpu_usage()`.
        *   Calcula `average_cpu_percent`: A média do uso de CPU de todas as instâncias ativas (ou 0.0 se não houver instâncias ou dados de CPU).

    6.  **Decisão de Autoscaling:**
        *   Chama `autoscaler_logic.get_scaling_decision()` passando:
            *   `average_cpu_percent`
            *   `num_current_instances`
            *   Parâmetros relevantes de `config.py` (limiares, min/max instâncias, cooldowns, etc.)
            *   `last_scaling_action_time`
            *   `datetime.datetime.now()`
        *   Recebe `decision` (ex: `SCALE_UP`) e `desired_instances`.

    7.  **Aplicação da Decisão de Scaling:**
        *   Se `decision == autoscaler_logic.SCALE_UP` e `num_current_instances < desired_instances`:
            *   Calcula quantas instâncias novas adicionar.
            *   Chama `docker_manager.start_new_instance()` para cada nova instância.
            *   Atualiza `last_scaling_action_time`.
        *   Se `decision == autoscaler_logic.SCALE_DOWN` e `num_current_instances > desired_instances`:
            *   Calcula quantas instâncias remover.
            *   Para cada instância a ser removida (geralmente as mais recentes ou com base em alguma lógica de seleção, aqui as últimas da lista):
                *   Chama `docker_manager.stop_instance()`.
            *   Atualiza `last_scaling_action_time`.

    8.  **Registro de Métricas:**
        *   Coleta os nomes dos contêineres ativos.
        *   Adiciona uma entrada à lista `metrics_data` contendo: `current_loop_time`, `num_current_instances`, `average_cpu_percent`, `decision`, e `active_containers_names_str`.
        *   Imprime um resumo no console.

    9.  **Intervalo de Simulação:**
        *   `time.sleep(config.SIMULATION_INTERVAL_SECONDS)`.

4.  **Finalização da Simulação:**
    *   Após o loop principal, garante que o ataque de tráfego seja parado se ainda estiver ativo.
    *   Chama `docker_manager.stop_all_managed_instances()` para limpar todos os contêineres da simulação.
    *   Chama `write_metrics_to_csv()` para salvar os dados coletados.

### Função `write_metrics_to_csv(metrics_data, filename)`
*   Escreve os dados da lista `metrics_data` em um arquivo CSV especificado por `filename` (de `config.METRICS_CSV_FILE`).
*   Inclui um cabeçalho no CSV.

### Bloco `if __name__ == "__main__":`
*   Chama `run_simulation()` quando o script é executado diretamente.
*   Inclui um bloco `try...finally` para garantir que `docker_manager.stop_all_managed_instances()` seja chamado mesmo se ocorrer um erro durante a simulação, para evitar deixar contêineres órfãos.

## Como Interage

*   É o ponto de entrada principal da simulação.
*   Importa e utiliza configurações de `config.py`.
*   Usa `docker_manager.py` para gerenciar contêineres Docker e obter métricas de CPU.
*   Usa `autoscaler_logic.py` para obter decisões de scaling.
*   Usa `traffic_injector.py` para controlar o ataque de tráfego.
*   Produz um arquivo CSV (`simulation_metrics.csv` por padrão) com os resultados da simulação.