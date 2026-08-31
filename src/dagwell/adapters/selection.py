"""Deterministic model selection — difficulty dictates the model (spec §3.3).

A pure function of (required tier, loaded registry, availability): filter to
models serving the tier on an available binding, take the lowest
relative_cost, break ties by (binding_id, model_id). No candidate -> hard
refusal before spend — nothing silently upgrades or downgrades a tier. This
is the entire routing model: no memory, no scores, no adaptation (learned
routing stays a deferred layer, Migration Plan §14).
"""

from dagwell.graph import CAPABILITY_TIERS


class SelectionError(Exception):
    pass


def select(tier: str, registry: dict, available=None) -> dict:
    """Resolve a required tier to transport facts for node_dispatched.

    `available`: optional set of binding_ids that passed their zero-cost
    probe (spec §6.6); None means no probe filtering.
    """
    if tier not in CAPABILITY_TIERS:
        raise SelectionError(
            f"unknown tier {tier!r} ({list(CAPABILITY_TIERS)})")
    candidates = []
    for bid, binding in registry["bindings"].items():
        if available is not None and bid not in available:
            continue
        for model in binding["models"]:
            if tier in model["tiers"]:
                candidates.append((model["relative_cost"], bid,
                                   model["model_id"], binding, model))
    if not candidates:
        raise SelectionError(
            f"no available binding serves tier {tier!r} — refusing before "
            "spend (spec §3.3; declare a capable model or lower the tier)")
    cost, bid, mid, binding, model = min(candidates)
    return {
        "binding_id": bid,
        "model_id": mid,
        "family": model["family"],
        "transport": binding["transport"],
        "registry_digest": registry["registry_digest"],
    }
