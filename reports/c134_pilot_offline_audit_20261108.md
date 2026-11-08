# Auditoria offline dos pilotos C1.3.4 — 2026-11-08

## 1. Resumo executivo

**Recomendação: não iniciar ainda a campanha completa de 80 execuções.** As capturas e os datasets das três tentativas selecionadas estão certificados, mas a disponibilidade de CPU está muito abaixo do contrato de 95%. Isso não invalida retroativamente os datasets; ameaça a elegibilidade das combinações método × CPU. O problema prioritário é a disponibilidade temporal da observação, não falha de aquisição Docker.

**Fatos:** cobertura CPU em [30,390): L2 78,89%, A3 68,06%, F96 40,00%. Limites superiores CoV: 109, 62 e 65 decisões em 360. No F96, 2.136 das 7.323 falhas HTTP observadas são de clientes legítimos; 5.187 são ofensivas. A inversão CSV de 2 µs não altera a janela nem os agregados de pacotes/bytes.

**Inferência fundamentada:** a antecedência de coleta de 25 ms oferece margem insuficiente diante dos tempos observados de aquisição e escalonamento. **Hipótese não verificada:** a origem sistêmica desses atrasos (CPU host, Docker, disco, escalonamento) e a eficácia de qualquer ajuste futuro.

## 2. Identificação e integridade

HEAD confirmado: `400ca8f8913bb4385c5e9aefcddc5acbf4037581`; branch `refactor/project-organization`; árvore inicialmente limpa. Especificação `docs/scientific_protocol_direct_20261108.json`, SHA256 confirmado: `be39b12ffcd09699da6311fb7a86ddab342dfba503e699b9df6833f9fed46303`.

Raiz: `/home/henrique-givisiez/tcc_c134_pilots_20261108_112324`. F96 significa exclusivamente `F96_fix_400ca8f_20261108_144956`; tentativas rejeitadas não integram os cálculos. Antes da análise foram confirmados os três manifests, registros de certificação e ausência de bloqueadores. Foram relidos e verificados bytes/SHA256 de todos os arquivos indexados: 81/107/107, sem divergências.

| Piloto / diretório | Run ID | Commit da execução (limpo) | Capturados CSV = PCAP / drops |
| --- | --- | --- | --- |
| L2 | 35133406d4654901b9a39c41d7a0d0ec | 49921a297e88 | 32833 / 0 em ambos |
| A3 | a4925d9f6c7942b4a7ad7b91dad3e5db | 49921a297e88 | 49743 / 0 em ambos |
| F96 / F96_fix_400ca8f_20261108_144956 | ef8a1e44071c48eaa46dc5ac0ff8823a | 400ca8f8913b | 95307 / 0 em ambos |

Todos: `dataset_valid=true`, `analysis_eligible=true`, execução completed, certificação completed, progression_allowed=true. Validador: zero erros; avisos L2=0, A3=1 (falhas de requisição), F96=2 (falhas e inversão temporal). A certificação do dataset não exige 95% de decisões de cada detector. As evidências CPU, requisições e CSV de pacotes analisados em raw também conferem com os respectivos hashes exportados.

L2/A3 antecedem o escritor CSV persistente, o parser singular/plural e `-B 4096` no PCAP. F96 inclui essas mudanças. Os hashes registrados de `simulator/cpu_observations.py`, `simulator/stats_collector.py` e `experiments/cpu_features.py` são iguais nas três execuções. Há comparabilidade do contrato CPU, mas as execuções não são réplicas sob instrumentação de captura idêntica.

## 3. Atividade A — CPU

### Coleta e atribuição

`StatsCollector._loop/_acquire` agenda a chamada em n−0,025 s, registra início/fim monotônicos e epochs, identifica contêiner/geração, coleta stats sem streaming e registra recebimento igual ao fim da chamada. Escreve evidência JSONL com flush/fsync; `next_slot` pula oportunidades vencidas sem backlog. Esse I/O pode influenciar o agendamento seguinte, mas os pilotos não demonstram que seja a causa dos atrasos.

`cpu_observations.delta` usa deltas de contadores Docker e número de CPUs online: Δusage/Δsystem × online_cpus × 100. Valida identidade/geração, counters, read RFC3339, ordem e bracket de aquisição; primeira leitura estabelece referência. `assign_cpu` revalida/reproduz os deltas e exige os DOIS brackets inteiros próximos às fronteiras da janela, tolerância ±50 ms. Exige ainda **received_seconds ≤ fim nominal**, sem carência de 50 ms para recebimento. Não interpola, não rateia intervalos e não repete cache. Múltiplos candidatos tornam a janela ausente.

O replay puro L2/A3 reproduz integralmente a qualidade CPU exportada. F96 não tem diretório de features preenchido: a grade e a qualidade foram calculadas em memória a partir das evidências, sem exportação nova. A regra do extrator é max(390, floor(última observação científica)+1): os três têm grade de **391**, pois há cauda após 390 s. A janela adicional [390,391) não entra em nenhuma fase nominal nem na seleção [30,390).

| Piloto | Nominais válidas / ausentes (390) | Cobertura | Maior lacuna nominal | Janela adicional [390,391) | Grade completa válidas / 391 |
| --- | --- | --- | --- | --- | --- |
| L2 | 313 / 77 | 80.26% | 4 | ausente | 313 |
| A3 | 273 / 117 | 70.00% | 4 | válida | 274 |
| F96 | 173 / 217 | 44.36% | 44 | ausente | 173 |

Denominadores: WARMUP=30, cada outra fase=120, nominal=390, seleção científica=360. No L2, ATTACK é apenas o recorte temporal de referência; não há ataque. As maiores lacunas no F96 incluem [230,274): 44 janelas, atravessando ATTACK/POST; recortada por fase, 40 e 26 são os máximos respectivos.

| Piloto | Fase | Esperadas | Válidas | Ausentes | Cobertura | Maior lacuna | Z / EWMA / CUSUM¹ | CoV¹ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| L2 | WARMUP | 30 | 29 | 1 | 96.67% | 1 | 29 | 24 |
| L2 | PRE | 120 | 103 | 17 | 85.83% | 2 | 103 | 64 |
| L2 | ATTACK | 120 | 103 | 17 | 85.83% | 1 | 103 | 43 |
| L2 | POST | 120 | 78 | 42 | 65.00% | 4 | 78 | 2 |
| L2 | SELECTION | 360 | 284 | 76 | 78.89% | 4 | 284 | 109 |
| A3 | WARMUP | 30 | 28 | 2 | 93.33% | 1 | 28 | 20 |
| A3 | PRE | 120 | 103 | 17 | 85.83% | 4 | 103 | 49 |
| A3 | ATTACK | 120 | 78 | 42 | 65.00% | 4 | 78 | 13 |
| A3 | POST | 120 | 64 | 56 | 53.33% | 4 | 64 | 0 |
| A3 | SELECTION | 360 | 245 | 115 | 68.06% | 4 | 245 | 62 |
| F96 | WARMUP | 30 | 29 | 1 | 96.67% | 1 | 29 | 24 |
| F96 | PRE | 120 | 103 | 17 | 85.83% | 3 | 103 | 60 |
| F96 | ATTACK | 120 | 30 | 90 | 25.00% | 40 | 30 | 5 |
| F96 | POST | 120 | 11 | 109 | 9.17% | 26 | 11 | 0 |
| F96 | SELECTION | 360 | 144 | 216 | 40.00% | 44 | 144 | 65 |

¹ Limites superiores de disponibilidade, não decisões calibradas. Z-Score/EWMA/CUSUM-freeze têm no máximo uma oportunidade por observação válida; baseline, thresholds e demais contratos podem reduzir esse total. CoV requer seis janelas válidas consecutivas, incluindo a atual, e ausência reinicia a sequência; a contagem percorreu a grade desde zero antes de selecionar fases. Não reiniciou artificialmente na fronteira de fase. Média CoV zero também pode impedir score; não se executaram detectores nem calibração.

### Causas quantificadas

L2/A3: 391 tentativas e snapshots cada, 390 deltas válidos e uma primeira leitura. F96: 394 tentativas/snapshots, 393 deltas válidos e uma primeira leitura. Em todos: **zero erros de aquisição, snapshots inválidos, timestamp inválido, counter reset, geração alterada, múltiplos candidatos e oportunidades perdidas**. Aquisição completa não implica feature disponível.

A tabela seguinte é uma partição das janelas nominais ausentes. O código verifica desalinhamento antes de atraso: categorias são exclusivas por prioridade, não causas fisicamente independentes.

| Piloto | Fase | Sem referência inicial | Recebimento tardio | Desalinhamento | Total |
| --- | --- | --- | --- | --- | --- |
| L2 | WARMUP | 1 | 0 | 0 | 1 |
| L2 | PRE | 0 | 17 | 0 | 17 |
| L2 | ATTACK | 0 | 17 | 0 | 17 |
| L2 | POST | 0 | 40 | 2 | 42 |
| A3 | WARMUP | 1 | 1 | 0 | 2 |
| A3 | PRE | 0 | 17 | 0 | 17 |
| A3 | ATTACK | 0 | 42 | 0 | 42 |
| A3 | POST | 0 | 44 | 12 | 56 |
| F96 | WARMUP | 1 | 0 | 0 | 1 |
| F96 | PRE | 0 | 17 | 0 | 17 |
| F96 | ATTACK | 0 | 49 | 41 | 90 |
| F96 | POST | 0 | 39 | 70 | 109 |

Totais nominais: L2=1+74+2=77; A3=1+104+12=117; F96=1+105+111=217. Fora do nominal: janela 390 rejeitada por desalinhamento no L2, válida no A3 e tardia no F96; três deltas F96 de índices 391–393 estão fora da grade. Não são oportunidades de coleta perdidas nem perdas científicas adicionais em [0,390).

Contando sobreposições, entre os deltas rejeitados nominais há recebimento tardio em 75/112/201 (L2/A3/F96); 1/8/96 também têm desalinhamento. No F96, 67 brackets iniciais e 67 finais ultrapassam a tolerância, com sobreposição. Um bracket inadequado pode comprometer dois deltas adjacentes.

| Piloto | p95 atraso início (ms) | p95 duração chamada (ms) | Fim após fronteira² | Atraso >25 ms² | Duração >25 ms² |
| --- | --- | --- | --- | --- | --- |
| L2 | 9.50 | 38.92 | 75 | 5 | 60 |
| A3 | 15.69 | 43.82 | 112 | 10 | 84 |
| F96 | 201.00 | 68.47 | 201 | 59 | 170 |

² Nas 390 chamadas com fronteiras agendadas 1–390; atraso/duração se sobrepõem. p95 usa todas as tentativas registradas, incluindo cauda. Com lead de 25 ms, fim−fronteira = atraso de início + duração−25 ms. Nos casos restantes, dois componentes individualmente ≤25 ms também excedem juntos o orçamento (14/23/28 chamadas).

Exemplo F96, sequência 56: agendada 55,975 s, iniciou 55,979690344, terminou/recebeu 56,006598350. O bracket cabe na tolerância de 50 ms, mas chega 6,598 ms após fechar [55,56), portanto é corretamente rejeitado. Isso prova que a tolerância não é prazo de chegada. Já em F96 ATTACK/POST as chamadas tardias são 82/102 e atrasos de início >25 ms são 19/40, com apenas 30/11 janelas finais válidas.

**Diagnóstico fundamentado:** a margem temporal de 25 ms é insuficiente para a distribuição observada de chamadas, mesmo com início pontual, e o atraso de início agrava o F96. Duração isolada supera 25 ms em mais chamadas que o atraso isolado; a causa sistêmica permanece desconhecida.

### Implicações para elegibilidade

A especificação exige `minimum_available_fraction=0.95`. O engine seleciona 360 janelas e exige ≥342 observações para suporte baseline; a elegibilidade dos métodos também exige ≥95% de decisões disponíveis em cada suporte, além de limites de falsos alarmes e calibração. Nenhum dos três pilotos alcança sequer o limite superior de 342 decisões CPU: Z/EWMA/CUSUM 284/245/144; CoV 109/62/65. Os déficits até 342 são 58/97/198 e 233/280/277, respectivamente.

São pilotos, não suportes completos BASELINE/CAL_A/CAL_B: não se declara inelegibilidade formal de uma campanha ainda inexistente nem elegibilidade de um detector. O resultado demonstra alto risco de inviabilizar **método × mean_cpu_percent**, inclusive no cenário legítimo, sem afetar automaticamente outras features ou a validade dos datasets. Lacunas dependentes de fase/carga também ameaçam representatividade, não apenas a porcentagem total.

## 4. Atividade B — HTTP

Unidade: tentativa com request_begin, classificada por generator/origem declarada; fases pelo **início** monotônico. Cada linha tem conclusão registrada; sucesso significa outcome=response (HTTP recebido sem erro), não prova de conclusão computacional interna. Os sucessos observados têm status 200. Falhas HTTP (status ≥400), client_error e incompletas: zero nos três pilotos. As falhas são de transporte.

| Piloto | Origem | Iniciadas = concluídas (toda cauda) | Sucessos | Transporte | Falhas % |
| --- | --- | --- | --- | --- | --- |
| L2 | normal | 6187 | 6187 | 0 | 0.00 |
| A3 | normal | 6187 | 3995 | 2192 | 35.43 |
| A3 | attack | 926 | 76 | 850 | 91.79 |
| F96 | normal | 6188 | 4052 | 2136 | 34.52 |
| F96 | attack | 5671 | 484 | 5187 | 91.47 |

Por fonte: L2 normal_1/2=3139/3048; A3 normal_1/2=3140/3047, attack_1/2=439/487; F96 normal_1/2=3140/3048, attack_1/2=2816/2855. A3 tem um início legítimo em 390,000454537 s, fora do nominal; por isso o total legítimo é 6187 e o nominal 6186.

| Piloto | Origem | Fase | Inícios | Inícios/s | Sucessos da coorte | Transporte | Falhas % |
| --- | --- | --- | --- | --- | --- | --- | --- |
| L2 | normal | WARMUP | 462 | 15.40 | 462 | 0 | 0.00 |
| L2 | normal | PRE | 1918 | 15.98 | 1918 | 0 | 0.00 |
| L2 | normal | ATTACK | 1870 | 15.58 | 1870 | 0 | 0.00 |
| L2 | normal | POST | 1937 | 16.14 | 1937 | 0 | 0.00 |
| A3 | normal | WARMUP | 460 | 15.33 | 460 | 0 | 0.00 |
| A3 | normal | PRE | 1920 | 16.00 | 1920 | 0 | 0.00 |
| A3 | normal | ATTACK | 1870 | 15.58 | 171 | 1699 | 90.86 |
| A3 | normal | POST | 1936 | 16.13 | 1443 | 493 | 25.46 |
| A3 | attack | ATTACK | 926 | 7.72 | 76 | 850 | 91.79 |
| F96 | normal | WARMUP | 461 | 15.37 | 461 | 0 | 0.00 |
| F96 | normal | PRE | 1919 | 15.99 | 1919 | 0 | 0.00 |
| F96 | normal | ATTACK | 1870 | 15.58 | 129 | 1741 | 93.10 |
| F96 | normal | POST | 1938 | 16.15 | 1543 | 395 | 20.38 |
| F96 | attack | ATTACK | 5671 | 47.26 | 484 | 5187 | 91.47 |

Taxa configurada legítima: 2×8=16/s por 390 s; ofensiva A3: 2×4=8/s, F96: 2×32=64/s, somente [150,270). São taxas de oportunidades com intervalos exponenciais, não quantidade fixa garantida. Expectativas nominais: 6240 legítimas, 960 ofensivas A3, 7680 F96. WARMUP legítimo realizou 15,40/15,33/15,37/s; para toda a origem legítima nominal, aproximadamente 15,86/s nos três.

Verificação do denominador ofensivo: todos os inícios A3 estão em [150,011497378;269,894457723] e F96 em [150,007658595;269,988783449]. Portanto 926/120=7,72/s e 5671/120=47,26/s são taxas realizadas **no intervalo programado de emissão**, não vazão de sucesso nem taxa de conclusões. A duração entre primeiro/último início é 119,883/119,981 s; não há inícios ofensivos POST.

A agregação registra A3: 926 admitidas, zero abandonadas, 926 iniciadas/concluídas. F96: 7203 admitidas, 1532 abandonadas antes do HTTP, 5671 iniciadas/concluídas (7203−1532=5671). Assim, taxa admitida F96=60,03/s e taxa de início=47,26/s; oportunidades não viram automaticamente requisições. `actual_end_seconds` é fechamento de admissão/STARTs enfileirados, não último HTTP iniciado: A3=270,006058, F96=271,765457. Drain das conclusões até 271,899659/273,040051. Não se dividem todas as conclusões por 120 s para chamar o resultado de vazão de conclusão.

Por **fim** da requisição: A3 tem 915 conclusões ofensivas ATTACK e 11 POST; F96 5575 ATTACK e 96 POST. As 11/96 conclusões ofensivas POST falham. Conclusões legítimas ATTACK/POST: L2 1870/1936; A3 1850/1956; F96 1845/1961. Há ainda 1/1/2 conclusões legítimas após 390 s, que permanecem nos artefatos.

No F96, 11859 tentativas = 6188 legítimas + 5671 ofensivas; 7323 falhas = 2136 legítimas + 5187 ofensivas. Total 61,75% falha; legítimas 34,52%, ofensivas 91,47%. Na fase ATTACK, 93,10% das tentativas legítimas falham, ante 0% PRE; POST mantém 20,38% de falhas. A3 tem 90,86%/25,46% legítimas ATTACK/POST. Isso caracteriza degradação percebida pelos clientes legítimos; falhas ofensivas são descritas separadamente. Não se atribui o mecanismo interno exclusivamente a CPU, fila ou rede.

F96: legítimos ReadTimeout=2080/ConnectTimeout=56; ofensivos ReadTimeout=5017/ConnectTimeout=170. A3: ReadTimeout legítimo=2192 e ofensivo=850. Distribuições abaixo incluem durações de sucesso **e falha**, disponíveis para todas as tentativas; são tempos cliente até resposta/erro, não tempo de processamento do servidor. Quantis por interpolação linear em (n−1)p.

| Piloto | Origem | Fase | n | p50 ms | p95 ms | p99 ms | Máx ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| L2 | normal | PRE | 1918 | 46.33 | 95.08 | 119.03 | 179.99 |
| L2 | normal | ATTACK | 1870 | 36.26 | 78.32 | 98.89 | 124.61 |
| L2 | normal | POST | 1937 | 35.78 | 77.47 | 87.88 | 109.19 |
| A3 | normal | PRE | 1920 | 36.70 | 77.81 | 94.94 | 159.73 |
| A3 | normal | ATTACK | 1870 | 2004.53 | 2005.66 | 2006.42 | 2021.39 |
| A3 | normal | POST | 1936 | 43.31 | 2005.16 | 2006.01 | 2008.76 |
| A3 | attack | ATTACK | 926 | 2004.55 | 2005.58 | 2006.09 | 2007.24 |
| F96 | normal | PRE | 1919 | 40.48 | 82.58 | 95.90 | 125.10 |
| F96 | normal | ATTACK | 1870 | 2005.18 | 3019.08 | 3057.63 | 3071.22 |
| F96 | normal | POST | 1938 | 54.90 | 2005.75 | 2007.46 | 3069.48 |
| F96 | attack | ATTACK | 5671 | 2005.33 | 3015.82 | 3065.39 | 3077.14 |

Condicionando a sucesso: nas respostas legítimas bem-sucedidas, p50/p95 ATTACK são L2 36,26/78,32 ms, A3 892,00/1946,65 ms, F96 1234,48/1968,48 ms. POST: L2 35,78/77,47; A3 35,91/79,29; F96 46,49/98,62 ms. Esses quantis condicionados a sucesso não apagam as falhas POST. Durações F96 acima de 2 s não contradizem automaticamente `request_timeout_seconds=2`: tempo total inclui fases cliente/conexão e espera, não um deadline global rígido de 2 s.

## 5. Atividade C — timestamps F96

O exemplo `40004` do validador é **linha física CSV com cabeçalho**, calculada como i+2, não índice zero de pacote. Na sequência original:

| Linha CSV | Epoch | Elapsed s | Direção / portas | Payload bytes |
| --- | --- | --- | --- | --- |
| 40003 | 1794160410.461582 | 201.62947750091553 | vítima:80 → fonte .6:55508 | 0 |
| 40004 | 1794160410.461580 | 201.6294755935669 | fonte .6:33818 → vítima:80 | 0 |
| 40005 | 1794160410.463245 | 201.63114047050476 | fonte .6:55940 → vítima:80 | 0 |

**Fato:** a inversão é −0,000002 s (2 µs); ambos os pacotes estão em [201,202), ATTACK, mesmo evento. Elapsed é derivado do epoch original; não houve alteração de timestamp/atribuição nesta auditoria. A diferença de elapsed é aproximadamente −1,907 µs devido à representação float do epoch; a diferença decimal registrada de epoch é exatamente −2 µs.

O extrator atribui cada pacote independentemente por floor(elapsed), não por cursor de ordenação. Comparação em memória dos contadores e somas ingress por segundo antes/depois de ordenar por epoch resultou idêntica em toda a grade; janela 201 tem 326 pacotes ingress e 25086 bytes de **payload TCP**. Logo a inversão não desloca pacote entre janelas nem altera essas features; ambos os payloads envolvidos são zero. Não são bytes completos do fio.

Leitura binária offline do PCAP clássico confirmou 95307 registros e oito inversões próprias de 1–14 µs, em outros pontos da sequência (sem executar tcpdump). Duas capturas independentes podem diferir em timestamps/ordem; não foi feito join pacote a pacote. **Inferência:** pequenas reordenações de entrega de pacotes timestampados são compatíveis com os dados. **Hipóteses não comprovadas:** entrega concorrente por CPUs, efeitos do caminho de captura ou variação do relógio. Não há prova de ajuste do relógio; a ordem do CSV por si só não o demonstra. Nenhum arquivo foi reordenado/corrigido.

## 6. Limitações da análise

- Três pilotos, sem replicação: percentuais descritivos não estimam incerteza da campanha nem isolam causalidade. O período POST não é prova automática de recuperação integral.
- Certificações existentes foram lidas e hashes rechecados; não se recalibraram detectores nem se executaram pipelines que escrevem nos datasets. Não houve Docker, captura, experimento ou mudança de protocolo/simulador.
- Qualidade CPU de F96 é replay puro em memória, não novo artefato exportado/certificado de features. Para L2/A3, replay coincide com as qualidades exportadas. Não foi medida latência de cálculo dos detectores.
- O instantâneo Docker tem incerteza delimitada pelos brackets; 100% de snapshots frescos não dá 100% de janelas válidas. As contagens de rejeição por prioridade não isolam causas sistêmicas.
- Capturas íntegras não provam a ausência de toda perda possível fora do ponto observado. Requisições finalizadas no cliente não provam drenagem do processamento interno da vítima.

## 7. Recomendações priorizadas

1. **Maior prioridade, intervenção mínima a investigar:** rever prospectivamente o orçamento temporal da coleta CPU, antecipando chamadas com base nos tempos medidos e garantindo simultaneamente alinhamento dos dois brackets e chegada até a fronteira. Aumentar lead desloca brackets e pode violar ±50 ms; não é um ajuste trivial garantido. Exige validação controlada posterior e registro da mudança de instrumentação; não foi implementado.
2. **Impacto moderado:** investigar a composição da latência (agendamento, chamadas Docker, serialização/fsync), reduzir trabalho no caminho de aquisição ou separar aquisição/persistência com drenagem/falhas explícitas. Primeiro medir; não assumir que fsync ou CPU é culpado. Preservar o contrato científico e timestamps.
3. **Impacto arquitetural maior:** avaliar coleta contínua/streaming ou aquisição dedicada com evidência bracketing equivalente. Pode alterar referências, cronologia e perfil de carga; requer projeto/contratos/testes próprios.
4. **Maior risco metodológico:** permitir disponibilidade posterior, mudar janela/tolerância ou retirar CPU da matriz muda o protocolo científico. Somente revisão prospectiva explícita, sem relaxamento retroativo, preenchimento de lacunas ou exclusão oportunista. Não é a solução desta auditoria.

A escolha entre preservar CPU com instrumentação corrigida ou revisar prospectivamente o escopo deve anteceder a campanha. Não é necessário alterar os pilotos existentes, reordenar o CSV, suprimir falhas HTTP ou recalibrar para ocultar indisponibilidade.

## 8. Decisão recomendada sobre prontidão

**Não pronta para a campanha completa no desenho atual com CPU.** Resolver/validar o contrato temporal CPU é a intervenção que realmente precisa ser decidida antes da campanha; caso contrário há risco concreto de consumir 80 execuções sem suporte às combinações CPU exigidas.

As falhas HTTP são resultados observados relevantes e compatíveis com degradação sob ataque, não motivo para invalidar datasets válidos nem para facilitar critérios. A inversão de 2 µs não exige correção para as features atuais de pacotes/bytes. Nenhuma correção ou commit foi criado nesta atividade.
