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
import fcntl
import shutil
from contextlib import contextmanager
from pathlib import Path

from dagwell import operations, runtime
from dagwell.artifacts import attempt_dir
from dagwell.canonical import json_digest
from dagwell.fold import fold
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
    ready = runtime.ready_nodes(graph, ledger, run_id)
    if not ready:
        return []
    available = {bid for bid, b in registry["bindings"].items()
                 if st.probe(b, env=env)}
    plans = []
    for nid, attempt in ready:
        p = _plan_node(graph["nodes"][nid], registry, available)
        p["attempt"] = attempt
        plans.append(p)
    return plans


def _artifact_evidence_from_disk(adir, out_name: str):
    path = adir / out_name
    if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        return None                      # honest failure: no usable output
    data = path.read_bytes()
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    manifest = [{"path": out_name, "artifact_digest": digest,
                 "size_bytes": len(data)}]
    return {"type": "artifact", "evidence_id": json_digest(manifest),
            "output_manifest": manifest}


def work(ledger, graph: dict, run_id: str, registry: dict, data_dir, *,
         operation: str | None = None, node_id: str | None = None,
         env=None, go: bool = False) -> list[dict]:
    """Process READY capability nodes. go=False plans; go=True SPENDS."""
    # Validate before creating even a lock file. A separate pilot lock never
    # holds the ledger lock across subprocess execution: status stays readable.
    runtime.ready_nodes(graph, ledger, run_id)
    if not go:
        return _work(ledger, graph, run_id, registry, data_dir,
                     operation=operation, node_id=node_id, env=env, go=False)
    with _pilot_lock(ledger, run_id):
        return _work(ledger, graph, run_id, registry, data_dir,
                     operation=operation, node_id=node_id, env=env, go=True)


@contextmanager
def _pilot_lock(ledger, run_id):
    key = hashlib.sha256(run_id.encode('utf-8')).hexdigest()
    ledger_path = ledger.path.resolve()
    lock = ledger_path.with_name(f'.{ledger_path.name}.{key}.work.lock')
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise operations.OperationRefused('another worker owns this run') from exc
        yield
    finally:
        os.close(fd)
    # Retain the inode: unlinking a lock allows two independently locked files.


def _work(ledger, graph, run_id, registry, data_dir, *, operation=None,
          node_id=None, env=None, go=False):
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

    if not ready:
        return []

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
                           node_id=nid, attempt=attempt)
        # Resolve the data root, but never follow a run/attempt symlink into
        # another attempt. Reserve this directory exclusively; retain history
        # even if a later guard refuses the dispatch.
        root = Path(data_dir).resolve()
        adir = root / adir.relative_to(Path(data_dir))
        if adir.resolve() != adir:
            raise operations.OperationRefused('attempt path contains a symlink')
        executable = st.build_argv(binding['invocation'], node['mission'])[0]
        search_path = os.pathsep.join(
            str(Path(entry) if Path(entry).is_absolute() else adir / entry)
            for entry in env.get('PATH', os.defpath).split(os.pathsep))
        command = (str(adir / executable) if '/' in executable
                   and not Path(executable).is_absolute() else executable)
        if shutil.which(command, path=search_path) is None:
            p.update(action='refused', reason='executable is unavailable in attempt environment')
            results.append(p)
            continue
        adir.mkdir(parents=True, exist_ok=False)
        out_path = str(adir / OUT_NAME)
        # The node's mission may reference $OUT; the child also receives OUT
        # in its environment. Substitute the concrete path so agents that
        # read the mission as plain text (claude -p) see it too.
        mission = node["mission"].replace("$OUT", out_path)

        operations.dispatch(ledger, graph, run_id, nid, transport=chosen,
                            expected_attempt=attempt)
        facts = st.execute(binding, mission, out_path, env=env)
        evidence = _artifact_evidence_from_disk(adir, OUT_NAME)
        if facts.get('transport_error'):
            # A race after preflight can still prevent spawn. No child means
            # no exit status; preserve the dispatch for explicit observation
            # via resume instead of inventing a return or auto-orphan policy.
            raise operations.OperationRefused(
                f"spawn error ({facts['transport_error']['type']}); "
                f"node {nid} attempt {attempt} remains in flight; "
                "resume with an explicit liveness provider to observe it")
        else:
            operations.record_return(
                ledger, graph, run_id, nid, attempt=attempt,
                exit_code=facts["exit_code"], output_evidence=evidence,
                transport={"duration_seconds": facts["duration_seconds"],
                           "timed_out": facts["timed_out"]})
        p["action"] = fold(graph, ledger.run(run_id), run_id)['nodes'][nid]['state']
        p["exit_code"] = facts["exit_code"]
        p["evidence_id"] = evidence["evidence_id"] if evidence else None
        p["attempt_dir"] = str(adir)
        results.append(p)
    return results
