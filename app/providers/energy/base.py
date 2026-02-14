"""Energy price provider plugin contract (v1)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class EnergyPriceSlot:
    """Normalized half-hour energy price slot."""

    region: str
    valid_from: datetime
    valid_to: datetime
    price_pence: float
    currency: str = "GBP"
    source_timestamp: Optional[datetime] = None
    confidence: Optional[float] = None


@dataclass
class EnergyProviderMetadata:
    """Provider metadata for registry/status views."""

    provider_id: str
    display_name: str
    version: str
    supported_regions: List[str]
    description: Optional[str] = None


class EnergyPriceProvider(ABC):
    """Base interface for energy price providers."""

    provider_id: str = "unknown"

    @abstractmethod
    def get_metadata(self) -> EnergyProviderMetadata:
        """Return provider metadata."""

    @abstractmethod
    def validate_config(self, config: Optional[Dict]) -> Dict[str, str]:
        """Validate provider config. Return dict of field errors (empty = valid)."""

    @abstractmethod
    async def fetch_prices(
        self,
        region: str,
        start_utc: datetime,
        end_utc: datetime,
        config: Optional[Dict] = None,
    ) -> List[EnergyPriceSlot]:
        """Fetch normalized price slots for the provided UTC window."""

    async def get_current_price(
        self,
        region: str,
        at_utc: datetime,
        config: Optional[Dict] = None,
    ) -> Optional[EnergyPriceSlot]:
        """Default current-price helper using fetch_prices for a one-slot window."""
        slots = await self.fetch_prices(region, at_utc, at_utc, config)
        if not slots:
            return None

        for slot in slots:
            if slot.valid_from <= at_utc < slot.valid_to:
                return slot

        return slots[0]

    async def health_check(self, config: Optional[Dict] = None) -> Dict[str, object]:
        """Basic liveness contract. Providers can override for richer checks."""
        return {
            "status": "ok",
            "provider_id": self.provider_id,
        }
