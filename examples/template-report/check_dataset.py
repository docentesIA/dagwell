#!/usr/bin/env python3
"""Verifier: the dataset at $OUT has the declared shape. Prints ONE JSON
object with the decision; exit 0 means "I decided", not "approved"."""
import csv, json, os, sys

reasons, ok = [], True
try:
    rows = list(csv.reader(open(os.environ["OUT"], newline="")))
except Exception as exc:                      # cannot read = cannot decide
    print(f"cannot read $OUT: {exc}", file=sys.stderr)
    sys.exit(2)
if not rows or rows[0] != ["id", "value"]:
    ok, reasons = False, reasons + ["header must be id,value"]
body = rows[1:]
if len(body) != 100:
    ok, reasons = False, reasons + [f"expected 100 rows, got {len(body)}"]
try:
    bad = [r for r in body if not 10.0 <= float(r[1]) <= 20.0]
    if bad:
        ok, reasons = False, reasons + [f"{len(bad)} values outside [10, 20]"]
except (ValueError, IndexError):
    ok, reasons = False, reasons + ["non-numeric value column"]
print(json.dumps({"verdict": "approved" if ok else "rejected",
                  "reasons": reasons or [f"{len(body)} rows, header ok, values in range"]}))
