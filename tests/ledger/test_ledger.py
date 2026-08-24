"""Ledger foundation: envelope, run_created, append-only, integrity. Zero-cost."""

import json
import tempfile
from pathlib import Path

from dagwell import ids
from dagwell.ledger import (
    FIRST_SEQ,
    EventValidationError,
    Ledger,
    LedgerIntegrityError,
    SCHEMA_VERSION,
    create_run,
    occurred_now,
    run_created_event,
)

GRAPH = "synthetic graph definition text\n"
AGENDA = "# synthetic agenda\ndo one thing\n"


def _tmp_ledger(tmp):
    return Ledger(Path(tmp) / "ledger.jsonl")


def _bare_event(run_id, event_type="run_cancelled", **extra):
    e = {
        "schema_version": SCHEMA_VERSION,
        "event_id": ids.new_event_id(),
        "run_id": run_id,
        "event_type": event_type,
        "occurred_at": occurred_now(),
    }
    e.update(extra)
    return e


def _expect(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    raise AssertionError(f"expected {exc_type.__name__}")


def test_create_run_appends_founding_event():
    with tempfile.TemporaryDirectory() as tmp:
        led = _tmp_ledger(tmp)
        e = create_run(led, graph_id="pesquisa", graph_text=GRAPH,
                       input_text=AGENDA, input_ref="synthetic://agenda")
        assert e["seq"] == FIRST_SEQ
        assert e["event_type"] == "run_created"
        assert e["graph_version"].startswith("sha256:")
        assert e["input_hash"].startswith("sha256:")
        assert e["parent_run_id"] is None
        assert led.run(e["run_id"]) == [e]


def test_second_run_created_refused():
    with tempfile.TemporaryDirectory() as tmp:
        led = _tmp_ledger(tmp)
        e = create_run(led, graph_id="g", graph_text=GRAPH,
                       input_text=AGENDA, input_ref="synthetic://a")
        dup = run_created_event(graph_id="g", graph_version=e["graph_version"],
                                input_hash=e["input_hash"], input_ref="synthetic://a",
                                run_id=e["run_id"])
        _expect(LedgerIntegrityError, led.append, dup)


def test_first_event_must_be_run_created():
    with tempfile.TemporaryDirectory() as tmp:
        led = _tmp_ledger(tmp)
        _expect(EventValidationError, led.append, _bare_event(ids.new_run_id()))


def test_run_id_required_everywhere():
    with tempfile.TemporaryDirectory() as tmp:
        led = _tmp_ledger(tmp)
        bad = _bare_event("x")
        del bad["run_id"]
        _expect(EventValidationError, led.append, bad)


def test_non_canonical_event_type_refused():
    with tempfile.TemporaryDirectory() as tmp:
        led = _tmp_ledger(tmp)
        e = create_run(led, graph_id="g", graph_text=GRAPH,
                       input_text=AGENDA, input_ref="synthetic://a")
        # Portuguese identifier must never enter the ledger (H1)
        _expect(EventValidationError, led.append,
                _bare_event(e["run_id"], event_type="execucao_cancelada"))


def test_duplicate_event_id_refused_at_write():
    with tempfile.TemporaryDirectory() as tmp:
        led = _tmp_ledger(tmp)
        e = create_run(led, graph_id="g", graph_text=GRAPH,
                       input_text=AGENDA, input_ref="synthetic://a")
        clash = _bare_event(e["run_id"])
        clash["event_id"] = e["event_id"]
        _expect(LedgerIntegrityError, led.append, clash)


def test_caller_seq_collision_regression_and_gap_refused_at_write():
    with tempfile.TemporaryDirectory() as tmp:
        led = _tmp_ledger(tmp)
        e = create_run(led, graph_id="g", graph_text=GRAPH,
                       input_text=AGENDA, input_ref="synthetic://a")
        for bad_seq in (1, 0, 3):  # collision, regression, would-be gap
            _expect(LedgerIntegrityError, led.append,
                    _bare_event(e["run_id"], seq=bad_seq))
        ok = led.append(_bare_event(e["run_id"], seq=2))
        assert ok["seq"] == 2


def test_two_runs_have_independent_seq():
    with tempfile.TemporaryDirectory() as tmp:
        led = _tmp_ledger(tmp)
        a = create_run(led, graph_id="g", graph_text=GRAPH,
                       input_text=AGENDA, input_ref="synthetic://a")
        b = create_run(led, graph_id="g", graph_text=GRAPH,
                       input_text=AGENDA + "b\n", input_ref="synthetic://b")
        e2 = led.append(_bare_event(a["run_id"]))
        assert e2["seq"] == 2
        assert [x["seq"] for x in led.run(b["run_id"])] == [1]


def test_append_only_prior_bytes_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        led = _tmp_ledger(tmp)
        e = create_run(led, graph_id="g", graph_text=GRAPH,
                       input_text=AGENDA, input_ref="synthetic://a")
        before = led.path.read_bytes()
        led.append(_bare_event(e["run_id"]))
        after = led.path.read_bytes()
        assert after.startswith(before)


def test_gap_read_diagnostic_but_append_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        led = _tmp_ledger(tmp)
        e = create_run(led, graph_id="g", graph_text=GRAPH,
                       input_text=AGENDA, input_ref="synthetic://a")
        rogue = _bare_event(e["run_id"], seq=3)
        with open(led.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rogue) + "\n")
        assert len(led.events()) == 2                       # diagnostic read works
        assert led.sequence_gaps() == {e["run_id"]: [2]}    # detection
        _expect(LedgerIntegrityError, led.append, _bare_event(e["run_id"]))


def test_seq_collision_in_file_fails_read():
    with tempfile.TemporaryDirectory() as tmp:
        led = _tmp_ledger(tmp)
        e = create_run(led, graph_id="g", graph_text=GRAPH,
                       input_text=AGENDA, input_ref="synthetic://a")
        with open(led.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(_bare_event(e["run_id"], seq=1)) + "\n")
        _expect(LedgerIntegrityError, led.events)


def test_seq_regression_in_file_fails_read():
    with tempfile.TemporaryDirectory() as tmp:
        led = _tmp_ledger(tmp)
        e = create_run(led, graph_id="g", graph_text=GRAPH,
                       input_text=AGENDA, input_ref="synthetic://a")
        with open(led.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(_bare_event(e["run_id"], seq=3)) + "\n")
            f.write(json.dumps(_bare_event(e["run_id"], seq=2)) + "\n")
        _expect(LedgerIntegrityError, led.events)


def test_malformed_line_fails_read():
    with tempfile.TemporaryDirectory() as tmp:
        led = _tmp_ledger(tmp)
        create_run(led, graph_id="g", graph_text=GRAPH,
                   input_text=AGENDA, input_ref="synthetic://a")
        with open(led.path, "a", encoding="utf-8") as f:
            f.write("{not json\n")
        _expect(LedgerIntegrityError, led.events)


def test_identity_is_content_not_path():
    with tempfile.TemporaryDirectory() as tmp:
        led = _tmp_ledger(tmp)
        a = create_run(led, graph_id="g", graph_text=GRAPH,
                       input_text=AGENDA, input_ref="/anywhere/a.md")
        b = create_run(led, graph_id="g", graph_text=GRAPH,
                       input_text=AGENDA, input_ref="/elsewhere/b.md")
        assert a["input_hash"] == b["input_hash"]        # same content, same identity
        assert a["input_ref"] != b["input_ref"]          # provenance differs
        assert a["run_id"] != b["run_id"]                # runs are distinct


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(vars(sys.modules["__main__"]).items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"test_ledger: {len(fns)} tests PASS")
