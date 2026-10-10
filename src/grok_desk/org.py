"""Organization builder (guide sections 3, 6, 8, 12).

Assembles the full research desk from the roster: 23 Bots with saved profiles,
six Groups, a Router enforcing the reporting chain, and the production routine
schedule (created paused). Also exposes a verify() for the acceptance checklist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from typing import Dict, List

from .agents import Chief, Lead, Specialist
from .enums import Department, SourceTier
from .groups import Group, Router
from .profile import Bot, BotProfile
from .roster import (
    CHIEF,
    EQUITY_LEAD,
    INDUSTRY_GEO_LEAD,
    LEAD_NAMES,
    MARKET_ACTIVITY_LEAD,
    MARKET_NEWS_LEAD,
    REVIEW_LEAD,
    ROSTER,
    RoleSpec,
    role_specific_forbidden,
    specialists_for_lead,
)
from .routines import Routine, Scheduler, first_monday, fridays, weekdays
from .skills import FundHoldingsSkill, NewsResearchSkill, Skill, SkillSpec

MARKET_SCOPE = "NSE and BSE listed Indian equities"

DEFAULT_PREFERRED_SOURCES = [
    SourceTier.COMPANY_IDENTITY_REGISTRY,
    SourceTier.EXCHANGE_FILINGS,
    SourceTier.INVESTOR_RELATIONS,
    SourceTier.REGULATOR,
    SourceTier.GOVERNMENT,
]


def _make_profile(role: RoleSpec) -> BotProfile:
    forbidden = list(role_specific_forbidden(role.role_name))
    if role.is_chief:
        handoff_dest = None
        forbidden += [
            "perform every raw search itself",
            "contact all specialists for every question",
        ]
    elif role.is_lead:
        handoff_dest = CHIEF
        forbidden += ["redo the specialist's full analysis", "bypass its specialists"]
    else:
        handoff_dest = role.reports_to
        forbidden += ["contact the Chief directly for normal work"]

    return BotProfile(
        role_name=role.role_name,
        department=role.department,
        market_scope=MARKET_SCOPE,
        reports_to=role.reports_to,
        tasks_forbidden=forbidden,
        preferred_sources=list(DEFAULT_PREFERRED_SOURCES),
        handoff_destination=handoff_dest,
        is_coordinator=role.is_lead or role.is_chief,
    )


def _make_bot(role: RoleSpec) -> Bot:
    bot = Bot(profile=_make_profile(role), icon_color=role.icon_color)
    bot.verified = True  # simulate the save-and-reopen read-back
    return bot


def _skill_for(role: RoleSpec) -> Skill:
    """Attach a concrete Skill to a specialist (news skill as the default method)."""
    spec = SkillSpec(
        name=f"{role.role_name} Skill",
        when_to_use=f"When {role.department.value} research is requested for the approved universe.",
        required_inputs=["symbols", "time_window", "request_id"],
        approved_universe=MARKET_SCOPE,
        source_priority=list(DEFAULT_PREFERRED_SOURCES),
        time_window_rules="Separate event/publication/retrieval/data-as-of times.",
        retrieval_retry_limits="Max 1 retry per source tier.",
        evidence_thresholds="At least one primary-source-backed fact for high confidence.",
        calculations_validation="Use validated figures; no prose arithmetic.",
        status_labels=[],
        handoff_format="structured Handoff (guide section 9)",
        delivery_destination=role.reports_to or CHIEF,
        duplicate_prevention="Idempotent via DeliveryLedger run/period identities.",
        completion_failure="Complete on coverage; fail-retryable on source outage.",
        non_goals=["No trades", "No guaranteed outcomes", "No fabricated data"],
    )
    if role.role_name == "Fund Holdings Research Analyst":
        return FundHoldingsSkill(spec)
    return NewsResearchSkill(spec)


@dataclass
class Organization:
    chief: Chief
    leads: Dict[str, Lead]
    specialists: Dict[str, Specialist]
    groups: Dict[str, Group]
    router: Router
    scheduler: Scheduler
    bots: Dict[str, Bot] = field(default_factory=dict)

    # --- acceptance helpers (guide section 18) --------------------------
    def verify(self) -> Dict[str, object]:
        issues: List[str] = []
        if len(self.leads) != 5:
            issues.append(f"expected 5 Leads, found {len(self.leads)}")
        if len(self.specialists) != 17:
            issues.append(f"expected 17 specialists, found {len(self.specialists)}")
        if len(self.groups) != 6:
            issues.append(f"expected 6 Groups, found {len(self.groups)}")
        for name, sp in self.specialists.items():
            if sp.bot.profile.reports_to not in self.leads:
                issues.append(f"specialist '{name}' has no valid Lead")
        ids = [b.identifier for b in self.bots.values()]
        if len(set(ids)) != len(ids):
            issues.append("duplicate bot identifiers detected")
        return {
            "ok": not issues,
            "bot_count": len(self.bots),
            "lead_count": len(self.leads),
            "specialist_count": len(self.specialists),
            "group_count": len(self.groups),
            "active_routines": len(self.scheduler.active_routines()),
            "paused_routines": len(self.scheduler.paused_routines()),
            "issues": issues,
        }


# --- production schedule (guide section 12) -----------------------------
def _build_schedule(scheduler: Scheduler, universe: List[str]) -> None:
    def add(name, owner, skill, hh, mm, cadence, dest):
        scheduler.add(
            Routine(
                name=name,
                owner_name=owner,
                skill_name=skill,
                at=time(hh, mm),
                cadence=cadence,
                approved_universe=universe,
                destination_lead=dest,
            )
        )

    add("Pre-Earnings defence calendar", "Pre-Earnings Intelligence Analyst",
        "Pre-Earnings Intelligence Analyst Skill", 8, 0, weekdays, EQUITY_LEAD)
    add("Industry structure morning", "Industry Research Analyst",
        "Industry Research Analyst Skill", 8, 15, weekdays, INDUSTRY_GEO_LEAD)
    add("Geopolitical transmission morning", "Geopolitical Risk Analyst",
        "Geopolitical Risk Analyst Skill", 8, 30, weekdays, INDUSTRY_GEO_LEAD)
    add("Pre-market Lead synthesis", CHIEF,
        "Chief Pre-market Synthesis", 9, 0, weekdays, CHIEF)
    add("Primary-source news", "Research Analyst",
        "Research Analyst Skill", 12, 0, weekdays, MARKET_NEWS_LEAD)
    add("Midday published-narrative check", "Sentiment Analyst",
        "Sentiment Analyst Midday Skill", 12, 30, weekdays, MARKET_NEWS_LEAD)
    add("Closing published-narrative check", "Sentiment Analyst",
        "Sentiment Analyst Closing Skill", 15, 35, weekdays, MARKET_NEWS_LEAD)
    add("End-of-day volume triage", "Market Volume Intelligence Analyst",
        "Market Volume Intelligence Analyst Skill", 18, 0, weekdays, MARKET_ACTIVITY_LEAD)
    add("Insider-disclosure review", "Insider Activity Analyst",
        "Insider Activity Analyst Skill", 18, 10, weekdays, MARKET_ACTIVITY_LEAD)
    add("Fundamental pair review", "Fundamental Research Analyst",
        "Fundamental Research Analyst Skill", 18, 30, fridays, EQUITY_LEAD)
    add("Fund-holdings review", "Fund Holdings Research Analyst",
        "Fund Holdings Research Analyst Skill", 18, 30, first_monday, MARKET_ACTIVITY_LEAD)
    add("Financial-forensics pair review", "Financial Forensics Analyst",
        "Financial Forensics Analyst Skill", 18, 50, fridays, EQUITY_LEAD)
    add("Evening Lead synthesis", CHIEF,
        "Chief Evening Synthesis", 19, 15, weekdays, CHIEF)


def build_organization(universe: List[str] = None) -> Organization:
    """Construct the entire research desk, with routines created PAUSED."""
    universe = universe or ["RELIANCE", "TCS", "INFY", "HDFCBANK"]

    bots: Dict[str, Bot] = {}
    for role in ROSTER:
        bots[role.role_name] = _make_bot(role)

    chief_bot = bots[CHIEF]
    chief = Chief(chief_bot, lead_names=LEAD_NAMES)

    leads: Dict[str, Lead] = {}
    for ln in LEAD_NAMES:
        leads[ln] = Lead(bots[ln], authorised_specialists=specialists_for_lead(ln))

    specialists: Dict[str, Specialist] = {}
    for role in ROSTER:
        if role.is_lead or role.is_chief:
            continue
        specialists[role.role_name] = Specialist(bots[role.role_name], _skill_for(role))

    # Router wiring
    router = Router(chief)
    for lead in leads.values():
        router.register_lead(lead)
    for name, sp in specialists.items():
        router.register_specialist(sp, sp.bot.profile.reports_to)

    # Groups (guide section 8): one Chief group + five department desks.
    groups: Dict[str, Group] = {}
    chief_group = Group("Chief Intelligence Group", lead_name=CHIEF, is_chief_group=True)
    for ln in LEAD_NAMES:
        chief_group.add_member(ln)
    groups[chief_group.name] = chief_group

    desk_names = {
        MARKET_NEWS_LEAD: "Market News Research Desk",
        EQUITY_LEAD: "Equity Research Desk",
        INDUSTRY_GEO_LEAD: "Industry & Geopolitical Desk",
        MARKET_ACTIVITY_LEAD: "Market Activity & Ownership Desk",
        REVIEW_LEAD: "Independent Research Review Desk",
    }
    for ln, gname in desk_names.items():
        g = Group(gname, lead_name=ln)
        for sp_name in specialists_for_lead(ln):
            g.add_member(sp_name)
        groups[gname] = g

    # Record group membership on bots (roster bookkeeping)
    for gname, g in groups.items():
        bots[g.lead_name].group_memberships.append(gname)
        for m in g.member_names:
            bots[m].group_memberships.append(gname)

    scheduler = Scheduler()
    _build_schedule(scheduler, universe)

    return Organization(
        chief=chief,
        leads=leads,
        specialists=specialists,
        groups=groups,
        router=router,
        scheduler=scheduler,
        bots=bots,
    )
