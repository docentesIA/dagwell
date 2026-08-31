"""Shared fixtures — tools/run_tests.py puts tests/ on PYTHONPATH.

Evidence payloads must carry the evidence_id DERIVED from their material
(Adapter/Output Evidence Spec v1.0 §4.1); hand-picked ids are refused at the
boundary. Build them here so every test speaks the promoted format.
"""

from dagwell.canonical import json_digest

FILE_DIGEST = "sha256:" + "ab" * 32


def artifact_manifest(path="o.md", digest=FILE_DIGEST, size_bytes=2):
    return [{"path": path, "artifact_digest": digest, "size_bytes": size_bytes}]


def artifact_evidence(path="o.md", digest=FILE_DIGEST, size_bytes=2):
    manifest = artifact_manifest(path, digest, size_bytes)
    return {"type": "artifact", "evidence_id": json_digest(manifest),
            "output_manifest": manifest}


EVID = artifact_evidence()["evidence_id"]
