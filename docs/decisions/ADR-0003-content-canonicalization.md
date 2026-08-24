# ADR-0003 — `graph_version` / `input_hash` Content Canonicalization

- **Status: ACCEPTED — human gate, 2026-08-23**
- **Proposed:** 2026-08-23 · **Accepted:** 2026-08-23
- **Relates to:** Execution Contract §2 (emenda H2), §13.5 (deliberate Open Question)
- **Phase binding:** entry condition of Phase 2 (Architecture & Migration Plan §8);
  the exact `graph_version` file-set scope closes with Phase 4 (graph model)

**Approved decision:** initial canonicalization scheme is **Model T / `c1`** —
strict UTF-8, BOM removed, line endings normalized to LF, Unicode NFC, per-line
trailing whitespace preserved, exactly one terminal LF; digest SHA-256,
represented as `sha256:<lowercase-hex>`. The scheme is pinned via the existing
event `schema_version` mechanism (option H-a); historical hashes are never
redesigned. Graph includes/templates/preprocessing are NOT invented; the
definitive multi-file `graph_version` file-set remains deferred to the graph
phase, exactly as recorded in §D. Approved with the boundaries already stated in
this proposal. This resolves §13.5's initial scheme through the normal
human-gated ADR process; it does not modify the Execution Contract.

## Frozen semantics (NOT revisited here)

- `graph_version`: digest of the **content** of the executable graph definition at
  run creation. Not a git commit, tag, branch or nickname. Frozen in `run_created`.
- `input_hash`: digest of the **semantic canonicalized content** of the effective
  input. The filesystem path **never** participates; provenance lives in
  `input_ref`. Frozen in `run_created`.

This ADR designs only the *how*: algorithm, normalization, scope, failure
behavior, and versioning of the canonicalization itself.

## Guiding asymmetry (drives every recommendation below)

For identity digests, the two error directions are not symmetric:

- **False-distinct** (same semantics, different hash) is *safe*: worst case is a
  refused `resume` and a deliberate child run. Annoying, never corrupting.
- **False-identical** (different semantics, same hash) is *dangerous*: `resume`
  proceeds against changed semantics — exactly what I11 exists to prevent.

Therefore: canonicalize only what is provably a **machine accident** (the same
class of accident H2 removed when it expelled the path), and refuse to
canonicalize anything whose semantic equivalence we cannot guarantee.

## A. Digest algorithm

- **Candidate:** SHA-256 (stdlib, universal, already this project's convention —
  MANIFEST, recorded foundation hashes). BLAKE3 is faster but third-party;
  digest speed is irrelevant at pauta/graph sizes.
- **Representation:** algorithm-prefixed lowercase hex — `sha256:<64 hex>` —
  matching the contract's own illustrative values (`"graph_version": "sha256:…"`).
  The prefix gives algorithm agility without reinterpreting stored history.

## B. Text normalization (candidate "Model T" — normalized text)

Applied to text content before hashing; each knob listed is an explicit decision:

| Knob | Proposed default | Rationale |
|---|---|---|
| Encoding | UTF-8, **strict** decode | invalid bytes → fail closed (G) |
| BOM | strip a leading U+FEFF | editor artifact, not content |
| Line endings | CRLF / lone CR → LF | OS accident (requirement F) |
| Unicode normalization | NFC | same rendered text, one byte form |
| Per-line trailing whitespace | **preserve** | Markdown hard-break (two trailing spaces) is *semantic* — stripping would merge distinct documents |
| Terminal newline | normalize to exactly one LF | presence/absence of final EOL is an editor accident |

Model T removes machine accidents only; it never parses, reorders or interprets.

## C. Structured formats (candidate "Model S" — structural canonicalization)

Parse (YAML/JSON) → canonical re-serialization (sorted map keys, pinned scalar
forms) → hash. Honest accounting of what it drags in:

- key ordering: mappings sorted — reorder-only edits keep the hash;
- comments: erased by parsing — comment edits keep the hash;
- numeric forms: `1` vs `1.0` vs `0x1`, float formatting — a pinned number
  canon is required;
- booleans/null: YAML 1.1 (`yes/no/on/off`) vs 1.2 — the **loader dialect
  becomes part of the identity**;
- aliases/anchors: expansion is well-defined but changes the shape being hashed;
- duplicate keys: must **fail closed** (silent last-wins would hash a document
  the author never saw);
- invalid input: fail closed;
- equivalent syntax, identical semantics: the whole point — and the whole risk:
  the parser+serializer version pair silently defines "identical".

Model S maximizes stability against formatting noise, at the price of putting a
parser dialect inside the identity function. A library upgrade that changes any
parsing corner becomes a silent identity change — the exact class of hazard the
ledger design exists to avoid.

## D. `graph_version` scope — what is "the executable graph definition"?

DAGWELL's graph model does not exist yet (it is Phase 4 work). Today's honest
scope statement:

- **In scope:** the graph definition document(s) exactly as the executor will
  load them for the run.
- **Multi-file mechanism (candidate, decided at Phase 4):** per-file canonical
  digest, assembled as a manifest of `(stable-identifier, digest)` pairs sorted
  by identifier, then digested — identifiers being definition-internal names,
  never filesystem paths (H2 discipline).
- **Not invented here:** includes, references, graph fragments, templates —
  no such mechanism is specified in DAGWELL; they are marked **scope
  boundaries / future questions**, not solved by hashing tricks.
- **Schemas:** the validation schema shipped with the engine is *engine* version,
  not *graph* content — proposed as **out of scope** for `graph_version`
  (flagged for human confirmation).
- **Environment-dependent values:** a definition whose content depends on the
  environment at load time cannot have stable content identity — proposed as
  **invalid in the executable definition** (fail closed at `--go`), flagged for
  human confirmation.

## E. `input_hash` scope

Four distinct layers, kept distinct:

1. raw source bytes;
2. parsed semantic content;
3. normalized structured content;
4. "effective input" after deterministic preprocessing.

No preprocessing is specified anywhere in DAGWELL — so today, **effective input
= the input document content as presented at `--go`**, and layer 4 collapses
onto the document itself. This ADR does **not** add preprocessing. The input
(pauta) is prose/Markdown: layers 2–3 (structural parsing) do not meaningfully
apply — **Model T over the document content** is the natural candidate. If a
future specification defines preprocessing (e.g. includes), its *output* becomes
the effective input under the same canonicalization — future question, not
invented now.

## F. Reproducibility

By construction of Model T: the same semantic content on different paths (path
never read — H2), different machines, and different OS line-ending conventions
produces the **same** `input_hash`/`graph_version`. NFC removes the remaining
byte-form divergence of identical text.

## G. Collision / integrity behavior — fail closed

- Undecodable bytes, unsupported format, (under Model S) parse errors or
  duplicate keys → **hard error at `--go`**, before any spend (I5 pattern).
- **Canonicalization errors never fall back silently to raw-byte hashing** — a
  fallback would make one recorded value mean two different functions.
- Digest collision (cryptographically negligible): no special machinery; the
  identity comparison of I11 simply behaves as designed.

## H. Versioning of the canonicalization itself

Historical hashes must never be reinterpreted. The canonicalization function
must therefore be **identified per run**. Two candidate mechanisms (human
decision required):

- **H-a (recommended):** pin the canonicalization scheme to the
  `schema_version` of the `run_created` event — each `schema_version` maps to
  exactly one documented scheme (e.g. `c1` = Model T + SHA-256 as specified
  here). Uses existing contract machinery; stored values keep the contract's
  `sha256:<hex>` shape.
- **H-b:** encode the scheme in the value itself (e.g. `sha256:c1:<hex>`).
  Self-describing, but extends the value format beyond the contract's
  illustrative shape — a step this proposal does not take unilaterally.

Either way: a future scheme (e.g. structural Model S) is introduced as a new
version through the normal gated process; old runs keep their old scheme and
`resume` compares like with like.

## I. Migration (Maxwell V1 / legacy)

- V1 never computed these identities. **No hash is fabricated** for legacy data:
  `legacy-<operation>` synthetic runs remain `legacy_ambiguous: true`, outside
  modern checkpoints, with `legacy_raw`/`legacy_origin` preserved (§2, I23).
- Whether a synthetic `run_created` for legacy runs carries null/absent identity
  fields belongs to §13.6 — untouched here.
- Modern DAGWELL runs are unaffected by legacy: the scheme applies from its
  approval forward.

## Decision drivers

1. False-distinct is safe; false-identical is dangerous — canonicalize machine
   accidents only (the H2 principle, extended from paths to bytes).
2. Keep parsers out of the identity function until evidence shows formatting
   noise is a real cost (data-driven escalation to Model S remains open).
3. Fail closed, before spend, always; no silent fallbacks.
4. Every hash must be re-derivable forever → the scheme itself is versioned.
5. Do not invent mechanisms (includes, preprocessing, binary inputs) to make
   hashing more interesting.

## Candidate canonicalization models

| Model | Function | Strength | Cost |
|---|---|---|---|
| R — raw bytes | hash exact bytes | zero ambiguity | CRLF/BOM/NFC accidents split identical content — fails requirement F |
| **T — normalized text** | §B table, then SHA-256 | removes exactly the machine accidents; no parser in the identity path | formatting/comment edits create new (safe) versions |
| S — structural | parse → canonical serialize → hash | immune to formatting noise | parser dialect inside identity; silent-drift hazard; high spec burden (§C) |

## Recommended model

**Model T for both identities, under scheme id `c1`:**

- digest: SHA-256, stored as `sha256:<64 hex>`;
- canonicalization: UTF-8 strict, BOM stripped, EOL→LF, Unicode NFC, per-line
  trailing whitespace preserved, exactly one terminal LF;
- `input_hash`: Model T over the effective input document (today: the pauta as
  presented at `--go`);
- `graph_version`: Model T per constituent definition file; multi-file assembly
  via sorted identifier+digest manifest, with the definitive file-set scope
  fixed in Phase 4 alongside the graph model;
- scheme version pinned via `run_created.schema_version` (H-a);
- Model S deliberately **deferred** as a possible future scheme, introduced only
  through the gated versioning process if real data shows formatting noise is a
  material cost.

## Exact boundaries still requiring human decision

1. Confirm Model T over Model S as the initial scheme (the core choice).
2. Confirm each §B knob (notably: trailing-whitespace preservation; single
   terminal LF).
3. Confirm H-a (scheme via `run_created.schema_version`) over H-b (in-value).
4. Confirm schemas are engine version, out of `graph_version` scope (§D).
5. Confirm environment-dependent definition content is invalid, fail closed (§D).
6. Phase 4: the definitive `graph_version` file-set rule and the multi-file
   manifest identifiers.
7. Future only if ever specified: preprocessing/effective-input pipeline; binary
   input types (raw-bytes digest by declaration).

## Rejected alternatives

- Model R raw bytes (fails reproducibility requirement F for identical content).
- Model S as the *initial* scheme (parser dialect inside identity; silent-drift
  hazard disproportionate to today's needs — kept as a future versioned scheme).
- Silent fallback raw-hash on canonicalization error (one value, two meanings —
  forbidden by drivers 3–4).
- Path-salted hashing (violates frozen H2 semantics outright).
- Git-derived identity for `graph_version` (violates frozen semantics: the graph
  is data outside the product's version control).

## Consequences

- Identical content on different machines/paths/EOL conventions yields identical
  identity; `resume` validation (I11/I25) behaves as the contract intends.
- Comment or formatting edits to a graph definition change `graph_version` —
  producing safe false-distincts (new version ⇒ child run), never false
  identity.
- The canonicalization function is documented, versioned, and re-derivable —
  historical hashes never reinterpreted.
- No new dependencies: `hashlib` + `unicodedata`, stdlib only.

## Migration considerations

No retroactive hashing of V1 history; legacy stays explicitly ambiguous
(`legacy_ambiguous: true`) exactly as the contract requires; §13.6 decides the
physical importer separately; nothing here blocks or presupposes it.

## Human gate — outcome

**APPROVED (2026-08-23), with the boundaries already stated in this proposal.**
Model T / `c1` is the initial scheme; scheme identification via the existing
`schema_version` mechanism (H-a); no includes/templates/preprocessing invented;
the §D/Phase 4 boundaries (definitive multi-file `graph_version` file-set) close
later at their own gate. This ADR is the recorded architectural decision for
§13.5's initial scheme; Phase 2 implementation is authorized against it.
