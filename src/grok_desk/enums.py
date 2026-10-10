"""Shared enumerations: coverage states, source tiers, data freshness, statuses."""

from __future__ import annotations

from enum import Enum


class CoverageState(str, Enum):
    """Coverage states from guide section 7. Avoids forcing a conclusion.

    "No information found" must NOT automatically become "nothing happened".
    """

    COMPLETED_WITH_FINDINGS = "completed_with_material_findings"
    COMPLETED_NO_FINDINGS = "completed_with_no_material_findings"
    INCOMPLETE = "incomplete_coverage"
    NOT_CLASSIFIED = "not_classified"
    FAILED_RETRYABLE = "failed_but_retryable"
    NOT_DUE = "not_due"
    EVENT_NOT_TRIGGERED = "event_driven_and_not_triggered"

    @property
    def is_terminal_success(self) -> bool:
        return self in (
            CoverageState.COMPLETED_WITH_FINDINGS,
            CoverageState.COMPLETED_NO_FINDINGS,
        )


class SourceTier(int, Enum):
    """Primary-source-first ordering from guide section 7. Lower = higher priority."""

    COMPANY_IDENTITY_REGISTRY = 1
    EXCHANGE_FILINGS = 2  # NSE / BSE filings and market publications
    INVESTOR_RELATIONS = 3
    REGULATOR = 4  # SEBI and other regulators
    GOVERNMENT = 5  # Government of India / ministry publications
    FUND_DISCLOSURE = 6  # AMFI and fund-house disclosures
    SECONDARY = 7  # Secondary reporting, must be clearly labelled

    @property
    def is_primary(self) -> bool:
        return self.value <= SourceTier.FUND_DISCLOSURE.value


class DataFreshness(str, Enum):
    """Market-data freshness labels from guide section 15."""

    LIVE = "live"
    DELAYED = "delayed"
    END_OF_DAY = "end_of_day"
    HISTORICAL = "historical"
    LATEST_AVAILABLE = "latest_available"


class DeliveryStatus(str, Enum):
    """Delivery/duplicate-control statuses from guide section 10."""

    OPEN = "open"
    PENDING_DELIVERY = "pending_delivery"
    DELIVERED = "delivered"
    PARTIAL = "partial"
    FAILED = "failed"


class LeadDecision(str, Enum):
    """A Lead's explicit decision on a handoff (guide section 9).

    Message delivery by itself is NOT research acceptance.
    """

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CORRECTION_REQUESTED = "correction_requested"
    INCOMPLETE = "marked_incomplete"


class RoutineState(str, Enum):
    PAUSED = "paused"
    ACTIVE = "active"
    RETIRED = "retired"


class Department(str, Enum):
    CHIEF = "Chief"
    MARKET_NEWS = "Market News Research"
    EQUITY_RESEARCH = "Equity Research"
    INDUSTRY_GEO = "Industry and Geopolitical Research"
    MARKET_ACTIVITY = "Market Activity and Ownership"
    INDEPENDENT_REVIEW = "Independent Research Review"
