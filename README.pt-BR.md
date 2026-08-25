# DAGWELL

> **Tradução informativa.** O original em inglês ([README.md](README.md))
> governa; em caso de divergência, prevalece o texto em inglês. Os
> identificadores canônicos do protocolo permanecem em inglês (contrato,
> emenda H1); a localização vive apenas na camada de exibição.

DAGWELL é um motor de orquestração público e agnóstico de provedor que executa
trabalho de agentes como um grafo governado sobre um **ledger append-only
orientado a eventos**. Estado nunca é armazenado — é um fold determinístico dos
eventos. Verificação e portões humanos são cidadãos de primeira classe:
transporte bem-sucedido sozinho nunca completa nada (`executed != completed`);
completude é
`successful transport + required output evidence + required approvals`.

**Status: o core governado (os seis passos incrementais do contrato) está
implementado; ainda sem adapters.** Nada aqui despacha trabalho real nem gasta
— transportes pertencem ao marco Adapter Transport & Capability Model, ainda
por vir. O comportamento normativo é totalmente especificado antes da
implementação, e o código cresce em fases incrementais com portões.

## Onde está o quê

| O quê | Onde |
|---|---|
| Instruções para agentes (canônica, agnóstica de ferramenta) | [AGENTS.md](AGENTS.md) |
| Contrato normativo (supremo) | [docs/contracts/DAGWELL-EXECUTION-CONTRACT-v1.0.md](docs/contracts/DAGWELL-EXECUTION-CONTRACT-v1.0.md) |
| Manifesto de documentos promovidos | [docs/contracts/MANIFEST.sha256](docs/contracts/MANIFEST.sha256) |
| Plano de Arquitetura & Migração | [docs/architecture/](docs/architecture/) |
| Registros de decisão (ADRs) | [docs/decisions/](docs/decisions/) |
| Definições de grafo de exemplo | [examples/](examples/) |
| Schemas embarcados (auxílio de forma — o validador é a autoridade) | [src/dagwell/schemas/](src/dagwell/schemas/) |
| Checagem de integridade dos contratos | `python3 tools/check_contracts.py` |
| Suíte de testes de custo zero | `python3 tools/run_tests.py` |

## Como isto foi feito, e como foi conferido

Este código foi escrito por agentes de IA sob gate humano, e os rodapés dos commits
dizem isso. Está declarado aqui em vez de ficar para ser descoberto: um projeto sobre
governar trabalho de agentes não tem por que ser vago sobre a própria produção.

O que o torna conferível não é quem digitou:

- O **contrato normativo veio antes**. `docs/contracts/` guarda um documento promovido,
  travado por SHA-256 e verificado a cada push; a implementação segue a ordem
  incremental dele e nunca o edita no lugar.
- **Duas auditorias independentes**, por modelos de famílias diferentes da que escreveu
  o core — a regra do próprio projeto de que o verificador não pode ser da mesma família
  do produtor. As duas devolveram REWORK REQUIRED.
- **Cada achado foi reproduzido** no interpretador antes de virar correção. Duas
  afirmações não sobreviveram à reprodução e foram descartadas — uma de cada auditor.
- **A suíte reporta 142 casos em 12 arquivos, 47 deles adversariais** (a matriz
  T1–T22 mais a cobertura de hardening), cada um escrito para falhar se um buraco
  específico reabrir. Só biblioteca padrão, sem rede, sem cota:
  `python3 tools/run_tests.py` imprime as mesmas contagens para quem rodar.
- **Os achados que NÃO foram corrigidos estão escritos nas mensagens de commit**, não
  omitidos. Dois seguem abertos e são acompanhados como issues.

Nada disso torna o código correto. Torna as afirmações sobre ele conferíveis, que é o
máximo que um repositório pode honestamente oferecer.

## Licença

Copyright 2026 Reinaldo Elias.

Licenciado sob a Apache License, Versão 2.0 — ver [LICENSE](LICENSE) e
[NOTICE](NOTICE).
