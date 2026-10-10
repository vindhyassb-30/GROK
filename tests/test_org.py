"""Organization shape and acceptance-checklist tests (guide sections 2, 18)."""

from grok_desk.org import build_organization
from grok_desk.roster import LEAD_NAMES, SPECIALIST_NAMES


def test_roster_counts():
    org = build_organization()
    v = org.verify()
    assert v["ok"] is True
    assert v["bot_count"] == 23
    assert v["lead_count"] == 5
    assert v["specialist_count"] == 17
    assert v["group_count"] == 6


def test_lead_and_specialist_counts_const():
    assert len(LEAD_NAMES) == 5
    assert len(SPECIALIST_NAMES) == 17


def test_every_specialist_has_one_lead():
    org = build_organization()
    for name, sp in org.specialists.items():
        assert sp.bot.profile.reports_to in org.leads, name


def test_unique_bot_identifiers():
    org = build_organization()
    ids = [b.identifier for b in org.bots.values()]
    assert len(set(ids)) == len(ids)


def test_routines_start_paused():
    org = build_organization()
    assert len(org.scheduler.active_routines()) == 0
    assert len(org.scheduler.paused_routines()) == 13
