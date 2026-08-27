# ADR-0010 — `land_run` Motive Asymmetry: Ratifying the Principle

- **Status: ACCEPTED — human gate, 2026-08-26**
- **Relates to:** Execution Contract I13, I17, I28, §13.12 (OPEN — Runtime
  Policy Specification)
- **Origin:** independent audit of 2026-08-25 (finding A3, xai auditor;
  finding A6-contradiction, openai auditor; reproduced before drafting).
  Implementation already closed in commit `06b3ca8` ("fifth audit finding");
  this ADR ratifies the principle behind that fix as governance.

## Context

I17 closes `run_landed` to exactly three motives:
`{budget_exhausted, retries_exhausted, human_rejection}`. The three are not
equally verifiable by the core, and `land_run` (`operations.py`) treats them
asymmetrically on purpose:

- `human_rejection` is a fact the fold can see: it requires a `rejected` node
  in the projection.
- `retries_exhausted` is checked against a `failed` node in the projection.
- `budget_exhausted` is accepted as **caller-asserted**, with no fold check,
  because the core owns no budget model — inventing one here would resolve
  §13.12 (the future Runtime Policy Specification) by fiat, which this
  project's own decision drivers forbid (ADR-0003, driver 5: do not invent
  mechanisms to make an open question more interesting).

The 2026-08-25 audit surfaced two problems with this asymmetry as it stood:

1. **`retries_exhausted`'s check is a weak proxy.** A single failed transport
   already produces a `failed` node (I13 makes no claim about *how many*
   retries occurred before failure). `failed in states` proves *a* failure
   happened, not that the retry policy — whose formula §13.12 explicitly
   defers — was actually exhausted. The check is honest about what it can
   verify and no more.
2. **`budget_exhausted`, being unattestable, was usable as an escape hatch.**
   Before commit `06b3ca8`, `land_run(reason="budget_exhausted")` could land a
   run with a node still in `executed` — successfully returned, verification
   still owed (I28: `executed != completed`). Because the core cannot
   contradict a caller-asserted motive, this froze a required verification
   behind a reason nothing could check. `06b3ca8` closed this: landing is now
   refused for **any** motive while a node is `executed`, not only for the
   two fold-verifiable reasons.

## Decision

**Ratify the asymmetry as the intended, permanent shape of `land_run` — not a
gap awaiting a future formula:**

1. `human_rejection` and `retries_exhausted` are grounded in what the fold's
   projection can actually show (`rejected` / `failed` nodes respectively).
   `retries_exhausted`'s grounding is acknowledged as a **necessary, not
   sufficient**, proxy — the core proves *a* failure occurred, not that a
   retry policy's exhaustion condition was met, because that condition
   belongs to §13.12 and is not decided. This is not a defect to fix: closing
   it properly requires the Runtime Policy Specification, not a `land_run`
   patch.
2. `budget_exhausted` remains **caller-asserted, permanently**, until §13.12
   supplies a fold-verifiable budget model. No formula is invented by this
   ADR or by any future patch that stops short of a ratified Runtime Policy
   Specification.
3. **Independently of which motive is asserted, `land_run` refuses to land
   while any node is `executed`** (already implemented, `06b3ca8`). This is
   the actual safeguard against motive (2)'s unattestability: an unverifiable
   *reason* can no longer excuse landing over unverified *work*. The
   asymmetry in motive-checking is safe to keep exactly because this
   orthogonal, fully fold-verifiable check does not depend on which reason
   was given.

## Consequences

- No code change beyond what `06b3ca8` already shipped. This ADR is the
  governance record for that fix's underlying principle, closing eixo 4(b)
  of the 2026-08-25 audit synthesis.
- §13.12 (Runtime Policy Specification) remains explicitly open. This ADR
  does not narrow it, and no future work should treat `land_run`'s current
  checks as a substitute for that specification.
- Documents the residual honesty of `retries_exhausted`: it is grounded in
  fact (`failed` occurred), not in the policy that decides exhaustion — a
  distinction future readers of `operations.py` should not mistake for a bug.
