"""Approved company universe / identity registry (guide sections 7 and 15).

Resolve the canonical name, exchange symbol and aliases before research. If the
identity service is unavailable, use only an explicitly approved fallback
universe and report the outage. The company universe is NEVER expanded from
model memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Company:
    canonical_name: str
    nse_symbol: Optional[str]
    bse_code: Optional[str]
    aliases: tuple = field(default_factory=tuple)


class IdentityRegistryUnavailable(Exception):
    """Raised when the identity service is down and no fallback is approved."""


class CompanyRegistry:
    """Resolves company identity from an approved universe only."""

    def __init__(self, companies: List[Company], available: bool = True):
        self._companies = list(companies)
        self._available = available
        self._index: Dict[str, Company] = {}
        for c in self._companies:
            self._index[c.canonical_name.lower()] = c
            if c.nse_symbol:
                self._index[c.nse_symbol.lower()] = c
            if c.bse_code:
                self._index[c.bse_code.lower()] = c
            for a in c.aliases:
                self._index[a.lower()] = c

    @property
    def available(self) -> bool:
        return self._available

    def set_available(self, value: bool) -> None:
        self._available = value

    def resolve(self, token: str) -> Optional[Company]:
        """Resolve a token to an approved company, or None if not in the universe.

        Raises IdentityRegistryUnavailable if the registry is down -- callers must
        report the outage rather than guessing identities from memory.
        """
        if not self._available:
            raise IdentityRegistryUnavailable(
                "Company identity registry is unavailable; outage must be reported."
            )
        return self._index.get(token.strip().lower())

    def is_approved(self, token: str) -> bool:
        try:
            return self.resolve(token) is not None
        except IdentityRegistryUnavailable:
            return False

    def universe(self) -> List[Company]:
        return list(self._companies)
