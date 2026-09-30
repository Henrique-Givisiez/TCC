# Simulador de Autoscaling e Distribuição de Carga

Este projeto é um simulador robusto projetado para demonstrar e testar o comportamento de sistemas com autoscaling dinâmico e injeção de tráfego. Ele permite observar como um sistema reage a variações de carga, escalando recursos para cima ou para baixo com base em métricas de desempenho, e como o tráfego é distribuído entre as instâncias ativas.

## Descrição da Versão Atual

Esta versão do simulador representa um avanço significativo na capacidade de modelar ambientes de produção com alta demanda. Ela simula um cenário onde uma aplicação (representada por instâncias Docker) precisa lidar com picos de tráfego, e um sistema de autoscaling entra em ação para manter a performance.

### Principais Funcionalidades:

1.  **Autoscaling Dinâmico Baseado em CPU:**
    *   O simulador monitora continuamente o uso médio de CPU das instâncias ativas.
    *   Com base em limites configuráveis (ex: `SCALE_UP` se CPU > 60%, `SCALE_DOWN` se CPU < 25%), o sistema adiciona ou remove instâncias automaticamente.
    *   Inclui um período de "cooldown" para evitar oscilações rápidas de escalonamento.

2.  **Injeção de Tráfego Controlada:**
    *   Um módulo de injeção de tráfego simula uma carga de requisições HTTP (HTTP Flood) em um período de tempo e intensidade definidos.
    *   Isso permite testar a resiliência do sistema e a eficácia das políticas de autoscaling sob estresse.

3.  **Distribuição de Carga Dinâmica (Balanceamento de Tráfego):**
    *   **Funcionalidade Aprimorada:** O injetor de tráfego agora se adapta dinamicamente às mudanças no número de instâncias. Sempre que uma nova instância é adicionada (ou removida), o injetor é reiniciado com a lista atualizada de URLs de destino.
    *   Isso garante que o tráfego seja distribuído de forma equitativa entre *todas* as instâncias ativas, evitando que uma única instância fique sobrecarregada enquanto outras permanecem ociosas.

4.  **Gerenciamento de Instâncias Docker:**
    *   As "instâncias" da aplicação são contêineres Docker leves, permitindo uma simulação realista do ambiente de execução.
    *   O simulador gerencia o ciclo de vida dos contêineres (iniciar, parar, remover).

5.  **Coleta e Log de Métricas:**
    *   Durante a simulação, métricas importantes como tempo decorrido, número de instâncias ativas, uso médio de CPU e decisões de escalonamento são registradas em um arquivo CSV (`simulation_metrics.csv`).
    *   Isso fornece dados valiosos para análise pós-simulação e validação do comportamento do sistema.

6.  **Cálculo de Custo Fictício:**
    *   Um módulo de cálculo de custo estima o "custo" da simulação com base no tempo de atividade e número de instâncias, oferecendo uma perspectiva de otimização de recursos.

## Como Funciona

O simulador é orquestrado por um script principal (`main_orchestrator.py`) que coordena os seguintes componentes:

*   **`docker_manager.py`**: Gerencia a criação, inicialização, monitoramento e remoção de contêineres Docker.
*   **`autoscaler_logic.py`**: Contém a lógica de decisão para escalonamento (para cima ou para baixo) com base nas métricas de CPU e políticas configuradas.
*   **`traffic_injector.py`**: Simula a carga de trabalho enviando requisições HTTP para as instâncias da aplicação. Ele é dinamicamente atualizado pelo orquestrador para distribuir a carga.
*   **`config.py`**: Armazena todas as configurações da simulação, como limites de CPU, duração do ataque, número mínimo/máximo de instâncias, etc.

## Propósito

Este simulador é uma ferramenta valiosa para:

*   **Testar Estratégias de Autoscaling:** Validar a eficácia de diferentes políticas de escalonamento sob diversas condições de carga.
*   **Observar Comportamento do Sistema:** Entender como a adição/remoção de recursos afeta o desempenho geral e a utilização de CPU.
*   **Otimização de Custos:** Analisar o impacto das políticas de escalonamento nos custos operacionais simulados.
*   **Educação e Demonstração:** Ilustrar conceitos de computação em nuvem, balanceamento de carga e escalabilidade.

## Uso

Para executar a simulação:

1.  Certifique-se de ter o Docker instalado e em execução.
2.  Instale as dependências Python (ex: `docker` SDK).
    ```bash
    pip install docker
    ```
3.  Configure os parâmetros da simulação no arquivo `config.py`.
4.  Execute o script principal:
    ```bash
    python main_orchestrator.py
    ```

A saída detalhada no console e o arquivo `simulation_metrics.csv` fornecerão insights sobre o comportamento da simulação.
