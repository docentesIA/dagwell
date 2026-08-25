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

## Licença

Copyright 2026 Reinaldo Elias.

Licenciado sob a Apache License, Versão 2.0 — ver [LICENSE](LICENSE) e
[NOTICE](NOTICE).
