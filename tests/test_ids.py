"""UUIDv7 run_id/event_id (ADR-0002). Zero-cost."""

import re
import time
import uuid

from dagwell import ids

UUID7_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def test_canonical_lowercase_hyphenated_uuid7_form():
    for _ in range(50):
        assert UUID7_RE.match(ids.new_run_id())
        assert UUID7_RE.match(ids.new_event_id())


def test_version_and_variant_bits():
    u = ids.uuid7()
    assert u.version == 7
    assert u.variant == uuid.RFC_4122


def test_embedded_timestamp_is_roughly_now():
    ms = ids.uuid7().int >> 80
    now_ms = time.time_ns() // 1_000_000
    assert abs(now_ms - ms) < 10_000


def test_uniqueness():
    batch = {ids.new_run_id() for _ in range(2000)}
    assert len(batch) == 2000


def test_legacy_namespace_never_collides():
    # hex alphabet contains no "l": generated ids can never enter legacy-*
    for _ in range(100):
        rid = ids.new_run_id()
        assert not rid.startswith(ids.LEGACY_PREFIX)
        assert set(rid) <= set("0123456789abcdef-")


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(vars(sys.modules["__main__"]).items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"test_ids: {len(fns)} tests PASS")
