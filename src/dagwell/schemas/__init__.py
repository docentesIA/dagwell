"""Shipped schema documents (package data).

Schemas are a shape aid for editors and external tooling. The authoritative
validator is `dagwell.graph.validate_graph`: it enforces what a JSON Schema
cannot express (unique ids, existing deps, acyclicity, the R1 rule). Parity
between the two is locked by a test, so the schema can never drift into being
a second source of truth.
"""

import json
from pathlib import Path

_DIR = Path(__file__).resolve().parent

GRAPH_SCHEMA = "graph.schema.json"


def load(name: str = GRAPH_SCHEMA) -> dict:
    """Load a shipped schema document by file name."""
    path = _DIR / name
    if path.parent != _DIR or not path.is_file():
        raise FileNotFoundError(f"no such shipped schema: {name!r}")
    return json.loads(path.read_text(encoding="utf-8"))
