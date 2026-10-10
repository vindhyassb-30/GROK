"""Pluggable source layer (guide sections 7 and 15).

Research prefers primary sources (exchange filings, IR pages, regulators,
government, fund disclosures) over secondary reporting. Snippets are discovery
leads; the underlying document must be opened whenever possible. Source
unavailability is reported, never silently replaced with invented data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Protocol, runtime_checkable

from .enums import DataFreshness, SourceTier
from .timestamps import TimeStamps, utcnow


@dataclass(frozen=True)
class Document:
    """A primary/secondary document returned by a source provider."""

    tier: SourceTier
    title: str
    url: str
    body: str
    published: datetime
    data_as_of: Optional[datetime] = None
    freshness: DataFreshness = DataFreshness.LATEST_AVAILABLE


class SourceUnavailable(Exception):
    """Raised when a provider cannot be reached. Callers must report the outage."""


@runtime_checkable
class SourceProvider(Protocol):
    """Contract for any source backend (mock fixtures now, real HTTP later)."""

    tier: SourceTier

    def search(self, symbol: str, window_days: int) -> List[Document]:
        ...


class MockSourceProvider:
    """Offline fixture provider for one source tier.

    Documents are keyed by symbol. An ``outage`` flag simulates a source failure
    so the desk can prove it reports gaps instead of fabricating.
    """

    def __init__(self, tier: SourceTier, fixtures: Dict[str, List[Document]], outage: bool = False):
        self.tier = tier
        self._fixtures = fixtures
        self.outage = outage

    def search(self, symbol: str, window_days: int) -> List[Document]:
        if self.outage:
            raise SourceUnavailable(f"{self.tier.name} provider is down for {symbol}")
        cutoff = utcnow() - timedelta(days=window_days)
        docs = self._fixtures.get(symbol.upper(), [])
        return [d for d in docs if d.published >= cutoff]


@dataclass
class RetrievalResult:
    """Outcome of a primary-source-first retrieval attempt."""

    documents: List[Document] = field(default_factory=list)
    failed_tiers: List[SourceTier] = field(default_factory=list)
    opened_full: bool = False

    @property
    def had_failures(self) -> bool:
        return len(self.failed_tiers) > 0


class SourceDesk:
    """Aggregates providers and retrieves in strict primary-source-first order."""

    def __init__(self, providers: List[SourceProvider]):
        # Sort by tier so lower tier numbers (more primary) are consulted first.
        self._providers = sorted(providers, key=lambda p: p.tier.value)

    def retrieve(self, symbol: str, window_days: int, retry_limit: int = 1) -> RetrievalResult:
        result = RetrievalResult()
        for provider in self._providers:
            attempts = 0
            while attempts < max(1, retry_limit):
                attempts += 1
                try:
                    docs = provider.search(symbol, window_days)
                    result.documents.extend(docs)
                    if docs:
                        result.opened_full = True  # we open underlying documents
                    break
                except SourceUnavailable:
                    if attempts >= max(1, retry_limit):
                        result.failed_tiers.append(provider.tier)
        return result

    def timestamps_for(self, doc: Document) -> TimeStamps:
        return TimeStamps(
            retrieval_time=utcnow(),
            publication_time=doc.published,
            data_as_of=doc.data_as_of or doc.published,
        )
