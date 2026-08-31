"""dagwell CLI — a PRESENTATION surface only.

It parses arguments, calls the governed domain operations (dagwell.operations,
dagwell.human, dagwell.runtime, dagwell.fold) and prints results. No authority
invariant lives here: the human-only write privilege and every precondition are
enforced below, in the domain layer and the ledger (I8). Display strings may be
localized in the future; canonical identifiers never are (H1).

Nothing in this file dispatches work to a provider or spends anything.
`dispatch` records that a node was HANDED OUT; the work itself happens by
whatever means the operator already uses, and `return` records what came back.
Transport belongs to the Adapter milestone, not here.
"""

import argparse
import getpass
import json
import sys
import tempfile
from pathlib import Path

from dagwell import __version__, canonical, human, operations, runtime
from dagwell.fold import fold
from dagwell.graph import load_graph
from dagwell.ledger import Ledger

LAND_REASONS = ("budget_exhausted", "retries_exhausted", "human_rejection")


def _load(args):
    ledger = Ledger(args.ledger)
    graph = load_graph(Path(args.graph).read_text(encoding="utf-8"))
    return ledger, graph


def _evidence(raw):
    """--evidence takes inline JSON, or @path to read it from a file."""
    if raw is None:
        return None
    if raw.startswith("@"):
        raw = Path(raw[1:]).read_text(encoding="utf-8")
    return json.loads(raw)


def _print_status(folded):
    print(f"run {folded['run_id']}: {folded['run_state']} "
          f"(integrity: {folded['integrity']})")
    for nid, info in folded["nodes"].items():
        att = f" attempt {info['attempt']}" if info["attempt"] else ""
        print(f"  {nid}: {info['state']}{att}")
    if folded["anomalies"]:
        for a in folded["anomalies"]:
            print(f"  ! {a}")


def _emit(event):
    print(json.dumps(event, indent=2, ensure_ascii=False))


def _demo():
    """Run the whole governed cycle in a throwaway directory and narrate it.

    The point is the two states near the end: a successful return with valid
    evidence lands on `executed`, and only the human gate makes it `completed`.
    """
    graph_text = json.dumps({"graph_id": "demo", "nodes": [
        {"id": "write-report", "deps": [], "output_evidence": "artifact",
         "verifications": [{"verification_id": "review", "family": "human"}]}]})
    digest = "sha256:" + "ab" * 32
    manifest = [{"path": "report.md", "artifact_digest": digest,
                 "size_bytes": 2}]
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Ledger(Path(tmp) / "run.jsonl")
        graph, founding = runtime.start_run(
            ledger, graph_text=graph_text, input_text="the task",
            input_ref="demo://task")
        rid = founding["run_id"]
        print(f"1. started run {rid}")

        operations.dispatch(ledger, graph, rid, "write-report")
        print("2. dispatched 'write-report' — the work itself happens outside "
              "dagwell; nothing was spent")

        operations.record_return(
            ledger, graph, rid, "write-report", attempt=1, exit_code=0,
            output_evidence={"type": "artifact",
                             "evidence_id": canonical.json_digest(manifest),
                             "output_manifest": manifest})
        state = fold(graph, ledger.run(rid), rid)["nodes"]["write-report"]["state"]
        print(f"3. recorded a successful return with evidence -> {state}")
        print("   exit code 0 AND evidence present, and it is still not completed")

        operations.request_verification(ledger, graph, rid, "write-report",
                                        verification_id="review")
        human.decide(ledger, graph, rid, "write-report", "approved", actor="you")
        state = fold(graph, ledger.run(rid), rid)["nodes"]["write-report"]["state"]
        print(f"4. the human approved the gate -> {state}")

        print("")
        print("   executed != completed: transport alone completes nothing.")
        print("   Against a real ledger, start here: dagwell start --help")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="dagwell",
        description="Govern agent work as a graph over an append-only ledger.")
    parser.add_argument("--version", action="version",
                        version=f"dagwell {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--ledger", required=True, help="path to the ledger JSONL")
        p.add_argument("--graph", required=True, help="path to the graph JSON")
        p.add_argument("--run", required=True, help="run id")

    sub.add_parser("demo", help="run the whole cycle in a temp dir and explain it")

    p_start = sub.add_parser("start",
                             help="create a run (validates fail-closed first)")
    p_start.add_argument("--ledger", required=True)
    p_start.add_argument("--graph", required=True)
    p_start.add_argument("--input", required=True,
                         help="path to the run's input file")
    p_start.add_argument("--input-ref",
                         help="provenance reference (default: file://<path>)")

    p_ready = sub.add_parser("ready", help="list nodes the topology has unblocked")
    common(p_ready)

    p_status = sub.add_parser("status", help="read-only projection")
    common(p_status)

    p_dispatch = sub.add_parser(
        "dispatch", help="record that a node was handed out (does NOT run it)")
    common(p_dispatch)
    p_dispatch.add_argument("--node", required=True)

    p_return = sub.add_parser("return", help="record the transport return")
    common(p_return)
    p_return.add_argument("--node", required=True)
    p_return.add_argument("--attempt", type=int, required=True)
    p_return.add_argument("--exit-code", type=int, required=True)
    p_return.add_argument("--evidence",
                          help="output evidence as inline JSON, or @file")

    p_req = sub.add_parser("request-verification",
                           help="open the verification the order requires next")
    common(p_req)
    p_req.add_argument("--node", required=True)
    p_req.add_argument("--verification", required=True)

    p_verdict = sub.add_parser(
        "verdict", help="record a NON-human verdict (human verdicts: use decide)")
    common(p_verdict)
    p_verdict.add_argument("--node", required=True)
    p_verdict.add_argument("--verification", required=True)
    p_verdict.add_argument("--status", required=True,
                           choices=["completed", "error", "timeout", "cancelled"])
    p_verdict.add_argument("--verdict", choices=["approved", "rejected"],
                           help="required iff --status completed")
    p_verdict.add_argument("--reason")
    p_verdict.add_argument("--actor", default=getpass.getuser())

    p_decide = sub.add_parser("decide", help="record the human verdict")
    common(p_decide)
    p_decide.add_argument("--node", required=True)
    p_decide.add_argument("verdict", choices=["approved", "rejected"])
    p_decide.add_argument("--reason")
    p_decide.add_argument("--actor", default=getpass.getuser())

    p_retry = sub.add_parser("human-retry", help="open producer attempt k+1")
    common(p_retry)
    p_retry.add_argument("--node", required=True)
    p_retry.add_argument("--actor", default=getpass.getuser())

    p_land = sub.add_parser("land",
                            help="land the run (WIP saved, never truncated)")
    common(p_land)
    p_land.add_argument("--reason", required=True, choices=LAND_REASONS)

    p_resume = sub.add_parser("resume",
                              help="resume the same run after interruption")
    common(p_resume)
    p_resume.add_argument("--input", required=True)

    p_cancel = sub.add_parser("cancel", help="cancel the run (absorbing)")
    common(p_cancel)
    p_cancel.add_argument("--actor", default=getpass.getuser())

    args = parser.parse_args(argv)

    if args.command == "demo":
        return _demo()

    try:
        if args.command == "start":
            input_path = Path(args.input)
            _, founding = runtime.start_run(
                Ledger(args.ledger),
                graph_text=Path(args.graph).read_text(encoding="utf-8"),
                input_text=input_path.read_text(encoding="utf-8"),
                input_ref=args.input_ref or f"file://{input_path.resolve()}")
            print(founding["run_id"])
            return 0

        ledger, graph = _load(args)

        if args.command == "status":
            revents = ledger.run(args.run)
            if not revents:
                # A run with NO events is not a run at rest — it does not
                # exist, and projecting it would make a mistyped id read as a
                # real stalled run. A run that HAS events but no authoritative
                # run_created is a different case: damaged identity, still
                # readable diagnostically (§2).
                raise LookupError(f"unknown run: {args.run}")
            _print_status(fold(graph, revents, args.run))
        elif args.command == "ready":
            nodes = runtime.ready_nodes(graph, ledger, args.run)
            if not nodes:
                print("nothing dispatchable")
            for nid, attempt in nodes:
                print(f"{nid} (next attempt {attempt})")
        elif args.command == "dispatch":
            _emit(operations.dispatch(ledger, graph, args.run, args.node))
        elif args.command == "return":
            _emit(operations.record_return(
                ledger, graph, args.run, args.node, attempt=args.attempt,
                exit_code=args.exit_code,
                output_evidence=_evidence(args.evidence)))
        elif args.command == "request-verification":
            _emit(operations.request_verification(
                ledger, graph, args.run, args.node,
                verification_id=args.verification))
        elif args.command == "verdict":
            _emit(operations.record_machine_verdict(
                ledger, graph, args.run, args.node, args.verification,
                verification_status=args.status, verdict=args.verdict,
                actor=args.actor, reason=args.reason))
        elif args.command == "decide":
            _emit(human.decide(ledger, graph, args.run, args.node, args.verdict,
                               actor=args.actor, reason=args.reason))
        elif args.command == "human-retry":
            _emit(human.human_retry(ledger, graph, args.run, args.node,
                                    actor=args.actor))
        elif args.command == "land":
            _emit(operations.land_run(ledger, graph, args.run, args.reason))
        elif args.command == "resume":
            _emit(runtime.resume(ledger, None,
                                 Path(args.input).read_text(encoding="utf-8"),
                                 args.run))
        elif args.command == "cancel":
            _emit(human.cancel_run(ledger, graph, args.run, actor=args.actor))
    except Exception as exc:  # presentation: report, exit nonzero
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
