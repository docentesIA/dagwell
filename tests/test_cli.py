"""CLI surface: the full governed cycle driven from the command line.

The CLI is presentation only — every refusal here is enforced below. What these
tests protect is that the commands EXIST and stay wired to the governed
operations, because that is what a person installing the package can actually
reach. Output is captured, never printed: a test suite that prints refusal
messages reads like a failing suite to whoever runs it for the first time.
"""

import io
import json
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from dagwell import cli

from helpers import artifact_evidence

_PAYLOAD = artifact_evidence(path="o.bin")
EVID = _PAYLOAD["evidence_id"]
ARTIFACT = json.dumps(_PAYLOAD)
GRAPH = json.dumps({"graph_id": "release", "nodes": [
    {"id": "build", "deps": [], "output_evidence": "artifact",
     "verifications": [{"verification_id": "tests", "family": "deterministic"}]},
    {"id": "ship", "deps": ["build"], "output_evidence": "artifact",
     "verifications": [{"verification_id": "signoff", "family": "human"}]}]})


def run(*argv):
    """Invoke the CLI, capturing both streams. Returns (rc, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = cli.main(list(argv))
    return rc, out.getvalue(), err.getvalue()


def test_version_and_demo_need_no_ledger():
    rc, out, _ = run("demo")
    assert rc == 0
    # the demo exists to show the thesis; if it stops showing it, it is broken
    assert "executed" in out and "completed" in out


def test_full_cycle_from_the_command_line():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "graph.json").write_text(GRAPH, encoding="utf-8")
        (tmp / "input.txt").write_text("the release task\n", encoding="utf-8")
        led, gph = str(tmp / "run.jsonl"), str(tmp / "graph.json")

        rc, out, _ = run("start", "--ledger", led, "--graph", gph,
                         "--input", str(tmp / "input.txt"))
        assert rc == 0
        run_id = out.strip()
        base = ["--ledger", led, "--graph", gph, "--run", run_id]

        rc, out, _ = run("ready", *base)
        assert rc == 0 and out.startswith("build")

        assert run("dispatch", *base, "--node", "build")[0] == 0
        assert run("return", *base, "--node", "build", "--attempt", "1",
                   "--exit-code", "0", "--evidence", ARTIFACT)[0] == 0

        # transport succeeded and evidence is present: still not completed
        rc, out, _ = run("status", *base)
        assert "build: executed" in out

        assert run("request-verification", *base, "--node", "build",
                   "--verification", "tests")[0] == 0
        assert run("verdict", *base, "--node", "build", "--verification",
                   "tests", "--status", "completed", "--verdict",
                   "approved")[0] == 0

        rc, out, _ = run("status", *base)
        assert "build: completed" in out and "ship: ready" in out

        # the human gate on the second node
        assert run("dispatch", *base, "--node", "ship")[0] == 0
        assert run("return", *base, "--node", "ship", "--attempt", "1",
                   "--exit-code", "0", "--evidence", ARTIFACT)[0] == 0
        assert run("request-verification", *base, "--node", "ship",
                   "--verification", "signoff")[0] == 0
        assert run("decide", *base, "--node", "ship", "approved",
                   "--actor", "rey")[0] == 0

        rc, out, _ = run("status", *base)
        assert "ship: completed" in out and ": completed" in out


def test_the_cli_cannot_issue_a_human_verdict_through_verdict():
    """`verdict` is the machine surface. The human family is refused there and
    exists only through `decide` (I8) — the CLI must not become the way around
    the boundary the library enforces."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "graph.json").write_text(GRAPH, encoding="utf-8")
        (tmp / "input.txt").write_text("t\n", encoding="utf-8")
        led, gph = str(tmp / "run.jsonl"), str(tmp / "graph.json")
        run_id = run("start", "--ledger", led, "--graph", gph,
                     "--input", str(tmp / "input.txt"))[1].strip()
        base = ["--ledger", led, "--graph", gph, "--run", run_id]
        run("dispatch", *base, "--node", "build")
        run("return", *base, "--node", "build", "--attempt", "1",
            "--exit-code", "0", "--evidence", ARTIFACT)
        run("request-verification", *base, "--node", "build",
            "--verification", "tests")
        run("verdict", *base, "--node", "build", "--verification", "tests",
            "--status", "completed", "--verdict", "approved")
        run("dispatch", *base, "--node", "ship")
        run("return", *base, "--node", "ship", "--attempt", "1",
            "--exit-code", "0", "--evidence", ARTIFACT)
        run("request-verification", *base, "--node", "ship",
            "--verification", "signoff")
        # the open verification is family human: the machine surface refuses it
        rc, _, err = run("verdict", *base, "--node", "ship", "--verification",
                         "signoff", "--status", "completed", "--verdict",
                         "approved")
        assert rc == 1 and "refused" in err


def test_unknown_run_is_refused_not_projected():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "graph.json").write_text(GRAPH, encoding="utf-8")
        (tmp / "run.jsonl").write_text("", encoding="utf-8")
        rc, _, err = run("status", "--ledger", str(tmp / "run.jsonl"),
                         "--graph", str(tmp / "graph.json"),
                         "--run", "id-that-does-not-exist")
        assert rc == 1 and "unknown run" in err


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(vars(sys.modules["__main__"]).items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"test_cli: {len(fns)} tests PASS")
