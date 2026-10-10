"""Staged acceptance checks (guide section 13).

Programmatic versions of the Stage A-G acceptance sequence, returning a simple
pass/fail report the CLI can print. These are design-level checks over the
simulated org; production acceptance in real Grok Bot still requires real sources.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List

from .agents import BoundaryViolation
from .fixtures import build_registry, build_source_desk
from .org import build_organization
from .pipeline import Desk
from .roster import role_specific_forbidden


def _check(name: str, passed: bool, detail: str = "") -> Dict[str, object]:
    return {"stage": name, "passed": bool(passed), "detail": detail}


def run_all() -> List[Dict[str, object]]:
    org = build_organization()
    registry = build_registry()
    sources = build_source_desk()
    desk = Desk(org, registry, sources)
    results: List[Dict[str, object]] = []

    # Stage A: identity -- every specialist reports to a real Lead with a destination.
    bad_identity = [
        n for n, sp in org.specialists.items()
        if sp.identity().lead not in org.leads or sp.identity().handoff_destination not in org.leads
    ]
    results.append(_check("A: identity", not bad_identity, f"bad={bad_identity}"))

    # Stage B: boundary -- role-specific forbidden requests are refused.
    b_ok = True
    b_detail = []
    for role, phrases in {
        n: role_specific_forbidden(n) for n in org.specialists if role_specific_forbidden(n)
    }.items():
        sp = org.specialists[role]
        for phrase in phrases:
            try:
                sp.check_boundary(f"please {phrase}")
                b_ok = False
                b_detail.append(f"{role} failed to refuse '{phrase}'")
            except BoundaryViolation:
                pass
    results.append(_check("B: boundary", b_ok, "; ".join(b_detail)))

    # Stage C: controlled real-source -- opens sources, keeps timestamps, routes to Lead.
    report = desk.run_department("Market News Research Lead", ["RELIANCE"], 7, "accC")
    c_ok = report.accepted_handoffs and all(
        all(f.timestamps.retrieval_time for f in h.facts) for h in report.accepted_handoffs
    )
    results.append(_check("C: real-source", bool(c_ok), report.summary()))

    # Stage D: generalisation -- a different company flows through the same method.
    report_d = desk.run_department("Market News Research Lead", ["TCS"], 7, "accD")
    results.append(_check("D: generalisation", bool(report_d.accepted_handoffs), report_d.summary()))

    # Stage E: handoff -- Lead explicitly decides, not merely acknowledges.
    e_ok = all(h.lead_decision is not None for h in report.accepted_handoffs)
    results.append(_check("E: handoff review", e_ok, "all handoffs carry a Lead decision"))

    # Stage F: routine -- date-gated Fund Holdings exits when not first Monday.
    from .skills import SkillContext
    sp = org.specialists["Fund Holdings Research Analyst"]
    ctx = SkillContext(registry, sources, ["HDFCBANK"], 30, "accF",
                       sp.bot.identifier, sp.bot.name, run_date=date(2026, 10, 8))  # a Thursday
    h = sp.skill.run(ctx)
    results.append(_check("F: date-gated routine", h.coverage.value == "not_due", h.coverage.value))

    # Stage G: department -> Chief, direct worker->chief blocked.
    try:
        org.router.route_specialist_to("Research Analyst", org.chief.name)
        g_ok = False
    except BoundaryViolation:
        g_ok = True
    results.append(_check("G: chain enforced", g_ok, "direct worker->Chief blocked"))

    return results


def summarise(results: List[Dict[str, object]]) -> str:
    lines = []
    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        lines.append(f"[{mark}] {r['stage']}  {r['detail']}")
    passed = sum(1 for r in results if r["passed"])
    lines.append(f"\n{passed}/{len(results)} stages passed")
    return "\n".join(lines)
