"""Department Groups and routing (guide sections 8, 9).

A Group is a controlled communication room: a Lead plus its authorised
specialists, or the Chief plus the five Leads. Routing enforces the chain:
specialists address their Lead, the Lead reports to the Chief. Direct
worker-to-Chief routing for normal work is blocked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .agents import BoundaryViolation, Chief, Lead, Specialist


@dataclass
class Group:
    """A department room with one Lead owner and its authorised members."""

    name: str
    lead_name: str
    member_names: List[str] = field(default_factory=list)
    is_chief_group: bool = False
    bot_limit: Optional[int] = None  # design around Grok's per-group limit if present

    def add_member(self, role_name: str) -> None:
        if self.bot_limit is not None and len(self.member_names) + 1 >= self.bot_limit:
            raise ValueError(
                f"Group '{self.name}' would exceed bot_limit={self.bot_limit}; "
                "design the hierarchy around the limit instead."
            )
        if role_name not in self.member_names:
            self.member_names.append(role_name)

    def contains(self, role_name: str) -> bool:
        return role_name == self.lead_name or role_name in self.member_names


class Router:
    """Enforces the specialist -> Lead -> Chief chain across the organization."""

    def __init__(self, chief: Chief):
        self.chief = chief
        self.leads: Dict[str, Lead] = {}
        self.specialists: Dict[str, Specialist] = {}
        # specialist role_name -> lead role_name
        self._reporting: Dict[str, str] = {}

    def register_lead(self, lead: Lead) -> None:
        self.leads[lead.name] = lead

    def register_specialist(self, specialist: Specialist, lead_name: str) -> None:
        self.specialists[specialist.name] = specialist
        self._reporting[specialist.name] = lead_name

    # --- routing rules --------------------------------------------------
    def route_specialist_to(self, specialist_name: str, recipient_name: str) -> None:
        """Validate a specialist's intended handoff recipient.

        A specialist may hand off ONLY to its own authorised Lead. Direct
        worker-to-Chief routing is refused for normal work.
        """
        if recipient_name == self.chief.name:
            raise BoundaryViolation(
                f"Direct worker->Chief routing blocked for '{specialist_name}'. "
                "Specialists address their Lead."
            )
        expected_lead = self._reporting.get(specialist_name)
        if expected_lead is None:
            raise BoundaryViolation(f"Unknown specialist '{specialist_name}'.")
        if recipient_name != expected_lead:
            raise BoundaryViolation(
                f"'{specialist_name}' may only hand off to its Lead "
                f"'{expected_lead}', not '{recipient_name}'."
            )
        lead = self.leads.get(expected_lead)
        if lead is None or not lead.may_task(specialist_name):
            raise BoundaryViolation(
                f"Lead '{expected_lead}' does not authorise '{specialist_name}'."
            )

    def route_lead_to_chief(self, lead_name: str) -> None:
        """Only a registered Lead may deliver to the Chief."""
        if lead_name not in self.leads:
            raise BoundaryViolation(
                f"'{lead_name}' is not a Lead and may not report to the Chief."
            )

    def lead_for(self, specialist_name: str) -> Optional[Lead]:
        ln = self._reporting.get(specialist_name)
        return self.leads.get(ln) if ln else None
