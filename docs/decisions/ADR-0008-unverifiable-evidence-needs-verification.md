# ADR-0008 — An Evidence Type §13.17 Has Not Specified Cannot Waive Verification

- **Status: ACCEPTED — human gate, 2026-08-25**
- **Relates to:** Execution Contract §4, §7, I5, I28, §13.17 (OPEN)
- **Origin:** independent audit of 2026-08-25 (finding A5, openai auditor;
  reproduced before acting)

## Context

A node could declare `output_evidence: side_effect_receipt` together with
`no_verification: <reason>` and reach `completed` by returning
`{"type": "side_effect_receipt", "evidence_id": "we-did-it"}`. An external side
effect completed on a sentence.

The code was not wrong about the contract. The contract fixes what makes evidence
INVALID only for `artifact` (manifest absent, empty or malformed); for the other
types the concrete format belongs to the future Adapter/Output Evidence
Specification, and the contract says plainly that `evidence_id` **need not be a
hash** — it requires a **stable/verifiable** identity and leaves the encoding to
§13.17. Imposing a format here would resolve an open question by invention, which
this project forbids.

But the same passage says the contract fixes "o conceito, a identidade canônica e
o **fail-closed**". The hole was not a missing format — it was fail-OPEN behaviour
in its absence.

## Decision

`no_verification` is available **only** for evidence types the core can validate
on its own. Today that is `artifact`, and only because the contract defines its
invalidity. For `structured_value`, `remote_receipt` and `side_effect_receipt`,
a node must declare a verification; refused at graph load, before any spend.

Nothing is invented: no encoding, no format, no `evidence_id` shape. The node may
still return whatever payload it wants for those types — but something other than
the claim itself has to check it, and the contract already supplies that
mechanism.

## Consequences

- An unverified node can no longer complete on an unchecked claim. `executed !=
  completed` holds for every evidence type, not just for `artifact`.
- `examples/graph-canonical.json` changes: `summary` (a `structured_value` node)
  now declares a human verification instead of waiving it. It was the example
  demonstrating the hole.
- **This restriction is temporary by construction.** When §13.17 fixes the
  formats and the core can validate those types, the vacuum becomes signable for
  them and this ADR is superseded. Until then the restriction is the honest
  reading of a fail-closed contract with an open specification.
- The shipped JSON Schema (`schemas/graph.schema.json`) remains a shape aid and is
  not the authority. It is now more permissive than the validator on this point —
  the same parity gap the audit records separately as an open finding.
