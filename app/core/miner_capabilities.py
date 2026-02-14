"""
Miner capability registry for strategy/policy logic.

Provides a single place to resolve miner modes and strategy field mappings,
with dynamic driver introspection and safe baseline fallbacks.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class MinerCapability:
    miner_type: str
    display_name: str
    available_modes: List[str]
    champion_lowest_mode: Optional[str]


# Baseline fallback contract (used when dynamic loader is unavailable)
_FALLBACK_CAPABILITIES: Dict[str, MinerCapability] = {
    "bitaxe": MinerCapability(
        miner_type="bitaxe",
        display_name="Bitaxe 601",
        available_modes=["eco", "standard", "turbo", "oc"],
        champion_lowest_mode="eco",
    ),
    "nerdqaxe": MinerCapability(
        miner_type="nerdqaxe",
        display_name="NerdQaxe++",
        available_modes=["eco", "standard", "turbo", "oc"],
        champion_lowest_mode="eco",
    ),
    "avalon_nano": MinerCapability(
        miner_type="avalon_nano",
        display_name="Avalon Nano 3/3S",
        available_modes=["low", "med", "high"],
        champion_lowest_mode="low",
    ),
    "nmminer": MinerCapability(
        miner_type="nmminer",
        display_name="NMMiner ESP32",
        available_modes=["fixed"],
        champion_lowest_mode="fixed",
    ),
}


def _humanize_miner_type(miner_type: str) -> str:
    parts = [p for p in miner_type.replace("-", "_").split("_") if p]
    if not parts:
        return miner_type
    return " ".join(part.capitalize() for part in parts)


def _normalize_modes(raw_modes: Optional[List[str]], miner_type: str) -> List[str]:
    if raw_modes:
        normalized = [str(m) for m in raw_modes if m]
        if normalized:
            return normalized

    fallback = _FALLBACK_CAPABILITIES.get(miner_type)
    return list(fallback.available_modes) if fallback else []


def _fallback_capability(miner_type: str) -> MinerCapability:
    fallback = _FALLBACK_CAPABILITIES.get(miner_type)
    if fallback:
        return fallback
    return MinerCapability(
        miner_type=miner_type,
        display_name=_humanize_miner_type(miner_type),
        available_modes=[],
        champion_lowest_mode=None,
    )


def get_miner_capabilities() -> Dict[str, MinerCapability]:
    """
    Return capabilities keyed by miner type.

    Uses loaded dynamic drivers when available and merges with baseline fallbacks
    so strategy logic remains stable during startup and reload transitions.
    """
    capabilities: Dict[str, MinerCapability] = dict(_FALLBACK_CAPABILITIES)

    try:
        from core.miner_loader import get_miner_loader

        loader = get_miner_loader()
        for miner_type, driver_class in loader.drivers.items():
            fallback = _fallback_capability(miner_type)

            modes = _normalize_modes(getattr(driver_class, "MODES", None), miner_type)
            champion_lowest_mode = getattr(driver_class, "CHAMPION_LOWEST_MODE", None)
            if not champion_lowest_mode:
                champion_lowest_mode = fallback.champion_lowest_mode
            if not champion_lowest_mode and modes:
                champion_lowest_mode = modes[0]

            display_name = getattr(driver_class, "DISPLAY_NAME", None) or getattr(driver_class, "NAME", None)
            if not display_name:
                display_name = fallback.display_name

            capabilities[miner_type] = MinerCapability(
                miner_type=miner_type,
                display_name=display_name,
                available_modes=modes,
                champion_lowest_mode=champion_lowest_mode,
            )
    except Exception:
        # Loader unavailable during early startup/import: fallback-only is valid
        pass

    return capabilities


def get_strategy_mode_map() -> Dict[str, List[str]]:
    """Return miner_type -> valid strategy modes for band validation."""
    mode_map: Dict[str, List[str]] = {}
    for miner_type, capability in get_miner_capabilities().items():
        if not capability.available_modes:
            continue

        modes = list(capability.available_modes)
        if "managed_externally" not in modes:
            modes.insert(0, "managed_externally")
        mode_map[miner_type] = modes

    return mode_map


def get_champion_lowest_mode(miner_type: str) -> str:
    """Return lowest champion mode for miner type, with safe fallback."""
    capability = get_miner_capabilities().get(miner_type)
    if capability and capability.champion_lowest_mode:
        return capability.champion_lowest_mode
    return "eco"
