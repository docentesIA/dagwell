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

## How this was built, and how it was checked

This code was written by AI agents under a human gate, and the commit trailers say
so. That is stated here rather than left to be discovered, because a project about
governing agent work has no business being vague about how it was produced.

What makes it checkable is not who typed it:

- The **normative contract came first**. `docs/contracts/` holds a promoted document
  pinned by SHA-256 and verified on every push; the implementation follows its
  incremental order and never edits it in place.
- **Two independent audits**, by models from different families than the one that
  wrote the core — the project's own rule that a verifier must not share the
  producer's family. Both returned REWORK REQUIRED.
- **Every finding was reproduced** in the interpreter before being acted on. Two
  claims did not survive reproduction and were discarded — one from each auditor.
- **The suite reports 142 cases across 12 files, 47 of them adversarial** (the
  T1-T22 matrix plus the hardening coverage), each written to fail if a specific
  hole reopens. Stdlib only, no network, no quota: `python3 tools/run_tests.py`
  prints the same counts for anyone who runs it.
- **The findings that were NOT fixed are written into the commit messages**, not
  omitted. Two remain open and are tracked as issues.

None of that makes the code correct. It makes the claims about it checkable, which
is the most any repository can honestly offer.

## License

Copyright 2026 Reinaldo Elias.

Licensed under the Apache License, Version 2.0 — see [LICENSE](LICENSE) and
[NOTICE](NOTICE).
