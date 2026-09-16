"""The pilot: doctor, plan, advance, declared verifiers, next actions.

Everything runs at zero cost — the "agent" is python3 -c, the verifiers are
python3 -c, and every claim is checked against the ledger and the disk. What
these tests protect, in the order of the 0.0.3rc1 acceptance criteria:

A1 doctor reports actionable failures without secrets;
A2 plan writes no event, creates no directory, runs no verifier;
A3 advance --go walks dependencies and produces hashed artifacts;
A4 exit 0 is not a verdict, rejection lands failed, verifier error escalates;
A5 the human gate opens and stops; a test actor continues it;
A6 repeating the command duplicates nothing; retry preserves attempt 1.
"""

import io
import json
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from dagwell import cli, human
from dagwell.adapters import pilot
from dagwell.adapters.registry import load_registry
from dagwell.fold import fold
from dagwell.graph import load_graph
from dagwell.ledger import Ledger, create_run

PY = sys.executable
ROOT = Path(__file__).resolve().parent.parent

REGISTRY = json.dumps({"registry_version": 1, "bindings": [
    {"binding_id": "py", "transport": "subprocess", "platform": "python",
     "invocation": PY + " -c {mission}", "probe": PY + " --version",
     "timeout_seconds": 60,
     "models": [{"model_id": "py3", "family": "local-python",
                 "tiers": ["trivial", "simple"], "relative_cost": 1}]}]})

PRODUCE = "import os\nopen(os.environ['OUT'],'w').write('data-v1\\n')"
PRODUCE_2 = ("import os,glob\np=sorted(glob.glob('../../a/t*/out'))[-1]\n"
             "open(os.environ['OUT'],'w').write(open(p).read()+'report\\n')")
LIAR = "pass"                                           # exit 0, no $OUT
APPROVE = PY + " -c \"import json,os;open(os.environ['OUT']).read();print(json.dumps({'verdict':'approved','reasons':['ok']}))\""
REJECT = PY + " -c \"import json;print(json.dumps({'verdict':'rejected','reasons':['bad']}))\""
CRASH = PY + " -c \"import sys;sys.exit(2)\""
GARBAGE = PY + " -c \"print('not json')\""
SLOW = PY + " -c \"import time;time.sleep(30)\""
SENTINEL = PY + " -c \"import os;open(os.environ['DAGWELL_SENTINEL'],'w').write('ran');print('{\\\"verdict\\\":\\\"approved\\\"}')\""


def _graph(a_verifier=APPROVE, b_verifier=APPROVE, a_mission=PRODUCE,
           human_gate=True, a_timeout=30):
    b_ver = [{"verification_id": "b-check", "family": "deterministic",
              "x_verifier": b_verifier, "x_verifier_timeout_seconds": 30}]
    if human_gate:
        b_ver.append({"verification_id": "review", "family": "human"})
    return json.dumps({"graph_id": "pilot-test", "nodes": [
        {"id": "a", "deps": [], "output_evidence": "artifact",
         "capability_requirements": {"tier": "trivial"}, "mission": a_mission,
         "verifications": [{"verification_id": "a-check",
                            "family": "deterministic",
                            "x_verifier": a_verifier,
                            "x_verifier_timeout_seconds": a_timeout}]},
        {"id": "b", "deps": ["a"], "output_evidence": "artifact",
         "capability_requirements": {"tier": "trivial"}, "mission": PRODUCE_2,
         "verifications": b_ver}]})


def _setup(tmp, graph_text):
    graph = load_graph(graph_text)
    led = Ledger(Path(tmp) / "run.jsonl")
    rid = create_run(led, graph_id=graph["graph_id"], graph_text=graph_text,
                     input_text="t\n", input_ref="synthetic://t")["run_id"]
    return led, graph, rid, load_registry(REGISTRY)


def _types(led, rid):
    return [(e["event_type"], e.get("node_id"), e.get("verification_status"),
             e.get("verdict")) for e in led.run(rid)]


def _run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = cli.main(list(argv))
    return rc, out.getvalue(), err.getvalue()


# -- A2: plan is free ---------------------------------------------------------

def test_plan_writes_nothing_and_runs_no_verifier():
    with tempfile.TemporaryDirectory() as tmp:
        sentinel = Path(tmp) / "sentinel"
        env = {**os.environ, "DAGWELL_SENTINEL": str(sentinel)}
        led, graph, rid, reg = _setup(tmp, _graph(a_verifier=SENTINEL))
        data = Path(tmp) / "data"
        before = len(led.run(rid))
        report = pilot.plan(led, graph, rid, reg, data, env=env)
        assert len(led.run(rid)) == before, "plan wrote an event"
        assert not data.exists(), "plan created the data area"
        assert not sentinel.exists(), "plan executed a verifier"
        (p,) = [r for r in report if r["kind"] == "producer"]
        assert p["action"] == "dispatch" and p["node_id"] == "a"
        # a node already executed shows the verifier it WOULD run, and does not
        pilot.advance(led, graph, rid, reg, data, env=env, node_id="a",
                      actor="fixture-test-actor")
        assert sentinel.exists()
        sentinel.unlink()
        n = len(led.run(rid))
        report = pilot.plan(led, graph, rid, reg, data, env=env)
        assert len(led.run(rid)) == n and not sentinel.exists()
        assert [r["action"] for r in report] == ["dispatch"]  # b is ready now


# -- A3 + A5: the real path, dependencies, artifacts, gate, continuation -------

def test_advance_walks_dependencies_verifies_and_stops_at_the_gate():
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, _graph())
        data = Path(tmp) / "data"
        report = pilot.advance(led, graph, rid, reg, data, actor="pilot-test")
        actions = [(r["kind"], r.get("node_id"), r["action"]) for r in report]
        assert actions == [
            ("producer", "a", "executed"), ("verification", "a", "verified"),
            ("producer", "b", "executed"), ("verification", "b", "verified"),
            ("gate", "b", "gate_open")]
        folded = fold(graph, led.run(rid), rid)
        assert folded["run_state"] == "waiting_human"
        assert folded["nodes"]["a"]["state"] == "completed"
        assert folded["nodes"]["b"]["state"] == "waiting_human"
        # evidence comes from the artifact: the ledger digest is the disk digest
        import hashlib
        for nid, content in (("a", "data-v1\n"), ("b", "data-v1\nreport\n")):
            adir = data / "runs" / "pilot-test" / rid / nid / "t1"
            assert (adir / "out").read_text() == content
            ret = next(e for e in led.run(rid) if e["event_type"] == "node_returned"
                       and e["node_id"] == nid)
            digest = "sha256:" + hashlib.sha256((adir / "out").read_bytes()).hexdigest()
            assert ret["output_evidence"]["output_manifest"][0]["artifact_digest"] == digest
        # the verifier's record stands apart from the producer's attempt
        vdir = data / "verifications" / "pilot-test" / rid / "a" / "a-check" / "t1-v1"
        assert json.loads((vdir / "result.json").read_text())["verdict"] == "approved"
        assert (vdir / "exit").read_text().strip() == "0"
        verdict = next(e for e in led.run(rid) if e["event_type"] == "verdict_recorded"
                       and e["node_id"] == "a")
        assert verdict["family"] == "deterministic" and verdict["actor"] == "pilot-test"
        assert "result_sha256=" in verdict["reason"]
        # silence: nothing approves; only the human command continues it
        n = len(led.run(rid))
        pilot.advance(led, graph, rid, reg, data, actor="pilot-test")
        assert len(led.run(rid)) == n
        human.decide(led, graph, rid, "b", "approved", actor="fixture-test-actor",
                     reason="test fixture, not a real decision")
        pilot.advance(led, graph, rid, reg, data, actor="pilot-test")
        assert fold(graph, led.run(rid), rid)["run_state"] == "completed"


# -- A4: exit 0 is not a verdict; rejection; verifier failure -------------------

def test_liar_producer_lands_failed_and_advance_stops():
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, _graph(a_mission=LIAR))
        data = Path(tmp) / "data"
        report = pilot.advance(led, graph, rid, reg, data, actor="t")
        assert [r["action"] for r in report] == ["failed"]
        assert fold(graph, led.run(rid), rid)["nodes"]["a"]["state"] == "failed"
        assert _types(led, rid)[-1][0] == "node_returned"     # no verification
        # A6: the human reopens; attempt 2 is born beside attempt 1, never over it
        human.human_retry(led, graph, rid, "a", actor="fixture-test-actor")
        t1 = data / "runs" / "pilot-test" / rid / "a" / "t1"
        assert t1.is_dir() and not (t1 / "out").exists()
        report = pilot.advance(led, graph, rid, reg, data, actor="t", node_id="a")
        assert report[0]["action"] == "failed" and report[0]["attempt"] == 2
        assert t1.is_dir() and (data / "runs" / "pilot-test" / rid / "a" / "t2").is_dir()


def test_verifier_rejected_is_failed_not_rejected_and_not_retried():
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, _graph(a_verifier=REJECT))
        data = Path(tmp) / "data"
        report = pilot.advance(led, graph, rid, reg, data, actor="t")
        v = [r for r in report if r["action"] == "verified"]
        assert len(v) == 1 and v[0]["verdict"] == "rejected"
        assert v[0]["node_state"] == "failed"          # machine refused: failed
        assert len([r for r in report if r["kind"] == "producer"]) == 1
        assert fold(graph, led.run(rid), rid)["nodes"]["b"]["state"] == "pending"


def test_verifier_error_and_timeout_and_garbage_escalate_never_reject():
    for verifier, status in ((CRASH, "error"), (GARBAGE, "error"), (SLOW, "timeout")):
        with tempfile.TemporaryDirectory() as tmp:
            timeout = 1 if verifier is SLOW else 30
            led, graph, rid, reg = _setup(tmp, _graph(a_verifier=verifier,
                                                      a_timeout=timeout))
            report = pilot.advance(led, graph, rid, reg, Path(tmp) / "data", actor="t")
            v = next(r for r in report if r["action"] == "verified")
            assert v["verification_status"] == status and v["verdict"] is None
            assert any(r["action"] == "escalated" for r in report)
            types = [t[0] for t in _types(led, rid)]
            assert types[-1] == "human_escalation"
            folded = fold(graph, led.run(rid), rid)
            assert folded["nodes"]["a"]["state"] == "waiting_human"
            # not rejected, not approved, not re-fired: the human owns it now
            assert not any(t[3] for t in _types(led, rid))


def test_disk_tampering_after_return_stops_without_a_verdict():
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, _graph())
        data = Path(tmp) / "data"
        # produce a without verifying it: run only the producer via the worker
        from dagwell.adapters import worker
        worker.work(led, graph, rid, reg, data, go=True)
        (data / "runs" / "pilot-test" / rid / "a" / "t1" / "out").write_text("tampered")
        n = len(led.run(rid))
        report = pilot.advance(led, graph, rid, reg, data, actor="t")
        assert [r["action"] for r in report] == ["inconsistent"]
        assert len(led.run(rid)) == n           # nothing requested, nothing judged


def test_missing_declaration_exposes_the_manual_step():
    graph_text = json.dumps({"graph_id": "pilot-test", "nodes": [
        {"id": "a", "deps": [], "output_evidence": "artifact",
         "capability_requirements": {"tier": "trivial"}, "mission": PRODUCE,
         "verifications": [{"verification_id": "lint", "family": "deterministic"}]}]})
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, graph_text)
        report = pilot.advance(led, graph, rid, reg, Path(tmp) / "data", actor="t")
        assert [r["action"] for r in report] == ["executed", "manual"]
        assert "request-verification" in report[1]["reason"]
        assert fold(graph, led.run(rid), rid)["nodes"]["a"]["state"] == "executed"


def test_malformed_declaration_refuses_before_anything_runs():
    bad = json.dumps({"graph_id": "pilot-test", "nodes": [
        {"id": "a", "deps": [], "output_evidence": "artifact",
         "capability_requirements": {"tier": "trivial"}, "mission": PRODUCE,
         "verifications": [{"verification_id": "lint", "family": "deterministic",
                            "x_verifier": APPROVE}]}]})   # no timeout
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, bad)
        n = len(led.run(rid))
        try:
            pilot.advance(led, graph, rid, reg, Path(tmp) / "data", actor="t")
            assert False, "malformed x_verifier must refuse"
        except pilot.PilotRefused as exc:
            assert "timeout" in str(exc)
        assert len(led.run(rid)) == n and not (Path(tmp) / "data").exists()


# -- A6: interruption and repetition --------------------------------------------

def test_graceful_interrupt_records_intent_and_the_command_resumes():
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, _graph())
        data = Path(tmp) / "data"
        calls = []

        def stop():                    # the signal lands after a's dispatch
            calls.append(1)
            return len(calls) > 1
        report = pilot.advance(led, graph, rid, reg, data, actor="t",
                               stop_requested=stop)
        assert report[-1]["action"] == "interrupt_recorded"
        types = [t[0] for t in _types(led, rid)]
        assert types[-1] == "run_interrupt_requested"
        # what finished in the step is recorded; b was never dispatched
        assert types.count("node_dispatched") == 1
        assert fold(graph, led.run(rid), rid)["nodes"]["a"]["state"] == "completed"
        # same command again: same run, same attempt dirs, the rest proceeds
        report = pilot.advance(led, graph, rid, reg, data, actor="t")
        assert [r.get("node_id") for r in report] == ["b", "b", "b"]
        assert (data / "runs" / "pilot-test" / rid / "a" / "t1" / "out").exists()
        assert not (data / "runs" / "pilot-test" / rid / "a" / "t2").exists()


def test_interrupt_mid_step_starts_no_sibling_dispatch():
    """§10(a): once interruption is requested, no NEW dispatch starts — not
    even a sibling that was already ready in the same step. The producer of
    `a` raises the flag while it runs (a Ctrl+C mid-flight); `c`, ready
    alongside it, must stay untouched until the next command."""
    with tempfile.TemporaryDirectory() as tmp:
        flag = Path(tmp) / "interrupt"
        raise_flag = ("import os\nopen(os.environ['OUT'],'w').write('x\\n')\n"
                      f"open({str(flag)!r},'w').close()")
        node = {"deps": [], "output_evidence": "artifact",
                "capability_requirements": {"tier": "trivial"},
                "no_verification": "test fixture"}
        graph_text = json.dumps({"graph_id": "fanout", "nodes": [
            {"id": "a", "mission": raise_flag, **node},
            {"id": "c", "mission": PRODUCE, **node}]})
        led, graph, rid, reg = _setup(tmp, graph_text)
        data = Path(tmp) / "data"
        report = pilot.advance(led, graph, rid, reg, data, actor="t",
                               stop_requested=flag.exists)
        assert report[-1]["action"] == "interrupt_recorded"
        types = [t[0] for t in _types(led, rid)]
        assert types.count("node_dispatched") == 1, types
        nodes = fold(graph, led.run(rid), rid)["nodes"]
        assert nodes["a"]["state"] == "completed"
        assert nodes["c"]["state"] == "ready"
        assert not (data / "runs" / "fanout" / rid / "c").exists()
        # the next command picks c up; nothing about a is redone
        pilot.advance(led, graph, rid, reg, data, actor="t")
        assert fold(graph, led.run(rid), rid)["run_state"] == "completed"
        assert not (data / "runs" / "fanout" / rid / "a" / "t2").exists()


def test_second_pilot_is_refused_while_the_first_holds_the_run():
    with tempfile.TemporaryDirectory() as tmp:
        led, graph, rid, reg = _setup(tmp, _graph())
        from dagwell.adapters import worker
        with worker.pilot_lock(led, rid):
            try:
                pilot.advance(led, graph, rid, reg, Path(tmp) / "data", actor="t")
                assert False
            except Exception as exc:
                assert "another worker owns this run" in str(exc)
        assert len(led.run(rid)) == 1


# -- A1: doctor -----------------------------------------------------------------

def test_doctor_reports_actionable_failures_without_secrets():
    env = {**os.environ, "SUPERSECRET_TOKEN": "hunter2"}
    ok, lines = pilot.doctor(_graph(), REGISTRY, env=env)
    assert ok and any(l.startswith("ok: verifier a/a-check") for l in lines)
    assert any("NOT verified" in l for l in lines)
    assert not any("hunter2" in l for l in lines)
    # missing executable in a binding
    broken = json.loads(REGISTRY)
    broken["bindings"][0]["invocation"] = "no-such-binary-xyz {mission}"
    ok, lines = pilot.doctor(_graph(), json.dumps(broken), env=env)
    assert not ok and any("not found on PATH" in l for l in lines)
    assert any(l.startswith("FAIL: tier 'trivial'") for l in lines)
    # invalid registry, invalid graph
    ok, lines = pilot.doctor(_graph(), "{}", env=env)
    assert not ok and any(l.startswith("FAIL: registry") for l in lines)
    ok, lines = pilot.doctor("{}", REGISTRY, env=env)
    assert not ok and any(l.startswith("FAIL: graph") for l in lines)
    # verifier script path that does not exist
    g = json.loads(_graph())
    g["nodes"][0]["verifications"][0]["x_verifier"] = PY + " /nowhere/check.py"
    ok, lines = pilot.doctor(json.dumps(g), REGISTRY, env=env)
    assert not ok and any("'/nowhere/check.py' not found" in l for l in lines)


# -- the CLI surface -----------------------------------------------------------------

def test_cli_doctor_advance_status_and_the_shipped_template():
    """The shipped template is the flow a person copies: it must run as
    documented, end to end, through the real command line."""
    with tempfile.TemporaryDirectory() as tmp:
        tdir = Path(tmp) / "template"
        shutil.copytree(ROOT / "examples" / "template-report", tdir)
        g, r, i = str(tdir / "graph.json"), str(tdir / "registry.json"), str(tdir / "input.txt")
        led, data = str(tdir / "run.jsonl"), str(tdir / "data")
        rc, out, _ = _run("doctor", "--graph", g, "--registry", r, "--data-dir", data)
        assert rc == 0 and "doctor: ok" in out
        rc, out, _ = _run("start", "--ledger", led, "--graph", g, "--input", i)
        assert rc == 0
        run_id = out.strip()
        base = ["--ledger", led, "--graph", g, "--run", run_id]
        adv = ["advance", *base, "--registry", r, "--data-dir", data]
        rc, out, _ = _run(*adv)
        assert rc == 0 and "plan only" in out and not Path(data).exists()
        # --node on the first node: executed + verified, nothing "refused"
        rc, out, _ = _run(*adv, "--go", "--actor", "pilot-test", "--node", "dataset")
        assert rc == 0 and "refused" not in out, out
        assert "verifier dataset/csv-shape (v1): status completed, verdict approved" in out
        rc, out, _ = _run(*adv, "--go", "--actor", "pilot-test")
        assert rc == 0 and "gate report/review: gate_open" in out
        assert "next: decide --node report" in out
        rc, out, _ = _run("status", *base)
        assert "report: waiting_human" in out and "next: decide --node report" in out
        rc, _, _ = _run("decide", *base, "--node", "report", "approved",
                        "--actor", "fixture-test-actor", "--reason", "test fixture")
        assert rc == 0
        rc, out, _ = _run(*adv, "--go", "--actor", "pilot-test")
        assert rc == 0 and "next: nothing — the run is completed" in out
        report = Path(data) / "runs" / "report-template" / run_id / "report" / "t1" / "out"
        assert report.read_text().startswith("# Synthetic report")
        # failure exits nonzero and names the next action
        events = [json.loads(l) for l in Path(led).read_text().splitlines()]
        assert [e["event_type"] for e in events][-1] == "verdict_recorded"
        assert events[-1]["family"] == "human" and events[-1]["actor"] == "fixture-test-actor"


def test_cli_advance_exits_nonzero_on_failure_and_status_names_the_retry():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "graph.json").write_text(_graph(a_mission=LIAR), encoding="utf-8")
        (tmp / "registry.json").write_text(REGISTRY, encoding="utf-8")
        (tmp / "input.txt").write_text("t\n", encoding="utf-8")
        rc, out, _ = _run("start", "--ledger", str(tmp / "run.jsonl"), "--graph",
                          str(tmp / "graph.json"), "--input", str(tmp / "input.txt"))
        run_id = out.strip()
        base = ["--ledger", str(tmp / "run.jsonl"), "--graph", str(tmp / "graph.json"),
                "--run", run_id]
        rc, out, _ = _run("advance", *base, "--registry", str(tmp / "registry.json"),
                          "--data-dir", str(tmp / "data"), "--go")
        assert rc == 1 and "producer a (attempt 1): failed" in out
        assert "human-retry --node a opens attempt 2" in out


if __name__ == "__main__":
    fns = [v for k, v in sorted(vars(sys.modules["__main__"]).items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"test_pilot: {len(fns)} tests PASS")
