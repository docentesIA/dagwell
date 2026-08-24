"""Deterministic state projection (contract §3, §4, §7 — the fold).

events + frozen graph -> projected state. Pure: no I/O, no clock, no policy —
the projection uses only facts materialized in events (I3). Ordering is seq,
never timestamps (I20). seq collision refuses computation (fail closed);
duplicate event_id keeps the first by seq authoritative and flags the rest;
an unresolved seq gap yields a DIAGNOSTIC projection marked
integrity: "degraded" — a derived view, never persisted state (P3/I27); the
write-side block of mutable actions lives in the ledger, not here.
"""

from dagwell.evidence import evidence_is_valid
from dagwell.graph import (
    declared_evidence_type,
    declared_verifications,
)
from dagwell.ledger import events as ev

RUN_STATES = ("cancelled", "completed", "landed", "running", "waiting_human",
              "created", "stalled")
LANDED_REASONS = frozenset({"budget_exhausted", "retries_exhausted",
                            "human_rejection"})


def fold(graph: dict, events: list[dict], run_id: str) -> dict:
    revents = [e for e in events if e.get("run_id") == run_id]
    anomalies: list[str] = []

    seqs = [e.get("seq") for e in revents]
    if len(seqs) != len(set(seqs)):
        raise ev.LedgerIntegrityError(
            f"run {run_id}: seq collision — fold refuses to compute (I20)")
    revents.sort(key=lambda e: e["seq"])

    # duplicate event_id: first by seq authoritative, later ignored + flagged
    seen_ids: set = set()
    deduped = []
    for e in revents:
        eid = e.get("event_id")
        if eid in seen_ids:
            anomalies.append(f"duplicate event_id ignored: {eid}")
            continue
        seen_ids.add(eid)
        deduped.append(e)
    revents = deduped

    integrity = "ok"
    if revents:
        expected = set(range(ev.FIRST_SEQ, max(e["seq"] for e in revents) + 1))
        missing = sorted(expected - {e["seq"] for e in revents})
        if missing:
            integrity = "degraded"
            anomalies.append(f"unresolved seq gap: missing {missing} (I27)")

    revents = _normalize(revents, anomalies)

    founders = [e for e in revents if e.get("event_type") == "run_created"]
    identity = None
    if founders:
        identity = {f: founders[0].get(f) for f in ev.RUN_CREATED_FIELDS}
        identity["graph_id"] = founders[0].get("graph_id")
        for extra in founders[1:]:
            anomalies.append(
                f"non-authoritative run_created ignored (seq {extra['seq']})")
    else:
        integrity = "degraded"
        anomalies.append("no authoritative run_created — identity not validatable")

    if identity is not None:
        if founders[0]["seq"] != ev.FIRST_SEQ:
            anomalies.append(
                f"run_created is not the first logical event "
                f"(seq {founders[0]['seq']}) — historical violation")
        if graph.get("graph_version") and \
                identity.get("graph_version") != graph["graph_version"]:
            raise ev.LedgerIntegrityError(
                "frozen graph mismatch (I24): the supplied graph does not "
                "correspond to run_created.graph_version — fold refused")
        if graph.get("graph_id") and identity.get("graph_id") \
                and identity["graph_id"] != graph["graph_id"]:
            raise ev.LedgerIntegrityError(
                "graph_id mismatch: supplied graph is not this run's graph")

    cancelled = any(e.get("event_type") == "run_cancelled" for e in revents)

    nodes = {}
    for node_id in graph["nodes"]:
        nodes[node_id] = _node_projection(graph, node_id, revents)

    # derived views: pending/ready for undispatched or reopened nodes
    for node_id, info in nodes.items():
        if info["state"] is None:
            deps = graph["nodes"][node_id].get("deps", [])
            deps_done = all(nodes[d]["state"] == "completed" for d in deps)
            info["state"] = "ready" if deps_done else "pending"
            info["view"] = True

    if cancelled:
        for info in nodes.values():
            if info["state"] not in ("completed", "failed", "rejected"):
                info["state"] = "cancelled"
                info["view"] = True

    run_state = _run_projection(graph, nodes, revents, cancelled)

    checkpoint = sorted(nid for nid, i in nodes.items()
                        if i["state"] == "completed")
    return {
        "run_id": run_id,
        "run_state": run_state,
        "integrity": integrity,
        "anomalies": anomalies,
        "identity": identity,
        "nodes": nodes,
        "checkpoint": checkpoint,
    }


# -- node projection (contract §4) ----------------------------------------

def _node_projection(graph, node_id, revents):
    nevents = [e for e in revents if e.get("node_id") == node_id]
    dispatches = [e for e in nevents if e.get("event_type") == "node_dispatched"]
    if not dispatches:
        return {"state": None, "attempt": None, "view": False}
    k = max(e["attempt"] for e in dispatches)

    state = _attempt_state(graph, node_id, k, nevents)

    retry_seqs = [e["seq"] for e in nevents
                  if e.get("event_type") == "human_retry"
                  and e.get("attempt") == k]
    escalated = any(e.get("event_type") == "human_escalation"
                    and e.get("attempt") == k for e in nevents)
    if (retry_seqs
            and max(retry_seqs) > _terminalizing_seq(nevents, k)
            and (state in ("failed", "rejected") or escalated)):
        # reopened by the explicit human command (I10): node returns to the
        # pending/ready derived view awaiting dispatch of attempt k+1
        return {"state": None, "attempt": k, "view": False}
    return {"state": state, "attempt": k, "view": False}


def _terminalizing_seq(nevents, k):
    seqs = [e["seq"] for e in nevents if e.get("attempt") == k
            and e.get("event_type") in ("node_returned", "orphan_detected",
                                        "verdict_recorded", "human_escalation")]
    return max(seqs) if seqs else 0


def _attempt_state(graph, node_id, k, nevents):
    kevents = [e for e in nevents if e.get("attempt") == k]
    returned = next((e for e in kevents
                     if e.get("event_type") == "node_returned"), None)
    if returned is None:
        # orphan_detected only acts on a running attempt; on anything else it
        # is inert (the recorded return wins) — here there IS no return.
        if any(e.get("event_type") == "orphan_detected" for e in kevents):
            return "failed"
        return "running"

    etype = declared_evidence_type(graph, node_id)
    evd = returned.get("output_evidence")
    transport_ok = returned.get("exit_code") == 0
    evidence_ok = evd is not None and evidence_is_valid(evd, etype)
    if not (transport_ok and evidence_ok):
        return "failed"

    return _verification_progress(graph, node_id, k, evd["evidence_id"], nevents)


def _verification_progress(graph, node_id, k, evidence_id, nevents):
    declared = declared_verifications(graph, node_id)
    if not declared:
        return "completed"  # declared vacuum (validated at graph load, I5)

    def authoritative(vid):
        for e in nevents:  # seq order preserved
            if (e.get("event_type") == "verdict_recorded"
                    and e.get("attempt") == k
                    and e.get("verification_id") == vid
                    and e.get("verification_status") == "completed"
                    and e.get("evidence_id") == evidence_id):
                return e
        return None

    verdicts = {v["verification_id"]: authoritative(v["verification_id"])
                for v in declared}

    for v in declared:
        a = verdicts[v["verification_id"]]
        if a and a["verdict"] == "rejected":
            # partition by author (§4): the human refused vs the machine refused
            return "rejected" if a.get("family") == "human" else "failed"

    if all(a and a["verdict"] == "approved" for a in verdicts.values()):
        return "completed"

    requests = [e for e in nevents
                if e.get("event_type") == "verification_requested"
                and e.get("attempt") == k]
    outcomes = [e for e in nevents
                if e.get("event_type") == "verdict_recorded"
                and e.get("attempt") == k]

    def open_request(req):
        return not any(o.get("verification_id") == req.get("verification_id")
                       and o.get("verification_attempt")
                       == req.get("verification_attempt")
                       for o in outcomes)

    if any(req.get("family") == "human" and open_request(req)
           for req in requests):
        return "waiting_human"
    esc = [e for e in nevents
           if e.get("event_type") == "human_escalation"
           and e.get("attempt") == k]
    if esc:
        last = max(e["seq"] for e in esc)
        resolved = any(
            e.get("attempt") == k and e["seq"] > last
            and (e.get("event_type") == "human_retry"
                 or (e.get("event_type") == "verdict_recorded"
                     and e.get("family") == "human"))
            for e in nevents)
        if not resolved:
            return "waiting_human"
    if not requests:
        return "executed"
    return "verifying"


# -- run projection (contract §3, exact precedence) ------------------------

def _run_projection(graph, nodes, revents, cancelled):
    if cancelled:
        return "cancelled"
    if all(i["state"] == "completed" for i in nodes.values()):
        return "completed"

    landed = [e for e in revents if e.get("event_type") == "run_landed"]
    if landed:
        last = landed[-1]
        reason = last.get("reason")
        removed = False
        if reason == "budget_exhausted":
            removed = any(e.get("event_type") == "budget_extended"
                          and e["seq"] > last["seq"] for e in revents)
        elif reason in ("human_rejection", "retries_exhausted"):
            removed = any(e.get("event_type") == "human_retry"
                          and e["seq"] > last["seq"] for e in revents)
        if not removed:
            return "landed"

    in_flight_attempt = any(i["state"] == "running" for i in nodes.values())
    in_flight_verification = _open_nonhuman_verification(revents)
    if in_flight_attempt or in_flight_verification:
        return "running"

    if any(i["state"] == "waiting_human" for i in nodes.values()):
        return "waiting_human"

    if (any(e.get("event_type") == "run_created" for e in revents)
            and not any(e.get("event_type") == "node_dispatched"
                        for e in revents)):
        return "created"
    return "stalled"


def _open_nonhuman_verification(revents):
    outcomes = [e for e in revents if e.get("event_type") == "verdict_recorded"]
    for req in revents:
        if (req.get("event_type") == "verification_requested"
                and req.get("family") != "human"):
            if not any(o.get("node_id") == req.get("node_id")
                       and o.get("attempt") == req.get("attempt")
                       and o.get("verification_id") == req.get("verification_id")
                       and o.get("verification_attempt")
                       == req.get("verification_attempt")
                       for o in outcomes):
                return True
    return False


# -- read-side authority/integrity normalization (audit hardening 2) -------

def _normalize(revents, anomalies):
    """Make causally impossible or malformed historical facts inert and
    signaled (never repaired in place): unsupported schema versions;
    malformed required domain fields; verdicts without a matching request or
    with divergent binding; human substitution without the auditable
    escalation precondition. First-by-seq behavior is preserved where the
    contract defines it."""
    normalized = []
    requests = []      # accepted verification_requested events
    escalations = []   # accepted human_escalation events
    for e in revents:
        seq = e.get("seq")
        if e.get("schema_version") != ev.SCHEMA_VERSION:
            anomalies.append(
                f"unsupported schema_version {e.get('schema_version')!r} — "
                f"event inert (seq {seq})")
            continue
        try:
            ev.validate_event(e)
        except ev.EventValidationError as exc:
            anomalies.append(f"malformed event inert (seq {seq}): {exc}")
            continue
        etype = e["event_type"]
        if etype == "verification_requested":
            requests.append(e)
        elif etype == "human_escalation":
            escalations.append(e)
        elif etype == "verdict_recorded":
            req = next(
                (r for r in requests
                 if r.get("node_id") == e.get("node_id")
                 and r.get("attempt") == e.get("attempt")
                 and r.get("verification_id") == e.get("verification_id")
                 and r.get("verification_attempt")
                 == e.get("verification_attempt")),
                None)
            if req is None:
                anomalies.append(
                    f"verdict without matching verification_requested — "
                    f"inert (seq {seq})")
                continue
            if e.get("evidence_id") != req.get("evidence_id"):
                anomalies.append(
                    f"verdict bound to divergent evidence_id — inert "
                    f"(seq {seq})")
                continue
            if e.get("family") != req.get("family"):
                if e.get("family") != "human":
                    anomalies.append(
                        f"verdict family mismatch — inert (seq {seq})")
                    continue
                substituted = any(
                    esc.get("node_id") == e.get("node_id")
                    and esc.get("attempt") == e.get("attempt")
                    and esc["seq"] < seq
                    for esc in escalations)
                if not substituted:
                    anomalies.append(
                        f"human substitution without human_escalation — "
                        f"inert (seq {seq})")
                    continue
        normalized.append(e)
    return normalized
