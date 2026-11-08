# Correção pontual PCAP após F96

Base: `66f623d9faa55432976294b54edfef937cb607e9`, branch `refactor/project-organization`, working tree inicialmente limpo.

## Diagnóstico

O parser exigia `packets` nos três contadores. A linha `1 packet dropped by kernel` não correspondia ao padrão, gerando `None` e estatísticas incompletas. A rejeição anterior foi correta; nenhum artefato ou certificação foi reescrito. Os números desta nova tentativa são os fornecidos pelo operador; não se fez nova auditoria dos pilotos nesta atividade.

## Buffer e fatores alternativos

Antes, PCAP não passava `-B`; CSV solicitava `-B 4096`. O ambiente consultado tem tcpdump 4.99.4, libpcap 1.10.4 (suporte TPACKET_V3), kernel 7.0.0-42-generic. Não houve captura ativa para medir a alocação real.

O backend Linux da libpcap 1.10.4 solicita por padrão ring de 2 MiB. O mesmo código evita TPACKET_V3 em immediate mode, usando V2; pode reduzir o ring ao encontrar ENOMEM. Portanto, suporte V3 anunciado não demonstra uso de V3 nesta captura, e tamanho solicitado não garante tamanho alocado. [Código da versão libpcap 1.10.4](https://raw.githubusercontent.com/the-tcpdump-group/libpcap/libpcap-1.10.4/pcap-linux.c).

`-B 4096` solicita 4096 KiB (4 MiB) ao buffer de captura. É uma mudança local adequada para dar margem a rajadas/pausas e igualar a solicitação CSV. `-U` com `-w` entrega a saída ao arquivo por pacote, podendo contribuir com custo de I/O; foi mantido. [Manual tcpdump 4.99.4](https://raw.githubusercontent.com/the-tcpdump-group/tcpdump/tcpdump-4.99.4/tcpdump.1.in).

Os limites locais lidos foram `net.core.rmem_max=4194304` e `rmem_default=212992` bytes. Não foram alterados e não determinam, por si sós, o tamanho do ring PACKET_RX_RING. A alocação depende de geometria, memória e implementação do backend; o Linux exige restrições de alinhamento dos blocos/frames. [Documentação PACKET_MMAP](https://www.kernel.org/doc/html/latest/networking/packet_mmap.html).

A hipótese de buffer menor é plausível, não comprovada pelo único descarte. Contenção entre capturas, I/O por pacote, rajadas e pausas de escalonamento também podem explicar esgotamento transitório. O código encerra produtores antes das capturas, solicita SIGTERM e aguarda até 5 s, recorrendo a SIGKILL em timeout (falha explícita). Janelas distintas podem gerar diferenças nas contagens, mas não justificam aceitar um descarte reportado pelo kernel. Não há evidência temporal/perfil de processos nesta atividade para atribuir a perda ao encerramento ou a um desses fatores.

## Alterações

- Parser aceita `packet` e `packets` nos três contadores. Conta também ocorrências malformadas com o mesmo identificador, rejeitando duplicata válida + inválida. Somente um valor decimal não negativo por contador é aceito.
- PCAP passa `-B 4096`, registrado naturalmente no argv do sidecar. Interface, BPF, immediate mode, `-U`, formatos, tráfego, CPU e critérios de integridade preservados.
- Zero descartes continua condição necessária; descartes positivos, contador ausente/duplicado/inválido ou retorno inválido continuam rejeitados.

## Validação e próximos passos

128 testes passaram em 9,600 s:

```
.venv/bin/python -m unittest tests.test_capture_lifecycle tests.test_tcpdump_writer tests.test_source_containers tests.test_dataset_validation tests.test_dataset_export tests.test_diagnostics tests.test_clock_diagnostics
```

Incluem singular/plural para todos os contadores, zero/um/múltiplos descartes, valores inválidos, ausência, duplicação e duplicação mista; caso PCAP 94652/94653/1 com inteiro 1 persistido e rejeição; argv PCAP exato, aceitação sem perdas, drenagem/escritor CSV e contratos de dataset. `git diff --check` passou. Processos tcpdump nos testes são fakes; não se verificou alocação efetiva sob carga.

Nenhum F96 ou campanha foi executado, nem artefatos anteriores modificados. A tentativa com um descarte permanece rejeitada. Buffer maior consome mais memória e pode continuar insuficiente; não substitui capacidade sustentada de processamento/I/O.

Recomendação: próxima tentativa F96 autorizada em diretório novo, mesma configuração científica, com o novo commit registrado. Exigir zero descartes em CSV e PCAP, estatísticas completas, encerramento/drenagem e certificação aprovados; conferir contagens e janelas. Preservar todos os artefatos caso volte a falhar e medir o capturador antes de novas alterações. A perda não está definitivamente resolvida sem validação real.
