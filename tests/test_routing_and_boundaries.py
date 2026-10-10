"""Routing chain and boundary enforcement (guide sections 6, 8, 9, 13)."""

import pytest

from grok_desk.agents import BoundaryViolation
from grok_desk.org import build_organization


def test_direct_worker_to_chief_blocked():
    org = build_organization()
    with pytest.raises(BoundaryViolation):
        org.router.route_specialist_to("Research Analyst", org.chief.name)


def test_specialist_cannot_route_to_wrong_lead():
    org = build_organization()
    with pytest.raises(BoundaryViolation):
        org.router.route_specialist_to("Research Analyst", "Equity Research Lead")


def test_specialist_routes_to_its_own_lead():
    org = build_organization()
    # Should not raise.
    org.router.route_specialist_to("Research Analyst", "Market News Research Lead")


def test_non_lead_cannot_report_to_chief():
    org = build_organization()
    with pytest.raises(BoundaryViolation):
        org.router.route_lead_to_chief("Research Analyst")


def test_lead_reports_to_chief_ok():
    org = build_organization()
    org.router.route_lead_to_chief("Market News Research Lead")


def test_chief_refuses_report_from_non_lead():
    from grok_desk.handoff import LeadReport
    org = build_organization()
    fake = LeadReport(
        report_id="x", lead_identifier="y", lead_name="Research Analyst",
        department="Market News Research", request_id="r",
    )
    with pytest.raises(BoundaryViolation):
        org.chief.accept_report(fake)


@pytest.mark.parametrize("role,phrase", [
    ("Sentiment Analyst", "claim price causation"),
    ("Market Volume Intelligence Analyst", "call unusual activity manipulation"),
    ("Financial Forensics Analyst", "label an anomaly fraud"),
    ("Market Impact Analyst", "turn a project milestone into a new order without evidence"),
])
def test_role_specific_boundaries(role, phrase):
    org = build_organization()
    sp = org.specialists[role]
    with pytest.raises(BoundaryViolation):
        sp.check_boundary(f"please {phrase}")
