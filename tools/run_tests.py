#!/usr/bin/env python3
"""Run the full zero-cost test suite (stdlib only, no quota, no network)."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    env = {**os.environ,
           "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(ROOT / "tests")])}
    files = sorted((ROOT / "tests").rglob("test_*.py"))
    failed = []
    for f in files:
        r = subprocess.run([sys.executable, str(f)], env=env)
        if r.returncode != 0:
            failed.append(f.relative_to(ROOT))
    if failed:
        print(f"suite: {len(files)} files, FAILED: {', '.join(map(str, failed))}")
        return 1
    print(f"suite: {len(files)} files, ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
