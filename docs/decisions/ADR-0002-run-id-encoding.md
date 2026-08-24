# ADR-0002 — `run_id` Encoding

- **Status: ACCEPTED — human gate, 2026-08-23**
- **Proposed:** 2026-08-23 · **Accepted:** 2026-08-23
- **Relates to:** Execution Contract §2, §13.2 (deliberate Open Question)
- **Phase binding:** entry condition of Phase 2 (Architecture & Migration Plan §8)

**Approved decision:** DAGWELL `run_id` encoding is **UUIDv7 (RFC 9562)**, canonical
lowercase hyphenated text form. Preserved by the approval: opaque identity; never
derived from graph/input; `legacy-` namespace reserved; `seq` remains the
authoritative ordering inside a run — `run_id` time-sortability is convenience,
not fold ordering. This resolves §13.2 for implementation through the normal
human-gated ADR process; it does not modify the Execution Contract.

## Frozen requirements (NOT revisited here)

The contract already fixes the semantics; every option below is evaluated against
them, none of them is reopened:

opaque · globally unique in DAGWELL's operational domain · never reused · not
derived from graph/input content · time-orderable · generable under the ledger
serialization mechanism · `legacy-` prefix reserved for synthetic legacy runs ·
CLI prefix acceptance only with unique resolution.

## Three properties that are NOT synonyms

- **Sortable by creation time**: the textual/byte form sorts in approximate
  creation order (timestamp-prefixed encodings). Ties possible within clock
  granularity.
- **Strictly monotonic**: every new id compares greater than every previously
  issued id, guaranteed — requires a coordination point (counter/lock).
- **Globally unique**: no two ids ever collide, across processes, machines and
  data areas, without coordination.

Note: within a run, the **authoritative order is `seq`** (contract §9), never the
`run_id`. Time-orderability of `run_id` is an operational convenience (listing,
pruning, human navigation), not a fold-ordering mechanism. This lowers the stakes
of strict monotonicity.

## Options

### O1 — UUIDv7 (RFC 9562)

128 bits: 48-bit Unix-epoch millisecond timestamp + version/variant bits +
74 random bits. Canonical text: lowercase hex with dashes, 36 chars
(e.g. `0198c7a0-5f2e-7c3a-9f4e-2d6b8a1c0e55`).

1. Conformity: opaque ✔, unique ✔, never reused ✔ (never re-generated), not
   content-derived ✔, time-orderable ✔, generable under (but independent of) the
   lock ✔.
2. Uniqueness: 74 random bits per ms — collision probability negligible; the
   `run_created` uniqueness precondition (§2/§9) is the hard backstop.
3. Time ordering: lexicographic sort of the canonical text = byte order =
   millisecond creation order.
4. Monotonicity/clock: NOT strictly monotonic by default (same-ms randomness);
   clock regression can produce out-of-order ids but never duplicates. RFC 9562
   defines optional monotonicity counters if strictness is ever wanted.
5. Concurrent/future writers: no coordination needed — each writer generates
   independently. Ready for §13.7 without redesign.
6. Lock dependence: none. Generation may happen inside the `--go` critical
   section, but correctness does not require it.
7. Portability: fully portable; ids minted in different machines/data areas never
   collide.
8. Human usability / prefix: first chars are the timestamp, so short prefixes
   discriminate well between runs created at different times; same-ms runs need
   longer prefixes. Prefix resolution stays lookup-based with hard error on
   ambiguity (frozen rule).
9. Canonical text: standardized, lowercase hex-with-dashes.
10. `legacy-` interaction: hex alphabet (`0-9a-f`) cannot produce the letter `l`;
    collision with the reserved prefix is impossible by construction.
11. Python: `uuid.uuid7()` in the stdlib from Python 3.14; for the 3.11 floor, a
    ~20-line vendored RFC 9562 generator (or a small dependency) — trivial, pure
    stdlib primitives (`os.urandom`, `time.time_ns`).
12. Migration: none needed; legacy rows keep `legacy-<operation>` (§2).
13. Security/privacy: embeds creation time (already public in `occurred_at`);
    random bits from the OS CSPRNG; no content linkage (opacity preserved).
14. Failure modes: clock skew/regression → ordering anomaly only; low-entropy
    environments (exotic) → mitigated by OS CSPRNG.
15. Interoperability: IETF standards-track; universally understood; excellent for
    a public project.

### O2 — ULID

128 bits: 48-bit ms timestamp + 80 random bits. Text: 26-char Crockford base32
(e.g. `01J8ZC9QK7T2N4R6W8XA0B1C2D`), lexicographically sortable.

1–7. Essentially equivalent to UUIDv7 (opaque, unique, sortable, coordination-
   free, lock-independent, portable). A community "monotonic mode" increments the
   random part within the same ms — strict monotonicity per process only.
8. Usability: shorter (26 chars, no dashes), pleasant to read/paste; prefix
   behavior same as O1.
9. Canonical text: Crockford base32; spec canonical is uppercase, ecosystem usage
   is mixed — a canonical case would have to be pinned by us.
10. `legacy-`: Crockford alphabet excludes `I`, `L`, `O`, `U` — collision with the
    reserved prefix impossible.
11. Python: no stdlib support; third-party (`python-ulid`) or ~40-line vendored
    implementation.
12–14. Same profile as O1.
15. Interoperability: popular but community-specified (no IETF standard); slightly
    weaker as a public-protocol choice.

### O3 — Serialization-backed monotonic/sequential identifier

An identifier minted under the ledger's serialization mechanism (today `flock`),
e.g. `run-000123` or `<epoch-ms>-<counter>`.

1. Conformity: opaque-ish (a counter leaks run count — arguably metadata, not
   content; opacity in the contract's sense — non-derivability from graph/input —
   holds), unique **only within one ledger domain**, time-orderable ✔ (if
   timestamped) , generable under the lock ✔ (by definition).
2. Uniqueness: guaranteed by the lock **locally**; two data areas / machines can
   mint the same id — cross-domain aggregation, backup-merge and any future
   multi-writer world inherit a collision hazard.
3. Time ordering: exact, if timestamp-prefixed.
4. Monotonicity: **strictly monotonic** — the only option that gives this.
5. Concurrent/future writers: requires the lock (or a successor coordination
   service) on every mint; couples id generation to §13.7's unresolved
   concurrency design.
6. Lock dependence: total — the defining property and the defining liability.
7. Portability: poor (domain-local uniqueness only).
8. Usability: best-in-class (short, human-friendly, trivial prefixes).
9. Canonical text: ours to define (no external standard).
10. `legacy-`: must be kept disjoint by explicit prefix choice (e.g. `run-`);
    works, but by convention rather than by alphabet.
11. Python: trivial; but the counter needs durable state — a **second mutable
    file beside the ledger** (or a scan of the ledger on every mint), which sits
    uncomfortably close to "no second authoritative artifact" (I2/I25) even if it
    is formally just an allocator.
12. Migration: fine locally; painful if the domain ever splits/merges.
13. Security/privacy: leaks run cadence/count.
14. Failure modes: counter-state corruption/loss → mint blocked or duplicate risk;
    exactly the class of failure the ledger design tries to avoid.
15. Interoperability: none (bespoke).

### Briefly considered and set aside

- **UUIDv4**: globally unique but not time-orderable — fails a frozen
  requirement outright.
- **KSUID**: second-granularity timestamp (coarser ordering), third-party only,
  no material advantage over O1/O2.

## Decision drivers

1. Survive the future the contract already names: §13.7 concurrency must not
   force a re-encoding — coordination-free generation wins.
2. `seq` is the authoritative order; strict monotonicity of `run_id` buys little.
3. Public project → prefer an IETF standard over community or bespoke encodings.
4. Fail-closed backstop already exists (`run_created` uniqueness precondition).
5. Keep the ledger the only durable artifact — no allocator side-files.

## Options table

| Criterion | O1 UUIDv7 | O2 ULID | O3 sequential |
|---|---|---|---|
| Frozen requirements | ✔ | ✔ | ✔ local-domain only |
| Sortable by creation time | ✔ (ms) | ✔ (ms) | ✔ (exact) |
| Strictly monotonic | ✖ (opt. ext.) | per-process opt. | ✔ |
| Globally unique | ✔ | ✔ | ✖ (domain-local) |
| Lock/coordination needed | none | none | required |
| §13.7-ready | ✔ | ✔ | ✖ |
| Stdlib path | 3.14+, trivial fallback | none | trivial + state file |
| Text form | 36-char std | 26-char nice | shortest |
| `legacy-` disjoint | by alphabet | by alphabet | by convention |
| Public interoperability | standard (RFC 9562) | community spec | none |

## Recommended option

**O1 — UUIDv7**, canonical lowercase hex-with-dashes text form.

## Why

It is the only candidate that is simultaneously standards-track, globally unique
without coordination, time-sortable, alphabet-disjoint from `legacy-`, and ready
for the concurrency future (§13.7) without redesign. Its one weakness — no strict
monotonicity — is neutralized by the contract itself: `seq` is the authoritative
order, and run-level creation-time sorting at millisecond precision is sufficient
for every operational use named so far. O2 loses only on standardization and
stdlib trajectory; O3 buys strict monotonicity at the price of lock coupling,
domain-local uniqueness and an allocator state file — three future liabilities
for one property nothing currently needs.

## Rejected alternatives

- UUIDv4 (not time-orderable — violates a frozen requirement).
- KSUID (coarser ordering, no stdlib, no material gain).
- O3 sequential (lock-coupled, domain-local uniqueness, allocator state file).
- ULID (strong runner-up; loses on standardization and stdlib trajectory).

## Consequences

- `run_id` values are 36-char opaque strings; events store them verbatim.
- Prefix resolution: any unique prefix accepted by the CLI; ambiguity is a hard
  error (frozen rule) — same-millisecond runs simply require longer prefixes.
- Clock regression cannot corrupt identity, only cosmetic listing order.
- `legacy-<operation>` remains trivially distinguishable forever.

## Open implementation details (Phase 2, after approval)

- Pre-3.14 generation: vendored ~20-line RFC 9562 method vs small dependency.
- Whether to enable an RFC 9562 monotonicity counter inside the `--go` critical
  section (harmless; not required).
- Display truncation length used by `status` output (pure presentation).

## Human gate — outcome

**APPROVED (2026-08-23).** The recommendation (O1 — UUIDv7) was accepted as
proposed. This ADR is the recorded architectural decision for §13.2; Phase 2
implementation is authorized against it.
