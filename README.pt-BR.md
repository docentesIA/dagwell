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

**Status: bootstrap da fundação — ainda sem runtime.** O comportamento
normativo é totalmente especificado antes da implementação; o código cresce em
fases incrementais com portões.

## Onde está o quê

| O quê | Onde |
|---|---|
| Instruções para agentes (canônica, agnóstica de ferramenta) | [AGENTS.md](AGENTS.md) |
| Contrato normativo (supremo) | [docs/contracts/DAGWELL-EXECUTION-CONTRACT-v1.0.md](docs/contracts/DAGWELL-EXECUTION-CONTRACT-v1.0.md) |
| Manifesto de documentos promovidos | [docs/contracts/MANIFEST.sha256](docs/contracts/MANIFEST.sha256) |
| Plano de Arquitetura & Migração | [docs/architecture/](docs/architecture/) |
| Registros de decisão (ADRs) | [docs/decisions/](docs/decisions/) |
| Checagem de integridade dos contratos | `python3 tools/check_contracts.py` |
| Teste de fumaça | `PYTHONPATH=src python3 tests/test_smoke.py` |

## Licença

Apache License 2.0 — ver [LICENSE](LICENSE).
