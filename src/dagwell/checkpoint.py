"""Operational checkpoint (contract §7, I19) — fail-closed, non-authoritative
cache.

The checkpoint is ALWAYS recomputed from the fold (the simplest correct
implementation; a proof-preserving cache design may replace this later). The
materialized cache file is write-through advisory output only: it is NEVER
read to answer an operational question, so tampering with it can never affect
the returned checkpoint — the ledger/fold always wins.

Fail-closed refusals:
- unresolved seq gap or missing authoritative run_created (integrity
  degraded) → no operational checkpoint (P3/I27);
- frozen graph mismatch (graph_version / graph_id vs run_created) → refused
  by the fold itself (I24);
- identity (run_id, graph_version, input_hash) is recorded in the cache for
  audit, not for trust.
"""

import json
from pathlib import Path

from dagwell.fold import fold


class CheckpointRefused(Exception):
    pass


def operational_checkpoint(cache_path, ledger, graph, run_id: str) -> dict:
    revents = ledger.run(run_id)
    folded = fold(graph, revents, run_id)   # refuses on frozen-graph mismatch
    if folded["integrity"] == "degraded":
        raise CheckpointRefused(
            "integrity degraded (seq gap or missing run_created) — no "
            "operational checkpoint may be materialized (P3/I27)")
    identity = folded["identity"]
    cp = {
        "run_id": run_id,
        "graph_id": identity.get("graph_id"),
        "graph_version": identity.get("graph_version"),
        "input_hash": identity.get("input_hash"),
        "watermark": max((e["seq"] for e in revents), default=0),
        "completed": folded["checkpoint"],
    }
    if cache_path is not None:
        Path(cache_path).write_text(
            json.dumps(cp, ensure_ascii=False) + "\n", encoding="utf-8")
    return cp


# Backward-compatible name: semantics are now always-recompute + write-through.
load_or_recompute = operational_checkpoint
