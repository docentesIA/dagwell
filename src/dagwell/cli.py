"""dagwell CLI — a PRESENTATION surface only.

It parses arguments, calls the governed domain operations (dagwell.human,
dagwell.fold) and prints results. No authority invariant lives here: the
human-only write privilege and every precondition are enforced below, in the
domain layer and the ledger (I8). Display strings may be localized in the
future; canonical identifiers never are (H1).
"""

import argparse
import getpass
import json
import sys
from pathlib import Path

from dagwell import human
from dagwell.fold import fold
from dagwell.graph import load_graph
from dagwell.ledger import Ledger


def _load(args):
    ledger = Ledger(args.ledger)
    graph = load_graph(Path(args.graph).read_text(encoding="utf-8"))
    return ledger, graph


def _print_status(folded):
    print(f"run {folded['run_id']}: {folded['run_state']} "
          f"(integrity: {folded['integrity']})")
    for nid, info in folded["nodes"].items():
        att = f" attempt {info['attempt']}" if info["attempt"] else ""
        print(f"  {nid}: {info['state']}{att}")
    if folded["anomalies"]:
        for a in folded["anomalies"]:
            print(f"  ! {a}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="dagwell")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--ledger", required=True)
        p.add_argument("--graph", required=True)
        p.add_argument("--run", required=True)

    p_status = sub.add_parser("status", help="read-only projection")
    common(p_status)

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

    p_cancel = sub.add_parser("cancel", help="cancel the run (absorbing)")
    common(p_cancel)
    p_cancel.add_argument("--actor", default=getpass.getuser())

    args = parser.parse_args(argv)
    ledger, graph = _load(args)
    try:
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
        elif args.command == "decide":
            e = human.decide(ledger, graph, args.run, args.node, args.verdict,
                             actor=args.actor, reason=args.reason)
            print(json.dumps(e, indent=2, ensure_ascii=False))
        elif args.command == "human-retry":
            e = human.human_retry(ledger, graph, args.run, args.node,
                                  actor=args.actor)
            print(json.dumps(e, indent=2, ensure_ascii=False))
        elif args.command == "cancel":
            e = human.cancel_run(ledger, graph, args.run, actor=args.actor)
            print(json.dumps(e, indent=2, ensure_ascii=False))
    except Exception as exc:  # presentation: report, exit nonzero
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
