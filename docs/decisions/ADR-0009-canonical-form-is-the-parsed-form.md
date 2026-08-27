# ADR-0009 — Addendum to ADR-0003: The Canonical Form Is the Parsed Form

- **Status: ACCEPTED — human gate, 2026-08-26**
- **Relates to:** ADR-0003 (content canonicalization); Execution Contract I24, §13.5
- **Origin:** independent audit of 2026-08-25 (both auditors, openai and xai,
  independently recommend ratification; reproduced before drafting)

## Context

ADR-0003 fixes *how* `graph_version` is computed: canonicalize the text (Model
T / scheme `c1`), then digest. It does not say, in so many words, what text the
*parser* reads to build the in-memory graph the executor runs against.

There are two candidates: parse the raw file as written, or parse the same
canonicalized text the digest addresses. `src/dagwell/graph.py` already does
the latter — `load_graph` canonicalizes first, then parses — and its docstring
already carries the reasoning. This ADR ratifies that choice as the recorded
architectural decision; it changes no code.

Both independent auditors of 2026-08-25 reviewed this convention and both
recommend ratification. Their reasoning, confirmed here: parsing the raw form
instead would let one `graph_version` digest name two different parsed graphs.
Unicode NFC normalization (part of Model T) can compose or decompose
code-point sequences that render identically — a node id written in
decomposed form in the raw file and in composed form after canonicalization
would be two different id strings for what the digest treats as one identity
(I24: the frozen snapshot *is* the canonicalized text). Parsing the raw file
would silently reintroduce the byte-form divergence Model T exists to remove.

## Decision

**The parser reads the canonical `c1` form — the same text the digest
addresses and the same text the frozen snapshot stores.** Canonicalize first,
parse second, always. This is not a new rule: it is what `load_graph` already
does, now recorded as the architectural decision rather than left implicit in
one function's docstring.

Nothing is invented beyond ADR-0003's existing scope: no new normalization
knob, no change to Model T, no change to the digest algorithm.

## Consequence to register (not a defect — a semantic fact)

Because parsing happens after NFC normalization, **NFC participates in the
identity of every node id, not only in the identity of the graph as a whole.**
Two node ids that are byte-distinct in the raw file but canonically equivalent
under NFC collapse into the same string after canonicalization.

This is not silently permissive: `validate_graph` runs against the
already-canonicalized data and its existing duplicate-id check
(`graph.py::validate_graph`) catches the collision as `GraphValidationError`
— a hard failure at `--go`, before any spend, exactly as I5 requires. The
authoring surface this ADR asks graph authors to know: **node ids are
compared in canonical NFC form**, so two ids that look identical on screen but
differ only in Unicode composition will be treated as one identity and
refused as a duplicate, never silently treated as two.

## Consequences

- No code change. This ADR documents `graph.py::load_graph`'s existing
  behavior as the ratified decision, closing eixo 4(a) of the 2026-08-25
  audit synthesis.
- Future graph-authoring tooling (linters, editors) should normalize-and-check
  ids at author time, so this collision surfaces before `--go`, not at it —
  a tooling recommendation, not a contract requirement.
- Phase 4's multi-file `graph_version` file-set rule (ADR-0003 §D, still
  deferred) inherits this same discipline: canonicalize each constituent file
  before parsing it, for the same reason.
