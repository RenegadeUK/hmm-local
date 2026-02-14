"""Octopus Agile energy provider plugin (reference implementation)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from urllib.parse import urlencode

import aiohttp

from providers.energy.base import EnergyPriceProvider, EnergyPriceSlot, EnergyProviderMetadata

__version__ = "1.0.1"


class OctopusAgileEnergyProvider(EnergyPriceProvider):
    """Fetches Agile UK 30-minute price slots from Octopus public API."""

    provider_id = "octopus_agile"

    API_TEMPLATES = [
        # Active Agile tariff (current)
        (
            "AGILE-24-10-01",
            "https://api.octopus.energy/v1/products/AGILE-24-10-01/"
            "electricity-tariffs/E-1R-AGILE-24-10-01-{region}/standard-unit-rates/",
        ),
        # Legacy fallback
        (
            "AGILE-FLEX-22-11-25",
            "https://api.octopus.energy/v1/products/AGILE-FLEX-22-11-25/"
            "electricity-tariffs/E-1R-AGILE-FLEX-22-11-25-{region}/standard-unit-rates/",
        ),
    ]

    def get_metadata(self) -> EnergyProviderMetadata:
        return EnergyProviderMetadata(
            provider_id=self.provider_id,
            display_name="Octopus Agile (UK)",
            version=__version__,
            supported_regions=[
                "A", "B", "C", "D", "E", "F", "G", "H",
                "J", "K", "L", "M", "N", "P",
            ],
            description="Public Octopus Agile tariff provider (30-minute slots).",
        )

    def validate_config(self, config: Optional[Dict]) -> Dict[str, str]:
        errors: Dict[str, str] = {}
        cfg = config or {}

        region = (cfg.get("region") or "H").upper()
        if region not in self.get_metadata().supported_regions:
            errors["region"] = f"Unsupported region '{region}'"

        return errors

    async def fetch_prices(
        self,
        region: str,
        start_utc: datetime,
        end_utc: datetime,
        config: Optional[Dict] = None,
    ) -> List[EnergyPriceSlot]:
        # NOTE: Octopus API returns broad pages; scheduler/repository should upsert/filter window.
        now = datetime.utcnow()
        errors: List[str] = []

        query_from = (start_utc - timedelta(hours=12)).replace(microsecond=0).isoformat() + "Z"
        query_to = (end_utc + timedelta(hours=12)).replace(microsecond=0).isoformat() + "Z"
        query = urlencode({
            "period_from": query_from,
            "period_to": query_to,
            "page_size": 500,
        })

        for product_code, template in self.API_TEMPLATES:
            url = f"{template.format(region=region.upper())}?{query}"

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=10) as resp:
                        resp.raise_for_status()
                        payload = await resp.json()
            except Exception as e:
                errors.append(f"{product_code}: {e}")
                continue

            rows = payload.get("results", [])
            if not rows:
                errors.append(f"{product_code}: no results")
                continue

            parsed = []
            for item in rows:
                valid_from = datetime.fromisoformat(item["valid_from"].replace("Z", "+00:00"))
                valid_to = datetime.fromisoformat(item["valid_to"].replace("Z", "+00:00"))
                parsed.append((valid_from, valid_to, float(item["value_inc_vat"])))

            freshest_valid_to = max(vt for _, vt, _ in parsed)
            freshest_naive = freshest_valid_to.replace(tzinfo=None)

            # Reject stale tariff pages (historical products) and try next template.
            if freshest_naive < (now - timedelta(hours=12)):
                errors.append(
                    f"{product_code}: stale data (max valid_to {freshest_valid_to.isoformat()})"
                )
                continue

            slots: List[EnergyPriceSlot] = []
            for valid_from, valid_to, price in parsed:
                slots.append(
                    EnergyPriceSlot(
                        region=region.upper(),
                        valid_from=valid_from.replace(tzinfo=None),
                        valid_to=valid_to.replace(tzinfo=None),
                        price_pence=price,
                        currency="GBP",
                        source_timestamp=datetime.utcnow(),
                    )
                )

            return slots

        raise RuntimeError(f"Failed to fetch non-stale Agile prices: {'; '.join(errors)}")
