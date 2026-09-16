# DAGWELL 0.0.3rc1 — operational closure, release candidate

Status: **historical record of the candidate.** Reviewed and committed as `eeb73a3`
on `main`, then promoted to **0.0.3** — see [RELEASE-0.0.3.md](RELEASE-0.0.3.md) for the
public notes and the current rollback. The *Rollback* section below describes the
state **before** that commit (an uncommitted working tree) and is kept as written.
Per [ADR-0012](decisions/ADR-0012-public-version-numbering.md), `rc` numbers are
internal candidate control only; no `v0.0.3rc1` tag exists or will exist.
Built on `05a79f4` (0.0.2 + adaptive-routing design notes + ADR-0011). The
governed core, the contracts and the promoted specifications are unchanged;
`tools/check_contracts.py` still verifies the three promoted documents byte for
byte. Publication (tag, push, release) remains a separate human decision.

## What this candidate adds

One operational path a person can follow without rebuilding commands:

```
dagwell doctor  → dagwell start → dagwell advance (plan) → dagwell advance --go
      → stops at the human gate → dagwell decide → dagwell advance --go → completed
```

- **`dagwell doctor`** — read-only diagnosis of a configuration: graph and
  registry loaded fail-closed, binding executables found, zero-cost probes run,
  every tier the graph needs served by an available binding, every declared
  verifier parsed and its executable/script found, data directory checked.
  `FAIL:` lines are actionable; no environment value is printed; what a probe
  cannot prove (authentication, quota, model capability) is said out loud.
- **Declared verifiers** — a verification entry may carry `x_verifier` (an
  argv template, no shell; `{graph_dir}` for portability) and the mandatory
  `x_verifier_timeout_seconds`. The core ignores the fields (they enter
  `graph_version` like any byte); the pilot runs the verifier with `$OUT` set
  to the evidence file, in the producer's attempt directory, and records its
  structured decision (`{"verdict": ..., "reasons": [...]}` on stdout) through
  the machine verdict surface. Exit code is never a verdict: nonzero →
  `error`, expiry → `timeout`, exit 0 without a valid object → `error`; none
  carries a verdict, and the next `advance --go` escalates to the human. Before
  running, the evidence on disk must still hash to the recorded
  `artifact_digest`, or nothing runs and nothing is recorded.
- **`dagwell advance`** — without `--go`, a plan (no run, no event, no
  directory, no verifier subprocess, no inference; only the bindings' probes).
  With `--go`, one pilot (the existing `work` lock) executes READY capability
  nodes through the worker, runs declared verifiers in contract order, opens
  the human gate, escalates verifier failures, and stops as soon as an
  iteration writes nothing. Stops are explicit and named: gate, failed
  producer, rejecting verifier, verifier error/timeout, inconsistent evidence,
  manual verification, external-runner node, unservable tier, verification in
  flight. Repeating the command duplicates nothing; Ctrl+C once finishes the
  current step, records `run_interrupt_requested` and stops.
- **`dagwell status`** ends with `next:` lines — what blocks and the next
  valid command (`decide`, `human-retry`, `advance --go`, external runner,
  in-flight notice). Read-only.
- **`examples/template-report/`** — the copyable flow: synthetic dataset →
  report → two declared verifiers → one human gate. No model, no network, no
  personal path. The suite runs it end to end through the real CLI.

## Changed files

```
pyproject.toml, src/dagwell/__init__.py            version 0.0.3rc1
src/dagwell/adapters/pilot.py                       NEW: doctor, declared verifiers, advance, next_actions
src/dagwell/cli.py                                  doctor, advance, status next-lines, pilot report
src/dagwell/adapters/worker.py                      pilot_lock public; work(locked=, stop_requested=) — no dispatch after an interrupt
src/dagwell/adapters/transports/subprocess_transport.py   run_argv extracted from execute (same behavior)
src/dagwell/artifacts.py                            verification_dir() layout
tests/test_pilot.py                                 NEW: 14 zero-cost tests (A1–A6, CLI, shipped template, review fixes)
examples/template-report/                           NEW: graph, registry, verifiers, input, README
examples/README.md, README.md, docs/USAGE.md, docs/USAGE.pt-BR.md, docs/RELEASE-0.0.3rc1.md
```

No change to: `docs/contracts/*` (manifest verified), `fold.py`,
`operations.py`, `human.py`, `ledger/*`, `graph.py`, `evidence.py`,
`selection.py`, `registry.py`, schemas. No new event type, no new field read by
the fold, no open question resolved.

## Compatibility and limits

- Every 0.0.2 command, flag and output line is preserved; `status` prints
  additional `next:` lines after the projection and anomalies.
- Graphs without `x_verifier` behave exactly as before; `advance` stops at each
  verification and prints the manual step.
- `x_verifier` without `x_verifier_timeout_seconds` (or a malformed template)
  is refused by `advance`/`doctor` before anything runs — the graph itself
  still loads (the core does not validate operator fields).
- Orphan constatation is not provided by the CLI (§13.4 open): a producer
  attempt or a verification left in flight by an abrupt loss still needs the
  library's `runtime.resume(..., still_in_progress=...)`.
- No retry/budget policy (§13.12 open): `failed` waits for `human-retry`; a
  verifier that did not conclude waits for `decide` or `human-retry` after
  `human_escalation`.
- A producer receives only `$OUT`; a dependency's output is located by the
  attempt-directory convention. Injecting dependency outputs into the
  producer's environment is backlog, not done.
- `doctor` does not verify authentication with a real provider; the first
  `--go` against a real binding is that test, and it spends.
- The pilot's machine verdicts carry `actor = --actor` (default: the local
  user), the family the graph declared, and a `reason` citing the
  `result.json` sha256. Strong actor identity remains §13.8.

## Verification of this candidate

```bash
python3 tools/check_contracts.py     # 3/3 PASS
python3 -m compileall -q src tests
python3 tools/run_tests.py           # 23 files, ALL PASS
```

### Review of the candidate (second pass, same day)

Two concrete defects found reading the diff against the contract; both fixed
with their smallest failing check in `tests/test_pilot.py` (now 14 tests):

- **Interruption in a fan-out step (§10(a)).** The worker dispatched every
  READY node of one step before the pilot consulted the interrupt flag, so a
  Ctrl+C during node `a` still started its ready siblings `b`, `c` — new
  dispatches after the human asked to stop. Now `worker.work` takes
  `stop_requested` and checks it before each dispatch; a sibling left behind is
  reported `not_started` and stays `ready` for the next `advance --go`.
  Check: `test_interrupt_mid_step_starts_no_sibling_dispatch`.
- **`advance --node X --go` exit code.** The closing iteration asked the worker
  for `X` again after it was executed; the worker's honest answer for a node
  that is not ready (`refused`) leaked into the report and made the CLI exit 1
  on a successful step. The loop now calls the producer step only while `X` is
  ready. Check: `--node dataset` leg added to
  `test_cli_doctor_advance_status_and_the_shipped_template`.

Read and left alone: exit code never becomes a verdict (`_run_verifier`);
`inconsistent`, `in_flight`, `manual` and `refused` return before any ledger
write; verifier `error`/`timeout` escalates on the next iteration and stops;
resume never re-executes a `completed` node (attempt directories are
`exist_ok=False`). A disk failure after `verification_requested` and before the
verifier's outcome leaves that request in flight — the same shape as a verifier
crash, observed by `resume`, not papered over.

## Rollback — without touching the working tree

Two facts first:

- The candidate exists only as **uncommitted changes** on top of `05a79f4`
  (10 modified files, 9 new files under `src/dagwell/adapters/pilot.py`,
  `tests/test_pilot.py`, `docs/RELEASE-0.0.3rc1.md`, `examples/template-report/`).
  Nothing is staged, committed, tagged or pushed.
- Where `dagwell` on `PATH` is a **pipx editable install** (`pipx install -e
  <checkout>`, which drops an `__editable__.*.pth` pointing at `<checkout>/src`),
  the command reads this checkout directly. Such an install was **not**
  reconfigured, reinstalled or upgraded by this candidate (its `pipx list`
  metadata keeps whatever version it was installed with). Because the install is
  editable, the installed command already runs the candidate code —
  `dagwell --version` prints `0.0.3rc1` for that reason alone.

Rollback therefore never means `git checkout -- .`, `git stash` or `git clean`:
each of those removes the candidate from the working tree, and the last one
deletes the new files outright. Use one of these instead, all of which keep
the candidate intact:

- **Run 0.0.2 side by side** (recommended for a review or a comparison):
  `git worktree add ../dagwell-0.0.2 v0.0.2` then
  `PYTHONPATH=../dagwell-0.0.2/src python3 -m dagwell.cli --version` →
  `dagwell 0.0.2`. The `dagwell` on `PATH`
  keeps running the candidate; remove the worktree with `git worktree remove`
  when done.
- **Set the candidate aside on a branch** (if the working tree must show 0.0.2):
  `git switch -c wip/0.0.3rc1`, stage the files listed under *Changed files*
  one by one (never a blind `add -A`; secrets scan first), commit as
  `wip: 0.0.3rc1 candidate (not reviewed)`, then `git switch main`. The work is preserved in
  history; the editable install then runs `main` (0.0.2). This creates a
  commit, so it is Reinaldo's decision, not a default.
- **After a reviewed commit `<rc>` on `main`:** `git revert <rc>` — history
  stays append-only; never rewrite it.
- **To make the installed command run 0.0.2 without changing the checkout:**
  `pipx install --force git+https://github.com/docentesIA/dagwell.git@v0.0.2`
  would do it, but that **reconfigures pipx** (non-editable, pinned to the
  tag) and loses the editable link — an explicit decision, not part of this
  candidate.

Data the candidate wrote lives only under the operator's `--data-dir`
(`runs/`, `verifications/`) and in the ledger, and every event the pilot
writes is an existing event type through the existing operations: 0.0.2 reads
the same ledgers and projects the same states. Rolling the code back never
touches them.

## Backlog (frente C — outside this release)

Dependency-output injection for producers; CLI orphan constatation (needs the
§13.4 specification); retry/budget policy (§13.12); `model:*` verifier
registry and cost reporting; remote transports; learned routing (activation
criteria first); dashboards and integrations.
