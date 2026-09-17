# DAGWELL 0.0.4 — reliability review

Status: **released.** 0.0.4 is the commit on `main` that the annotated tag
`v0.0.4` points at. Reaching the public remote is the human gate every release
passes (AGENTS.md §11). `v0.0.3` is untouched and keeps pointing at 0.0.3.

Built on 0.0.3 (`v0.0.3`). Six defects found by an independent review of 0.0.3
were reproduced, fixed and covered by tests. **No new feature**: no adaptive
routing, no new transport, no budget model, no dependency injection. The
governed core, the promoted contracts and the event vocabulary are unchanged —
`tools/check_contracts.py` still verifies the three promoted documents byte for
byte, and 0.0.4 introduces no event type and no field the fold reads.

Versioning follows [ADR-0012](decisions/ADR-0012-public-version-numbering.md):
the public number is `0.0.4` and the tag is `v0.0.4`.

## The six defects

Every row was reproduced **before** anything was edited, by an independent
reproducer supplied with the review and by the new regression tests in
`tests/test_reliability_review.py`, which fail on 0.0.3 and pass on 0.0.4.

| # | Defect on 0.0.3 | Reproduction before | Fix | Test | Result |
|---|---|---|---|---|---|
| D1 | A record holding U+0085, U+2028 or U+2029 was written and then unreadable: `LedgerIntegrityError` on the next read | `create_run(... input_ref="synthetic://a\u2028b")` then `ledger.run(...)` raised, for all three characters | `Ledger._parse` frames on the physical newline (`split("\n")`) instead of `str.splitlines()`, which also breaks on six Unicode separators that `ensure_ascii=False` writes verbatim inside strings | `test_unicode_line_breaks_survive_the_round_trip_and_framing_stays_physical` | round trip preserves the character; CRLF and a missing final newline read identically; a malformed record is still refused |
| D2 | A verifier that rewrote `$OUT` returned `approved` and the node reached `completed` with a digest different from the one recorded at return | verifier writing `CHANGED` into `$OUT`: node `a` `completed`, `hash_matches: false` | the manifest is checked **again after** the verifier runs and before its verdict is recorded; a mismatch records `verification_status: error` with a null verdict (I7) — never `rejected` — so the node does not complete and its descendants stay blocked | `test_a_verifier_that_changes_the_artifact_never_gets_its_verdict_accepted` (rewrite, delete, symlink swap, unreadable) | node ends `waiting_human` after `human_escalation`; `b` stays `pending`; the verifier's `result.json` and `log.txt` are kept. Evidence the verifier leaves **unreadable** (chmod, dangling mount) is `error` too: reading it raises `OSError`, now caught instead of abandoning an open verification with no outcome |
| D3 | A probe that timed out left its descendants running; a grandchild wrote its marker **after** the probe had answered | parent spawning a child that sleeps and writes: `probe → False`, `descendant_wrote_after_timeout: true` | `probe` now goes through `run_argv`: its own session, the §6.3 ladder (SIGINT → SIGTERM → SIGKILL) applied to its **own** process group, with a short probe-specific grace | `test_probe_timeout_kills_descendants_and_spares_the_caller_group` (a cooperative descendant and one that ignores INT/TERM) and `test_the_short_grace_belongs_to_the_probe_alone` | no late write; a descendant that ignores the polite signals is still killed before it can finish its work; the caller's own process group is never signalled; the ladder stays bounded |
| D4 | With an interrupt already requested, `advance` still opened a new verification and ran the verifier, writing `run_interrupt_requested` only afterwards | `stop_requested=lambda: True` on an already-executed producer: verifier ran, `verification_requested` + `verdict_recorded` written | `_verification_step` checks the stop request before opening **anything** new — a machine verifier, the human gate, an escalation. A verifier already running is always seen through to its recorded outcome | `test_interrupt_requested_starts_no_new_verifier` and `test_real_sigint_stops_before_the_verifier_and_keeps_finished_work` (a real SIGINT to the CLI, synchronised on handshake files, no sleeps) | events stop at `node_returned` + `run_interrupt_requested`; the finished producer is kept; the next `advance --go` continues the same run |
| D5 | `doctor` refused inline Python code as a missing file because the code contained `a/b`, while `advance` ran the same node without trouble | `x_verifier` = `python3 -c "...'a/b'..."` → `doctor_ok: false`, node state `completed` | the slash heuristic is gone. Only an argument the operator **wrote** as `{graph_dir}/…` is a path by declaration, and only those are checked for existence; the executable keeps being resolved on `PATH` | `test_doctor_does_not_mistake_inline_code_or_text_for_a_path` and `test_doctor_still_fails_on_a_declared_path_and_a_missing_executable` | inline code and URL-like arguments pass; a declared `{graph_dir}` path that is missing and a missing executable still FAIL |
| D6 | `resume` read `--graph` and passed `None` to the library: a tampered graph was accepted with exit 0 and no warning, while a missing file was refused although the snapshot was valid | `resume --graph tampered.json` → exit 0, no message | the CLI passes the graph it read, so the library validates its identity; `--from-snapshot` is a new, explicit, documented path that needs no original file. Exactly one source is required — both or neither is refused | `test_resume_validates_the_graph_it_is_given`, `test_resume_from_snapshot_needs_no_original_file`, `test_resume_keeps_the_snapshot_and_input_hash_validations` | a different graph is refused naming `graph_version`; the snapshot path works with the original deleted; `input_hash`, missing and corrupted snapshots keep being refused |

## What changes for someone already running 0.0.3

- **A verifier that touches `$OUT` no longer produces an approval.** If your
  verifier normalises, reformats or rewrites the artifact it judges, the
  verification now ends in `error` and escalates to you. Make the verifier
  read-only, or make the rewriting a producer step of its own.
- **`resume` needs exactly one graph source.** `resume --graph <file>` keeps
  working and is now actually validated; a script that passed the *wrong*
  graph used to exit 0 and now exits 1. To resume without the original file,
  pass `--from-snapshot`.
- **An interrupt stops more.** A `Ctrl+C` between two steps no longer lets a
  verification open; the next `advance --go` picks it up.
- **`doctor` reports fewer false failures and the same real ones.** It no
  longer guesses that an argument is a path because it contains a slash.
- **Ledgers written by 0.0.2/0.0.3 are unaffected on disk.** D1 was a reading
  defect: the bytes were always correct. A ledger that 0.0.3 refused to read is
  readable by 0.0.4 with no repair, no rewrite and no event dropped. **The
  reverse does not hold**: a ledger whose records contain U+0085, U+2028 or
  U+2029 inside a string is readable by 0.0.4 and stays unreadable to 0.0.3,
  because that is precisely the defect. The writer never changed, so nothing on
  disk marks such a ledger as "0.0.4"; going back to 0.0.3 goes back to the bug,
  for old and new runs alike (see *Rollback*).
- Two tests that asserted the pre-fix behaviour were updated, not deleted:
  the `doctor` path case in `tests/test_pilot.py` now declares its path through
  `{graph_dir}`, and the graceful-interrupt case now expects the interrupted
  run to stop before the verification instead of completing it.

## A second opinion on the same findings

An independent patch reviewed the same six findings in parallel with this one.
Two of its improvements are in here: catching `OSError` when the evidence is
re-read (an unreadable artifact used to crash the pilot and leave the
verification open with no outcome), and a stronger probe regression proving the
final `SIGKILL` reaches a descendant that ignores the polite signals. Where the
two disagree — how `doctor` decides an argument is a path, and whether resuming
from the snapshot is a flag or the absence of one — this release keeps the rules
stated above, and the reasoning is in the sections that describe them.

That exchange also caught a regression this release had introduced into itself:
giving `run_argv` a `grace_seconds` default bound at import silently made the
module's `GRACE_SECONDS` unpatchable, so two existing transport tests stopped
shortening the ladder they were written to shorten and started taking twenty
seconds each while still passing. The parameter now resolves at call time, and
a wiring test keeps the short grace where it belongs: a probe asks for it, a
producer never does. The short goodbye is for a liveness question, not for
work.

## Limits that remain (what 0.0.4 does not promise)

- **Re-reading the evidence is not immutability.** D2's fix compares the
  artifact to its recorded digest before and after the verifier runs. A change
  made *after* that second read, or one made and reverted *between* the two,
  is invisible to it. Isolating the evidence (read-only copy, snapshot,
  sandboxed verifier) is separate hardening and is not in this release.
- **The probe contains its own session, not the machine.** A probe command
  that deliberately leaves its session (`setsid`, a daemon, a service manager)
  is outside this containment; that needs a sandbox this transport does not
  provide.
- **`doctor` does not validate every path inside an arbitrary command.** It
  checks the executable and the paths declared through the supported
  convention, `{graph_dir}/…`. A verifier command is arbitrary — inline code,
  regexes, URLs and payloads all contain slashes — so a clean `doctor` run does
  not promise that a loose script mentioned inside the command exists. The
  diagnosis is deliberately smaller and predictable: guessing which arguments
  are files would raise its own questions (options before the script, wrappers,
  new interpreters, different command syntaxes) for a benefit this release does
  not need. Declare the path with `{graph_dir}` and `doctor` will check it.
- Carried over from 0.0.3, unchanged: no orphan constatation from the CLI
  (§13.4 open), no retry/budget policy (§13.12 open), no dependency-output
  injection, no remote transports, no strong actor identity (§13.8 open).
  `doctor` still cannot prove that a model will answer — the first `--go`
  against a real binding is that test, and it spends.

## Verification

Zero cost, no network, no model, no paid inference:

```bash
python3 tools/check_contracts.py     # 3/3 PASS — promoted documents byte-identical
python3 -m compileall -q src tests
python3 tools/run_tests.py           # 24 files, ALL PASS
PYTHONPATH=src:tests python3 tests/test_reliability_review.py   # 11 tests PASS
```

The regression file is the review itself: run it against `v0.0.3` and ten of
its eleven tests fail. The eleventh is a guard rather than a reproduction — it
proves `doctor` still reports a genuinely missing declared path, which 0.0.3
also did.

## Rollback — without discarding work

0.0.4 is a commit on `main`, tagged `v0.0.4`. History is append-only
(AGENTS.md §11), so going back means adding a commit, never rewriting one, and
the release itself can no longer be lost by a working-tree command:

- **Run 0.0.3 side by side**: `git worktree add ../dagwell-0.0.3 v0.0.3`, then
  `PYTHONPATH=../dagwell-0.0.3/src python3 -m dagwell.cli --version` →
  `dagwell 0.0.3`. Remove with `git worktree remove ../dagwell-0.0.3`.
- **Undo the release on `main`**: `git revert $(git rev-list -n1 v0.0.4)`. The
  revert is a new commit; the tag keeps pointing at what 0.0.4 was.
- **To make an installed command run 0.0.3 without touching this checkout**:
  `pipx install --force git+https://github.com/docentesIA/dagwell.git@v0.0.3`
  (a fresh, pinned, non-editable install — it replaces an editable one).

An earlier draft of this section lumped three commands together as ways to
"delete the candidate". Correcting that: `git checkout -- .` overwrites
modified tracked files and `git clean` removes untracked ones, so both destroy
uncommitted work; `git stash` does **not** — it saves the changes on the stash
stack and `git stash pop` restores them. What made stash the wrong tool for
reviewing a candidate was that it empties the working tree of the very change
under review, not that it loses it.

Where `dagwell` on `PATH` is an **editable** install pointing at this
checkout's `src/`, the installed command already runs this candidate; that is
a property of the install, not something this release changed.

Data is untouched by any of this: what the pilot wrote lives under the
operator's `--data-dir` and in the ledger, and no rollback rewrites a byte of
either. One caveat, and it is D1 itself: a ledger whose records contain U+0085,
U+2028 or U+2029 is read by 0.0.4 and refused by 0.0.3, so a rollback restores
that reading defect for the runs that have such a record. The events are all
still there — 0.0.3 simply will not frame them. Every other ledger projects the
same states under both versions.

## Changed files

```
src/dagwell/ledger/ledger.py                        D1: physical-newline framing
src/dagwell/adapters/pilot.py                       D2, D4, D5
src/dagwell/adapters/transports/subprocess_transport.py   D3: probe through run_argv
src/dagwell/cli.py                                  D6: resume --graph / --from-snapshot
tests/test_reliability_review.py                    NEW: 11 zero-cost regression tests
tests/test_pilot.py                                 two assertions that encoded the bugs
pyproject.toml, src/dagwell/__init__.py             version 0.0.4
docs/USAGE.md, docs/USAGE.pt-BR.md                  §4.9 resume sources
README.md, README.pt-BR.md, docs/RELEASE-0.0.4.md   release notes
```

No change to: `docs/contracts/*` (manifest verified), `fold.py`,
`operations.py`, `human.py`, `graph.py`, `evidence.py`, `selection.py`,
`registry.py`, `artifacts.py`, `worker.py`, schemas, `examples/`.

## Relato em português

A 0.0.4 corrige seis defeitos de confiabilidade achados numa revisão
independente da 0.0.3, todos reproduzidos antes de qualquer alteração e
cobertos por teste que falha sem a correção: leitura do ledger com Unicode
válido (U+0085/U+2028/U+2029); veredito de verificador que alterou a própria
evidência (agora `error`, sem veredito, sem liberar descendentes); probe que
deixava descendentes vivos após o timeout; interrupção que ainda abria
verificação nova; `doctor` que tratava qualquer argumento com barra como
caminho; e `resume`, que lia `--graph` e o ignorava — agora valida a identidade
do grafo e oferece `--from-snapshot` explícito. Nenhuma funcionalidade nova,
nenhum contrato alterado, nenhuma questão em aberto resolvida. Suíte de custo
zero: 24 arquivos, todos aprovados. Publicação (commit, tag, push) continua
atrás do gate humano; a `v0.0.3` não foi tocada.
