"""Human decision workflow (contract §5, I8–I10). Zero-cost."""

import json
import tempfile
from pathlib import Path

from dagwell import cli, human
from dagwell.fold import fold
from dagwell.graph import load_graph
from dagwell.ledger import Ledger
from tests_scenario import S, GRAPH_TEXT  # shared synthetic scenario


def _expect(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    raise AssertionError(f"expected {exc_type.__name__}")


def _to_gate(s):
    """Bring node a to waiting_human (declared gate)."""
    s.dispatch()
    s.ret()
    s.request("lint", "deterministic")
    s.verdict("lint", "deterministic")
    s.request("gate", "human")


def test_decide_approves_gate_completes_node():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        _to_gate(s)
        e = human.decide(s.led, s.graph, s.rid, "a", "approved", actor="rey")
        assert e["family"] == "human" and e["verdict"] == "approved"
        assert s.fold()["nodes"]["a"]["state"] == "completed"


def test_reject_requires_reason_and_blocks_auto_retry():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        _to_gate(s)
        _expect(Exception, human.decide, s.led, s.graph, s.rid, "a",
                "rejected", actor="rey")           # no reason → refused
        human.decide(s.led, s.graph, s.rid, "a", "rejected", actor="rey",
                     reason="wrong tone")
        f = s.fold()
        assert f["nodes"]["a"]["state"] == "rejected"
        # nothing auto-retries: state persists until the explicit human verb
        assert s.fold()["nodes"]["a"]["state"] == "rejected"
        human.human_retry(s.led, s.graph, s.rid, "a", actor="rey")
        assert s.fold()["nodes"]["a"]["state"] == "ready"   # attempt k+1 opens
        s.dispatch(attempt=2)
        assert s.fold()["nodes"]["a"]["state"] == "running"


def test_decide_refused_when_not_waiting():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        _expect(human.DecisionRefused, human.decide, s.led, s.graph, s.rid,
                "a", "approved", actor="rey")


def test_decide_refused_on_cancelled_run():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        _to_gate(s)
        human.cancel_run(s.led, s.graph, s.rid, actor="rey")
        _expect(human.DecisionRefused, human.decide, s.led, s.graph, s.rid,
                "a", "approved", actor="rey")
        # cancel is idempotent
        again = human.cancel_run(s.led, s.graph, s.rid, actor="rey")
        assert again["event_type"] == "run_cancelled"


def test_duplicate_identical_decision_is_noop_conflict_refused():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        _to_gate(s)
        human.decide(s.led, s.graph, s.rid, "a", "approved", actor="rey")
        n = len(s.led.events())
        # node is completed now; decide() refuses because nothing waits
        _expect(human.DecisionRefused, human.decide, s.led, s.graph, s.rid,
                "a", "approved", actor="rey")
        assert len(s.led.events()) == n


def test_human_retry_refused_on_completed_and_on_normal_gate():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        _to_gate(s)
        # waiting at a DECLARED gate: retry is not the verb — decide is
        _expect(human.DecisionRefused, human.human_retry, s.led, s.graph,
                s.rid, "a", actor="rey")
        human.decide(s.led, s.graph, s.rid, "a", "approved", actor="rey")
        _expect(human.DecisionRefused, human.human_retry, s.led, s.graph,
                s.rid, "a", actor="rey")           # completed is absolute


def test_failed_node_is_human_retryable():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret(exit_code=1)
        assert s.fold()["nodes"]["a"]["state"] == "failed"
        human.human_retry(s.led, s.graph, s.rid, "a", actor="rey")
        assert s.fold()["nodes"]["a"]["state"] == "ready"


def test_escalation_assume_verification_path():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        s.request("lint", "deterministic")
        s.verdict("lint", "deterministic", status="error", verdict=None)
        s.ev("human_escalation", node_id="a", attempt=1,
             reason="verifier_error")
        assert s.fold()["nodes"]["a"]["state"] == "waiting_human"
        # the human ASSUMES the substituted verification (new human attempt)
        human.decide(s.led, s.graph, s.rid, "a", "approved", actor="rey")
        st = s.fold()["nodes"]["a"]["state"]
        assert st == "verifying"       # human gate still undischarged
        s.request("gate", "human")
        human.decide(s.led, s.graph, s.rid, "a", "approved", actor="rey")
        assert s.fold()["nodes"]["a"]["state"] == "completed"


def test_escalation_human_retry_path():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        s.request("lint", "deterministic")
        s.verdict("lint", "deterministic", status="error", verdict=None)
        s.ev("human_escalation", node_id="a", attempt=1,
             reason="verifier_error")
        human.human_retry(s.led, s.graph, s.rid, "a", actor="rey")
        assert s.fold()["nodes"]["a"]["state"] == "ready"


def test_cli_presentation_surface():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        _to_gate(s)
        gpath = Path(tmp) / "graph.json"
        gpath.write_text(GRAPH_TEXT, encoding="utf-8")
        base = ["--ledger", str(s.led.path), "--graph", str(gpath),
                "--run", s.rid]
        assert cli.main(["status"] + base) == 0
        assert cli.main(["decide"] + base + ["--node", "a", "approved",
                                             "--actor", "rey"]) == 0
        assert s.fold()["nodes"]["a"]["state"] == "completed"
        # refusal surfaces as nonzero exit, no traceback
        assert cli.main(["decide"] + base + ["--node", "a", "approved",
                                             "--actor", "rey"]) == 1
        # an unknown run is refused, never projected: a mistyped id must not
        # read as a real run sitting at rest
        assert cli.main(["status", "--ledger", str(s.led.path),
                         "--graph", str(gpath),
                         "--run", "id-that-does-not-exist"]) == 1


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(vars(sys.modules["__main__"]).items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"test_human: {len(fns)} tests PASS")
