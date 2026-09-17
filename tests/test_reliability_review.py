"""Independent reliability review of 0.0.3: the six defects fixed in 0.0.4.

Each test reproduces one finding and fails on 0.0.3. Zero cost: the "agents"
and the verifiers are `python3 -c`, nothing leaves the temp directory.

D1 ledger framing: a record holding U+0085/U+2028/U+2029 is written and then
   unreadable, because reading splits on Unicode line breaks (ledger.py).
D2 evidence: a verifier that rewrites, deletes or replaces $OUT still gets its
   `approved` accepted — the digest is checked before it runs, never after.
D3 probe: on timeout the probe abandons its descendants, which keep writing.
D4 interrupt: an interrupt already requested does not stop a NEW verifier from
   being requested and executed before the run stops.
D5 doctor: any argument containing a slash is treated as a path, so inline code
   is reported as a missing file while `advance` runs the node fine.
D6 resume: the CLI reads --graph and passes None to the library — a tampered
   graph is accepted silently, and a valid snapshot cannot be used without the
   original file.
"""

import json
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from dagwell import runtime
from dagwell.adapters import pilot, worker
from dagwell.adapters.transports import subprocess_transport as st
from dagwell.fold import fold
from dagwell.ledger import Ledger, LedgerIntegrityError, create_run
from test_cli import run as cli_run
from test_pilot import PY, REGISTRY, _graph, _setup

DEADLINE = 30.0


def _await(predicate, what):
    """Bounded wait on a real condition — never a bare sleep."""
    deadline = time.monotonic() + DEADLINE
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {what}")


# -- D1: JSONL framing is physical lines, not Unicode line breaks -------------

def test_unicode_line_breaks_survive_the_round_trip_and_framing_stays_physical():
    with tempfile.TemporaryDirectory() as tmp:
        for char in ("\u0085", "\u2028", "\u2029"):   # NEL, LS, PS
            led = Ledger(Path(tmp) / f"u{ord(char):04x}.jsonl")
            ref = "synthetic://a" + char + "b"
            founding = create_run(led, graph_id="pilot-test", graph_text=_graph(),
                                  input_text="t\n", input_ref=ref)
            events = led.run(founding["run_id"])          # 0.0.3: raises here
            assert len(events) == 1
            assert events[0]["input_ref"] == ref, "the character must survive"

        # CRLF and a missing final newline are both readable; a ledger written
        # elsewhere is read as it is, never rewritten to be readable.
        src = (Path(tmp) / "u0085.jsonl").read_text(encoding="utf-8")
        crlf = Path(tmp) / "crlf.jsonl"
        crlf.write_text(src.replace("\n", "\r\n").rstrip("\r\n"), encoding="utf-8")
        assert Ledger(crlf).events() == Ledger(Path(tmp) / "u0085.jsonl").events()

        # A malformed record is still refused — framing is fixed, not loosened.
        bad = Path(tmp) / "bad.jsonl"
        bad.write_text(src + "{not json}\n", encoding="utf-8")
        try:
            Ledger(bad).events()
            assert False, "a malformed record must still be refused"
        except LedgerIntegrityError:
            pass


# -- D2: the verdict binds to the evidence that is still there ----------------

def _tamper(code):
    return (PY + ' -c "import json,os;' + code
            + ";print(json.dumps({'verdict':'approved','reasons':['ok']}))\"")


REWRITE = _tamper("open(os.environ['OUT'],'w').write('CHANGED')")
DELETE = _tamper("os.remove(os.environ['OUT'])")
UNREADABLE = _tamper("os.chmod(os.environ['OUT'], 0)")
SWAP = _tamper("p=os.environ['OUT'];d=p+'.decoy';open(d,'w').write('data-v1\\n');"
               "os.remove(p);os.symlink(d,p)")


def test_a_verifier_that_changes_the_artifact_never_gets_its_verdict_accepted():
    cases = [("rewrite", REWRITE), ("delete", DELETE), ("swap", SWAP)]
    if os.geteuid() != 0:          # root reads through any permission bits
        cases.append(("unreadable", UNREADABLE))
    for label, verifier in cases:
        with tempfile.TemporaryDirectory() as tmp:
            led, graph, rid, reg = _setup(tmp, _graph(a_verifier=verifier))
            data = Path(tmp) / "data"
            pilot.advance(led, graph, rid, reg, data, actor="review-fixture")
            events = led.run(rid)
            verdicts = [e for e in events if e["event_type"] == "verdict_recorded"]
            assert len(verdicts) == 1, label
            # honest outcome: the process could not conclude; no verdict at all
            assert verdicts[0]["verification_status"] == "error", label
            assert verdicts[0].get("verdict") is None, label
            nodes = fold(graph, events, rid)["nodes"]
            assert nodes["a"]["state"] != "completed", label   # 0.0.3: completed
            assert nodes["b"]["state"] == "pending", label     # never released
            assert any(e["event_type"] == "human_escalation" for e in events), label
            # the verifier's own record is kept, not erased
            results = list((data / "verifications").rglob("result.json"))
            assert len(results) == 1 and (results[0].parent / "log.txt").exists(), label


# -- D3: a probe timeout takes its whole process group with it ----------------

def _probe_fixture(pidfile, marker, sleep_for, stubborn):
    """A probe whose LEADER exits on the first polite signal but which leaves a
    descendant behind. `stubborn` makes that descendant ignore INT and TERM, so
    only the final SIGKILL to the group can stop it."""
    ignore = ("import signal;signal.signal(signal.SIGINT,signal.SIG_IGN);"
              "signal.signal(signal.SIGTERM,signal.SIG_IGN);" if stubborn else "")
    child = (ignore + "import os,time;from pathlib import Path;"
             f"Path({str(pidfile)!r}).write_text(str(os.getpid()));"
             f"time.sleep({sleep_for});"
             f"Path({str(marker)!r}).write_text('late')")
    return ("import subprocess,sys,time;"
            f"subprocess.Popen([sys.executable,'-c',{child!r}]);time.sleep(30)")


def test_probe_timeout_kills_descendants_and_spares_the_caller_group():
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        sibling = subprocess.Popen([PY, "-c", "import time;time.sleep(30)"])
        try:
            # (a) a cooperative descendant is gone before it can write at all
            probe = _probe_fixture(t / "a.pid", t / "a.late", 0.4, stubborn=False)
            started = time.monotonic()
            alive = st.probe({"probe": f"{PY} -c {json.dumps(probe)}"},
                             env=dict(os.environ), timeout_seconds=0.25)
            elapsed = time.monotonic() - started
            assert alive is False
            assert elapsed < 5, f"the kill ladder must stay bounded ({elapsed:.1f}s)"
            assert sibling.poll() is None, "the caller's own group was signalled"
            _await(lambda: (t / "a.pid").exists(), "the fixture descendant to start")
            deadline = time.monotonic() + 1.5
            while time.monotonic() < deadline:
                time.sleep(0.05)
            assert not (t / "a.late").exists(), "a descendant outlived the probe"

            # (b) one that ignores INT and TERM is still killed: it would write
            # after the ladder ends, and the write never happens
            probe = _probe_fixture(t / "b.pid", t / "b.late", 3, stubborn=True)
            started = time.monotonic()
            alive = st.probe({"probe": f"{PY} -c {json.dumps(probe)}"},
                             env=dict(os.environ), timeout_seconds=0.25)
            ladder = time.monotonic() - started
            assert alive is False
            _await(lambda: (t / "b.pid").exists(), "the stubborn descendant to start")
            deadline = started + 4                # past its own sleep(3)
            while time.monotonic() < deadline:
                time.sleep(0.05)
            assert not (t / "b.late").exists(), (
                "the descendant finished its work after the probe had answered: "
                f"the kill ladder took {ladder:.1f}s, longer than the work itself")
            assert ladder < 3, f"the ladder must stay bounded ({ladder:.1f}s)"
            assert sibling.poll() is None, "the caller's own group was signalled"
        finally:
            sibling.kill()
            sibling.wait()


def test_the_short_grace_belongs_to_the_probe_alone():
    """A probe answers a question; a producer does work. The short goodbye is
    the probe's and must never quietly become the producer's — so this checks
    the wiring, not the constants: `execute` asks for no grace at all (the
    module's GRACE_SECONDS applies, and stays patchable at call time), while
    `probe` asks for the short one."""
    assert st.PROBE_GRACE_SECONDS < st.GRACE_SECONDS
    seen = []

    def capture(argv, **kwargs):
        seen.append(kwargs.get("grace_seconds"))
        return {"transport": "subprocess", "exit_code": 0,
                "duration_seconds": 0.0, "timed_out": False}

    with tempfile.TemporaryDirectory() as tmp:
        with patch.object(st, "run_argv", capture):
            st.probe({"probe": f"{PY} --version"}, env=dict(os.environ))
            st.execute({"invocation": PY + " -c {mission}", "timeout_seconds": 5},
                       "pass", str(Path(tmp) / "out"), env=dict(os.environ))
    probe_grace, producer_grace = seen
    assert probe_grace == st.PROBE_GRACE_SECONDS, probe_grace
    assert producer_grace is None, "a producer's ladder must keep the full grace"


# -- D4: an interrupt stops the next verifier, by callback and by real signal --

def _marker_verifier(path):
    return (PY + ' -c "import json;from pathlib import Path;'
            f"Path({str(path)!r}).write_text('ran');"
            "print(json.dumps({'verdict':'approved'}))\"")


def test_interrupt_requested_starts_no_new_verifier():
    with tempfile.TemporaryDirectory() as tmp:
        marker = Path(tmp) / "verifier-ran"
        led, graph, rid, reg = _setup(tmp, _graph(a_verifier=_marker_verifier(marker)))
        data = Path(tmp) / "data"
        worker.work(led, graph, rid, reg, data, go=True, node_id="a")
        pilot.advance(led, graph, rid, reg, data, node_id="a",
                      actor="review-fixture", stop_requested=lambda: True)
        kinds = [e["event_type"] for e in led.run(rid)]
        assert not marker.exists(), "a verifier started after the interrupt"
        assert "verification_requested" not in kinds
        assert "verdict_recorded" not in kinds
        assert kinds[-1] == "run_interrupt_requested"
        assert "node_returned" in kinds, "finished work must stay recorded"


def _peek(proc):
    """What the CLI has already said on stderr, without blocking on it."""
    os.set_blocking(proc.stderr.fileno(), False)
    try:
        return proc.stderr.read() or ""
    except (BlockingIOError, TypeError):
        return ""


def test_real_sigint_stops_before_the_verifier_and_keeps_finished_work():
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        started, release, ran = t / "started", t / "release", t / "verifier-ran"
        mission = (
            "import os,time\n"
            "open(os.environ['OUT'],'w').write('data-v1\\n')\n"
            f"open({str(started)!r},'w').close()\n"
            f"deadline=time.monotonic()+{DEADLINE}\n"
            f"while not os.path.exists({str(release)!r}) and time.monotonic()<deadline:\n"
            "    time.sleep(0.01)\n")
        graph_text = _graph(a_mission=mission, a_verifier=_marker_verifier(ran))
        (t / "graph.json").write_text(graph_text, encoding="utf-8")
        (t / "registry.json").write_text(REGISTRY, encoding="utf-8")
        led, graph, rid, _ = _setup(tmp, graph_text)
        argv = [PY, "-m", "dagwell.cli", "advance",
                "--ledger", str(led.path), "--graph", str(t / "graph.json"),
                "--run", rid, "--registry", str(t / "registry.json"),
                "--data-dir", str(t / "data"), "--actor", "review-fixture", "--go"]
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        try:
            _await(started.exists, "the producer to start")
            proc.send_signal(signal.SIGINT)      # a real Ctrl+C, not a callback
            seen = []

            def reacted():
                seen.append(_peek(proc))
                return "interrupt requested" in "".join(seen)

            _await(reacted, "the CLI's interrupt handler to react")
            release.touch()                      # only now the producer finishes
            proc.wait(timeout=DEADLINE)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
        kinds = [e["event_type"] for e in led.run(rid)]
        assert "node_returned" in kinds, "the finished producer must be recorded"
        assert not ran.exists(), "a verifier started after a real SIGINT"
        assert "verification_requested" not in kinds
        assert "run_interrupt_requested" in kinds
        assert fold(graph, led.run(rid), rid)["nodes"]["a"]["state"] == "executed"


# -- D5: doctor validates what the interface says is a path, nothing else -----

INLINE = (PY + ' -c "import json;'
          "print(json.dumps({'verdict':'approved','reasons':['a/b']}))\"")
URLISH = (PY + ' -c "import json;'
          "print(json.dumps({'verdict':'approved'}))\" --ref https://example.invalid/x")


def _doctor(graph_text, graph_dir=None):
    ok, lines = pilot.doctor(graph_text, REGISTRY, None, graph_dir=graph_dir)
    return ok, [line for line in lines if line.startswith("FAIL:")]


def test_doctor_does_not_mistake_inline_code_or_text_for_a_path():
    for label, verifier in (("inline", INLINE), ("url", URLISH)):
        ok, fails = _doctor(_graph(a_verifier=verifier))
        assert ok, f"{label}: doctor invented a path: {fails}"      # 0.0.3: FAIL


def test_doctor_still_fails_on_a_declared_path_and_a_missing_executable():
    with tempfile.TemporaryDirectory() as tmp:
        ok, fails = _doctor(_graph(a_verifier="python3 {graph_dir}/absent_check.py"),
                            graph_dir=tmp)
        assert not ok and "absent_check.py" in fails[0], fails
        ok, fails = _doctor(_graph(a_verifier="dagwell-no-such-executable --x"))
        assert not ok and "not found on PATH" in fails[0], fails


# -- D6: resume says what it does with --graph --------------------------------

def _resume_fixture(tmp):
    t = Path(tmp)
    led = Ledger(t / "run.jsonl")
    graph_text = _graph()
    _, founding = runtime.start_run(led, graph_text=graph_text, input_text="t\n",
                                    input_ref="synthetic://resume")
    (t / "graph.json").write_text(graph_text, encoding="utf-8")
    (t / "input.txt").write_text("t\n", encoding="utf-8")
    tampered = json.loads(graph_text)
    tampered["nodes"][0]["mission"] = "print('DIFFERENT GRAPH')"
    (t / "tampered.json").write_text(json.dumps(tampered), encoding="utf-8")
    return led, founding["run_id"], t


def test_resume_validates_the_graph_it_is_given():
    with tempfile.TemporaryDirectory() as tmp:
        led, rid, t = _resume_fixture(tmp)
        base = ["--ledger", str(led.path), "--run", rid,
                "--input", str(t / "input.txt")]
        rc, _, err = cli_run("resume", *base, "--graph", str(t / "graph.json"))
        assert rc == 0, err                       # the run's own graph resumes
        rc, _, err = cli_run("resume", *base, "--graph", str(t / "tampered.json"))
        assert rc == 1, "a different graph must be refused"      # 0.0.3: exit 0
        assert "graph_version" in err, err


def test_resume_from_snapshot_needs_no_original_file():
    with tempfile.TemporaryDirectory() as tmp:
        led, rid, t = _resume_fixture(tmp)
        base = ["--ledger", str(led.path), "--run", rid,
                "--input", str(t / "input.txt")]
        (t / "graph.json").unlink()                # the original file is gone
        rc, _, err = cli_run("resume", *base, "--from-snapshot")
        assert rc == 0, err                        # 0.0.3: no such path exists
        # the two sources are mutually exclusive, and one must be chosen
        rc, _, err = cli_run("resume", *base, "--from-snapshot",
                             "--graph", str(t / "tampered.json"))
        assert rc != 0 and "--from-snapshot" in err, err
        rc, _, err = cli_run("resume", *base)
        assert rc != 0 and "--from-snapshot" in err, err


def test_resume_keeps_the_snapshot_and_input_hash_validations():
    with tempfile.TemporaryDirectory() as tmp:
        led, rid, t = _resume_fixture(tmp)
        base = ["--ledger", str(led.path), "--run", rid]
        (t / "other.txt").write_text("a different agenda\n", encoding="utf-8")
        rc, _, err = cli_run("resume", *base, "--input", str(t / "other.txt"),
                             "--graph", str(t / "graph.json"))
        assert rc == 1 and "input_hash" in err, err
        snapshot = next((t / "graphs").glob("*.graph"))
        snapshot.write_text("corrupted snapshot\n", encoding="utf-8")
        rc, _, err = cli_run("resume", *base, "--input", str(t / "input.txt"),
                             "--from-snapshot")
        assert rc == 1 and "snapshot" in err, err
        snapshot.unlink()
        rc, _, err = cli_run("resume", *base, "--input", str(t / "input.txt"),
                             "--from-snapshot")
        assert rc == 1 and "snapshot" in err, err


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().copy().items()) if k.startswith("test_")]
    for test in tests:
        test()
    print(f"test_reliability_review: {len(tests)} tests PASS")
