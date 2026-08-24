"""Graph declarations + output evidence fail-closed validation. Zero-cost."""

import json

from dagwell.evidence import EvidenceValidationError, validate_output_evidence
from dagwell.graph import GraphValidationError, load_graph

EVID = "sha256:" + "ab" * 32


def _g(**over):
    base = {
        "graph_id": "demo",
        "nodes": [
            {"id": "a", "deps": [], "output_evidence": "artifact",
             "verifications": [
                 {"verification_id": "lint", "family": "deterministic"},
                 {"verification_id": "gate", "family": "human"}]},
            {"id": "b", "deps": ["a"], "output_evidence": "structured_value",
             "no_verification": "read-only summary, checked downstream"},
        ],
    }
    base.update(over)
    return base


def _expect(exc_type, fn, *args):
    try:
        fn(*args)
    except exc_type:
        return
    raise AssertionError(f"expected {exc_type.__name__}")


def test_valid_graph_loads_with_frozen_identity():
    text = json.dumps(_g())
    g = load_graph(text)
    assert g["graph_id"] == "demo"
    assert g["graph_version"].startswith("sha256:")
    assert g["order"] == ["a", "b"]


def test_output_evidence_declaration_mandatory():
    bad = _g()
    del bad["nodes"][0]["output_evidence"]
    _expect(GraphValidationError, load_graph, json.dumps(bad))
    bad2 = _g()
    bad2["nodes"][0]["output_evidence"] = "filesystem"
    _expect(GraphValidationError, load_graph, json.dumps(bad2))


def test_verifications_xor_no_verification():
    neither = _g()
    del neither["nodes"][0]["verifications"]
    _expect(GraphValidationError, load_graph, json.dumps(neither))
    empty = _g()
    empty["nodes"][0]["verifications"] = []
    _expect(GraphValidationError, load_graph, json.dumps(empty))
    both = _g()
    both["nodes"][0]["no_verification"] = "reason"
    _expect(GraphValidationError, load_graph, json.dumps(both))
    empty_reason = _g()
    empty_reason["nodes"][1]["no_verification"] = ""
    _expect(GraphValidationError, load_graph, json.dumps(empty_reason))


def test_r1_consecutive_same_family():
    bad = _g()
    bad["nodes"][0]["verifications"] = [
        {"verification_id": "v1", "family": "deterministic"},
        {"verification_id": "v2", "family": "deterministic"}]
    _expect(GraphValidationError, load_graph, json.dumps(bad))
    ok = _g()
    ok["nodes"][0]["verifications"] = [
        {"verification_id": "v1", "family": "deterministic"},
        {"verification_id": "v2", "family": "deterministic",
         "r1_exception": "deliberate double deterministic gate"}]
    load_graph(json.dumps(ok))
    nonconsec = _g()
    nonconsec["nodes"][0]["verifications"] = [
        {"verification_id": "v1", "family": "deterministic"},
        {"verification_id": "v2", "family": "model:x"},
        {"verification_id": "v3", "family": "deterministic"}]
    load_graph(json.dumps(nonconsec))


def test_family_form_checked_in_graph():
    bad = _g()
    bad["nodes"][0]["verifications"][0]["family"] = "robot"
    _expect(GraphValidationError, load_graph, json.dumps(bad))


def test_structural_rules():
    dup = _g()
    dup["nodes"].append(dict(dup["nodes"][0]))
    _expect(GraphValidationError, load_graph, json.dumps(dup))
    unknown_dep = _g()
    unknown_dep["nodes"][1]["deps"] = ["zz"]
    _expect(GraphValidationError, load_graph, json.dumps(unknown_dep))
    cycle = _g()
    cycle["nodes"][0]["deps"] = ["b"]
    _expect(GraphValidationError, load_graph, json.dumps(cycle))
    dup_vid = _g()
    dup_vid["nodes"][0]["verifications"] = [
        {"verification_id": "v", "family": "deterministic"},
        {"verification_id": "v", "family": "human"}]
    _expect(GraphValidationError, load_graph, json.dumps(dup_vid))
    _expect(GraphValidationError, load_graph, "{not json")


def test_artifact_evidence_validation():
    ok = {"type": "artifact", "evidence_id": EVID,
          "output_manifest": [{"name": "out.md", "artifact_digest": EVID}]}
    validate_output_evidence(ok, "artifact")
    empty = {"type": "artifact", "evidence_id": EVID, "output_manifest": []}
    _expect(EvidenceValidationError, validate_output_evidence, empty, "artifact")
    no_digest = {"type": "artifact", "evidence_id": EVID,
                 "output_manifest": [{"name": "out.md"}]}
    _expect(EvidenceValidationError, validate_output_evidence, no_digest, "artifact")


def test_evidence_identity_and_type_binding():
    missing_id = {"type": "structured_value"}
    _expect(EvidenceValidationError, validate_output_evidence,
            missing_id, "structured_value")
    mismatch = {"type": "remote_receipt", "evidence_id": EVID}
    _expect(EvidenceValidationError, validate_output_evidence,
            mismatch, "structured_value")
    minimal = {"type": "side_effect_receipt", "evidence_id": "receipt-0001"}
    validate_output_evidence(minimal, "side_effect_receipt")


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(vars(sys.modules["__main__"]).items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"test_graph: {len(fns)} tests PASS")
