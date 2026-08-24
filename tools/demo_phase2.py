#!/usr/bin/env python3
"""Phase 2 end-to-end demonstration — ZERO COST, synthetic data only.

graph text + input text -> canonical identities -> run_id -> run_created ->
append to ledger -> read ledger -> founding event verified. This is NOT a
DAGWELL run: nothing is dispatched, nothing is spent.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dagwell.ledger import Ledger, create_run  # noqa: E402

GRAPH_TEXT = "synthetic graph definition text (the graph model itself is Phase 4 work)\n"
INPUT_TEXT = (
    "# Synthetic agenda (demo)\n"
    "One line of synthetic work. Same content anywhere yields the same input_hash.\n"
)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Ledger(Path(tmp) / "ledger.jsonl")
        event = create_run(
            ledger,
            graph_id="demo",
            graph_text=GRAPH_TEXT,
            input_text=INPUT_TEXT,
            input_ref="synthetic://demo-agenda",
        )
        (readback,) = ledger.run(event["run_id"])
        assert readback == event, "ledger read-back must equal the appended event"
        print("founding event (read back from the ledger):")
        print(json.dumps(readback, indent=2, ensure_ascii=False))
        print("\ndemo_phase2: PASS")


if __name__ == "__main__":
    main()
