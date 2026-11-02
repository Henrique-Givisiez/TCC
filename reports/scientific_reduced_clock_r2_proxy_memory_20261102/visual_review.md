# Inspeção e verificações da investigação de memória

Inspeção em 02/11/2026 das três figuras em proporção e tamanho de página A4 paisagem, em prévias de 1.403 pixels de largura. Todas mantêm amplitude integral, unidades e suporte identificados. Foram examinadas legendas, blocos, limites de emissão/parada, distribuições e a distinção entre níveis e diferenças. Os rótulos da figura C foram ampliados para melhorar a leitura dos nove grupos.

| Figura | Inspeção |
|---|---|
| A — 36 execuções | Uma linha por bloco em cada cenário, escala comum em MiB, uma leitura nativa por célula de 1 s. A oscilação de B01 também aparece nos outros blocos, inclusive C16/PRE. Início/fim e comando estão marcados por linha; C16 não recebe fronteiras ofensivas. Não há preenchimento ou recorte da amplitude. |
| B — ECDFs por run/fase | As curvas preservam as duas regiões da distribuição e os picos raros. E16/ACTIVE desloca a distribuição para valores inferiores sem remover todos os picos. Cada curva é uma execução, com denominador próprio; não se definiu limiar alto/baixo ou componente de memória. |
| C — associações por run/fase | Cada ponto resume uma execução/fase; linhas de zero não representam ausência imputada. Níveis e diferenças aparecem separados. Os efeitos de nível em conexões/upstream não se repetem da mesma forma nas diferenças, enquanto a associação com duração de status é mais consistente. N e motivos de coeficiente indefinido estão no CSV. |

PDFs finais: vetoriais, incluindo a barra de cores, com fontes TrueType incorporadas e texto dentro das páginas. PNGs: 300 dpi. Recomenda-se usar as páginas em largura integral; a leitura dos 36 blocos exige esse espaço.

As verificações de [verification.json](verification.json) cobrem:

- 14.094 memórias em bytes/MiB e diferenças consecutivas conferidas contra os JSONL vinculados nos datasets;
- 108 médias/fases coincidentes com a apresentação anterior, sem alteração de artefatos;
- 119 falhas de status preservadas como ausência de Reading/Writing/Waiting/active, sem último valor carregado;
- janelas científicas estritamente em [t−1,t), por run/classe, com volume observado e média upstream sem observações mantida ausente;
- 31 pequenos gaps estimados negativos mantidos, sem transformá-los em zero ou interpretá-los como inversão da sequência de código;
- 14.094 logs de monitoring com pareamento temporal único, sem reutilização; zero slots pulados e nenhum docker_read repetido;
- chaves reais da resposta serializada: memória apenas em `memory_usage_bytes`; não há componentes ou memória por PID;
- coeficientes descritivos com suporte registrado, variáveis constantes indefinidas e ausência de p-valores/ICs ou testes inferenciais;
- hashes das saídas e formato das três exportações.

Cinco testes unitários passaram: postos com empates, suporte/constantes/ausências, pareamento temporal limitado sem reutilização, regras sem limiar de memória e descoberta de campos de memória. Três proteções da CLI foram exercitadas sem escrever nos diretórios protegidos: SHA incorreto, sobrescrita sem opção explícita e tentativa de saída no relatório anterior. Ver [cli_checks.json](cli_checks.json).

Repetir somente verificações, na raiz do repositório:

```bash
.venv/bin/python -B reports/scientific_reduced_clock_r2_proxy_memory_20261102/test_memory.py
.venv/bin/python -B reports/scientific_reduced_clock_r2_proxy_memory_20261102/verify_outputs.py
```

O [comando de reprodução](reproduce.sh) executa exclusivamente a análise offline. A investigação se restringiu às quatro verificações solicitadas. Não houve alteração do monitor, configuração, resultados científicos ou apresentações anteriores, nem preparação/execução de outro experimento. A identidade causal do componente de memória continua sem suporte: faltam decomposição sincronizada do cgroup e memória/vida/liberação dos processos.
