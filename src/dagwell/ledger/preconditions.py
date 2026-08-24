"""Domain write preconditions, checked under the ledger lock before append.

Contract grounding: §5/§6 verdict preconditions (P2 attempt closure, §6
identity-level authoritativeness, evidence binding P5), §4 verification
ordering over produced evidence. check() returns None to proceed with the
write, or an EXISTING event to signal an idempotent no-op (identical duplicate
decision — contract §5/§6); it raises to refuse.
"""

from dagwell.ledger import events as ev


def check(event: dict, run_events: list[dict]):
    etype = event.get("event_type")
    if etype == "verification_requested":
        _check_request(event, run_events)
    elif etype == "verdict_recorded":
        return _check_verdict(event, run_events)
    return None


# -- helpers ---------------------------------------------------------------

def _vid_key(e):
    return (e.get("node_id"), e.get("attempt"), e.get("verification_id"))


def _requests_for(run_events, key):
    return [e for e in run_events
            if e.get("event_type") == "verification_requested" and _vid_key(e) == key]


def _outcomes_for(run_events, key, verification_attempt=None):
    out = [e for e in run_events
           if e.get("event_type") == "verdict_recorded" and _vid_key(e) == key]
    if verification_attempt is not None:
        out = [e for e in out
               if e.get("verification_attempt") == verification_attempt]
    return out


def _returned_evidence_id(run_events, node_id, attempt):
    for e in run_events:
        if (e.get("event_type") == "node_returned"
                and e.get("node_id") == node_id and e.get("attempt") == attempt):
            evd = e.get("output_evidence") or {}
            return evd.get("evidence_id")
    return None


# -- verification_requested ------------------------------------------------

def _check_request(event, run_events):
    node_id, attempt = event["node_id"], event["attempt"]
    if not any(e.get("event_type") == "node_dispatched"
               and e.get("node_id") == node_id and e.get("attempt") == attempt
               for e in run_events):
        raise ev.EventValidationError(
            f"verification_requested for undispatched attempt "
            f"({node_id}, {attempt})")
    recorded = _returned_evidence_id(run_events, node_id, attempt)
    if recorded is None:
        raise ev.EventValidationError(
            "verification_requested before output evidence exists for the attempt")
    if recorded != event["evidence_id"]:
        raise ev.LedgerIntegrityError(
            "verification_requested bound to divergent evidence_id (P5)")

    key = _vid_key(event)
    prev = _requests_for(run_events, key)
    next_va = (max(e["verification_attempt"] for e in prev) + 1) if prev \
        else ev.FIRST_VERIFICATION_ATTEMPT
    if event["verification_attempt"] != next_va:
        raise ev.LedgerIntegrityError(
            f"verification_attempt must be {next_va} (monotonic, P2), "
            f"got {event['verification_attempt']}")
    if prev:
        last_va = next_va - 1
        outcomes = _outcomes_for(run_events, key, last_va)
        if not outcomes:
            raise ev.LedgerIntegrityError(
                f"previous verification_attempt {last_va} is still open — "
                "no re-fire without a recorded outcome")
        if any(o.get("verification_status") == "completed" for o in outcomes):
            raise ev.LedgerIntegrityError(
                "verification already completed for this attempt/evidence — "
                "re-fire refused (§6)")


# -- verdict_recorded ------------------------------------------------------

def _check_verdict(event, run_events):
    key = _vid_key(event)
    va = event["verification_attempt"]
    requests = [e for e in _requests_for(run_events, key)
                if e.get("verification_attempt") == va]
    if not requests:
        raise ev.EventValidationError(
            "verdict_recorded without a matching verification_requested "
            f"(verification_attempt {va})")
    request = requests[0]
    if event["evidence_id"] != request["evidence_id"]:
        raise ev.LedgerIntegrityError(
            "verdict bound to divergent evidence_id — decision refused (P5, §5)")
    if event["family"] != request["family"] and event["family"] != "human":
        # human substitution during escalation is the single legitimate
        # family override (contract §4); anything else is refused.
        raise ev.LedgerIntegrityError(
            f"verdict family {event['family']!r} does not match requested "
            f"family {request['family']!r}")

    # P2: a closed verification attempt accepts no second outcome.
    closed = _outcomes_for(run_events, key, va)
    if closed:
        prior = closed[0]
        if (prior.get("verification_status") == event.get("verification_status")
                and prior.get("verdict") == event.get("verdict")
                and prior.get("evidence_id") == event.get("evidence_id")):
            return prior  # identical duplicate: idempotent no-op
        raise ev.LedgerIntegrityError(
            "verification_attempt already closed — conflicting outcome refused (P2)")

    # §6: one authoritative completed verdict per (verification_id, attempt,
    # evidence_id) across ALL verification_attempts.
    if event.get("verification_status") == "completed":
        for o in _outcomes_for(run_events, key):
            if (o.get("verification_status") == "completed"
                    and o.get("evidence_id") == event.get("evidence_id")):
                if o.get("verdict") == event.get("verdict"):
                    return o  # identical duplicate at identity level: no-op
                raise ev.LedgerIntegrityError(
                    "conflicting verdict for an identity that already has an "
                    "authoritative completed verdict (§6)")
    return None
