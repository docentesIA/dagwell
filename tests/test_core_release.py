"""Core release regressions: synthetic histories, no providers or quota."""

import tempfile

from dagwell import ids
from dagwell.fold import fold
from dagwell.ledger import events as ev
from helpers import artifact_evidence
from tests_scenario import S


def refuses(exc, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc:
        return
    raise AssertionError(f"expected {exc.__name__}")


def test_fold_refuses_sequence_regression_before_sorting():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        history = s.led.events()
        refuses(ev.LedgerIntegrityError, fold, s.graph,
                [history[0], history[2], history[1]], s.rid)


def test_closed_verification_outcomes_are_inert_and_signaled():
    for closed_status in ("error", "timeout", "cancelled"):
        with tempfile.TemporaryDirectory() as tmp:
            s = S(tmp)
            s.dispatch()
            s.ret()
            s.request()
            ended = s.verdict(status=closed_status, verdict=None)
            history = s.led.events()
            late = dict(ended, seq=ended["seq"] + 1,
                        event_id=ids.new_event_id(),
                        verification_status="completed", verdict="rejected")
            f = fold(s.graph, history + [late], s.rid)
            assert f["nodes"]["a"]["state"] == "verifying", f
            assert any("closed verification_attempt" in a for a in f["anomalies"])


def test_late_old_outcome_cannot_override_new_verification():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        s.request()
        ended = s.verdict(status="timeout", verdict=None)
        s.request(va=2)
        s.verdict(va=2)
        s.request("gate", "human")
        s.verdict("gate", "human")
        history = s.led.events()
        late = dict(ended, seq=history[-1]["seq"] + 1,
                    event_id=ids.new_event_id(),
                    verification_status="completed", verdict="rejected")
        f = fold(s.graph, history + [late], s.rid)
        assert f["nodes"]["a"]["state"] == "completed"
        assert any("closed verification_attempt" in a for a in f["anomalies"])


def test_producer_timeout_with_exit_zero_is_failed():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ev("node_returned", node_id="a", attempt=1, exit_code=0,
             output_evidence=artifact_evidence(), transport={"timed_out": True})
        assert s.fold()["nodes"]["a"]["state"] == "failed"
        assert s.fold()["checkpoint"] == []


def test_writer_refuses_noncanonical_run_ids_without_appending():
    valid = "0198c7a0-5f2e-7c3a-9f4e-2d6b8a1c0e55"
    invalid = ("", "../escape", "arbitrary", valid.upper(), valid.replace("-", ""),
               valid.replace("7c3a", "4c3a"), valid.replace("9f4e", "1f4e"))
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        before = s.led.path.read_bytes()
        for rid in invalid:
            event = ev.run_created_event(graph_id="g", graph_version="v",
                                         input_hash="h", input_ref="synthetic://a",
                                         run_id=rid)
            refuses(ev.EventValidationError, s.led.append, event)
            assert s.led.path.read_bytes() == before


def test_historical_noncanonical_run_id_remains_readable():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        history = [dict(e, run_id="historical-id") for e in s.led.events()]
        f = fold(s.graph, history, "historical-id")
        assert f["identity"] is not None
        assert f["nodes"]["a"]["state"] == "executed"


def test_writer_preserves_synthetic_legacy_namespace():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        event = ev.run_created_event(graph_id="g", graph_version="v",
                                     input_hash="h", input_ref="synthetic://a",
                                     run_id="legacy-synthetic")
        event["legacy_ambiguous"] = True
        assert s.led.append(event)["run_id"] == "legacy-synthetic"


def test_malformed_timeout_facts_refused_on_write_and_inert_on_read():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        history = s.led.events()
        for transport in (None, [], {"timed_out": "false"}, {"timed_out": 0}):
            event = dict(history[-1], event_id=ids.new_event_id(),
                         seq=history[-1]["seq"] + 1, event_type="node_returned",
                         exit_code=0, output_evidence=artifact_evidence(),
                         transport=transport)
            refuses(ev.EventValidationError, s.led.append, event)
            f = fold(s.graph, history + [event], s.rid)
            assert f["nodes"]["a"]["state"] == "running"
            assert any("malformed event inert" in a for a in f["anomalies"])


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(vars(sys.modules["__main__"]).items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"test_core_release: {len(fns)} tests PASS")
