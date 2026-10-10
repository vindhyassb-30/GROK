"""Skill framework (guide section 7).

A Skill is a reusable research procedure. Every production Skill declares the
14 required elements and executes against the source layer, producing a
structured Handoff. Skills never fabricate figures and keep missing evidence
visible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from .company import CompanyRegistry, IdentityRegistryUnavailable
from .enums import CoverageState, SourceTier
from .handoff import Fact, Handoff, SourceRef
from .sources import SourceDesk


@dataclass
class SkillSpec:
    """The 14 required elements of a production Skill (guide section 7)."""

    name: str
    when_to_use: str                      # 1
    required_inputs: List[str]            # 2
    approved_universe: str                # 3
    source_priority: List[SourceTier]     # 4
    time_window_rules: str                # 5
    retrieval_retry_limits: str           # 6
    evidence_thresholds: str              # 7
    calculations_validation: str          # 8
    status_labels: List[CoverageState]    # 9
    handoff_format: str                   # 10
    delivery_destination: str             # 11
    duplicate_prevention: str             # 12
    completion_failure: str               # 13
    non_goals: List[str]                  # 14

    def missing_elements(self) -> List[str]:
        """Return names of any unset 14-point elements (for acceptance checks)."""
        checks = {
            "when_to_use": self.when_to_use,
            "required_inputs": self.required_inputs,
            "approved_universe": self.approved_universe,
            "source_priority": self.source_priority,
            "time_window_rules": self.time_window_rules,
            "retrieval_retry_limits": self.retrieval_retry_limits,
            "evidence_thresholds": self.evidence_thresholds,
            "calculations_validation": self.calculations_validation,
            "status_labels": self.status_labels,
            "handoff_format": self.handoff_format,
            "delivery_destination": self.delivery_destination,
            "duplicate_prevention": self.duplicate_prevention,
            "completion_failure": self.completion_failure,
            "non_goals": self.non_goals,
        }
        return [k for k, v in checks.items() if not v]


@dataclass
class SkillContext:
    """Everything a Skill needs at run time."""

    registry: CompanyRegistry
    source_desk: SourceDesk
    symbols: List[str]
    window_days: int
    request_id: str
    bot_identifier: str
    bot_name: str
    retry_limit: int = 1
    run_date: Optional[date] = None  # for date-gated skills


class Skill:
    """Base class. Subclasses implement ``run`` to produce a Handoff."""

    spec: SkillSpec

    def __init__(self, spec: SkillSpec):
        self.spec = spec

    @property
    def name(self) -> str:
        return self.spec.name

    def run(self, ctx: SkillContext) -> Handoff:  # pragma: no cover - abstract
        raise NotImplementedError

    # --- shared helpers -------------------------------------------------
    def _resolve_single(self, ctx: SkillContext) -> tuple:
        """Resolve the first symbol against the approved universe.

        Returns (company_name, symbol, outage_note). Never guesses identity.
        """
        if not ctx.symbols:
            return None, None, None
        token = ctx.symbols[0]
        try:
            company = ctx.registry.resolve(token)
        except IdentityRegistryUnavailable:
            return None, token, "identity registry unavailable"
        if company is None:
            return None, token, "symbol not in approved universe"
        return company.canonical_name, (company.nse_symbol or token), None


class NewsResearchSkill(Skill):
    """Primary-source news discovery for the Market News Research team."""

    def run(self, ctx: SkillContext) -> Handoff:
        name, symbol, outage = self._resolve_single(ctx)
        h = Handoff(
            request_id=ctx.request_id,
            bot_identifier=ctx.bot_identifier,
            bot_name=ctx.bot_name,
            company_name=name,
            company_symbol=symbol,
            scope="primary-source news discovery",
            time_window=f"last {ctx.window_days}d",
        )
        if outage:
            h.unknowns.append(outage)
            h.coverage = CoverageState.INCOMPLETE
            h.recommended_lead_action = "Report identity/source outage; do not infer 'no news'."
            return h

        result = ctx.source_desk.retrieve(symbol, ctx.window_days, ctx.retry_limit)
        for tier in result.failed_tiers:
            h.unknowns.append(f"source tier {tier.name} unavailable")

        for doc in result.documents:
            ts = ctx.source_desk.timestamps_for(doc)
            ref = SourceRef(
                tier=doc.tier,
                title=doc.title,
                url=doc.url,
                opened_full_document=True,
                freshness=doc.freshness,
            )
            fact = Fact(statement=doc.title, sources=[ref], timestamps=ts)
            h.facts.append(fact)

        if h.facts:
            h.coverage = CoverageState.COMPLETED_WITH_FINDINGS
            h.confidence = 0.7 if any(f.is_primary_backed() for f in h.facts) else 0.4
            h.interpretation = "Items listed are published events, not causal claims."
            h.recommended_lead_action = "Deduplicate events and reconcile against other specialists."
        elif result.had_failures:
            h.coverage = CoverageState.INCOMPLETE
            h.recommended_lead_action = "Retry failed sources; coverage gap must stay visible."
        else:
            # No findings, but sources were reachable -> explicitly no material findings.
            h.coverage = CoverageState.COMPLETED_NO_FINDINGS
            h.confidence = 0.5
            h.recommended_lead_action = "Record 'no material findings' (NOT 'nothing happened')."
        return h


class FundHoldingsSkill(Skill):
    """Monthly fund-holdings review that is date-gated to the first Monday.

    Per guide section 12, it exits without research unless the run date is within
    the first seven days of the month AND is a Monday.
    """

    def run(self, ctx: SkillContext) -> Handoff:
        name, symbol, outage = self._resolve_single(ctx)
        h = Handoff(
            request_id=ctx.request_id,
            bot_identifier=ctx.bot_identifier,
            bot_name=ctx.bot_name,
            company_name=name,
            company_symbol=symbol,
            scope="monthly fund-holdings review",
            time_window="monthly",
        )
        run_day = ctx.run_date or date.today()
        is_first_week = run_day.day <= 7
        is_monday = run_day.weekday() == 0
        if not (is_first_week and is_monday):
            h.coverage = CoverageState.NOT_DUE
            h.recommended_lead_action = "Not the first Monday; exit without research."
            return h

        if outage:
            h.unknowns.append(outage)
            h.coverage = CoverageState.INCOMPLETE
            return h

        result = ctx.source_desk.retrieve(symbol, ctx.window_days, ctx.retry_limit)
        for doc in result.documents:
            if doc.tier != SourceTier.FUND_DISCLOSURE:
                continue
            ts = ctx.source_desk.timestamps_for(doc)
            ref = SourceRef(tier=doc.tier, title=doc.title, url=doc.url, opened_full_document=True)
            h.facts.append(Fact(statement=doc.title, sources=[ref], timestamps=ts))

        h.coverage = (
            CoverageState.COMPLETED_WITH_FINDINGS if h.facts else CoverageState.COMPLETED_NO_FINDINGS
        )
        h.confidence = 0.6 if h.facts else 0.5
        h.recommended_lead_action = "Reconcile ownership changes against AMFI disclosures."
        return h


class LeadSynthesisSkill(Skill):
    """Lead-side synthesis: consolidate accepted handoffs without redoing research."""

    def consolidate(self, accepted: List[Handoff]) -> List[str]:
        """Deduplicate findings by statement text, preserving order."""
        seen = set()
        findings: List[str] = []
        for h in accepted:
            for f in h.facts:
                if f.statement not in seen:
                    seen.add(f.statement)
                    findings.append(f.statement)
        return findings

    def run(self, ctx: SkillContext) -> Handoff:  # pragma: no cover - leads use consolidate()
        raise NotImplementedError("LeadSynthesisSkill consolidates handoffs, not raw sources.")
