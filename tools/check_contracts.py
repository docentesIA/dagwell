#!/usr/bin/env python3
"""Verify promoted normative documents in docs/contracts/ against MANIFEST.sha256.

Only documents declared in the manifest are validated: files present under
docs/contracts/ but absent from the manifest are NOT promoted and are ignored
(reported informationally). Fails if the manifest is missing, empty, or
malformed, if a declared document is missing, or if any digest mismatches.
Zero-cost: stdlib only, no network, no inference.
"""

import hashlib
import sys
from pathlib import Path

CONTRACTS = Path(__file__).resolve().parent.parent / "docs" / "contracts"
MANIFEST = CONTRACTS / "MANIFEST.sha256"


def main() -> int:
    if not MANIFEST.is_file():
        print(f"FAIL: manifest not found: {MANIFEST}")
        return 1
    entries = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, name = line.partition("  ")
        if len(digest) != 64 or not name:
            print(f"FAIL: malformed manifest line: {line!r}")
            return 1
        entries.append((digest.lower(), name.strip()))
    if not entries:
        print("FAIL: manifest declares no promoted documents")
        return 1
    failed = False
    declared = set()
    for expected, name in entries:
        declared.add(name)
        path = CONTRACTS / name
        if not path.is_file():
            print(f"FAIL: declared document missing: {name}")
            failed = True
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        ok = actual == expected
        failed |= not ok
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
        print(f"  expected {expected}")
        print(f"  actual   {actual}")
    for path in sorted(CONTRACTS.iterdir()):
        if path.is_file() and path.name not in declared and path.name != MANIFEST.name:
            print(f"note: not promoted (ignored): {path.name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
