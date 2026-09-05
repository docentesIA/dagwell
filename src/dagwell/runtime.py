"""Recovery substrate: run creation, verification advancement, interruption,
orphan observation, resume (contract §1, §3, §4, §8, §10).

All operational mutations route through the governed boundary
(dagwell.operations; human decisions through dagwell.human). No transports
are executed here; the capability worker lives at the adapter edge.
With no Runtime Policy Specification (§13.12) automatic retry/re-fire is
DISABLED — fail-closed: verifier error/timeout/orphaned outcomes escalate to
the human; interruption-cancelled verifications re-fire without policy burn
(§6/§10). Orphan observation uses only the injected constatation provider
(ADR-0005): no provider → nothing orphaned; no universal timeout.
"""

from dagwell import canonical, operations, snapshots
from dagwell.fold import fold
from dagwell.graph import load_graph
from dagwell.ledger import Ledger, create_run, events as ev
from dagwell.operations import OperationRefused


class ResumeRefused(ev.LedgerError):
    pass


def _snapshot_dir(ledger: Ledger):
    return ledger.path.parent / "graphs"


# -- run creation (the --go validation home) -------------------------------

def start_run(ledger: Ledger, *, graph_text, input_text, input_ref,
              parent_run_id=None):
    """Validate the graph fail-closed, persist the frozen snapshot (I24) in
    the private data area beside the ledger, then create the run."""
    graph = load_graph(graph_text)
    snapshots.store(_snapshot_dir(ledger), graph_text)
    founding = create_run(ledger, graph_id=graph["graph_id"],
                          graph_text=graph_text, input_text=input_text,
                          input_ref=input_ref, parent_run_id=parent_run_id)
    return graph, founding


# -- governed operation delegates ------------------------------------------

def dispatch_node(ledger: Ledger, graph: dict, run_id: str,
                  node_id: str) -> dict:
    return operations.dispatch(ledger, graph, run_id, node_id)


def record_return(ledger: Ledger, graph: dict, run_id: str, node_id: str,
                  attempt: int, exit_code: int, output_evidence=None) -> dict:
    return operations.record_return(ledger, graph, run_id, node_id, attempt,
                                    exit_code, output_evidence)


def request_interrupt(ledger: Ledger, graph: dict, run_id: str) -> dict:
    return operations.request_interrupt(ledger, graph, run_id)


def cancel_verification(ledger: Ledger, graph: dict, run_id: str,
                        node_id: str, verification_id: str) -> dict:
    return operations.cancel_verification(ledger, graph, run_id, node_id,
                                          verification_id)


def land_run(ledger: Ledger, graph: dict, run_id: str, reason: str) -> dict:
    return operations.land_run(ledger, graph, run_id, reason)


def extend_budget(ledger: Ledger, graph: dict, run_id: str, new_budget,
                  actor: str) -> dict:
    return operations.extend_budget(ledger, graph, run_id, new_budget, actor)


def ready_nodes(graph: dict, ledger: Ledger, run_id: str) -> list[tuple]:
    # Planning must not grant authority to a missing/damaged run. Completed
    # runs are valid reads and simply have no ready work.
    folded, _ = operations._guard(ledger, graph, run_id, allow_completed=True)
    return [(nid, (i["attempt"] or 0) + 1)
            for nid, i in folded["nodes"].items() if i["state"] == "ready"]


# -- verification advancement (machines first, human last) -----------------

def advance_verifications(ledger: Ledger, graph: dict, run_id: str) -> list[dict]:
    emitted = []
    folded = fold(graph, ledger.run(run_id), run_id)
    for node_id, info in folded["nodes"].items():
        if info["state"] not in ("executed", "verifying"):
            continue
        revents = ledger.run(run_id)
        evidence_id = operations._evidence_id_of(revents, node_id,
                                                 info["attempt"])
        if evidence_id is None:
            continue
        due = operations.next_due(graph, node_id, info["attempt"],
                                  evidence_id, revents)
        if due is None:
            continue
        if due[0] == "escalate":
            emitted.append(operations.escalate(ledger, graph, run_id, node_id))
        else:  # "request" | "refire"
            emitted.append(operations.request_verification(
                ledger, graph, run_id, node_id, due[1]))
    return emitted


# -- orphans (abrupt loss; observation only — ADR-0005) --------------------

def observe_orphans(ledger: Ledger, graph: dict, run_id: str,
                    still_in_progress) -> list[dict]:
    """Produce orphan evidence AT OBSERVATION for work whose non-continuity
    the injected provider constates (§10; per-transport liveness stays open,
    §13.4/Phase 8). Human verifications are never orphaned (I9)."""
    if still_in_progress is None:
        return []
    from dagwell import verification as vf
    from dagwell.operations import _base
    emitted = []
    folded = fold(graph, ledger.run(run_id), run_id)
    for node_id, info in folded["nodes"].items():
        if info["state"] == "running":
            k = info["attempt"]
            if not still_in_progress({"kind": "attempt", "node_id": node_id,
                                      "attempt": k}):
                emitted.append(ledger.append(_base(
                    run_id, "orphan_detected", node_id=node_id, attempt=k)))
    revents = ledger.run(run_id)
    outcomes = [e for e in revents if e.get("event_type") == "verdict_recorded"]
    for req in revents:
        if (req.get("event_type") != "verification_requested"
                or req.get("family") == "human"):
            continue
        closed = any(o.get("node_id") == req["node_id"]
                     and o.get("attempt") == req["attempt"]
                     and o.get("verification_id") == req["verification_id"]
                     and o.get("verification_attempt")
                     == req["verification_attempt"]
                     for o in outcomes)
        if closed:
            continue
        if not still_in_progress({"kind": "verification",
                                  "node_id": req["node_id"],
                                  "attempt": req["attempt"],
                                  "verification_id": req["verification_id"],
                                  "verification_attempt":
                                      req["verification_attempt"]}):
            emitted.append(ledger.append(vf.verdict_recorded_event(
                run_id=run_id, node_id=req["node_id"],
                attempt=req["attempt"],
                verification_id=req["verification_id"],
                verification_attempt=req["verification_attempt"],
                family=req["family"], actor="runtime",
                verification_status="error", verdict=None,
                reason="orphaned", evidence_id=req["evidence_id"])))
    return emitted


# -- resume (§8): the SAME run --------------------------------------------

def resume(ledger: Ledger, graph_text, input_text, run_id: str,
           still_in_progress=None) -> dict:
    """Resume the same run, validating the frozen identity against
    run_created (I11/I25). graph_text=None loads the frozen snapshot (I24)
    from the private data area — the run always resumes against ITS graph."""
    revents = ledger.run(run_id)
    if not revents:
        raise ResumeRefused(f"unknown run: {run_id}")
    if ledger.sequence_gaps().get(run_id):
        raise ResumeRefused(
            "unresolved seq gap — resume is a mutable action and is blocked "
            "until explicit reconciliation (I27, §13.16)")

    founders = sorted((e for e in revents
                       if e.get("event_type") == "run_created"),
                      key=lambda e: e["seq"])
    if not founders:
        raise ResumeRefused("no authoritative run_created — identity not "
                            "validatable; run is read-only diagnostic (§2)")
    frozen_gv = founders[0].get("graph_version")
    frozen_ih = founders[0].get("input_hash")

    if graph_text is None:
        try:
            graph_text = snapshots.load(_snapshot_dir(ledger), frozen_gv)
        except snapshots.SnapshotIntegrityError as exc:
            raise ResumeRefused(f"frozen snapshot unavailable/corrupt (I24): "
                                f"{exc}") from exc
    if canonical.graph_version(graph_text) != frozen_gv:
        raise ResumeRefused(
            "frozen identity mismatch (I11): graph_version differs from "
            "run_created — create a CHILD run with parent_run_id=" + run_id)
    if canonical.input_hash(input_text) != frozen_ih:
        raise ResumeRefused(
            "frozen identity mismatch (I11): input_hash differs from "
            "run_created — create a CHILD run with parent_run_id=" + run_id)

    graph = load_graph(graph_text)
    folded = fold(graph, revents, run_id)
    if folded["run_state"] == "cancelled":
        raise ResumeRefused("run is cancelled (absorbing) — create a child run")
    if folded["run_state"] == "landed":
        raise ResumeRefused(
            "run is landed — the human action that removes the motive "
            "(budget_extended / human_retry) must precede resume (§3)")

    observe_orphans(ledger, graph, run_id, still_in_progress)
    if folded["run_state"] != "completed":
        advance_verifications(ledger, graph, run_id)
    folded = fold(graph, ledger.run(run_id), run_id)
    return {
        "state": folded,
        "ready": [(nid, (i["attempt"] or 0) + 1)
                  for nid, i in folded["nodes"].items()
                  if i["state"] == "ready"],
    }
