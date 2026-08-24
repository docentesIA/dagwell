# DAGWELL

DAGWELL is a public, provider-agnostic orchestration engine that executes agent
work as a governed graph over an **event-sourced, append-only ledger**. State is
never stored — it is a deterministic fold of events. Verification and human
gates are first-class: successful transport alone never completes anything
(`executed != completed`); completion is
`successful transport + required output evidence + required approvals`.

**Status: foundation bootstrap — no runtime yet.** The normative behavior is
fully specified before implementation; the code grows in gated, incremental
phases.

## Where things are

| What | Where |
|---|---|
| Agent instructions (canonical, tool-agnostic) | [AGENTS.md](AGENTS.md) |
| Normative contract (supreme) | [docs/contracts/DAGWELL-EXECUTION-CONTRACT-v1.0.md](docs/contracts/DAGWELL-EXECUTION-CONTRACT-v1.0.md) |
| Promoted-document manifest | [docs/contracts/MANIFEST.sha256](docs/contracts/MANIFEST.sha256) |
| Architecture & Migration Plan | [docs/architecture/](docs/architecture/) |
| Decision records (ADRs) | [docs/decisions/](docs/decisions/) |
| Contract integrity check | `python3 tools/check_contracts.py` |
| Smoke test | `PYTHONPATH=src python3 tests/test_smoke.py` |

Note: the Execution Contract's prose is Portuguese by design; all canonical
protocol identifiers — event types, fields, enums, states — are English
(contract amendment H1). Localized documentation is informational only; the
English/canonical originals govern.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
