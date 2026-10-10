"""Duplicate and delivery controls (guide section 10)."""

from grok_desk.delivery import DeliveryLedger, event_identity, period_identity
from grok_desk.enums import DeliveryStatus


def test_event_identity_is_stable():
    a = event_identity("RELIANCE", "board meeting outcome")
    b = event_identity("reliance", "Board Meeting Outcome")
    assert a == b


def test_duplicate_event_suppressed():
    led = DeliveryLedger()
    evt = event_identity("TCS", "results")
    assert led.record_event(evt) is True
    assert led.record_event(evt) is False
    assert led.is_duplicate_event(evt) is True


def test_delivery_is_idempotent():
    led = DeliveryLedger()
    period = period_identity("Market News Research Lead", "req1")
    run = led.open_run("Market News Research Lead", period)
    led.mark_pending(run)
    r1 = led.deliver(run, recipient_known=True)
    assert r1 is not None
    assert run.status == DeliveryStatus.DELIVERED
    # A second deliver of the same period is suppressed (no new receipt).
    run2 = led.open_run("Market News Research Lead", period)
    led.mark_pending(run2)
    r2 = led.deliver(run2, recipient_known=True)
    assert r2 is None


def test_delivery_waits_when_recipient_unknown():
    led = DeliveryLedger()
    period = period_identity("wf", "p")
    run = led.open_run("wf", period)
    led.mark_pending(run)
    assert led.deliver(run, recipient_known=False) is None
    assert run.status == DeliveryStatus.PENDING_DELIVERY


def test_stale_run_cannot_overwrite_newer():
    led = DeliveryLedger()
    period = period_identity("wf", "p")
    old = led.open_run("wf", period)       # sequence 1
    newer = led.open_run("wf", period)     # sequence 2
    assert led.is_stale(old) is True
    assert led.is_stale(newer) is False
    led.mark_pending(old)
    # Stale run refuses to go pending.
    assert old.status != DeliveryStatus.PENDING_DELIVERY


def test_cursor_advances_only_after_delivery_and_acceptance():
    led = DeliveryLedger()
    period = period_identity("wf", "p")
    run = led.open_run("wf", period)
    led.mark_pending(run)
    # Not accepted yet -> no advance.
    led.deliver(run, recipient_known=True)
    assert led.advance_cursor(run) is False
    run.lead_accepted = True
    assert led.advance_cursor(run) is True
    assert led.cursor("wf") == period
