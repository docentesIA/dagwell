# ADR-0004 — Event Schema v1 Initial Ordinals

- **Status: ACCEPTED — human gate, 2026-08-23** (ratified by the consolidated
  core hardening authorization)
- **Relates to:** Execution Contract §2, §9, §13.2 (first seq note), §13.18

## Decision

For event **schema v1** (`schema_version: "1"`):

- `FIRST_SEQ = 1` — the first valid `seq` of a run is 1, incrementing by 1.
- `FIRST_VERIFICATION_ATTEMPT = 1` — the first `verification_attempt` of an
  identity `(run_id, node_id, attempt, verification_id)` is 1, incrementing
  by 1.

Both match the Execution Contract's own illustrative values (§2, §6).
**§13.18 is explicitly closed for schema v1** by this ADR. A future schema
version may choose different encodings through its own gated process;
historical events are never reinterpreted.

## Consequences

Events with `schema_version` other than `"1"` are never silently interpreted
as v1: the fold treats them as inert and signals an anomaly (read-side
integrity normalization).
