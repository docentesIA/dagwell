"""Human decision operations (contract §5, I8, I9, I10).

These are the GOVERNED domain operations: every presentation surface (CLI
today, any UI/API later) must call through here — the human-only write
privilege and its preconditions live below presentation, never in it. Only
these operations produce family: human verdicts; no agent or adapter has this
verb. Silence never approves: absence of a decision leaves waiting_human
forever — there is no timeout here, by construction.

Remote actor authentication is §13.8 and remains open: the actor is the local
user under process control.
"""

from dagwell import verification as vf
from dagwell.fold import fold
from dagwell.graph import declared_verifications
from dagwell.ledger import Ledger, events as ev
from dagwell import ids


class DecisionRefused(ev.LedgerError):
    """The human operation's preconditions are not met."""


def _fold_for(ledger: Ledger, graph: dict, run_id: str):
    revents = ledger.run(run_id)
    if not revents:
        raise DecisionRefused(f"unknown run: {run_id}")
    return fold(graph, revents, run_id), revents


def _guard_mutable(ledger: Ledger, folded: dict, run_id: str) -> None:
    if folded["run_state"] == "cancelled":
        raise DecisionRefused("run is cancelled — human decisions are refused")
    if ledger.sequence_gaps().get(run_id):
        raise DecisionRefused(
            "unresolved seq gap — mutable actions blocked (I27, §13.16)")


def decide(ledger: Ledger, graph: dict, run_id: str, node_id: str,
           verdict: str, actor: str, reason: str | None = None) -> dict:
    """Record the human verdict for the node's pending human verification.

    Covers both the declared gate (open family-human request) and the
    escalation path (§4): on human_escalation the human ASSUMES the
    substituted verification — a new verification_attempt is opened with
    family human (the escalation event in the ledger is the auditable
    exception to same-family consecutivity) and concluded by this verdict.
    """
    if verdict not in ("approved", "rejected"):
        raise DecisionRefused(f"verdict must be approved|rejected, got {verdict!r}")
    folded, revents = _fold_for(ledger, graph, run_id)
    _guard_mutable(ledger, folded, run_id)

    node = folded["nodes"].get(node_id)
    if node is None:
        raise DecisionRefused(f"unknown node: {node_id}")
    if node["state"] != "waiting_human":
        raise DecisionRefused(
            f"node {node_id} is {node['state']}, not waiting_human — "
            "nothing to decide")
    k = node["attempt"]

    open_human = [
        req for req in revents
        if req.get("event_type") == "verification_requested"
        and req.get("node_id") == node_id and req.get("attempt") == k
        and req.get("family") == "human"
        and not any(o.get("event_type") == "verdict_recorded"
                    and o.get("node_id") == node_id
                    and o.get("attempt") == k
                    and o.get("verification_id") == req.get("verification_id")
                    and o.get("verification_attempt")
                    == req.get("verification_attempt")
                    for o in revents)
    ]
    if open_human:
        req = open_human[0]
        vid, va, evidence_id = (req["verification_id"],
                                req["verification_attempt"],
                                req["evidence_id"])
    else:
        # escalation: assume the first declared non-human verification that
        # still lacks an authoritative completed verdict
        vid, evidence_id = _substituted_verification(graph, node_id, k, revents)
        va = vf.next_verification_attempt(revents, node_id, k, vid)
        ledger.append(vf.verification_requested_event(
            run_id=run_id, node_id=node_id, attempt=k, verification_id=vid,
            verification_attempt=va, family="human", evidence_id=evidence_id))

    return ledger.append(vf.verdict_recorded_event(
        run_id=run_id, node_id=node_id, attempt=k, verification_id=vid,
        verification_attempt=va, family="human", actor=actor,
        verification_status="completed", verdict=verdict,
        evidence_id=evidence_id, reason=reason))


def _substituted_verification(graph, node_id, k, revents):
    evidence_id = None
    for e in revents:
        if (e.get("event_type") == "node_returned"
                and e.get("node_id") == node_id and e.get("attempt") == k):
            evidence_id = (e.get("output_evidence") or {}).get("evidence_id")
    if evidence_id is None:
        raise DecisionRefused("no output evidence recorded for the attempt")
    for v in declared_verifications(graph, node_id):
        if v["family"] == "human":
            continue
        vid = v["verification_id"]
        done = any(o.get("event_type") == "verdict_recorded"
                   and o.get("node_id") == node_id and o.get("attempt") == k
                   and o.get("verification_id") == vid
                   and o.get("verification_status") == "completed"
                   and o.get("evidence_id") == evidence_id
                   for o in revents)
        if not done:
            return vid, evidence_id
    raise DecisionRefused("no substitutable verification found for escalation")


def human_retry(ledger: Ledger, graph: dict, run_id: str, node_id: str,
                actor: str) -> dict:
    """THE single human verb that opens producer attempt k+1 (I10).

    Defined over: a rejected node; a failed node whose automatic-retry policy
    is exhausted — with no Runtime Policy Specification (§13.12) automatic
    retry is disabled, so the policy is exhausted at zero; and waiting_human
    reached through human_escalation. On a normally-declared human gate the
    auditable path is decide(), never retry. Never re-arms a verifier.
    """
    folded, revents = _fold_for(ledger, graph, run_id)
    _guard_mutable(ledger, folded, run_id)
    node = folded["nodes"].get(node_id)
    if node is None:
        raise DecisionRefused(f"unknown node: {node_id}")
    state, k = node["state"], node["attempt"]
    if state == "rejected" or state == "failed":
        pass
    elif state == "waiting_human" and any(
            e.get("event_type") == "human_escalation"
            and e.get("node_id") == node_id and e.get("attempt") == k
            for e in revents):
        pass
    else:
        raise DecisionRefused(
            f"human_retry is not defined for node state {state!r} — "
            "on a declared human gate, decide instead (I10)")
    e = {
        "schema_version": ev.SCHEMA_VERSION,
        "event_id": ids.new_event_id(),
        "run_id": run_id,
        "event_type": "human_retry",
        "occurred_at": ev.occurred_now(),
        "node_id": node_id,
        "attempt": k,
        "actor": actor,
    }
    return ledger.append(e)


def cancel_run(ledger: Ledger, graph: dict, run_id: str, actor: str) -> dict:
    """Cancel the run (absorbing terminal). Idempotent: cancelling a
    cancelled run returns the existing event."""
    folded, revents = _fold_for(ledger, graph, run_id)
    for e in revents:
        if e.get("event_type") == "run_cancelled":
            return e
    if ledger.sequence_gaps().get(run_id):
        raise DecisionRefused(
            "unresolved seq gap — mutable actions blocked (I27)")
    e = {
        "schema_version": ev.SCHEMA_VERSION,
        "event_id": ids.new_event_id(),
        "run_id": run_id,
        "event_type": "run_cancelled",
        "occurred_at": ev.occurred_now(),
        "actor": actor,
    }
    return ledger.append(e)
