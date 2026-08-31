"""The capability worker — the loop that binds the engine to real CLIs.

For every READY node that declares capability_requirements:
probe -> select (difficulty dictates the model) -> dispatch (with transport
facts) -> execute over the subprocess transport -> return with the evidence
DERIVED from what actually landed on disk. Verification execution stays
outside: it is a declared open area ("automatic verification execution" is
not yet), so the worker reports what became due and stops there — opening
is not deciding, and deciding is not its verb at all.

Two modes, one boundary:
- plan (default): pure read + zero-cost probes. No event is written, no
  attempt directory is created, nothing is spent.
- go: the spending surface. Each processed node is a real dispatch of the
  operator's quota — which is exactly why the flag exists (§1 of the
  contract: a run advances only on explicit real execution).

Nodes pinned by x_command are the external runner's business
(examples/runner.sh) and are skipped here, loudly.
"""

import hashlib
import os

from dagwell import operations, runtime
from dagwell.artifacts import attempt_dir
from dagwell.canonical import json_digest
from dagwell.adapters.selection import SelectionError, select
from dagwell.adapters.transports import subprocess_transport as st

OUT_NAME = "out"


def _plan_node(node: dict, registry: dict, available: set) -> dict:
    caps = node.get("capability_requirements")
    if caps is None:
        return {"node_id": node["id"], "action": "skipped",
                "reason": "no capability_requirements (x_command nodes "
                          "belong to an external runner)"}
    if node["output_evidence"] != "artifact":
        return {"node_id": node["id"], "action": "refused",
                "reason": f"worker v1 collects artifact evidence only — "
                          f"{node['output_evidence']!r} needs its own "
                          "collection, not a pretend one"}
    try:
        chosen = select(caps["tier"], registry, available)
    except SelectionError as exc:
        return {"node_id": node["id"], "action": "refused", "reason": str(exc)}
    return {"node_id": node["id"], "action": "dispatch",
            "tier": caps["tier"], "selection": chosen}


def plan(graph: dict, ledger, run_id: str, registry: dict, *, env=None) -> list[dict]:
    """What `go` would do, spending nothing and writing nothing."""
    env = dict(env if env is not None else os.environ)
    available = {bid for bid, b in registry["bindings"].items()
                 if st.probe(b, env=env)}
    plans = []
    for nid, attempt in runtime.ready_nodes(graph, ledger, run_id):
        p = _plan_node(graph["nodes"][nid], registry, available)
        p["attempt"] = attempt
        plans.append(p)
    return plans


def _artifact_evidence_from_disk(adir, out_name: str):
    path = adir / out_name
    if not path.is_file() or path.stat().st_size == 0:
        return None                      # honest failure: no usable output
    digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = [{"path": out_name, "artifact_digest": digest,
                 "size_bytes": path.stat().st_size}]
    return {"type": "artifact", "evidence_id": json_digest(manifest),
            "output_manifest": manifest}


def work(ledger, graph: dict, run_id: str, registry: dict, data_dir, *,
         operation: str | None = None, node_id: str | None = None,
         env=None, go: bool = False) -> list[dict]:
    """Process READY capability nodes. go=False plans; go=True SPENDS."""
    env = dict(env if env is not None else os.environ)
    operation = operation or graph["graph_id"]
    if node_id is not None:
        ready = [(n, a) for n, a in runtime.ready_nodes(graph, ledger, run_id)
                 if n == node_id]
        if not ready:
            return [{"node_id": node_id, "action": "refused",
                     "reason": "node is not in the ready derived state"}]
    else:
        ready = runtime.ready_nodes(graph, ledger, run_id)

    available = {bid for bid, b in registry["bindings"].items()
                 if st.probe(b, env=env)}
    results = []
    for nid, attempt in ready:
        node = graph["nodes"][nid]
        p = _plan_node(node, registry, available)
        p["attempt"] = attempt
        if p["action"] != "dispatch" or not go:
            results.append(p)
            continue

        chosen = p["selection"]
        binding = registry["bindings"][chosen["binding_id"]]
        adir = attempt_dir(data_dir, operation=operation, run_id=run_id,
                           node_id=nid, attempt=attempt, create=True)
        out_path = str(adir / OUT_NAME)
        # The node's mission may reference $OUT; the child also receives OUT
        # in its environment. Substitute the concrete path so agents that
        # read the mission as plain text (claude -p) see it too.
        mission = node["mission"].replace("$OUT", out_path)

        operations.dispatch(ledger, graph, run_id, nid, transport=chosen)
        facts = st.execute(binding, mission, out_path, env=env)
        evidence = _artifact_evidence_from_disk(adir, OUT_NAME)
        operations.record_return(
            ledger, graph, run_id, nid, attempt=attempt,
            exit_code=facts["exit_code"] if facts["exit_code"] is not None
            else 1,
            output_evidence=evidence,
            transport={"duration_seconds": facts["duration_seconds"],
                       "timed_out": facts["timed_out"]})
        p["action"] = "executed" if evidence else "failed"
        p["exit_code"] = facts["exit_code"]
        p["evidence_id"] = evidence["evidence_id"] if evidence else None
        p["attempt_dir"] = str(adir)
        results.append(p)
    return results
