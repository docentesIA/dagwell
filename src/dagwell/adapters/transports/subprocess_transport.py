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


def build_argv(invocation: str, mission: str) -> list[str]:
    """Template -> argv. The template is split first, the mission is then
    substituted as a single argument — mission content never reaches a
    shell and cannot add, split, or reorder arguments."""
    argv = shlex.split(invocation)
    if "{mission}" not in argv:
        raise TransportError(
            "invocation template must carry {mission} as its own argument — "
            "embedding it inside another token would splice mission text "
            "into that argument")
    return [mission if token == "{mission}" else token for token in argv]


def execute(binding: dict, mission: str, out_path: str, *, env: dict) -> dict:
    """Run one attempt. Returns transport facts only."""
    argv = build_argv(binding["invocation"], mission)
    child_env = {**env, "OUT": out_path}
    started = time.monotonic()
    proc = subprocess.Popen(argv, env=child_env)
    timed_out = False
    try:
        proc.wait(timeout=binding["timeout_seconds"])
    except subprocess.TimeoutExpired:
        timed_out = True
        for sig, grace in ((signal.SIGINT, GRACE_SECONDS),
                           (signal.SIGTERM, GRACE_SECONDS)):
            proc.send_signal(sig)
            try:
                proc.wait(timeout=grace)
                break
            except subprocess.TimeoutExpired:
                continue
        else:
            proc.kill()
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
