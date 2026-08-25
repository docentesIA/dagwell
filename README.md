# DAGWELL

DAGWELL is a public, provider-agnostic orchestration engine that executes agent
work as a governed graph over an **event-sourced, append-only ledger**. State is
never stored — it is a deterministic fold of events. Verification and human
gates are first-class: successful transport alone never completes anything
(`executed != completed`); completion is
`successful transport + required output evidence + required approvals`.

**Status: the governed core (the contract's six incremental steps) is
implemented; no adapters yet.** Nothing here dispatches real work or spends —
transports belong to the Adapter Transport & Capability Model milestone, still
ahead. The normative behavior is fully specified before implementation, and the
code grows in gated, incremental phases.

## Install

Requires Python 3.11+. No runtime dependencies — the engine is stdlib only.

```bash
pipx install git+https://github.com/docentesIA/dagwell.git
```

That puts the `dagwell` command on your PATH with no virtualenv to activate. If
you prefer a checkout (to run the suite, read the contract, or hack on it):

```bash
git clone https://github.com/docentesIA/dagwell.git && cd dagwell
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
python3 tools/check_contracts.py    # the promoted contract still hashes as promoted
python3 tools/run_tests.py          # 142 cases, zero cost, no network
```

The suite prints refusal messages and a sample event as it runs (`refused: unknown
run: …`). That is the output of tests asserting that refusals happen — not errors.
The last line is the verdict.

## What it does today, and what it does not

**There are no adapters.** Nothing here dispatches work to a provider, launches a
process, or spends anything. That is the Adapter Transport & Capability Model
milestone, still ahead.

What that leaves is not nothing, and it is the part worth understanding: **you do
the work, DAGWELL governs it.** You (a script, a human, an agent, a CI job) execute
the step by whatever means you already use; the engine decides whether it was
allowed to start, records what came back, refuses a completion that lacks evidence
or approval, and can reconstruct the whole state from events alone.

| Available now | Not yet |
|---|---|
| Declare a graph; fail-closed validation before any spend | Dispatching work to a provider |
| Start a run with a frozen graph identity | Any transport, retry policy or budget model |
| Record dispatch and return; refuse malformed evidence at the boundary | Automatic verification execution |
| Request verifications in contract order; record machine verdicts | Liveness/timeout per transport |
| Human gates: approve, reject, retry, escalate, cancel | |
| Land a run; resume after interruption; detect orphans | |
| Deterministic state via `fold`; tamper-proof checkpoint | |

The CLI exposes the human side (`dagwell status | decide | human-retry | cancel`),
because that is the part a person drives from a terminal. The rest is the library
API shown below — a governed boundary, not raw ledger writes.

## Quickstart

```python
import json
from pathlib import Path

from dagwell import human, operations, runtime
from dagwell.fold import fold
from dagwell.ledger import Ledger

GRAPH = json.dumps({"graph_id": "hello", "nodes": [
    {"id": "write-report", "deps": [], "output_evidence": "artifact",
     "verifications": [{"verification_id": "review", "family": "human"}]}]})

Path("graph.json").write_text(GRAPH)          # the graph is a file you keep
ledger = Ledger("run.jsonl")
graph, founding = runtime.start_run(ledger, graph_text=GRAPH,
                                    input_text="the task", input_ref="local://task")
run_id = founding["run_id"]
print("run:", run_id)

operations.dispatch(ledger, graph, run_id, "write-report")

# ---- you, your script, or an agent does the actual work here ----

operations.record_return(
    ledger, graph, run_id, "write-report", attempt=1, exit_code=0,
    output_evidence={"type": "artifact", "evidence_id": "sha256:" + "ab" * 32,
                     "output_manifest": [{"name": "report.md",
                                          "artifact_digest": "sha256:" + "ab" * 32}]})

print(fold(graph, ledger.run(run_id), run_id)["nodes"]["write-report"]["state"])
# executed   <- transport succeeded AND evidence is present. Still not completed.

operations.request_verification(ledger, graph, run_id, "write-report",
                                verification_id="review")
human.decide(ledger, graph, run_id, "write-report", "approved", actor="you")

print(fold(graph, ledger.run(run_id), run_id)["nodes"]["write-report"]["state"])
# completed  <- only now.
```

`run.jsonl` now holds every event, and `graphs/` the frozen graph. Delete nothing:
the ledger is append-only and the state is a fold of it. Inspect the run with:

```bash
dagwell status --ledger run.jsonl --graph graph.json --run <the run id printed above>
```

## Where things are

| What | Where |
|---|---|
| Agent instructions (canonical, tool-agnostic) | [AGENTS.md](AGENTS.md) |
| Normative contract (supreme) | [docs/contracts/DAGWELL-EXECUTION-CONTRACT-v1.0.md](docs/contracts/DAGWELL-EXECUTION-CONTRACT-v1.0.md) |
| Promoted-document manifest | [docs/contracts/MANIFEST.sha256](docs/contracts/MANIFEST.sha256) |
| Architecture & Migration Plan | [docs/architecture/](docs/architecture/) |
| Decision records (ADRs) | [docs/decisions/](docs/decisions/) |
| Example graph definitions | [examples/](examples/) |
| Shipped schemas (shape aid — the validator is authoritative) | [src/dagwell/schemas/](src/dagwell/schemas/) |
| Contract integrity check | `python3 tools/check_contracts.py` |
| Zero-cost test suite | `python3 tools/run_tests.py` |

Note: the Execution Contract's prose is Portuguese by design; all canonical
protocol identifiers — event types, fields, enums, states — are English
(contract amendment H1). Localized documentation is informational only; the
English/canonical originals govern.

## How this was built, and how it was checked

This code was written by AI agents under a human gate, and the commit trailers say
so. That is stated here rather than left to be discovered, because a project about
governing agent work has no business being vague about how it was produced.

What makes it checkable is not who typed it:

- The **normative contract came first**. `docs/contracts/` holds a promoted document
  pinned by SHA-256 and verified on every push; the implementation follows its
  incremental order and never edits it in place.
- **Two independent audits**, by models from different families than the one that
  wrote the core — the project's own rule that a verifier must not share the
  producer's family. Both returned REWORK REQUIRED.
- **Every finding was reproduced** in the interpreter before being acted on. Two
  claims did not survive reproduction and were discarded — one from each auditor.
- **The suite reports 142 cases across 12 files, 47 of them adversarial** (the
  T1-T22 matrix plus the hardening coverage), each written to fail if a specific
  hole reopens. Stdlib only, no network, no quota: `python3 tools/run_tests.py`
  prints the same counts for anyone who runs it.
- **The findings that were NOT fixed are written into the commit messages**, not
  omitted. Two remain open and are tracked as issues.

None of that makes the code correct. It makes the claims about it checkable, which
is the most any repository can honestly offer.

## License

Copyright 2026 Reinaldo Elias.

Licensed under the Apache License, Version 2.0 — see [LICENSE](LICENSE) and
[NOTICE](NOTICE).
