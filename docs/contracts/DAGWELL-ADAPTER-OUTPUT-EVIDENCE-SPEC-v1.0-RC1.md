# DAGWELL — Adapter / Output Evidence Specification · v1.0-RC1

> **Status: RELEASE CANDIDATE — NON-NORMATIVE.**
> This document is the deliverable of the Phase 8 milestone (Migration Plan §10,
> Execution Contract §13.17). It is **not normative** until human promotion into
> `MANIFEST.sha256`. Until then, nothing in it authorizes implementation, resolves
> an open question in code, or weakens any invariant. The Execution Contract v1.0
> prevails over this document at every point of contact.
>
> Promotion procedure: review → human gate → recorded hash in `MANIFEST.sha256`,
> with this RC preserved intact (AGENTS.md §11).

---

## 1. Purpose and scope

The Execution Contract fixed the concept of output evidence, its canonical
identity (`evidence_id`, I29), the per-node declaration duty (I5, I28) and the
fail-closed rule. It deliberately left open (§13.17): the concrete format of each
evidence type, the `evidence_id` encoding per type, the validation of external
receipts, and the adapter mapping. The Migration Plan (§10) reserved twenty
questions the adapter model must answer before any adapter is implemented.

This specification answers those questions. It closes §13.17 and §13.15, and it
specifies the **capability model** that governs which harness and which model
family executes a node.

What this specification does **not** do:

- It does not implement anything. Phase 9 implements, one adapter at a time, each
  behind its own spending gate.
- It does not resolve §13.12 (retry policy), §13.4 (orphan alert calibration),
  §13.16 (sequence-gap reconciliation), §13.8 (strong actor identity) — those
  stay open, and every default here in their area is fail-closed.
- It does not introduce learning, scoring, bandits, or any automatic routing.
  Model selection under this specification is **declarative and deterministic**
  (§4). Learned routing remains a deferred layer (Migration Plan §14) with its
  own written activation criteria.

## 2. The three-layer model

The Migration Plan (§3.4) institutionalizes a separation this specification now
fixes as the shape of the adapter interior:

| Layer | Question it answers | Examples |
|---|---|---|
| **Transport** | *How* is work handed to an executor and how does the result come back? | `subprocess` (local CLI), `http`, `sdk`, `mcp`, `a2a` |
| **Platform binding** | *What* is being spoken to, in that transport's terms? | the `claude` CLI, the `codex` CLI, an OpenAI-compatible endpoint, a Hermes instance |
| **Capability** | *What can it do, at what tier, at what relative cost?* | model families offered, difficulty tiers served, headless invocation form, streaming support |

**Resolution of reserved question 20:** adapters are organized **by composition**
— a platform binding *names a transport* and *declares capabilities*; transports
are shared infrastructure, never duplicated per platform. Neither
`adapters/hermes/` nor `adapters/subprocess/` alone: `adapters/transports/` holds
transport implementations, `adapters/bindings/` holds platform bindings as
**data** (declarations), and binding logic stays generic. The `adapters/`
boundary fixed by ADR-0001 is unchanged; this fixes its interior.

Two consequences, stated once:

- **Adapters emit transport events and output evidence — never verdicts**
  (AGENTS.md §8, I6). Nothing in any layer translates an exit code, HTTP status,
  or model output into `approved`/`rejected`.
- **The engine core never imports adapters** (Migration Plan, Phase 9). The core
  defines the interfaces in this specification; adapters conform to them at the
  edge.

## 3. Adapter binding declaration

### 3.1 Node side — what enters run identity

A node declares **what the work needs**, never which concrete executor performs
it:

```json
{
  "id": "write-script",
  "deps": ["research"],
  "output_evidence": "artifact",
  "verifications": [{"verification_id": "has-sources", "family": "deterministic"}],
  "capability_requirements": {"tier": "standard"},
  "mission": "Write the script from briefing.md. Write it to $OUT."
}
```

- `capability_requirements` and `mission` are **semantic content**: they enter
  the graph canonicalization (ADR-0003/0009) and therefore `graph_version`.
  Changing the tier or the mission changes the work's identity — correctly.
- The concrete binding, model id, and command line are **not** in the graph and
  do **not** enter identity. The same graph may run today against one registry
  and tomorrow against a cheaper one: it is the same work. Which executor
  actually ran is a **transport fact**, recorded on `node_dispatched` (§3.3).
- The legacy `x_harness`/`x_command` convention (USAGE §5) remains valid for
  operator-driven runs: unknown fields are still ignored by the engine and still
  enter the graph hash. A node carrying `x_command` pins its executor by
  identity, deliberately. A node carrying `capability_requirements` delegates
  resolution to the registry. Carrying **both** is a hard validation error at
  graph load — one identity model per node.

### 3.2 Registry side — the binding registry

The binding registry is **data, not product** (lives in the data area, never in
the public repository — Migration Plan §13). It is a JSON document mapping
platform bindings to transports, capabilities, and tiers:

```json
{
  "registry_version": 1,
  "bindings": [
    {
      "binding_id": "claude-cli",
      "transport": "subprocess",
      "platform": "claude",
      "invocation": "claude -p {mission}",
      "probe": "claude --version",
      "timeout_seconds": 3600,
      "models": [
        {"model_id": "haiku",  "family": "anthropic-claude", "tiers": ["trivial", "simple"],            "relative_cost": 1},
        {"model_id": "sonnet", "family": "anthropic-claude", "tiers": ["standard"],                     "relative_cost": 5},
        {"model_id": "opus",   "family": "anthropic-claude", "tiers": ["complex", "frontier"],          "relative_cost": 25}
      ]
    }
  ]
}
```

- `invocation` is a template; `{mission}` and the exported `$OUT` are the only
  substitution points. No shell interpolation of ledger content beyond these.
- `relative_cost` is an operator-declared ordering aid, not a billing model —
  §13.12 stays open and no budget formula is introduced here.
- The registry file's content digest (`registry_digest`, same canonicalization
  scheme as ADR-0003) is recorded on every dispatch it resolved (§3.3), so the
  provenance of a selection is always reconstructible — without making the
  registry a second source of truth: the ledger records what *was* used; the
  registry proposes what *may* be used.

### 3.3 Deterministic selection — difficulty dictates the model

Reserved questions 2 and 14 resolve here, together with the operating directive
that motivates the capability model: **the difficulty of the task dictates the
model — never the reverse, and never prestige.** A trivial task must not burn a
frontier model.

Tiers form a closed, ordered set:

```
trivial < simple < standard < complex < frontier
```

Selection rule (normative once promoted):

1. Filter registry models to those whose `tiers` include the node's required
   tier and whose binding transport is available (probe, §6.6).
2. Among them, select the **lowest `relative_cost`**. Tie → lowest
   lexicographic `(binding_id, model_id)` — determinism over cleverness.
3. No candidate → **hard refusal before spend** (the run does not start, or the
   node cannot be dispatched; nothing silently upgrades or downgrades a tier).

The resolved selection is recorded on `node_dispatched` as transport facts:

```json
{"binding_id": "claude-cli", "model_id": "haiku",
 "family": "anthropic-claude", "registry_digest": "sha256:…"}
```

- Capability discovery is **static and declared** (question 2): the registry is
  written by the operator. No runtime probing of what a platform "can do" — a
  probe checks liveness (§6.6), never capabilities.
- This is the entire routing model of this specification. It contains no memory,
  no scores, no adaptation. Hermes and Buzz consume it by writing registries and
  graphs — the engine's answer is a pure function of (graph, registry).

## 4. Output evidence — concrete formats and `evidence_id` encoding

The contract fixes four types (§13.17) and the binding of every verdict to
`(run_id, node_id, attempt, verification_id, verification_attempt, evidence_id)`
(I29). This section gives each type its concrete format and its `evidence_id`.

### 4.1 Uniform encoding

`evidence_id` is uniformly `sha256:<64 lowercase hex>` for every type. The
contract permits a non-hash identity; this specification chooses the hash form
anyway because it is stable, verifiable offline, and already the digest
discipline of the ledger. What varies per type is **what is digested** — always
a canonical byte sequence, canonicalized under the same scheme already promoted
for content addressing (ADR-0003 Model T / `c1`; for JSON payloads: UTF-8,
lexicographically ordered keys, no insignificant whitespace, minimal number
form — the RFC 8785 discipline — reusing the existing canonicalizer wherever it
applies).

### 4.2 `artifact`

- **Format**: non-empty `output_manifest`: ordered list of entries
  `{path, artifact_digest, size_bytes}`, `path` relative to the attempt
  directory (`runs/<operation>/<run_id>/<node_id>/t<k>/` — I18), `artifact_digest`
  = `sha256:` of file bytes.
- **`evidence_id`**: sha256 of the canonicalized manifest. `artifact_digest`
  therefore *participates in the derivation*, as I29 anticipates.
- **Invalid** (already contract-fixed): manifest absent, empty, or malformed;
  any listed file absent or digest-mismatched at validation time.

### 4.3 `structured_value`

- **Format**: a JSON value returned by the executor, stored verbatim in the
  attempt directory as `value.json`, plus its canonicalized form.
- **`evidence_id`**: sha256 of the canonicalized JSON bytes.
- **Invalid**: not parseable as JSON; canonicalization failure; empty payload.

### 4.4 `remote_receipt`

- **Format**: a JSON receipt **issued by the remote side**, containing at
  minimum `{issuer, remote_id, issued_at}` — the remote system's own job/receipt
  identifier, not a local claim about it. Stored verbatim as `receipt.json`.
- **`evidence_id`**: sha256 of the canonicalized receipt.
- **Invalid**: missing any minimum field; `remote_id` empty; receipt not
  attributable to the dispatched work (attribution rule per adapter, proven by
  that adapter's Phase 9 tests).

### 4.5 `side_effect_receipt`

- **Format**: a JSON proof of the external effect, minimum
  `{effect_type, proof}` where `proof` is externally checkable (a published URL,
  a transaction id, a message id — something a verifier can go look at).
  Stored verbatim as `receipt.json`.
- **`evidence_id`**: sha256 of the canonicalized receipt.
- **Invalid**: missing minimum fields; `proof` empty or self-referential (the
  bare assertion "we did it" — the exact failure ADR-0008 closed).

### 4.6 Interaction with ADR-0008

ADR-0008 restricts `no_verification` to evidence types the core can validate on
its own — today only `artifact`. Once this specification is promoted **and** the
per-type validations above are implemented and tested, the core can validate the
*form* of all four types; ADR-0008's restriction may then be revisited **by a
new ADR, never silently**. Until that ADR exists, the restriction stands
unchanged: form-validity is not effect-validity, and a receipt that parses
still proves nothing about the world without a verifier looking at it.

## 5. `model:<family>` namespace — §13.15 decided

The Migration Plan allows §13.15 to be decided within the Phase 8 specification.
Decision:

- Verdict family syntax: `model:<vendor>-<family>`, lowercase, hyphen-separated,
  ASCII — e.g. `model:anthropic-claude`, `model:openai-gpt`, `model:xai-grok`,
  `model:google-gemini`, `model:moonshot-kimi`.
- `<family>` names the **model family**, never the specific model: `haiku`,
  `sonnet` and `opus` are all `anthropic-claude`. The specific `model_id` is a
  transport fact (§3.3) and never appears in `family`.
- R1 (I16) operates on the family string: a producer executed by any
  `anthropic-claude` model and a verifier of family `model:anthropic-claude`
  are the **same family** — same-family verification requires `r1_exception`,
  regardless of which model within the family ran.
- The canonical registry of family names is a versioned product file
  (`docs/registries/model-families.md`), changed only by reviewed commit. Two
  adapters labelling the same model with different family names is exactly the
  silent R1 weakening §13.15 warned about; the registry file is the tie-breaker.

## 6. Transports

### 6.1 Transport set (question 1)

`transport ∈ {subprocess, http, sdk, mcp, a2a}` — a closed set **of names**;
only `subprocess` is specified by this document. The other four are **reserved**:
each becomes usable only through its own gated extension of this specification
(same RC → human gate → promotion process). Naming them here prevents ad-hoc
strings; it authorizes nothing.

### 6.2 `subprocess` — the v1 transport

The one transport with verified real-world forms today (USAGE §5.4):

- **Execution model** (question 3): synchronous. Spawn, wait, reap. One process
  per dispatched attempt.
- **Environment**: `$OUT` exported, pointing into the attempt directory (I18 —
  never shared between runs or attempts). Working directory is the attempt
  directory. Credentials are **never** passed as ledger/graph content: the
  process inherits named environment variables from the operator's environment;
  the ledger may record the *names*, never the values (question 8; AGENTS.md §9).
- **Session persistence** (question 4): none. Every dispatch is stateless; a
  platform's conversational memory is out of scope for v1 and would require its
  own extension (recorded as open, not half-supported).
- **Streaming** (question 5): the transport MAY capture stdout/stderr
  incrementally into the attempt directory; evidence is only ever the final
  state. No streaming surface is exposed upward.
- **Timeout** (question 10): `timeout_seconds` is **mandatory** in every
  subprocess binding — a binding without it is refused at registry validation
  (fail-closed; no invented universal default). Expiry ⇒ cancellation ladder
  (§6.3); for a producer the attempt records transport failure (→ `failed`, §4
  of the contract); for a verifier, `verification_status: timeout` (I7).
- **Exit codes**: transport facts, recorded verbatim. Never verdicts (I6), and
  never sufficient: `exit 0` without the declared evidence does not reach
  `executed` (I28 — the case USAGE §5.3 demonstrates).

### 6.3 Cancellation (question 6)

Graceful ladder: SIGINT → grace period → SIGTERM → grace period → SIGKILL.
Grace-period duration and cleanup mechanics remain runtime decisions under
§13.14 (open). Semantics are the contract's §10, unchanged: graceful
interruption records `run_interrupt_requested`; an in-flight verifier cancelled
this way records `verification_status: cancelled` without consuming re-fire
policy; abrupt loss records nothing and orphans are evidenced at observation.

### 6.4 Remote orphan detection (question 7)

Not specified for v1 — `subprocess` orphans are local and already covered by
§10/§13.4 (observation by `resume` or explicit human command; constatation
criteria still open). A future remote transport's extension MUST specify its
liveness/constatation mechanism before promotion; until then remote dispatch
does not exist, so there is nothing to detect. Fail-closed by absence.

### 6.5 Cost and quota reporting (question 9)

A transport MAY attach a `cost_report` object (free-form, adapter-documented) to
the return event as transport fact. It never participates in any verdict, gate,
or fold decision, and no budget model is derived from it — §13.12 stays open.
DAGWELL still spends nothing; the `x_command`/binding spends (USAGE §5.5).

### 6.6 Health, readiness, negotiation (questions 15, 16)

- `probe` is an optional **zero-cost** liveness command per binding (e.g.
  `claude --version`). It runs at selection time; failure removes the binding
  from candidates (§3.3). A probe that spends quota is a forbidden probe.
- Version/capability **negotiation** does not exist in v1: capabilities are
  static declarations (§3.2). If a platform changes under a binding, the
  operator updates the registry — the `registry_digest` on each dispatch keeps
  history honest.

### 6.7 Lifecycles and fallback (questions 17, 18, 19)

- **Local process lifecycle** (17): §6.2–§6.3 are the complete v1 answer.
- **Remote job lifecycle** (18): reserved to each remote transport's future
  extension. Not sketched here — sketching surfaces is what the contract
  forbids.
- **Fallback between transports** (19): **none in v1.** Automatic fallback would
  silently change who executed the work — the kind of invisible substitution
  the ledger exists to prevent. A binding failure is a dispatch failure,
  recorded; switching bindings is an operator/registry decision, visible in the
  next dispatch's transport facts.

### 6.8 Retry interaction (question 11)

None introduced. Automatic retry remains disabled until the Runtime Policy
Specification (§13.12) exists — not as a choice but because nothing authorizes
automated spending (Migration Plan, Phase 7). Only `human_retry` acts. This
specification only guarantees that every new attempt is a fresh dispatch
through §3.3 selection (a retry may therefore resolve to a different model —
recorded, deterministic, and within the same declared tier).

## 7. The twenty reserved questions — disposition table

| # | Question (Plan §10) | Disposition |
|---|---|---|
| 1 | transport type | closed name set; only `subprocess` specified (§6.1–6.2) |
| 2 | capability discovery | static, operator-declared registry (§3.2–3.3) |
| 3 | sync vs async | v1 synchronous subprocess; async reserved to future transports (§6.2) |
| 4 | session persistence | none in v1; explicit future extension (§6.2) |
| 5 | streaming | capture-only, never a surface (§6.2) |
| 6 | cancellation | signal ladder + contract §10 semantics; grace mechanics stay §13.14 (§6.3) |
| 7 | remote orphan detection | reserved to remote-transport extensions; local per §10/§13.4 (§6.4) |
| 8 | auth/credentials boundary | env-var names as handles, values never in ledger/graph (§6.2) |
| 9 | cost/quota reporting | optional transport fact, never decisional (§6.5) |
| 10 | timeout semantics | mandatory per-binding `timeout_seconds`, fail-closed (§6.2) |
| 11 | retry interaction | none until §13.12; fresh selection per attempt (§6.8) |
| 12 | evidence/receipt production | four concrete formats + uniform `evidence_id` (§4) |
| 13 | side-effect evidence | `side_effect_receipt` with externally checkable proof (§4.5) |
| 14 | model/provider family identity | `model:<vendor>-<family>` + registry file (§5) |
| 15 | health/readiness | zero-cost `probe` at selection (§6.6) |
| 16 | version/capability negotiation | none; static declarations + `registry_digest` (§6.6) |
| 17 | local process lifecycle | §6.2–6.3 |
| 18 | remote job lifecycle | reserved, unsketched (§6.7) |
| 19 | fallback between transports | forbidden in v1; operator decision only (§6.7) |
| 20 | organization of adapters | layered composition: transports as code, bindings as data (§2) |

## 8. What stays open after promotion

Promotion of this document closes §13.17 and §13.15. It does **not** close:

- §13.12 — retry/budget policy (automatic retry stays off).
- §13.4 — orphan constatation and alert calibration.
- §13.16 — sequence-gap reconciliation.
- §13.8 — strong actor identity (bindings run as the local user).
- §13.14 — grace-period mechanics.
- Session persistence, remote transports (`http`, `sdk`, `mcp`, `a2a`), and
  remote job lifecycles — each requires its own gated extension.
- Learned routing (Migration Plan §14) — activation criteria must be written
  and human-approved before any design work. The tier model here is its
  substrate, not its beginning.

## 9. Phase 9 conformance checklist

An adapter implementation may enter Phase 9 review only with, at minimum:

1. Registry validation tests: missing `timeout_seconds`, unknown transport,
   empty tier list, malformed invocation template — all refused before spend.
2. Selection tests: cheapest-satisfying rule, tie-break determinism, hard
   refusal when no candidate serves the tier, both-identity-models node refused
   at load.
3. Evidence tests per supported type: valid form accepted; each "invalid" bullet
   of §4 refused; `evidence_id` reproducible from stored bytes alone.
4. Transport-fact isolation tests: exit codes, cost reports, and model ids never
   appear in any `verdict` or `family` field the adapter emits — because the
   adapter emits none (AGENTS.md §8).
5. The zero-cost suite stays zero-cost: probes and all tests run without quota,
   paid inference, or external effects.
6. Its own human spending gate before the first real dispatch.

## 10. Alternatives considered

| Alternative | Why not |
|---|---|
| Model id inside the graph (identity) | prestige pinning; same mission would need N graphs for N price points; tier is the semantic fact, executor is history |
| Automatic tier upgrade when no cheap model is available | silent spend escalation — the exact failure the tier model exists to prevent; refusal is the correct answer |
| Automatic transport fallback | invisible substitution of executor; contradicts the ledger's reason to exist |
| Runtime capability probing | probing costs and lies (a model listing an endpoint is not a capability); declarations + registry digest are auditable |
| Per-type bespoke `evidence_id` encodings (hash for artifact, remote id verbatim for receipts) | two identity disciplines to audit; remote ids survive inside the receipt, the digest survives outside it |
| Free-form family strings per adapter | two names for one model silently weakens R1 — §13.15's own warning |

---

*Predecessor documents: none — first RC of this specification. Review findings
and gate outcome to be recorded in the promoting commit and, where architectural,
as ADRs.*
