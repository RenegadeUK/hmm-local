"""Dynamic loader for energy price provider plugins."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Dict, List, Optional

from providers.energy.base import EnergyPriceProvider

logger = logging.getLogger(__name__)


class EnergyProviderLoader:
    """Loads energy providers from /config/providers/energy/."""

    def __init__(self, config_path: str = "/config"):
        self.config_path = Path(config_path)
        self.providers_path = self.config_path / "providers" / "energy"
        self.providers: Dict[str, EnergyPriceProvider] = {}

    def load_all(self) -> None:
        self.load_providers()

    def load_providers(self) -> None:
        self.providers.clear()

        if not self.providers_path.exists():
            logger.warning(f"Energy providers directory not found: {self.providers_path}")
            return

        for file_path in self.providers_path.glob("*_provider.py"):
            try:
                spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
                if not spec or not spec.loader:
                    logger.error(f"Failed to create module spec for {file_path}")
                    continue

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, EnergyPriceProvider)
                        and attr is not EnergyPriceProvider
                    ):
                        instance: EnergyPriceProvider = attr()
                        provider_id = getattr(instance, "provider_id", None)
                        if not provider_id:
                            logger.warning(
                                f"Energy provider class {attr.__name__} in {file_path.name} "
                                "missing provider_id"
                            )
                            continue

                        self.providers[provider_id] = instance
                        logger.info(f"Loaded energy provider: {provider_id} from {file_path.name}")
            except Exception as exc:
                logger.error(f"Failed to load energy provider {file_path.name}: {exc}")

        logger.info(f"Loaded {len(self.providers)} energy providers: {list(self.providers.keys())}")

    def get_provider(self, provider_id: str) -> Optional[EnergyPriceProvider]:
        return self.providers.get(provider_id)

    def get_default_provider(self) -> Optional[EnergyPriceProvider]:
        if not self.providers:
            return None

        # Prefer Octopus Agile if present for backward compatibility.
        if "octopus_agile" in self.providers:
            return self.providers["octopus_agile"]

        return next(iter(self.providers.values()))

    def get_provider_ids(self) -> List[str]:
        return list(self.providers.keys())


_energy_provider_loader: Optional[EnergyProviderLoader] = None


def init_energy_provider_loader(config_path: str = "/config") -> EnergyProviderLoader:
    global _energy_provider_loader
    _energy_provider_loader = EnergyProviderLoader(config_path)
    _energy_provider_loader.load_all()
    return _energy_provider_loader


def get_energy_provider_loader() -> EnergyProviderLoader:
    if _energy_provider_loader is None:
        raise RuntimeError("Energy provider loader not initialized. Call init_energy_provider_loader() first.")
    return _energy_provider_loader
