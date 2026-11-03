**Relatório de progresso — TCC**  
**Período: após o relatório de 31/10/2026 até 03/11/2026**

O trabalho deste período concentrou-se na exploração dos resultados já coletados, na ampliação das visualizações e no esclarecimento dos limites metodológicos da campanha. **Não há registro, nas informações compartilhadas, de novas execuções experimentais ou de recalibração dos detectores nesse intervalo.** A campanha científica permanece com 56 coletas aceitas, incluindo 36 execuções TEST organizadas em 12 blocos C16/M16/E16.

Este registro distingue entregas confirmadas de propostas e investigações cuja conclusão ainda precisa ser conferida.

**1. Visualizações do comportamento dos detectores**

Após a primeira seleção de figuras, identificamos que a figura temporal D não mostrava suficientemente o comportamento dos detectores. A necessidade passou a ser visualizar, para uma execução e cenário específicos, a evolução da feature junto dos escores, limiares e alarmes.

Foi compartilhado o commit `c1106256a4925689c951a992b7da19796881f917`, relacionado às alterações do gerador. Na sequência, identificamos uma limitação: a seleção de outras features, como `mean_cpu_percent`, ainda precisava ser incorporada.

Encaminhamos ao Codex a ampliação do gerador para permitir examinar diferentes features, execuções e cenários, reutilizando os resultados persistidos. Essa abordagem permite investigar, por exemplo, se um método reage rapidamente ao aumento de requisições, mas demora mais para sinalizar alterações de CPU ou duração.

**Situação:** houve avanço no gerador, mas a conclusão da seleção genérica de features e sua interface final precisam ser confirmadas no código e na documentação atualizados.

**2. Visualizações e análise do proxy**

Foi desenvolvido um conjunto específico de visualizações do proxy, associado ao commit `49ca2f273d2bbbf8f3d4d452b3bd55ea9687b86c`. As figuras discutidas foram:

- `P_proxy_temporal_B01.pdf`: comportamento temporal do proxy no bloco B01;
- `Q_proxy_individual_runs_phases.pdf`: comparação das execuções individuais e das fases.

Esse trabalho ampliou a análise para além dos detectores e da vítima. Passamos a examinar CPU, memória, conexões e tempos de atendimento upstream, relacionando essas variáveis às fases do experimento.

A interpretação precisa conservar as limitações de instrumentação já identificadas: existem registros do proxy nas 36 execuções TEST, mas houve 119 falhas de parsing de `stub_status`. Valores ausentes não devem ser preenchidos como zero nem confundidos com ausência de atividade.

**3. Principais questões levantadas pela análise do proxy**

Uma questão central foi por que E16 apresenta maior atividade no proxy mesmo com a mesma taxa ofensiva nominal de M16.

A explicação discutida é que **igualdade de RPS não implica igualdade de trabalho nem de concorrência**. Requisições a `/expensive` demandam mais processamento na vítima e podem permanecer mais tempo em atendimento. Enquanto aguardam respostas, mantêm recursos e conexões ocupados no proxy. Assim, o aumento de conexões ativas e de tempos upstream é compatível com respostas mais lentas, mesmo sem aumento da taxa nominal de chegada.

Essa interpretação não demonstra, por si só, que o proxy se tornou o gargalo. Também não permite atribuir toda variação de CPU exclusivamente ao custo do endpoint: taxas realizadas, duração das exposições e demais condições precisam acompanhar a análise.

Outra questão foi a queda de memória observada em E16 durante ACTIVE. Foi encaminhada uma investigação offline, com quatro verificações, para esclarecer o comportamento e a definição da métrica.

**Situação:** a investigação foi solicitada, mas seu resultado não aparece no material compartilhado neste histórico. Portanto, a causa da queda de memória permanece pendente; não deve ser apresentada como liberação de memória, efeito de cache ou consequência do ataque sem confirmação.

**4. Esclarecimento da interrupção antecipada em E16**

Discutimos por que o ataque em E16 pode terminar antes de M16. A campanha prevê emissão ofensiva nominal entre 150 e 270 segundos, mas possui uma proteção que encerra o atacante quando identifica comprometimento elevado do serviço.

Essa proteção:

- funciona independentemente dos quatro detectores avaliados;
- encerra a emissão ofensiva;
- mantém o tráfego legítimo e a coleta quando possível;
- permite acompanhar a recuperação após o encerramento.

O término antecipado **não representa uma ação de mitigação tomada pelos detectores**. Também não torna automaticamente inválida uma execução com coleta íntegra.

Na campanha consolidada, E16 teve parada precoce em 10 das 12 execuções; M16 não teve paradas precoces. Por isso, as comparações precisam apresentar a exposição efetiva. Os resultados descrevem o comportamento dos cenários **sob a política de proteção adotada**, sem demonstrar como E16 evoluiria caso a emissão continuasse até o fim nominal.

Também discutimos que retirar a proteção poderia prolongar filas, timeouts e recuperação, mas isso permanece uma possibilidade, não um resultado observado. Não foi decidido executar uma nova campanha sem proteção.

**5. Estatísticas descritivas e intervalos de confiança**

Avançamos no esclarecimento de como consultar e interpretar médias, medianas, desvios padrão e intervalos de confiança.

A distinção importante para a apresentação dos resultados é entre:

- estatísticas calculadas dentro de uma execução, como duração média ou p95 das requisições;
- estatísticas entre execuções, que descrevem a variação entre os blocos;
- contrastes pareados, calculados entre condições pertencentes ao mesmo bloco.

Essas populações não devem ser misturadas. Uma média entre médias de execução, por exemplo, não é necessariamente a média de todas as requisições agrupadas. Da mesma forma, os percentis individuais não devem ser apresentados como um único percentil obtido pela média dos p95.

Os intervalos de confiança já estavam implementados e publicados na consolidação anterior. Neste período, o foco foi compreender sua interpretação: eles expressam a incerteza da estimativa segundo o procedimento estatístico adotado, não a faixa que contém 95% das requisições nem uma garantia sobre futuras execuções.

**6. Reutilização dos dados para novos detectores**

Discutimos a possibilidade de implementar outro método e avaliá-lo com os dados já preservados. A conclusão foi que **novos métodos podem ser processados offline, sem necessariamente repetir a coleta**, desde que as variáveis necessárias estejam disponíveis.

A separação das funções deve permanecer:

| Partição | Uso para um novo método |
|---|---|
| BASELINE | Estimar referências ou ajustar um modelo benigno, quando aplicável |
| CAL-A | Selecionar parâmetros e limiares |
| CAL-B | Verificar o método com parâmetros fixos |
| TEST | Avaliar o desempenho final sem reajuste |

Essa possibilidade depende do tipo de método. Um detector que precise de treinamento supervisionado com ataques não encontra esse conjunto de treinamento nas partições benignas atuais; seria necessário planejar dados apropriados, preservando TEST.

Há também uma limitação metodológica: os resultados TEST já foram examinados. Um novo método desenvolvido em resposta a esses achados deve ser apresentado como extensão exploratória. Uma alegação confirmatória independente pode exigir novas execuções de teste.

**7. Estado atual e próximos passos**

O avanço principal foi transformar os resultados consolidados em análises mais interpretáveis: observar trajetórias dos detectores, incluir o proxy e explicitar o papel da proteção e da exposição real.

As pendências são:

1. Confirmar e documentar a interface final do gerador para todas as features, execuções e cenários.
2. Concluir as verificações da memória do proxy e registrar quais explicações são sustentadas pelos dados.
3. Conferir a correspondência entre as métricas prometidas na redação e as efetivamente disponíveis no projeto.
4. Organizar as estatísticas descritivas com população, fase, unidade e número de execuções explícitos.
5. Incorporar as figuras e interpretações à metodologia e aos resultados, preservando as lacunas de monitoramento e as diferenças de exposição.
6. Manter novos detectores, autoscaling, ataques periódicos e campanhas sem proteção como extensões separadas, sem apresentá-los como funcionalidades já avaliadas.

**O escopo experimental consolidado permanece inalterado:** ataque HTTP contínuo, vítima com capacidade fixa, um regime legítimo de 16 RPS e comparação principal entre C16, M16 e E16. O trabalho deste período ampliou a análise dessa evidência, sem ampliar a campanha.