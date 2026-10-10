"""Routine state machine, duplicate-routine guard, and end-to-end pipeline."""

from datetime import date, time

import pytest

from grok_desk.enums import CoverageState, RoutineState
from grok_desk.fixtures import build_registry, build_source_desk
from grok_desk.org import build_organization
from grok_desk.pipeline import Desk
from grok_desk.routines import Routine, Scheduler, weekdays


def test_routine_activation_lifecycle():
    org = build_organization()
    r = org.scheduler.get("Primary-source news")
    assert r.state == RoutineState.PAUSED
    r.activate()
    assert r.state == RoutineState.ACTIVE
    rb = r.readback()
    assert rb["timezone"] == "Asia/Kolkata"
    assert rb["state"] == "active"


def test_scheduler_rejects_duplicate_purpose_and_time():
    sched = Scheduler()
    base = dict(skill_name="S", at=time(12, 0), cadence=weekdays,
                approved_universe=["RELIANCE"], destination_lead="L", owner_name="A")
    sched.add(Routine(name="first", **base))
    with pytest.raises(ValueError):
        sched.add(Routine(name="second", **base))


def test_retired_routine_cannot_activate():
    org = build_organization()
    r = org.scheduler.get("Evening Lead synthesis")
    r.retire()
    with pytest.raises(ValueError):
        r.activate()


def test_due_excludes_paused_by_default():
    org = build_organization()
    monday = date(2026, 10, 5)
    assert org.scheduler.due(monday) == []  # all paused
    assert len(org.scheduler.due(monday, include_paused=True)) > 0


def test_pipeline_end_to_end_single_department():
    org = build_organization()
    desk = Desk(org, build_registry(), build_source_desk())
    result = desk.ask_chief(
        "Any material news on Reliance?",
        symbols=["RELIANCE"],
        departments=["Market News Research Lead"],
    )
    b = result.briefing
    assert b["overall_coverage"] == CoverageState.COMPLETED_WITH_FINDINGS
    assert "RELIANCE board meeting outcome filed with NSE" in b["findings"]
    assert len(result.receipts) == 1
    assert "No trades" in b["disclaimer"]


def test_pipeline_rejects_non_department():
    org = build_organization()
    desk = Desk(org, build_registry(), build_source_desk())
    from grok_desk.agents import BoundaryViolation
    with pytest.raises(BoundaryViolation):
        desk.ask_chief("x", symbols=["TCS"], departments=["Research Analyst"])


def test_findings_are_deduplicated_across_specialists():
    org = build_organization()
    desk = Desk(org, build_registry(), build_source_desk())
    report = desk.run_department("Market News Research Lead", ["RELIANCE"], 7, "r")
    # Five specialists all run the same news skill; findings must be deduped.
    assert len(report.reconciled_findings) == len(set(report.reconciled_findings))
