"""Phase 9 conformance (Adapter/Output Evidence Spec v1.0 §9). Zero-cost:
the subprocess transport is exercised with shell built-ins only — no quota,
no paid inference, no network."""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

from dagwell.adapters.registry import (
    RegistryValidationError, load_registry, validate_registry,
)
from dagwell.adapters.selection import SelectionError, select
from dagwell.adapters.transports import subprocess_transport as st
from dagwell.graph import CAPABILITY_TIERS, GraphValidationError, load_graph

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

REGISTRY = {
    "registry_version": 1,
    "bindings": [
        {"binding_id": "claude-cli", "transport": "subprocess",
         "platform": "claude", "invocation": "claude -p {mission}",
         "timeout_seconds": 60,
         "models": [
             {"model_id": "haiku", "family": "anthropic-claude",
              "tiers": ["trivial", "simple"], "relative_cost": 1},
             {"model_id": "opus", "family": "anthropic-claude",
              "tiers": ["simple", "complex", "frontier"], "relative_cost": 25}]},
        {"binding_id": "codex-cli", "transport": "subprocess",
         "platform": "codex", "invocation": "codex exec {mission}",
         "timeout_seconds": 60,
         "models": [
             {"model_id": "default", "family": "openai-gpt",
              "tiers": ["simple", "standard"], "relative_cost": 1}]},
    ],
}


def _expect(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    raise AssertionError(f"expected {exc_type.__name__}")


def _mutated(**binding_over):
    data = json.loads(json.dumps(REGISTRY))
    data["bindings"][0].update(binding_over)
    return data


# == §9.1 — registry refused before spend ===================================

def test_registry_validation_refuses_malformations():
    validate_registry(REGISTRY)
    _expect(RegistryValidationError, validate_registry,
            _mutated(timeout_seconds=None))                 # missing timeout
    _expect(RegistryValidationError, validate_registry,
            _mutated(timeout_seconds=0))                    # non-positive
    _expect(RegistryValidationError, validate_registry,
            _mutated(transport="telepathy"))                # unknown transport
    _expect(RegistryValidationError, validate_registry,
            _mutated(transport="http"))                     # reserved transport
    _expect(RegistryValidationError, validate_registry,
            _mutated(invocation="claude -p"))               # no {mission}
    _expect(RegistryValidationError, validate_registry,
            _mutated(models=[{"model_id": "m", "family": "anthropic-claude",
                              "tiers": [], "relative_cost": 1}]))  # empty tiers
    _expect(RegistryValidationError, validate_registry,
            _mutated(models=[{"model_id": "m", "family": "Claude",
                              "tiers": ["simple"], "relative_cost": 1}]))  # family form
    _expect(RegistryValidationError, validate_registry,
            _mutated(models=[{"model_id": "m", "family": "anthropic-claude",
                              "tiers": ["epic"], "relative_cost": 1}]))  # unknown tier
    _expect(RegistryValidationError, validate_registry, {"bindings": []})
    _expect(RegistryValidationError, load_registry, "{not json")


def test_load_registry_fixes_provenance():
    reg = load_registry(json.dumps(REGISTRY))
    assert reg["registry_digest"].startswith("sha256:")
    assert set(reg["bindings"]) == {"claude-cli", "codex-cli"}
    # The shipped example registry is itself valid.
    load_registry((EXAMPLES / "registry.example.json").read_text())


# == §9.2 — deterministic selection =========================================

def test_selection_cheapest_satisfying_and_tiebreak():
    reg = load_registry(json.dumps(REGISTRY))
    # simple is served by haiku (1), codex default (1), opus (25):
    # cheapest wins; tie between (claude-cli, haiku) and (codex-cli, default)
    # breaks lexicographically -> claude-cli/haiku. Difficulty dictates the
    # model: opus never fires for a simple task.
    chosen = select("simple", reg)
    assert (chosen["binding_id"], chosen["model_id"]) == ("claude-cli", "haiku")
    assert chosen["family"] == "anthropic-claude"
    assert chosen["transport"] == "subprocess"
    assert chosen["registry_digest"] == reg["registry_digest"]
    # frontier only opus serves.
    assert select("frontier", reg)["model_id"] == "opus"
    # availability filter (failed probe) removes a binding's models.
    assert select("simple", reg, available={"codex-cli"})[
        "binding_id"] == "codex-cli"


def test_selection_refuses_before_spend():
    reg = load_registry(json.dumps(REGISTRY))
    _expect(SelectionError, select, "standard", reg, set())   # none available
    _expect(SelectionError, select, "trivial", reg, {"codex-cli"})
    _expect(SelectionError, select, "epic", reg)              # unknown tier


def test_graph_capability_requirements():
    def g(node_extra):
        return json.dumps({"graph_id": "t", "nodes": [dict(
            {"id": "a", "deps": [], "output_evidence": "artifact",
             "verifications": [{"verification_id": "v",
                                "family": "deterministic"}]}, **node_extra)]})
    loaded = load_graph(g({"capability_requirements": {"tier": "simple"},
                           "mission": "write it to $OUT"}))
    assert loaded["nodes"]["a"]["capability_requirements"]["tier"] == "simple"
    # one identity model per node (spec §3.1)
    _expect(GraphValidationError, load_graph,
            g({"capability_requirements": {"tier": "simple"},
               "mission": "m", "x_command": "echo hi"}))
    _expect(GraphValidationError, load_graph,
            g({"capability_requirements": {"tier": "epic"}, "mission": "m"}))
    _expect(GraphValidationError, load_graph,
            g({"capability_requirements": {}, "mission": "m"}))
    _expect(GraphValidationError, load_graph,          # mission required
            g({"capability_requirements": {"tier": "simple"}}))
    assert list(CAPABILITY_TIERS) == [
        "trivial", "simple", "standard", "complex", "frontier"]


# == §9.4 — transport facts only, never verdicts ============================

def test_subprocess_transport_returns_facts_only():
    with tempfile.TemporaryDirectory() as tmp:
        out = str(Path(tmp) / "o.txt")
        binding = {"invocation": sys.executable + " -c {mission}",
                   "timeout_seconds": 30}
        facts = st.execute(binding,
                           "import os,sys;open(os.environ['OUT'],'w')"
                           ".write('done')",
                           out, env=dict(os.environ))
        assert facts["exit_code"] == 0
        assert facts["timed_out"] is False
        assert Path(out).read_text() == "done"     # $OUT reached the child
        for forbidden in ("verdict", "family", "verification_status"):
            assert forbidden not in facts
        failing = st.execute(binding, "raise SystemExit(3)", out,
                             env=dict(os.environ))
        assert failing["exit_code"] == 3           # a fact, not a verdict


def test_subprocess_timeout_ladder_records_the_fact():
    st_grace = st.GRACE_SECONDS
    st.GRACE_SECONDS = 0.5
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "o.txt")
            binding = {"invocation": sys.executable + " -c {mission}",
                       "timeout_seconds": 0.3}
            started = time.monotonic()
            # The child ignores SIGINT: the ladder's next rung (SIGTERM) must
            # end it — silently, keeping the suite's output clean.
            facts = st.execute(binding,
                               "import signal,time;"
                               "signal.signal(signal.SIGINT, signal.SIG_IGN);"
                               "time.sleep(60)",
                               out, env=dict(os.environ))
            assert facts["timed_out"] is True
            assert facts["exit_code"] != 0
            assert time.monotonic() - started < 30
    finally:
        st.GRACE_SECONDS = st_grace


def test_mission_is_one_argument_never_shell():
    argv = st.build_argv("claude -p {mission}", "a; rm -rf / #")
    assert argv == ["claude", "-p", "a; rm -rf / #"]   # one argv entry, inert
    _expect(st.TransportError, st.build_argv,
            "claude -p prefix-{mission}", "x")         # embedded token refused


def test_probe_is_zero_cost_and_gates_availability():
    env = dict(os.environ)
    assert st.probe({"probe": "true"}, env=env) is True
    assert st.probe({"probe": "false"}, env=env) is False
    assert st.probe({"probe": "definitely-not-a-command-xyz"}, env=env) is False
    assert st.probe({}, env=env) is True               # no probe declared


if __name__ == "__main__":
    fns = [v for k, v in sorted(vars(sys.modules["__main__"]).items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"test_adapters: {len(fns)} tests PASS")
