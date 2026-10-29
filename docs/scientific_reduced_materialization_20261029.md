# Campanha reduzida materializada — sem coleta iniciada

56 configurações reais em `experiments/configs/scientific_reduced_20261029/`:4 BASELINE,8 CAL-A,8 CAL-B e12 blocos TEST C16/M16/E16, com32 seeds novas auditadas. Cada uma das seis ordens aparece duas vezes. Template, gates, proteção e até duas substituições técnicas permanecem vinculados pela especificação. Seeds iguais somente dentro de cada bloco TEST; nenhum dado DEVELOPMENT é entrada de treinamento/TEST.

[Plano](../experiments/protocols/scientific_reduced_20261029/plan.json): SHA256 `752b8c516faf0c931ed19347b298d7348e670797d1e286dfe6c9f6fa7b518385`.

[Especificação](scientific_protocol_reduced_20261029.json): `d4ac35dadcf97a85cecfdaecbdc28bf90ef711fc00cb2874a9872780d7ac9afb`.

[Ambiente](../experiments/protocols/scientific_reduced_20261029/environment.json): `f6ad090b29f5a09aa20bcbb819e49735f624ccb2304a0314c06d40bc6a17f138`.

[Auditoria de seeds](../experiments/protocols/scientific_reduced_20261029/seed_audit.json): `aa351182d29bfe9b06844c755997e898f15abd6664df226cf499dfca941183ad`. Inventário de5330 arquivos históricos com seeds; derivação por namespace/grupo/contador e SHA256, sem colisões observadas. Apenas metadados históricos foram consultados para evitar reutilização.

O plano conserva os hashes de todo o código científico/simulador/experimentos e requisitos/imagens de construção exigidos pelo runner. Alterações posteriores exigem nova revisão do freeze, não troca silenciosa dos hashes. A materialização não fez commit nem modificou autoridades históricas.

## Ambiente observado e limites da prontidão

Consultas reais, somente leitura: daemon Docker `177c5506-8b67-45e1-ab1c-acd019f2994e`, kernel `7.0.0-38-generic` igual ao host, Python3.12.3 e versões locais das sete dependências; IDs das três imagens registrados no lock. Nenhum contêiner em execução. Porta8080 disponível por bind temporário sem listener/tráfego. Socket Docker e teste da porta exigiram acesso fora do sandbox, concedido nesta tarefa. Não houve criação/start de contêiner, build/pull ou requisição à vítima/proxy.

[Observação de prontidão](../experiments/protocols/scientific_reduced_20261029/readiness_observation.json) registra afinidade do host, capabilities de captura e escopo das consultas. Esses registros não certificam recursos de uma vítima ainda não criada. A consistência de fontes dentro das imagens, captura passiva e limites efetivos da vítima serão verificados pelo preflight de cada tentativa antes de liberar fontes. A autoridade está materializada e validável offline, com ambiente observado; **coleta não liberada/iniciada e prontidão completa por tentativa pendente**.

## Caminhos reservados

Raiz futura: `experiment_results/scientific-reduced-20261029/`, ainda ausente ao terminar a materialização. O runner reservará `collection/ID/attempt-1/raw`, `dataset`, `features`, recibos e tentativas consumidas antes da invocação. Substituição técnica aprovada usa `attempt-2`; não apaga a primeira. Análises em `analysis/FEATURE/`, checkpoints em `checkpoints/PARTITION`, journal encadeado e lock exclusivos. Os56 IDs/configurações/paths e32 grupos de seeds constam do [registro de materialização](scientific_reduced_materialization_20261029.json).

## Comandos exatos

Validação offline, sem Docker/carga:

```bash
.venv/bin/python -B -m experiments.scientific_campaign --plan experiments/protocols/scientific_reduced_20261029/plan.json --plan-sha256 752b8c516faf0c931ed19347b298d7348e670797d1e286dfe6c9f6fa7b518385 validate
```

Início futuro somente de BASELINE, quando sua execução for autorizada (não executado nesta preparação). Este comando fará o preflight e então coleta das quatro entradas BASELINE:

```bash
.venv/bin/python -B -m experiments.scientific_campaign --plan experiments/protocols/scientific_reduced_20261029/plan.json --plan-sha256 752b8c516faf0c931ed19347b298d7348e670797d1e286dfe6c9f6fa7b518385 run --partition BASELINE --authorize-partition BASELINE
```

Esse comando não inicia CAL-A. A fase seguinte exige o hash do checkpoint BASELINE e autorização própria. Repetição do mesmo comando recupera evidências de tentativas já consumidas e não gera coleta duplicada. Falhas técnicas/indeterminação/reprovação científica param o runner segundo o contrato. Não editar seeds, outputs ou hashes para contornar um gate. O envelope permanece16h48, teto17h24 com duas substituições; nenhuma tentativa foi consumida aqui.
