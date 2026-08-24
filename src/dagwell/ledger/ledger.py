"""Append-only local ledger: one JSON event per line, flock-serialized.

Phase 2 assumptions (Architecture & Migration Plan §8): single local process;
`flock` is the serialization mechanism the contract contracts (§9). seq is
writer-assigned, contiguous from FIRST_SEQ per run. Gap DETECTION exists
(`sequence_gaps`); gap RECONCILIATION is §13.16 and is deliberately absent —
a run with any seq anomaly refuses further appends (mutable action blocked,
contract P3/I27), while diagnostic reading stays possible.
"""

import fcntl
import json
import os
from pathlib import Path

from dagwell.ledger import events as ev
from dagwell.ledger import preconditions

# ponytail: full-file scan per append; add an index when ledgers grow.


class Ledger:
    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)

    # -- reading -----------------------------------------------------------

    def events(self) -> list[dict]:
        """All events, integrity-checked for reading.

        Per-run seq collision/regression are hard errors — the fold refuses
        to compute over them (contract I20, fail closed). A duplicate
        event_id is tolerated on read (fold conduct: first by seq is
        authoritative, later ones are ignored and flagged) but always refused
        at write. A seq gap is tolerated on read — diagnostic reading stays
        possible (contract P3) — and surfaces in sequence_gaps().
        """
        if not self.path.exists():
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                raw = f.read()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        parsed = self._parse(raw)
        self._check_integrity(parsed)
        return parsed

    def run(self, run_id: str) -> list[dict]:
        return [e for e in self.events() if e.get("run_id") == run_id]

    def sequence_gaps(self) -> dict[str, list[int]]:
        """Missing seq values per run — detection only (reconciliation: §13.16)."""
        gaps: dict[str, list[int]] = {}
        for run_id, seqs in self._seqs_by_run(self.events()).items():
            missing = sorted(set(range(ev.FIRST_SEQ, max(seqs) + 1)) - set(seqs))
            if missing:
                gaps[run_id] = missing
        return gaps

    def global_duplicate_event_ids(self) -> list[str]:
        """Duplicate event_id detection ACROSS runs (audit hardening 2) —
        detection/signal only; writes always refuse duplicates."""
        seen, dups = set(), []
        for e in self.events():
            eid = e.get("event_id")
            if eid in seen and eid not in dups:
                dups.append(eid)
            seen.add(eid)
        return dups

    # -- writing -----------------------------------------------------------

    def append(self, event: dict) -> dict:
        """Append one event; returns it with its assigned seq.

        Hard validations before any byte is written (contract §9, I20, I25):
        complete envelope; canonical English event_type; event_id uniqueness;
        run_created is the first and only founding event of its run; a
        caller-set seq must equal the next contiguous value (collision,
        regression and would-be gaps refused at write); a run whose recorded
        seqs are anomalous refuses appends entirely (I27).
        """
        with open(self.path, "a+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.seek(0)
                existing = self._parse(f.read())
                self._check_integrity(existing)
                seen_ids = {e.get("event_id") for e in existing}
                if len(seen_ids) != len(existing):
                    raise ev.LedgerIntegrityError(
                        "duplicate event_id in ledger — appends refused")

                run_id = event.get("run_id")
                if not isinstance(run_id, str) or not run_id:
                    raise ev.EventValidationError("run_id is required in every event")

                run_seqs = self._seqs_by_run(existing).get(run_id, [])
                if run_seqs and sorted(run_seqs) != list(
                        range(ev.FIRST_SEQ, max(run_seqs) + 1)):
                    raise ev.LedgerIntegrityError(
                        f"run {run_id}: unresolved seq anomaly — "
                        "mutable actions blocked (I27)")

                next_seq = (max(run_seqs) + 1) if run_seqs else ev.FIRST_SEQ
                if "seq" in event and event["seq"] != next_seq:
                    raise ev.LedgerIntegrityError(
                        f"run {run_id}: seq {event['seq']!r} refused — "
                        f"next expected is {next_seq}")
                event = {**event, "seq": next_seq}

                if event.get("event_type") == "run_created":
                    if run_seqs:
                        raise ev.LedgerIntegrityError(
                            f"run {run_id}: second run_created refused — one "
                            "authoritative run_created per run (I25)")
                elif not run_seqs:
                    raise ev.EventValidationError(
                        f"run {run_id}: first event of a run must be "
                        "run_created (contract §2)")

                ev.validate_event(event)

                run_events = [e for e in existing if e.get("run_id") == run_id]
                existing_authoritative = preconditions.check(event, run_events)
                if existing_authoritative is not None:
                    return existing_authoritative  # identical duplicate: no-op

                if event["event_id"] in seen_ids:
                    raise ev.LedgerIntegrityError(
                        f"duplicate event_id: {event['event_id']}")

                f.write(json.dumps(event, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        return event

    # -- internal ----------------------------------------------------------

    @staticmethod
    def _parse(raw: str) -> list[dict]:
        parsed = []
        for n, line in enumerate(raw.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                parsed.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ev.LedgerIntegrityError(
                    f"line {n}: not valid JSON: {exc}") from exc
        return parsed

    @staticmethod
    def _seqs_by_run(events_list: list[dict]) -> dict[str, list[int]]:
        by_run: dict[str, list[int]] = {}
        for e in events_list:
            by_run.setdefault(e.get("run_id"), []).append(e.get("seq"))
        return by_run

    @staticmethod
    def _check_integrity(events_list: list[dict]) -> None:
        for run_id, seqs in Ledger._seqs_by_run(events_list).items():
            if len(seqs) != len(set(seqs)):
                raise ev.LedgerIntegrityError(f"run {run_id}: seq collision")
            if seqs != sorted(seqs):
                raise ev.LedgerIntegrityError(f"run {run_id}: seq regression")
