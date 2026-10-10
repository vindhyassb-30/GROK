"""Agents: Specialist, Lead, Chief (guide sections 6, 13).

Each agent wraps a Bot (identity + profile) and enforces role boundaries:
- Specialists run one Skill and hand off ONLY to their Lead.
- Leads review/deduplicate/reconcile and send ONE consolidated report to the Chief.
- The Chief coordinates Leads and synthesises; it never scans raw sources itself.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .enums import CoverageState, Department, LeadDecision
from .handoff import Handoff, LeadReport
from .llm import LLM
from .profile import Bot
from .skills import LeadSynthesisSkill, Skill, SkillContext


class BoundaryViolation(Exception):
    """Raised when an agent is asked to act outside its profile boundaries."""


@dataclass
class IdentityStatement:
    """What a Bot reports in a Stage A identity test (guide section 13)."""

    role: str
    lead: Optional[str]
    permitted_sources: List[str]
    prohibited_actions: List[str]
    handoff_destination: Optional[str]


class Specialist:
    """A worker Bot that runs a single Skill and hands off to its Lead only."""

    def __init__(self, bot: Bot, skill: Skill, llm: Optional[LLM] = None):
        self.bot = bot
        self.skill = skill
        self.llm = llm

    @property
    def name(self) -> str:
        return self.bot.name

    def identity(self) -> IdentityStatement:
        p = self.bot.profile
        return IdentityStatement(
            role=p.role_name,
            lead=p.reports_to,
            permitted_sources=[s.name for s in p.preferred_sources],
            prohibited_actions=list(p.tasks_forbidden),
            handoff_destination=p.handoff_destination,
        )

    def check_boundary(self, request: str) -> None:
        """Stage B: refuse the unsupported portion of an out-of-role request."""
        if self.bot.profile.forbids(request):
            raise BoundaryViolation(
                f"{self.name} refuses out-of-role request: '{request}'. "
                f"Routing to Lead {self.bot.profile.reports_to}."
            )

    def perform(self, ctx: SkillContext) -> Handoff:
        """Run the owned Skill and return a handoff addressed to the Lead."""
        # Ensure the context carries this bot's identity for the handoff.
        ctx.bot_identifier = self.bot.identifier
        ctx.bot_name = self.bot.name
        return self.skill.run(ctx)


class Lead:
    """A coordinator Bot that reviews specialist handoffs and reports to the Chief."""

    def __init__(self, bot: Bot, authorised_specialists: List[str], llm: Optional[LLM] = None):
        self.bot = bot
        self.authorised = set(authorised_specialists)  # role_names it may task
        self.llm = llm
        self._synth = LeadSynthesisSkill(spec=None)  # consolidate() needs no spec

    @property
    def name(self) -> str:
        return self.bot.name

    @property
    def department(self) -> Department:
        return self.bot.department

    def identity(self) -> IdentityStatement:
        p = self.bot.profile
        return IdentityStatement(
            role=p.role_name,
            lead="Chief Market Intelligence Officer",
            permitted_sources=[s.name for s in p.preferred_sources],
            prohibited_actions=list(p.tasks_forbidden),
            handoff_destination=p.handoff_destination,
        )

    def may_task(self, specialist_name: str) -> bool:
        return specialist_name in self.authorised

    def review_handoff(self, h: Handoff) -> LeadDecision:
        """Explicitly accept/reject/request-correction/incomplete. Delivery != acceptance."""
        if h.coverage == CoverageState.INCOMPLETE:
            h.lead_decision = LeadDecision.INCOMPLETE
            h.lead_notes = "Coverage incomplete; gap must remain visible."
        elif h.coverage == CoverageState.NOT_DUE:
            h.lead_decision = LeadDecision.INCOMPLETE
            h.lead_notes = "Routine not due; no research expected."
        elif h.coverage == CoverageState.COMPLETED_WITH_FINDINGS and not h.has_evidence():
            h.lead_decision = LeadDecision.CORRECTION_REQUESTED
            h.lead_notes = "Claims findings but carries no evidence."
        else:
            h.lead_decision = LeadDecision.ACCEPTED
            h.lead_notes = "Evidence reviewed and accepted."
        return h.lead_decision

    def synthesise(self, request_id: str, handoffs: List[Handoff]) -> LeadReport:
        """Deduplicate, reconcile, preserve disagreements; one report to the Chief."""
        report = LeadReport(
            report_id=f"rep_{uuid.uuid4().hex[:10]}",
            lead_identifier=self.bot.identifier,
            lead_name=self.bot.name,
            department=self.department.value,
            request_id=request_id,
        )
        for h in handoffs:
            if h.lead_decision is None:
                self.review_handoff(h)
            if h.lead_decision == LeadDecision.ACCEPTED:
                report.accepted_handoffs.append(h)
            else:
                report.coverage_gaps.append(f"{h.bot_name}: {h.lead_notes}")

        report.reconciled_findings = self._synth.consolidate(report.accepted_handoffs)

        # Preserve disagreements rather than hiding them.
        interps = {h.interpretation for h in report.accepted_handoffs if h.interpretation}
        if len(interps) > 1:
            report.unresolved_disagreements = sorted(interps)

        if report.accepted_handoffs and report.reconciled_findings:
            report.overall_coverage = CoverageState.COMPLETED_WITH_FINDINGS
        elif report.accepted_handoffs:
            report.overall_coverage = CoverageState.COMPLETED_NO_FINDINGS
        elif report.coverage_gaps:
            report.overall_coverage = CoverageState.INCOMPLETE
        else:
            report.overall_coverage = CoverageState.NOT_CLASSIFIED
        return report


class Chief:
    """The Chief Market Intelligence Officer: coordinates Leads and synthesises.

    Receives consolidated reports ONLY from the five Leads. Combines findings
    without hiding disagreements and preserves coverage gaps. It does not perform
    raw searches or contact specialists directly.
    """

    def __init__(self, bot: Bot, lead_names: List[str], llm: Optional[LLM] = None):
        self.bot = bot
        self.lead_names = set(lead_names)
        self.llm = llm

    @property
    def name(self) -> str:
        return self.bot.name

    def accept_report(self, report: LeadReport) -> None:
        """Reject reports that did not originate from an authorised Lead."""
        if report.lead_name not in self.lead_names:
            raise BoundaryViolation(
                f"Chief refuses report from non-Lead '{report.lead_name}'. "
                "Only the five Leads may report to the Chief."
            )

    def combine(self, reports: List[LeadReport]) -> Dict[str, object]:
        """Combine Lead reports into a user-facing briefing, preserving gaps."""
        for r in reports:
            self.accept_report(r)

        findings: List[str] = []
        disagreements: List[str] = []
        gaps: List[str] = []
        for r in reports:
            findings.extend(r.reconciled_findings)
            disagreements.extend(r.unresolved_disagreements)
            gaps.extend(r.coverage_gaps)

        # Deduplicate top-level findings across departments.
        deduped = list(dict.fromkeys(findings))

        if deduped:
            coverage = CoverageState.COMPLETED_WITH_FINDINGS
        elif gaps:
            coverage = CoverageState.INCOMPLETE
        else:
            coverage = CoverageState.COMPLETED_NO_FINDINGS

        return {
            "findings": deduped,
            "disagreements": disagreements,
            "coverage_gaps": gaps,
            "overall_coverage": coverage,
            "departments_consulted": [r.department for r in reports],
            "disclaimer": (
                "Research and decision support only. No trades placed, no guaranteed "
                "outcomes. Missing evidence is shown, not hidden."
            ),
        }
