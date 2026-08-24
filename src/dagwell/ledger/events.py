"""Canonical event vocabulary, envelope and run_created (contract §2, §9).

All canonical identifiers are English and enter the ledger only in canonical
form (contract, emenda H1). schema_version "1" pins canonicalization scheme c1
(ADR-0003) and FIRST_SEQ = 1.
"""

from datetime import datetime

from dagwell import ids

SCHEMA_VERSION = "1"
FIRST_SEQ = 1

EVENT_TYPES = frozenset({
    "run_created",
    "node_dispatched",
    "node_returned",
    "verification_requested",
    "verdict_recorded",
    "orphan_detected",
    "budget_extended",
    "human_escalation",
    "human_retry",
    "run_interrupt_requested",
    "run_landed",
    "run_cancelled",
})

ENVELOPE_FIELDS = (
    "schema_version", "event_id", "run_id", "seq", "event_type", "occurred_at",
)
RUN_CREATED_FIELDS = (
    "graph_id", "graph_version", "input_hash", "input_ref", "parent_run_id",
)


class LedgerError(Exception):
    """Base for all ledger failures."""


class EventValidationError(LedgerError):
    """The event is malformed or violates a write precondition."""


class LedgerIntegrityError(LedgerError):
    """The ledger content violates an integrity invariant."""


def occurred_now() -> str:
    """Observational timestamp, local timezone with explicit offset."""
    return datetime.now().astimezone().isoformat()


def run_created_event(*, graph_id: str, graph_version: str, input_hash: str,
                      input_ref: str, parent_run_id: str | None = None,
                      run_id: str | None = None) -> dict:
    """Founding event carrying the frozen run identity (contract §2).

    No seq: the ledger assigns it at append.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": ids.new_event_id(),
        "run_id": run_id or ids.new_run_id(),
        "event_type": "run_created",
        "occurred_at": occurred_now(),
        "graph_id": graph_id,
        "graph_version": graph_version,
        "input_hash": input_hash,
        "input_ref": input_ref,
        "parent_run_id": parent_run_id,
    }


def validate_event(event: dict) -> None:
    """Hard write validation: refuse before recording (contract §9, I20)."""
    for field in ENVELOPE_FIELDS:
        if field not in event:
            raise EventValidationError(f"missing envelope field: {field}")
    for field in ("schema_version", "event_id", "run_id", "occurred_at"):
        if not isinstance(event[field], str) or not event[field]:
            raise EventValidationError(f"{field} must be a non-empty string")
    if event["event_type"] not in EVENT_TYPES:
        raise EventValidationError(
            f"unknown event_type: {event['event_type']!r} (canonical English enum only)")
    if not isinstance(event["seq"], int) or isinstance(event["seq"], bool) \
            or event["seq"] < FIRST_SEQ:
        raise EventValidationError(f"invalid seq: {event['seq']!r}")
    if event["event_type"] == "run_created":
        for field in RUN_CREATED_FIELDS:
            if field not in event:
                raise EventValidationError(f"run_created missing identity field: {field}")
        for field in ("graph_id", "graph_version", "input_hash", "input_ref"):
            if not isinstance(event[field], str) or not event[field]:
                raise EventValidationError(
                    f"run_created identity field must be a non-empty string: {field}")
        parent = event["parent_run_id"]
        if parent is not None and (not isinstance(parent, str) or not parent):
            raise EventValidationError("parent_run_id must be null or a non-empty string")
