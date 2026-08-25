# ADR-0001 — Repository Structure Adoption

- **Status:** Accepted (human-gated)
- **Date:** 2026-08-23
- **Workstream:** `dagwell-foundation`

## Decision

This repository adopts the structure defined by **DAGWELL Repository Structure
Proposal v1** (SHA-256
`d0979ccdc4622af34305f223d4c168504f6d93d0e9eeb3dcd2fca7c95a87bafe`; approved at
its final human gate after patches P1–P4; kept in the private foundation data
area — not part of this repository). The repository was bootstrapped exactly per
that proposal's §13 minimal bootstrap, under explicit human authorization
(2026-08-23, Phase 1 of the Architecture & Migration Plan).

ADRs in this directory record human-approved decisions and are **subordinate to
the promoted documents in `docs/contracts/`**. An ADR never silently rewrites
protocol semantics: where a decision changes semantics governed by a
contract/specification, the corresponding normative document is updated through
its explicit versioned human-gated process.

## Recorded foundation identities (SHA-256)

| Document | Role | SHA-256 |
|---|---|---|
| `docs/contracts/DAGWELL-EXECUTION-CONTRACT-v1.0.md` | promoted, normative (supreme) | `bd1552a9f7f6aa9f03b78c6fbd46f8526f642ebced7aacec654066bcd29e623a` |
| `AGENTS.md` | ratified canonical agent instructions — **hash as ratified, 2026-08-23** | `54c4ab7c1483038149afe07fc636c539dcf73fc59651c1f7a5e2019eacc55feb` |
| `CLAUDE.md` | thin Claude Code bridge | `b1e599e43a3182f5cd22845d1b2251c558b7e9ae3ac31e0cd4d1347380a3b1d6` |
| `docs/architecture/DAGWELL-ARCHITECTURE-MIGRATION-PLAN-v1.md` | approved plan (explanation/planning, non-normative) | `11af09daa4b19e90e07d3782877f6bb8545808d14b3cd5cde481665896d94784` |

The contract's hash is **fixed**: a promoted document is immutable and any copy in
the repository must match it (`tools/check_contracts.py` enforces this). `AGENTS.md`
is different — it is amendable by human gate, so the value above is its identity **at
ratification**, not a claim about the working tree. Amendments are recorded as ADRs
(§11 by ADR-0006; the language rule by ADR-0007); the current identity is derivable
with `sha256sum AGENTS.md` and is deliberately not restated here, because a derived
value copied into a static document drifts and then lies.

## Also recorded

- **License:** Apache-2.0 (foundation decision, 2026-08-23); `LICENSE` carries
  the standard unmodified Apache License 2.0 text.
- **Architecture & Migration Plan v1: APPROVED by human gate (2026-08-23).**
  Its §6 / §15.1 order-vs-locus reconciliation was **CONFIRMED as a
  clarification of implementation locus, not a reinterpretation of the
  Execution Contract**.
- The per-operation Maxwell V1 → DAGWELL cutover remains **UNDECIDED and
  human-gated**.
- Transport choices remain **UNDECIDED** (Adapter Transport & Capability Model
  milestone, conditioned on Execution Contract §13.17).
- Bootstrap details delegated by the proposal (§12.5) and fixed at creation:
  `requires-python >= 3.11`, `setuptools` build backend. No console entry point
  (added only when `src/dagwell/cli/` is created, Phase 6).
- **This ADR resolves NO Execution Contract §13 Open Question.**
