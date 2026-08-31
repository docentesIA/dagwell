"""Consolidated hardening pass — adversarial coverage. Zero-cost, synthetic.

Covers: governed operational boundary refusal matrix (H1); read-side
integrity normalization (H2); fail-closed non-authoritative checkpoint (H3);
frozen graph snapshots / I24 (H4).
"""

import json
import tempfile
from pathlib import Path

from dagwell import human, ids, operations, runtime, snapshots
from dagwell.checkpoint import CheckpointRefused, operational_checkpoint
from dagwell.fold import fold
from dagwell.graph import GraphValidationError, load_graph
from dagwell.ledger import Ledger, LedgerIntegrityError, SCHEMA_VERSION, occurred_now
from dagwell.ledger import events as ev_mod
from dagwell.operations import OperationRefused
from helpers import artifact_evidence
from tests_scenario import AGENDA, EVID, GRAPH_TEXT, S


def _expect(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    raise AssertionError(f"expected {exc_type.__name__}")


def _to_gate(s):
    s.dispatch()
    s.ret()
    s.request("lint", "deterministic")
    s.verdict("lint", "deterministic")
    s.request("gate", "human")


# -- H1: governed dispatch refusal matrix ----------------------------------

def test_dispatch_refusal_matrix():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        _expect(OperationRefused, operations.dispatch, s.led, s.graph,
                s.rid, "zz")                       # unknown node
        _expect(OperationRefused, operations.dispatch, s.led, s.graph,
                s.rid, "b")                        # dependency-blocked
        operations.dispatch(s.led, s.graph, s.rid, "a")
        _expect(OperationRefused, operations.dispatch, s.led, s.graph,
                s.rid, "a")                        # duplicate/in-flight
        s.ret()
        s.request("lint", "deterministic")
        s.verdict("lint", "deterministic")
        s.request("gate", "human")
        _expect(OperationRefused, operations.dispatch, s.led, s.graph,
                s.rid, "a")                        # waiting_human
        human.decide(s.led, s.graph, s.rid, "a", "approved", actor="rey")
        _expect(OperationRefused, operations.dispatch, s.led, s.graph,
                s.rid, "a")                        # completed node


def test_dispatch_rejected_and_failed_need_human_retry():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        _to_gate(s)
        human.decide(s.led, s.graph, s.rid, "a", "rejected", actor="rey",
                     reason="no")
        _expect(OperationRefused, operations.dispatch, s.led, s.graph,
                s.rid, "a")                        # rejected, no reopen
        human.human_retry(s.led, s.graph, s.rid, "a", actor="rey")
        e = operations.dispatch(s.led, s.graph, s.rid, "a")
        assert e["attempt"] == 2
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret(exit_code=1)                         # failed
        _expect(OperationRefused, operations.dispatch, s.led, s.graph,
                s.rid, "a")                        # no authorized policy
        human.human_retry(s.led, s.graph, s.rid, "a", actor="rey")
        assert operations.dispatch(s.led, s.graph, s.rid, "a")["attempt"] == 2


def test_dispatch_run_level_guards():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        human.cancel_run(s.led, s.graph, s.rid, actor="rey")
        _expect(OperationRefused, operations.dispatch, s.led, s.graph,
                s.rid, "a")                        # cancelled run
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret(exit_code=1)
        operations.land_run(s.led, s.graph, s.rid, "retries_exhausted")
        _expect(OperationRefused, operations.dispatch, s.led, s.graph,
                s.rid, "a")                        # landed, motive present


def test_machine_first_enforced_at_boundary():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        # requesting the human gate before the machine check is refused
        _expect(OperationRefused, operations.request_verification, s.led,
                s.graph, s.rid, "a", "gate")
        operations.request_verification(s.led, s.graph, s.rid, "a", "lint")
        s.verdict("lint", "deterministic")
        e = operations.request_verification(s.led, s.graph, s.rid, "a", "gate")
        assert e["family"] == "human"


def test_human_verdict_only_via_governed_human_operation():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        _to_gate(s)
        _expect(OperationRefused, operations.record_machine_verdict, s.led,
                s.graph, s.rid, "a", "gate",
                verification_status="completed", verdict="approved",
                actor="robot")


def test_completed_run_cannot_become_cancelled():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        _to_gate(s)
        human.decide(s.led, s.graph, s.rid, "a", "approved", actor="rey")
        s.dispatch(node="b")
        s.ret(node="b")
        assert s.fold()["run_state"] == "completed"
        _expect(human.DecisionRefused, human.cancel_run, s.led, s.graph,
                s.rid, actor="rey")


def test_budget_and_land_guards():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        # landing a running run is refused
        _expect(OperationRefused, operations.land_run, s.led, s.graph,
                s.rid, "budget_exhausted")
        s.ret(exit_code=1)
        operations.land_run(s.led, s.graph, s.rid, "budget_exhausted")
        operations.extend_budget(s.led, s.graph, s.rid, 10, "rey")
        assert s.fold()["run_state"] != "landed"


# -- H2: read-side integrity normalization ---------------------------------

def _raw_write(led, event):
    with open(led.path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


def test_rogue_verdict_without_request_is_inert():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        rogue = {"schema_version": SCHEMA_VERSION,
                 "event_id": ids.new_event_id(), "run_id": s.rid, "seq": 4,
                 "event_type": "verdict_recorded",
                 "occurred_at": occurred_now(), "node_id": "a", "attempt": 1,
                 "verification_id": "lint", "verification_attempt": 1,
                 "family": "deterministic", "actor": "ghost",
                 "verification_status": "completed", "verdict": "approved",
                 "evidence_id": EVID}
        _raw_write(s.led, rogue)
        f = s.fold()
        assert f["nodes"]["a"]["state"] == "executed"   # NEVER counts
        assert any("without matching" in a for a in f["anomalies"])


def test_rogue_human_substitution_without_escalation_is_inert():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        s.request("lint", "deterministic")
        rogue = {"schema_version": SCHEMA_VERSION,
                 "event_id": ids.new_event_id(), "run_id": s.rid, "seq": 5,
                 "event_type": "verdict_recorded",
                 "occurred_at": occurred_now(), "node_id": "a", "attempt": 1,
                 "verification_id": "lint", "verification_attempt": 1,
                 "family": "human", "actor": "ghost",
                 "verification_status": "completed", "verdict": "approved",
                 "evidence_id": EVID}
        _raw_write(s.led, rogue)
        f = s.fold()
        assert f["nodes"]["a"]["state"] == "verifying"  # substitution inert
        assert any("substitution" in a for a in f["anomalies"])


def test_unsupported_schema_version_is_inert_not_v1():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        rogue = {"schema_version": "99", "event_id": ids.new_event_id(),
                 "run_id": s.rid, "seq": 2, "event_type": "run_cancelled",
                 "occurred_at": occurred_now()}
        _raw_write(s.led, rogue)
        f = s.fold()
        assert f["run_state"] != "cancelled"            # not interpreted as v1
        assert any("unsupported schema_version" in a for a in f["anomalies"])


def test_malformed_domain_fields_gain_no_authority():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        rogue = {"schema_version": SCHEMA_VERSION,
                 "event_id": ids.new_event_id(), "run_id": s.rid, "seq": 2,
                 "event_type": "run_landed", "occurred_at": occurred_now(),
                 "reason": "because"}                   # not in closed set
        _raw_write(s.led, rogue)
        f = s.fold()
        assert f["run_state"] != "landed"
        assert any("malformed" in a for a in f["anomalies"])


def test_global_duplicate_event_id_detectable_across_runs():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        other = S(tmp + "")  # same dir would clash; use nested dir
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        b = s.led.run(s.rid)[0]
        clone = dict(b, run_id="legacy-x", seq=1,
                     event_type="run_created")
        _raw_write(s.led, clone)                        # same event_id, other run
        dups = s.led.global_duplicate_event_ids()
        assert dups == [b["event_id"]]


def test_late_founder_is_anomaly_not_identity():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        founder2 = dict(s.led.run(s.rid)[0], event_id=ids.new_event_id(),
                        seq=3, graph_version="sha256:" + "ff" * 32)
        _raw_write(s.led, founder2)
        f = s.fold()
        assert f["identity"]["graph_version"] == s.graph["graph_version"]
        assert any("non-authoritative run_created" in a for a in f["anomalies"])


# -- H3: checkpoint fail-closed --------------------------------------------

def test_checkpoint_refused_on_gap_and_missing_founder():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        rogue = {"schema_version": SCHEMA_VERSION,
                 "event_id": ids.new_event_id(), "run_id": s.rid, "seq": 9,
                 "event_type": "run_interrupt_requested",
                 "occurred_at": occurred_now()}
        _raw_write(s.led, rogue)
        _expect(CheckpointRefused, operational_checkpoint, None, s.led,
                s.graph, s.rid)


def test_checkpoint_refuses_unrelated_graph():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        other = load_graph(GRAPH_TEXT.replace("demo", "demo2"))
        _expect(LedgerIntegrityError, operational_checkpoint, None, s.led,
                other, s.rid)


def test_checkpoint_cache_tamper_never_affects_result():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        cache = Path(tmp) / "cp.json"
        cp = operational_checkpoint(cache, s.led, s.graph, s.rid)
        assert cp["completed"] == []
        assert cp["input_hash"] == s.fold()["identity"]["input_hash"]
        cache.write_text(json.dumps(dict(cp, completed=["a", "b"])),
                         encoding="utf-8")              # tamper; ledger unchanged
        cp2 = operational_checkpoint(cache, s.led, s.graph, s.rid)
        assert cp2["completed"] == []                   # ledger/fold wins


# -- H4: frozen graph snapshots (I24) --------------------------------------

def test_snapshot_stored_verified_and_resume_from_snapshot():
    with tempfile.TemporaryDirectory() as tmp:
        led = Ledger(Path(tmp) / "data" / "ledger.jsonl")
        led.path.parent.mkdir(parents=True)
        graph, founding = runtime.start_run(
            led, graph_text=GRAPH_TEXT, input_text=AGENDA,
            input_ref="synthetic://a")
        gv = founding["graph_version"]
        stored = snapshots.load(led.path.parent / "graphs", gv)
        # stored content reproduces graph_version
        from dagwell import canonical
        assert canonical.content_digest(stored) == gv
        # resume with graph_text=None loads the frozen snapshot (I24)
        r = runtime.resume(led, None, AGENDA, founding["run_id"])
        assert r["ready"] == [("a", 1)]


def test_corrupt_snapshot_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        led = Ledger(Path(tmp) / "ledger.jsonl")
        graph, founding = runtime.start_run(
            led, graph_text=GRAPH_TEXT, input_text=AGENDA,
            input_ref="synthetic://a")
        gv = founding["graph_version"]
        path = next((led.path.parent / "graphs").glob("*.graph"))
        path.write_text("tampered\n", encoding="utf-8")
        _expect(snapshots.SnapshotIntegrityError, snapshots.load,
                led.path.parent / "graphs", gv)
        _expect(runtime.ResumeRefused, runtime.resume, led, None, AGENDA,
                founding["run_id"])


def test_fold_refuses_unrelated_graph():
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        other = load_graph(GRAPH_TEXT.replace("demo", "demo2"))
        _expect(LedgerIntegrityError, fold, other, s.led.events(), s.rid)


# -- H10: independent audit 2026-08-25 remediation -------------------------
# Three holes two independent auditors (openai, xai) found and reproduced.
# Each test fails if the hole reopens.

def test_raw_append_cannot_issue_a_human_verdict():
    """I8, §5 — a human verdict is a DECISION. Storage is not where decisions
    are made: the boundary is worthless if raw append is a way around it."""
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        _to_gate(s)
        from dagwell import verification as vf
        forged = vf.verdict_recorded_event(
            run_id=s.rid, node_id="a", attempt=1, verification_id="gate",
            verification_attempt=1, family="human", actor="an-adapter",
            verification_status="completed", verdict="approved", evidence_id=EVID)
        _expect(ev_mod.EventValidationError, s.led.append, forged)
        # the governed wing still works — the fix closes a door, not the wing
        human.decide(s.led, s.graph, s.rid, "a", "approved", actor="rey")
        assert fold(s.graph, s.led.run(s.rid), s.rid)["nodes"]["a"]["state"] \
            == "completed"


def _orphan_ledger(tmp):
    """A run whose founding run_created is absent: the fold cannot vouch for
    its identity (integrity degraded), so it is diagnostic-read only."""
    path = Path(tmp) / "l.jsonl"
    path.write_text(json.dumps({
        "schema_version": SCHEMA_VERSION, "event_id": ids.new_event_id(),
        "run_id": "orphan", "seq": 1, "event_type": "node_dispatched",
        "occurred_at": occurred_now(), "node_id": "a", "attempt": 1}) + "\n",
        encoding="utf-8")
    return Ledger(path), load_graph(GRAPH_TEXT)


def test_unvouched_identity_refuses_mutation_on_both_wings():
    """I25, §2 — the checkpoint and resume already refused; the write path
    did not. Both wings must refuse or the boundary is one-sided."""
    with tempfile.TemporaryDirectory() as tmp:
        led, graph = _orphan_ledger(tmp)
        assert fold(graph, led.run("orphan"), "orphan")["integrity"] != "ok"
        _expect(OperationRefused, operations.record_return, led, graph,
                "orphan", "a", attempt=1, exit_code=0,
                output_evidence=artifact_evidence())
        _expect(human.DecisionRefused, human.cancel_run, led, graph,
                "orphan", "rey")


def test_legacy_run_refuses_mutation_on_the_human_wing_too():
    """I23, §2 — operations refused legacy already; the human wing did not,
    so `dagwell cancel` mutated a label that is not an execution."""
    with tempfile.TemporaryDirectory() as tmp:
        from dagwell import canonical
        from dagwell.ledger import run_created_event
        led = Ledger(Path(tmp) / "l.jsonl")
        graph = load_graph(GRAPH_TEXT)
        founding = run_created_event(
            graph_id="demo", graph_version=canonical.graph_version(GRAPH_TEXT),
            input_hash=canonical.input_hash(AGENDA), input_ref="synthetic://a")
        founding["run_id"] = "legacy-demo"
        founding["legacy_ambiguous"] = True
        led.append(founding)
        _expect(OperationRefused, operations.dispatch, led, graph,
                "legacy-demo", "a")
        _expect(human.DecisionRefused, human.cancel_run, led, graph,
                "legacy-demo", "rey")
        _expect(human.DecisionRefused, human.decide, led, graph,
                "legacy-demo", "a", "approved", "rey")


def test_healthy_run_still_completes_end_to_end():
    """Regression guard: the three refusals above must not cost the ability
    to run a healthy run to completion, nor to cancel one legitimately."""
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        _to_gate(s)
        human.decide(s.led, s.graph, s.rid, "a", "approved", actor="rey")
        operations.dispatch(s.led, s.graph, s.rid, "b")
        operations.record_return(s.led, s.graph, s.rid, "b", attempt=1,
                                 exit_code=0,
                                 output_evidence=artifact_evidence())
        assert fold(s.graph, s.led.run(s.rid), s.rid)["run_state"] == "completed"
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        human.cancel_run(s.led, s.graph, s.rid, actor="rey")
        assert fold(s.graph, s.led.run(s.rid), s.rid)["run_state"] == "cancelled"


def test_unverifiable_evidence_type_cannot_be_left_unverified():
    """I5/I28, §4 fail-closed — the fourth audit finding. A node whose evidence
    type §13.17 has not specified CANNOT also waive verification: the core
    cannot tell a receipt from a sentence, so nothing would check the claim and
    `completed` would rest on a string. `artifact` keeps the signed vacuum,
    because the contract does define what makes an artifact invalid."""
    def graph_with(evidence, node):
        return json.dumps({"graph_id": "g", "nodes": [
            {"id": "n", "deps": [], "output_evidence": evidence, **node}]})

    for evidence in ("structured_value", "remote_receipt", "side_effect_receipt"):
        _expect(GraphValidationError, load_graph,
                graph_with(evidence, {"no_verification": "trust me"}))
        # the same type IS legal once something actually checks it
        load_graph(graph_with(evidence, {"verifications": [
            {"verification_id": "v", "family": "deterministic"}]}))

    # artifact is unchanged: the core validates it, so the vacuum stays signable
    load_graph(graph_with("artifact", {"no_verification": "leaf output"}))


def test_landing_refuses_a_node_that_still_owes_verification():
    """§3, I28 — the fifth audit finding. H6 closed landing over a READY node
    and left the symmetric hole: a node that returned successfully still owes
    its obligatory verification, and landing over it froze that verification
    behind `budget_exhausted` — a motive the core cannot attest while §13.12
    is open. Same WIP truncation, one step later in the node's life."""
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        folded = fold(s.graph, s.led.run(s.rid), s.rid)
        assert folded["nodes"]["a"]["state"] == "executed"
        assert folded["run_state"] == "stalled"      # looks like rest, is not
        for reason in ("budget_exhausted", "human_rejection", "retries_exhausted"):
            _expect(OperationRefused, operations.land_run, s.led, s.graph,
                    s.rid, reason)
        # once the verification is actually done, landing is available again
        s.request("lint", "deterministic")
        s.verdict("lint", "deterministic")
        s.request("gate", "human")
        human.decide(s.led, s.graph, s.rid, "a", "rejected", actor="rey",
                     reason="not good enough")
        operations.land_run(s.led, s.graph, s.rid, "human_rejection")
        assert fold(s.graph, s.led.run(s.rid), s.rid)["run_state"] == "landed"


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(vars(sys.modules["__main__"]).items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"test_hardening: {len(fns)} tests PASS")
