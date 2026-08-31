"""Content identity canonicalization — scheme c1 (ADR-0003, ACCEPTED).

c1: strict UTF-8, BOM stripped, line endings normalized to LF, Unicode NFC,
per-line trailing whitespace preserved, exactly one terminal LF; digest
SHA-256, represented as "sha256:<lowercase hex>". Event schema_version "1"
pins scheme c1 (ADR-0003, option H-a).

Filesystem paths never participate (contract §2, emenda H2): callers pass
content, never locations. Fail closed: undecodable input raises — there is no
silent fallback to raw-byte hashing.
"""

import hashlib
import unicodedata

SCHEME = "c1"


def canonicalize_text(data: bytes | str) -> str:
    if isinstance(data, bytes):
        data = data.decode("utf-8")  # strict: invalid bytes fail closed
    if data.startswith("\ufeff"):
        data = data[1:]
    data = data.replace("\r\n", "\n").replace("\r", "\n")
    data = unicodedata.normalize("NFC", data)
    return data.rstrip("\n") + "\n"


def content_digest(data: bytes | str) -> str:
    canonical = canonicalize_text(data)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def json_canonical(value) -> str:
    """Canonical JSON text of a value (Adapter/Output Evidence Spec §4.1).

    UTF-8, lexicographically ordered keys, no insignificant whitespace,
    minimal number form; NaN/Infinity refused (fail closed) — they have no
    JSON form and would otherwise serialize into unparseable text.
    """
    import json
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def json_digest(value) -> str:
    """sha256:<hex> of the canonical JSON bytes — the uniform evidence_id."""
    canonical = json_canonical(value)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def graph_version(graph_text: bytes | str) -> str:
    """Identity of one executable graph definition document.

    Phase 2 scope: a single document. The definitive multi-file file-set rule
    is deferred to the graph phase (ADR-0003 §D) — no includes/templates here.
    """
    return content_digest(graph_text)


def input_hash(input_text: bytes | str) -> str:
    """Identity of the effective input content (the path never participates)."""
    return content_digest(input_text)
