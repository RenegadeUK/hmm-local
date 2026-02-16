"""Pool warning derivation helpers for dashboard metadata."""

from __future__ import annotations


def derive_pool_warnings(pool_type: str | None, driver_available: bool) -> list[str]:
    """
    Return warning codes for pool metadata based on driver resolution state.

    Warning codes:
    - driver_unresolved: pool_type missing/unknown
    - driver_not_loaded: pool_type set but corresponding driver unavailable
    """
    normalized = (pool_type or "").strip().lower()
    if not normalized or normalized == "unknown":
        return ["driver_unresolved"]
    if not driver_available:
        return ["driver_not_loaded"]
    return []
