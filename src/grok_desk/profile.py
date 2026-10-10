"""Bot identity and permanent profile (guide sections 4, 5, 6).

A profile is the durable job description: identity, scope, sources, evidence
rules, routing, and safety boundaries. Identity is stored here, not merely in
conversation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from .enums import Department, SourceTier

# Boundaries every Bot carries (guide section 5 "Safety boundaries").
GLOBAL_SAFETY_BOUNDARIES: tuple = (
    "No fabricated figures or company identities",
    "No autonomous trades",
    "No unsupported allegations",
    "No expansion of the company universe from model memory",
    "No silent replacement of missing data",
    "No creation of new system objects (Bots, Skills, Routines, integrations) without owner approval",
    "No guaranteed outcomes or promised returns",
)


@dataclass
class BotProfile:
    """The permanent profile description saved in Bot settings."""

    role_name: str  # exact roster name
    department: Department
    market_scope: str  # e.g. "NSE and BSE listed Indian equities"
    reports_to: Optional[str]  # role_name of direct Lead, or Chief; None for Chief
    tasks_owned: List[str] = field(default_factory=list)
    tasks_forbidden: List[str] = field(default_factory=list)
    preferred_sources: List[SourceTier] = field(default_factory=list)
    handoff_destination: Optional[str] = None  # role_name of recipient
    handoff_format: str = "structured Handoff (guide section 9)"
    unknown_info_rule: str = (
        "Report unknown/incomplete/disputed explicitly; never convert missing "
        "evidence into 'no news' or 'no risk'."
    )
    is_coordinator: bool = False  # True for Chief and Leads
    safety_boundaries: tuple = GLOBAL_SAFETY_BOUNDARIES

    def forbids(self, text: str) -> bool:
        t = text.lower()
        return any(f.lower() in t or t in f.lower() for f in self.tasks_forbidden)


@dataclass
class Bot:
    """A persistent AI role with its own identity and saved profile.

    The identifier (not the display name) is used for sensitive routing, since
    display names can be renamed or duplicated.
    """

    profile: BotProfile
    identifier: str = field(default_factory=lambda: f"bot_{uuid.uuid4().hex[:12]}")
    icon_color: str = "neutral"
    verified: bool = False  # set True only after a saved-state readback

    # Roster bookkeeping (guide section 4, step 6)
    group_memberships: List[str] = field(default_factory=list)
    skills_owned: List[str] = field(default_factory=list)
    routines_owned: List[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.profile.role_name

    @property
    def department(self) -> Department:
        return self.profile.department

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<Bot {self.name} ({self.identifier}) {self.department.value}>"
