"""Offline fixtures: a small approved company universe and mock source documents.

These stand in for real providers so the whole desk runs deterministically. The
company universe is intentionally tiny and explicit -- it is never expanded from
model memory.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Dict, List

from .company import Company, CompanyRegistry
from .enums import DataFreshness, SourceTier
from .sources import Document, MockSourceProvider, SourceDesk
from .timestamps import utcnow

# Approved universe (NSE/BSE listed Indian equities) -- explicit, bounded.
APPROVED_COMPANIES = [
    Company("Reliance Industries Limited", "RELIANCE", "500325", ("Reliance", "RIL")),
    Company("Tata Consultancy Services Limited", "TCS", "532540", ("TCS",)),
    Company("Infosys Limited", "INFY", "500209", ("Infosys",)),
    Company("HDFC Bank Limited", "HDFCBANK", "500180", ("HDFC Bank",)),
]


def build_registry(available: bool = True) -> CompanyRegistry:
    return CompanyRegistry(APPROVED_COMPANIES, available=available)


def _doc(tier: SourceTier, title: str, slug: str, days_ago: int) -> Document:
    published = utcnow() - timedelta(days=days_ago)
    return Document(
        tier=tier,
        title=title,
        url=f"https://example.test/{slug}",
        body=f"Primary document: {title}",
        published=published,
        data_as_of=published,
        freshness=DataFreshness.LATEST_AVAILABLE,
    )


def _fixtures() -> Dict[SourceTier, Dict[str, List[Document]]]:
    """Per-tier fixtures keyed by symbol."""
    return {
        SourceTier.EXCHANGE_FILINGS: {
            "RELIANCE": [_doc(SourceTier.EXCHANGE_FILINGS, "RELIANCE board meeting outcome filed with NSE", "rel-filing", 1)],
            "TCS": [_doc(SourceTier.EXCHANGE_FILINGS, "TCS quarterly results intimation to BSE", "tcs-filing", 2)],
        },
        SourceTier.INVESTOR_RELATIONS: {
            "RELIANCE": [_doc(SourceTier.INVESTOR_RELATIONS, "RELIANCE investor presentation published", "rel-ir", 1)],
        },
        SourceTier.FUND_DISCLOSURE: {
            "HDFCBANK": [_doc(SourceTier.FUND_DISCLOSURE, "AMFI monthly fund holdings update for HDFCBANK", "hdfc-amfi", 3)],
        },
    }


def build_source_desk(outage_tiers: List[SourceTier] = None) -> SourceDesk:
    """Build a SourceDesk across all tiers, optionally forcing some into outage."""
    outage_tiers = outage_tiers or []
    fixtures = _fixtures()
    providers = []
    for tier in SourceTier:
        tier_fixtures = fixtures.get(tier, {})
        providers.append(
            MockSourceProvider(tier=tier, fixtures=tier_fixtures, outage=tier in outage_tiers)
        )
    return SourceDesk(providers)
