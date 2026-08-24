"""THE governed operational write boundary (audit hardening 1).

Every operational protocol mutation goes through here (or through the human
wing in dagwell.human, which applies the same guards): current run, frozen
graph, projected state and writer role are validated BEFORE any append. Raw
`Ledger.append` is storage-level (envelope + stream integrity) and is NOT a
public protocol mutation surface; future adapters receive narrow operation
functions from this module — never the Ledger, never authority to append
arbitrary protocol events.

The ledger remains the sole source of truth: this module holds no state.
"""

from dagwell import ids, verification as vf
from dagwell.fold import fold
from dagwell.graph import declared_verifications
from dagwell.ledger import Ledger, events as ev


class OperationRefused(ev.LedgerError):
    pass


def _base(run_id: str, event_type: str, **extra) -> dict:
    e = {
        "schema_version": ev.SCHEMA_VERSION,
        "event_id": ids.new_event_id(),
        "run_id": run_id,
        "event_type": event_type,
        "occurred_at": ev.occurred_now(),
    }
    e.update(extra)
    return e


def _guard(ledger: Ledger, graph: dict, run_id: str, *, allow_landed=False,
           allow_completed=False):
    revents = ledger.run(run_id)
    if not revents:
        raise OperationRefused(f"unknown run: {run_id}")
    if ledger.sequence_gaps().get(run_id):
        raise OperationRefused(
            "unresolved seq gap — mutable operations blocked (I27, §13.16)")
    folded = fold(graph, revents, run_id)   # refuses on frozen-graph mismatch
    if folded["run_state"] == "cancelled":
        raise OperationRefused("run is cancelled (absorbing terminal)")
    if folded["run_state"] == "completed" and not allow_completed:
        raise OperationRefused("run is completed (terminal)")
    if folded["run_state"] == "landed" and not allow_landed:
        raise OperationRefused(
            "run is landed — the motive-removing human event must come first (§3)")
    return folded, revents


def _node(folded, node_id):
    node = folded["nodes"].get(node_id)
    if node is None:
        raise OperationRefused(f"unknown node: {node_id}")
    return node


def _evidence_id_of(revents, node_id, k):
    for e in revents:
        if (e.get("event_type") == "node_returned"
                and e.get("node_id") == node_id and e.get("attempt") == k):
            return (e.get("output_evidence") or {}).get("evidence_id")
    return None


# -- producer operations ---------------------------------------------------

def dispatch(ledger: Ledger, graph: dict, run_id: str, node_id: str) -> dict:
    """Dispatch the node's next producer attempt. Refused unless the node is
    in the derived READY state — which encodes every gate: dependency-blocked
    (pending), completed, rejected/failed until an explicit human_retry
    reopens, waiting_human, and duplicate/in-flight attempts; run-level
    guards refuse cancelled/completed/landed runs and seq gaps."""
    folded, _ = _guard(ledger, graph, run_id)
    node = _node(folded, node_id)
    if node["state"] != "ready":
        raise OperationRefused(
            f"node {node_id} is {node['state']} — dispatch requires the "
            "ready derived state")
    attempt = (node["attempt"] or 0) + 1
    return ledger.append(_base(run_id, "node_dispatched", node_id=node_id,
                               attempt=attempt))


def record_return(ledger: Ledger, graph: dict, run_id: str, node_id: str,
                  attempt: int, exit_code: int, output_evidence=None) -> dict:
    folded, _ = _guard(ledger, graph, run_id)
    node = _node(folded, node_id)
    if node["state"] != "running" or node["attempt"] != attempt:
        raise OperationRefused(
            f"node {node_id} attempt {attempt} is not in flight "
            f"(state {node['state']}, attempt {node['attempt']})")
    e = _base(run_id, "node_returned", node_id=node_id, attempt=attempt,
              exit_code=exit_code)
    if output_evidence is not None:
        e["output_evidence"] = output_evidence
    return ledger.append(e)


# -- verification operations (machine-first enforced at the boundary) ------

def next_due(graph: dict, node_id: str, k: int, evidence_id: str,
             revents: list) -> tuple | None:
    """What the verification order requires next for the node's attempt:
    ("request", vid, family) | ("refire", vid, family) | ("escalate", vid)
    | None (in flight / nothing due / escalation unresolved)."""
    declared = declared_verifications(graph, node_id)

    def outcomes(vid, va=None):
        out = [e for e in revents
               if e.get("event_type") == "verdict_recorded"
               and e.get("node_id") == node_id and e.get("attempt") == k
               and e.get("verification_id") == vid]
        if va is not None:
            out = [o for o in out if o.get("verification_attempt") == va]
        return out

    def requests(vid):
        return [e for e in revents
                if e.get("event_type") == "verification_requested"
                and e.get("node_id") == node_id and e.get("attempt") == k
                and e.get("verification_id") == vid]

    def open_request(vid):
        return any(not outcomes(vid, r["verification_attempt"])
                   for r in requests(vid))

    def approved(vid):
        return any(o.get("verification_status") == "completed"
                   and o.get("verdict") == "approved"
                   and o.get("evidence_id") == evidence_id
                   for o in outcomes(vid))

    esc = [e for e in revents if e.get("event_type") == "human_escalation"
           and e.get("node_id") == node_id and e.get("attempt") == k]
    if esc:
        last = max(e["seq"] for e in esc)
        unresolved = not any(
            e.get("node_id") == node_id and e.get("attempt") == k
            and e["seq"] > last
            and (e.get("event_type") == "human_retry"
                 or (e.get("event_type") == "verdict_recorded"
                     and e.get("family") == "human"))
            for e in revents)
        if unresolved:
            return None

    for v in declared:
        if v["family"] == "human":
            continue
        vid = v["verification_id"]
        if approved(vid):
            continue
        if open_request(vid):
            return None
        prior = outcomes(vid)
        if prior:
            last = max(prior, key=lambda o: o["seq"])
            if last.get("verification_status") == "cancelled":
                return ("refire", vid, v["family"])
            return ("escalate", vid)
        return ("request", vid, v["family"])

    for v in declared:
        if v["family"] != "human":
            continue
        vid = v["verification_id"]
        if not approved(vid) and not open_request(vid):
            return ("request", vid, "human")
    return None


def request_verification(ledger: Ledger, graph: dict, run_id: str,
                         node_id: str, verification_id: str) -> dict:
    """Emit verification_requested for the verification the ORDER requires
    next (§4: machines first, human gate last). Requesting anything else is
    refused at this boundary."""
    folded, revents = _guard(ledger, graph, run_id)
    node = _node(folded, node_id)
    if node["state"] not in ("executed", "verifying"):
        raise OperationRefused(
            f"node {node_id} is {node['state']} — no verification is due")
    k = node["attempt"]
    evidence_id = _evidence_id_of(revents, node_id, k)
    due = next_due(graph, node_id, k, evidence_id, revents)
    if due is None or due[0] == "escalate":
        raise OperationRefused(
            "no verification request is due (in flight, unresolved "
            "escalation, or escalation required)")
    kind, vid, family = due
    if vid != verification_id:
        raise OperationRefused(
            f"machine-first ordering (§4): next due is {vid!r}, "
            f"not {verification_id!r}")
    va = vf.next_verification_attempt(revents, node_id, k, vid)
    return ledger.append(vf.verification_requested_event(
        run_id=run_id, node_id=node_id, attempt=k, verification_id=vid,
        verification_attempt=va, family=family, evidence_id=evidence_id))


def record_machine_verdict(ledger: Ledger, graph: dict, run_id: str,
                           node_id: str, verification_id: str, *,
                           verification_status: str, verdict=None,
                           actor: str, reason=None) -> dict:
    """Record a NON-human verdict for the open verification attempt.
    family: human is refused here — human verdicts exist only through the
    governed human operation (I8)."""
    folded, revents = _guard(ledger, graph, run_id)
    node = _node(folded, node_id)
    k = node["attempt"]
    reqs = [e for e in revents
            if e.get("event_type") == "verification_requested"
            and e.get("node_id") == node_id and e.get("attempt") == k
            and e.get("verification_id") == verification_id]
    if not reqs:
        raise OperationRefused("no verification request to conclude")
    req = max(reqs, key=lambda r: r["verification_attempt"])
    if req["family"] == "human":
        raise OperationRefused(
            "human verdicts are written only by the governed human "
            "operation (I8)")
    return ledger.append(vf.verdict_recorded_event(
        run_id=run_id, node_id=node_id, attempt=k,
        verification_id=verification_id,
        verification_attempt=req["verification_attempt"],
        family=req["family"], actor=actor,
        verification_status=verification_status, verdict=verdict,
        evidence_id=req["evidence_id"], reason=reason))


def escalate(ledger: Ledger, graph: dict, run_id: str, node_id: str) -> dict:
    """Emit human_escalation — legal only when the order says escalation is
    due (verifier failure outcome under the zero automatic-re-fire policy)."""
    folded, revents = _guard(ledger, graph, run_id)
    node = _node(folded, node_id)
    k = node["attempt"]
    evidence_id = _evidence_id_of(revents, node_id, k)
    due = next_due(graph, node_id, k, evidence_id, revents)
    if not due or due[0] != "escalate":
        raise OperationRefused("escalation is not due for this node")
    return ledger.append(_base(run_id, "human_escalation", node_id=node_id,
                               attempt=k, reason="verifier_error"))


def cancel_verification(ledger: Ledger, graph: dict, run_id: str,
                        node_id: str, verification_id: str) -> dict:
    """Graceful-interruption cancellation of the open verification attempt
    (status cancelled, verdict null) — never counted against re-fire."""
    folded, revents = _guard(ledger, graph, run_id)
    reqs = [e for e in revents
            if e.get("event_type") == "verification_requested"
            and e.get("node_id") == node_id
            and e.get("verification_id") == verification_id]
    if not reqs:
        raise OperationRefused("no verification request to cancel")
    req = max(reqs, key=lambda r: r["verification_attempt"])
    return ledger.append(vf.verdict_recorded_event(
        run_id=run_id, node_id=node_id, attempt=req["attempt"],
        verification_id=verification_id,
        verification_attempt=req["verification_attempt"],
        family=req["family"], actor="runtime",
        verification_status="cancelled", verdict=None,
        evidence_id=req["evidence_id"]))


# -- run-level operations --------------------------------------------------

def request_interrupt(ledger: Ledger, graph: dict, run_id: str) -> dict:
    _guard(ledger, graph, run_id, allow_landed=True)
    return ledger.append(_base(run_id, "run_interrupt_requested"))


def land_run(ledger: Ledger, graph: dict, run_id: str, reason: str) -> dict:
    folded, _ = _guard(ledger, graph, run_id)
    if folded["run_state"] != "stalled":
        raise OperationRefused(
            f"run is {folded['run_state']} — run_landed applies only to a "
            "grounded run (§3)")
    return ledger.append(_base(run_id, "run_landed", reason=reason))


def extend_budget(ledger: Ledger, graph: dict, run_id: str, new_budget,
                  actor: str) -> dict:
    _guard(ledger, graph, run_id, allow_landed=True)
    return ledger.append(_base(run_id, "budget_extended",
                               new_budget=new_budget, actor=actor))
