"""The pilot — the thin operational layer over the governed operations.

Three read/write surfaces, no new authority:

- `doctor`: read-only diagnosis of a configuration (graph, registry,
  executables, zero-cost probes, declared verifiers, data area). It reports
  what is configured, what is found, what answered a probe — and says out
  loud what it cannot know (authentication, quota, model capability).
- `plan` / `advance`: drive ONE run as far as the contracts allow without a
  human. Producers go through the capability worker (`dagwell work`);
  declared verifiers run as subprocesses and their STRUCTURED decision is
  recorded through the machine verdict surface; the human gate is opened and
  the loop stops. Nothing here decides for a person, retries on its own,
  polls, or invents orphanhood.
- `next_actions`: the sentence `status` prints after the projection — what
  finished, what blocks, what the next valid command is.

Declared verifiers are an operator convention in the graph, like `x_command`:
a verification entry may carry `x_verifier` (an argv template, no shell) and
`x_verifier_timeout_seconds` (mandatory with it). The core never reads these
fields; they enter `graph_version` like every other byte of the graph, so the
verifier's identity is frozen with the run. The verifier receives `$OUT`
(the evidence file the verdict will bind to) and writes ONE JSON object to
stdout: `{"verdict": "approved"|"rejected", "reasons": [...]}`. Its exit code
is a transport fact, never a verdict (I6): nonzero -> `verification_status:
error`; over time -> `timeout`; exit 0 without a valid object -> `error`.
None of those carries a verdict (I7).
"""

import getpass
import hashlib
import json
import os
import shlex
import shutil
import sys
from pathlib import Path

from dagwell import operations, runtime
from dagwell.adapters import worker
from dagwell.adapters.registry import RegistryValidationError, load_registry
from dagwell.adapters.selection import SelectionError, select
from dagwell.adapters.transports import subprocess_transport as st
from dagwell.artifacts import attempt_dir, verification_dir
from dagwell.fold import fold
from dagwell.graph import GraphValidationError, load_graph

GRAPH_DIR_MARKER = "{graph_dir}"
RESULT_NAME, LOG_NAME, EXIT_NAME = "result.json", "log.txt", "exit"


class PilotRefused(operations.OperationRefused):
    pass


# -- declared verifiers ----------------------------------------------------

def verifier_declaration(verification: dict, *, graph_dir=None):
    """Parse a verification entry's `x_verifier` fail-closed. Returns
    {"argv": [...], "timeout_seconds": n} or None when nothing is declared."""
    template = verification.get("x_verifier")
    vid = verification.get("verification_id")
    if template is None:
        if "x_verifier_timeout_seconds" in verification:
            raise PilotRefused(
                f"verification {vid!r}: x_verifier_timeout_seconds without "
                "x_verifier")
        return None
    if not isinstance(template, str) or not template.strip():
        raise PilotRefused(f"verification {vid!r}: x_verifier must be a "
                           "non-empty command template")
    try:
        argv = shlex.split(template)
    except ValueError as exc:
        raise PilotRefused(
            f"verification {vid!r}: x_verifier has invalid quoting") from exc
    if not argv or "\x00" in template:
        raise PilotRefused(f"verification {vid!r}: x_verifier is empty")
    timeout = verification.get("x_verifier_timeout_seconds")
    if (not isinstance(timeout, (int, float)) or isinstance(timeout, bool)
            or timeout <= 0 or timeout != timeout or timeout == float("inf")):
        raise PilotRefused(
            f"verification {vid!r}: x_verifier_timeout_seconds must be a "
            "positive number (mandatory with x_verifier, no invented default)")
    if any(GRAPH_DIR_MARKER in a for a in argv):
        if graph_dir is None:
            raise PilotRefused(
                f"verification {vid!r}: x_verifier uses {GRAPH_DIR_MARKER} "
                "but no graph directory is known")
        argv = [a.replace(GRAPH_DIR_MARKER, str(Path(graph_dir).resolve()))
                for a in argv]
    return {"argv": argv, "timeout_seconds": timeout}


def _verification(graph, node_id, vid):
    for v in graph["nodes"][node_id].get("verifications") or []:
        if v["verification_id"] == vid:
            return v
    raise PilotRefused(f"node {node_id}: undeclared verification {vid!r}")


def _which(executable: str, env: dict):
    return shutil.which(executable, path=env.get("PATH", os.defpath))


def _parse_result(path: Path):
    """The verifier's structured decision, validated whole. Raises ValueError."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("result is not a JSON object")
    verdict = data.get("verdict")
    if verdict not in ("approved", "rejected"):
        raise ValueError(f"verdict must be approved|rejected, got {verdict!r}")
    reasons = data.get("reasons", [])
    if not isinstance(reasons, list) or not all(isinstance(r, str) for r in reasons):
        raise ValueError("reasons must be a list of strings")
    return verdict, reasons


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_mismatch(adir: Path, manifest: list) -> str | None:
    """The verifier will look at files on disk; the verdict binds to the
    evidence recorded at return. Refuse to run when they are not the same
    bytes — a verdict about other bytes would be laundered into the record."""
    for entry in manifest:
        path = adir / entry["path"]
        if path.is_symlink() or not path.is_file():
            return f"{entry['path']} is missing from {adir}"
        if "sha256:" + _sha256(path) != entry["artifact_digest"]:
            return (f"{entry['path']} on disk differs from the artifact_digest "
                    f"recorded at return ({adir})")
    return None


def _run_verifier(decl, *, adir: Path, vdir: Path, env: dict, out_path: str,
                  ids: dict) -> tuple[str, str | None, str]:
    """Execute one declared verifier. Returns (verification_status, verdict,
    reason) — the two contract axes, derived only from the verifier's own
    structured output and the transport facts."""
    vdir.mkdir(parents=True, exist_ok=False)   # never overwrite a record
    child_env = {**env, "OUT": out_path,
                 **{f"DAGWELL_{k.upper()}": str(v) for k, v in ids.items()}}
    name = Path(decl["argv"][0]).name
    with open(vdir / RESULT_NAME, "wb") as out, open(vdir / LOG_NAME, "wb") as log:
        facts = st.run_argv(decl["argv"], env=child_env, cwd=adir,
                            timeout_seconds=decl["timeout_seconds"],
                            stdout=out, stderr=log)
    (vdir / EXIT_NAME).write_text(f"{facts.get('exit_code')}\n", encoding="utf-8")
    log_sha = _sha256(vdir / LOG_NAME)
    if facts.get("transport_error"):
        return ("error", None,
                f"{name}: could not be spawned ({facts['transport_error']['type']})")
    if facts["timed_out"]:
        return ("timeout", None,
                f"{name}: exceeded {decl['timeout_seconds']}s (verifier "
                f"timeout, no verdict); log_sha256={log_sha}")
    if facts["exit_code"] != 0:
        return ("error", None,
                f"{name}: exit={facts['exit_code']} (verifier error, no "
                f"verdict); log_sha256={log_sha}")
    try:
        verdict, reasons = _parse_result(vdir / RESULT_NAME)
    except (ValueError, OSError) as exc:
        return ("error", None,
                f"{name}: exit=0 but no valid verdict object on stdout "
                f"({exc}); log_sha256={log_sha}")
    text = "; ".join(reasons)[:400] or "no reasons given"
    return ("completed", verdict,
            f"{name}: {text}; result_sha256={_sha256(vdir / RESULT_NAME)}")


# -- doctor ------------------------------------------------------------------

def doctor(graph_text, registry_text, data_dir=None, *, graph_dir=None,
           env=None) -> tuple[bool, list[str]]:
    """Read-only. Returns (ok, lines). `FAIL:` lines make ok False; `warn:`
    and `note:` lines are for the operator's eyes. No environment VALUE is
    ever printed — names of executables, yes; secrets, never."""
    env = dict(env if env is not None else os.environ)
    lines, fails = [], []

    def fail(msg):
        fails.append(msg)
        lines.append(f"FAIL: {msg}")

    if sys.version_info < (3, 11):
        fail(f"python {sys.version_info.major}.{sys.version_info.minor} — "
             "dagwell requires 3.11+")
    else:
        lines.append(f"ok: python {sys.version_info.major}.{sys.version_info.minor}")

    graph = registry = None
    try:
        graph = load_graph(graph_text)
        lines.append(f"ok: graph {graph['graph_id']!r} ({len(graph['nodes'])} "
                     f"nodes, {graph['graph_version']})")
    except GraphValidationError as exc:
        fail(f"graph: {exc}")
    try:
        registry = load_registry(registry_text)
        lines.append(f"ok: registry ({len(registry['bindings'])} bindings, "
                     f"{registry['registry_digest']})")
    except RegistryValidationError as exc:
        fail(f"registry: {exc}")

    available = set()
    if registry is not None:
        for bid, b in registry["bindings"].items():
            exe = st.build_argv(b["invocation"], "doctor",
                                model_id=b["models"][0]["model_id"])[0]
            if _which(exe, env) is None:
                fail(f"binding {bid}: executable {exe!r} not found on PATH")
                continue
            lines.append(f"ok: binding {bid}: executable {exe!r} found")
            if b.get("probe"):
                if st.probe(b, env=env):
                    available.add(bid)
                    lines.append(f"ok: binding {bid}: probe passed")
                else:
                    lines.append(f"warn: binding {bid}: probe failed — binding "
                                 "unavailable for selection")
            else:
                available.add(bid)
                lines.append(f"note: binding {bid}: no probe declared — treated "
                             "as available")
            models = ", ".join(f"{m['model_id']}[{'/'.join(m['tiers'])}]"
                               for m in b["models"])
            lines.append(f"note: binding {bid}: models {models}; authentication "
                         "and quota NOT verified here (a probe proves the "
                         "executable answers, not that a model will)")

    if graph is not None:
        tiers = sorted({n["capability_requirements"]["tier"]
                        for n in graph["nodes"].values()
                        if n.get("capability_requirements")})
        for tier in tiers:
            if registry is None:
                break
            try:
                sel = select(tier, registry, available)
                lines.append(f"ok: tier {tier!r} served by "
                             f"{sel['binding_id']}/{sel['model_id']}")
            except SelectionError as exc:
                fail(f"tier {tier!r}: {exc}")
        for nid in graph["order"]:
            node = graph["nodes"][nid]
            if "x_command" in node:
                lines.append(f"note: node {nid}: x_command — an external runner "
                             "executes it (examples/runner.sh); advance skips it")
            if node.get("capability_requirements") is None and "x_command" not in node:
                lines.append(f"note: node {nid}: neither capability_requirements "
                             "nor x_command — dispatch/return by hand")
            for v in node.get("verifications") or []:
                vid, fam = v["verification_id"], v["family"]
                if fam == "human":
                    lines.append(f"note: {nid}/{vid}: human gate — advance opens "
                                 "it and stops; only `decide` closes it")
                    continue
                try:
                    decl = verifier_declaration(v, graph_dir=graph_dir)
                except PilotRefused as exc:
                    fail(str(exc))
                    continue
                if decl is None:
                    lines.append(f"note: {nid}/{vid} ({fam}): no x_verifier — "
                                 "advance stops there; record the verdict by "
                                 "hand (request-verification + verdict)")
                    continue
                if _which(decl["argv"][0], env) is None:
                    fail(f"verifier {nid}/{vid}: executable "
                         f"{decl['argv'][0]!r} not found on PATH")
                    continue
                missing = [a for a in decl["argv"][1:]
                           if "/" in a and not Path(a).exists()
                           and not a.startswith("-")]
                if missing:
                    fail(f"verifier {nid}/{vid}: path {missing[0]!r} not found")
                    continue
                lines.append(f"ok: verifier {nid}/{vid} ({fam}): "
                             f"{shlex.join(decl['argv'])} "
                             f"(timeout {decl['timeout_seconds']}s)")

    if data_dir is not None:
        d = Path(data_dir)
        if not d.exists():
            lines.append(f"note: data dir {d} does not exist yet — created at "
                         "the first --go")
        elif not d.is_dir():
            fail(f"data dir {d} is not a directory")
        elif not os.access(d, os.W_OK):
            fail(f"data dir {d} is not writable")
        else:
            lines.append(f"ok: data dir {d} writable")
    return not fails, lines


# -- plan / advance --------------------------------------------------------

def _verification_step(ledger, graph, run_id, data_dir, *, operation,
                       node_id, actor, env, go, graph_dir):
    """One pass over nodes owing verification: what the contract order says
    is due next, done — or the exact reason it was not."""
    report, progressed = [], False
    data_root = Path(data_dir).resolve()   # $OUT and cwd must be absolute
    revents = ledger.run(run_id)
    folded = fold(graph, revents, run_id)
    for nid in graph["order"]:
        if node_id is not None and nid != node_id:
            continue
        info = folded["nodes"][nid]
        if info["state"] not in ("executed", "verifying"):
            continue
        k = info["attempt"]
        evidence_id = operations._evidence_id_of(revents, nid, k)
        due = operations.next_due(graph, nid, k, evidence_id, revents)
        if due is None:
            open_req = [e for e in revents
                        if e.get("event_type") == "verification_requested"
                        and e.get("node_id") == nid and e.get("attempt") == k
                        and e.get("family") != "human"
                        and not any(o.get("event_type") == "verdict_recorded"
                                    and o.get("node_id") == nid
                                    and o.get("attempt") == k
                                    and o.get("verification_id") == e["verification_id"]
                                    and o.get("verification_attempt")
                                    == e["verification_attempt"]
                                    for o in revents)]
            if open_req:
                r = open_req[-1]
                report.append({"kind": "verification", "node_id": nid,
                               "verification_id": r["verification_id"],
                               "action": "in_flight",
                               "reason": f"verification_attempt "
                                         f"{r['verification_attempt']} requested at "
                                         f"{r['occurred_at']} has no outcome; this "
                                         "command does not assume it died (§13.4 open) "
                                         "— observe it with runtime.resume("
                                         "still_in_progress=...) or record its outcome"})
            continue
        if due[0] == "escalate":
            if go:
                operations.escalate(ledger, graph, run_id, nid)
                progressed = True
            report.append({"kind": "verification", "node_id": nid,
                           "verification_id": due[1],
                           "action": "escalated" if go else "would_escalate",
                           "reason": "verifier outcome was error/timeout and "
                                     "automatic re-fire is off (§13.12 open) — "
                                     "the human decides: decide or human-retry"})
            continue
        _, vid, family = due
        if family == "human":
            if go:
                operations.request_verification(ledger, graph, run_id, nid, vid)
                progressed = True
            report.append({"kind": "gate", "node_id": nid, "verification_id": vid,
                           "action": "gate_open" if go else "would_open_gate",
                           "reason": "waiting for the human decision — silence "
                                     "never approves"})
            continue
        decl = verifier_declaration(_verification(graph, nid, vid),
                                    graph_dir=graph_dir)
        if decl is None:
            report.append({"kind": "verification", "node_id": nid,
                           "verification_id": vid, "action": "manual",
                           "reason": f"no x_verifier declared for {vid} "
                                     f"({family}) — request-verification, run "
                                     "it, then verdict"})
            continue
        adir = attempt_dir(data_root, operation=operation, run_id=run_id,
                           node_id=nid, attempt=k)
        returned = next(e for e in revents
                        if e.get("event_type") == "node_returned"
                        and e.get("node_id") == nid and e.get("attempt") == k)
        manifest = returned["output_evidence"].get("output_manifest") or []
        if not manifest:
            report.append({"kind": "verification", "node_id": nid,
                           "verification_id": vid, "action": "manual",
                           "reason": "evidence is not an artifact manifest — "
                                     "declared verifiers examine $OUT files"})
            continue
        mismatch = _manifest_mismatch(adir, manifest)
        if mismatch:
            report.append({"kind": "verification", "node_id": nid,
                           "verification_id": vid, "action": "inconsistent",
                           "reason": mismatch + " — verifier not run, nothing "
                                                "recorded"})
            continue
        if _which(decl["argv"][0], env) is None:
            report.append({"kind": "verification", "node_id": nid,
                           "verification_id": vid, "action": "refused",
                           "reason": f"verifier executable {decl['argv'][0]!r} "
                                     "not found — nothing recorded"})
            continue
        out_path = str(adir / manifest[0]["path"])
        if not go:
            report.append({"kind": "verification", "node_id": nid,
                           "verification_id": vid, "action": "would_verify",
                           "reason": f"{shlex.join(decl['argv'])} in {adir} "
                                     f"(timeout {decl['timeout_seconds']}s)"})
            continue
        req = operations.request_verification(ledger, graph, run_id, nid, vid)
        va = req["verification_attempt"]
        vdir = verification_dir(data_root, operation=operation, run_id=run_id,
                                node_id=nid, verification_id=vid, attempt=k,
                                verification_attempt=va)
        status, verdict, reason = _run_verifier(
            decl, adir=adir, vdir=vdir, env=env, out_path=out_path,
            ids={"run_id": run_id, "node_id": nid, "attempt": k,
                 "verification_id": vid, "verification_attempt": va,
                 "evidence_id": evidence_id})
        operations.record_machine_verdict(
            ledger, graph, run_id, nid, vid, verification_status=status,
            verdict=verdict, actor=actor, reason=reason)
        progressed = True
        state = fold(graph, ledger.run(run_id), run_id)["nodes"][nid]["state"]
        report.append({"kind": "verification", "node_id": nid,
                       "verification_id": vid, "verification_attempt": va,
                       "action": "verified", "verification_status": status,
                       "verdict": verdict, "node_state": state,
                       "verification_dir": str(vdir), "reason": reason})
    return report, progressed


def plan(ledger, graph, run_id, registry, data_dir, *, operation=None,
         node_id=None, env=None, graph_dir=None) -> list[dict]:
    """What `advance` would do next, spending nothing and writing nothing:
    zero-cost probes only (spec §6.6), no run, no event, no directory, no
    verifier subprocess."""
    env = dict(env if env is not None else os.environ)
    operation = operation or graph["graph_id"]
    _preflight(graph, graph_dir)
    report = [{"kind": "producer", **p} for p in
              worker.work(ledger, graph, run_id, registry, data_dir,
                          operation=operation, node_id=node_id, env=env, go=False)]
    vreport, _ = _verification_step(ledger, graph, run_id, data_dir,
                                    operation=operation, node_id=node_id,
                                    actor=None, env=env, go=False,
                                    graph_dir=graph_dir)
    return report + vreport


def _preflight(graph, graph_dir):
    """Every declared verifier parses, or nothing starts (fail-closed)."""
    for nid in graph["order"]:
        for v in graph["nodes"][nid].get("verifications") or []:
            verifier_declaration(v, graph_dir=graph_dir)


def advance(ledger, graph, run_id, registry, data_dir, *, operation=None,
            node_id=None, actor=None, env=None, graph_dir=None,
            stop_requested=None) -> list[dict]:
    """Drive the run until nothing more can happen without a human or a
    repair: execute READY capability nodes, run declared verifiers in
    contract order, open human gates, escalate verifier failures. Every
    iteration must write at least one event or the loop ends — no polling,
    no silent retry. `stop_requested()` (graceful interruption) ends the loop
    after the current step and records `run_interrupt_requested`."""
    env = dict(env if env is not None else os.environ)
    operation = operation or graph["graph_id"]
    actor = actor or getpass.getuser()
    _preflight(graph, graph_dir)
    runtime.ready_nodes(graph, ledger, run_id)   # validate before locking
    report = []
    with worker.pilot_lock(ledger, run_id):
        while True:
            # `--node X` after X was dispatched: it owes verification, not a
            # producer — asking the worker again would only yield "refused".
            results = [] if node_id is not None and node_id not in {
                n for n, _ in runtime.ready_nodes(graph, ledger, run_id)} else \
                worker.work(ledger, graph, run_id, registry, data_dir,
                            operation=operation, node_id=node_id,
                            env=env, go=True, locked=True,
                            stop_requested=stop_requested)
            progressed = any(r["action"] in ("executed", "failed", "completed")
                             for r in results)
            report.extend({"kind": "producer", **r} for r in results)
            vreport, vprog = _verification_step(
                ledger, graph, run_id, data_dir, operation=operation,
                node_id=node_id, actor=actor, env=env, go=True,
                graph_dir=graph_dir)
            report.extend(vreport)
            progressed = progressed or vprog
            if stop_requested is not None and stop_requested():
                try:
                    operations.request_interrupt(ledger, graph, run_id)
                    report.append({"kind": "run", "action": "interrupt_recorded",
                                   "reason": "run_interrupt_requested written; "
                                             "resume with advance --go"})
                except operations.OperationRefused as exc:
                    report.append({"kind": "run", "action": "interrupt_not_recorded",
                                   "reason": str(exc)})
                break
            if not progressed:
                break
    # A statement that nothing changed (manual step, in flight, skipped,
    # refused) recurs on the closing iteration; say it once.
    seen, unique = set(), []
    for r in report:
        key = (r["kind"], r.get("node_id"), r.get("verification_id"),
               r["action"], r.get("attempt"), r.get("verification_attempt"))
        if r["action"] in ("executed", "failed", "completed", "verified",
                           "gate_open", "escalated") or key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


# -- status: the next valid action ----------------------------------------

def next_actions(graph, folded, revents) -> list[str]:
    """Derived sentences for `status`: what blocks and what to type next.
    Pure read; nothing here has authority."""
    lines = []
    rs = folded["run_state"]
    if folded.get("integrity") != "ok":
        return ["next: mutation is blocked (integrity degraded) — reconciliation "
                "is an open specification (§13.16); status stays readable"]
    if rs == "completed":
        return ["next: nothing — the run is completed"]
    if rs == "cancelled":
        return ["next: nothing — the run is cancelled (absorbing)"]
    if rs == "landed":
        return ["next: the run is landed — human-retry --node <failed|rejected node> "
                "(or budget_extended via the library) before resume"]
    for nid, info in folded["nodes"].items():
        st_ = info["state"]
        node = graph["nodes"][nid]
        if st_ == "waiting_human":
            escalated = any(e.get("event_type") == "human_escalation"
                            and e.get("node_id") == nid
                            and e.get("attempt") == info["attempt"]
                            for e in revents)
            lines.append(f"next: decide --node {nid} approved|rejected "
                         f"--actor <you> [--reason ...]"
                         + (f" — or human-retry --node {nid} (escalated: the "
                            "verifier did not conclude)" if escalated else ""))
        elif st_ in ("failed", "rejected"):
            lines.append(f"next: {nid} is {st_} (attempt {info['attempt']}) — "
                         f"human-retry --node {nid} opens attempt "
                         f"{info['attempt'] + 1}, or land the run")
        elif st_ == "running":
            lines.append(f"in flight: {nid} attempt {info['attempt']} has no "
                         "return — wait for it, or observe orphanhood via the "
                         "library (no automatic timeout)")
        elif st_ == "ready":
            if node.get("capability_requirements") is not None:
                lines.append(f"next: {nid} is ready — advance --go (or work --go)")
            elif "x_command" in node:
                lines.append(f"next: {nid} is ready — external runner "
                             "(dispatch / return)")
            else:
                lines.append(f"next: {nid} is ready — dispatch, do the work, return")
        elif st_ in ("executed", "verifying"):
            k = info["attempt"]
            due = operations.next_due(graph, nid, k,
                                      operations._evidence_id_of(revents, nid, k),
                                      revents)
            if due is None:
                lines.append(f"in flight: {nid} has a verification without outcome")
            elif due[0] == "escalate":
                lines.append(f"next: {nid} — verifier {due[1]} did not conclude; "
                             "advance --go escalates to the human")
            elif due[2] == "human":
                lines.append(f"next: {nid} — advance --go opens the human gate "
                             f"{due[1]}")
            else:
                v = _verification(graph, nid, due[1])
                if v.get("x_verifier"):
                    lines.append(f"next: {nid} — advance --go runs verifier {due[1]}")
                else:
                    lines.append(f"next: {nid} — request-verification --verification "
                                 f"{due[1]}, run it, then verdict")
    return lines or ["next: nothing dispatchable and nothing owed — see the "
                     "node states above"]
