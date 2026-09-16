# DAGWELL 0.0.3 — the pilot layer

Status: **0.0.3, promoted from the reviewed candidate; tagged `v0.0.3`
locally.** Push and any GitHub release remain behind the explicit human
publication gate (AGENTS.md §11).

Built on 0.0.2 (`v0.0.2`) plus the adaptive-routing design notes (`1d64f61`)
and ADR-0011 (`05a79f4`). The
governed core, the contracts and the promoted specifications are unchanged;
`tools/check_contracts.py` verifies the three promoted documents byte for byte.
The candidate's own notes, its review and its pre-commit rollback are kept as
written in [RELEASE-0.0.3rc1.md](RELEASE-0.0.3rc1.md); version numbering follows
[ADR-0012](decisions/ADR-0012-public-version-numbering.md).

## What 0.0.3 adds

One operational path a person can follow without rebuilding commands:

```
dagwell doctor → dagwell start → dagwell advance (plan) → dagwell advance --go
     → stops at the human gate → dagwell decide → dagwell advance --go → completed
```

- **`dagwell doctor`** — read-only diagnosis of a configuration: graph and
  registry loaded fail-closed, binding executables found on `PATH`, zero-cost
  probes run, every tier the graph needs served by an available binding, every
  declared verifier parsed and its executable/script found, data directory
  checked. `FAIL:` lines are actionable; no environment *value* is ever
  printed; what a probe cannot prove (authentication, quota, model capability)
  is said out loud.
- **Declared verifiers** — a verification entry may carry `x_verifier` (an
  argv template, no shell; `{graph_dir}` expands to the graph file's
  directory) and the mandatory `x_verifier_timeout_seconds`. The core ignores
  both fields (they enter `graph_version` like any other byte, so the
  verifier's identity is frozen with the run). The pilot runs the verifier with
  `$OUT` set to the evidence file, in the producer's attempt directory, and
  records its structured decision — one JSON object on stdout,
  `{"verdict": "approved"|"rejected", "reasons": [...]}` — through the machine
  verdict surface. **Exit code is never a verdict** (I6): nonzero →
  `verification_status: error`, expiry → `timeout`, exit 0 without a valid
  object → `error`; none carries a verdict (I7), and the next iteration
  escalates to the human (`human_escalation`). Before a verifier runs, the
  evidence on disk must still hash to the `artifact_digest` recorded at
  return; otherwise nothing runs and nothing is recorded (`inconsistent`).
  Each verifier run leaves `result.json`, `log.txt` and `exit` under
  `<data-dir>/verifications/<operation>/<run>/<node>/<verification>/t<k>-v<j>/`.
- **`dagwell advance`** — without `--go`: a plan (no run, no event, no
  directory, no verifier subprocess; only the bindings' zero-cost probes).
  With `--go`: one pilot (the existing per-run lock) executes READY capability
  nodes through the worker, runs declared verifiers in contract order
  (machines first, human gate last), opens the human gate, escalates verifier
  failures, and stops as soon as an iteration writes nothing. Every stop is
  named: gate open, failed producer, rejecting verifier, verifier
  error/timeout, inconsistent evidence, manual verification, external-runner
  node, unservable tier, verification in flight. Repeating the command
  duplicates nothing. `Ctrl+C` once: no new dispatch starts (not even a ready
  sibling in the same step), the node in flight finishes and is recorded,
  `run_interrupt_requested` is written, the command stops; the next
  `advance --go` continues the same run and attempt directories. A second
  `Ctrl+C` aborts hard and leaves the current work in flight.
- **`dagwell status`** ends with `next:` lines — what blocks and the next
  valid command (`decide`, `human-retry`, `advance --go`, external runner,
  in-flight notice). Read-only, no authority.
- **`examples/template-report/`** — the copyable flow: a synthetic dataset, a
  report, two declared verifiers, one human gate. No model, no network, no
  personal path. The zero-cost suite runs it end to end through the real CLI.

## How to use it

Full manual: [USAGE.md §5.7–5.8](USAGE.md) ([pt-BR](USAGE.pt-BR.md)); copyable
flow with every command and every provoked failure:
[examples/template-report/README.md](../examples/template-report/README.md).

```bash
cp -r examples/template-report /tmp/demo && cd /tmp/demo
dagwell doctor  --graph graph.json --registry registry.json --data-dir data
RUN=$(dagwell start --ledger run.jsonl --graph graph.json --input input.txt)
dagwell advance --ledger run.jsonl --graph graph.json --run $RUN \
                --registry registry.json --data-dir data          # plan only
dagwell advance --ledger run.jsonl --graph graph.json --run $RUN \
                --registry registry.json --data-dir data --go     # stops at the gate
dagwell status  --ledger run.jsonl --graph graph.json --run $RUN
dagwell decide  --ledger run.jsonl --graph graph.json --run $RUN \
                --node report approved --actor "$USER"
dagwell advance --ledger run.jsonl --graph graph.json --run $RUN \
                --registry registry.json --data-dir data --go     # completed
```

Declaring a verifier in your own graph:

```json
{"verification_id": "csv-shape", "family": "deterministic",
 "x_verifier": "python3 {graph_dir}/check_dataset.py",
 "x_verifier_timeout_seconds": 30}
```

## Compatibility and limits

- Every 0.0.2 command, flag and output line is preserved; `status` prints
  additional `next:` lines after the projection and anomalies. 0.0.2 reads the
  ledgers 0.0.3 writes: every event the pilot records is an existing event
  type through the existing operations. No new event type, no field read by
  the fold, no open question resolved.
- Graphs without `x_verifier` behave exactly as before; `advance` stops at
  each verification and prints the manual step.
- `x_verifier` without `x_verifier_timeout_seconds`, or a malformed template,
  is refused by `advance`/`doctor` before anything runs — the graph itself
  still loads (the core does not validate operator fields).
- Orphan constatation is not provided by the CLI (§13.4 open): a producer
  attempt or a verification left in flight by an abrupt loss still needs the
  library's `runtime.resume(..., still_in_progress=...)`.
- No retry/budget policy (§13.12 open): `failed` waits for `human-retry`; a
  verifier that did not conclude waits for `decide` or `human-retry` after
  `human_escalation`. Automatic re-fire is off.
- A producer receives only `$OUT`; a dependency's output is located by the
  attempt-directory convention (`../../<node>/t<k>/out`). Injecting dependency
  outputs into the producer's environment is backlog.
- `doctor` does not verify authentication with a real provider; the first
  `--go` against a real binding is that test, and it spends.
- The pilot's machine verdicts carry `actor = --actor` (default: the local
  user), the family the graph declared, and a `reason` citing the
  `result.json` sha256. Strong actor identity remains §13.8.
- A disk failure between `verification_requested` and the verifier's outcome
  leaves that request in flight — the same shape as a verifier crash,
  observed by `resume`, never papered over.

## Verification

Zero cost, no network, no model:

```bash
python3 tools/check_contracts.py     # 3/3 PASS — promoted documents byte-identical
python3 -m compileall -q src tests
python3 tools/run_tests.py           # 23 files, ALL PASS (tests/test_pilot.py: 14)
```

`tests/test_pilot.py` covers, in the order of the candidate's acceptance
criteria: `doctor` reports actionable failures without secrets; a plan writes
no event, creates no directory and runs no verifier; `advance --go` walks
dependencies and produces hashed artifacts; exit 0 is not a verdict, rejection
lands `failed`, verifier error/timeout/garbage escalates and never rejects;
tampered evidence stops without a verdict; the human gate opens and stops, a
test actor continues it; repeating the command duplicates nothing; retry
preserves attempt 1; graceful interruption records intent and the command
resumes; no sibling dispatch after an interrupt; a second pilot is refused;
the shipped template runs through the real CLI; `--node` exits 0 on success.
Secrets scan (gitleaks) clean on every commit of this line.

## Rollback

History is append-only (AGENTS.md §11). `main` contains the candidate
(`eeb73a3`) and the promotion commit tagged `v0.0.3`. To go back:

- **Run 0.0.2 side by side** (for a comparison or a review):
  `git worktree add ../dagwell-0.0.2 v0.0.2`, then
  `PYTHONPATH=../dagwell-0.0.2/src python3 -m dagwell.cli --version` →
  `dagwell 0.0.2`. Remove with `git worktree remove ../dagwell-0.0.2`.
- **Revert on `main`**: `git revert <promotion> eeb73a3` (newest
  first; the promotion hash is the commit `v0.0.3` points at:
  `git rev-list -n1 v0.0.3`). Each revert is a new commit; nothing is rewritten.
- **Install the previous version** without touching a checkout:
  `pipx install --force git+https://github.com/docentesIA/dagwell.git@v0.0.2`
  (a fresh, non-editable, pinned install — replaces any editable install).

Data the pilot wrote lives only under the operator's `--data-dir` (`runs/`,
`verifications/`) and in the ledger; rolling the code back never touches
them, and 0.0.2 projects the same states from the same ledgers.

## Backlog (outside this release)

Dependency-output injection for producers; CLI orphan constatation (needs the
§13.4 specification); retry/budget policy (§13.12); `model:*` verifier registry
and cost reporting; remote transports; learned routing (activation criteria
first); dashboards and integrations.

## Relato em português

A 0.0.3 acrescenta a camada piloto: `dagwell doctor` (diagnóstico só de
leitura), verificadores declarados no grafo (`x_verifier`, executados como
subprocesso; o veredito vem só do JSON estruturado do verificador — exit code
nunca é veredito), `dagwell advance` (conduz o run até o gate humano e para) e
linhas `next:` no `status`. O núcleo governado, os contratos e as especificações
promovidas não mudaram; nenhum tipo de evento novo; nenhuma questão em aberto
resolvida. Suíte de custo zero: 23 arquivos, todos aprovados. Versão pública
`0.0.3`, tag `v0.0.3` (ADR-0012: `rc` é só controle interno). Push e release no
GitHub continuam atrás do gate humano explícito.
