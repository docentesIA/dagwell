"""Cross-phase integration chains A–G (Phases 2–7). Synthetic data only."""

import json
import tempfile
from pathlib import Path

from dagwell import human, ids, runtime
from dagwell.checkpoint import load_or_recompute
from dagwell.fold import fold
from dagwell.ledger import Ledger, LedgerIntegrityError, SCHEMA_VERSION, occurred_now
from tests_scenario import AGENDA, EVID, GRAPH_TEXT, S

DEAD = lambda item: False  # noqa: E731


def _expect(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    raise AssertionError(f"expected {exc_type.__name__}")


def _complete_node_a(s):
    s.dispatch()
    s.ret()
    runtime.advance_verifications(s.led, s.graph, s.rid)     # lint
    s.verdict("lint", "deterministic")
    runtime.advance_verifications(s.led, s.graph, s.rid)     # gate
    human.decide(s.led, s.graph, s.rid, "a", "approved", actor="rey")


def test_chain_a_run_created_ledger_fold_checkpoint_resume():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        _complete_node_a(s)
        cache = Path(tmp) / "cp.json"
        cp = load_or_recompute(cache, s.led, s.graph, s.rid)
        assert cp["completed"] == ["a"]
        r = runtime.resume(s.led, GRAPH_TEXT, AGENDA, s.rid)
        assert r["state"]["checkpoint"] == ["a"]     # completed skipped
        assert r["ready"] == [("b", 1)]
        cp2 = load_or_recompute(cache, s.led, s.graph, s.rid)
        assert cp2["completed"] == ["a"]             # cache still consistent


def test_chain_b_evidence_to_completed():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        _complete_node_a(s)
        s.dispatch(node="b")
        runtime.record_return(
            s.led, s.graph, s.rid, "b", 1, exit_code=0,
            output_evidence={"type": "artifact", "evidence_id": EVID,
                             "output_manifest": [{"name": "o.md",
                                                  "artifact_digest": EVID}]})
        f = s.fold()
        assert f["nodes"]["b"]["state"] == "completed"   # declared vacuum
        assert f["run_state"] == "completed"
        # and for node a the full chain held:
        # evidence -> evidence_id -> requested -> attempt -> verdict -> completed
        assert f["checkpoint"] == ["a", "b"]


def test_chain_c_human_rejection_blocked_retry_then_k_plus_1():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        runtime.advance_verifications(s.led, s.graph, s.rid)
        s.verdict("lint", "deterministic")
        runtime.advance_verifications(s.led, s.graph, s.rid)
        human.decide(s.led, s.graph, s.rid, "a", "rejected", actor="rey",
                     reason="tone")
        assert s.fold()["nodes"]["a"]["state"] == "rejected"
        # nothing in the runtime auto-retries a human rejection:
        assert runtime.advance_verifications(s.led, s.graph, s.rid) == []
        r = runtime.resume(s.led, GRAPH_TEXT, AGENDA, s.rid)
        assert r["ready"] == []                       # still blocked
        human.human_retry(s.led, s.graph, s.rid, "a", actor="rey")
        r = runtime.resume(s.led, GRAPH_TEXT, AGENDA, s.rid)
        assert r["ready"] == [("a", 2)]               # producer attempt k+1
        runtime.dispatch_node(s.led, s.graph, s.rid, "a")
        assert s.fold()["nodes"]["a"]["state"] == "running"


def test_chain_d_timeout_new_attempt_late_result_inert():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        runtime.advance_verifications(s.led, s.graph, s.rid)   # lint va1
        s.verdict("lint", "deterministic", status="timeout", verdict=None)
        # human_retry is NOT the verb to re-arm a verifier; the escalation
        # path exists, but here we exercise the direct re-fire boundary:
        # cancelled re-fires; timeout escalates under the zero policy.
        e = runtime.advance_verifications(s.led, s.graph, s.rid)
        assert e[0]["event_type"] == "human_escalation"
        # the human assumes the substituted verification -> va2 (family human)
        human.decide(s.led, s.graph, s.rid, "a", "approved", actor="rey")
        # LATE result from closed va1 cannot conclude anything:
        _expect(LedgerIntegrityError, s.verdict, "lint", "deterministic",
                va=1, status="completed", verdict="approved")
        # current state proceeded on the current attempt's authority
        runtime.advance_verifications(s.led, s.graph, s.rid)   # gate
        human.decide(s.led, s.graph, s.rid, "a", "approved", actor="rey")
        assert s.fold()["nodes"]["a"]["state"] == "completed"


def test_chain_e_seq_gap_degraded_read_only():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        rogue = {"schema_version": SCHEMA_VERSION,
                 "event_id": ids.new_event_id(), "run_id": s.rid, "seq": 5,
                 "event_type": "run_interrupt_requested",
                 "occurred_at": occurred_now()}
        with open(s.led.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rogue) + "\n")
        f = s.fold()                                   # inspection allowed
        assert f["integrity"] == "degraded"
        _expect(LedgerIntegrityError, s.ev, "run_cancelled")   # append blocked
        _expect(runtime.ResumeRefused, runtime.resume, s.led, GRAPH_TEXT,
                AGENDA, s.rid)                          # resume blocked
        _expect(human.DecisionRefused, human.human_retry, s.led, s.graph,
                s.rid, "a", actor="rey")               # human verb blocked


def test_chain_f_graceful_interruption_then_resume():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        runtime.advance_verifications(s.led, s.graph, s.rid)   # lint va1 open
        runtime.request_interrupt(s.led, s.graph, s.rid)                # intent recorded
        runtime.cancel_verification(s.led, s.graph, s.rid, "a", "lint")
        r = runtime.resume(s.led, GRAPH_TEXT, AGENDA, s.rid)
        # resume re-fired the cancelled verification (no policy burn)
        reqs = [e for e in s.led.run(s.rid)
                if e["event_type"] == "verification_requested"
                and e["verification_id"] == "lint"]
        assert [q["verification_attempt"] for q in reqs] == [1, 2]
        assert r["state"]["run_state"] == "running"


def test_chain_g_abrupt_loss_orphan_retry_resume():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        # abrupt loss: no death event exists; observation constates death
        r = runtime.resume(s.led, GRAPH_TEXT, AGENDA, s.rid,
                           still_in_progress=DEAD)
        assert r["state"]["nodes"]["a"]["state"] == "failed"
        # retry boundary: automatic retry is disabled (no §13.12 policy);
        # the explicit human verb opens k+1
        human.human_retry(s.led, s.graph, s.rid, "a", actor="rey")
        r = runtime.resume(s.led, GRAPH_TEXT, AGENDA, s.rid)
        assert r["ready"] == [("a", 2)]
        runtime.dispatch_node(s.led, s.graph, s.rid, "a")
        s.ret(attempt=2)
        runtime.advance_verifications(s.led, s.graph, s.rid)
        assert s.fold()["nodes"]["a"]["state"] == "verifying"


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(vars(sys.modules["__main__"]).items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"test_integration_chains: {len(fns)} chains PASS")
