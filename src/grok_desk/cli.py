"""Command-line entrypoint for the Grok research-desk simulation.

Subcommands:
  verify     -- build the org and print the acceptance-checklist summary
  roster     -- print the 23-bot roster with identifiers and reporting lines
  schedule   -- print the routine schedule and active/paused state
  accept     -- run the Stage A-G acceptance checks
  ask        -- send a question to the Chief, routed to chosen departments
  routine    -- manually test one routine while it stays paused
"""

from __future__ import annotations

import argparse
import json
from datetime import date

from .acceptance import run_all, summarise
from .fixtures import build_registry, build_source_desk
from .org import build_organization
from .pipeline import Desk
from .roster import LEAD_NAMES


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_verify(_args) -> int:
    org = build_organization()
    _print(org.verify())
    return 0


def cmd_roster(_args) -> int:
    org = build_organization()
    rows = []
    for name, bot in org.bots.items():
        rows.append({
            "role": name,
            "identifier": bot.identifier,
            "department": bot.department.value,
            "reports_to": bot.profile.reports_to or "(user)",
            "color": bot.icon_color,
            "groups": bot.group_memberships,
            "verified": bot.verified,
        })
    _print(rows)
    return 0


def cmd_schedule(_args) -> int:
    org = build_organization()
    rows = [r.readback() for r in org.scheduler.all()]
    _print(rows)
    return 0


def cmd_accept(_args) -> int:
    results = run_all()
    print(summarise(results))
    return 0 if all(r["passed"] for r in results) else 1


def cmd_ask(args) -> int:
    org = build_organization()
    desk = Desk(org, build_registry(), build_source_desk())
    departments = args.departments or LEAD_NAMES
    result = desk.ask_chief(
        question=args.question,
        symbols=args.symbols,
        departments=departments,
        window_days=args.window,
    )
    _print({
        "request_id": result.request_id,
        "receipts": result.receipts,
        "briefing": result.briefing,
    })
    return 0


def cmd_routine(args) -> int:
    org = build_organization()
    routine = org.scheduler.get(args.name)
    if routine is None:
        print(f"No routine named '{args.name}'. Use 'schedule' to list them.")
        return 1
    # Manual test run while the routine remains paused (guide Stage F).
    desk = Desk(org, build_registry(), build_source_desk())
    owner = org.specialists.get(routine.owner_name)
    out = {"readback": routine.readback(), "note": "routine remains PAUSED during test"}
    if owner is not None:
        report = desk.run_department(routine.destination_lead, args.symbols, args.window,
                                     f"routine-test:{routine.name}", run_date=date.today())
        out["result"] = report.summary()
    else:
        out["result"] = "owner is a coordinator (Chief); synthesis routine, no raw run"
    _print(out)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="grok-desk", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("verify", help="print acceptance-checklist summary").set_defaults(func=cmd_verify)
    sub.add_parser("roster", help="print the 23-bot roster").set_defaults(func=cmd_roster)
    sub.add_parser("schedule", help="print the routine schedule").set_defaults(func=cmd_schedule)
    sub.add_parser("accept", help="run Stage A-G acceptance checks").set_defaults(func=cmd_accept)

    p_ask = sub.add_parser("ask", help="ask the Chief a question")
    p_ask.add_argument("question")
    p_ask.add_argument("--symbols", nargs="+", default=["RELIANCE"])
    p_ask.add_argument("--departments", nargs="+", default=None)
    p_ask.add_argument("--window", type=int, default=7)
    p_ask.set_defaults(func=cmd_ask)

    p_rt = sub.add_parser("routine", help="manually test one paused routine")
    p_rt.add_argument("name")
    p_rt.add_argument("--symbols", nargs="+", default=["RELIANCE"])
    p_rt.add_argument("--window", type=int, default=7)
    p_rt.set_defaults(func=cmd_routine)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
