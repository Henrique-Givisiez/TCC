# Inventário observado — diagnóstico anterior à Etapa 11

Leitura em 15/10/2026. Cada linha é uma execução identificada por run_id; cópias não contam como repetição. JSON guarda configurações completas, eventos efetivos, todos os caminhos, relatórios e referências. Taxas são nominais por source, não contagens realizadas. Atacantes configurados com enabled=false não significam tráfego atacante.

## Datasets padronizados

| Origem | run_id | status/elegível | T/seed | Benigno: sources × RPS; operação | Ataque: sources × RPS; operação; perfil | Início/duração planejados; burst | Modo/proxy/vítimas | Δ; N/S/I |
|---|---|---|---|---|---|---|---|---|
| manual-test/periodic-dataset | `67273219aab144799f7474719b411662` | completed/não avaliado | 15 s / 42 | 4 × 2; /light | 1 × 10; /expensive; periodic_burst | 2/11.5 s; {'period_seconds': 3, 'duration_seconds': 1, 'jitter_seconds': None} | containers/True/1 | ausente |
| stage7-regressions/stage3/A | `5dc389a82b9f4639a0cd62c627bf87a4` | completed/True | 30 s / 42 | 4 × 10; / | desabilitado | 10/10 s; None | host/False/1 | 1 s; não/sim/sim |
| stage7-regressions/stage3/B | `9e91c57a00ce4c1cb434b65d975b24d0` | completed/True | 30 s / 42 | 0 × 10; / | 4 × 10; /; continuous | 10/10 s; None | host/False/1 | 1 s; não/sim/sim |
| stage7-regressions/stage3/C | `0a9e7ffd4984415ebb43d1828a029440` | completed/True | 30 s / 42 | 4 × 10; / | 4 × 10; /; continuous | 10/10 s; None | host/False/1 | 1 s; não/sim/sim |
| stage7-regressions/stage4/A | `eec833adeaa843829e9902dff5041c55` | completed/True | 30 s / 42 | 4 × 10; / | desabilitado | 10/10 s; None | host/True/1 | 1 s; não/sim/sim |
| stage7-regressions/stage4/B | `cae84b78088449889bfb2f2e7600c673` | completed/True | 30 s / 42 | 0 × 10; / | 4 × 10; /; continuous | 10/10 s; None | host/True/1 | 1 s; não/sim/sim |
| stage7-regressions/stage4/C | `c48d973ce7a840cc8fbfc543f16224ec` | completed/True | 30 s / 42 | 4 × 10; / | 4 × 10; /; continuous | 10/10 s; None | host/True/1 | 1 s; não/sim/sim |
| stage7-regressions/stage4/failure | `269fb62699144d7cada6289620e8458d` | incomplete/False | 10 s / 42 | 4 × 10; / | desabilitado | 10/10 s; None | host/True/1 | ausente |
| stage7-regressions/stage4/technical | `101a04aeedc147b79baca310524972cc` | completed/True | 10 s / 42 | 4 × 10; / | desabilitado | 10/10 s; None | host/True/2 | 1 s; não/sim/sim |
| stage7-regressions/stage5/A | `bd1303b0312e4b3bbf9436d92ae02b77` | completed/True | 30 s / 42 | 4 × 10; / | desabilitado | 10/10 s; None | containers/True/1 | 1 s; sim/sim/sim |
| stage7-regressions/stage5/B | `1f40809ba7f247ad9a26d20f4253a809` | completed/True | 30 s / 42 | 0 × 10; / | 4 × 10; /; continuous | 10/10 s; None | containers/True/1 | 1 s; sim/sim/sim |
| stage7-regressions/stage5/C | `0753ec271c414dc79fed784be2d86d20` | completed/True | 30 s / 42 | 4 × 10; / | 4 × 10; /; continuous | 10/10 s; None | containers/True/1 | 1 s; sim/sim/sim |
| stage7-regressions/stage5/failure | `393c9ecad8c6407abd1c3b8c2bae9f73` | incomplete/False | 10 s / 42 | 4 × 10; / | 4 × 10; /; continuous | 1/8 s; None | containers/True/1 | ausente |
| stage7-regressions/stage6/expensive | `3bb3047840d0477d983446d9a0806d08` | completed/True | 8 s / 42 | 4 × 2; /expensive | 4 × 2; /expensive; continuous | 2/4 s; None | containers/True/1 | 1 s; sim/sim/sim |
| stage7-regressions/stage6/light | `763570269483495fbe0b3d2468bcd219` | completed/True | 8 s / 42 | 4 × 2; /light | 4 × 2; /light; continuous | 2/4 s; None | containers/True/1 | 1 s; sim/sim/sim |
| stage7-regressions/stage6/medium | `33623c248c6049eda4f3f27981550de0` | completed/True | 8 s / 42 | 4 × 2; /medium | 4 × 2; /medium; continuous | 2/4 s; None | containers/True/1 | 1 s; sim/sim/sim |
| stage7-validation/capacity | `0440b798496f4fb3abf25cffd0ca7f07` | completed/True | 15 s / 42 | 4 × 2; /light | 1 × 10; /expensive; periodic_burst | 2/11.5 s; {'period_seconds': 3, 'duration_seconds': 1, 'jitter_seconds': None} | containers/True/1 | 1 s; sim/sim/sim |
| stage7-validation/continuous | `aac4906df9ae494ab1d87ca99adcc8b6` | completed/True | 15 s / 42 | 4 × 2; /light | 1 × 10; /light; continuous | 2/11.5 s; None | containers/True/1 | 1 s; sim/sim/sim |
| stage7-validation/multiple | `f059147f9be94d499f509535a55acf85` | completed/True | 15 s / 42 | 4 × 2; /light | 4 × 10; /light; periodic_burst | 2/11.5 s; {'period_seconds': 3, 'duration_seconds': 1, 'jitter_seconds': None} | containers/True/1 | 1 s; sim/sim/sim |
| stage7-validation/periodic | `99619e207ea2462b9b2eea7cba67940a` | completed/True | 15 s / 42 | 4 × 2; /light | 1 × 10; /expensive; periodic_burst | 2/11.5 s; {'period_seconds': 3, 'duration_seconds': 1, 'jitter_seconds': None} | containers/True/1 | 1 s; sim/sim/sim |
| stage8-validation/fresh-periodic-dataset | `927e03c2d49843c8b74427070067527e` | completed/True | 15 s / 42 | 4 × 2; /light | 1 × 10; /expensive; periodic_burst | 2/11.5 s; {'period_seconds': 3, 'duration_seconds': 1, 'jitter_seconds': None} | containers/True/1 | 1 s; sim/sim/sim |

N/S/I = famílias network/service/infrastructure. Infra disponível não significa ausência de null. Todos têm autoscaler desligado, pool de 2 workers, monitoramento 1 s e histórico 30 s. As diferenças de operação, workload, concorrência e timeout estão em runs.json. Nos 17 elegíveis históricos a proveniência de execução não foi registrada; fresh-periodic registra execução com árvore dirty. Manual-test registra proveniência, mas não tem validação Stage 9 final nem features finais. Os dois incomplete são dataset_valid=true e analysis_eligible=false.

Warnings: NETWORK_DIRECTION_UNAVAILABLE nos sete elegíveis host; INFRASTRUCTURE_RECORDS_WITHOUT_SUPPORT nos 18 feature datasets; STAGE9_WARNING nos 18. Falha stage4: 31 requests sem response; falha stage5: 46 falhas e falta de observações pós-fim planejado em três modalidades. Detalhes literais e fingerprints em feature_references.json.

## Demais execuções identificáveis

Não possuem a cadeia final Stage 8 → 9 → 10. São desenvolvimento/regressão, não reservas científicas. Há 16 benignos completed entre os 58 IDs totais, mas apenas quatro benignos elegíveis na cadeia final; nenhum dos 58 muda a seed 42. Não confundir repetição da mesma seed com replicação da aleatoriedade.

| Origem | run_id | Status | T | Benignas × taxa; operação | Atacantes × taxa; operação/perfil | Início/duração; burst | Modo/proxy/vítimas |
|---|---|---|---|---|---|---|---|
| stage4-final/A | `0552fece56364278aa24fefbccbbc1df` | completed | 30 | 4 × 10; / | False: 4 × 10; //continuous | 10/10; None | não registrado/True/1 |
| stage4-final/B | `adeeb14748a340b39cdd3142093e03ba` | completed | 30 | 0 × 10; / | True: 4 × 10; //continuous | 10/10; None | não registrado/True/1 |
| stage4-final/C | `f060075d028d4b6cbd0021d0bbc60fba` | completed | 30 | 4 × 10; / | True: 4 × 10; //continuous | 10/10; None | não registrado/True/1 |
| stage4-final/failure | `880ce269d0d04be0a403d10fbe2aa40c` | incomplete | 10 | 4 × 10; / | False: 4 × 10; //continuous | 10/10; None | não registrado/True/1 |
| stage4-final/technical | `f5d2f18261094190806d9e50abb5a0e7` | completed | 10 | 4 × 10; / | False: 4 × 10; //continuous | 10/10; None | não registrado/True/2 |
| stage4-native/A | `732e383c2fae4440bad01598907d51cd` | completed | 30 | 4 × 10; / | False: 4 × 10; //continuous | 10/10; None | não registrado/True/1 |
| stage4-native/B | `3d6c2d0f403e4e2ea787367e223a9cf2` | completed | 30 | 0 × 10; / | True: 4 × 10; //continuous | 10/10; None | não registrado/True/1 |
| stage4-native/C | `bca50db8c6ab4ab480b28b1e5274b1ce` | completed | 30 | 4 × 10; / | True: 4 × 10; //continuous | 10/10; None | não registrado/True/1 |
| stage4-native/failure | `8a62bf6c5e5d4829add04244d3950d4d` | completed | 10 | 4 × 10; / | False: 4 × 10; //continuous | 10/10; None | não registrado/True/1 |
| stage4-native/failure_real | `0df848ce18874796ba1b88838436cea2` | incomplete | 10 | 4 × 10; / | False: 4 × 10; //continuous | 10/10; None | não registrado/True/1 |
| stage4-native/technical | `30d5fb1070054da4a681d117168fd08b` | completed | 10 | 4 × 10; / | False: 4 × 10; //continuous | 10/10; None | não registrado/True/2 |
| stage5-development/A | `abdf51c57c5b42d993db59f6e5351dfe` | incomplete | 30 | 4 × 10; / | False: 4 × 10; //continuous | 10/10; None | containers/True/1 |
| stage5-development/A2 | `df9fa04918c2408382ac897d66bbdec8` | completed | 30 | 4 × 10; / | False: 4 × 10; //continuous | 10/10; None | containers/True/1 |
| stage5-development/B | `c82a383756db4bc087d2e00bf9c9abd3` | completed | 30 | 0 × 10; / | True: 4 × 10; //continuous | 10/10; None | containers/True/1 |
| stage5-development/C | `fb2d3805f4724bfeb2ac2ee83618c0f6` | completed | 30 | 4 × 10; / | True: 4 × 10; //continuous | 10/10; None | containers/True/1 |
| stage5-development/failure | `77415133fc494c609612368f73991df7` | incomplete | 10 | 4 × 10; / | True: 4 × 10; //continuous | 1/8; None | containers/True/1 |
| stage5-final/A | `d5a88ccf41484d62847338780a481a15` | completed | 30 | 4 × 10; / | False: 4 × 10; //continuous | 10/10; None | containers/True/1 |
| stage5-final/B | `84859740b32e435f97a53af1c81fc55a` | completed | 30 | 0 × 10; / | True: 4 × 10; //continuous | 10/10; None | containers/True/1 |
| stage5-final/C | `e0a14b5c95984fedb957c33a57089134` | completed | 30 | 4 × 10; / | True: 4 × 10; //continuous | 10/10; None | containers/True/1 |
| stage5-final/failure | `2aa7303d2d234dc5a3662435add66599` | incomplete | 10 | 4 × 10; / | True: 4 × 10; //continuous | 1/8; None | containers/True/1 |
| stage5-final/regression-stage4/A | `aa90b5d0e30742dfb8ef3734b7e51c9c` | completed | 30 | 4 × 10; / | False: 4 × 10; //continuous | 10/10; None | host/True/1 |
| stage5-final/regression-stage4/B | `69b86316f3e248988bd690fee16c4789` | completed | 30 | 0 × 10; / | True: 4 × 10; //continuous | 10/10; None | host/True/1 |
| stage5-final/regression-stage4/C | `010fa174a95b47aba8a88dec59a954ff` | completed | 30 | 4 × 10; / | True: 4 × 10; //continuous | 10/10; None | host/True/1 |
| stage5-final/regression-stage4/failure | `273b7b4d36954f938222507aed02984b` | incomplete | 10 | 4 × 10; / | False: 4 × 10; //continuous | 10/10; None | host/True/1 |
| stage5-final/regression-stage4/technical | `a1e0d4e48c1846e9ba7804c5aafd3e4e` | completed | 10 | 4 × 10; / | False: 4 × 10; //continuous | 10/10; None | host/True/2 |
| stage6-regressions/stage4/A | `34a49acce14145799f7f30e35a50c10b` | completed | 30 | 4 × 10; / | False: 4 × 10; //continuous | 10/10; None | host/True/1 |
| stage6-regressions/stage4/B | `92480564dabc4986af878ade5467242a` | completed | 30 | 0 × 10; / | True: 4 × 10; //continuous | 10/10; None | host/True/1 |
| stage6-regressions/stage4/C | `378eea926d794e12bfc01e9520b5b6ea` | completed | 30 | 4 × 10; / | True: 4 × 10; //continuous | 10/10; None | host/True/1 |
| stage6-regressions/stage4/failure | `0ceb90c0f9834f68a757868f9c13133f` | incomplete | 10 | 4 × 10; / | False: 4 × 10; //continuous | 10/10; None | host/True/1 |
| stage6-regressions/stage4/technical | `445a139fdb144ffa9fd0aceec6a9c441` | completed | 10 | 4 × 10; / | False: 4 × 10; //continuous | 10/10; None | host/True/2 |
| stage6-regressions/stage5/A | `43cae37a3e1948b6994cbbb714dfb42e` | completed | 30 | 4 × 10; / | False: 4 × 10; //continuous | 10/10; None | containers/True/1 |
| stage6-regressions/stage5/B | `108cbd3908cd4af0b43cdc2665cbd96f` | completed | 30 | 0 × 10; / | True: 4 × 10; //continuous | 10/10; None | containers/True/1 |
| stage6-regressions/stage5/C | `faf6112c94504b48b94e2503c6f67e8b` | completed | 30 | 4 × 10; / | True: 4 × 10; //continuous | 10/10; None | containers/True/1 |
| stage6-regressions/stage5/failure | `ef75bc3dd603488e84c02cee8ebac67c` | incomplete | 10 | 4 × 10; / | True: 4 × 10; //continuous | 1/8; None | containers/True/1 |
| stage6-validation/expensive | `d3129e92bc46443ea94df3a043c6795b` | completed | 8 | 4 × 2; /expensive | True: 4 × 2; /expensive/continuous | 2/4; None | containers/True/1 |
| stage6-validation/light | `47bd101c9f8f4226b6e6eb9594899190` | completed | 8 | 4 × 2; /light | True: 4 × 2; /light/continuous | 2/4; None | containers/True/1 |
| stage6-validation/medium | `c74997f045dc4798925b3dd956788e44` | completed | 8 | 4 × 2; /medium | True: 4 × 2; /medium/continuous | 2/4; None | containers/True/1 |

## Nulls por run — grade principal de 1 s

| Run | Janelas | Null network (por feature) | Null request_starts | Null mean_duration_ms | Null mean_cpu_percent |
|---|---:|---:|---:|---:|
| stage7-regressions/stage3/A | 31 | 31 | 0 | 1 | 4 |
| stage7-regressions/stage3/B | 30 | 30 | 0 | 20 | 3 |
| stage7-regressions/stage3/C | 31 | 31 | 0 | 1 | 4 |
| stage7-regressions/stage4/A | 31 | 31 | 0 | 0 | 3 |
| stage7-regressions/stage4/B | 30 | 30 | 0 | 19 | 2 |
| stage7-regressions/stage4/C | 31 | 31 | 0 | 0 | 3 |
| stage7-regressions/stage4/technical | 11 | 11 | 0 | 0 | 3 |
| stage7-regressions/stage5/A | 31 | 0 | 0 | 0 | 3 |
| stage7-regressions/stage5/B | 30 | 0 | 0 | 19 | 2 |
| stage7-regressions/stage5/C | 31 | 0 | 0 | 1 | 3 |
| stage7-regressions/stage6/expensive | 9 | 0 | 0 | 0 | 3 |
| stage7-regressions/stage6/light | 9 | 0 | 0 | 0 | 3 |
| stage7-regressions/stage6/medium | 9 | 0 | 0 | 1 | 3 |
| stage7-validation/capacity | 16 | 0 | 0 | 1 | 3 |
| stage7-validation/continuous | 16 | 0 | 0 | 1 | 3 |
| stage7-validation/multiple | 16 | 0 | 0 | 1 | 3 |
| stage7-validation/periodic | 16 | 0 | 0 | 1 | 3 |
| stage8-validation/fresh-periodic-dataset | 16 | 0 | 0 | 1 | 3 |

## Limite do inventário legado

Diretórios legados sem run_status/ID contêm CSVs por nome de cenário: normal_baseline=666; wedos_grid=1480; atacantes_intensidade_grid=2160; clients_rps_grid=644; desempate_combinado_isolado=408; wedos_failure=140; combined_sweep=96; wu_calibration=75; ataque_isolado=36. Estes números contam arquivos CSV diretos, não runs. Não há inferência de analysis_eligible, seed, ground truth compatível ou independência a partir dos nomes. results/ e analysis/ também são produtos legados, fora da cadeia aprovada. Reuso exigiria auditoria própria; não foram exportados, revalidados ou convertidos neste diagnóstico.

## Estatística descritiva

feature_statistics.csv/json contém todas as 14 features, por run e Δ, nulls, mínimo/máximo, média/desvio amostral e contagens. normal_full_inside_plan usa apenas overlap=0 e fim da janela ≤ duração planejada; attack_full usa overlap=1. É um recorte descritivo explícito, não política de label ou seleção de feature. Pós-ataque pode conter recuperação; não é baseline certificado. Os cálculos auxiliares usam float, não substituem os CSVs Decimal da Etapa 10.

394 janelas na grade principal: 195 nulls em cada feature network (sete runs), zero em request_starts, 67 em mean_duration_ms e 54 em CPU/memória. A extração CLI de 0,5 s é outra representação do MESMO periodic, nunca amostra independente. development/validation/determinism são cópias/extrações de validação; IDs e hashes devem prevalecer sobre diretórios.
