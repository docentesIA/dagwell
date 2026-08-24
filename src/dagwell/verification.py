"""Verification event builders (contract §5, §6).

Two separate axes: verification_status (process) × verdict (merit, binary).
attempt identifies the PRODUCER's try; verification_attempt identifies the
VERIFIER's try (P2). Every verdict binds to
(run_id, node_id, attempt, verification_id, verification_attempt, evidence_id).
"""

from dagwell import ids
from dagwell.ledger import events as ev


def next_verification_attempt(run_events, node_id: str, attempt: int,
                              verification_id: str) -> int:
    prev = [e["verification_attempt"] for e in run_events
            if e.get("event_type") == "verification_requested"
            and e.get("node_id") == node_id and e.get("attempt") == attempt
            and e.get("verification_id") == verification_id]
    return (max(prev) + 1) if prev else ev.FIRST_VERIFICATION_ATTEMPT


def verification_requested_event(*, run_id, node_id, attempt, verification_id,
                                 verification_attempt, family, evidence_id,
                                 artifact_digest=None) -> dict:
    e = {
        "schema_version": ev.SCHEMA_VERSION,
        "event_id": ids.new_event_id(),
        "run_id": run_id,
        "event_type": "verification_requested",
        "occurred_at": ev.occurred_now(),
        "node_id": node_id,
        "attempt": attempt,
        "verification_id": verification_id,
        "verification_attempt": verification_attempt,
        "family": family,
        "evidence_id": evidence_id,
    }
    if artifact_digest is not None:
        e["artifact_digest"] = artifact_digest
    return e


def verdict_recorded_event(*, run_id, node_id, attempt, verification_id,
                           verification_attempt, family, actor,
                           verification_status, evidence_id, verdict=None,
                           reason=None, artifact_digest=None) -> dict:
    e = {
        "schema_version": ev.SCHEMA_VERSION,
        "event_id": ids.new_event_id(),
        "run_id": run_id,
        "event_type": "verdict_recorded",
        "occurred_at": ev.occurred_now(),
        "node_id": node_id,
        "attempt": attempt,
        "verification_id": verification_id,
        "verification_attempt": verification_attempt,
        "family": family,
        "actor": actor,
        "verification_status": verification_status,
        "verdict": verdict,
        "evidence_id": evidence_id,
    }
    if reason is not None:
        e["reason"] = reason
    if artifact_digest is not None:
        e["artifact_digest"] = artifact_digest
    return e
