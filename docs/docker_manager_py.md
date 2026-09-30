> Nota da Etapa 0: documentação histórica; algumas descrições são de versões anteriores. O núcleo atual está em `simulator/`, o entrypoint é `python3 -m simulator.main_orchestrator` (na raiz) e o injetor ativo é `simulator/traffic_injectorV0.py`. Consulte o [README](../README.md).

# Documentação: docker_manager.py

## Objetivo Principal

O `docker_manager.py` encapsula toda a interação com o daemon Docker. Ele fornece uma interface para o `main_orchestrator.py` gerenciar o ciclo de vida dos contêineres da aplicação alvo, incluindo iniciá-los, pará-los, listar os ativos e obter métricas de uso de CPU.

## Estrutura e Lógica

### Classe `DockerManager`

*   **`__init__(self, image_name, internal_port, base_host_port, network_name)`**:
    *   **Parâmetros:**
        *   `image_name`: Nome da imagem Docker a ser usada (ex: `config.TARGET_APP_IMAGE_NAME`).
        *   `internal_port`: Porta interna na qual a aplicação no contêiner escuta (ex: `config.TARGET_APP_INTERNAL_PORT`).
        *   `base_host_port`: Porta base no host para mapeamento (ex: `config.TARGET_APP_BASE_HOST_PORT`).
        *   `network_name`: Nome da rede Docker customizada (ex: `config.DOCKER_NETWORK_NAME`).
    *   Inicializa o cliente Docker (`docker.from_env()`).
    *   Armazena os parâmetros de configuração.
    *   Mantém um conjunto (`self.used_host_ports`) para rastrear as portas do host já em uso e evitar conflitos.
    *   Garante que a rede Docker customizada especificada exista, criando-a se necessário.

*   **`_get_next_available_host_port(self)`**:
    *   Método auxiliar para encontrar a próxima porta do host não utilizada, começando de `base_host_port` e incrementando.

*   **`start_new_instance(self, instance_num=None)`**:
    *   **Objetivo:** Iniciar um novo contêiner da aplicação alvo.
    *   Gera um nome único para o contêiner (ex: `target_instance_1`, `target_instance_X`).
    *   Encontra uma porta de host disponível usando `_get_next_available_host_port()`.
    *   Define variáveis de ambiente para o contêiner, como `APP_PORT` (com a porta interna) e, crucialmente, `PROCESSING_TIME="0.1"` (ou o valor desejado para simular o trabalho no `simple_server.py`, se ele usar essa variável).
    *   Usa `self.client.containers.run()` para iniciar o contêiner:
        *   Em modo `detach=True` (background).
        *   Mapeia a `internal_port` do contêiner para a `host_port_to_use` encontrada.
        *   Define as `environment` variáveis.
        *   Atribui o `name` gerado.
        *   Conecta o contêiner à `network_name` especificada.
    *   Retorna o objeto do contêiner Docker e a URL base da instância (ex: `http://localhost:8080`).
    *   Trata exceções se o contêiner não iniciar corretamente.

*   **`stop_instance(self, container_name_or_id)`**:
    *   **Objetivo:** Parar e remover um contêiner específico.
    *   Obtém o objeto do contêiner pelo nome ou ID.
    *   Extrai a porta do host que estava sendo usada por este contêiner para liberá-la (removendo de `self.used_host_ports`).
    *   Chama `container.stop()` e `container.remove()`.
    *   Trata exceções se o contêiner não for encontrado ou não puder ser parado/removido.

*   **`get_active_instances_details(self, prefix="target_instance_")`**:
    *   **Objetivo:** Listar todas as instâncias ativas (contêineres rodando) que correspondem a um prefixo de nome.
    *   Usa `self.client.containers.list()` com filtros para encontrar contêineres com o `status="running"` e o `name` começando com o prefixo.
    *   Para cada contêiner encontrado, extrai seu ID, nome, e a URL base (IP e porta mapeada).
        *   **Importante:** A URL é construída usando `localhost` e a porta mapeada no host. Isso assume que o `main_orchestrator.py` (e, portanto, o `traffic_injector.py`) está rodando na mesma máquina (ou VM) que o daemon Docker, ou que `localhost` resolve corretamente para o host Docker.
    *   Retorna uma lista de dicionários, cada um contendo `id`, `name`, e `url` da instância.

*   **`get_container_cpu_usage(self, container_name_or_id)`**:
    *   **Objetivo:** Obter o percentual de uso de CPU de um contêiner específico.
    *   Obtém o objeto do contêiner.
    *   Usa `container.stats(stream=False)` para obter uma única leitura das estatísticas do contêiner.
    *   **Cálculo do CPU:** A lógica para calcular o percentual de CPU a partir dos dados brutos de `container.stats()` é complexa e envolve comparar `cpu_stats['cpu_usage']['total_usage']` e `precpu_stats['cpu_usage']['total_usage']` (uso de CPU do sistema), e o número de CPUs online.
        ```python
        # Exemplo simplificado da lógica central do cálculo de CPU:
        cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - stats['precpu_stats']['cpu_usage']['total_usage']
        system_cpu_delta = stats['cpu_stats']['system_cpu_usage'] - stats['precpu_stats']['system_cpu_usage']
        number_cpus = stats['cpu_stats'].get('online_cpus', len(stats['cpu_stats']['cpu_usage']['percpu_usage'] or []))
        
        if system_cpu_delta > 0.0 and cpu_delta > 0.0:
            cpu_percent = (cpu_delta / system_cpu_delta) * number_cpus * 100.0
        else:
            cpu_percent = 0.0
        return cpu_percent
        ```
    *   Retorna o percentual de CPU ou `0.0` se não puder ser calculado.
    *   Trata o caso de `precpu_stats` não estar disponível na primeira leitura de estatísticas (retornando `0.0` nesses casos).

*   **`stop_all_managed_instances(self, prefix="target_instance_")`**:
    *   **Objetivo:** Parar todas as instâncias gerenciadas (com o prefixo de nome especificado). Útil para limpeza no final da simulação.
    *   Obtém a lista de instâncias ativas.
    *   Chama `stop_instance()` para cada uma.

## Como Interage

*   É instanciado e usado pelo `main_orchestrator.py` para todas as operações relacionadas ao Docker.
*   Lê configurações como `TARGET_APP_IMAGE_NAME`, `DOCKER_NETWORK_NAME`, etc., do módulo `config.py` (indiretamente, pois esses valores são passados durante a inicialização do `DockerManager` pelo orquestrador).
*   Inicia contêineres da imagem `app/simple_server.py`.
*   As métricas de CPU que ele coleta são usadas pelo `autoscaler_logic.py` (via `main_orchestrator.py`).
*   As URLs das instâncias ativas que ele fornece são usadas pelo `traffic_injector.py` (via `main_orchestrator.py`).