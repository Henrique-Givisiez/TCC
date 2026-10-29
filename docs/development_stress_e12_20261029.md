# Piloto de estresse E12 — preparado offline

Somente `stress_E12_A` foi materializado: uma vítima, pool de dois processos, proxy estático, autoscaling desligado, quatro clientes ×4 RPS `/medium`, um atacante ×12 RPS `/expensive`. Configuração derivada de E8-R2, mudando apenas ID, seed e taxa ofensiva. Workers legítimos 64 agregados (16 por cliente), ofensivos 64; timeout 2 s. Seed `14077813496258071338`, derivada por SHA256 de namespace próprio e auditada contra 5.293 arquivos com seeds. Não existem configurações E16/E20 deste piloto. A campanha científica de 98 runs permanece pausada e não materializada.

Autoridade: [manifesto](../experiments/protocols/development_stress_e12_20261029/manifest.json). Configuração: [E12](../experiments/configs/development_stress_e12_20261029/stress_E12_A.json). Uma tentativa, zero retries/substituições, nenhuma progressão automática. Resultados reservados sob `experiment_results/development-stress-e12-20261029/`; nenhum resultado real criado.

390 s nominais (warmup 0–30, PRE 30–150, emissão prevista 150–270, observação até390), até30 s de drenagem, ≥60 s de repouso e600 s administrativos: teto18 min. A revisão posterior decide sobre E16, considerando conjuntamente serviço, pendências, vazão, recursos e gerador. p95 >2×PRE ou sucesso <95%, com suporte, é comprometimento forte e exige revisão; não comprova saturação nem capacidade máxima. CPU isolada também não comprova capacidade. O piloto não calibra detectores e não consulta TEST.

## Observador e parada

O adaptador é exclusivo, opt-in via `experiments.stress_runtime`. Não altera os arquivos históricos do simulador nem requer modificação da imagem das fontes. Journals locais são bind mounts; `Journal` fecha cada append. A leitura concorrente aceita apenas linhas completas e verifica identidade/seqüência. Cada decisão conserva os números de sequência efetivamente disponíveis, cutoff observado, disponibilidade da decisão, suporte e motivo; replay usa somente esses prefixos, descartando tempos posteriores ao cutoff.

A cada250 ms, o observador acompanha a origem ofensiva e as coortes legítimas. A janela móvel de starts é `[agora−13, agora−3)`: cada requisição tem ao menos3 s de maturação. Com≥50 starts, ≥20% sem2xx em até3 s do próprio início solicita parada. Respostas posteriores não corrigem retroativamente a decisão. Isso é um limite operacional individual; a revisão de serviço mantém horizonte por janela `b+3 s` e identifica a diferença.

Outros motivos: fila ofensiva admitida ainda não iniciada >128 por≥10 s, ou ausência de nova amostra Docker da vítima por>5 s. O timestamp `read` precisa avançar para renovar o frescor: CPU idêntica em nova amostra é válida; releitura de cache, timestamp repetido ou regressivo não renova a coleta. O observador roda em thread própria, não depende do loop que publica métricas. Erro do observador solicita parada e impede integridade técnica aprovada. Queda/OOM da vítima, proxy ou fonte continua acionando o encerramento de segurança do orquestrador; preservar serviço nesse caso pode ser impossível.

A primeira decisão acionável cria `source_artifacts/stress_stop.json`, com run ID, motivo, horário observado e comando efetivo em relógios monotônico/epoch. Somente `attack_1/control/command.json` recebe stop. Não há segunda parada após certificado de emissão nem início de outro patamar. Se a escrita do comando falhar, SIGTERM à mesma origem é fallback de segurança; a tentativa não ganha integridade presumida. Não se mata o pool da vítima para simular recuperação.

A fonte deixa de admitir novas oportunidades, mas requisições previamente admitidas podem começar depois do comando. O certificado `emission_closed` é a autoridade sobre o fim efetivo; `drained_end_seconds` é outra fronteira. Timeout do cliente não cancela nem comprova cancelamento do trabalho da vítima. Legítimos, captura e recursos continuam até390 s quando operacionalmente possível. Drenagem incompleta permanece registrada e bloqueia conclusão íntegra, sem retry. Limite externo do processo protege o envelope; primeiro SIGINT e oportunidade de cleanup, depois SIGKILL somente se necessário.

## Revisão e recursos

A revisão reutiliza reconciliação/certificados R2, métricas de coortes, coleta, exportação, validação do dataset, vínculos operacionais e publicação sem sobrescrita. A adaptação de lifecycle permite fechamento ofensivo antecipado apenas com comando vinculado e motivo consistente; mantém identidade, horários, contagens e transições emissão→drenagem. ACTIVE termina no certificado real e POST começa depois dele, em grade fixa30 s; recortes com<95% de exposição não recebem qualificação. Nenhum dado posterior ao fim real vira exposição ofensiva nominal.

Referência de serviço: PRE da própria execução. Suporte≥200 starts/durações; p95>1,25×PRE e sucesso<99% evidenciam comprometimento. Janelas fortes (>2×PRE ou<95%) ficam explícitas. Recuperação exige duas janelas POST qualificadas, limites de pendências/idade/crescimento existentes e ofensivas drenadas; fim da janela, horizonte de evidência, disponibilidade batch e publicação são separados. Interrupção por serviço pode permanecer tecnicamente válida e observacionalmente útil. Falta de suporte vira incerteza, não sucesso presumido. Histórico C não é reauditado como requisito novo.

O preflight verifica imagens/código, ausência de concorrência, porta e captura passiva. Um processo Python temporário e ocioso, sem rede e sem HTTP, registra afinidade, quota/cpuset/memória/PIDs e cadeia de cgroups do host. Isso é prontidão, não experimento de capacidade. Antes de liberar qualquer fonte, o adaptador repete a inspeção na vítima real e recusa divergência. Os relatórios conservam HostConfig e limites efetivos; não inferem capacidade medida. Kernel/cgroup v2, permissões de inspeção e imagens ainda precisam passar nessa futura verificação real.

O registro de tentativa antecede a invocação; o runtime exige os argumentos e hashes vinculados e cria um marcador exclusivo, impedindo invocação duplicada. Revisões/dados anteriores, inclusive a reprovação original de D3_origins, permanecem intocados. A autoridade nova vincula o código atual por SHA256 e registra os arquivos históricos dos quais os adaptadores foram derivados.

## Uso futuro

Somente preflight, sem carga HTTP:

```bash
.venv/bin/python -B -m experiments.stress_pilot_ops preflight --entry stress_E12_A
```

Execução depende de autorização posterior específica e preflight aprovado; não foi executada nesta preparação:

```bash
.venv/bin/python -B -m experiments.stress_pilot_ops run --entry stress_E12_A --preflight-id pf-0001 --authorize-entry stress_E12_A
.venv/bin/python -B -m experiments.stress_pilot review
```

Use o ID realmente emitido pelo preflight. O comando de run não é retomável/repetível; tentativa consumida ou outputs existentes bloqueiam nova coleta. Após cleanup, respeitar≥60 s de repouso. A revisão não autoriza E16/E20.

Validação: [registro offline](../experiments/protocols/development_stress_e12_20261029/offline_validation.json). Passaram17 testes (9 do piloto e8 de fontes), incluindo exportação, dataset, revisão vinculada e recusa de sobrescrita. A execução ampliada teve29/30 aprovados: o teste legado `test_e_tcpdump_timestamp_unknown_and_final_timeline` também falha isoladamente porque chama `stop()` sem processo de captura, ramo que retorna sem reconciliar. Teste e sniffer são idênticos ao HEAD e não foram alterados; o caminho com processo/captura parcial é coberto pela regressão aprovada. Essa pendência de fixture histórico fica explícita, sem modificar autoridades anteriores.
