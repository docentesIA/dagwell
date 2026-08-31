"""Output evidence (contract §4, P4/P5; Adapter/Output Evidence Spec v1.0 §4).

The Adapter/Output Evidence Specification v1.0 (promoted 2026-08-31) fixes the
concrete format of each evidence type and the uniform evidence_id encoding:
sha256 of the canonical JSON bytes of the type's material (the manifest, the
value, the receipt). Validation here is fail-closed and self-contained — it
recomputes the evidence_id from the payload's own material and refuses a
mismatch, so an id is always reproducible from stored bytes alone (spec §9.3).

What this module does NOT do: touch the filesystem. Whether a manifested file
actually exists with the declared digest is boundary work for whoever owns the
attempt directory (the adapter, spec §4.2) — the fold and the write path stay
pure.
"""

from dagwell import canonical

EVIDENCE_TYPES = frozenset({
    "artifact", "structured_value", "remote_receipt", "side_effect_receipt",
})

_DIGEST_FORM = "sha256:"


class EvidenceValidationError(Exception):
    pass


def _require_str(obj: dict, field: str, where: str) -> str:
    value = obj.get(field)
    if not isinstance(value, str) or not value:
        raise EvidenceValidationError(f"{where} requires non-empty {field}")
    return value


def _safe_relative_path(path: str) -> None:
    """A manifest path is relative to the attempt directory, never a route
    out of it (spec §4.2; same discipline as artifacts._component)."""
    if path.startswith("/") or "\\" in path or "\0" in path:
        raise EvidenceValidationError(f"unsafe manifest path: {path!r}")
    parts = path.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise EvidenceValidationError(f"unsafe manifest path: {path!r}")


def _validate_digest(value: str, where: str) -> None:
    if (not value.startswith(_DIGEST_FORM)
            or len(value) != len(_DIGEST_FORM) + 64
            or not all(c in "0123456789abcdef" for c in value[len(_DIGEST_FORM):])):
        raise EvidenceValidationError(
            f"{where}: digest must be sha256:<64 lowercase hex>, got {value!r}")


def _material(payload: dict, declared_type: str):
    """The per-type material the evidence_id is derived from (spec §4)."""
    if declared_type == "artifact":
        manifest = payload.get("output_manifest")
        if not isinstance(manifest, list) or not manifest:
            raise EvidenceValidationError(
                "artifact evidence requires a non-empty output_manifest")
        for entry in manifest:
            if not isinstance(entry, dict):
                raise EvidenceValidationError(
                    "output_manifest entries must be objects")
            _safe_relative_path(_require_str(entry, "path", "output_manifest entry"))
            _validate_digest(
                _require_str(entry, "artifact_digest", "output_manifest entry"),
                "output_manifest entry")
            size = entry.get("size_bytes")
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                raise EvidenceValidationError(
                    "output_manifest entry requires size_bytes >= 0")
        return manifest
    if declared_type == "structured_value":
        if "value" not in payload:
            raise EvidenceValidationError(
                "structured_value evidence requires a value")
        return payload["value"]
    if declared_type == "remote_receipt":
        receipt = payload.get("receipt")
        if not isinstance(receipt, dict):
            raise EvidenceValidationError(
                "remote_receipt evidence requires a receipt object")
        for field in ("issuer", "remote_id", "issued_at"):
            _require_str(receipt, field, "remote_receipt")
        return receipt
    if declared_type == "side_effect_receipt":
        receipt = payload.get("receipt")
        if not isinstance(receipt, dict):
            raise EvidenceValidationError(
                "side_effect_receipt evidence requires a receipt object")
        for field in ("effect_type", "proof"):
            _require_str(receipt, field, "side_effect_receipt")
        return receipt
    raise EvidenceValidationError(
        f"unknown declared evidence type: {declared_type!r}")


def derive_evidence_id(payload: dict, declared_type: str) -> str:
    """The canonical evidence_id of a payload's material (spec §4.1)."""
    try:
        return canonical.json_digest(_material(payload, declared_type))
    except (TypeError, ValueError) as exc:
        raise EvidenceValidationError(
            f"evidence material is not canonicalizable JSON: {exc}") from exc


def validate_output_evidence(payload, declared_type: str) -> None:
    """Fail-closed validation of a node's returned output evidence."""
    if declared_type not in EVIDENCE_TYPES:
        raise EvidenceValidationError(
            f"unknown declared evidence type: {declared_type!r}")
    if not isinstance(payload, dict):
        raise EvidenceValidationError("output_evidence must be an object")
    if payload.get("type") != declared_type:
        raise EvidenceValidationError(
            f"evidence type {payload.get('type')!r} does not match the node's "
            f"declaration {declared_type!r}")
    eid = payload.get("evidence_id")
    if not isinstance(eid, str) or not eid:
        raise EvidenceValidationError("evidence_id is required (P5)")
    derived = derive_evidence_id(payload, declared_type)
    if eid != derived:
        raise EvidenceValidationError(
            f"evidence_id {eid!r} does not match the id derived from the "
            f"evidence material ({derived!r}) — a claim is not an identity "
            "(spec §4.1, ADR-0008)")


def evidence_is_valid(payload, declared_type: str) -> bool:
    try:
        validate_output_evidence(payload, declared_type)
        return True
    except EvidenceValidationError:
        return False
