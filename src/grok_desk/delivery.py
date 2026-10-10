"""Duplicate and delivery controls (guide section 10).

Scheduled systems can wake twice, retry after an interruption, or lose track of
a delivery. These controls give every recurring workflow stable identities and
idempotent delivery:

- event identity: stable key for the underlying event
- reporting-period identity: which window the work covers
- run identity: a unique id for one execution
- delivery receipt: proof a specific report reached a recipient
- status: open / pending / delivered / partial / failed
- an older run never overwrites a newer run
- only the exact pending report is resent
- delivery waits when recipient status is unknown
- an already-delivered duplicate is suppressed
- the research window advances only after success AND Lead acceptance
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Optional

from .enums import DeliveryStatus


def event_identity(symbol: str, event_key: str) -> str:
    """Stable identity for a specific event (idempotent across retries)."""
    raw = f"{symbol.upper()}::{event_key.strip().lower()}"
    return "evt_" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def period_identity(workflow: str, period_label: str) -> str:
    """Stable identity for a reporting period of a workflow."""
    raw = f"{workflow}::{period_label}"
    return "per_" + hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class RunRecord:
    """One execution of a workflow for a given reporting period."""

    workflow: str
    period_id: str
    run_id: str = field(default_factory=lambda: f"run_{uuid.uuid4().hex[:12]}")
    sequence: int = 0  # monotonic; higher = newer
    status: DeliveryStatus = DeliveryStatus.OPEN
    lead_accepted: bool = False
    delivery_receipt: Optional[str] = None


class DeliveryLedger:
    """Idempotent ledger of runs, receipts, and per-workflow research cursors."""

    def __init__(self):
        self._runs: Dict[str, RunRecord] = {}            # run_id -> record
        self._latest_seq: Dict[str, int] = {}            # period_id -> highest sequence
        self._receipts: Dict[str, str] = {}              # period_id -> receipt id
        self._cursor: Dict[str, str] = {}                # workflow -> last completed period
        self._seen_events: set = set()                   # suppressed duplicate events

    # --- events ---------------------------------------------------------
    def is_duplicate_event(self, evt_id: str) -> bool:
        return evt_id in self._seen_events

    def record_event(self, evt_id: str) -> bool:
        """Return True if newly recorded, False if it was a suppressed duplicate."""
        if evt_id in self._seen_events:
            return False
        self._seen_events.add(evt_id)
        return True

    # --- runs -----------------------------------------------------------
    def open_run(self, workflow: str, period_id: str) -> RunRecord:
        seq = self._latest_seq.get(period_id, 0) + 1
        rec = RunRecord(workflow=workflow, period_id=period_id, sequence=seq)
        self._latest_seq[period_id] = seq
        self._runs[rec.run_id] = rec
        return rec

    def is_stale(self, rec: RunRecord) -> bool:
        """An older run must not change a newer run."""
        return rec.sequence < self._latest_seq.get(rec.period_id, 0)

    def mark_pending(self, rec: RunRecord) -> None:
        if self.is_stale(rec):
            return  # refuse: a newer run exists
        rec.status = DeliveryStatus.PENDING_DELIVERY

    def deliver(self, rec: RunRecord, recipient_known: bool = True) -> Optional[str]:
        """Deliver only the exact pending report; suppress duplicates; wait if unknown.

        Returns the delivery receipt id, or None if delivery was withheld.
        """
        if self.is_stale(rec):
            return None  # never let an old run overwrite a newer one
        # Suppress an already-delivered period.
        if rec.period_id in self._receipts:
            rec.status = DeliveryStatus.DELIVERED
            rec.delivery_receipt = self._receipts[rec.period_id]
            return None  # duplicate suppressed
        if not recipient_known:
            # Wait when recipient status is unknown.
            return None
        if rec.status != DeliveryStatus.PENDING_DELIVERY:
            return None  # only the exact pending report is sent
        receipt = f"rcpt_{uuid.uuid4().hex[:12]}"
        rec.delivery_receipt = receipt
        rec.status = DeliveryStatus.DELIVERED
        self._receipts[rec.period_id] = receipt
        return receipt

    # --- cursor ---------------------------------------------------------
    def advance_cursor(self, rec: RunRecord) -> bool:
        """Advance the research window ONLY after success AND Lead acceptance."""
        if rec.status != DeliveryStatus.DELIVERED or not rec.lead_accepted:
            return False
        self._cursor[rec.workflow] = rec.period_id
        return True

    def cursor(self, workflow: str) -> Optional[str]:
        return self._cursor.get(workflow)
