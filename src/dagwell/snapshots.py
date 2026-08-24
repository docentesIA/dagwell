"""Frozen graph snapshot store (contract I24).

The digest freezes the identity; the snapshot freezes the CONTENT — without
it, "fold recomputable at any time" would be an empty promise. Snapshots live
in the PRIVATE DATA AREA (beside the run's ledger, never in the public
repository), addressed deterministically by graph_version. Stored content is
verified to reproduce its graph_version on every store and load (fail
closed).
"""

from pathlib import Path

from dagwell import canonical


class SnapshotIntegrityError(Exception):
    pass


def _path_for(data_dir, graph_version: str) -> Path:
    algo, _, hexdigest = graph_version.partition(":")
    if algo != "sha256" or len(hexdigest) != 64:
        raise SnapshotIntegrityError(f"malformed graph_version: {graph_version!r}")
    return Path(data_dir) / f"{hexdigest}.graph"


def store(data_dir, graph_text) -> Path:
    """Persist the canonical frozen snapshot; idempotent; verified."""
    text = canonical.canonicalize_text(graph_text)
    graph_version = canonical.content_digest(text)
    path = _path_for(data_dir, graph_version)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if canonical.content_digest(existing) != graph_version:
            raise SnapshotIntegrityError(
                f"snapshot {path.name} does not reproduce its graph_version")
        return path
    path.write_text(text, encoding="utf-8")
    if canonical.content_digest(path.read_text(encoding="utf-8")) != graph_version:
        raise SnapshotIntegrityError("stored snapshot failed round-trip verification")
    return path


def load(data_dir, graph_version: str) -> str:
    """Load and verify the frozen graph text for graph_version."""
    path = _path_for(data_dir, graph_version)
    if not path.is_file():
        raise SnapshotIntegrityError(
            f"no frozen snapshot for {graph_version} (I24 violated)")
    text = path.read_text(encoding="utf-8")
    if canonical.content_digest(text) != graph_version:
        raise SnapshotIntegrityError(
            f"snapshot for {graph_version} is corrupt (digest mismatch)")
    return text
