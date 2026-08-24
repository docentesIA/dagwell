"""Canonical event vocabulary, envelope and run_created (contract §2, §9).

All canonical identifiers are English and enter the ledger only in canonical
form (contract, emenda H1). schema_version "1" pins canonicalization scheme c1
(ADR-0003) and FIRST_SEQ = 1.
"""

import re
from datetime import datetime

from dagwell import ids

SCHEMA_VERSION = "1"
FIRST_SEQ = 1
# §13.18 note: initial verification_attempt pinned to the contract's own
# illustrative value (§6 examples) under schema_version "1"; the formal
# encoding specification remains open.
FIRST_VERIFICATION_ATTEMPT = 1

VERIFICATION_STATUS = frozenset({"completed", "error", "timeout", "cancelled"})
VERDICT = frozenset({"approved", "rejected"})
# family is closed IN FORM (contract §6); the model:<family> namespace is §13.15.
_MODEL_FAMILY_RE = re.compile(r"^model:[A-Za-z0-9][A-Za-z0-9._-]*$")


def valid_family(family) -> bool:
    return family in ("deterministic", "human") or (
        isinstance(family, str) and bool(_MODEL_FAMILY_RE.match(family)))

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
    # The writer only ever emits the schema it implements. Accepting another
    # version here would launder an event this code cannot interpret into the
    # record; on READ such an event stays inert and signaled (ADR-0004),
    # never reinterpreted as v1.
    if event["schema_version"] != SCHEMA_VERSION:
        raise EventValidationError(
            f"unsupported schema_version {event['schema_version']!r}: this "
            f"implementation writes {SCHEMA_VERSION!r} only")
    if event["event_type"] not in EVENT_TYPES:
        raise EventValidationError(
            f"unknown event_type: {event['event_type']!r} (canonical English enum only)")
    if not isinstance(event["seq"], int) or isinstance(event["seq"], bool) \
            or event["seq"] < FIRST_SEQ:
        raise EventValidationError(f"invalid seq: {event['seq']!r}")
    if event["event_type"] in ("node_dispatched", "node_returned",
                               "orphan_detected"):
        _require_str(event, "node_id")
        _require_int(event, "attempt", 1)
        if event["event_type"] == "node_returned":
            ec = event.get("exit_code")
            if not isinstance(ec, int) or isinstance(ec, bool):
                raise EventValidationError(f"invalid exit_code: {ec!r}")
    if event["event_type"] in ("verification_requested", "verdict_recorded"):
        validate_verification_fields(event)
    if event["event_type"] == "run_landed":
        if event.get("reason") not in ("budget_exhausted", "retries_exhausted",
                                       "human_rejection"):
            raise EventValidationError(
                f"run_landed reason must be closed-set, got {event.get('reason')!r}")
    if event["event_type"] == "human_escalation":
        _require_str(event, "node_id")
        _require_int(event, "attempt", 1)
        if event.get("reason") != "verifier_error":
            raise EventValidationError(
                f"human_escalation reason must be verifier_error, got {event.get('reason')!r}")
    if event["event_type"] == "human_retry":
        _require_str(event, "node_id")
        _require_int(event, "attempt", 1)
        _require_str(event, "actor")
    if event["event_type"] == "budget_extended":
        _require_str(event, "actor")
        nb = event.get("new_budget")
        if not isinstance(nb, (int, float)) or isinstance(nb, bool) or nb <= 0:
            raise EventValidationError(f"invalid new_budget: {nb!r}")
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
        _validate_legacy_boundary(event)


def _validate_legacy_boundary(event: dict) -> None:
    """The reserved `legacy-` namespace and `legacy_ambiguous` travel together
    (contract §2, I23).

    A synthetic run aggregating indistinguishable V1 history must SAY so, and
    a real execution must never be able to wear the label that exempts a run
    from modern checkpoints.
    """
    legacy_id = ids.is_legacy(event["run_id"])
    flag = event.get("legacy_ambiguous")
    if legacy_id and flag is not True:
        raise EventValidationError(
            "a legacy- run_id is a synthetic aggregation label and must "
            "carry legacy_ambiguous: true (§2, I23)")
    if not legacy_id and flag is not None:
        raise EventValidationError(
            "legacy_ambiguous belongs to the reserved legacy- namespace "
            "only — a real execution is never labeled ambiguous (I23)")


def _require_str(event: dict, field: str) -> None:
    if not isinstance(event.get(field), str) or not event[field]:
        raise EventValidationError(f"{field} must be a non-empty string")


def _require_int(event: dict, field: str, minimum: int) -> None:
    v = event.get(field)
    if not isinstance(v, int) or isinstance(v, bool) or v < minimum:
        raise EventValidationError(f"invalid {field}: {v!r}")


def validate_verification_fields(event: dict) -> None:
    """Field-level rules for verification_requested / verdict_recorded
    (contract §5, §6): two separate axes, verdict binary, human by
    construction, evidence_id mandatory (P5), verification_attempt (P2)."""
    _require_str(event, "node_id")
    _require_int(event, "attempt", 1)
    _require_str(event, "verification_id")
    _require_int(event, "verification_attempt", FIRST_VERIFICATION_ATTEMPT)
    _require_str(event, "evidence_id")
    family = event.get("family")
    if not valid_family(family):
        raise EventValidationError(f"invalid family: {family!r}")
    if event["event_type"] == "verification_requested":
        return
    # verdict_recorded
    _require_str(event, "actor")
    status = event.get("verification_status")
    if status not in VERIFICATION_STATUS:
        raise EventValidationError(f"invalid verification_status: {status!r}")
    verdict = event.get("verdict")
    if status == "completed":
        if verdict not in VERDICT:
            raise EventValidationError(
                f"verdict must be approved|rejected when completed, got {verdict!r}")
    elif verdict is not None:
        raise EventValidationError(
            "verdict must be null unless verification_status is completed")
    if family == "human":
        if status != "completed":
            raise EventValidationError(
                "family human produces only verification_status completed (by construction)")
        if verdict == "rejected":
            reason = event.get("reason")
            if not isinstance(reason, str) or not reason:
                raise EventValidationError("human rejection requires a reason (I8)")
