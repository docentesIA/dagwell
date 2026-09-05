"""The subprocess transport — the one v1 transport (spec §6.2).

Spawn, wait, reap: synchronous, one process per dispatched attempt. $OUT is
exported into the attempt directory; credentials are inherited from the
operator's environment by NAME only — no value ever passes through here as
data. On timeout, the cancellation ladder of §6.3: SIGINT -> grace ->
SIGTERM -> grace -> SIGKILL.

Everything returned is a TRANSPORT FACT — exit codes, durations, timeout
flags. No verdict, no family, no interpretation: translating any of this
into approved/rejected is exactly what no adapter component may do
(AGENTS.md §8, I6).
"""

import os
from pathlib import Path
import shlex
import signal
import subprocess
import time

# ponytail: fixed grace steps; §13.14 (grace mechanics) is open, so this is a
# runtime choice, not contract — make it configurable when a real workload
# needs a longer goodbye.
GRACE_SECONDS = 10.0


class TransportError(Exception):
    pass


def build_argv(invocation: str, mission: str, *, model_id: str | None = None) -> list[str]:
    """Template -> argv. The template is split first, the mission is then
    substituted as a single argument — mission content never reaches a
    shell and cannot add, split, or reorder arguments."""
    try:
        argv = shlex.split(invocation)
    except ValueError as exc:
        raise TransportError("invalid invocation quoting") from exc
    markers = ("{mission}", "{model_id}")
    if (not argv or argv[0] in markers or "\x00" in invocation
            or "{mission}" not in argv
            or any(marker in token and token != marker
                   for token in argv for marker in markers)):
        raise TransportError(
            "invocation requires {mission}; {mission} and {model_id} must "
            "be whole arguments and cannot be the executable")
    if "{model_id}" in argv and (
            not isinstance(model_id, str) or not model_id or "\x00" in model_id):
        raise TransportError("{model_id} requires a non-empty selected model without NUL")
    replacements = {"{mission}": mission, "{model_id}": model_id}
    # One substitution pass: marker-looking content inside either value is data.
    resolved = [replacements.get(token, token) for token in argv]
    for argument in resolved:
        if not isinstance(argument, str) or '\x00' in argument:
            raise TransportError('invocation arguments must be strings without NUL')
        try:
            argument.encode('utf-8')
        except UnicodeEncodeError as exc:
            raise TransportError('invocation arguments must be valid UTF-8') from exc
    return resolved


def _signal_group(proc, sig):
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        pass


def _wait_group(proc, grace):
    deadline = time.monotonic() + grace
    while True:
        proc.poll()  # reap the leader independently of surviving descendants
        try:
            os.killpg(proc.pid, 0)
        except ProcessLookupError:
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.02, remaining))


def execute(binding: dict, mission: str, out_path: str, *, env: dict,
            model_id: str | None = None) -> dict:
    """Run one attempt. Returns transport facts only."""
    argv = build_argv(binding["invocation"], mission, model_id=model_id)
    output = Path(out_path).resolve()
    child_env = {**env, "OUT": str(output)}
    started = time.monotonic()
    try:
        proc = subprocess.Popen(argv, env=child_env, cwd=output.parent,
                                start_new_session=True)
    except OSError as exc:
        # No process existed, hence there is no exit status to invent. Avoid
        # exception messages: executable names and environment may be private.
        return {"transport": "subprocess", "exit_code": None,
                "duration_seconds": round(time.monotonic() - started, 3),
                "timed_out": False,
                "transport_error": {"type": type(exc).__name__, "errno": exc.errno}}
    timed_out = False
    try:
        proc.wait(timeout=binding["timeout_seconds"])
    except subprocess.TimeoutExpired:
        timed_out = True
        for sig, grace in ((signal.SIGINT, GRACE_SECONDS),
                           (signal.SIGTERM, GRACE_SECONDS)):
            _signal_group(proc, sig)
            if _wait_group(proc, grace):
                break
        else:
            _signal_group(proc, signal.SIGKILL)
        proc.wait()
    return {
        "transport": "subprocess",
        "exit_code": proc.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "timed_out": timed_out,
    }


def probe(binding: dict, *, env: dict, timeout_seconds: float = 10.0) -> bool:
    """Zero-cost liveness check (spec §6.6). A binding without a probe is
    treated as alive — declaring one is the operator's choice. A probe that
    spends quota is a forbidden probe; that property belongs to the probe
    command the operator declares, and this function cannot check it."""
    command = binding.get("probe")
    if not command:
        return True
    try:
        result = subprocess.run(shlex.split(command), env=env,
                                timeout=timeout_seconds,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0
