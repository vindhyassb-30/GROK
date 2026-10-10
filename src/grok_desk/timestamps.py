"""Time handling (guide section 7).

Every piece of research distinguishes four distinct times so that an old filing
retrieved today is never described as a new event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TimeStamps:
    """The four distinct times every Skill must separate.

    - event_time: when the underlying event actually happened
    - publication_time: when the source released it
    - retrieval_time: when the Bot accessed it
    - data_as_of: the period represented by the data
    """

    retrieval_time: datetime
    event_time: Optional[datetime] = None
    publication_time: Optional[datetime] = None
    data_as_of: Optional[datetime] = None

    @classmethod
    def retrieved_now(cls, **kwargs) -> "TimeStamps":
        return cls(retrieval_time=utcnow(), **kwargs)

    def is_stale_as_new(self) -> bool:
        """True if publication is far older than retrieval -> likely NOT a new event."""
        if self.publication_time is None:
            return False
        age = self.retrieval_time - self.publication_time
        return age.days > 2

    def describe(self) -> str:
        def fmt(d: Optional[datetime]) -> str:
            return d.isoformat() if d else "unknown"

        return (
            f"event={fmt(self.event_time)} "
            f"published={fmt(self.publication_time)} "
            f"retrieved={fmt(self.retrieval_time)} "
            f"data_as_of={fmt(self.data_as_of)}"
        )
