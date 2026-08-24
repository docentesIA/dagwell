"""Adversarial matrix T1-T22 — explicit coverage of the governed core.

Zero-cost, synthetic fixtures only. Each T states the attack (or the required
behavior) and the contract clause it answers to. The matrix covers the second
half of the consolidated core hardening — output evidence fail-closed (H5),
the stalled -> run_landed lifecycle (H6), schema_version / UUIDv7 / legacy
boundaries (H7), c1 parser consistency (H8), the approved phase-gate debt
(H9) — plus the cross-cutting invariants those changes must never weaken.

Provenance note: the original mission's T1-T22 numbering arrived truncated
and is unrecoverable. This matrix is a RECONSTRUCTION derived from the
Execution Contract itself (I1-I29 and the section-13 boundaries), not a copy
of that lost list. The labels are ours; the obligations are the contract's.
"""

import json
import re
import tempfile
import unicodedata
import uuid
from pathlib import Path

from dagwell import (
    artifacts, canonical, human, ids, operations, runtime, schemas,
    verification as vf,
)
from dagwell.artifacts import ArtifactLayoutError
from dagwell.checkpoint import CheckpointRefused, operational_checkpoint
from dagwell.evidence import EVIDENCE_TYPES
from dagwell.graph import GraphValidationError, load_graph, validate_graph
from dagwell.ledger import (
    EventValidationError, Ledger, LedgerIntegrityError, SCHEMA_VERSION,
    occurred_now,
)
from dagwell.ledger.events import _MODEL_FAMILY_RE, valid_family
from dagwell.operations import OperationRefused
from tests_scenario import AGENDA, EVID, GRAPH_TEXT, S

EVID2 = "sha256:" + "cd" * 32
EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

# two independent nodes: lets a run hold a failed node AND a ready one
TWO_NODE_GRAPH = json.dumps({
    "graph_id": "two",
    "nodes": [
        {"id": "x", "deps": [], "output_evidence": "structured_value",
         "no_verification": "leaf"},
        {"id": "y", "deps": [], "output_evidence": "structured_value",
         "no_verification": "leaf"},
    ],
})


def _expect(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    raise AssertionError(f"expected {exc_type.__name__}")


def _raw_write(led, event):
    """Bypass every write guard — simulates a ledger damaged or forged out of
    band, which the read side must survive without granting authority."""
    with open(led.path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


def _artifact_evidence(evidence_id):
    return {"type": "artifact", "evidence_id": evidence_id,
            "output_manifest": [{"name": "o.md",
                                 "artifact_digest": evidence_id}]}


def _to_gate(s):
    s.dispatch()
    s.ret()
    s.request("lint", "deterministic")
    s.verdict("lint", "deterministic")
    s.request("gate", "human")


# == H5 — output evidence fail-closed (contract §4, §7, I28, I29) ==========

def test_T01_successful_transport_without_evidence_never_reaches_executed():
    """T1: exit 0 alone is not execution. Absent required evidence lands the
    attempt in failed — it does not reach executed, much less completed."""
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret(exit_code=0, evidence=None)
        f = s.fold()
        assert f["nodes"]["a"]["state"] == "failed"
        assert f["checkpoint"] == []


def test_T02_malformed_evidence_is_refused_before_it_is_recorded():
    """T2: a malformed evidence claim never enters the ledger. The honest
    alternative — recording the return with no evidence — stays available, so
    refusing the lie never costs the ability to record the failure."""
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        operations.dispatch(s.led, s.graph, s.rid, "a")
        for bad in ({"type": "artifact", "evidence_id": EVID},      # no manifest
                    {"type": "artifact", "evidence_id": EVID,
                     "output_manifest": []},                        # empty
                    {"type": "artifact", "evidence_id": "",
                     "output_manifest": [{"name": "o", "artifact_digest": EVID}]},
                    {"type": "artifact", "evidence_id": EVID,
                     "output_manifest": [{"name": "o"}]},           # no digest
                    "not-an-object"):
            _expect(OperationRefused, operations.record_return, s.led, s.graph,
                    s.rid, "a", 1, 0, bad)
        assert s.fold()["nodes"]["a"]["state"] == "running"   # nothing recorded
        operations.record_return(s.led, s.graph, s.rid, "a", 1, 0)
        assert s.fold()["nodes"]["a"]["state"] == "failed"


def test_T03_evidence_type_must_match_the_node_declaration():
    """T3: the node declares its evidence type (I28); returning another type
    is refused at the boundary and, if forged into the ledger, folds to
    failed — it never becomes executed."""
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        operations.dispatch(s.led, s.graph, s.rid, "a")
        _expect(OperationRefused, operations.record_return, s.led, s.graph,
                s.rid, "a", 1, 0, {"type": "structured_value",
                                   "evidence_id": EVID})
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret(evidence={"type": "structured_value", "evidence_id": EVID})
        assert s.fold()["nodes"]["a"]["state"] == "failed"


def test_T04_artifact_evidence_requires_a_non_empty_digested_manifest():
    """T4: for artifact evidence the specialized realization is a non-empty
    output_manifest carrying artifact_digest (§7) — presence of a handoff was
    the V1 predicate, content/proof is the contract's."""
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret(evidence={"type": "artifact", "evidence_id": EVID,
                        "output_manifest": []})
        assert s.fold()["nodes"]["a"]["state"] == "failed"
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret(evidence=_artifact_evidence(EVID))
        assert s.fold()["nodes"]["a"]["state"] == "executed"


def test_T05_verification_never_binds_to_a_failed_transport():
    """T5: only an executed attempt enters verification. Valid evidence does
    not rescue an unsuccessful transport, and neither half alone opens the
    gate (§4)."""
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret(exit_code=1)                       # evidence fine, transport not
        assert s.fold()["nodes"]["a"]["state"] == "failed"
        _expect(EventValidationError, s.request, "lint", "deterministic")


def test_T06_a_verdict_on_old_evidence_never_validates_new_evidence():
    """T6 (I29): the verdict binds to (run, node, attempt, verification_id,
    verification_attempt, evidence_id). Attempt k+1 produces new evidence, and
    the previous attempt's approval is worth nothing against it."""
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()
        s.request("lint", "deterministic")
        s.verdict("lint", "deterministic", verdict="rejected")
        assert s.fold()["nodes"]["a"]["state"] == "failed"
        human.human_retry(s.led, s.graph, s.rid, "a", actor="rey")
        s.dispatch(attempt=2)
        s.ret(attempt=2, evidence=_artifact_evidence(EVID2))
        s.led.append(vf.verification_requested_event(
            run_id=s.rid, node_id="a", attempt=2, verification_id="lint",
            verification_attempt=1, family="deterministic",
            evidence_id=EVID2))
        # concluding attempt 2's verification with attempt 1's evidence id
        _expect(LedgerIntegrityError, s.led.append, vf.verdict_recorded_event(
            run_id=s.rid, node_id="a", attempt=2, verification_id="lint",
            verification_attempt=1, family="deterministic", actor="v",
            verification_status="completed", verdict="approved",
            evidence_id=EVID))


# == H6 — the stalled -> run_landed lifecycle (contract §3, §8) ============

def test_T07_landing_is_refused_while_dispatchable_work_remains():
    """T7: run_landed means nothing dispatchable AND nothing in flight (§3).
    A node the topology already unblocked is work waiting to be done, not a
    run at rest — landing it would truncate WIP under a closed motive."""
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp, graph_text=TWO_NODE_GRAPH)
        s.dispatch(node="x")
        s.ret(node="x", exit_code=1)
        f = s.fold()
        assert f["run_state"] == "stalled" and f["nodes"]["y"]["state"] == "ready"
        _expect(OperationRefused, operations.land_run, s.led, s.graph, s.rid,
                "retries_exhausted")
        s.dispatch(node="y")
        s.ret(node="y", exit_code=1)
        assert operations.land_run(s.led, s.graph, s.rid,
                                   "retries_exhausted")["reason"] \
            == "retries_exhausted"
        assert s.fold()["run_state"] == "landed"


def test_T08_landing_is_refused_in_flight_and_with_a_pending_gate():
    """T8: neither a running attempt nor a pending human gate is a landing."""
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        assert s.fold()["run_state"] == "running"
        _expect(OperationRefused, operations.land_run, s.led, s.graph, s.rid,
                "budget_exhausted")
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        _to_gate(s)
        assert s.fold()["run_state"] == "waiting_human"
        _expect(OperationRefused, operations.land_run, s.led, s.graph, s.rid,
                "human_rejection")


def test_T09_landing_motive_must_be_supported_by_the_projection():
    """T9: the motive set is closed (§3) AND the two fold-verifiable motives
    must be true of the projection — a run does not land on a rejection that
    never happened. budget_exhausted stays caller-asserted: the core owns no
    budget model (§13.12 open) and invents none."""
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret(exit_code=1)                                  # failed, none rejected
        _expect(OperationRefused, operations.land_run, s.led, s.graph, s.rid,
                "human_rejection")
        _expect(EventValidationError, operations.land_run, s.led, s.graph,
                s.rid, "because")                           # outside closed set
        operations.land_run(s.led, s.graph, s.rid, "retries_exhausted")
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        _to_gate(s)
        human.decide(s.led, s.graph, s.rid, "a", "rejected", actor="rey",
                     reason="not good enough")
        assert s.fold()["nodes"]["a"]["state"] == "rejected"
        _expect(OperationRefused, operations.land_run, s.led, s.graph, s.rid,
                "retries_exhausted")                        # nothing failed
        operations.land_run(s.led, s.graph, s.rid, "human_rejection")


def test_T10_landed_is_a_rest_not_a_death_and_resume_needs_the_motive_gone():
    """T10: a run lands, never dies (§3). Resume is refused while the motive
    stands; the human event that removes it un-lands the run and resume then
    continues the SAME run (§8)."""
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret(exit_code=1)
        operations.land_run(s.led, s.graph, s.rid, "retries_exhausted")
        assert s.fold()["run_state"] == "landed"
        _expect(runtime.ResumeRefused, runtime.resume, s.led, s.graph_text,
                s.input_text, s.rid)
        human.human_retry(s.led, s.graph, s.rid, "a", actor="rey")
        assert s.fold()["run_state"] != "landed"
        r = runtime.resume(s.led, s.graph_text, s.input_text, s.rid)
        assert r["state"]["run_id"] == s.rid          # the SAME run
        assert ("a", 2) in r["ready"]


# == H7 — schema_version / UUIDv7 / legacy boundaries (§2, I23, ADRs) ======

def test_T11_unsupported_schema_version_refused_on_write_inert_on_read():
    """T11: the writer emits only the schema it implements; a foreign version
    is refused rather than laundered in. On read it stays inert and signaled —
    never reinterpreted as v1 (ADR-0004)."""
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        _expect(EventValidationError, s.ev, "run_interrupt_requested",
                schema_version="99")
        _raw_write(s.led, {"schema_version": "99",
                           "event_id": ids.new_event_id(), "run_id": s.rid,
                           "seq": 2, "event_type": "run_cancelled",
                           "occurred_at": occurred_now()})
        f = s.fold()
        assert f["run_state"] != "cancelled"
        assert any("unsupported schema_version" in a for a in f["anomalies"])


def test_T12_run_and_event_ids_are_rfc9562_uuidv7_and_opaque():
    """T12 (ADR-0002): version 7, RFC variant, time-ordered, never derived
    from content, and never able to squat the reserved legacy namespace."""
    a, b = ids.new_run_id(), ids.new_run_id()
    for text in (a, b, ids.new_event_id()):
        u = uuid.UUID(text)
        assert u.version == 7
        assert (u.int >> 62) & 0b11 == 0b10          # RFC 4122/9562 variant
        assert text == text.lower() and str(u) == text
    assert (uuid.UUID(b).int >> 80) >= (uuid.UUID(a).int >> 80)   # time-sortable
    assert a != b                                   # identical context, distinct id
    assert not ids.is_legacy(a) and ids.is_legacy("legacy-pesquisa")


def test_T13_legacy_namespace_and_ambiguity_label_travel_together():
    """T13 (§2, I23): a synthetic run aggregating indistinguishable history
    must SAY so; and a real execution can never wear the label that exempts a
    run from modern checkpoints."""
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        legacy = {"schema_version": SCHEMA_VERSION,
                  "event_id": ids.new_event_id(), "run_id": "legacy-pesquisa",
                  "event_type": "run_created", "occurred_at": occurred_now(),
                  "graph_id": "demo",
                  "graph_version": s.graph["graph_version"],
                  "input_hash": canonical.input_hash(AGENDA),
                  "input_ref": "legacy://v1", "parent_run_id": None}
        _expect(EventValidationError, s.led.append, dict(legacy))
        assert s.led.append(dict(legacy, legacy_ambiguous=True))["seq"] == 1
        _expect(EventValidationError, s.led.append,
                dict(legacy, run_id=ids.new_run_id(),
                     event_id=ids.new_event_id(), legacy_ambiguous=True))


def test_T14_legacy_runs_never_checkpoint_and_never_mutate():
    """T14 (I23): the legacy label is history, not an execution. It yields no
    modern operational checkpoint and accepts no operational mutation — while
    the real runs sharing the same ledger are untouched."""
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.led.append({"schema_version": SCHEMA_VERSION,
                      "event_id": ids.new_event_id(),
                      "run_id": "legacy-pesquisa", "event_type": "run_created",
                      "occurred_at": occurred_now(), "graph_id": "demo",
                      "graph_version": s.graph["graph_version"],
                      "input_hash": canonical.input_hash(AGENDA),
                      "input_ref": "legacy://v1", "parent_run_id": None,
                      "legacy_ambiguous": True})
        _expect(CheckpointRefused, operational_checkpoint, None, s.led,
                s.graph, "legacy-pesquisa")
        _expect(OperationRefused, operations.dispatch, s.led, s.graph,
                "legacy-pesquisa", "a")
        _expect(OperationRefused, operations.land_run, s.led, s.graph,
                "legacy-pesquisa", "retries_exhausted")
        assert operational_checkpoint(None, s.led, s.graph, s.rid)["completed"] == []


# == H8 — c1 parser consistency (ADR-0003, I24) ============================

def test_T15_raw_text_and_frozen_snapshot_parse_to_the_same_graph():
    """T15: one graph_version must mean one parsed graph. NFC composition can
    merge distinct code-point sequences, so parsing the raw file while the
    snapshot holds the canonical form would give two different node id sets
    for a single identity. The parser reads the canonical form."""
    decomposed = "gaté"                    # 'gate' + combining acute
    composed = unicodedata.normalize("NFC", decomposed)
    assert composed != decomposed
    text = json.dumps({"graph_id": "acentos", "nodes": [
        {"id": decomposed, "deps": [], "output_evidence": "structured_value",
         "no_verification": "leaf"}]}, ensure_ascii=False)

    from_raw = load_graph(text)
    from_canonical = load_graph(canonical.canonicalize_text(text))
    assert set(from_raw["nodes"]) == set(from_canonical["nodes"]) == {composed}
    assert from_raw["graph_version"] == from_canonical["graph_version"]

    with tempfile.TemporaryDirectory() as tmp:
        led = Ledger(Path(tmp) / "l.jsonl")
        _, founding = runtime.start_run(led, graph_text=text,
                                        input_text=AGENDA,
                                        input_ref="synthetic://a")
        # resume loads the frozen snapshot and must see the same graph (I24)
        r = runtime.resume(led, None, AGENDA, founding["run_id"])
        assert [nid for nid, _ in r["ready"]] == [composed]


def test_T16_c1_is_idempotent_content_only_and_fails_closed():
    """T16 (ADR-0003, emenda H2): identity is content, never location; line
    endings, BOM and Unicode form are normalized; undecodable input raises
    instead of silently falling back to raw bytes."""
    for sample in ("", "a", "a\r\nb\r\n", "﻿x\n\n\n", "é", "  keep  \n"):
        once = canonical.canonicalize_text(sample)
        assert canonical.canonicalize_text(once) == once            # idempotent
        assert canonical.content_digest(sample) == canonical.content_digest(once)
        assert once.endswith("\n") and not once.endswith("\n\n")
    assert canonical.content_digest("a\r\nb") == canonical.content_digest("a\nb")
    assert canonical.content_digest("﻿a") == canonical.content_digest("a")
    assert canonical.content_digest("é") == canonical.content_digest("é")
    assert canonical.canonicalize_text("  keep  \n") == "  keep  \n"  # inner ws kept
    assert canonical.content_digest("x\n").startswith("sha256:")
    _expect(UnicodeDecodeError, canonical.content_digest, b"\xff\xfe\x00")


# == H9 — approved phase-gate debt (Plan Phase 4/7, §1, I18) ==============

def test_T17_shipped_schema_is_in_parity_with_the_authoritative_validator():
    """T17: the schema is a shape aid, never a second source of truth. Its
    enums and required fields are locked to the code's, and a document the
    schema's shape accepts can still be refused by the validator — which is
    exactly why the validator stays authoritative."""
    schema = schemas.load()
    node = schema["$defs"]["node"]
    verification = schema["$defs"]["verification"]
    assert set(node["properties"]["output_evidence"]["enum"]) == set(EVIDENCE_TYPES)
    literal, patterned = verification["properties"]["family"]["anyOf"]
    assert set(literal["enum"]) == {"deterministic", "human"}
    assert patterned["pattern"] == _MODEL_FAMILY_RE.pattern
    assert set(schema["required"]) == {"graph_id", "nodes"}
    assert set(node["required"]) == {"id", "output_evidence"}
    assert {frozenset(o["required"]) for o in node["oneOf"]} == {
        frozenset({"verifications"}), frozenset({"no_verification"})}
    for family in ("deterministic", "human", "model:claude", "model:gpt-5"):
        assert valid_family(family)
        assert (family in literal["enum"]
                or re.match(patterned["pattern"], family))
    for family in ("model:", "robot", "", None, "Model:x"):
        assert not valid_family(family)
    # shape-valid, rule-invalid: only the validator catches a dependency cycle
    validate_graph(json.loads(EXAMPLES.joinpath("graph-canonical.json")
                              .read_text(encoding="utf-8")))
    _expect(GraphValidationError, validate_graph, {"graph_id": "c", "nodes": [
        {"id": "x", "deps": ["y"], "output_evidence": "structured_value",
         "no_verification": "leaf"},
        {"id": "y", "deps": ["x"], "output_evidence": "structured_value",
         "no_verification": "leaf"}]})


def test_T18_the_canonical_example_graph_loads_and_freezes_an_identity():
    """T18 (Plan Phase 4 exit): the shipped example validates against the
    authoritative loader and yields a content-addressed graph_version."""
    text = EXAMPLES.joinpath("graph-canonical.json").read_text(encoding="utf-8")
    graph = load_graph(text)
    assert graph["graph_id"] == "canonical-example"
    assert set(graph["nodes"]) == {"draft", "publish", "summary"}
    assert graph["graph_version"] == canonical.content_digest(text)
    assert graph["nodes"]["summary"]["no_verification"]          # signed vacuum
    assert [v["family"] for v in graph["nodes"]["draft"]["verifications"]] \
        == ["deterministic", "human"]                            # machines first


def test_T19_artifacts_of_distinct_runs_and_attempts_never_share_a_directory():
    """T19 (§1, I18): append-only applies to disk. Distinct runs and attempts
    get distinct directories by construction, and graph/node ids — which are
    DATA — can never steer a write out of the run's directory."""
    with tempfile.TemporaryDirectory() as tmp:
        def d(**kw):
            base = {"operation": "op", "run_id": "r1", "node_id": "a",
                    "attempt": 1}
            return artifacts.attempt_dir(tmp, **{**base, **kw})
        paths = {d(), d(run_id="r2"), d(attempt=2), d(node_id="b"),
                 d(operation="other")}
        assert len(paths) == 5
        assert d().parts[-1] == "t1" and "runs" in d().parts
        assert d(attempt=2).parts[-1] == "t2"
        for bad in ("..", ".", "", "a/b", "/etc", "a\\b", "a\0b", None, 7):
            _expect(ArtifactLayoutError, d, operation=bad)
            _expect(ArtifactLayoutError, d, run_id=bad)
            _expect(ArtifactLayoutError, d, node_id=bad)
        for bad in (0, -1, "1", True, 1.0):
            _expect(ArtifactLayoutError, d, attempt=bad)
        created = artifacts.attempt_dir(tmp, operation="op", run_id="r1",
                                        node_id="a", attempt=1, create=True)
        assert created.is_dir()
        assert artifacts.attempt_dir(tmp, operation="op", run_id="r1",
                                     node_id="a", attempt=1,
                                     create=True) == created   # idempotent
        assert created.is_relative_to(Path(tmp))                # stays inside


# == Cross-cutting invariants the hardening must never weaken ==============

def test_T20_seq_is_the_authority_and_timestamps_never_decide_order():
    """T20 (I20): occurred_at is observational — clocks drift, lag and
    disagree between machines. A ledger whose timestamps run backwards still
    folds by seq."""
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.ev("node_dispatched", node_id="a", attempt=1,
             occurred_at="2000-01-01T00:00:00-03:00")
        s.ev("node_returned", node_id="a", attempt=1, exit_code=0,
             occurred_at="1999-01-01T00:00:00-03:00",
             output_evidence=_artifact_evidence(EVID))
        s.led.append(vf.verification_requested_event(
            run_id=s.rid, node_id="a", attempt=1, verification_id="lint",
            verification_attempt=1, family="deterministic", evidence_id=EVID))
        s.led.append(dict(vf.verdict_recorded_event(
            run_id=s.rid, node_id="a", attempt=1, verification_id="lint",
            verification_attempt=1, family="deterministic", actor="v",
            verification_status="completed", verdict="approved",
            evidence_id=EVID), occurred_at="1998-01-01T00:00:00-03:00"))
        events = s.led.run(s.rid)
        seqs = [e["seq"] for e in events]
        stamps = [e["occurred_at"] for e in events]
        assert seqs == sorted(seqs) == [1, 2, 3, 4, 5]
        assert stamps != sorted(stamps)          # timestamps contradict order
        # reachable only by folding dispatch -> return -> request -> verdict
        # in seq order; by timestamp the verdict would precede its request
        f = s.fold()
        assert f["nodes"]["a"]["state"] == "verifying"
        assert f["checkpoint"] == []             # the human gate is still due


def test_T21_a_seq_gap_reduces_observability_but_never_grants_authority():
    """T21 (P3, I27): the founding rule. A run with an unresolved gap can be
    READ diagnostically — marked integrity: degraded — and can do nothing
    else: every mutable path is closed until explicit reconciliation."""
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        _raw_write(s.led, {"schema_version": SCHEMA_VERSION,
                           "event_id": ids.new_event_id(), "run_id": s.rid,
                           "seq": 9, "event_type": "run_interrupt_requested",
                           "occurred_at": occurred_now()})
        f = s.fold()
        assert f["integrity"] == "degraded"
        assert any("seq gap" in a for a in f["anomalies"])
        assert f["run_state"] == "running"            # observability preserved
        _expect(OperationRefused, operations.dispatch, s.led, s.graph, s.rid, "a")
        _expect(OperationRefused, operations.land_run, s.led, s.graph, s.rid,
                "retries_exhausted")
        _expect(human.DecisionRefused, human.human_retry, s.led, s.graph,
                s.rid, "a", actor="rey")
        _expect(human.DecisionRefused, human.cancel_run, s.led, s.graph,
                s.rid, actor="rey")
        _expect(runtime.ResumeRefused, runtime.resume, s.led, s.graph_text,
                s.input_text, s.rid)
        _expect(CheckpointRefused, operational_checkpoint, None, s.led,
                s.graph, s.rid)
        _expect(LedgerIntegrityError, s.ev, "run_interrupt_requested")


def test_T22_completed_is_inexpressible_over_an_authoritative_rejection():
    """T22 (§7, the red team's problem 4): successful transport + a rejecting
    verifier + a 'completed' node. With an authoritative rejection recorded
    there is no path into the checkpoint — not by re-firing the verifier, not
    by a human overruling it, not by forging a later approval."""
    with tempfile.TemporaryDirectory() as tmp:
        s = S(tmp)
        s.dispatch()
        s.ret()                                   # exit 0 + valid evidence
        s.request("lint", "deterministic")
        s.verdict("lint", "deterministic", verdict="rejected")
        assert s.fold()["nodes"]["a"]["state"] == "failed"
        assert s.fold()["checkpoint"] == []
        # re-firing the concluded verification is refused
        _expect(LedgerIntegrityError, s.request, "lint", "deterministic", va=2)
        # the node is not waiting on a human, so no human can approve it
        _expect(human.DecisionRefused, human.decide, s.led, s.graph, s.rid,
                "a", "approved", actor="rey")
        # a forged later approval loses to the first authoritative verdict
        _raw_write(s.led, dict(vf.verdict_recorded_event(
            run_id=s.rid, node_id="a", attempt=1, verification_id="lint",
            verification_attempt=1, family="deterministic", actor="ghost",
            verification_status="completed", verdict="approved",
            evidence_id=EVID), seq=6))
        f = s.fold()
        assert f["nodes"]["a"]["state"] == "failed"
        assert f["checkpoint"] == []


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(vars(sys.modules["__main__"]).items())
           if k.startswith("test_T") and callable(v)]
    for fn in fns:
        fn()
    print(f"test_matrix: {len(fns)} adversarial cases (T1-T22) PASS")
