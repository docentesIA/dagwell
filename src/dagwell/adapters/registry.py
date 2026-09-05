"""Binding registry — platform bindings as data (spec §3.2).

The registry maps binding_id -> transport + invocation + models, each model
carrying its family, its served difficulty tiers, and an operator-declared
relative_cost. Validation is fail-closed and happens before any selection:
a malformed registry never reaches a dispatch. The registry file's content
digest (scheme c1) is what dispatch records as provenance — the ledger
records what WAS used; the registry proposes what MAY be used.
"""

import json
import math
import re
import shlex

from dagwell import canonical
from dagwell.graph import CAPABILITY_TIERS
from dagwell.adapters.transports.subprocess_transport import TransportError, build_argv

# Closed set of transport NAMES (spec §6.1). Only subprocess is implemented;
# the others are reserved and refuse at load until their gated extensions
# exist — naming them here prevents ad-hoc strings, it authorizes nothing.
TRANSPORTS = frozenset({"subprocess", "http", "sdk", "mcp", "a2a"})
IMPLEMENTED_TRANSPORTS = frozenset({"subprocess"})

_FAMILY_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)+$")  # <vendor>-<family>


class RegistryValidationError(Exception):
    pass


def _require_str(obj: dict, field: str, where: str) -> str:
    value = obj.get(field)
    if not isinstance(value, str) or not value:
        raise RegistryValidationError(f"{where}: non-empty {field} is required")
    return value


def load_registry(text: bytes | str) -> dict:
    """Parse + validate + fix provenance. Fail closed on any violation."""
    try:
        canonical_text = canonical.canonicalize_text(text)
    except UnicodeDecodeError as exc:
        raise RegistryValidationError(
            f"registry is not valid UTF-8: {exc}") from exc
    try:
        data = json.loads(canonical_text)
    except json.JSONDecodeError as exc:
        raise RegistryValidationError(
            f"registry is not valid JSON: {exc}") from exc
    validate_registry(data)
    return {
        "registry_digest": canonical.content_digest(canonical_text),
        "bindings": {b["binding_id"]: b for b in data["bindings"]},
    }


def validate_registry(data) -> None:
    if not isinstance(data, dict):
        raise RegistryValidationError("registry must be an object")
    bindings = data.get("bindings")
    if not isinstance(bindings, list) or not bindings:
        raise RegistryValidationError("bindings must be a non-empty list")
    seen = set()
    for binding in bindings:
        if not isinstance(binding, dict):
            raise RegistryValidationError("every binding must be an object")
        bid = _require_str(binding, "binding_id", "binding")
        if bid in seen:
            raise RegistryValidationError(f"duplicate binding_id: {bid}")
        seen.add(bid)
        _validate_binding(binding)


def _validate_binding(binding: dict) -> None:
    bid = binding["binding_id"]
    transport = _require_str(binding, "transport", f"binding {bid}")
    if transport not in TRANSPORTS:
        raise RegistryValidationError(
            f"binding {bid}: unknown transport {transport!r} "
            f"(spec §6.1: {sorted(TRANSPORTS)})")
    if transport not in IMPLEMENTED_TRANSPORTS:
        raise RegistryValidationError(
            f"binding {bid}: transport {transport!r} is reserved — usable only "
            "through its own gated extension of the spec (§6.1)")
    _require_str(binding, "platform", f"binding {bid}")

    invocation = _require_str(binding, "invocation", f"binding {bid}")
    try:
        build_argv(invocation, "validation-only")
    except TransportError as exc:
        raise RegistryValidationError(
            f"binding {bid}: {exc}") from exc
    if "probe" in binding:
        probe = _require_str(binding, "probe", f"binding {bid}")
        try:
            if not shlex.split(probe) or "\x00" in probe:
                raise ValueError("empty or invalid probe")
        except ValueError as exc:
            raise RegistryValidationError(f"binding {bid}: invalid probe command") from exc

    # Spec §6.2: timeout is MANDATORY for subprocess bindings — no invented
    # universal default, fail-closed on absence.
    timeout = binding.get("timeout_seconds")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) \
            or (isinstance(timeout, float) and not math.isfinite(timeout)) or timeout <= 0:
        raise RegistryValidationError(
            f"binding {bid}: timeout_seconds must be a positive number "
            "(mandatory, spec §6.2)")

    models = binding.get("models")
    if not isinstance(models, list) or not models:
        raise RegistryValidationError(
            f"binding {bid}: models must be a non-empty list")
    model_ids = set()
    for model in models:
        if not isinstance(model, dict):
            raise RegistryValidationError(
                f"binding {bid}: every model must be an object")
        mid = _require_str(model, "model_id", f"binding {bid} model")
        if mid in model_ids:
            raise RegistryValidationError(
                f"binding {bid}: duplicate model_id {mid}")
        model_ids.add(mid)
        family = _require_str(model, "family", f"binding {bid} model {mid}")
        if not _FAMILY_RE.match(family):
            raise RegistryValidationError(
                f"binding {bid} model {mid}: family must be lowercase "
                f"<vendor>-<family> (spec §5), got {family!r}")
        tiers = model.get("tiers")
        if not isinstance(tiers, list) or not tiers:
            raise RegistryValidationError(
                f"binding {bid} model {mid}: tiers must be a non-empty list")
        for tier in tiers:
            if tier not in CAPABILITY_TIERS:
                raise RegistryValidationError(
                    f"binding {bid} model {mid}: unknown tier {tier!r} "
                    f"({list(CAPABILITY_TIERS)})")
        cost = model.get("relative_cost")
        if not isinstance(cost, (int, float)) or isinstance(cost, bool) \
                or (isinstance(cost, float) and not math.isfinite(cost)) or cost <= 0:
            raise RegistryValidationError(
                f"binding {bid} model {mid}: relative_cost must be a "
                "positive number")
