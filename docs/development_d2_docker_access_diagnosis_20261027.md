# D2 — diagnóstico de acesso ao Docker no ambiente Codex

Data: 2026-10-27. Diagnóstico feito no mesmo shell/contexto que executa os
utilitários; nenhuma configuração do daemon ou permissão foi alterada.

## Observações

- `docker context show`: `default`; endpoint reportado por `docker context
  inspect`: `unix:///var/run/docker.sock`.
- `DOCKER_HOST` e `DOCKER_CONTEXT` não estão definidos. O simulador e o SDK
  Python usam `unix:///var/run/docker.sock` (`simulator.config.DOCKER_ENGINE_SOCKET`).
- Tanto `docker info` executado diretamente como `docker info` chamado por
  subprocesso Python falharam com `permission denied ... connect:
  operation not permitted`. O SDK Python falhou com `PermissionError(1,
  'Operation not permitted')` no mesmo caminho.
- Processo: UID/GID 1000; grupos suplementares incluem 65534 (`nogroup`).
  Socket: `/var/run/docker.sock`, modo `0660`, owner/group `nobody:nogroup`;
  diretório `/run` tem modo `0755`. A permissão DAC do socket não explica por
  si só o `EPERM` observado.
- `/proc/self/status`: `NoNewPrivs=1`, `Seccomp=2`, um filtro ativo, sem
  capacidades efetivas. `/proc/self/attr/current`: `snap.code.code (complain)`.

## Conclusão e incerteza

A causa operacional confirmada é que este contexto de execução do Codex não
consegue conectar ao socket, apesar de CLI e SDK usarem o mesmo endpoint. A
presença do filtro seccomp e do ambiente confinado é compatível com a negação;
os artefatos disponíveis não identificam qual regra específica produziu o
`EPERM`. AppArmor está em modo `complain`, e as permissões DAC observadas não
justificam ampliar acesso ao socket. Uma chamada CLI anterior autorizada em
outra execução do agente teve sucesso; a diferença entre contextos de chamada
reforça que não se deve inferir falha do daemon nem alterar permissões.

## Comando para o terminal do usuário

Na raiz do repositório e em um terminal com acesso Docker aprovado, execute
somente o preflight abaixo. Ele preserva `pf-0001` e criará um novo relatório
identificado (esperado `pf-0002`, se nenhuma outra checagem for feita):

```bash
.venv/bin/python -B -m experiments.development_d1_ops \
  --manifest experiments/protocols/development_d2_endpoint_comparison_20261027/manifest_v3.json \
  preflight --entry d2_probe_expensive_4rps
```

Somente se a saída indicar `ready: true`, execute o run uma vez, substituindo
o ID pelo `preflight_id` retornado:

```bash
.venv/bin/python -B -m experiments.development_d1_ops \
  --manifest experiments/protocols/development_d2_endpoint_comparison_20261027/manifest_v3.json \
  run --entry d2_probe_expensive_4rps --preflight-id pf-0002
```

O comando `run` aceita apenas um relatório pronto vinculado à mesma entrada e
ao mesmo manifesto. Cada execução continua protegida por `attempt.json`, sem
retry; prontidão pode ser verificada novamente em novos relatórios.
