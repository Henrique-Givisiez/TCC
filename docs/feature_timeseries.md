# Etapa 10 — séries regulares de observações

`experiments.extract_features` transforma um dataset Stage 8 com relatório Stage 9
correspondente e analysis_eligible=true em quatro CSVs regulares e autodescritivos.
Não modifica inputs, produtores ou etapas anteriores. Não utiliza o extrator legado
em analysis/, detectores, thresholds, normalização, smoothing, imputação, mediana
ou remoção de outliers. Usa somente biblioteca padrão, CSV e JSON.

```bash
.venv/bin/python -B -m experiments.extract_features \
  experiment_results/stage8-final/stage7-validation/periodic \
  --validation-report experiment_results/stage9-final/stage7-validation/periodic/validation_report.json \
  --output experiment_results/my-features \
  --window-size-seconds 1
```

API: `extract_features(dataset, validation_report, destination, window_size_seconds='1')`.
A versão inicial exige elegibilidade, sem override. Destino deve ser novo e separado
dos inputs, sem nesting ou overwrite. A publicação é feita após construção em
diretório temporário e nova conferência dos hashes. Erros não publicam saída parcial.
Inputs devem estar encerrados/quiescentes; não existe locking de produtores.

## Estrutura

```text
feature_dataset/
  feature_manifest.json
  feature_schema.json
  timeseries/
    network.csv
    service.csv
    infrastructure.csv
    labels.csv
  evidence/
    stage9_validation_report.json
```

Schema e extrator usam versão 1. Cada tabela tem uma linha por janela e chaves
iguais: run_id, window_index, window_start_seconds, window_end_seconds. Chaves
não são features. O schema documenta tipo, unidade, nullability, papel e semântica
de cada campo; detector_columns é a lista explícita de entradas permitidas.
labels.csv possui detector_columns vazio. CSV null é célula vazia, não NaN/zero.

## Tempo e horizonte

Origem elapsed=0 do experimento, com âncoras epoch/monotônica registradas no
manifest. Requests e ticks usam elapsed monotônico; packets usam elapsed
epoch-âncora epoch já registrado. Nada é reconvertido para aparentar sincronismo.

Para Δ positivo finito, configurable e default inicial 1 s:

```text
Wk = [k*Δ, (k+1)*Δ)
Tmax = max(packet elapsed, request start/end elapsed, metric tick elapsed)
N = max(ceil(planned_duration/Δ), floor(Tmax/Δ)+1)
grid_end = N*Δ
```

Tmax inclui ticks sem suporte e packets cuja direção não seja suportada, pois são
observações persistidas. Ground truth não determina o horizonte. Todas as janelas
são completas, incluindo vazias e a cauda pós-duração. Observação exatamente na
borda pertence à janela seguinte, inclusive quando a borda é a duração planejada.
Elapsed negativo causa recusa explícita: não é descartado nem deslocado silenciosamente.

A atribuição e limites usam Decimal a partir dos valores textuais. Precisão é
derivada da amplitude/exponentes dos inputs, com mínimo 50 dígitos; não usa epsilon.
A representação de médias utiliza 50 dígitos significativos e ROUND_HALF_EVEN;
não há quantização em casas fixas. A política é explícita no manifest, independentemente
do contexto Decimal do chamador. Médias são somas em ordem determinística e pesos iguais.

Manifest registra duração planejada, última observação, grid_end, trecho após
última observação, cauda após plano e padding além de ambos. **Nenhum desses
trechos é declarado cobertura comprovada.** Janelas finais podem conter somente
packets, com service counts zero e médias de infraestrutura null.

## Semântica das features

| Família | Feature | Unidade e definição |
|---|---|---|
| network | ingress_packet_count | Registros de packet source→proxy em W |
| network | egress_packet_count | Registros proxy→source em W |
| network | ingress_tcp_payload_length_sum_bytes | Soma do campo packet_length no ingresso, em bytes |
| network | egress_tcp_payload_length_sum_bytes | Soma do mesmo campo no retorno, em bytes |
| network | unique_client_src_ips | IPs distintos de sources presentes como origem no ingresso |
| service | request_starts | Tentativas por elapsed_seconds de começo |
| service | request_completions | Tentativas por end_elapsed_seconds conhecido |
| service | request_failures | Conclusões http_error + transport_error + client_error |
| service | http_failures | Conclusões outcome=http_error, HTTP ≥400 |
| service | transport_failures | Conclusões outcome=transport_error |
| service | client_failures | Conclusões outcome=client_error |
| service | mean_duration_ms | Média de duration_ms de todas as tentativas concluídas em W, incluindo falhas |
| infrastructure | mean_cpu_percent | Média dos average_cpu_percent dos ticks suportados em W |
| infrastructure | mean_memory_mib | Média dos mem_usage dos mesmos ticks, em MiB |

Counts/sums em família disponível vazia são zero: **zero registros**, não prova de
ausência física ou captura completa. Médias sem samples são null; médias observadas
iguais a zero continuam zero. Não são produzidas rates/s ou features normalizadas
pelo tamanho da janela. Não existe critério de número mínimo de samples para média:
um sample conhecido é suficiente, cuja limitação é auditável na origem.

### Rede

Direção exige inventory + capture_metadata de segmento source_proxy. Clientes
são TODOS os IPs do inventário, sem ler traffic_class/source_type para selecionar
tráfego. IP do proxy vem da capture metadata; porta de serviço vem do endpoint
dos sources, exigindo uniformidade. Ingresso: client→proxy:service_port;
retorno: proxy:service_port→client. Pacote não classificável nesse segmento provoca
erro, não exclusão silenciosa. Proxy não é contado como client_src_ip.

packet_length é o resumo do payload TCP extraído pelo parser existente, não frame
Ethernet, bytes on-wire ou HTTP útil único. Handshake/ACKs com comprimento zero
contam como registros. Nenhuma descrição duplicada/retransmissão é deduplicada.

Datasets antigos no host sem o inventário/segmento exigido recebem as cinco
features network como null e warning NETWORK_DIRECTION_UNAVAILABLE. Seus packets
continuam participando de Tmax e dos spans observados. Não se inventa client
identity ou direção a partir de traffic_class, portas de vítimas ou assumptions
do modo containers. Service/infrastructure continuam disponíveis. Stage 9 eligibility
é geral e não prova aplicabilidade de toda família de features da versão 1.

### Serviço

Fonte: request_log.csv, nunca apenas rtt_log (subconjunto response). Início e
conclusão de uma request podem ser atribuídos a janelas distintas. Duração é do
cliente, incluindo transporte/instrumentação; não TCP RTT nem CPU da aplicação.
HTTP/transport/client failures continuam observações da média. Incomplete sem
end conhecido não recebe conclusão/falha/duração fictícia e aparece nos diagnósticos.

### Infraestrutura

O coletor já produz médias de histórico recente e fallback para cache, arredondadas
na escrita original. A média Stage 10 é média dos valores reportados, não dados
Docker individuais ou média ponderada por tempo. CPU pode superar 100%; mem_usage
tem unidade MiB apesar do nome histórico.

active_containers_names vazio identifica falta de suporte do coletor no contrato
atual. O tick é preservado nos diagnósticos com elapsed, window_index e valores
reportados originais, mas excluído das médias. Janela sem tick suportado permanece
null. Nomes presentes permitem zeros observados; frescor do cache não é reconstruível
e seus valores não são removidos. Nenhuma correção é aplicada ao CSV original.

## Labels e diagnósticos

Exclusivamente labels.csv:

* attack_event_overlap_seconds: tamanho da interseção W com a união dos intervalos
  efetivos [actual_start,actual_end), sem dupla contagem de eventos sobrepostos.
* attack_event_overlap_fraction: overlap_seconds/Δ, sem binarização.
* attack_request_starts: quantidade causal de starts atacantes pela janela de início.

drained_end não define overlap. Silêncio de PeriodicBurst continua dentro do evento
global. Sem evento efetivamente iniciado, overlap é zero; evento iniciado sem fim
conhecido provoca recusa, não label inventado. Params de burst/perfil, event IDs,
traffic_class/attack_active e quaisquer campos causais não aparecem em feature CSVs.

Manifest/evidence também não são entradas do detector. Não selecionar automaticamente
todas as colunas numéricas: usar detector_columns, excluindo chaves, timestamps,
labels, suporte/cobertura, cenário e proveniência. Características de ausência/cauda
podem correlacionar com a campanha; isso exige cuidado posterior na avaliação.

## Cobertura, integridade e proveniência

observed_coverage registra primeira/última observação e contagem de instantes para
network, service (inícios + conclusões) e infrastructure suportada. Também explicita
service_starts, service_completions e infrastructure_records (incluindo placeholders).
Esses spans têm completeness=not_proven; não definem um período garantido de captura.

O extrator verifica report schema, dataset schema, run ID, dataset_manifest_sha256,
dataset_valid e analysis_eligible. Confere hash/tamanho de TODOS os inputs consumidos
antes da leitura e novamente seus hashes antes da publicação, mais manifest/report.
A cópia byte a byte do report também tem SHA conferido. Origin paths externos não
são utilizados. Hashes não são assinatura de autenticidade de relatório/manifest.

input_files lista paths relativos ao Stage 8 identificado por source_run_id/hash.
Configuração/status, raw CSVs e topologia efetivamente usados são indexados; raw
inputs não são duplicados na saída. Outputs registram SHA/tamanho de quatro CSVs,
schema e report copiado. Manifest não contém hash de si mesmo, evitando circularidade.

Proveniência identifica scope feature_extraction, Git SHA/dirty, hashes do runtime
e dos arquivos do extrator/schema/helper, Python/OS/kernel. Dirty tem escopo explícito
de código/receitas/dependências, excluindo docs e outputs gerados; não é sinônimo de
estado dirty de toda a árvore. Não registra timestamp variável de extração ou
paths absolutos de destino. Mesmos inputs/código/proveniência/ambiente produzem
os mesmos bytes; mudanças nesses elementos são declaradas, não mascaradas.
Não afirma que essa versão do código executou o run histórico. Warnings Stage 9
são preservados no manifest, junto às limitações de network/startup/completions.

## Testes e resultados

```bash
.venv/bin/python -B -m unittest tests.test_feature_extraction -v
.venv/bin/python -B -m unittest discover -s tests -q
```

Fixtures são datasets Stage 8 temporários e relatórios Stage 9 sintéticos. Corrupções
nunca atingem dados reais. Testes de não uso de causal class exercitam essa independência
isoladamente; não equivalem a validação científica de um inventário corrompido.

Resultados reais, warnings e evidência temporal estão em [feature_extraction_results.md](feature_extraction_results.md).
Limitações: clock drift, captura parcial, payload TCP/retransmissões, ausência de
direção nos hosts legados, médias/cache prévios e zeros sem suporte. A implementação
mantém agregações em memória; grades muito extensas ou Δ muito pequeno podem exigir
mais memória. Nenhum threshold científico é imposto para resolver esse limite.
Detectores e políticas de avaliação ficam para a Etapa 11.
