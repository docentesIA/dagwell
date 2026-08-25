# DAGWELL Architecture & Migration Plan — v1

> **Status: APPROVED — human gate, 2026-08-23 (`dagwell-foundation` workstream).**
> Gate record: the §6 / §15.1 order-vs-locus reconciliation ("order from the
> Execution Contract; locus from the approved Repository Structure Proposal") was
> explicitly **CONFIRMED as a clarification of implementation locus, NOT a
> reinterpretation of the Execution Contract**. The per-operation Maxwell V1 →
> DAGWELL cutover remains UNDECIDED and human-gated. Transport choices remain
> UNDECIDED. No Execution Contract §13 Open Question was resolved by this approval.
> Nothing in this Plan creates repositories, writes runtime code, modifies Maxwell V1,
> executes anything, or resolves an Execution Contract §13 Open Question.

## 1. Purpose and Scope

This Plan defines how the frozen Maxwell V1 baseline evolves into DAGWELL: the target
architecture, the migration strategy, a phased roadmap with activation gates, and the
dependency map of the contract's Open Questions. It is an explanation-and-planning
document (`docs/architecture/` class) — **not** a normative protocol document. It
designs no classes, no APIs, no adapters, and no transports.

## 2. Governing Documents

Precedence (higher prevails; this Plan reinterprets none of them):

1. **DAGWELL Execution Contract v1.0 (Stable)** — SHA-256
   `bd1552a9f7f6aa9f03b78c6fbd46f8526f642ebced7aacec654066bcd29e623a`
2. **AGENTS.md (ratified)** — SHA-256 at ratification (2026-08-23)
   `54c4ab7c1483038149afe07fc636c539dcf73fc59651c1f7a5e2019eacc55feb`.
   Amendable by human gate; amendments are recorded as ADRs and the current
   identity is derivable (`sha256sum AGENTS.md`), never restated here.
3. **Repository Structure Proposal v1 — APPROVED** (final human gate passed after
   patches P1–P4). Structure decisions are settled and are not reopened here.
4. This Plan.

## 3. Architectural Principles

1. **The ledger is the system.** Event-sourced, append-only, single source of truth;
   state is a deterministic fold ordered by `seq`. Every phase below either extends
   the ledger's vocabulary or derives from it — nothing else is authoritative.
2. **Fail-closed before spend.** Validation errors refuse at `--go`; missing
   specifications mean the governed capability stays off, never improvised.
3. **The contract's implementation order is the roadmap's spine.** The Execution
   Contract's "Incremental implementation order" (6 steps) is preserved verbatim as
   the capability sequence; this Plan adds gates around it, never a competing order.
4. **Platform ≠ Transport ≠ Capabilities.** The core architecture distinguishes:

   ```
   Platform / Agent            (who does the work: e.g. Hermes, OpenClaw, Buzz,
         ↓                      Claude Code, Codex, local agents/models, remote agents)
   Capability description      (what it can do, declared/discovered)
         ↓
   Transport binding           (how DAGWELL talks to it: candidate mechanisms only —
         ↓                      CLI/subprocess, HTTP/API, SDK, OpenAI-compatible,
         ↓                      A2A, ACP, MCP, another protocol, or hybrid)
   DAGWELL governed execution  (dispatch, verification, gates, budget)
         ↓
   ledger events + output_evidence + evidence_id
   ```

   Hermes, OpenClaw and Buzz are **platforms/agents, not transport types**. No
   one-platform = one-transport assumption is encoded anywhere. **DAGWELL has NOT
   decided** which transport/protocol any platform will use — that decision space
   belongs to the Adapter Transport & Capability Model milestone (§10).
5. **Provider-agnostic core.** Core packages do not import, depend on, or encode
   provider/platform-specific behavior; provider-specific content lives at the edge
   (adapter implementations, adapter tests, adapter docs/examples, compatibility
   documentation, thin tool bridges). Adapter transport success never equals
   semantic approval; adapters emit transport facts and output evidence, never
   verdicts; remote execution counts as work only with adequate evidence/receipt.
   Consequence: moving any platform from CLI to API/A2A/MCP/etc. in the future must
   not require changing the Execution Contract — only the adapter layer.
6. **Working system at every step.** Maxwell V1 stays frozen and operational; each
   DAGWELL phase leaves the new codebase coherent, its zero-cost suite green, and
   nothing half-wired into production paths.

## 4. Maxwell V1 Baseline

```
baseline commit: 58a0aed   tag: maxwell-v1-baseline
known later product commit: 89efb6b — fix: track token measurement source explicitly
```

The baseline is **frozen and never mutated**. It serves as: (a) the operational
system until DAGWELL reaches gated parity; (b) the behavioral reference for porting;
(c) the source of legacy data for the eventual data migration (§11).

**Behavior to preserve (contract-blessed V1 essence):**
- `--go` as the only act that creates a run and spends; everything else is dry-run.
- Output born under `runs/` in the data area, never in the product root.
- Ledger append-only as memory — including errors.
- Preference for deterministic gates over model verifiers; R1 discipline with
  written `r1_exception`.
- Zero-cost test suite run before any change.
- Product/data separation.

**Behavior to replace (contract-mandated corrections):**
- `(operation, node)` identity → `run_id` + `run_created` anchor.
- Checkpoint file as source of truth → checkpoint as fold-derived cache.
- Shared per-operation run directories → `runs/<operation>/<run_id>/<node_id>/t<k>/`
  (V1 layout read as legacy, history never moved).
- Portuguese/ad-hoc ledger vocabulary → canonical English identifiers, two axes
  (`verification_status` × `verdict`), `verification_attempt`, `evidence_id`.
- "Handoff exists" presence predicate → required output evidence, validated.

## 5. Target DAGWELL Architecture

Per the approved Repository Structure Proposal: a public, provider-agnostic Python
package (`src/dagwell/`) whose boundaries name contract concepts — `ledger/`,
`verification/`, `graph/`, `schemas/`, `evidence/`, `fold/`, `cli/`, `runtime/`,
`adapters/`, `migration/` — each created when its phase starts. Presentation
surfaces (CLI today) sit above a governed authority layer that enforces the
human-only decision privilege and all write preconditions below presentation
(contract I8, §5–§6), keeping future CLI/UI/API surfaces possible without
duplicating authority rules (actor authentication remains open, §13.8).

## 6. Migration Strategy

**Order from the contract; locus from the approved structure.** The contract fixes
the capability sequence (its 6 steps). The approved repository structure fixes where
that sequence is implemented: the new DAGWELL package. Maxwell V1 is never rewritten
in place and never mutated — it keeps working, untouched, while DAGWELL is built
alongside it against synthetic fixtures and V1-derived reference behavior. This
satisfies the contract's own guarantee ("no step requires rewriting the runtime that
already works") — the working runtime is preserved by freezing, and each DAGWELL
phase is independently useful and testable.

Two migrations, strictly distinguished:

- **Product migration** (code): phased implementation of the contract in the DAGWELL
  package (Phases 2–7), then adapters (Phases 8–9). Cutover from V1 to DAGWELL is
  **per-operation and human-gated**; after cutover V1 remains read-only legacy.
- **Data migration** (ledger): a separate, later phase (Phase 10) that converts the
  legacy V1 ledger into canonical events — gated on the §13.1 audit and the §13.6
  migration specification, preserving `legacy_raw`/`legacy_origin`, labeling
  synthetic runs `legacy-<operation>` with `legacy_ambiguous: true`, and **never**
  fabricating verdicts (`unmapped` stays outside canonical fields). Originals are
  preserved; migration writes forward, it never rewrites history.

**Compatibility rules:** legacy V1 layout and ledger are read as legacy without
moving history; legacy-ambiguous runs never join modern checkpoints; real migration
runs execute only in the private data area.

## 7. Phased Implementation Roadmap

Progression (labels are phases, **not** package names):

```
Phase 0   Foundation (documents)                       ← current workstream
Phase 1   Repository bootstrap
Phase 2   Event envelope + run_created + run_id        (contract step 1)
Phase 3   Canonical verification vocabulary
          + verification_attempt                       (contract step 2)
Phase 4   Graph declarations + validation
          + output_evidence declaration                (contract step 3)
Phase 5   Deterministic fold + checkpoint              (contract step 4)
Phase 6   Human decision operation + human_retry       (contract step 5)
Phase 7   Resume + interruption + orphan semantics     (contract step 6)
Phase 8   MILESTONE: Adapter Transport & Capability Model   (→ §10)
Phase 9   Adapter implementations (incremental, per promoted spec)
Phase 10  Migration from Maxwell V1 (data)             (gated: §13.1 + §13.6)
Phase 11  Deferred: parallelism / learning / routing   (explicit activation criteria)
```

Phases 2–7 track the contract's incremental order one-to-one. Phase 10 may begin
earlier than Phase 9 if its gates open first — data migration depends on Phases 2–5
plus §13.1/§13.6, not on adapters.

## 8. Phase Entry / Exit Gates

Common to every phase: zero-cost suite green before and after; no §13 question
resolved silently (blockage → ADR, §9); no user data; Maxwell V1 untouched.

**Phase 0 — Foundation** *(current)*
- Entry: Execution Contract v1.0 STABLE. — Allowed: foundation documents.
- Forbidden: code, repository creation, runtime, adapters.
- Exit: AGENTS.md ratified ✔; structure approved ✔; this Plan human-approved.
- Human gate: yes — approval of this Plan.

**Phase 1 — Repository bootstrap**
- Entry: Phase 0 exit; license RESOLVED (Apache-2.0) ✔; sanitization check defined.
- Allowed: exactly the approved minimal bootstrap (proposal §13): root files,
  `docs/contracts/` copy + `MANIFEST.sha256`, ADR-0001, `src/dagwell/__init__.py`,
  smoke test, `tools/check_contracts.py`. No console entry point.
- Forbidden: runtime code, additional packages, publication without its own gate.
- Exit: all three hash verifications pass; `check_contracts` passes; suite green;
  sanitization clean (no personal paths/secrets/user data).
- Human gate: yes — repository creation; publication is a separate later gate.

**Phase 2 — Event envelope + `run_created` + `run_id`**
- Entry: Phase 1 exit; ADRs approved for §13.2 (run_id encoding) and initial §13.5
  (canonicalization of `graph_version`/`input_hash`) — decisions required, made
  explicitly, never improvised.
- Allowed: `ledger` boundary — envelope (§9), canonical event types, append
  serialization contract, integrity detection (duplicate `event_id`, `seq`
  collision/regression hard-fail, gap signaling), `run_created` uniqueness
  precondition, `legacy-<operation>` labeling rules (`legacy_ambiguous`).
- Forbidden: fold beyond test needs; vocabulary migration; adapters; touching real
  V1 ledgers.
- Exit: envelope + integrity anomaly tests pass on synthetic fixtures;
  refusal-before-spend tests for write preconditions.
- Human gate: the two ADRs.

**Phase 3 — Canonical vocabulary + `verification_attempt`**
- Entry: Phase 2 exit; ADR for §13.18 (`verification_attempt` initial
  value/encoding).
- Allowed: `verification` boundary — closed sets, two axes (§6), verdict-write
  preconditions (duplicate no-op, conflict refusal, late-verdict refusal),
  `verification_attempt` identity; legacy mapping table encoded **as
  hypothesis-with-gate only** (§6 table) — never applied to legacy data.
- Forbidden: applying migration to any real ledger (waits §13.1); inventing the
  `model:<family>` namespace (§13.15).
- Exit: out-of-set refusal tests; precondition tests across families.
- Human gate: the §13.18 ADR.

**Phase 4 — Graph declarations + validation + output evidence declaration**
- Entry: Phase 3 exit.
- Allowed: `graph` + `schemas` (package data) + start of `evidence` boundary —
  fail-closed `--go` validation (declared verifications or `no_verification:
  <reason>`; declared output evidence type; `r1_exception`; refuse before spend);
  evidence types as contract-fixed concepts, `artifact` realization
  (`output_manifest`/`artifact_digest`).
- Forbidden: per-type `evidence_id` encodings beyond `artifact`'s specialized case
  (waits §13.17); adapters.
- Exit: fail-closed validation tests; first `examples/` graphs validating against
  the shipped schemas.
- Human gate: none beyond common rules.

**Phase 5 — Deterministic fold + checkpoint**
- Entry: Phases 2–4 exit.
- Allowed: `fold` boundary — pure projections (run §3 precedence order, node §4),
  checkpoint conjunction (§7) bound to attempt + `evidence_id`, cache with
  watermark (I19), anomaly signaling, `integrity: degraded` view, mutable-action
  blocking predicate (P3).
- Forbidden: retry policy (waits §13.12); any reconciliation mechanism (§13.16 —
  fail-closed blocking IS the complete specified behavior).
- Exit: golden fold tests over synthetic ledgers including anomalies (duplicates,
  gaps, late verdicts, historical violations); cache-divergence recompute test.
- Human gate: none beyond common rules.

**Phase 6 — Human decision operation + `human_retry`**
- Entry: Phase 5 exit.
- Allowed: governed decision operation below presentation (I8 preconditions:
  current attempt + current `evidence_id`, gap blocking, cancelled-run refusal,
  duplicate no-op, conflict refusal, `reason` required on rejection); `human_retry`
  with its single meaning; `cli` presentation surface; console entry point added to
  `pyproject.toml` now.
- Forbidden: remote surfaces / actor authentication (§13.8); UI/API design.
- Exit: full precondition test matrix for human writes and `human_retry` domains.
- Human gate: none beyond common rules (the operation itself IS the gate machinery).

**Phase 7 — Resume + interruption + orphan semantics**
- Entry: Phase 6 exit; decision recorded for the §13.4 "work no longer in progress"
  constatation mechanism (ADR).
- Allowed: `runtime` boundary — dispatch with triple-uniqueness precondition,
  `resume` validating frozen identity against `run_created`, graceful interruption
  (`run_interrupt_requested`, fold-inert) vs abrupt loss, orphan evidence produced
  at observation only, per-run/attempt artifact layout, `run_landed`/
  `budget_extended` handling. **Automatic retry remains disabled** — not as a
  policy choice but because no Runtime Policy Specification exists to authorize
  automated spending (fail-closed; only `human_retry` acts).
- Forbidden: retry formulas; universal orphan timeouts; concurrency (§13.7).
- Exit: resume idempotence; orphan inertness on non-running attempts; landed
  resumption via motive-removing events; interruption test matrix.
- Human gate: §13.4 ADR; and the **first real run** (`--go`) of DAGWELL on a real
  operation is its own explicit human spending gate, outside this Plan.

**Phase 8 — MILESTONE: Adapter Transport & Capability Model** — see §10.

**Phase 9 — Adapter implementations**
- Entry: Phase 8 spec promoted; §13.15 namespace decided (ADR or in-spec) before
  any `model:<family>` verdict is emitted.
- Allowed: one adapter at a time, per the promoted specification; adapter-specific
  tests/docs/examples at the edge.
- Forbidden: core importing adapters; verdict manufacture; big-bang adapter sets.
- Exit per adapter: evidence/receipt production proven by tests; transport facts
  isolated from verdicts.
- Human gate: each new spending surface.

**Phase 10 — Migration from Maxwell V1 (data)**
- Entry: §13.1 audit completed (semantics of `pass-ok`/`pass-falhou` established
  from the components that write them); §13.6 migration specification promoted;
  Phases 2–5 stable.
- Allowed: `migration` boundary — importer preserving `legacy_raw`/`legacy_origin`;
  `legacy-<operation>` synthetic runs with `legacy_ambiguous: true`; `unmapped`
  outside canonical fields; migration dry-run reports.
- Forbidden: fabricating verdicts; mutating V1 originals; running against real data
  without its own gate; legacy runs entering modern checkpoints.
- Exit: dry-run report approved; real migration executed in the private data area
  under human gate; originals verified intact.
- Human gate: yes — before touching real data.

**Phase 11 — Deferred layers** — see §14. No entry conditions defined yet: entry
requires written activation criteria approved as ADRs.

## 9. Open Questions Dependency Map

No question is resolved here. Classification: **P** = prerequisite for a phase,
**D** = decision required during a phase (via explicit human-approved ADR/spec),
**L** = later / non-blocking.

| §13 | Question | Class | Binding |
|---|---|---|---|
| 13.1 | legacy verdict audit (`pass-ok`/`pass-falhou`) | **P** | prerequisite of Phase 10; non-blocking for new runs (Phases 2–7) |
| 13.2 | `run_id` encoding | **D** | ADR at Phase 2 entry |
| 13.4 | orphan detection (constatation + alert calibration) | **D**/L | constatation ADR at Phase 7; alert calibration later, with measured latencies |
| 13.5 | `graph_version`/`input_hash` canonicalization | **D** | initial ADR at Phase 2 entry; refinable at Phase 4 via the same gated process |
| 13.6 | physical ledger migration (incl. synthetic `run_created`) | **P** | specification prerequisite of Phase 10 |
| 13.7 | real concurrency (claims/leases) | **L** | Phase 11 only; envelope already provides the substrate |
| 13.8 | human `actor` authentication | **L** | input to §10 milestone (Q8) and to any future remote surface; local-user model until then |
| 13.12 | Runtime Policy Specification (concrete retry) | **P** | prerequisite for enabling automatic retry (Phase 7+); until promoted, automatic retry stays off (fail-closed) |
| 13.15 | `model:<family>` namespace | **D** | decided within Phase 8 spec or by ADR before first model-family verdict |
| 13.16 | sequence-gap reconciliation mechanism | **L** | never blocks: fail-closed blocking is the complete behavior until the mechanism's future spec |
| 13.17 | Adapter/Output Evidence Specification | **P** | THE condition of the Phase 8 milestone; prerequisite of Phase 9 |
| 13.18 | `verification_attempt` initial value/encoding | **D** | ADR at Phase 3 entry |

Remaining §13 items (13.3 selective checkpoint inheritance, 13.9 `cancelled` in
denominators, 13.10 composite verifiers, 13.11 optional nodes, 13.13 duplicate/seq
mechanics, 13.14 grace period mechanics): **L** — later/non-blocking; 13.13 and
13.14 become **D** within Phases 2 and 7 respectively only to the extent the
implementation must pick a concrete runtime mechanism, recorded by ADR.

## 10. Adapter Transport & Capability Model Milestone

**MANDATORY milestone. It MUST happen before broad implementation of
platform/provider adapters, and it is conditioned on Execution Contract §13.17 —
the Adapter/Output Evidence Specification.** The milestone's deliverable is that
specification, produced through the governed process (RC in `docs/contracts/`,
explicitly non-normative until human promotion; promoted into `MANIFEST.sha256`).

The milestone institutionalizes the Platform / Transport / Capabilities separation
(§3.4). **Explicitly undecided today** — and to remain undecided until this
milestone: whether Hermes, OpenClaw, Buzz, Claude Code, Codex, local agents/models,
or remote agents connect through CLI/subprocess, HTTP/API, SDK, OpenAI-compatible
API, A2A, ACP, MCP, another protocol, or a hybrid. Every one of these is a
**candidate mechanism, not an architectural commitment**.

The specification must answer — and this Plan only **reserves** — at least:

1. transport type; 2. capability discovery; 3. synchronous vs asynchronous
execution; 4. session/conversation persistence; 5. streaming support;
6. cancellation semantics; 7. remote orphan detection; 8. authentication/credentials
boundary (with §13.8); 9. cost/quota reporting; 10. timeout semantics; 11. retry
interaction (with §13.12); 12. evidence/receipt production; 13. side-effect
evidence; 14. model/provider family identity (with §13.15); 15. health/readiness
checks; 16. version/capability negotiation; 17. local process lifecycle; 18. remote
job lifecycle; 19. fallback between transports; 20. whether adapters are organized
primarily by transport, by platform, or by a composition of both.

**Design-space preservation:** neither `adapters/hermes|openclaw|buzz/` (platform-
oriented) nor `adapters/subprocess|http|a2a|acp/` (transport-oriented) is frozen
now. The future specification may conclude transport-oriented, platform-oriented,
capability-oriented, layered/compositional, or hybrid — the approved repository
structure deliberately fixes only the `adapters/` boundary, not its interior.

## 11. Maxwell Compatibility and Legacy Boundary

- The baseline (`58a0aed`, tag `maxwell-v1-baseline`) is immutable history; the
  product tree is not modified by any phase of this Plan.
- V1 remains the operational system per operation until a human-gated cutover;
  after cutover, V1 is read-only legacy for that operation.
- Legacy ledger rows and the V1 `runs/<operacao>/<no>/` layout are read as legacy
  in place — history is never moved or rewritten.
- Legacy-ambiguous synthetic runs (`legacy-<operation>`, `legacy_ambiguous: true`)
  never participate in modern checkpoints and never enter future learning without
  explicit treatment (I23).
- The verdict-mapping table is a hypothesis with a gate (§13.1) — no migration of
  legacy verdicts before the audit.

## 12. Testing and Evidence Strategy

- **Zero-cost, always.** The entire suite runs without quota, paid inference, or
  external side effects — before and after every change, in every phase.
- **The fold is the crown jewel of testing**: golden tests of events-in/states-out,
  including every integrity anomaly the contract names (duplicate `event_id`, `seq`
  collision/regression/gap, second `run_created`, duplicate dispatch triple, late
  verdicts, conflicting verdicts, historical violations).
- **Refusal-before-spend tests** for every hard validation (closed sets, envelope,
  preconditions, `--go` declarations).
- **Synthetic fixtures only** (`tests/fixtures/`): synthetic ledgers, graphs, and
  V1-shaped samples; never real user data or personal paths.
- **Evidence discipline applies to the work itself** (AGENTS.md Definition of
  Done): a phase exits with tests, hashes, and records — a claim without evidence
  is not done.

## 13. Security and Product/Data Boundary

- Public repository: code, contracts, docs, schemas, examples, synthetic fixtures.
  Never: user ledgers, real runs, agendas, personal paths, credentials, private
  operation graphs, Maxwell user data.
- No literal secret values anywhere in repo/ledger/events; non-secret
  references/handles allowed; secret values never resolved into the ledger.
- Sanitization gate before any publication; secrets scan before any commit.
- Real runs and real migrations execute only in the private data area.
- `actor` remains the local user under process control until §13.8 is addressed —
  no simulated identity guarantees.

## 14. Deferred Architecture

Recorded as deferred layers only — **not designed now**:

- **Parallelism / real concurrency** (§13.7): claims/leases, multiple writers. The
  envelope (`event_id` + `seq`) is already the substrate; activation requires the
  parallelism round and written criteria.
- **Learning / routing** (Hamiltonian routing, bandits, scoring): requires a stable
  execution substrate and measurable evidence from real runs (closed verdicts +
  `family` per event; `verification_attempt` metrics). Activation criteria must be
  written and human-approved (ADR) before any design work — V1's deferred rules
  keep their written numeric criteria until DAGWELL equivalents exist.
- **Remote/UI/API surfaces**: possible by construction (authority below
  presentation), designed only after §13.8 and the §10 milestone.

## 15. Risks and Failure Modes

1. **Order-vs-locus tension.** The contract's incremental order says "on top of
   V1"; the approved structure builds a new package alongside a frozen V1. This
   Plan records the reconciliation (§6) explicitly — flagged so the human gate can
   confirm it is a clarification, not a reinterpretation. **Gate outcome
   (2026-08-23): CONFIRMED as clarification, not reinterpretation.**
2. **Parity gap at cutover.** DAGWELL may lag V1 features per operation; mitigated
   by per-operation human-gated cutover and V1 remaining operational.
3. **Schema churn in Phases 2–4.** Early ADRs (§13.2, §13.5, §13.18) constrain
   later phases; mitigated by `schema_version` in every event and by making those
   ADRs explicit entry conditions.
4. **§13.1 audit surprises.** `pass-ok`/`pass-falhou` semantics may not match the
   hypothesis table; the migration gate exists precisely for this — no legacy
   migration before the audit.
5. **Premature transport pressure.** The strongest failure mode: an implementer
   "just wiring" a platform through one transport and freezing the design by
   accident. Countered by the mandatory §10 milestone, the undecided-transport
   record, and the adapters-after-spec gate.
6. **Single-writer assumption ossifying.** `flock`-serialized appends are the
   present mechanism; the contract contracts serialization, not `flock`. Phase 11
   revisits under §13.7 — no distributed mechanics before then.
7. **Agent overreach.** A future agent jumping phases or resolving §13 silently;
   countered by AGENTS.md, per-phase forbidden lists, and ADR-gated entry
   conditions.

## 16. Human Decision Points

Explicit gates requiring Reinaldo (or a designated human) — chronological:

1. Approval of this Plan (Phase 0 exit).
2. Repository bootstrap authorization (Phase 1).
3. ADRs: §13.2 and initial §13.5 (Phase 2 entry); §13.18 (Phase 3 entry);
   §13.4 constatation (Phase 7 entry); §13.13/§13.14 runtime mechanics as they
   arise.
4. Promotion gates for future specifications: Runtime Policy Specification
   (§13.12); Adapter/Output Evidence Specification (§13.17, the §10 milestone);
   ledger migration spec (§13.6); `model:<family>` namespace (§13.15).
5. First real DAGWELL `--go` (spending gate).
6. Per-operation cutover V1 → DAGWELL.
7. Real data migration execution (Phase 10).
8. Publication/release gates (sanitization + human approval).
9. Phase 11 activation criteria (ADRs).

## 17. Definition of Foundation Complete

The `dagwell-foundation` workstream is complete when:

1. AGENTS.md ratified ✔ (hash recorded);
2. CLAUDE.md thin bridge created ✔ (hash recorded);
3. Repository Structure Proposal approved ✔ (final gate passed);
4. License resolved ✔ (Apache-2.0);
5. This Architecture & Migration Plan approved by human gate — **done ✔
   (2026-08-23)**;
6. Repository bootstrap (Phase 1) executed under its own authorization, with all
   hash verifications passing and the sanitization check clean.

Items 1–5 are done; the workstream closes on item 6 (repository bootstrap).

## 18. Recommended Next Action

This Plan passed its human gate on 2026-08-23. The next mission is **Phase 1 —
Repository bootstrap**: create the physical DAGWELL repository exactly per the
approved minimal bootstrap (proposal §13), under explicit authorization — nothing
beyond it, no publication, no runtime code.
