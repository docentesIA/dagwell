"""Shared synthetic scenario for DAGWELL tests. Synthetic data only."""

import json
from pathlib import Path

from dagwell import ids, verification as vf
from dagwell.fold import fold
from dagwell.graph import load_graph
from dagwell.ledger import Ledger, SCHEMA_VERSION, create_run, occurred_now

EVID = "sha256:" + "ab" * 32

GRAPH_TEXT = json.dumps({
    "graph_id": "demo",
    "nodes": [
        {"id": "a", "deps": [], "output_evidence": "artifact",
         "verifications": [
             {"verification_id": "lint", "family": "deterministic"},
             {"verification_id": "gate", "family": "human"}]},
        {"id": "b", "deps": ["a"], "output_evidence": "structured_value",
         "no_verification": "summary node, verified downstream"},
    ],
})
AGENDA = "# synthetic agenda\n"


class S:
    """One synthetic scenario: ledger + graph + run."""

    def __init__(self, tmp, graph_text=GRAPH_TEXT, input_text=AGENDA):
        self.graph_text = graph_text
        self.input_text = input_text
        self.graph = load_graph(graph_text)
        self.led = Ledger(Path(tmp) / "l.jsonl")
        self.rid = create_run(self.led, graph_id=self.graph["graph_id"],
                              graph_text=graph_text, input_text=input_text,
                              input_ref="synthetic://a")["run_id"]

    def ev(self, event_type, **extra):
        e = {"schema_version": SCHEMA_VERSION, "event_id": ids.new_event_id(),
             "run_id": self.rid, "event_type": event_type,
             "occurred_at": occurred_now()}
        e.update(extra)
        return self.led.append(e)

    def dispatch(self, node="a", attempt=1):
        return self.ev("node_dispatched", node_id=node, attempt=attempt)

    def ret(self, node="a", attempt=1, exit_code=0, evidence="ok"):
        if evidence == "ok" and node == "a":
            payload = {"type": "artifact", "evidence_id": EVID,
                       "output_manifest": [{"name": "o.md",
                                            "artifact_digest": EVID}]}
        elif evidence == "ok":
            payload = {"type": "structured_value", "evidence_id": EVID}
        elif evidence is None:
            payload = None
        else:
            payload = evidence
        e = {"node_id": node, "attempt": attempt, "exit_code": exit_code}
        if payload is not None:
            e["output_evidence"] = payload
        return self.ev("node_returned", **e)

    def request(self, vid="lint", family="deterministic", node="a", attempt=1,
                va=1):
        return self.led.append(vf.verification_requested_event(
            run_id=self.rid, node_id=node, attempt=attempt,
            verification_id=vid, verification_attempt=va, family=family,
            evidence_id=EVID))

    def verdict(self, vid="lint", family="deterministic", node="a", attempt=1,
                va=1, status="completed", verdict="approved", reason=None,
                actor="verifier"):
        # family human goes through the storage path explicitly: these are
        # SYNTHETIC historical ledgers, not decisions being issued (I8, §5).
        return self.led.append(_human_wing=(family == "human"),
                               event=vf.verdict_recorded_event(
            run_id=self.rid, node_id=node, attempt=attempt,
            verification_id=vid, verification_attempt=va, family=family,
            actor=actor, verification_status=status, verdict=verdict,
            evidence_id=EVID, reason=reason))

    def fold(self):
        return fold(self.graph, self.led.events(), self.rid)
