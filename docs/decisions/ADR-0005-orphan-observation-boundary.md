# ADR-0005 — Orphan Observation Boundary (Phase 7)

- **Status: ACCEPTED — human gate, 2026-08-23** (ratified by the consolidated
  core hardening authorization)
- **Relates to:** Execution Contract §10, §13.4

## Decision

The Phase-7 core observes orphans exclusively through an **injected
liveness/constatation provider** (`still_in_progress` callback):

- with **no provider**, the core never invents orphanhood — in-flight work
  stays in flight;
- **no universal timeout** is authorized (the contract forbids it);
- orphan evidence is produced only **at observation** (resume or explicit
  human command), for the specific producer attempt or
  `verification_attempt` whose non-continuity the provider constates;
- human verifications are never orphaned (silence stays `waiting_human`, I9).

**Concrete per-transport liveness semantics remain OPEN** for Phase 8 /
adapters (§13.4 stays open beyond this boundary; §13.16 and every other §13
question are untouched).
