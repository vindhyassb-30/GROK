"""Routines and the scheduler (guide sections 11, 12).

A Routine is a scheduled wake-up that tells one Bot to run a saved Skill at a
particular time. Routines are created PAUSED, verified by read-back, and only
then activated. The scheduler is the authority for active/paused state.

Cadence is kept deliberately simple and testable: a routine declares a time of
day, a timezone (default Asia/Kolkata), and a cadence predicate over a date.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Callable, Dict, List, Optional

from .enums import RoutineState

try:  # Python 3.9+ stdlib
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


# --- cadence predicates -------------------------------------------------
def weekdays(d: date) -> bool:
    """Monday-Friday."""
    return d.weekday() < 5


def fridays(d: date) -> bool:
    return d.weekday() == 4


def first_monday(d: date) -> bool:
    """First Monday of the month (within the first seven days)."""
    return d.weekday() == 0 and d.day <= 7


@dataclass
class Routine:
    """A scheduled run of one Skill owned by one Bot."""

    name: str                       # precise, unique
    owner_name: str                 # Bot role_name that executes
    skill_name: str                 # the single named Skill to run
    at: time                        # time of day
    cadence: Callable[[date], bool] # which dates it fires on
    approved_universe: List[str]    # symbols it is allowed to cover
    destination_lead: str           # where the handoff goes
    on_incomplete: str = "leave coverage incomplete; do not infer absence"
    source_limit: int = 10
    retry_limit: int = 1
    allow_object_creation: bool = False  # routines never create system objects
    timezone: str = "Asia/Kolkata"
    state: RoutineState = RoutineState.PAUSED  # created paused

    def tzinfo(self):
        if ZoneInfo is None:  # pragma: no cover
            return None
        return ZoneInfo(self.timezone)

    def due_on(self, d: date) -> bool:
        return self.cadence(d)

    def scheduled_datetime(self, d: date) -> Optional[datetime]:
        if not self.due_on(d):
            return None
        tz = self.tzinfo()
        dt = datetime.combine(d, self.at)
        return dt.replace(tzinfo=tz) if tz else dt

    def activate(self) -> None:
        if self.state == RoutineState.RETIRED:
            raise ValueError(f"Routine '{self.name}' is retired and cannot be activated.")
        self.state = RoutineState.ACTIVE

    def pause(self) -> None:
        self.state = RoutineState.PAUSED

    def retire(self) -> None:
        self.state = RoutineState.RETIRED

    def readback(self) -> Dict[str, str]:
        """What the scheduler UI would display on reopen (guide section 11, step 11)."""
        return {
            "name": self.name,
            "owner": self.owner_name,
            "skill": self.skill_name,
            "time": self.at.strftime("%H:%M"),
            "timezone": self.timezone,
            "destination_lead": self.destination_lead,
            "state": self.state.value,
        }


class Scheduler:
    """Registry + runner of routines. Authority for active/paused state."""

    def __init__(self):
        self._routines: Dict[str, Routine] = {}

    def add(self, routine: Routine) -> None:
        # Reject duplicate purpose+time (guide section 11): same time + same skill.
        for existing in self._routines.values():
            if (
                existing.state != RoutineState.RETIRED
                and existing.skill_name == routine.skill_name
                and existing.at == routine.at
                and existing.owner_name == routine.owner_name
            ):
                raise ValueError(
                    f"Duplicate routine purpose/time: '{routine.name}' collides with "
                    f"'{existing.name}'. Rename or retire the older copy."
                )
        self._routines[routine.name] = routine

    def get(self, name: str) -> Optional[Routine]:
        return self._routines.get(name)

    def active_routines(self) -> List[Routine]:
        return [r for r in self._routines.values() if r.state == RoutineState.ACTIVE]

    def paused_routines(self) -> List[Routine]:
        return [r for r in self._routines.values() if r.state == RoutineState.PAUSED]

    def due(self, d: date, include_paused: bool = False) -> List[Routine]:
        """Routines that would fire on date d. Paused ones excluded unless testing."""
        out = []
        for r in self._routines.values():
            if r.state == RoutineState.RETIRED:
                continue
            if r.state == RoutineState.PAUSED and not include_paused:
                continue
            if r.due_on(d):
                out.append(r)
        return out

    def all(self) -> List[Routine]:
        return list(self._routines.values())
