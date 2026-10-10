"""Skill behavior, date-gating, source outage, and identity-registry outage.

Covers guide sections 7 and 15: missing evidence stays visible, data is never
fabricated, identity is never guessed, and the fund-holdings routine is gated.
"""

from datetime import date

from grok_desk.company import IdentityRegistryUnavailable
from grok_desk.enums import CoverageState, SourceTier
from grok_desk.fixtures import build_registry, build_source_desk
from grok_desk.org import build_organization
from grok_desk.skills import SkillContext


def _ctx(symbols, window=7, run_date=None, outage_tiers=None, registry=None):
    org = build_organization()
    sp = org.specialists["Research Analyst"]
    return SkillContext(
        registry=registry or build_registry(),
        source_desk=build_source_desk(outage_tiers=outage_tiers or []),
        symbols=symbols,
        window_days=window,
        request_id="t",
        bot_identifier=sp.bot.identifier,
        bot_name=sp.bot.name,
        run_date=run_date,
    ), sp


def test_news_skill_finds_primary_facts():
    ctx, sp = _ctx(["RELIANCE"])
    h = sp.skill.run(ctx)
    assert h.coverage == CoverageState.COMPLETED_WITH_FINDINGS
    assert h.has_evidence()
    assert any(f.is_primary_backed() for f in h.facts)


def test_news_skill_no_findings_is_not_nothing_happened():
    # INFY has no fixtures but sources are reachable -> explicit "no material findings".
    ctx, sp = _ctx(["INFY"])
    h = sp.skill.run(ctx)
    assert h.coverage == CoverageState.COMPLETED_NO_FINDINGS
    assert not h.has_evidence()


def test_source_outage_reports_gap_not_fabrication():
    ctx, sp = _ctx(["RELIANCE"], outage_tiers=[SourceTier.EXCHANGE_FILINGS,
                                               SourceTier.INVESTOR_RELATIONS])
    h = sp.skill.run(ctx)
    # With its primary fixtures down, coverage stays incomplete and gaps are visible.
    assert h.coverage == CoverageState.INCOMPLETE
    assert any("unavailable" in u for u in h.unknowns)


def test_unknown_symbol_not_invented():
    ctx, sp = _ctx(["NOTREAL"])
    h = sp.skill.run(ctx)
    assert h.coverage == CoverageState.INCOMPLETE
    assert "symbol not in approved universe" in h.unknowns


def test_identity_registry_outage_reported():
    reg = build_registry(available=False)
    ctx, sp = _ctx(["RELIANCE"], registry=reg)
    h = sp.skill.run(ctx)
    assert h.coverage == CoverageState.INCOMPLETE
    assert "identity registry unavailable" in h.unknowns


def test_registry_resolve_raises_when_down():
    import pytest
    reg = build_registry(available=False)
    with pytest.raises(IdentityRegistryUnavailable):
        reg.resolve("RELIANCE")


def test_fund_holdings_gated_off_first_monday():
    org = build_organization()
    sp = org.specialists["Fund Holdings Research Analyst"]
    ctx = SkillContext(build_registry(), build_source_desk(), ["HDFCBANK"], 30, "t",
                       sp.bot.identifier, sp.bot.name, run_date=date(2026, 10, 8))  # Thursday
    h = sp.skill.run(ctx)
    assert h.coverage == CoverageState.NOT_DUE


def test_fund_holdings_runs_on_first_monday():
    org = build_organization()
    sp = org.specialists["Fund Holdings Research Analyst"]
    # 2026-10-05 is the first Monday of October 2026.
    ctx = SkillContext(build_registry(), build_source_desk(), ["HDFCBANK"], 30, "t",
                       sp.bot.identifier, sp.bot.name, run_date=date(2026, 10, 5))
    h = sp.skill.run(ctx)
    assert h.coverage in (CoverageState.COMPLETED_WITH_FINDINGS,
                          CoverageState.COMPLETED_NO_FINDINGS)
