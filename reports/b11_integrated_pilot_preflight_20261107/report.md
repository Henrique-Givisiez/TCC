# B1.1 — Piloto integrado bloqueado no preflight

## Ambiente
Branch refactor/project-organization; HEAD ab8961ccbf65137bee68dd86009cdc6ddd7bf16e; working tree inicialmente limpo.
Python 3.12.3; Docker Engine 29.9.3 disponível. RAM disponível inicial: 9.488.523.264 bytes.
Disco livre inicial: 2.937.081.856 bytes, inferior aos 4.294.967.296 exigidos pela política.
Não há contêineres em execução. Quatro contêineres externos parados/criados foram preservados.
Inventários e comandos estão em environment.json.

## Preparação
Configuração fornecida confirmada: composição offensive, computational_asymmetry, /expensive,
duas fontes a 1 RPS, zero legítimos, 150 s, ataque [30,60), dois workers, timeout 2 s,
topologia direta e diagnóstico habilitado. Política exploratory-offensive-v1 preservada.
Imagens inventariadas, sem certificação de correspondência com o checkout:
- Vítima: sha256:3f0a418c93db324644b86f06f99b604f6aa0c833faf27abea8a3d484234f3c09.
- Fontes: sha256:b8e3996d9b73a155efc59fef7a33510d33187acf6e4eca488600ed28f26d453c.
Não foram construídas imagens nem criados contêineres temporários. Nenhuma correção de integração.

## Execução e tráfego
Não iniciados por condição insegura no preflight. Zero tentativas de coleta experimental.
Nominal previsto: 2 RPS agregados. Taxas realizadas, admissões, submissões, inícios e conclusões
HTTP, expirações, erros e timeouts não foram observados; ausência de dados não representa zero.

## Vítima
Nenhuma vítima iniciada. Não há medidas de pendências, residual, CPU/op, espera ou CPU Docker.
Comparação com A2 (~227 ms/op) não aplicável.

## Evidências e certificação
Somente evidência ambiental. Não há dataset, captura, journals, diagnósticos, run_status,
manifesto ou certificado experimental. Validadores de dataset não se aplicam sem execução.
Este registro é auditoria prévia, não um attempt certificado pelo executor.

## Limpeza
Nenhum recurso foi criado ou removido. Contêineres externos preservados; redes experimentais
confirmadas sem membros. Nenhuma limpeza destrutiva foi realizada.

## Problemas
Bloqueante: disco livre abaixo do mínimo obrigatório. Limitação: integração e imagens atuais
continuam por validar. Limites não foram flexibilizados.

## Conclusão
Não é possível confirmar prontidão técnica para B1.2 com base neste piloto: ele não foi executado.
É necessário disponibilizar espaço suficiente e realizar nova auditoria antes de uma tentativa
identificada separadamente. Não houve repetição automática, B1.2/B2, push ou alteração de parâmetros.

## Artefatos
reports/b11_integrated_pilot_preflight_20261107/environment.json
reports/b11_integrated_pilot_preflight_20261107/report.md
Nenhum commit de correção.

Nova medição de disco livre: 2936807424 bytes.
Redes e membros: [('edos_network', []), ('edos_sources', [])]
