# DAGWELL 0.0.2 — release candidate review

Status: **0.0.2 candidate for the final publication gate; not published.**
The model-invocation amendment received human approval on 2026-09-04.
Push, tag and release publication still require separate final approval.

## Corrected

- The selected model reaches subprocess argv through `{model_id}`, required for
  multimodel bindings, under the promoted v1.1 amendment. Literal single-model
  bindings remain compatible as operator declarations, not provider attestations.
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

## Approved model-invocation amendment

The previous transport lost the selector's model before subprocess invocation.
A fake executor reproduced different selected models producing identical argv.
The preserved Adapter Specification v1.0 permitted only `{mission}` and `$OUT`,
so the additional substitution was proposed and approved before implementation.

[Adapter v1.1](contracts/DAGWELL-ADAPTER-OUTPUT-EVIDENCE-SPEC-v1.1.md), approved
on 2026-09-04, adds `{model_id}` as its own argument, mandatory for multimodel
bindings. The selected value is passed as data after argv parsing, with no shell
interpretation. Literal single-model bindings remain operator declarations; the
operator is responsible for matching the command to the declared model. Neither
mode supplies remote provider attestation. The original v1.0 and the v1.1-RC1
proposal are preserved intact.

## Compatibility and limits

- Multimodel registries must add `{model_id}` as a separate argument; omission
  is refused before probes or dispatch. Example: `claude --model {model_id} -p
  {mission}`. Single-model literal invocations remain accepted.
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

Baseline: 15 test files passed at `7e68053` and both then-promoted contract hashes
matched. The suite discovers current test files dynamically; run
`python3 tools/run_tests.py` for the candidate's current results.
Final local validation passed all 22 test files in Python 3.11, 3.12 and 3.13.
Regression tests cover worker state, stale attempts, directory isolation,
concurrent pilot/read access, registry refusal, process-group timeout, missing
executable, late verification, sequence integrity, writer IDs and selected-model
argument propagation.

The wheel was built without network and installed in a fresh environment;
version, demo, packaged schema and worker regressions passed against that install.
Gitleaks directory scan passed with redacted output. Both original promoted
normative documents remain byte-identical; the v1.1 promotion adds its own hash.
CI still must run on the final approved commit.

## Relato em português

A candidata corrige coerência entre CLI e ledger, timeout, diretório de trabalho,
validação antecipada, isolamento de tentativas e pendências de integridade do
núcleo. A emenda v1.1 foi aprovada em 2026-09-04: o modelo selecionado chega ao argv
por `{model_id}`, obrigatório para bindings com múltiplos modelos. Bindings
literais de modelo único continuam sendo declarações do operador, sem atestado
do provedor. Não houve publicação nem execução paga. A candidata 0.0.2 segue para
o gate humano final de push/tag/release.
