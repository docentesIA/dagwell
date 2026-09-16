# Examples

Synthetic graph definitions, validated by the zero-cost suite against the
authoritative validator (`dagwell.graph.load_graph`) and checked for parity
with the shipped schema in `src/dagwell/schemas/`.

| File | Shows |
|---|---|
| `graph-canonical.json` | the three declaration duties of every node: a declared `output_evidence` type (I28), a declared obligatory verification set — or an explicit signed vacuum `no_verification: <reason>` (I5) — and a `family` per verification, machines before the human gate (§4) |
| `graph-with-commands.json` | nodes pinned to an exact command through the `x_command` operator convention, executed by `runner.sh` |
| `template-report/` | the copyable flow for `dagwell doctor` → `start` → `advance --go`: a synthetic dataset, a report, two declared verifiers (`x_verifier`), one human gate; no model, no network, no personal path |

A graph definition is **data**, addressed by the content digest
`graph_version` (scheme c1). These files are examples of the format, not
product configuration: real graphs live in the private data area, never in
this repository.
