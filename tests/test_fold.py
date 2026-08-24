"""Deterministic fold + checkpoint (contract §3, §4, §7). Zero-cost."""

import json
import tempfile
from pathlib import Path

from dagwell import ids
from dagwell.checkpoint import load_or_recompute
from dagwell.fold import fold
from dagwell.ledger import LedgerIntegrityError, SCHEMA_VERSION, occurred_now
from tests_scenario import EVID, S


def _expect(exc_type, fn, *args):
    try:
        fn(*args)
    except exc_type:
        return
    raise AssertionError(f"expected {exc_type.__name__}")


def test_created_then_views():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        f = s.fold()
        assert f["run_state"] == "created"
        assert f["nodes"]["a"]["state"] == "ready"
        assert f["nodes"]["b"]["state"] == "pending"
        assert f["identity"]["graph_version"] == s.graph["graph_version"]


def test_running_and_transport_failure():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        assert s.fold()["run_state"] == "running"
        assert s.fold()["nodes"]["a"]["state"] == "running"
        s.ret(exit_code=1)
        f = s.fold()
        assert f["nodes"]["a"]["state"] == "failed"
        assert f["run_state"] == "stalled"


def test_missing_or_invalid_evidence_never_reaches_executed():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret(evidence=None)
        assert s.fold()["nodes"]["a"]["state"] == "failed"
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret(evidence={"type": "artifact", "evidence_id": EVID,
                        "output_manifest": []})
        assert s.fold()["nodes"]["a"]["state"] == "failed"


def test_executed_is_not_completed():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        f = s.fold()
        assert f["nodes"]["a"]["state"] == "executed"
        assert f["checkpoint"] == []


def test_verifying_then_waiting_human_then_completed():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        s.request("lint", "deterministic")
        f = s.fold()
        assert f["nodes"]["a"]["state"] == "verifying"
        assert f["run_state"] == "running"          # verification in flight
        s.verdict("lint", "deterministic")
        s.request("gate", "human")
        f = s.fold()
        assert f["nodes"]["a"]["state"] == "waiting_human"
        assert f["run_state"] == "waiting_human"
        s.verdict("gate", "human", actor="reviewer")
        f = s.fold()
        assert f["nodes"]["a"]["state"] == "completed"
        assert f["checkpoint"] == ["a"]
        assert f["nodes"]["b"]["state"] == "ready"


def test_declared_vacuum_completes_and_run_completes():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        s.request("lint", "deterministic")
        s.verdict("lint", "deterministic")
        s.request("gate", "human")
        s.verdict("gate", "human", actor="reviewer")
        s.dispatch(node="b")
        s.ret(node="b")
        f = s.fold()
        assert f["nodes"]["b"]["state"] == "completed"   # signed vacuum
        assert f["run_state"] == "completed"
        assert f["checkpoint"] == ["a", "b"]


def test_nonhuman_rejected_is_failed_human_rejected_is_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        s.request("lint", "deterministic")
        s.verdict("lint", "deterministic", verdict="rejected")
        assert s.fold()["nodes"]["a"]["state"] == "failed"
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        s.request("lint", "deterministic")
        s.verdict("lint", "deterministic")
        s.request("gate", "human")
        s.verdict("gate", "human", verdict="rejected", reason="not enough",
                  actor="reviewer")
        assert s.fold()["nodes"]["a"]["state"] == "rejected"


def test_orphan_only_acts_on_running():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ev("orphan_detected", node_id="a", attempt=1)
        assert s.fold()["nodes"]["a"]["state"] == "failed"
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        s.ev("orphan_detected", node_id="a", attempt=1)
        assert s.fold()["nodes"]["a"]["state"] == "executed"  # inert: return wins


def test_verifier_timeout_keeps_verifying_and_escalation_waits():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        s.request("lint", "deterministic")
        s.verdict("lint", "deterministic", status="timeout", verdict=None)
        assert s.fold()["nodes"]["a"]["state"] == "verifying"
        s.ev("human_escalation", node_id="a", attempt=1,
             reason="verifier_error")
        f = s.fold()
        assert f["nodes"]["a"]["state"] == "waiting_human"
        assert f["run_state"] == "waiting_human"


def test_landed_and_motive_removal():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        s.request("lint", "deterministic")
        s.verdict("lint", "deterministic")
        s.request("gate", "human")
        s.verdict("gate", "human", verdict="rejected", reason="no",
                  actor="reviewer")
        s.ev("run_landed", reason="human_rejection")
        assert s.fold()["run_state"] == "landed"
        s.ev("human_retry", node_id="a", attempt=1, actor="reviewer")
        f = s.fold()
        assert f["run_state"] != "landed"           # motive removed
        assert f["nodes"]["a"]["state"] == "ready"  # reopened for attempt 2


def test_budget_extension_removes_budget_motive():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret(exit_code=1)
        s.ev("run_landed", reason="budget_exhausted")
        assert s.fold()["run_state"] == "landed"
        s.ev("budget_extended", new_budget=10, actor="reviewer")
        assert s.fold()["run_state"] != "landed"


def test_cancelled_is_absorbing_and_views_cancelled():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        s.ev("run_cancelled")
        f = s.fold()
        assert f["run_state"] == "cancelled"
        assert f["nodes"]["a"]["state"] == "cancelled"
        assert f["nodes"]["b"]["state"] == "cancelled"


def test_seq_gap_degraded_diagnostic():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        rogue = {"schema_version": SCHEMA_VERSION,
                 "event_id": ids.new_event_id(), "run_id": s.rid, "seq": 4,
                 "event_type": "run_cancelled", "occurred_at": occurred_now()}
        with open(s.led.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rogue) + "\n")
        f = s.fold()
        assert f["integrity"] == "degraded"
        assert any("seq gap" in a for a in f["anomalies"])


def test_seq_collision_refuses_fold():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        events = s.led.events()
        clash = dict(events[0], event_id=ids.new_event_id())
        _expect(LedgerIntegrityError, fold, s.graph, events + [clash], s.rid)


def test_duplicate_event_id_first_wins_flagged():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        events = s.led.events()
        dup = dict(events[1], seq=3)  # same event_id, new seq
        f = fold(s.graph, events + [dup], s.rid)
        assert any("duplicate event_id" in a for a in f["anomalies"])
        assert f["nodes"]["a"]["state"] == "running"


def test_checkpoint_cache_ledger_wins():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        cache = Path(tmp) / "checkpoint.json"
        c1 = load_or_recompute(cache, s.led, s.graph, s.rid)
        assert c1["completed"] == []
        # complete node a
        s.dispatch()
        s.ret()
        s.request("lint", "deterministic")
        s.verdict("lint", "deterministic")
        s.request("gate", "human")
        s.verdict("gate", "human", actor="reviewer")
        c2 = load_or_recompute(cache, s.led, s.graph, s.rid)
        assert c2["completed"] == ["a"]
        # tamper with the cache: ledger must win
        cache.write_text(json.dumps(dict(c2, completed=["a", "b"],
                                         watermark=-1)), encoding="utf-8")
        c3 = load_or_recompute(cache, s.led, s.graph, s.rid)
        assert c3["completed"] == ["a"]


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(vars(sys.modules["__main__"]).items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"test_fold: {len(fns)} tests PASS")
