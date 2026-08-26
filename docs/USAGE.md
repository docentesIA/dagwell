# DAGWELL — Usage

How to drive DAGWELL after installing it. For what the project *is*, read the
[README](../README.md); for what it *guarantees*, the
[Execution Contract](contracts/DAGWELL-EXECUTION-CONTRACT-v1.0.md) governs.

## 1. Install

Python 3.11+. No runtime dependencies.

```bash
pipx install git+https://github.com/docentesIA/dagwell.git
dagwell --version
```

`pipx` puts `dagwell` on your PATH and there is no virtualenv to activate. If you
want the test suite and the contract too, clone instead:

```bash
git clone https://github.com/docentesIA/dagwell.git && cd dagwell
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
python3 tools/run_tests.py
```

With a clone, `.venv/bin/dagwell` works without activating anything.

## 2. The mental model

**You do the work. DAGWELL governs it.**

There are no adapters yet: DAGWELL never launches a process, calls a provider or
spends anything. You run each step however you already do — a script, a CLI, an
agent, a person — and DAGWELL decides whether it was allowed to start, records what
came back, and refuses to call anything finished without the evidence and the
approvals the graph demands.

The one rule worth internalising:

```
executed != completed
completed = successful transport + required output evidence + required approvals
```

A step that exits 0 and produces its output is `executed`. It is **not** done. It
becomes `completed` only after its declared verifications conclude.

State is never stored. Every projection you see is recomputed from the event log.

## 3. Sixty-second tour

```bash
dagwell demo
```

Runs the full cycle in a throwaway directory and narrates it. Nothing is written
outside the temp dir and nothing is spent.

## 4. A real run, step by step

### 4.1 Declare the graph

A graph is a JSON file you keep. Each node declares its dependencies, the **type of
evidence** it will produce, and the **verifications** it must pass.

```json
{
  "graph_id": "release",
  "nodes": [
    {"id": "build", "deps": [], "output_evidence": "artifact",
     "verifications": [{"verification_id": "tests", "family": "deterministic"}]},
    {"id": "ship", "deps": ["build"], "output_evidence": "artifact",
     "verifications": [{"verification_id": "signoff", "family": "human"}]}
  ]
}
```

Rules the loader enforces before anything can run:

- Every node declares `output_evidence`: `artifact`, `structured_value`,
  `remote_receipt` or `side_effect_receipt`. Omitting it is a hard error.
- Every node declares verifications, **or** waives them with an explicit
  `"no_verification": "<reason>"`. A waiver is only available for `artifact`,
  the one type the engine can validate on its own (see ADR-0008).
- Two consecutive verifications of the same family need
  `"r1_exception": "<reason>"` — a verifier from the producer's own family is
  worth little, and saying so out loud is the price of doing it anyway.
- Node ids unique, dependencies exist, graph acyclic.

### 4.2 Start the run

```bash
echo "cut release 1.4" > input.txt
RUN=$(dagwell start --ledger run.jsonl --graph graph.json --input input.txt)
echo $RUN
```

`start` validates the graph fail-closed **before** creating anything, freezes the
graph by content hash, and prints the run id. The identity comes from content, never
from paths — moving the files later does not change the run.

### 4.3 See what is dispatchable

```bash
dagwell ready --ledger run.jsonl --graph graph.json --run $RUN
# build (next attempt 1)
```

`ship` is absent: its dependency is not satisfied yet.

### 4.4 Hand out the work, then do it

```bash
dagwell dispatch --ledger run.jsonl --graph graph.json --run $RUN --node build
```

This records that `build` was handed out. **It does not run anything.** Now go run
it — `make build`, an agent, whatever the node means in your world.

### 4.5 Record what came back

```bash
dagwell return --ledger run.jsonl --graph graph.json --run $RUN \
  --node build --attempt 1 --exit-code 0 \
  --evidence '{"type":"artifact","evidence_id":"sha256:...","output_manifest":[{"name":"app.bin","artifact_digest":"sha256:..."}]}'
```

`--evidence` takes inline JSON or `@path/to/evidence.json`. Malformed evidence is
refused **before** it reaches the ledger; evidence of the wrong type for what the
node declared is refused too.

Check the state:

```bash
dagwell status --ledger run.jsonl --graph graph.json --run $RUN
# build: executed
```

Exit code 0 and evidence present — and still not completed. That is the point.

If the step **failed**, record that honestly: `--exit-code 1`, no `--evidence`. An
absent evidence is legal and lands the attempt as `failed`. Lying is what gets
refused, not failing.

### 4.6 Verify

```bash
dagwell request-verification --ledger run.jsonl --graph graph.json --run $RUN \
  --node build --verification tests

# run your tests, then record the outcome
dagwell verdict --ledger run.jsonl --graph graph.json --run $RUN \
  --node build --verification tests --status completed --verdict approved
```

Two axes, and they are not the same question:

- `--status` is what happened to the **verification process**: `completed`,
  `error`, `timeout`, `cancelled`.
- `--verdict` is the **answer**: `approved` or `rejected`. It exists only when the
  status is `completed`.

"Could not verify" is not "rejected". A verifier that crashed produces
`--status error` and no verdict, and the node does not advance on it.

Verifications run in the order the contract requires: machine families first, the
human gate last. Requesting one out of order is refused.

### 4.7 The human gate

```bash
dagwell decide --ledger run.jsonl --graph graph.json --run $RUN \
  --node ship approved --actor rey
```

`decide` is the **only** way a human verdict enters the ledger. The machine surface
(`verdict`) refuses `family: human`, and so does raw storage. A rejection requires a
reason:

```bash
dagwell decide ... --node ship rejected --reason "signature missing"
```

After a rejection the node does not run again on its own. Reopening is a human act:

```bash
dagwell human-retry --ledger run.jsonl --graph graph.json --run $RUN --node ship --actor rey
```

That opens attempt *k+1*. Previous attempts are never rewritten — they stay in the
ledger as what happened.

### 4.8 Ending the run

A run ends in one of three ways:

```bash
# everything completed: nothing to do, the projection says completed

# work remains but you are stopping: land it (WIP is saved, never truncated)
dagwell land --ledger run.jsonl --graph graph.json --run $RUN --reason budget_exhausted

# abandon it (absorbing terminal; a completed run can never become cancelled)
dagwell cancel --ledger run.jsonl --graph graph.json --run $RUN --actor rey
```

`land` refuses while there is dispatchable work, work in flight, a pending gate, or
a node that still owes its verification. `--reason human_rejection` and
`--reason retries_exhausted` must be supported by what the projection actually
shows; `budget_exhausted` is asserted by you, because the engine owns no budget
model (§13.12 is open).

### 4.9 After an interruption

```bash
dagwell resume --ledger run.jsonl --graph graph.json --run $RUN --input input.txt
```

Resume continues **the same run**, validating that the graph and input still match
the identity frozen at `start`. A different graph is refused rather than silently
accepted. The frozen graph snapshot is stored beside the ledger, so resume works
even if you lost the original file.

## 5. Binding it to real CLIs

This is the question everyone asks after installing: **how does DAGWELL call claude,
codex, grok?**

It does not. That is not an omission in this manual — it is the state of the project.
Adapters are the next milestone. What exists today is the inverse model, and it is
already useful:

> **You call the CLI. DAGWELL decides whether you could, records what came back, and
> refuses to call finished anything that has no proof.**

It is the same shape as a dispatch script: your script executes, the ledger governs.
The difference is that here the governance is the product, not a side effect.

### 5.1 Declare the command in the graph itself

The engine **ignores fields it does not know**, which is useful: a node can carry the
command that executes it. By convention, prefix them with `x_`:

```json
{
  "id": "script",
  "deps": [],
  "output_evidence": "artifact",
  "verifications": [{"verification_id": "has-sources", "family": "deterministic"}],
  "x_harness": "claude",
  "x_command": "claude -p \"Write the script from briefing.md. Write it to $OUT.\""
}
```

Those fields go into the graph hash — **changing the command changes the run's
identity**, which is correct: it is different work. Full example in
[`examples/graph-with-commands.json`](../examples/graph-with-commands.json).

### 5.2 The loop

[`examples/runner.sh`](../examples/runner.sh) is the whole loop in ~110 lines of
shell, meant to be copied and adapted:

```bash
./examples/runner.sh run.jsonl graph.json "$RUN" out
```

What it does, and why each step matters:

1. `dagwell ready` — asks what the topology released. It never decides that itself.
2. `dagwell dispatch` — records that the node **was handed out**, before anything
   happens. If the machine dies here, the ledger knows work was in flight.
3. Runs `x_command` **in a subshell**, with `$OUT` exported, pointing at the file
   that node must produce.
4. `dagwell return` — records the exit code and the **digest of what was actually
   written**. Not what the command claimed: what is on disk.
5. Machine verifications, in contract order, each with its verdict.
6. Human gate: the loop **opens** the verification and **stops**. Opening is not
   deciding.

### 5.3 The case that justifies all of it

```bash
x_command: "echo 'done, file generated' && exit 0"
```

The command claims the work is done and exits zero. No file appears.

```
-> gera (attempt 1)
   exit 0, no usable output -> recording the failure
   gera is now: failed
```

**`failed`.** Not `completed`. That is the expensive failure mode of any agent
orchestration — the agent reporting success without producing — and it is caught by
evidence, not by trust. An orchestrator that only checks exit codes would have
recorded success.

### 5.4 Headless invocations

An interactive agent hangs waiting for a terminal. These are the verified
non-interactive forms:

| CLI | Invocation |
|---|---|
| claude | `claude -p "<mission>"` |
| codex | `codex exec --sandbox workspace-write "<mission>"` |
| grok | `grok -p "<mission>" --output-format plain --always-approve --max-turns 25` |
| shell/make | any command; `$OUT` is the contract |

For the others, check each one's `--help` for its headless flag before putting it in
a graph — the pattern is always the same: non-interactive mode, mission as argument,
and the file at `$OUT` as the proof.

### 5.5 Cost

DAGWELL spends nothing. **Your `x_command` spends.** Every dispatched node is a paid
call or a consumed quota, and the engine owns no budget model — §13.12 is open and no
formula was invented.

In practice:

- Run `dagwell ready` before the runner to see **how many** nodes will fire.
- A 10-node graph is 10 calls, and a retry is one more.
- `dagwell land --reason budget_exhausted` exists precisely to stop without
  truncating work: what was in flight stays recorded, and `resume` picks it up.

### 5.6 Where this fits

The pattern holds for any pipeline where steps depend on each other and someone must
approve before the result ships:

| Pipeline | Typical nodes |
|---|---|
| Video | script → composition → render → human approval |
| Website | research → copy → build → deterministic checker → gate |
| Animation | storyboard → keyframes → render → review |

In all of them the gain is the same: **a node does not advance because the command
said it worked, but because the evidence is there and the verification passed.** What
changes between them is only the `x_command`.

## 6. Command reference

| Command | What it does |
|---|---|
| `demo` | full cycle in a temp dir, narrated. No ledger needed |
| `start` | validate the graph, freeze its identity, create the run. Prints the run id |
| `ready` | nodes the topology has unblocked |
| `status` | the projection: run state, every node, anomalies |
| `dispatch` | record that a node was handed out (**does not run it**) |
| `return` | record the transport return and, when produced, the evidence |
| `request-verification` | open the verification the order requires next |
| `verdict` | record a NON-human verdict |
| `decide` | record the human verdict (the only path for `family: human`) |
| `human-retry` | open producer attempt *k+1* after a rejection or failure |
| `land` | end the run with work still pending, WIP preserved |
| `cancel` | cancel the run (absorbing terminal) |
| `resume` | continue the same run after an interruption |

Every command except `demo` and `start` takes `--ledger`, `--graph` and `--run`.

## 7. Reading a status

Node states:

| State | Meaning |
|---|---|
| `pending` | dependencies not satisfied |
| `ready` | dispatchable now |
| `running` | handed out, nothing back yet |
| `executed` | returned successfully with its evidence — **not done** |
| `verifying` | a machine verification is open |
| `waiting_human` | waiting on a human gate |
| `completed` | transport + evidence + approvals, all present |
| `failed` | the machine did not accept it: bad transport, missing evidence, orphan |
| `rejected` | a human rejected it |
| `cancelled` | the run was cancelled |

Run states: `created`, `running`, `stalled` (nothing in flight and no pending gate),
`waiting_human`, `completed`, `landed`, `cancelled`.

A line starting with `!` is an **anomaly**: something in the ledger that the fold
made inert rather than obeyed — a verdict with no request, a duplicate founder, an
event in a schema this version does not interpret. Anomalies are never deleted; the
ledger keeps mistakes as historical data.

`(integrity: degraded)` means the fold cannot vouch for this run's identity — a gap
in `seq`, or no authoritative `run_created`. The run stays **readable** but every
mutation is refused until a human reconciles it.

## 8. When something is refused

Refusals are the product working, not failing. They print as `refused: <reason>`
and exit nonzero. The common ones:

| Refusal | What it means |
|---|---|
| `node X is pending — dispatch requires the ready derived state` | a `deps` entry is not completed yet |
| `node X is running — dispatch requires the ready derived state` | that node already has an open attempt |
| `node X is executed, not waiting_human — nothing to decide` | you are deciding a gate that is not open |
| `unresolved seq gap` | the ledger has a hole; mutation is blocked until reconciled |
| `evidence type ... does not match the node's declaration` | the node declared another type |
| `verification is still owed` | landing over a node whose verification never ran |
| `run is cancelled` / `run is completed` | terminal states are terminal |

Nothing here can be forced with a flag. If a refusal is wrong, the graph or the
ledger is wrong — fix that, not the guard.

## 9. What lands on disk

| Path | What |
|---|---|
| `run.jsonl` | the ledger: every event, append-only, one JSON object per line |
| `graphs/` | frozen graph snapshots, addressed by content hash |

Never edit or delete either. State is a deterministic fold of the ledger: remove a
line and you have changed history, not fixed it. The checkpoint is always recomputed
from events, so tampering with a cache changes nothing except the tamper evidence.

Both paths are yours — commit them, back them up, or keep them private, as the work
demands.

## 10. Using the library instead

Everything above is available as a Python API, and some things only exist there
(`observe_orphans`, `advance_verifications`, `extend_budget`). The README's
quickstart is the shortest complete example; the modules are `dagwell.runtime`,
`dagwell.operations`, `dagwell.human` and `dagwell.fold`.

Do not write to the ledger directly. `Ledger.append` is storage, not a protocol
surface: it refuses human verdicts outright, and the preconditions that make the
other operations safe live in the governed layer above it.
