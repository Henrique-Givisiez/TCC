# Etapa 3: topologia fixa com uma vítima

A configuração `experiments/configs/single_victim.json` define 30 segundos,
seed 42, `initial=min=max=1`, autoscaler desligado e ataque contínuo entre
10 e 20 segundos planejados. Os demais parâmetros são herdados dos defaults.
`default.json` permanece intacto.

O componente chamado load balancer é um seletor client-side, não um proxy:

```text
gerador no host
  → LoadBalancer.get_next_target()
  → http://localhost:8080
  → Docker port forwarding
  → vítima:80
```

Cada gerador mantém seu seletor e sua lista contendo somente essa URL. A vítima
usa a imagem `edos_target_app:latest`, rede bridge `edos_network` e porta interna
80. Não há novo endpoint intermediário nem containers para os clientes.

## Integridade

Somente para a configuração fixa (`autoscaler.enabled=false` e
`initial=min=max=1`), o orquestrador retém o ID Docker criado no setup.
Consulta esse ID antes de coletar métricas, imediatamente antes de escrever
cada linha e ao terminar a janela experimental. Confirma quantidade, identidade
e estado Docker `running`. Não infere saúde a partir de CPU, memória ou HTTP.

Falha de identidade, container parado/ausente ou erro de consulta interrompe
a execução; o encerramento existente drena os produtores e registra
`run_status.json` com `status=incomplete`, `end_reason=error` e causa em `errors`.
Não há recuperação automática. Linhas válidas anteriores são preservadas.
O campo adicional `topology_integrity` no status contém `expected_victim_id`,
`verified_victim_ids`, `checks` e `last_verified_elapsed_seconds`.
Os schemas científicos dos CSVs permanecem inalterados.

As verificações são amostrais: não demonstram disponibilidade contínua entre
consultas, nem saúde HTTP. A validação verifica também respostas HTTP reais.
Um processo pode parar entre a consulta e a escrita da métrica; a verificação
representa evidência no instante consultado, não uma garantia futura.

`autoscaler_logic.py` permanece intacto: desabilitado retorna `NO_ACTION`.
Setup e cleanup criam/removem a vítima fora da janela; isso não é autoscaling.
Não há alterações nas fórmulas de métricas, custos ou modelos Poisson.

## Validação reproduzível

```bash
python3 -m simulator.main_orchestrator --config experiments/configs/single_victim.json --print-config
python3 -m experiments.validate_single_victim --output /tmp/edos-single-victim-validation
python3 -m unittest discover -s tests -q
```

O runner exige Docker acessível, dependências instaladas, porta 8080 livre e um
diretório de saída novo. Executa sequencialmente A (benigno), B (atacante) e C
(coexistência). B desliga os clientes com `clients=0`; A desliga o ataque com
`enabled=false`. Taxas, pools, timeouts, endpoints e workloads são preservados.
Cada cenário tem `effective_config.json` completo e usa `result_archive.move_result`
para arquivar todos os logs. Os nomes de containers recebem um prefixo único
para que o cleanup não alcance vítimas de execuções convencionais.
Evite execuções concorrentes na mesma porta. O runner não altera permissões
de captura nem tenta elevar privilégios do tcpdump.

A captura mantém `traffic_class=unknown`. Falha de tcpdump permanece em `errors`
e deixa o status incompleto, mesmo que as verificações de serviço passem.
`validation_summary.json` distingue o resultado geral da evidência de tráfego e
infraestrutura. Não fabrica pacotes nem reinterpreta resultados históricos.

A seed reproduz os streams aleatórios e a parametrização, não o scheduling
Docker/rede bit a bit. Tempos efetivos permanecem nos eventos da Etapa 2:
requisições benignas durante ataque continuam benignas; classe de pacote não
é atribuível ao gerador. Duração HTTP não significa RTT TCP.

## Limites e próxima etapa

Uma vítima pode usar vários núcleos; não há nova quota de CPU. A imagem local
já existente é reutilizada pelo Docker manager; disponibilidade da imagem e
porta é requisito operacional. As métricas continuam agregadas conforme os
coletores existentes. Os modelos futuros PeriodicBurst/RandomBurst/CustomPattern
poderão usar a timeline da Etapa 2 independentemente desta topologia; nenhum
scheduler de bursts foi implementado.

A evidência da execução real e amostras de configuração, status e CSVs estão em
[single_victim_validation.md](single_victim_validation.md).
