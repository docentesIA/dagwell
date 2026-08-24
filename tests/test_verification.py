"""Verification semantics: two axes, P2 attempts, evidence binding. Zero-cost."""

import tempfile
from pathlib import Path

from dagwell import ids, verification as vf
from dagwell.ledger import (
    EventValidationError,
    Ledger,
    LedgerIntegrityError,
    SCHEMA_VERSION,
    create_run,
    occurred_now,
)

GRAPH = "synthetic graph definition text\n"
AGENDA = "# synthetic agenda\n"
EVID = "sha256:" + "ab" * 32


def _expect(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    raise AssertionError(f"expected {exc_type.__name__}")


def _node_event(run_id, event_type, node_id="n1", attempt=1, **extra):
    e = {
        "schema_version": SCHEMA_VERSION,
        "event_id": ids.new_event_id(),
        "run_id": run_id,
        "event_type": event_type,
        "occurred_at": occurred_now(),
        "node_id": node_id,
        "attempt": attempt,
    }
    e.update(extra)
    return e


def _executed_run(led):
    """run_created + dispatched + returned(evidence) — attempt 1 executed."""
    r = create_run(led, graph_id="g", graph_text=GRAPH,
                   input_text=AGENDA, input_ref="synthetic://a")
    rid = r["run_id"]
    led.append(_node_event(rid, "node_dispatched"))
    led.append(_node_event(rid, "node_returned", exit_code=0,
                           output_evidence={"type": "artifact", "evidence_id": EVID,
                                            "output_manifest": [
                                                {"name": "out.md",
                                                 "artifact_digest": EVID}]}))
    return rid


def _request(led, rid, va=1, family="deterministic", evidence_id=EVID,
             verification_id="check-1"):
    return led.append(vf.verification_requested_event(
        run_id=rid, node_id="n1", attempt=1, verification_id=verification_id,
        verification_attempt=va, family=family, evidence_id=evidence_id))


def _verdict(led, rid, va=1, status="completed", verdict="approved",
             family="deterministic", evidence_id=EVID, actor="verifier",
             reason=None, verification_id="check-1"):
    return led.append(vf.verdict_recorded_event(
        run_id=rid, node_id="n1", attempt=1, verification_id=verification_id,
        verification_attempt=va, family=family, actor=actor,
        verification_status=status, verdict=verdict, evidence_id=evidence_id,
        reason=reason))


def test_happy_path_nonhuman_verification():
    with tempfile.TemporaryDirectory() as tmp:
        led = Ledger(Path(tmp) / "l.jsonl")
        rid = _executed_run(led)
        _request(led, rid)
        out = _verdict(led, rid)
        assert out["verdict"] == "approved"
        assert out["verification_status"] == "completed"


def test_verdict_null_iff_completed():
    with tempfile.TemporaryDirectory() as tmp:
        led = Ledger(Path(tmp) / "l.jsonl")
        rid = _executed_run(led)
        _request(led, rid)
        _expect(EventValidationError, _verdict, led, rid, status="completed", verdict=None)
        _expect(EventValidationError, _verdict, led, rid, status="error", verdict="approved")
        out = _verdict(led, rid, status="error", verdict=None)
        assert out["verdict"] is None


def test_human_by_construction():
    with tempfile.TemporaryDirectory() as tmp:
        led = Ledger(Path(tmp) / "l.jsonl")
        rid = _executed_run(led)
        _request(led, rid, family="human", verification_id="gate")
        _expect(EventValidationError, _verdict, led, rid, family="human",
                status="error", verdict=None, verification_id="gate")
        _expect(EventValidationError, _verdict, led, rid, family="human",
                verdict="rejected", verification_id="gate")  # no reason
        out = _verdict(led, rid, family="human", verdict="rejected",
                       reason="not good enough", actor="reviewer",
                       verification_id="gate")
        assert out["reason"] == "not good enough"


def test_family_form_validation():
    with tempfile.TemporaryDirectory() as tmp:
        led = Ledger(Path(tmp) / "l.jsonl")
        rid = _executed_run(led)
        _expect(EventValidationError, _request, led, rid, family="banana")
        _expect(EventValidationError, _request, led, rid, family="model:")
        _request(led, rid, family="model:some-model-family")  # form-valid (§13.15 open)


def test_verification_attempt_monotonic_and_refire_rules():
    with tempfile.TemporaryDirectory() as tmp:
        led = Ledger(Path(tmp) / "l.jsonl")
        rid = _executed_run(led)
        _request(led, rid, va=1)
        # re-fire while attempt 1 still open → refused
        _expect(LedgerIntegrityError, _request, led, rid, va=2)
        _verdict(led, rid, va=1, status="timeout", verdict=None)
        # skipping to 3 → refused; 2 → ok
        _expect(LedgerIntegrityError, _request, led, rid, va=3)
        _request(led, rid, va=2)
        out = _verdict(led, rid, va=2)
        assert out["verification_attempt"] == 2


def test_refire_after_completed_refused():
    with tempfile.TemporaryDirectory() as tmp:
        led = Ledger(Path(tmp) / "l.jsonl")
        rid = _executed_run(led)
        _request(led, rid, va=1)
        _verdict(led, rid, va=1)
        _expect(LedgerIntegrityError, _request, led, rid, va=2)


def test_verdict_without_request_refused():
    with tempfile.TemporaryDirectory() as tmp:
        led = Ledger(Path(tmp) / "l.jsonl")
        rid = _executed_run(led)
        _expect(EventValidationError, _verdict, led, rid, va=1)


def test_late_result_on_closed_attempt():
    with tempfile.TemporaryDirectory() as tmp:
        led = Ledger(Path(tmp) / "l.jsonl")
        rid = _executed_run(led)
        _request(led, rid, va=1)
        _verdict(led, rid, va=1, status="timeout", verdict=None)
        n_before = len(led.events())
        # identical late duplicate → idempotent no-op, nothing written
        dup = _verdict(led, rid, va=1, status="timeout", verdict=None)
        assert dup["verification_status"] == "timeout"
        assert len(led.events()) == n_before
        # late COMPLETION of the closed attempt → refused (P2)
        _expect(LedgerIntegrityError, _verdict, led, rid, va=1,
                status="completed", verdict="approved")


def test_conflicting_completion_at_identity_level_refused():
    with tempfile.TemporaryDirectory() as tmp:
        led = Ledger(Path(tmp) / "l.jsonl")
        rid = _executed_run(led)
        _request(led, rid, va=1)
        _verdict(led, rid, va=1, verdict="approved")
        n = len(led.events())
        # identical duplicate completion → no-op
        again = _verdict(led, rid, va=1, verdict="approved")
        assert len(led.events()) == n and again["verdict"] == "approved"
        # conflicting completion → refused
        _expect(LedgerIntegrityError, _verdict, led, rid, va=1, verdict="rejected")


def test_evidence_binding():
    with tempfile.TemporaryDirectory() as tmp:
        led = Ledger(Path(tmp) / "l.jsonl")
        rid = _executed_run(led)
        other = "sha256:" + "cd" * 32
        _expect(LedgerIntegrityError, _request, led, rid, evidence_id=other)
        _request(led, rid)
        _expect(LedgerIntegrityError, _verdict, led, rid, evidence_id=other)


def test_request_requires_produced_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        led = Ledger(Path(tmp) / "l.jsonl")
        r = create_run(led, graph_id="g", graph_text=GRAPH,
                       input_text=AGENDA, input_ref="synthetic://a")
        rid = r["run_id"]
        _expect(EventValidationError, _request, led, rid)          # not dispatched
        led.append(_node_event(rid, "node_dispatched"))
        _expect(EventValidationError, _request, led, rid)          # not returned


def test_human_substitution_family_override_allowed():
    with tempfile.TemporaryDirectory() as tmp:
        led = Ledger(Path(tmp) / "l.jsonl")
        rid = _executed_run(led)
        _request(led, rid, family="deterministic")
        out = _verdict(led, rid, family="human", verdict="approved", actor="reviewer")
        assert out["family"] == "human"       # escalation substitution path (§4)
        # non-human family mismatch is refused
        rid2 = None


def test_nonhuman_family_mismatch_refused():
    with tempfile.TemporaryDirectory() as tmp:
        led = Ledger(Path(tmp) / "l.jsonl")
        rid = _executed_run(led)
        _request(led, rid, family="deterministic")
        _expect(LedgerIntegrityError, _verdict, led, rid, family="model:x")


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(vars(sys.modules["__main__"]).items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"test_verification: {len(fns)} tests PASS")
