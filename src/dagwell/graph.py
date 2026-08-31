"""Graph declarations and fail-closed validation (contract I5, I16, I28).

The graph definition is DATA, addressed by content digest (graph_version,
scheme c1). Representation here is JSON via stdlib — a Phase 4 implementation
detail; the identity function applies to the text, and the definitive
multi-file file-set rule remains deferred (ADR-0003 §D). No includes,
templates or preprocessing exist — none are invented.

Declaration rules enforced before real execution (the --go validation home):
- every node declares its obligatory verification set; an empty set is legal
  only through an explicit `no_verification: <reason>` (I5);
- every verification declares a form-valid family; two consecutive
  verifications of the same family require `r1_exception: <reason>` (I16);
- every node declares its output_evidence type (I28);
- node ids unique; deps must exist; the graph must be acyclic.
"""

import json

from dagwell import canonical
from dagwell.evidence import EVIDENCE_TYPES
from dagwell.ledger.events import valid_family


class GraphValidationError(Exception):
    pass


# Ordered difficulty tiers (Adapter/Output Evidence Spec v1.0 §3.3). Order
# matters to operators reading a registry; selection matches tier membership,
# never "at least this tier" — an upgrade must be declared, not inferred.
CAPABILITY_TIERS = ("trivial", "simple", "standard", "complex", "frontier")


def load_graph(text: bytes | str) -> dict:
    """Parse + validate + freeze identity. Fail closed on any violation.

    The parser reads the CANONICAL c1 form — the same text the digest
    addresses and the same text the frozen snapshot stores (I24). Parsing the
    raw form instead would let one `graph_version` yield two different parsed
    graphs: NFC normalization can merge distinct code-point sequences, so a
    node id decomposed in the raw file and composed in the snapshot would be
    two different ids for one identity. Canonicalize first, then parse.
    """
    try:
        canonical_text = canonical.canonicalize_text(text)
    except UnicodeDecodeError as exc:
        raise GraphValidationError(
            f"graph definition is not valid UTF-8: {exc}") from exc
    try:
        data = json.loads(canonical_text)
    except json.JSONDecodeError as exc:
        raise GraphValidationError(f"graph definition is not valid JSON: {exc}") from exc
    validate_graph(data)
    return {
        "graph_id": data["graph_id"],
        "graph_version": canonical.graph_version(canonical_text),
        "nodes": {n["id"]: n for n in data["nodes"]},
        "order": [n["id"] for n in data["nodes"]],
    }


def validate_graph(data) -> None:
    if not isinstance(data, dict):
        raise GraphValidationError("graph definition must be an object")
    gid = data.get("graph_id")
    if not isinstance(gid, str) or not gid:
        raise GraphValidationError("graph_id is required")
    nodes = data.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise GraphValidationError("nodes must be a non-empty list")

    ids_seen = set()
    for node in nodes:
        if not isinstance(node, dict):
            raise GraphValidationError("every node must be an object")
        nid = node.get("id")
        if not isinstance(nid, str) or not nid:
            raise GraphValidationError("every node requires a non-empty id")
        if nid in ids_seen:
            raise GraphValidationError(f"duplicate node id: {nid}")
        ids_seen.add(nid)
        _validate_node(node)

    by_id = {n["id"]: n for n in nodes}
    for node in nodes:
        for dep in node.get("deps", []):
            if dep not in by_id:
                raise GraphValidationError(
                    f"node {node['id']}: unknown dependency {dep!r}")
            if dep == node["id"]:
                raise GraphValidationError(f"node {node['id']}: depends on itself")
    _check_acyclic(by_id)


def _validate_node(node: dict) -> None:
    nid = node["id"]
    deps = node.get("deps", [])
    if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
        raise GraphValidationError(f"node {nid}: deps must be a list of node ids")

    # Spec §3.1 — one identity model per node: either the node pins its
    # executor by identity (x_command) or it delegates resolution to the
    # binding registry (capability_requirements). Both at once would make the
    # graph hash claim one identity while the registry resolves another.
    caps = node.get("capability_requirements")
    if caps is not None:
        if "x_command" in node:
            raise GraphValidationError(
                f"node {nid}: capability_requirements and x_command are "
                "mutually exclusive — one identity model per node (spec §3.1)")
        if not isinstance(caps, dict):
            raise GraphValidationError(
                f"node {nid}: capability_requirements must be an object")
        tier = caps.get("tier")
        if tier not in CAPABILITY_TIERS:
            raise GraphValidationError(
                f"node {nid}: capability_requirements.tier must be one of "
                f"{list(CAPABILITY_TIERS)}, got {tier!r}")
        mission = node.get("mission")
        if not isinstance(mission, str) or not mission:
            raise GraphValidationError(
                f"node {nid}: capability_requirements requires a non-empty "
                "mission — the registry resolves who runs, the node still "
                "says what (spec §3.1)")

    # I28 — output evidence declaration is mandatory.
    evidence_type = node.get("output_evidence")
    if evidence_type not in EVIDENCE_TYPES:
        raise GraphValidationError(
            f"node {nid}: output_evidence must be declared as one of "
            f"{sorted(EVIDENCE_TYPES)} (omission is a hard error, I28)")

    # I5 — verification set declared, or explicit signed vacuum.
    has_no_verification = "no_verification" in node
    verifications = node.get("verifications")
    if has_no_verification:
        reason = node["no_verification"]
        if not isinstance(reason, str) or not reason:
            raise GraphValidationError(
                f"node {nid}: no_verification requires a non-empty reason")
        if verifications:
            raise GraphValidationError(
                f"node {nid}: no_verification and non-empty verifications "
                "are mutually exclusive")
        # ADR-0008 restricts no_verification to types the core can validate on
        # its own. The Adapter/Output Evidence Spec v1.0 (promoted) now fixes
        # every type's FORM — but form-validity is not effect-validity: a
        # receipt that parses still proves nothing about the world without a
        # verifier looking at it. Per spec §4.6 the restriction stands until a
        # new ADR lifts it explicitly — never silently here.
        if evidence_type != "artifact":
            raise GraphValidationError(
                f"node {nid}: no_verification is not available for evidence "
                f"type {evidence_type!r} while §13.17 is open — the core cannot "
                "validate that type on its own, so an unverified node would "
                "complete on an unchecked claim. Declare a verification "
                "(I5, I28, §4 fail-closed)")
        return
    if not isinstance(verifications, list) or not verifications:
        raise GraphValidationError(
            f"node {nid}: declare verifications or an explicit "
            "no_verification: <reason> (I5)")

    vids = set()
    prev_family = None
    for v in verifications:
        if not isinstance(v, dict):
            raise GraphValidationError(f"node {nid}: verifications must be objects")
        vid = v.get("verification_id")
        if not isinstance(vid, str) or not vid:
            raise GraphValidationError(
                f"node {nid}: every verification requires a verification_id")
        if vid in vids:
            raise GraphValidationError(
                f"node {nid}: duplicate verification_id {vid}")
        vids.add(vid)
        family = v.get("family")
        if not valid_family(family):
            raise GraphValidationError(
                f"node {nid}: verification {vid}: invalid family {family!r}")
        if family == prev_family:
            r1 = v.get("r1_exception")
            if not isinstance(r1, str) or not r1:
                raise GraphValidationError(
                    f"node {nid}: consecutive verifications of family "
                    f"{family!r} require r1_exception: <reason> (I16)")
        prev_family = family


def _check_acyclic(by_id: dict) -> None:
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in by_id}

    def visit(nid, stack):
        color[nid] = GRAY
        for dep in by_id[nid].get("deps", []):
            if color[dep] == GRAY:
                raise GraphValidationError(
                    f"dependency cycle involving {dep!r}")
            if color[dep] == WHITE:
                visit(dep, stack + [dep])
        color[nid] = BLACK

    for nid in by_id:
        if color[nid] == WHITE:
            visit(nid, [nid])


def declared_verifications(graph: dict, node_id: str) -> list[dict]:
    return graph["nodes"][node_id].get("verifications") or []


def declared_evidence_type(graph: dict, node_id: str) -> str:
    return graph["nodes"][node_id]["output_evidence"]


def has_declared_vacuum(graph: dict, node_id: str) -> bool:
    return "no_verification" in graph["nodes"][node_id]
