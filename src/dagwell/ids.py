"""Identifier generation: UUIDv7 run_id / event_id (ADR-0002, ACCEPTED).

`seq` — not run_id — is the authoritative ordering inside a run (contract §9);
run_id time-sortability is operational convenience only. run_id is opaque and
never derived from graph/input content.
"""

import os
import time
import uuid

# Reserved for synthetic legacy runs (contract §2); generated ids can never
# collide with it: the hex alphabet has no letter "l".
LEGACY_PREFIX = "legacy-"


def is_legacy(run_id) -> bool:
    """Whether run_id lives in the reserved synthetic-legacy namespace (§2).

    `legacy-<operation>` is the contract's acknowledged exception to run_id
    opacity: an aggregation label for indistinguishable V1 history, never an
    execution identity.
    """
    return isinstance(run_id, str) and run_id.startswith(LEGACY_PREFIX)


def uuid7() -> uuid.UUID:
    """RFC 9562 UUIDv7. Uses the stdlib generator when available (Python 3.14+)."""
    if hasattr(uuid, "uuid7"):
        return uuid.uuid7()
    unix_ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")  # 80 random bits
    value = (
        (unix_ms & ((1 << 48) - 1)) << 80
        | 0x7 << 76                    # version 7
        | (rand >> 68) << 64           # rand_a: top 12 of the 80 random bits
        | 0b10 << 62                   # RFC 4122 variant
        | (rand & ((1 << 62) - 1))     # rand_b: low 62 of the 80 random bits
    )
    return uuid.UUID(int=value)


def new_run_id() -> str:
    """Opaque run identity: canonical lowercase hyphenated UUIDv7 text."""
    return str(uuid7())


def new_event_id() -> str:
    """Globally unique event identity (contract §9)."""
    return str(uuid7())
