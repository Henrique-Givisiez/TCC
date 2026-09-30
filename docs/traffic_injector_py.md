> Nota da Etapa 0: documentação histórica; algumas descrições são de versões anteriores. O núcleo atual está em `simulator/`, o entrypoint é `python3 -m simulator.main_orchestrator` (na raiz) e o injetor ativo é `simulator/traffic_injectorV0.py`. Consulte o [README](../README.md).

# Documentação: traffic_injector.py

## Objetivo Principal

O `traffic_injector.py` é responsável por gerar uma carga de tráfego HTTP GET simulada contra as instâncias da aplicação alvo (`app/simple_server.py`). Seu objetivo é estressar a aplicação para que seu consumo de CPU aumente, permitindo testar a lógica do autoscaler. Ele utiliza múltiplas threads para simular múltiplos usuários ou fontes de tráfego concorrentes.

## Estrutura e Lógica

### Variáveis Globais
*   `attacker_threads`: Lista para armazenar as threads "atacantes" ativas.
*   `attack_active`: Flag booleana (`True`/`False`) que controla globalmente se os workers devem continuar enviando requisições. É usada para iniciar e parar o ataque de forma coordenada.

### Função `http_request_worker(target_url, rps_per_this_worker)`
Esta é a função executada por cada thread atacante.

*   **Parâmetros:**
    *   `target_url`: A URL completa da instância da aplicação alvo que esta thread específica deve atacar (ex: `http://localhost:8080`).
    *   `rps_per_this_worker`: O número de requisições por segundo (RPS) que este worker específico deve tentar enviar.
*   **Contadores Locais:**
    *   `worker_request_count`: Conta o número de requisições bem-sucedidas (status 200) enviadas por este worker.
    *   `worker_error_count`: Conta o número de erros (timeouts, outros erros de requisição, ou status diferente de 200) encontrados por este worker.
*   **Sessão `requests`:**
    *   Utiliza `requests.Session()` para potencialmente se beneficiar de keep-alive e reutilização de conexões TCP, o que pode ser mais eficiente para múltiplas requisições ao mesmo host.
*   **Controle de RPS:**
    *   Calcula `sleep_interval_seconds = 1.0 / rps_per_this_worker` para determinar o intervalo de tempo entre as requisições para atingir o RPS desejado.
    *   Se `rps_per_this_worker` for 0 ou negativo, o worker entra em um modo de espera, dormindo por um curto período e checando `attack_active` sem enviar requisições.
*   **Loop Principal (`while attack_active:`):**
    *   A thread continua em execução enquanto `attack_active` for `True`.
    *   Registra o tempo de início da iteração (`iteration_start_time`).
    *   **Envio da Requisição:**
        *   Faz uma requisição HTTP GET para `target_url` usando `session.get()`.
        *   Utiliza um timeout configurável (`config.HTTP_REQUEST_TIMEOUT_SECONDS`) para evitar que a thread bloqueie indefinidamente.
        *   Incrementa `worker_request_count` ou `worker_error_count` com base no resultado da requisição.
    *   **Cálculo do Sono:**
        *   Calcula o tempo gasto na iteração (`iteration_time_taken`).
        *   Calcula `time_to_sleep = sleep_interval_seconds - iteration_time_taken`.
        *   Se `time_to_sleep > 0`, a thread dorme por esse período para tentar manter o RPS. Se for `<=0` (a requisição demorou mais que o intervalo), prossegue imediatamente.
*   **Finalização:**
    *   Quando `attack_active` se torna `False`, o loop termina.
    *   Imprime uma mensagem com o total de requisições e erros enviados por este worker específico.

### Função `start_http_flood(target_urls, rps_per_worker, num_attackers)`
Esta função inicializa e inicia o ataque de tráfego.

*   **Parâmetros:**
    *   `target_urls`: Uma lista de URLs das instâncias ativas da aplicação alvo. Atualmente, todas as threads atacam a primeira URL da lista para simplificar, mas poderia ser estendido para distribuir a carga.
    *   `rps_per_worker`: RPS desejado por worker (obtido de `config.py`).
    *   `num_attackers`: Número total de workers/threads a serem criados (obtido de `config.py`).
*   **Lógica:**
    *   Verifica se `target_urls` não está vazia e se um ataque já não está em progresso.
    *   Define `attack_active = True`.
    *   Limpa a lista `attacker_threads` de qualquer ataque anterior.
    *   Seleciona a primeira URL da lista `target_urls` como o alvo.
    *   Em um loop, cria `num_attackers` threads, cada uma executando `http_request_worker` com a `effective_target_url` e `rps_per_worker`.
    *   Adiciona cada thread à lista `attacker_threads` e a inicia.
    *   Imprime mensagens indicando o início do ataque e o RPS total aproximado.
    *   A duração do ataque é gerenciada externamente pelo `main_orchestrator.py`, que chamará `stop_http_flood()`.

### Função `stop_http_flood()`
Esta função para o ataque de tráfego em andamento.

*   **Lógica:**
    *   Define `attack_active = False`. Isso sinaliza a todas as threads workers para terminarem seus loops.
    *   Itera sobre a lista `attacker_threads` e chama `thread_obj.join(timeout=...)` para cada thread. Isso faz com que o script principal espere que cada thread termine sua execução (ou até que o timeout do join seja atingido). O timeout do join é configurado para ser um pouco maior que o `HTTP_REQUEST_TIMEOUT_SECONDS` para dar tempo à thread de finalizar sua última requisição.
    *   Imprime mensagens indicando a parada dos workers.
    *   Limpa a lista `attacker_threads`.

## Como Interage

*   É chamado pelo `main_orchestrator.py` para iniciar (`start_http_flood`) e parar (`stop_http_flood`) o ataque de tráfego nos momentos apropriados da simulação.
*   Lê parâmetros de configuração do ataque (como `HTTP_ATTACK_NUM_ATTACKERS`, `HTTP_ATTACK_REQUESTS_PER_SECOND_PER_ATTACKER`, `HTTP_REQUEST_TIMEOUT_SECONDS`) do módulo `config.py`.
*   Envia requisições HTTP para as instâncias da aplicação alvo (`app/simple_server.py`) gerenciadas pelo `docker_manager.py`.