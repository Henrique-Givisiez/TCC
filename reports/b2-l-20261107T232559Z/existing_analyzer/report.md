# A1 — análise exploratória

Estatísticas e unidades: integrity.json; CSVs preservam precisão. Sem inferência ou seleção automática.

| Execução | Configuração | Comparação principal | Problemas |
|---|---|---|---|
| c5e06e3441e4499c94fc62275c5d9ff4 | L2 | False | operation integrity anomalies; valid subset is diagnostic only |

Coortes HTTP iniciadas em [30,150), incluindo conclusões conhecidas na drenagem. CPU em percentual Docker; duração/espera em segundos.

| Configuração | Run | Starts/s | HTTP média | CPU média | Espera média | Sucesso/starts |
|---|---|---:|---:|---:|---:|---:|
| L2 | c5e06e3441e4499c94fc62275c5d9ff4 | 16.075 | 0.046915518968373794 | 57.621 | 0.002853048949717185 | 1.0 |

Cobertura CPU em [30,150), em segundos relativos ao início efetivo:

| Run | Amostras | Primeira | Última | Maior intervalo consecutivo (s) | Intervalos de 10 s vazios |
|---|---:|---:|---:|---:|---|
| c5e06e3441e4499c94fc62275c5d9ff4 | 20 | 30.267440337999915 | 144.83862555099995 | 6.076231546999907 | [] |

Amostras pontuais não comprovam estabilidade contínua. Intervalos vazios e trechos antes da primeira/depois da última amostra não sustentam conclusões de estabilidade durante todo [30,150). Não há limiar automático de cobertura.
Espera por worker descreve apenas timelines disponíveis; contadores computacionais e trabalho pendente ficam indisponíveis quando faltam timelines. Ausências ambíguas não comprovam falha operacional nem corrupção.

Contrastes planejados: L2/L6 e L3/L7 (mesma taxa); L2/L3 e L6/L7 (mesmas fontes). Uma execução por célula não demonstra causalidade. Linhas excluídas da comparação principal continuam disponíveis acima para diagnóstico.

Configurações com problemas permanecem diagnósticas e são excluídas das comparações principais. Contagens sem observações são zero; estatísticas sem suporte são nulas. Consulte integrity.json para hashes e detalhes.
