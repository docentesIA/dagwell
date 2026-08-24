"""Per-run, per-attempt artifact layout (contract §1, I18).

    runs/<operation>/<run_id>/<node_id>/t<k>/

inside the PRIVATE data area — never a repository root, never the V1 layout
`runs/<operacao>/<no>/`, which two runs would overwrite. Append-only applies
to disk as well: a shared directory means one attempt erases another, and
erasure is exactly what the ledger's memory promise forbids. Distinct runs
and distinct attempts get distinct directories by construction of the path.

Reading V1's legacy layout in place stays legal (history is never moved);
this module only decides where NEW output is born.
"""

from pathlib import Path

RUNS_DIR = "runs"


class ArtifactLayoutError(Exception):
    pass


def _component(value, label: str) -> str:
    """A path component is a name, never a route: graph ids and node ids are
    DATA and must not be able to steer writes out of the run's directory."""
    if not isinstance(value, str) or not value:
        raise ArtifactLayoutError(f"{label} must be a non-empty string")
    if value in (".", "..") or "/" in value or "\\" in value or "\0" in value:
        raise ArtifactLayoutError(f"unsafe {label} path component: {value!r}")
    return value


def attempt_dir(data_dir, *, operation: str, run_id: str, node_id: str,
                attempt: int, create: bool = False) -> Path:
    """Directory where the given producer attempt's artifacts are born."""
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise ArtifactLayoutError(
            f"attempt must be a positive integer, got {attempt!r}")
    path = (Path(data_dir) / RUNS_DIR
            / _component(operation, "operation")
            / _component(run_id, "run_id")
            / _component(node_id, "node_id")
            / f"t{attempt}")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path
