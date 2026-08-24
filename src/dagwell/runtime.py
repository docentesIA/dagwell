"""Recovery substrate: run creation, verification advancement, interruption,
orphan observation, resume (contract §1, §3, §4, §8, §10).

No transports exist yet (adapters are Phase 8/9): dispatching is exposed as a
primitive for callers/tests; nothing here executes work or spends. With no
Runtime Policy Specification (§13.12) automatic retry/re-fire is DISABLED —
fail-closed: verifier error/timeout/orphaned outcomes escalate to the human
(policy exhausted at zero); a verification cancelled by graceful interruption
does NOT count against the policy (§6/§10) and is simply re-fired. There is
no universal orphan timeout: orphan evidence is produced only at observation
(resume or explicit human command) through an injected constatation callback
— the concrete mechanism is §13.4 and is NOT resolved here; without a
callback, in-flight work is never orphaned.
"""

from dagwell import canonical, ids, verification as vf
from dagwell.fold import fold
from dagwell.graph import declared_verifications, load_graph
from dagwell.ledger import Ledger, create_run, events as ev


class ResumeRefused(ev.LedgerError):
    pass


# -- run creation (the --go validation home) -------------------------------

def start_run(ledger: Ledger, *, graph_text, input_text, input_ref,
              parent_run_id=None):
    """Validate the graph fail-closed, then create the run. Returns
    (graph, run_created event). Refuse before spend (I5/I16/I28)."""
    graph = load_graph(graph_text)
    founding = create_run(ledger, graph_id=graph["graph_id"],
                          graph_text=graph_text, input_text=input_text,
                          input_ref=input_ref, parent_run_id=parent_run_id)
    return graph, founding


# -- dispatch / return primitives ------------------------------------------

def dispatch_node(ledger: Ledger, run_id: str, node_id: str,
                  attempt: int) -> dict:
    return ledger.append({
        "schema_version": ev.SCHEMA_VERSION,
        "event_id": ids.new_event_id(),
        "run_id": run_id,
        "event_type": "node_dispatched",
        "occurred_at": ev.occurred_now(),
        "node_id": node_id,
        "attempt": attempt,
    })


def ready_nodes(graph: dict, ledger: Ledger, run_id: str) -> list[tuple]:
    """(node_id, next_attempt) for every node in the ready derived view."""
    folded = fold(graph, ledger.run(run_id), run_id)
    out = []
    for nid, info in folded["nodes"].items():
        if info["state"] == "ready":
            out.append((nid, (info["attempt"] or 0) + 1))
    return out


def record_return(ledger: Ledger, run_id: str, node_id: str, attempt: int,
                  exit_code: int, output_evidence=None) -> dict:
    e = {
        "schema_version": ev.SCHEMA_VERSION,
        "event_id": ids.new_event_id(),
        "run_id": run_id,
        "event_type": "node_returned",
        "occurred_at": ev.occurred_now(),
        "node_id": node_id,
        "attempt": attempt,
        "exit_code": exit_code,
    }
    if output_evidence is not None:
        e["output_evidence"] = output_evidence
    return ledger.append(e)


# -- verification advancement (machines first, human last) -----------------

def advance_verifications(ledger: Ledger, graph: dict, run_id: str) -> list[dict]:
    """Emit the next due verification events. Non-human first; the human gate
    is requested only when every non-human obligatory verification is
    approved (§4). Verifier failure outcomes escalate (policy at zero);
    interruption-cancelled outcomes re-fire without escalation."""
    emitted = []
    revents = ledger.run(run_id)
    folded = fold(graph, revents, run_id)
    for node_id, info in folded["nodes"].items():
        if info["state"] not in ("executed", "verifying"):
            continue
        k = info["attempt"]
        evidence_id = _evidence_id_of(revents, node_id, k)
        if evidence_id is None:
            continue
        emitted.extend(_advance_node(ledger, graph, run_id, revents,
                                     node_id, k, evidence_id))
        revents = ledger.run(run_id)
    return emitted


def _evidence_id_of(revents, node_id, k):
    for e in revents:
        if (e.get("event_type") == "node_returned"
                and e.get("node_id") == node_id and e.get("attempt") == k):
            return (e.get("output_evidence") or {}).get("evidence_id")
    return None


def _advance_node(ledger, graph, run_id, revents, node_id, k, evidence_id):
    declared = declared_verifications(graph, node_id)

    def outcomes(vid, va=None):
        out = [e for e in revents
               if e.get("event_type") == "verdict_recorded"
               and e.get("node_id") == node_id and e.get("attempt") == k
               and e.get("verification_id") == vid]
        if va is not None:
            out = [o for o in out if o.get("verification_attempt") == va]
        return out

    def open_request(vid):
        reqs = [e for e in revents
                if e.get("event_type") == "verification_requested"
                and e.get("node_id") == node_id and e.get("attempt") == k
                and e.get("verification_id") == vid]
        return any(not outcomes(vid, r["verification_attempt"]) for r in reqs)

    def approved(vid):
        return any(o.get("verification_status") == "completed"
                   and o.get("verdict") == "approved"
                   and o.get("evidence_id") == evidence_id
                   for o in outcomes(vid))

    def unresolved_escalation():
        esc = [e for e in revents
               if e.get("event_type") == "human_escalation"
               and e.get("node_id") == node_id and e.get("attempt") == k]
        if not esc:
            return False
        last = max(e["seq"] for e in esc)
        return not any(
            e.get("node_id") == node_id and e.get("attempt") == k
            and e["seq"] > last
            and (e.get("event_type") == "human_retry"
                 or (e.get("event_type") == "verdict_recorded"
                     and e.get("family") == "human"))
            for e in revents)

    if unresolved_escalation():
        return []

    non_human = [v for v in declared if v["family"] != "human"]
    for v in non_human:
        vid = v["verification_id"]
        if approved(vid):
            continue
        if open_request(vid):
            return []  # in flight — wait for its outcome
        prior = outcomes(vid)
        if prior:
            last = max(prior, key=lambda o: o["seq"])
            if last.get("verification_status") == "cancelled":
                # graceful-interruption cancellation never counts against the
                # re-fire policy (§6/§10): re-fire as a new attempt
                va = vf.next_verification_attempt(revents, node_id, k, vid)
                return [ledger.append(vf.verification_requested_event(
                    run_id=run_id, node_id=node_id, attempt=k,
                    verification_id=vid, verification_attempt=va,
                    family=v["family"], evidence_id=evidence_id))]
            # error/timeout/orphaned: no policy exists to authorize an
            # automatic re-fire (§13.12) — escalate to the human (§4)
            return [ledger.append({
                "schema_version": ev.SCHEMA_VERSION,
                "event_id": ids.new_event_id(),
                "run_id": run_id,
                "event_type": "human_escalation",
                "occurred_at": ev.occurred_now(),
                "node_id": node_id,
                "attempt": k,
                "reason": "verifier_error",
            })]
        va = vf.next_verification_attempt(revents, node_id, k, vid)
        return [ledger.append(vf.verification_requested_event(
            run_id=run_id, node_id=node_id, attempt=k, verification_id=vid,
            verification_attempt=va, family=v["family"],
            evidence_id=evidence_id))]

    # every non-human approved → request the human gate, once
    for v in declared:
        if v["family"] != "human":
            continue
        vid = v["verification_id"]
        if approved(vid) or open_request(vid):
            continue
        va = vf.next_verification_attempt(revents, node_id, k, vid)
        return [ledger.append(vf.verification_requested_event(
            run_id=run_id, node_id=node_id, attempt=k, verification_id=vid,
            verification_attempt=va, family="human",
            evidence_id=evidence_id))]
    return []


# -- interruption (graceful) and orphans (abrupt loss) ---------------------

def request_interrupt(ledger: Ledger, run_id: str) -> dict:
    """Record the INTENT of graceful interruption (§10). Fold-inert; the
    interrupting process itself stops dispatching; the run stays resumable."""
    return ledger.append({
        "schema_version": ev.SCHEMA_VERSION,
        "event_id": ids.new_event_id(),
        "run_id": run_id,
        "event_type": "run_interrupt_requested",
        "occurred_at": ev.occurred_now(),
    })


def cancel_verification(ledger: Ledger, run_id: str, node_id: str,
                        attempt: int, verification_id: str) -> dict:
    """Graceful-interruption cancellation of the in-flight verification
    attempt: verification_status cancelled, verdict null (§6/§10)."""
    revents = ledger.run(run_id)
    reqs = [e for e in revents
            if e.get("event_type") == "verification_requested"
            and e.get("node_id") == node_id and e.get("attempt") == attempt
            and e.get("verification_id") == verification_id]
    if not reqs:
        raise ResumeRefused("no verification request to cancel")
    req = max(reqs, key=lambda r: r["verification_attempt"])
    return ledger.append(vf.verdict_recorded_event(
        run_id=run_id, node_id=node_id, attempt=attempt,
        verification_id=verification_id,
        verification_attempt=req["verification_attempt"],
        family=req["family"], actor="runtime",
        verification_status="cancelled", verdict=None,
        evidence_id=req["evidence_id"]))


def observe_orphans(ledger: Ledger, graph: dict, run_id: str,
                    still_in_progress) -> list[dict]:
    """Produce orphan evidence AT OBSERVATION for work whose non-continuity
    is constated by the injected callback (§10; concrete constatation is
    §13.4 — injected, not invented). Human verifications are never orphaned:
    the only clock for the human is the human (I9)."""
    if still_in_progress is None:
        return []
    emitted = []
    revents = ledger.run(run_id)
    folded = fold(graph, revents, run_id)
    for node_id, info in folded["nodes"].items():
        if info["state"] == "running":
            k = info["attempt"]
            if not still_in_progress({"kind": "attempt", "node_id": node_id,
                                      "attempt": k}):
                emitted.append(ledger.append({
                    "schema_version": ev.SCHEMA_VERSION,
                    "event_id": ids.new_event_id(),
                    "run_id": run_id,
                    "event_type": "orphan_detected",
                    "occurred_at": ev.occurred_now(),
                    "node_id": node_id,
                    "attempt": k,
                }))
    revents = ledger.run(run_id)
    outcomes = [e for e in revents if e.get("event_type") == "verdict_recorded"]
    for req in revents:
        if (req.get("event_type") != "verification_requested"
                or req.get("family") == "human"):
            continue
        closed = any(o.get("node_id") == req["node_id"]
                     and o.get("attempt") == req["attempt"]
                     and o.get("verification_id") == req["verification_id"]
                     and o.get("verification_attempt")
                     == req["verification_attempt"]
                     for o in outcomes)
        if closed:
            continue
        if not still_in_progress({"kind": "verification",
                                  "node_id": req["node_id"],
                                  "attempt": req["attempt"],
                                  "verification_id": req["verification_id"],
                                  "verification_attempt":
                                      req["verification_attempt"]}):
            emitted.append(ledger.append(vf.verdict_recorded_event(
                run_id=run_id, node_id=req["node_id"],
                attempt=req["attempt"],
                verification_id=req["verification_id"],
                verification_attempt=req["verification_attempt"],
                family=req["family"], actor="runtime",
                verification_status="error", verdict=None,
                reason="orphaned", evidence_id=req["evidence_id"])))
    return emitted


# -- resume (§8): the SAME run --------------------------------------------

def resume(ledger: Ledger, graph_text, input_text, run_id: str,
           still_in_progress=None) -> dict:
    """Resume the same run. Validates the frozen identity against
    run_created; observes orphans; advances verifications; returns the fold
    plus continuable work. Never decides anything; never dispatches (no
    transport exists yet — callers dispatch via dispatch_node)."""
    revents = ledger.run(run_id)
    if not revents:
        raise ResumeRefused(f"unknown run: {run_id}")
    if ledger.sequence_gaps().get(run_id):
        raise ResumeRefused(
            "unresolved seq gap — resume is a mutable action and is blocked "
            "until explicit reconciliation (I27, §13.16)")

    graph = load_graph(graph_text)
    folded = fold(graph, revents, run_id)
    identity = folded["identity"]
    if identity is None:
        raise ResumeRefused("no authoritative run_created — identity not "
                            "validatable; run is read-only diagnostic (§2)")
    current_gv = canonical.graph_version(graph_text)
    current_ih = canonical.input_hash(input_text)
    if (current_gv != identity["graph_version"]
            or current_ih != identity["input_hash"]):
        raise ResumeRefused(
            "frozen identity mismatch (I11): graph_version/input_hash differ "
            "from run_created — create a CHILD run with parent_run_id="
            + run_id)

    if folded["run_state"] == "cancelled":
        raise ResumeRefused("run is cancelled (absorbing) — create a child run")
    if folded["run_state"] == "landed":
        raise ResumeRefused(
            "run is landed — the human action that removes the motive "
            "(budget_extended / human_retry) must precede resume (§3)")

    observe_orphans(ledger, graph, run_id, still_in_progress)
    advance_verifications(ledger, graph, run_id)
    folded = fold(graph, ledger.run(run_id), run_id)
    return {
        "state": folded,
        "ready": [(nid, (i["attempt"] or 0) + 1)
                  for nid, i in folded["nodes"].items()
                  if i["state"] == "ready"],
    }


# -- landing / budget ------------------------------------------------------

def land_run(ledger: Ledger, graph: dict, run_id: str, reason: str) -> dict:
    """Emit run_landed when the run is grounded: not complete, nothing in
    flight, no gate pending (§3). Reason is the closed set (validated at
    write)."""
    folded = fold(graph, ledger.run(run_id), run_id)
    if folded["run_state"] not in ("stalled",):
        raise ResumeRefused(
            f"run is {folded['run_state']} — run_landed applies only to a "
            "grounded run (nothing in flight, not complete, no gate pending)")
    return ledger.append({
        "schema_version": ev.SCHEMA_VERSION,
        "event_id": ids.new_event_id(),
        "run_id": run_id,
        "event_type": "run_landed",
        "occurred_at": ev.occurred_now(),
        "reason": reason,
    })


def extend_budget(ledger: Ledger, run_id: str, new_budget, actor: str) -> dict:
    return ledger.append({
        "schema_version": ev.SCHEMA_VERSION,
        "event_id": ids.new_event_id(),
        "run_id": run_id,
        "event_type": "budget_extended",
        "occurred_at": ev.occurred_now(),
        "new_budget": new_budget,
        "actor": actor,
    })
