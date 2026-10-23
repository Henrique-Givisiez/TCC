# Proposta para discutir com o orientador: ataque HTTP contínuo

**Nome sugerido:** carga HTTP adversarial contínua com geração em controle aberto
e demanda computacional controlada. Fundamentação e evidências completas em
[continuous_attack_foundation.md](continuous_attack_foundation.md).

O objetivo do modelo é representar uma fonte que adiciona requisições HTTP
válidas e compete pelos recursos do serviço, sem presumir que todo aumento de
carga produz indisponibilidade ou dano econômico.

| Dimensão | Campanha C congelada |
|---|---|
| Intervalo nominal | [48,84) s, em run 144 s |
| Fontes atacantes | Uma origem em container |
| Geração por fonte |8 RPS nominais; esperas Exp(8/s), média 125 ms |
| Primeiro despacho | Imediato; demais após espera exponencial e custos do scheduler |
| Controle/concorrência | Sem esperar HTTP; até 64 tarefas em execução, fila contínua sem limite explícito |
| Caminho/endpoint | Source → NGINX → vítima; GET /medium |
| Trabalho |100000 iterações do kernel CPU, sleep 0; custo físico precisa ser medido |
| Referência benigna |4 fontes ×2RPS, também /medium; agregado8 RPS |
| Parada | Fecha novas admissões; tarefas admitidas podem começar depois; drenagem separada |

**Idealização:** fontes independentes com intensidade
`lambda_i(t)=lambda_i*1_[a,b)(t)` e intervalos exponenciais dariam oferta Poisson
ideal. **Implementação:** primeiro ponto imediato, despacho/escritas, scheduler e
executor introduzem diferenças. **Observação:** medir separadamente admissões,
starts do cliente e serviço recebido/processado; não afirmar que todos são8 RPS.

A literatura de Ranjan et al. (INFOCOM 2006) e Walfish et al. (SIGCOMM 2006) sustenta
requisições válidas como meio de consumir recursos computacionais. Não fornece
nossos valores de taxa, duração ou workers. O C usa custo igual por request nas
duas classes: não é uma reprodução do ataque assimétrico de Ranjan. O modelo
aberto é uma escolha explícita, discutida metodologicamente por Schroeder et al.
(NSDI 2006), não uma propriedade universal dos atacantes.

**Decisões propostas para a reunião:**

1. Apresentar os resultados atuais como avaliação sob carga adversarial contínua
   controlada, preservando a definição e todos os parâmetros congelados.
2. Separar a pergunta de detecção de carga das perguntas de saturação, ataque de
   baixa taxa eficaz e EDoS; cada uma exige evidências próprias de mecanismo/dano.
3. Para uma campanha futura, caracterizar capacidade e custo dos endpoints em
   DEVELOPMENT independente, com critérios de serviço previamente definidos.
   Escolher intensidade por esses critérios, não por desempenho de detector no
   TEST existente, e congelar plano/seeds antes de um novo TEST.
4. Se desejar testar assimetria, tratar endpoint/custo por request como fator novo,
   com baseline/calibração/avaliação próprias. Não reinterpretar /medium como
   /expensive nem work_units legado como custo efetivo.

Não se propõe mudar o runtime agora. Não há nova taxa recomendada sem
caracterização. “Contínuo” não significa necessariamente alta taxa, LDoS ou EDoS.
