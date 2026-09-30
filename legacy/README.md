# Código histórico

- `main_orchestrator_back.py`: orquestrador anterior, sem chamadas identificadas nos runners atuais.
- `traffic_injector.py`: injetor usado pelo orquestrador de backup; o fluxo ativo usa `simulator/traffic_injectorV0.py`.
- `Versions/`: snapshots ZIP e documentação histórica, preservados sem alteração.

Os imports dos dois módulos foram ajustados à nova organização. Eles ainda dependem de módulos compartilhados atuais; esta etapa não certifica compatibilidade funcional do fluxo antigo. Caso necessário, os módulos são executáveis a partir da raiz com `python3 -m legacy.<módulo>` e exigem os mesmos cuidados com Docker e tráfego.

Scripts de gráficos numerados e retomadas específicas de experimentos foram mantidos em `analysis/` e `experiments/`, pois sua substituição não foi demonstrada.
