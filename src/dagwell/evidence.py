"""Output evidence (contract §4, P4/P5).

Frozen conceptual types only. evidence_id is the canonical generic identity
(P5) and is treated as an opaque, stable, non-empty string: per-type
encoding/canonicalization belongs to the future Adapter/Output Evidence
Specification (§13.17) and is deliberately NOT invented here. The artifact
type keeps its specialized realization: non-empty output_manifest with
artifact_digest per entry.
"""

EVIDENCE_TYPES = frozenset({
    "artifact", "structured_value", "remote_receipt", "side_effect_receipt",
})


class EvidenceValidationError(Exception):
    pass


def validate_output_evidence(payload, declared_type: str) -> None:
    """Fail-closed shape validation of a node's returned output evidence."""
    if declared_type not in EVIDENCE_TYPES:
        raise EvidenceValidationError(f"unknown declared evidence type: {declared_type!r}")
    if not isinstance(payload, dict):
        raise EvidenceValidationError("output_evidence must be an object")
    if payload.get("type") != declared_type:
        raise EvidenceValidationError(
            f"evidence type {payload.get('type')!r} does not match the node's "
            f"declaration {declared_type!r}")
    eid = payload.get("evidence_id")
    if not isinstance(eid, str) or not eid:
        raise EvidenceValidationError("evidence_id is required (P5)")
    if declared_type == "artifact":
        manifest = payload.get("output_manifest")
        if not isinstance(manifest, list) or not manifest:
            raise EvidenceValidationError(
                "artifact evidence requires a non-empty output_manifest")
        for entry in manifest:
            if not isinstance(entry, dict):
                raise EvidenceValidationError("output_manifest entries must be objects")
            for field in ("name", "artifact_digest"):
                if not isinstance(entry.get(field), str) or not entry[field]:
                    raise EvidenceValidationError(
                        f"output_manifest entry requires non-empty {field}")
    # Other types: only type + evidence_id are contract-fixed; concrete
    # receipt/value formats belong to §13.17 — nothing else is imposed.


def evidence_is_valid(payload, declared_type: str) -> bool:
    try:
        validate_output_evidence(payload, declared_type)
        return True
    except EvidenceValidationError:
        return False
