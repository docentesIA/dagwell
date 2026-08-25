# DAGWELL

DAGWELL is a public, provider-agnostic orchestration engine that executes agent
work as a governed graph over an **event-sourced, append-only ledger**. State is
never stored — it is a deterministic fold of events. Verification and human
gates are first-class: successful transport alone never completes anything
(`executed != completed`); completion is
`successful transport + required output evidence + required approvals`.

**Status: the governed core (the contract's six incremental steps) is
implemented; no adapters yet.** Nothing here dispatches real work or spends —
transports belong to the Adapter Transport & Capability Model milestone, still
ahead. The normative behavior is fully specified before implementation, and the
code grows in gated, incremental phases.

## Where things are

| What | Where |
|---|---|
| Agent instructions (canonical, tool-agnostic) | [AGENTS.md](AGENTS.md) |
| Normative contract (supreme) | [docs/contracts/DAGWELL-EXECUTION-CONTRACT-v1.0.md](docs/contracts/DAGWELL-EXECUTION-CONTRACT-v1.0.md) |
| Promoted-document manifest | [docs/contracts/MANIFEST.sha256](docs/contracts/MANIFEST.sha256) |
| Architecture & Migration Plan | [docs/architecture/](docs/architecture/) |
| Decision records (ADRs) | [docs/decisions/](docs/decisions/) |
| Example graph definitions | [examples/](examples/) |
| Shipped schemas (shape aid — the validator is authoritative) | [src/dagwell/schemas/](src/dagwell/schemas/) |
| Contract integrity check | `python3 tools/check_contracts.py` |
| Zero-cost test suite | `python3 tools/run_tests.py` |

Note: the Execution Contract's prose is Portuguese by design; all canonical
protocol identifiers — event types, fields, enums, states — are English
(contract amendment H1). Localized documentation is informational only; the
English/canonical originals govern.

## License

Copyright 2026 Reinaldo Elias.

Licensed under the Apache License, Version 2.0 — see [LICENSE](LICENSE) and
[NOTICE](NOTICE).
