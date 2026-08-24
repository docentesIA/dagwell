"""Event foundation: envelope, run_created, append-only ledger (Phase 2)."""

from dagwell import canonical
from dagwell.ledger.events import (
    ENVELOPE_FIELDS,
    EVENT_TYPES,
    FIRST_SEQ,
    RUN_CREATED_FIELDS,
    SCHEMA_VERSION,
    EventValidationError,
    LedgerError,
    LedgerIntegrityError,
    occurred_now,
    run_created_event,
    validate_event,
)
from dagwell.ledger.ledger import Ledger


def create_run(ledger: Ledger, *, graph_id: str, graph_text: bytes | str,
               input_text: bytes | str, input_ref: str,
               parent_run_id: str | None = None) -> dict:
    """Compute the frozen identity from CONTENT (never paths) and append the
    founding run_created (contract §2). Returns the recorded event.

    Library primitive only: no dispatch, no execution, no spend — the `--go`
    semantics live in later phases.
    """
    event = run_created_event(
        graph_id=graph_id,
        graph_version=canonical.graph_version(graph_text),
        input_hash=canonical.input_hash(input_text),
        input_ref=input_ref,
        parent_run_id=parent_run_id,
    )
    return ledger.append(event)
