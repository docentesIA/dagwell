"""The capability worker loop, end to end at zero cost: the "agent CLI" is
python3 -c, the mission writes (or fails to write) $OUT, and every claim is
checked against the ledger and the disk."""

import json
import os
import sys
import tempfile
from pathlib import Path

from dagwell.adapters import worker
from dagwell.adapters.registry import load_registry
from dagwell.fold import fold
from dagwell.graph import load_graph
from dagwell.ledger import Ledger, create_run

PY = sys.executable

REGISTRY_TEXT = json.dumps({
    "registry_version": 1,
    "bindings": [
        {"binding_id": "py-cli", "transport": "subprocess",
         "platform": "python", "invocation": PY + " -c {mission}",
         "timeout_seconds": 60,
         "models": [
             {"model_id": "cheap", "family": "anthropic-claude",
              "tiers": ["trivial", "simple"], "relative_cost": 1},
             {"model_id": "dear", "family": "anthropic-claude",
              "tiers": ["frontier"], "relative_cost": 25}]},
        {"binding_id": "zz-dead", "transport": "subprocess",
         "platform": "dead", "invocation": "whatever {mission}",
         "probe": "false", "timeout_seconds": 60,
         "models": [
             {"model_id": "ghost", "family": "openai-gpt",
              "tiers": ["trivial", "simple", "standard", "complex",
                        "frontier"], "relative_cost": 0.001}]},
    ],
})

OK_MISSION = ("import os,sys\n"
              "open(os.environ['OUT'],'w').write('produced')")
LIAR_MISSION = "pass"                                   # exit 0, no file


def _graph_text(tier="simple", mission=OK_MISSION, evidence="artifact"):
    return json.dumps({"graph_id": "wk", "nodes": [
        {"id": "task", "deps": [], "output_evidence": evidence,
         "capability_requirements": {"tier": tier}, "mission": mission,
         "verifications": [{"verification_id": "review",
                            "family": "human"}]}]})


def _setup(tmp, graph_text):
    graph = load_graph(graph_text)
    led = Ledger(Path(tmp) / "l.jsonl")
    rid = create_run(led, graph_id=graph["graph_id"], graph_text=graph_text,
                     input_text="t\n", input_ref="synthetic://t")["run_id"]
    return led, graph, rid, load_registry(REGISTRY_TEXT)


def test_plan_spends_and_writes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, _graph_text())
        before = len(led.run(rid))
        plans = worker.plan(graph, led, rid, reg)
        assert len(led.run(rid)) == before            # zero events
        assert not (Path(tmp) / "runs").exists()      # zero directories
        (p,) = plans
        # the dead binding's cheaper ghost model is probe-filtered out:
        # availability gates selection (spec §6.6).
        assert p["action"] == "dispatch"
        assert p["selection"]["binding_id"] == "py-cli"
        assert p["selection"]["model_id"] == "cheap"


def test_go_executes_with_derived_evidence_and_transport_facts():
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, _graph_text())
        (r,) = worker.work(led, graph, rid, reg, tmp, go=True)
        assert r["action"] == "executed" and r["exit_code"] == 0
        out = Path(r["attempt_dir"]) / worker.OUT_NAME
        assert out.read_text() == "produced"
        f = fold(graph, led.run(rid), rid)
        assert f["nodes"]["task"]["state"] == "executed"   # not completed
        dispatched = next(e for e in led.run(rid)
                          if e["event_type"] == "node_dispatched")
        assert dispatched["transport"] == {
            "binding_id": "py-cli", "model_id": "cheap",
            "family": "anthropic-claude", "transport": "subprocess",
            "registry_digest": reg["registry_digest"]}
        returned = next(e for e in led.run(rid)
                        if e["event_type"] == "node_returned")
        assert returned["output_evidence"]["evidence_id"] == r["evidence_id"]
        assert returned["transport"]["timed_out"] is False


def test_liar_mission_lands_failed_not_executed():
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, _graph_text(mission=LIAR_MISSION))
        (r,) = worker.work(led, graph, rid, reg, tmp, go=True)
        assert r["action"] == "failed"
        assert r["exit_code"] == 0                    # transport succeeded...
        assert r["evidence_id"] is None               # ...but nothing landed
        f = fold(graph, led.run(rid), rid)
        assert f["nodes"]["task"]["state"] == "failed"


def test_unservable_tier_refuses_before_spend():
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, _graph_text(tier="standard"))
        before = len(led.run(rid))
        (r,) = worker.work(led, graph, rid, reg, tmp, go=True)
        assert r["action"] == "refused"
        assert len(led.run(rid)) == before            # nothing dispatched


def test_mission_out_token_is_substituted():
    with tempfile.TemporaryDirectory() as tmp:
        mission = ("import sys\n"
                   "open(r'''$OUT''','w').write('via-token')")
        led, graph, rid, reg = _setup(tmp, _graph_text(mission=mission))
        (r,) = worker.work(led, graph, rid, reg, tmp, go=True)
        assert r["action"] == "executed"
        assert (Path(r["attempt_dir"]) / worker.OUT_NAME
                ).read_text() == "via-token"


def test_non_artifact_capability_node_is_refused_in_plan():
    text = json.dumps({"graph_id": "wk", "nodes": [
        {"id": "task", "deps": [], "output_evidence": "structured_value",
         "capability_requirements": {"tier": "simple"}, "mission": "x",
         "verifications": [{"verification_id": "v",
                            "family": "deterministic"}]}]})
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, text)
        (p,) = worker.plan(graph, led, rid, reg)
        assert p["action"] == "refused"
        assert "artifact" in p["reason"]


def test_x_command_nodes_are_skipped_loudly():
    text = json.dumps({"graph_id": "wk", "nodes": [
        {"id": "task", "deps": [], "output_evidence": "artifact",
         "x_command": "echo hi > $OUT",
         "verifications": [{"verification_id": "v",
                            "family": "deterministic"}]}]})
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, text)
        (p,) = worker.plan(graph, led, rid, reg)
        assert p["action"] == "skipped"
        assert "runner" in p["reason"]


def test_mission_required_when_capability_declared():
    from dagwell.graph import GraphValidationError
    try:
        load_graph(json.dumps({"graph_id": "wk", "nodes": [
            {"id": "task", "deps": [], "output_evidence": "artifact",
             "capability_requirements": {"tier": "simple"},
             "verifications": [{"verification_id": "v",
                                "family": "deterministic"}]}]}))
    except GraphValidationError as exc:
        assert "mission" in str(exc)
    else:
        raise AssertionError("expected GraphValidationError")


if __name__ == "__main__":
    fns = [v for k, v in sorted(vars(sys.modules["__main__"]).items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"test_worker: {len(fns)} tests PASS")
