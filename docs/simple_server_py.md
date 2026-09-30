> Nota da Etapa 0: documentação histórica; algumas descrições são de versões anteriores. O núcleo atual está em `simulator/`, o entrypoint é `python3 -m simulator.main_orchestrator` (na raiz) e o injetor ativo é `simulator/traffic_injectorV0.py`. Consulte o [README](../README.md).

# Documentação: app/simple_server.py

## Objetivo Principal

O `app/simple_server.py` é uma aplicação web HTTP minimalista projetada para atuar como o "serviço alvo" na simulação de autoscaling. Seu principal objetivo é receber requisições HTTP GET e simular algum tipo de processamento que consuma recursos de CPU, permitindo que o autoscaler reaja ao aumento de carga.

## Estrutura e Lógica

O servidor é construído usando as classes `BaseHTTPRequestHandler` and `HTTPServer` do módulo `http.server` da biblioteca padrão do Python.

### Classe `SimpleAppHandler(BaseHTTPRequestHandler)`
Esta classe herda de `BaseHTTPRequestHandler` e define como o servidor lida com as requisições.

*   **`do_GET(self)`**:
    *   Este método é invocado para cada requisição HTTP GET recebida.
    *   **Simulação de Trabalho/Consumo de CPU:**
        *   Inicialmente, o consumo de CPU era simulado com `time.sleep(processing_time)`. O `processing_time` era obtido da variável de ambiente `PROCESSING_TIME`, com um padrão de `0.1` segundos. Isso simulava uma aplicação que gasta um tempo fixo por requisição, mas não necessariamente consome CPU ativamente durante todo esse tempo.
        *   Posteriormente, para um consumo de CPU mais efetivo e observável pelo `psutil` e `docker stats`, o `time.sleep()` foi substituído por um loop que realiza cálculos matemáticos intensivos:
            ```python
            import math # Necessário no topo do arquivo
            # ...
            for _ in range(int(1e6)): # O range pode ser ajustado
                _ = math.sqrt(123.456) * math.sin(123.456)
            ```
            Este loop garante que o processo Python esteja ativamente usando ciclos de CPU. O "peso" desse trabalho pode ser ajustado alterando o número de iterações do loop.
    *   **Resposta HTTP:**
        *   Após simular o trabalho, o servidor envia uma resposta HTTP 200 (OK).
        *   O corpo da resposta é um HTML simples que inclui o hostname do contêiner (obtido da variável de ambiente `HOSTNAME`, injetada pelo Docker) e o tempo de processamento simulado (se aplicável). Isso ajuda a identificar qual contêiner específico respondeu a uma requisição.
        *   Exemplo de mensagem: `f"Hello from {hostname}! Processed in {processing_time:.4f}s"` (a parte do `processing_time` pode ser adaptada se apenas o loop de `math` for usado).

### Bloco `if __name__ == '__main__':`
*   Este bloco é executado quando o script é rodado diretamente.
*   **Configuração da Porta:**
    *   A porta na qual o servidor escuta dentro do contêiner é determinada pela variável de ambiente `APP_PORT`, com `80` como padrão. O Dockerfile normalmente expõe esta porta.
*   **Inicialização do Servidor:**
    *   Cria uma instância de `HTTPServer`, vinculando-o ao endereço `('', server_port)` (escuta em todas as interfaces disponíveis dentro do contêiner na porta especificada) e usando `SimpleAppHandler` para tratar as requisições.
    *   Imprime uma mensagem no console indicando que o servidor está rodando.
    *   Chama `httpd.serve_forever()` para iniciar o loop principal do servidor, aguardando e processando requisições indefinidamente.

## Como Interage

*   É empacotado em uma imagem Docker (ex: `edos_target_app:latest`) usando um `Dockerfile` (não detalhado aqui, mas normalmente copia o `app/` para dentro da imagem e define o `CMD` para rodar este script).
*   O `docker_manager.py` inicia instâncias desta imagem Docker.
*   O `traffic_injector.py` envia requisições HTTP GET para as portas expostas das instâncias deste servidor.
*   O consumo de CPU gerado por este servidor ao processar requisições é monitorado pelo `docker_manager.py` e usado pelo `autoscaler_logic.py` para tomar decisões de scaling.

## Configuração

*   **`PROCESSING_TIME` (Variável de Ambiente):** Se a versão com `time.sleep(os.getenv("PROCESSING_TIME", "0.1"))` for usada, esta variável de ambiente, configurada ao rodar o contêiner (via `docker_manager.py` ou Dockerfile), determina a duração do sleep.
*   **`APP_PORT` (Variável de Ambiente):** Define a porta interna do contêiner.
*   **Loop de `math`**: O número de iterações no loop `for _ in range(int(X)):` pode ser ajustado diretamente no código para controlar a intensidade do consumo de CPU por requisição. Lembre-se de reconstruir a imagem Docker após qualquer alteração.