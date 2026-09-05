# DAGWELL 0.0.2 — release candidate review

Status: **0.0.2rc1, not published and not ready for the final release gate.**
The model-invocation amendment below still needs human approval and implementation.

## Corrected

- The worker reports the ledger-derived node state; nonzero exit with an artifact
  is failure. A declared verification waiver may yield `completed` immediately.
  CLI failure/refusal exits nonzero; it does not announce verification on failure.
- Timeout is failed transport even when the process handles the signal and exits
  zero. Opening verification for that return is refused before append.
- Subprocess cwd is its attempt directory; `$OUT` is absolute. Timeout signals
  the process group through INT/TERM/KILL, including descendants after leader exit.
- Missing runs, frozen-graph mismatch and degraded integrity are refused before
  probes or attempt creation. Diagnostic `status` remains available for supported
  damaged histories; sequence collisions and regressions refuse projection.
- One active worker per ledger/run uses a separate advisory lock, leaving the
  ledger readable. Expected attempt is checked at dispatch. Existing attempt
  directories and symlinked attempt paths are refused; history is not reused.
- Invalid templates/probes and non-finite timeout/cost values are refused.
  Missing executables are refused before dispatch.
- Fold refuses sequence regression and makes late verification outcomes inert
  and visible. New writes require canonical UUIDv7 IDs; historical reads and
  the synthetic legacy namespace are preserved without migration.

## Pending human decision

The selector's model is currently not passed to subprocess invocation. A fake
executor confirmed that different selected models produce identical argv.
The preserved Adapter Specification v1.0 permits only `{mission}` and `$OUT`,
so the implementation cannot silently add another substitution.

[Adapter v1.1-RC1](contracts/DAGWELL-ADAPTER-OUTPUT-EVIDENCE-SPEC-v1.1-RC1.md)
proposes `{model_id}` as its own argument, mandatory for multimodel bindings,
with literal single-model bindings retained as operator declarations. It is
**not promoted or implemented**. Do not publish this candidate as resolving
model-selection correctness.

## Compatibility and limits

- Scripts that treated worker refusal/failure as exit zero must handle exit 1.
- Relative subprocess paths now resolve in the attempt directory, as specified.
- Existing attempt directories are preserved and refused, including an empty
  reservation left by a later refusal. Inspect it; do not remove history blindly.
- A spawn race after preflight leaves the recorded dispatch in flight. The
  command explains the error; explicit liveness observation through the library's
  `resume(..., still_in_progress=...)` is required. No exit status is invented.
- Advisory worker locking does not introduce distributed claims or constrain
  arbitrary external writers. Processes deliberately escaping their process group
  are outside this local timeout containment.
- No strong provider model attestation, automatic retry, ACP or remote transport
  is introduced. Subagent review used the same model family, not an independent
  vendor-family verifier.
- `AGENTS.md` retains obsolete historical descriptions because it is normative;
  this release does not edit it in place. Promoted specs and accepted ADRs govern.

## Validation

Baseline: 15 test files passed at `7e68053` and both promoted contract hashes
matched. Candidate: 20 test files passed in Python 3.11, 3.12 and 3.13.
Regression tests cover worker state, stale attempts, directory isolation,
concurrent pilot/read access, registry refusal, process-group timeout, missing
executable, late verification, sequence integrity and writer IDs.

The wheel was built without network and installed in a fresh environment;
version, demo, packaged schema and worker regressions passed against that install.
Gitleaks directory scan passed with redacted output. Both promoted normative
documents remain byte-identical. CI still must run on the final approved commit.

## Relato em português

A candidata corrige coerência entre CLI e ledger, timeout, diretório de trabalho,
validação antecipada, isolamento de tentativas e pendências de integridade do
núcleo. A seleção do modelo permanece bloqueada pela aprovação da proposta v1.1.
Não houve publicação nem execução paga. O próximo gate é normativo; o gate de
push/tag/release vem somente depois de completar e revisar essa correção.
