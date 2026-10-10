# Grok Stock Market Intelligence Team — Local Simulation

A runnable Python model of the research-desk organization described in the build
guide. It encodes the hierarchy, structured handoffs, skills, department groups,
scheduled routines, and the safety / duplicate-delivery controls as actual
software so you can exercise the design end-to-end offline.

> Research and decision support only. The system does not place trades, promise
> returns, invent missing data, or present an unsupported opinion as fact.

## Why this is a simulation

The original guide describes operations inside the **Grok Bot** product
(creating Bots, Groups, Routines through its UI). This project does **not** talk
to Grok Bot. Instead it reproduces the same organizational rules as a local
system you can run, test, and extend — a faithful prototype of the behaviour,
with real integrations as drop-in points.

## The organization (23 Bots)

- 1 Chief: `Chief Market Intelligence Officer`
- 5 Leads: Market News, Equity Research, Industry & Geopolitical, Market Activity
  & Ownership, Independent Research Review
- 17 specialists, each reporting to exactly one Lead

Six Groups: one Chief Intelligence Group (Chief + 5 Leads) and five department
desks.

## Install

```powershell
python -m pip install -e .           # installs the `grok-desk` command
python -m pip install -r requirements-dev.txt   # pytest for the test suite
```

No third-party runtime dependencies — the mock LLM and mock source layer let the
whole desk run deterministically offline.

## Command line

```powershell
grok-desk verify        # acceptance-checklist summary (counts, routine states)
grok-desk roster        # the 23 bots with identifiers, reporting lines, groups
grok-desk schedule      # the 13 production routines and their active/paused state
grok-desk accept        # run the Stage A–G acceptance checks
grok-desk ask "Any material news on Reliance?" --symbols RELIANCE --departments "Market News Research Lead"
grok-desk routine "Primary-source news"   # manually test one routine (stays paused)
```

(If you have not installed the package, prefix with `python -m`:
`python -m grok_desk.cli accept`, after setting `PYTHONPATH=src`.)

## How the pieces map to the guide

| Guide concept | Module |
|---|---|
| Bot identity + permanent profile | `profile.py` |
| Roster (23 roles, departments, colours) | `roster.py` |
| Structured handoff + Lead report | `handoff.py` |
| Coverage states, source tiers, freshness | `enums.py` |
| Four distinct times | `timestamps.py` |
| Approved company universe / identity registry | `company.py` |
| Primary-source-first retrieval | `sources.py` |
| 14-point Skill framework + concrete skills | `skills.py` |
| Specialist / Lead / Chief behaviour + boundaries | `agents.py` |
| Groups + routing chain | `groups.py` |
| Duplicate & delivery controls | `delivery.py` |
| Routines + scheduler (paused/active, timezone) | `routines.py` |
| Builder for the whole org + production schedule | `org.py` |
| End-to-end request orchestration | `pipeline.py` |
| Stage A–G acceptance checks | `acceptance.py` |
| Pluggable LLM (mock) | `llm.py` |
| Offline fixtures (universe + documents) | `fixtures.py` |

## Safety behaviours enforced in code

- Direct worker→Chief routing is blocked; the Chief only accepts reports from the
  five Leads.
- Specialists may hand off only to their own authorised Lead.
- Missing evidence stays visible: "no information found" becomes an explicit
  `completed_with_no_material_findings` or `incomplete_coverage`, never
  "nothing happened".
- Company identity is never invented; an unknown symbol or a registry outage is
  reported, not guessed.
- Source outages surface as coverage gaps rather than fabricated facts.
- Scheduled delivery is idempotent: duplicate events and already-delivered
  periods are suppressed, stale runs cannot overwrite newer ones, and the
  research cursor advances only after delivery **and** Lead acceptance.
- The Fund Holdings routine is date-gated to the first Monday of the month.
- Routines are created paused; the scheduler is the authority for active state.

## Plugging in real integrations

- **LLM**: implement the `LLM` protocol in `llm.py` (one `complete` method) with
  a real provider and pass it to the agents.
- **Sources**: implement `SourceProvider` in `sources.py` (one `search` method)
  with real HTTP fetchers for NSE/BSE, SEBI, IR pages, AMFI, etc., and register
  them with `SourceDesk`.
- **Company registry**: replace the fixture universe in `fixtures.py` with a real
  identity service behind `CompanyRegistry`.

## Tests

```powershell
python -m pytest -q
```

Covers roster shape, routing and boundary enforcement, delivery idempotency, the
date-gated routine, source and identity-registry outages, and the end-to-end
pipeline.
