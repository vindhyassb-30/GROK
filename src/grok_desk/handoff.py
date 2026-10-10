"""The structured handoff contract (guide section 9) and evidence models.

A handoff is the contract between a specialist and its Lead. Facts,
interpretations and hypotheses are kept strictly separate; missing information
stays visible; coverage and delivery are tracked independently.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from .enums import CoverageState, DataFreshness, LeadDecision, SourceTier
from .timestamps import TimeStamps


@dataclass(frozen=True)
class SourceRef:
    """A single source consulted. Snippets are discovery leads, not final evidence."""

    tier: SourceTier
    title: str
    url: str
    opened_full_document: bool = False
    freshness: DataFreshness = DataFreshness.LATEST_AVAILABLE


@dataclass(frozen=True)
class Fact:
    """A verified fact tied to at least one source. Never fabricated."""

    statement: str
    sources: List[SourceRef]
    timestamps: TimeStamps

    def is_primary_backed(self) -> bool:
        return any(s.tier.is_primary and s.opened_full_document for s in self.sources)


@dataclass
class Handoff:
    """Standardised specialist -> Lead handoff. See guide section 9."""

    request_id: str
    bot_identifier: str
    bot_name: str
    company_name: Optional[str]
    company_symbol: Optional[str]
    scope: str
    time_window: str

    facts: List[Fact] = field(default_factory=list)
    interpretation: str = ""
    contradictions: List[str] = field(default_factory=list)
    unknowns: List[str] = field(default_factory=list)

    coverage: CoverageState = CoverageState.NOT_CLASSIFIED
    confidence: float = 0.0  # evidence-based, 0..1
    recommended_lead_action: str = ""

    handoff_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Set by the receiving Lead -- delivery is NOT acceptance.
    lead_decision: Optional[LeadDecision] = None
    lead_notes: str = ""

    @property
    def source_links(self) -> List[str]:
        links: List[str] = []
        for f in self.facts:
            links.extend(s.url for s in f.sources)
        return links

    def has_evidence(self) -> bool:
        return len(self.facts) > 0

    def summary(self) -> str:
        return (
            f"[{self.bot_name}] {self.company_symbol or self.company_name or 'N/A'} "
            f"scope='{self.scope}' coverage={self.coverage.value} "
            f"facts={len(self.facts)} unknowns={len(self.unknowns)} "
            f"confidence={self.confidence:.2f}"
        )


@dataclass
class LeadReport:
    """Consolidated report a Lead sends to the Chief (guide section 6).

    Deduplicated and reconciled; disagreements are preserved, not hidden.
    """

    report_id: str
    lead_identifier: str
    lead_name: str
    department: str
    request_id: str
    accepted_handoffs: List[Handoff] = field(default_factory=list)
    reconciled_findings: List[str] = field(default_factory=list)
    unresolved_disagreements: List[str] = field(default_factory=list)
    coverage_gaps: List[str] = field(default_factory=list)
    overall_coverage: CoverageState = CoverageState.NOT_CLASSIFIED

    def summary(self) -> str:
        return (
            f"<LeadReport {self.department}: "
            f"{len(self.accepted_handoffs)} accepted, "
            f"{len(self.unresolved_disagreements)} disagreements, "
            f"{len(self.coverage_gaps)} gaps, coverage={self.overall_coverage.value}>"
        )
