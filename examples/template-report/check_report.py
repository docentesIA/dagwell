#!/usr/bin/env python3
"""Verifier: the report at $OUT states the facts the dataset supports."""
import json, os, re, sys

text = open(os.environ["OUT"], encoding="utf-8").read()
facts = dict(re.findall(r"^(rows|mean|min|max): ([0-9.]+)$", text, re.M))
reasons, ok = [], True
if set(facts) != {"rows", "mean", "min", "max"}:
    ok, reasons = False, reasons + [f"missing facts: {sorted({'rows','mean','min','max'} - set(facts))}"]
else:
    if facts["rows"] != "100":
        ok, reasons = False, reasons + [f"rows {facts['rows']} != 100"]
    if not 10.0 <= float(facts["min"]) <= float(facts["mean"]) <= float(facts["max"]) <= 20.0:
        ok, reasons = False, reasons + ["min <= mean <= max within [10, 20] violated"]
if not text.startswith("# Synthetic report"):
    ok, reasons = False, reasons + ["title line missing"]
print(json.dumps({"verdict": "approved" if ok else "rejected",
                  "reasons": reasons or ["title, 100 rows, min<=mean<=max in range"]}))
