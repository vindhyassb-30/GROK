"""End-to-end request orchestration (guide sections 9, 16).

Drives one research request through the chain: the Chief picks departments, each
Lead tasks its specialists, specialists run skills and hand off, Leads review and
synthesise, and the Chief combines the Lead reports. Routing and delivery controls
are enforced throughout.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .agents import BoundaryViolation
from .company import CompanyRegistry
from .delivery import DeliveryLedger, period_identity
from .enums import DeliveryStatus
from .handoff import Handoff, LeadReport
from .org import Organization
from .skills import FundHoldingsSkill, SkillContext
from .sources import SourceDesk


@dataclass
class RequestResult:
    request_id: str
    briefing: Dict[str, object]
    lead_reports: List[LeadReport] = field(default_factory=list)
    handoffs: List[Handoff] = field(default_factory=list)
    receipts: List[str] = field(default_factory=list)


class Desk:
    """Runtime facade: holds the org plus the registry, sources, and ledger."""

    def __init__(
        self,
        org: Organization,
        registry: CompanyRegistry,
        source_desk: SourceDesk,
        ledger: Optional[DeliveryLedger] = None,
    ):
        self.org = org
        self.registry = registry
        self.sources = source_desk
        self.ledger = ledger or DeliveryLedger()

    def _run_specialist(self, specialist_name: str, symbols: List[str], window_days: int,
                        request_id: str, run_date=None) -> Handoff:
        sp = self.org.specialists[specialist_name]
        ctx = SkillContext(
            registry=self.registry,
            source_desk=self.sources,
            symbols=symbols,
            window_days=window_days,
            request_id=request_id,
            bot_identifier=sp.bot.identifier,
            bot_name=sp.bot.name,
            retry_limit=1,
            run_date=run_date,
        )
        handoff = sp.perform(ctx)
        # Enforce routing: specialist may only hand off to its Lead.
        self.org.router.route_specialist_to(specialist_name, sp.bot.profile.reports_to)
        return handoff

    def run_department(self, lead_name: str, symbols: List[str], window_days: int,
                       request_id: str, run_date=None) -> LeadReport:
        """Run every authorised specialist under a Lead, then synthesise one report."""
        lead = self.org.leads[lead_name]
        handoffs: List[Handoff] = []
        for sp_name in sorted(lead.authorised):
            h = self._run_specialist(sp_name, symbols, window_days, request_id, run_date)
            lead.review_handoff(h)
            handoffs.append(h)
        report = lead.synthesise(request_id, handoffs)
        # Lead -> Chief routing check.
        self.org.router.route_lead_to_chief(lead_name)
        return report

    def ask_chief(self, question: str, symbols: List[str], departments: List[str],
                  window_days: int = 7, run_date=None) -> RequestResult:
        """A user request to the Chief, routed only to the needed departments."""
        request_id = f"req_{uuid.uuid4().hex[:10]}"
        reports: List[LeadReport] = []
        all_handoffs: List[Handoff] = []
        receipts: List[str] = []

        for lead_name in departments:
            if lead_name not in self.org.leads:
                raise BoundaryViolation(f"'{lead_name}' is not a department Lead.")
            report = self.run_department(lead_name, symbols, window_days, request_id, run_date)
            all_handoffs.extend(report.accepted_handoffs)

            # Idempotent delivery of this department's report to the Chief.
            period = period_identity(lead_name, request_id)
            run = self.ledger.open_run(workflow=lead_name, period_id=period)
            self.ledger.mark_pending(run)
            receipt = self.ledger.deliver(run, recipient_known=True)
            run.lead_accepted = True
            self.ledger.advance_cursor(run)
            if receipt:
                receipts.append(receipt)
            reports.append(report)

        briefing = self.org.chief.combine(reports)
        briefing["question"] = question
        return RequestResult(
            request_id=request_id,
            briefing=briefing,
            lead_reports=reports,
            handoffs=all_handoffs,
            receipts=receipts,
        )
