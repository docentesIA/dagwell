# DAGWELL

DAGWELL is a public, provider-agnostic orchestration engine that executes agent
work as a governed graph over an **event-sourced, append-only ledger**. State is
never stored — it is a deterministic fold of events. Verification and human
gates are first-class: successful transport alone never completes anything
(`executed != completed`); completion is
`successful transport + required output evidence + required approvals`.

**Status: the governed core is implemented, the Adapter/Output Evidence
Specification v1.0 is promoted, and the first adapter exists** — the
`subprocess` transport with a capability worker (`dagwell work`). Nothing spends
by itself: `work` without `--go` is a plan, and `--go` is the operator
explicitly spending their own quota. The normative behavior is fully specified
before implementation, and the code grows in gated, incremental phases.

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
python3 tools/run_tests.py          # 146 cases, zero cost, no network
```

Then see the whole thing work, with nothing to set up:

```bash
dagwell demo
```

## What it does today, and what it does not

**One adapter exists: `subprocess`.** A node declares a difficulty tier and a
mission; a binding registry (your data, not this repo) declares which CLIs and
models serve which tiers at what relative cost; `dagwell work --go` probes,
selects the cheapest model that satisfies the tier — difficulty dictates the
model, a simple task never burns a frontier model — executes, and records the
evidence of what actually landed on disk. Remote transports, automatic
verification execution, and any retry/budget model remain ahead, each behind
its own gate.

The inverse model is still first-class, and still the part worth
understanding: **you do the work, DAGWELL governs it.** You (a script, a human, an agent, a CI job) execute
the step by whatever means you already use; the engine decides whether it was
allowed to start, records what came back, refuses a completion that lacks evidence
or approval, and can reconstruct the whole state from events alone.

| Available now | Not yet |
|---|---|
| Declare a graph; fail-closed validation before any spend | Remote transports (http, sdk, mcp, a2a) |
| Start a run with a frozen graph identity | Retry policy or budget model |
| Dispatch to local CLIs by difficulty tier (`dagwell work --go`) | Automatic verification execution |
| Record dispatch and return; refuse malformed evidence at the boundary | Session persistence per platform |
| Request verifications in contract order; record machine verdicts | |
| Human gates: approve, reject, retry, escalate, cancel | |
| Land a run; resume after interruption; detect orphans | |
| Deterministic state via `fold`; tamper-proof checkpoint | |

The CLI drives the whole cycle — `start`, `ready`, `dispatch`, `return`,
`request-verification`, `verdict`, `decide`, `human-retry`, `land`, `resume`,
`cancel`, `status` — so you never need to write Python to use it. The same
operations are available as a library. **[Full manual: docs/USAGE.md](docs/USAGE.md)**
([em português](docs/USAGE.pt-BR.md)).

## Field report: one engine, three worlds

On its first day of real production use the engine governed the same kind of work
in three territories: a hive of always-on agents behind a message relay (dispatch
by @mention, replies turned into hashed evidence), the local headless CLIs of one
machine (a binding registry with tiers, probes and relative costs), and an
autonomous resident agent that both received dispatches *inside its own home* and
drove its own governed runs there — no sudo, no crossed boundaries.

That day also produced the engine's best argument for itself: an agent exited `0`
having delivered nothing, and the ledger recorded `failed — evidence none`
instead of a false green — which is how a real headless permission bug got
caught. **[Full field report: docs/THREE-WORLDS.md](docs/THREE-WORLDS.md)**
([em português](docs/TRES-MUNDOS.pt-BR.md)).

## Quickstart

```python
import json
from pathlib import Path

from dagwell import human, operations, runtime
from dagwell.canonical import json_digest
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

manifest = [{"path": "report.md", "artifact_digest": "sha256:" + "ab" * 32,
             "size_bytes": 2}]
operations.record_return(
    ledger, graph, run_id, "write-report", attempt=1, exit_code=0,
    output_evidence={"type": "artifact", "evidence_id": json_digest(manifest),
                     "output_manifest": manifest})

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
| **How to use it, command by command** | **[docs/USAGE.md](docs/USAGE.md)** |
| Example graph definitions | [examples/](examples/) |
| Shipped schemas (shape aid — the validator is authoritative) | [src/dagwell/schemas/](src/dagwell/schemas/) |
| Contract integrity check | `python3 tools/check_contracts.py` |
| Zero-cost test suite | `python3 tools/run_tests.py` |

Note: the Execution Contract's prose is Portuguese by design; all canonical
protocol identifiers — event types, fields, enums, states — are English
(contract amendment H1). Localized documentation is informational only; the
English/canonical originals govern.

## The name

**Maxwell's demon**, and the reason it fails.

The demon is a thought experiment: an agent that watches molecules, uses
**information** to sort the fast ones from the slow, and lowers the entropy of a gas
— paying an energy cost per bit acquired (Landauer). It is not a metaphor picked for
sound. It is the same formal problem, with the same quantities:

| Maxwell's demon | An agent orchestrator |
|---|---|
| watches molecules | watches the state of the task |
| uses information to sort fast from slow | uses information to route to the right agent |
| lowers the entropy of the gas | lowers the uncertainty about the artifact |
| pays energy per bit (Landauer) | pays tokens per bit of uncertainty removed |
| the limit is thermodynamic | the limit is the budget |

And the demon's lesson is the whole point: **the demon only works if it actually
measures.** A demon that sorts molecules without observing them lowers no entropy at
all — it just burns energy.

That is `executed != completed`, stated in physics a century before anyone dispatched
an agent. A step that ran, exited zero and was never verified is a demon that sorted
without looking: tokens spent, uncertainty unchanged. The whole protocol exists to
refuse calling that finished.

The predecessor was called **Maxwell**. This engine keeps the `well` and replaces
`MAX` with **DAG** — the directed acyclic graph that became the structure the whole
thing is built on. The demon stayed; what changed is that its work is now a graph,
and what it measures is written down where anyone can check.

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
- **The suite reports 146 cases across 13 files, 47 of them adversarial** (the
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
