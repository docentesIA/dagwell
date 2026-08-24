"""Resume, interruption, orphan observation (contract §8, §10). Zero-cost."""

import json
import tempfile
from pathlib import Path

from dagwell import human, runtime
from dagwell.graph import GraphValidationError
from dagwell.ledger import Ledger
from tests_scenario import AGENDA, GRAPH_TEXT, S

DEAD = lambda item: False  # noqa: E731 — constatation: nothing is in progress
ALIVE = lambda item: True  # noqa: E731


def _expect(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    raise AssertionError(f"expected {exc_type.__name__}")


def test_start_run_fail_closed_before_spend():
    with tempfile.TemporaryDirectory() as tmp:
        led = Ledger(Path(tmp) / "l.jsonl")
        bad = json.dumps({"graph_id": "g", "nodes": [
            {"id": "a", "output_evidence": "artifact"}]})  # no verifications
        _expect(GraphValidationError, runtime.start_run, led,
                graph_text=bad, input_text=AGENDA, input_ref="synthetic://a")
        assert led.events() == []          # refused BEFORE creating the run


def test_ready_and_dispatch_flow():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        assert runtime.ready_nodes(s.graph, s.led, s.rid) == [("a", 1)]
        runtime.dispatch_node(s.led, s.graph, s.rid, "a")
        assert runtime.ready_nodes(s.graph, s.led, s.rid) == []


def test_advance_machines_first_then_human():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        e1 = runtime.advance_verifications(s.led, s.graph, s.rid)
        assert [x["verification_id"] for x in e1] == ["lint"]
        assert e1[0]["family"] == "deterministic"
        # in flight: advancing again emits nothing
        assert runtime.advance_verifications(s.led, s.graph, s.rid) == []
        s.verdict("lint", "deterministic")
        e2 = runtime.advance_verifications(s.led, s.graph, s.rid)
        assert [x["verification_id"] for x in e2] == ["gate"]
        assert e2[0]["family"] == "human"
        assert s.fold()["nodes"]["a"]["state"] == "waiting_human"


def test_advance_escalates_on_verifier_error_once():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        runtime.advance_verifications(s.led, s.graph, s.rid)
        s.verdict("lint", "deterministic", status="error", verdict=None)
        e = runtime.advance_verifications(s.led, s.graph, s.rid)
        assert [x["event_type"] for x in e] == ["human_escalation"]
        # idempotent while unresolved
        assert runtime.advance_verifications(s.led, s.graph, s.rid) == []
        assert s.fold()["nodes"]["a"]["state"] == "waiting_human"


def test_cancelled_verification_refires_without_escalation():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        runtime.advance_verifications(s.led, s.graph, s.rid)
        runtime.request_interrupt(s.led, s.graph, s.rid)
        runtime.cancel_verification(s.led, s.graph, s.rid, "a", "lint")
        e = runtime.advance_verifications(s.led, s.graph, s.rid)
        assert [x["event_type"] for x in e] == ["verification_requested"]
        assert e[0]["verification_attempt"] == 2   # re-fire, no policy burn


def test_resume_validates_frozen_identity():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        edited = GRAPH_TEXT.replace("demo", "demo2")   # valid, divergent
        _expect(runtime.ResumeRefused, runtime.resume, s.led,
                edited, AGENDA, s.rid)
        _expect(runtime.ResumeRefused, runtime.resume, s.led,
                GRAPH_TEXT, AGENDA + "changed\n", s.rid)
        r = runtime.resume(s.led, GRAPH_TEXT, AGENDA, s.rid)
        assert r["ready"] == [("a", 1)]


def test_resume_refused_on_cancelled_and_landed():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        human.cancel_run(s.led, s.graph, s.rid, actor="rey")
        _expect(runtime.ResumeRefused, runtime.resume, s.led, GRAPH_TEXT,
                AGENDA, s.rid)
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret(exit_code=1)                     # failed → grounded
        runtime.land_run(s.led, s.graph, s.rid, "retries_exhausted")
        _expect(runtime.ResumeRefused, runtime.resume, s.led, GRAPH_TEXT,
                AGENDA, s.rid)
        human.human_retry(s.led, s.graph, s.rid, "a", actor="rey")
        r = runtime.resume(s.led, GRAPH_TEXT, AGENDA, s.rid)
        assert r["ready"] == [("a", 2)]        # motive removed, attempt k+1


def test_resume_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        runtime.resume(s.led, GRAPH_TEXT, AGENDA, s.rid)   # emits lint request
        n = len(s.led.events())
        runtime.resume(s.led, GRAPH_TEXT, AGENDA, s.rid)
        assert len(s.led.events()) == n        # no changes → no new events


def test_producer_orphan_only_at_observed_death():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        # default: no constatation mechanism → never orphaned
        runtime.resume(s.led, GRAPH_TEXT, AGENDA, s.rid)
        assert s.fold()["nodes"]["a"]["state"] == "running"
        r = runtime.resume(s.led, GRAPH_TEXT, AGENDA, s.rid,
                           still_in_progress=DEAD)
        assert s.fold()["nodes"]["a"]["state"] == "failed"
        # in-progress work is NOT orphaned
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        runtime.resume(s.led, GRAPH_TEXT, AGENDA, s.rid,
                       still_in_progress=ALIVE)
        assert s.fold()["nodes"]["a"]["state"] == "running"


def test_verification_orphan_then_escalation():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        runtime.advance_verifications(s.led, s.graph, s.rid)   # lint va1 open
        emitted = runtime.observe_orphans(s.led, s.graph, s.rid, DEAD)
        assert [e["event_type"] for e in emitted] == ["verdict_recorded"]
        assert emitted[0]["verification_status"] == "error"
        assert emitted[0]["verdict"] is None
        assert emitted[0]["reason"] == "orphaned"
        assert emitted[0]["verification_attempt"] == 1
        e = runtime.advance_verifications(s.led, s.graph, s.rid)
        assert [x["event_type"] for x in e] == ["human_escalation"]


def test_human_verification_never_orphaned():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        s.request("lint", "deterministic")
        s.verdict("lint", "deterministic")
        s.request("gate", "human")
        emitted = runtime.observe_orphans(s.led, s.graph, s.rid, DEAD)
        assert emitted == []                   # silence stays waiting_human
        assert s.fold()["nodes"]["a"]["state"] == "waiting_human"


def test_graceful_interrupt_is_inert_and_recoverable():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        before = s.fold()["run_state"]
        runtime.request_interrupt(s.led, s.graph, s.rid)
        assert s.fold()["run_state"] == before     # intent is fold-inert
        r = runtime.resume(s.led, GRAPH_TEXT, AGENDA, s.rid,
                           still_in_progress=ALIVE)
        assert r["state"]["run_state"] == "running"


def test_completed_nodes_skipped_on_resume():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        s.request("lint", "deterministic")
        s.verdict("lint", "deterministic")
        s.request("gate", "human")
        human.decide(s.led, s.graph, s.rid, "a", "approved", actor="rey")
        r = runtime.resume(s.led, GRAPH_TEXT, AGENDA, s.rid)
        assert r["state"]["checkpoint"] == ["a"]
        assert r["ready"] == [("b", 1)]        # a skipped, b continuable


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(vars(sys.modules["__main__"]).items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"test_runtime: {len(fns)} tests PASS")
