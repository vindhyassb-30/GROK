"""The organization roster (guide section 2).

Declares the 23 roles: one Chief, five Leads and seventeen specialists, each
mapped to its department, reporting Lead, and icon colour. This is the single
source of truth the builder uses to construct Bots, Groups and routing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .enums import Department

# Canonical role names (used verbatim; exact naming aids routing + auditing).
CHIEF = "Chief Market Intelligence Officer"

MARKET_NEWS_LEAD = "Market News Research Lead"
EQUITY_LEAD = "Equity Research Lead"
INDUSTRY_GEO_LEAD = "Head of Industry & Geopolitical Research"
MARKET_ACTIVITY_LEAD = "Head of Market Activity & Ownership Research"
REVIEW_LEAD = "Independent Research Review Lead"


@dataclass(frozen=True)
class RoleSpec:
    role_name: str
    department: Department
    reports_to: Optional[str]  # None only for the Chief
    icon_color: str
    is_lead: bool = False
    is_chief: bool = False
    event_driven: bool = False  # specialists invoked on events, no daily routine


# Icon/colour convention (guide section 4, step 3).
COLORS = {
    Department.CHIEF: "white",
    Department.MARKET_NEWS: "red",
    Department.EQUITY_RESEARCH: "blue",
    Department.INDUSTRY_GEO: "orange",
    Department.MARKET_ACTIVITY: "green",
    Department.INDEPENDENT_REVIEW: "grey",
}


def _c(dep: Department) -> str:
    return COLORS[dep]


ROSTER: List[RoleSpec] = [
    # --- Chief ---------------------------------------------------------
    RoleSpec(CHIEF, Department.CHIEF, None, _c(Department.CHIEF), is_chief=True),

    # --- Market News Research team -------------------------------------
    RoleSpec(MARKET_NEWS_LEAD, Department.MARKET_NEWS, CHIEF, _c(Department.MARKET_NEWS), is_lead=True),
    RoleSpec("Research Analyst", Department.MARKET_NEWS, MARKET_NEWS_LEAD, _c(Department.MARKET_NEWS)),
    RoleSpec("Sentiment Analyst", Department.MARKET_NEWS, MARKET_NEWS_LEAD, _c(Department.MARKET_NEWS)),
    RoleSpec("Stock Movement Analyst", Department.MARKET_NEWS, MARKET_NEWS_LEAD, _c(Department.MARKET_NEWS), event_driven=True),
    RoleSpec("News Credibility Analyst", Department.MARKET_NEWS, MARKET_NEWS_LEAD, _c(Department.MARKET_NEWS), event_driven=True),
    RoleSpec("Market Impact Analyst", Department.MARKET_NEWS, MARKET_NEWS_LEAD, _c(Department.MARKET_NEWS), event_driven=True),

    # --- Equity Research team ------------------------------------------
    RoleSpec(EQUITY_LEAD, Department.EQUITY_RESEARCH, CHIEF, _c(Department.EQUITY_RESEARCH), is_lead=True),
    RoleSpec("Fundamental Research Analyst", Department.EQUITY_RESEARCH, EQUITY_LEAD, _c(Department.EQUITY_RESEARCH)),
    RoleSpec("Financial Forensics Analyst", Department.EQUITY_RESEARCH, EQUITY_LEAD, _c(Department.EQUITY_RESEARCH)),
    RoleSpec("Pre-Earnings Intelligence Analyst", Department.EQUITY_RESEARCH, EQUITY_LEAD, _c(Department.EQUITY_RESEARCH)),

    # --- Industry and Geopolitical Research team -----------------------
    RoleSpec(INDUSTRY_GEO_LEAD, Department.INDUSTRY_GEO, CHIEF, _c(Department.INDUSTRY_GEO), is_lead=True),
    RoleSpec("Industry Research Analyst", Department.INDUSTRY_GEO, INDUSTRY_GEO_LEAD, _c(Department.INDUSTRY_GEO)),
    RoleSpec("Geopolitical Risk Analyst", Department.INDUSTRY_GEO, INDUSTRY_GEO_LEAD, _c(Department.INDUSTRY_GEO)),

    # --- Market Activity and Ownership team ----------------------------
    RoleSpec(MARKET_ACTIVITY_LEAD, Department.MARKET_ACTIVITY, CHIEF, _c(Department.MARKET_ACTIVITY), is_lead=True),
    RoleSpec("Market Volume Intelligence Analyst", Department.MARKET_ACTIVITY, MARKET_ACTIVITY_LEAD, _c(Department.MARKET_ACTIVITY)),
    RoleSpec("Insider Activity Analyst", Department.MARKET_ACTIVITY, MARKET_ACTIVITY_LEAD, _c(Department.MARKET_ACTIVITY)),
    RoleSpec("Fund Holdings Research Analyst", Department.MARKET_ACTIVITY, MARKET_ACTIVITY_LEAD, _c(Department.MARKET_ACTIVITY)),
    RoleSpec("Short-Seller Research Analyst", Department.MARKET_ACTIVITY, MARKET_ACTIVITY_LEAD, _c(Department.MARKET_ACTIVITY)),

    # --- Independent Research Review team ------------------------------
    RoleSpec(REVIEW_LEAD, Department.INDEPENDENT_REVIEW, CHIEF, _c(Department.INDEPENDENT_REVIEW), is_lead=True),
    RoleSpec("Bull Case Analyst", Department.INDEPENDENT_REVIEW, REVIEW_LEAD, _c(Department.INDEPENDENT_REVIEW), event_driven=True),
    RoleSpec("Bear Case Analyst", Department.INDEPENDENT_REVIEW, REVIEW_LEAD, _c(Department.INDEPENDENT_REVIEW), event_driven=True),
    RoleSpec("Research Validation Analyst", Department.INDEPENDENT_REVIEW, REVIEW_LEAD, _c(Department.INDEPENDENT_REVIEW), event_driven=True),
]


LEAD_NAMES = [r.role_name for r in ROSTER if r.is_lead]
SPECIALIST_NAMES = [r.role_name for r in ROSTER if not r.is_lead and not r.is_chief]


def specialists_for_lead(lead_name: str) -> List[str]:
    return [r.role_name for r in ROSTER if r.reports_to == lead_name and not r.is_lead]


def role_specific_forbidden(role_name: str) -> List[str]:
    """Per-role boundary rules tested in Stage B (guide section 13)."""
    rules = {
        "Sentiment Analyst": ["claim price causation", "represent social-media sentiment"],
        "Market Volume Intelligence Analyst": ["call unusual activity manipulation"],
        "Financial Forensics Analyst": ["label an anomaly fraud"],
        "Market Impact Analyst": ["turn a project milestone into a new order without evidence"],
    }
    return rules.get(role_name, [])
