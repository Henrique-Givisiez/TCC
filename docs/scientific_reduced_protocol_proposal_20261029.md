# Proposta única de campanha reduzida — antes da coleta

Proposta para fechar o protocolo, sem configurações, seeds ou autorização de coleta. Substitui prospectivamente o desenho de98 runs, que permanece pausado e preservado. [E12/E16 encerrados](development_stress_closure_20261029.md); E20 fora do escopo. E12, N2 e demais DEVELOPMENT são evidência exploratória, nunca dados independentes de calibração/TEST.

## Matriz e perguntas

| Cenário TEST | Ataque | Legítimos | Pergunta |
|---|---|---|---|
| C16 | Desligado |4×4 RPS `/medium`|Generalização do falso alarme no regime benigno|
| M16 |1×16 RPS `/medium`|4×4 RPS `/medium`|Detecção e impacto de maior oferta com menor custo por requisição|
| E16 |1×16 RPS `/expensive`|4×4 RPS `/medium`|Detecção e impacto sob pressão mais clara sobre o atendimento|

Uma vítima, pool2, proxy estático, autoscaling off; mesmos workers, timeout2 s, recursos e monitoramento dos pilotos. O trio responde ao desempenho dos quatro detectores no regime legítimo16 RPS e ao contraste operacional de custo M16/E16 com oferta nominal igual. Não responde a curva de intensidade, origens ou robustez em diferentes regimes legítimos. M16 não tem piloto novo e não precisa de exploração prévia; impacto baixo ou ausente é resultado legítimo. E12 não entra na matriz: acrescentaria outra pergunta e coleta, sem ser necessário ao objetivo principal.

Quatro métodos: Z-score, CoV L6, EWMA λ=.2, CUSUM congelado k=.5; cinco features pré-especificadas, `request_starts` primária. Estimandos primários: detecção operacional de E16 e FPR de C16; contraste primário de métodos CUSUM congelado−EWMA em E16. M16 e E16−M16 são secundários. Não escolher vencedor/feature pelo TEST. A intervenção avaliada inclui a proteção de segurança, não um ataque hipotético forçado por120 s.

## Partições, blocos e precisão

Recomendo **12 blocos TEST completos de C16/M16/E16**,36 runs, conforme decisão adotada. As seis permutações aparecem duas vezes: cada cenário ocupa cada posição4 vezes e cada precedência ordenada adjacente aparece4 vezes. Ordem documental pré-fixada dos blocos:

`CME, MEC, ECM, EMC, MCE, CEM; MEC, ECM, CME, MCE, CEM, EMC`, onde C=C16, M=M16, E=E16.

A unidade independente é o bloco; seed nova compartilhada somente dentro dele, sem garantia de chegadas idênticas. Deriva temporal permanece limitação. Aceita-se menor precisão; sem parada por significância ou recall favorável. A variação de intensidade sai da pergunta principal; E12 permanece exploratório.

**Menor alocação benigna recomendada:4 BASELINE,8 CAL-A,8 CAL-B**,20 runs novos e independentes, em vez de34. São20 benignos de preparação,12 controles TEST e24 ataques:56 runs e32 seeds de tráfego distintas. A redução é prospectiva e exige novo contrato; não autoriza reutilizar DEVELOPMENT ou fazer o runner antigo aceitar outros números por exceção.

O indispensável é a separação das três funções e seus dados, suporte suficiente, sigma positivo na feature primária, replay por h e verificação independente antes de TEST. Os algoritmos não exigem6/12/16 execuções: ddof1 requer ao menos duas observações válidas, mas isso não justifica ajustar um estudo com duas observações nem com uma única realização longa. Não existe mínimo universal demonstrado para quantil99% sob dependência desconhecida. **4/8/8 é um piso de planejamento defensável para este estudo reduzido, não mínimo matemático nem dimensionamento por poder.** Reduzir além dele exigiria nova justificativa de estabilidade/cauda que a evidência disponível não fornece; não faremos coleta exploratória para escolher a alocação.

| Partição | Recomendação | Informação nominal útil em[30,390) | Necessidade e limitação |
|---|---:|---:|---|
| BASELINE |4 C16|24 min /1440 janelas|Momentos ddof1 fixos para Z/EWMA/CUSUM; CoV sem fit externo. Quatro realizações dão alguma diversidade entre runs;6 era reserva de robustez/precisão, não exigência do fitter. Com4, maior sensibilidade a deriva e estimativas instáveis; publicar suporte e momentos por run sem ajustar a seleção depois |
| CAL-A |8 C16|48 min /2880 janelas|Quantil99% e grade fechada/replay por h. Aproximadamente29 scores na cauda nominal de1%, contra43 com12, antes de missing/dependência. Quantil e seleção de h ficam mais instáveis; não são29 réplicas independentes nem garantia de cauda rara |
| CAL-B |8 C16|48 min /2880 janelas|Oito unidades independentes verificam o ponto fixo.16 era escolha de precisão fora da amostra. Um run com FPR5% pesa0,625 pp na média de8, contra0,3125 pp em16; zero runs com qualquer alarme ainda admite limite superior unilateral exato95%≈31,2% para probabilidade de um run ter alarme (não FPR por janela) |

**Critérios preservados, sem relaxamento:** BASELINE em[30,390), ddof1, suporte primário≥342/360 por run e sigma positivo; falha bloqueia ajuste. Em CAL-A, Z/CoV/EWMA usam quantil empírico superior99%, índice `ceil((N−1)×.99)`, alarme estrito score>limiar. CUSUM congelado usa a mesma grade fechada de h, escala h_ref, k=.5 e replay completo desde zero por candidato/run. Elegibilidade primária dos quatro métodos: média macro dos8 FPR≤1%, nenhum run>5%,≥342/360 decisões disponíveis em cada run; escolher menor h elegível. Nenhum candidato elegível ou reprovação de método primário bloqueia CAL-B, sem fallback/expansão de grade.

CAL-B aplica uma única vez os parâmetros fixos: para cada método primário, média macro FPR≤2%, nenhum run>5%,≥342/360 decisões disponíveis em cada um dos8 runs. Reprovação de qualquer método primário bloqueia TEST; não retunar em B/TEST, ampliar amostra ou substituir por reprovação estatística. Secundárias continuam pré-declaradas, com não avaliação explícita se não aceitas. ICs publicados não acrescentam gate oculto de limite superior. A redução altera a incerteza e o comportamento amostral dos gates, embora preserve seus valores; não se afirma equivalência ao desenho34. As regras completas de [calibração fechadas](scientific_campaign_implementation_20261029.md) permanecem referência, com novas quantidades ainda por integrar.

Com12 eventos por condição, semilargura Wilson máxima≈24,6 pp;12/12 detectados ainda dá limite inferior exato bilateral95%≈73,5%. Não são36 eventos por condição. É precisão limitada, aceita para comparação descritiva com ICs, sem prova de equivalência/superioridade. Inferência condicionada ao treinamento congelado não inclui incerteza de refitting; reduzir benignos aumenta a importância dessa limitação.

## Política prospectiva de parada e avaliação

Adotar a proteção E12/E16, idêntica em M16/E16, independente de alarmes dos detectores: a cada250 ms, coorte de starts `[agora−13,agora−3)`,≥50 starts e≥20% sem2xx em3 s; fila ofensiva admitida não iniciada>128 por≥10 s; ausência de amostra Docker nova por>5 s. Timestamp `read` precisa avançar: CPU repetida não é falta de coleta. Queda/OOM/integridade irrecuperável permite encerramento global de segurança. C16 mantém proteção/coleta, mas não possui emissão ofensiva a interromper. Os modelos não recebem a decisão do observador como feature/label e não são resetados pela parada.

Comando controlado cessa novas admissões ofensivas. Admissões anteriores podem começar depois; respostas e trabalho da vítima podem persistir além de timeout. Preservar legítimos, captura e recursos até390 s quando possível, sem estender a observação olhando resultados. Registrar decisão observada/disponível, comando, stop recebido, certificado de fim real, última conclusão e motivo; nominal150–270 nunca substitui esses tempos. Até30 s de drenagem e≥60 s de repouso após cleanup. Ausência de recuperação suspende o início de outra coleta para revisão operacional, preservando o run; não coletar repetidamente até obter recuperação favorável.

**Detecção primária:** primeira decisão positiva cuja janela tenha overlap positivo com a emissão real e esteja disponível entre actual_start e actual_end, inclusive o prazo final. Fim da janela≤disponibilidade; disponibilidade simulada no fechamento da janela não é tempo computacional medido. Prazo reduz automaticamente se a proteção encerrar a emissão. Detector não pode usar GT/parada para antecipar decisões. Alarme disponível após actual_end é descrito como tardio/persistência POST, sem converter o miss primário em acerto.

**Miss:** execução tecnicamente íntegra, com emissão observável e nenhuma decisão elegível, permanece no denominador com detecção0 e atraso observado=null. Isso inclui parada anterior à primeira oportunidade de decisão; indisponibilidade/suporte são mostrados separadamente. Não excluir por ausência de impacto, parada por serviço ou duração curta. Se nenhuma emissão ocorrer, reportar evento não executado/denominador de elegibilidade separadamente, preservando a tentativa e diagnosticando; não inventar FN nem autorizar repetição automática.

**Atraso:** disponibilidade−actual_start somente para detectados, em segundos. Publicar n detectados e atrasos junto de misses. Sem detecções: média/mediana/IC=null; IC condicional somente com≥8 detecções. Publicar também fração restrita sem detecção: atraso/duração efetiva se detectado,1 se miss. Ela descreve o desempenho sob a proteção e seu prazo variável, não imputa atraso observado nem estima tempo hipotético até120 s. Parada por comprometimento é informativa, dependente do serviço: não tratá-la como censura independente para Kaplan–Meier ou extrapolar detecções além do fim real.

**Impacto:** por run, PRE próprio e ACTIVE/POST reais: starts, términos e2xx por segundo, exposição, sucesso/timeout/incompletas, duração de todos os términos e dos2xx separadamente, pendências e idade, recursos, recuperação e motivo de parada. Janelas fixas30 s, recortes≥95% de exposição e suporte≥200 para critérios de serviço; recortes menores são descritivos. Comprometimento forte=p95>2×PRE ou sucesso<95%, com suporte; não comprova saturação. Avaliar backlog, recursos, oferta/atendimento e gerador em conjunto. POST tem exposição maior após parada antecipada, explicitada; taxas usam exposição real, contagens brutas não medem efeito comparável sozinhas. Recuperação censurada se não confirmada até390; isso não invalida o run nem é atraso de detector.

**Pareamento:** métodos usam exatamente o mesmo run e prazo real; permanecem plenamente pareados. C16/M16/E16 permanecem vinculados por bloco, mas E16−M16 compara políticas operacionais com exposições potencialmente distintas. Não igualar retrospectivamente durações, selecionar sobreviventes ou preencher ataque após parada. Publicar diferenças pareadas dos resumos por execução, exposição e frequência/tempo de parada. O contraste não isola custo a dose realizada constante. A fração restrita normalizada ajuda descrição, sem remover essa diferença causal.

Parada por serviço e limitação observada do gerador são resultados, não exclusões técnicas. Falha objetiva de coleta/identidade/suporte técnico tem diagnóstico separado e atrição visível. No máximo duas substituições exclusivamente técnicas, uma por slot, mesma seed/configuração e nova tentativa/paths com aprovação do hash da falha. Critérios técnicos anteriormente fechados permanecem; comprometimento, miss, baixa taxa realizada e ausência de recuperação não permitem substituição. Indeterminação exige diagnóstico, não retry automático. Bloco com falha técnica não substituída: preservar resultados válidos por condição e explicitar n; contrastes só com pares completos, sem imputação ou descarte silencioso do bloco inteiro.

## ICs existentes, lacunas e orçamento

Já implementados em `analysis/detection/scientific/statistics.py`: proporções Wilson95% e exato nos extremos; diferenças de detecção por discordâncias pareadas/exato97,5%+Bonferroni; BCa10000 para médias/diferenças contínuas; fallback Hoeffding para variáveis limitadas degeneradas; atraso condicional com suporte mínimo8. A avaliação já usa fim real como deadline, miss com null e fração restrita. Reamostrar execuções/blocos completos, conservando métodos e cenários, nunca janelas/requisições iid. ICs pontuais, sem cobertura simultânea de toda a tabela.

Falta adaptar e validar, antes de coleta: contrato hoje fixado em98 runs/quatro condições/16 blocos; M16/E16, preparação4/8/8 e ordem12×3; observador/recursos do piloto no backend científico; certificados de fechamento antecipado; agrupamento/ICs de exposição, paradas e impacto; n elegíveis/pares incompletos; fixtures fim antecipado antes da detecção, miss, disponibilidade tardia, recuperação censurada e substituição técnica. Contraste primário ainda codificado E8 deve mudar sob nova autoridade para E16. Para métricas de impacto sem bounds válidos, BCa degenerado produz IC indisponível com motivo, sem inventar bound de2 s a partir do timeout. Não se altera código nesta tarefa nem se afirma que o runner atual já executa essa proposta.

| Partição / teto | Runs | Nominal390 s/run | Operacional: nominal+30 s drenagem+60 s repouso | Administrativo600 s/run | Envelope |
|---|---:|---:|---:|---:|---:|
| BASELINE |4|26 min|32 min|40 min|1h12|
| CAL-A |8|52 min|1h04|1h20|2h24|
| CAL-B |8|52 min|1h04|1h20|2h24|
| TEST:12×3 |36|3h54|4h48|6h00|10h48|
| **Total** |**56**|**6h04**|**7h28**|**9h20**|**16h48**|
| Teto com2 substituições técnicas |58|6h17|7h44|9h40|17h24|

Operacional já inclui nominal; envelope=operacional+administrativo. Parada ofensiva antecipada não reduz reserva: legítimos/POST continuam até390. Implementação, diagnóstico excepcional, análise e escrita ficam fora do envelope; falha de A/B pode bloquear a campanha e não autoriza gasto extra implícito. Frente aos98 runs, são42 runs e12h36 de envelope a menos; frente à proposta anterior de88,32 runs e9h36 a menos. Prazo15/11 depende de reservar até17h24 de coleta mais as tarefas pendentes; não é garantia de calendário. Próximo passo é fechar este protocolo e integrar as lacunas antes de materialização/coleta. Somente esta proposta foi atualizada; documentos anteriores permanecem históricos.
