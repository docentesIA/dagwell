"""Checkpoint = the completed-set derived by the fold. The materialized file
is CACHE with a watermark — never a source of truth: on any divergence the
ledger wins and the cache is recomputed (contract §7, I19).
"""

import json
from pathlib import Path

from dagwell.fold import fold


def derive(folded: dict) -> dict:
    identity = folded.get("identity") or {}
    return {
        "run_id": folded["run_id"],
        "graph_version": identity.get("graph_version"),
        "input_hash": identity.get("input_hash"),
        "watermark": folded.get("_watermark"),
        "completed": folded["checkpoint"],
    }


def load_or_recompute(cache_path, ledger, graph, run_id: str) -> dict:
    """Return the checkpoint, trusting the cache only when its identity and
    watermark exactly match the ledger. Anything else → recompute + rewrite."""
    cache_path = Path(cache_path)
    revents = ledger.run(run_id)
    watermark = max((e["seq"] for e in revents), default=0)

    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            cache = None
        if cache is not None:
            folded_identity_ok = cache.get("run_id") == run_id
            if (folded_identity_ok and cache.get("watermark") == watermark
                    and cache.get("graph_version") == graph.get("graph_version")):
                return cache

    folded = fold(graph, revents, run_id)
    folded["_watermark"] = watermark
    cache = derive(folded)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    return cache
