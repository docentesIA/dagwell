# ADR-0011 — Selection Observability Metadata

- **Status: ACCEPTED — human gate, 2026-09-13 (America/Belem), approved by Reinaldo**
- **Relates to:** Adapter/Output Evidence Specification v1.1, Execution Contract
  I3 (state is a deterministic fold — these fields are not read by it), I28
  (`executed != completed`), `docs/architecture/DAGWELL-ADAPTIVE-ROUTING-DESIGN-NOTES.md`
  §17 step 2.
- **Origin:** step 2 of the adaptive-routing design notes' incremental migration
  sequence. Drafted 2026-09-13, revised through independent cross-review between
  Claude and Codex (technical counsel) before this human gate. The initial draft
  named the fields `estimated_cost`/`reason_for_selection`; the cross-review
  rejected that vocabulary as monetarily misleading and produced the names below.

## Context

`select()` (`src/dagwell/adapters/selection.py`) deterministically picks the
lowest-`relative_cost` candidate that serves the requested tier (restricted to
`available` when given), tie-breaking by `(binding_id, model_id)`. The winning
model's `relative_cost` and the reason it won are computed internally and then
discarded — the returned dict carries only `binding_id`, `model_id`, `family`,
`transport`, `registry_digest`.

These values are **not available directly from the ledger today**. With the
historical registry version that matches a past selection's `registry_digest`,
part of that information can be recovered after the fact — but reproducing the
*complete* selection also requires knowing which bindings were `available`
(passed their zero-cost probe) at that moment, which the ledger does not record
either. This ADR does not close that gap; it only stops discarding the two
values `select()` already computes.

`node_dispatched.transport` (`src/dagwell/operations.py`, `dispatch()`) already
carries `binding_id`/`model_id`/`family`/`registry_digest` as facts opaque to
the fold — "facts, never decisions: nothing in the fold reads them". It is the
right place for the new fields: they describe the same selection, not a new
event structure.

## Decision

1. `select()` also returns:
   - **`selected_relative_cost`** — an exact copy of the winning model's
     `relative_cost` from the registry. No conversion, rounding, or
     normalization. Not a price, not a monetary estimate, not a budget.
   - **`selection_reason`** — a stable code, not a variable human sentence.
     Today exactly one constant is emitted: `"lowest_relative_cost_serving_tier"`,
     naming the complete policy already implemented: filter candidates by tier
     and `available`, minimize `relative_cost`, tie-break by
     `(binding_id, model_id)`. Restricting `available` is not a new selection
     criterion — it only narrows the eligible set under the same policy.
2. Both fields are **optional**: historical `node_dispatched` events and any
   external/manual dispatch that bypasses `select()` remain valid without them.
   Nothing in the fold requires their presence.
3. No mandatory enum or selection-strategy framework is introduced now. A
   single documented constant is enough while `select()` has exactly one
   criterion. If a second criterion is ever added, the code set becomes closed
   and documented (same pattern as `CAPABILITY_TIERS`).
4. Out of scope for this ADR, by deliberate naming choice: `estimated_cost`,
   `actual_cost`, `price`, `budget`. No monetary semantics are introduced by
   this decision.
5. These fields raise observability; they do not by themselves prove a
   selection was reproducible or correct — see Context above on what recovering
   a past selection still requires.
6. `select()` remains pure and deterministic; `fold.py` does not interpret the
   new fields; no automatic fallback, adaptation, or budget is introduced.
7. The product consumer checked for this change is
   `src/dagwell/adapters/worker.py`, which accesses selected fields and
   forwards the selection dictionary as transport metadata. The strict
   dispatch-transport assertion in
   `test_go_executes_with_derived_evidence_and_transport_facts`
   (`tests/test_worker.py`) was updated to include the new fields. This is a
   test expectation change, not evidence of a production consumer failure.
   *(Rectified 2026-09-13, after implementation: the original wording claimed
   no strict whole-dict comparison existed in the suite; that claim was wrong.
   Decision unchanged.)*

## Required tests before implementation

- Exact `selected_relative_cost` value and `selection_reason` code for the
  winning model.
- Correct selection and metadata under an availability filter, a tie, and a
  reversed registry entry order.
- Refusal with no candidate produces no metadata (no dispatch, no spend).
- A fake executor confirms the new fields reach the ledger event but are never
  forwarded as subprocess arguments — only `model_id` is.
- Historical `node_dispatched` events without the new fields remain valid, and
  adding the fields does not change the fold's projection.
- Full existing suite + contract checks pass after implementation.

## Consequences

- Enables querying the relative cost declared by a given selection/dispatch,
  taken from the ledger event that recorded it. This ADR does not establish
  that these values are summable across a run — that is a separate,
  unaddressed question.
- Resolves no Open Question from §13 or from the design notes' §19.
- Does not unblock `capability_tags` or `agent_ref` — each still needs its own
  ADR.
