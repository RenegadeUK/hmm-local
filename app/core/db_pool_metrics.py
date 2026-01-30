"""Database pool high-water mark tracking (daily + since boot)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from core.config import settings


METRICS_PATH = settings.CONFIG_DIR / "db_pool_metrics.json"


@dataclass
class PoolMetrics:
    db_pool_in_use_peak: int = 0
    db_pool_wait_count: int = 0
    db_pool_wait_seconds_sum: float = 0.0
    active_queries_peak: int = 0
    slow_query_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "db_pool_in_use_peak": self.db_pool_in_use_peak,
            "db_pool_wait_count": self.db_pool_wait_count,
            "db_pool_wait_seconds_sum": round(self.db_pool_wait_seconds_sum, 2),
            "active_queries_peak": self.active_queries_peak,
            "slow_query_count": self.slow_query_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PoolMetrics":
        return cls(
            db_pool_in_use_peak=int(data.get("db_pool_in_use_peak", 0)),
            db_pool_wait_count=int(data.get("db_pool_wait_count", 0)),
            db_pool_wait_seconds_sum=float(data.get("db_pool_wait_seconds_sum", 0.0)),
            active_queries_peak=int(data.get("active_queries_peak", 0)),
            slow_query_count=int(data.get("slow_query_count", 0)),
        )


@dataclass
class MetricsStore:
    last_24h_date: str
    last_24h: PoolMetrics
    since_boot: PoolMetrics

    def to_dict(self) -> Dict[str, Any]:
        return {
            "last_24h_date": self.last_24h_date,
            "last_24h": self.last_24h.to_dict(),
            "since_boot": self.since_boot.to_dict(),
        }


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_store() -> MetricsStore:
    if METRICS_PATH.exists():
        with open(METRICS_PATH, "r") as f:
            data = json.load(f)
        return MetricsStore(
            last_24h_date=data.get("last_24h_date", _today_key()),
            last_24h=PoolMetrics.from_dict(data.get("last_24h", {})),
            since_boot=PoolMetrics.from_dict(data.get("since_boot", {})),
        )

    return MetricsStore(
        last_24h_date=_today_key(),
        last_24h=PoolMetrics(),
        since_boot=PoolMetrics(),
    )


def _save_store(store: MetricsStore) -> None:
    settings.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(METRICS_PATH, "w") as f:
        json.dump(store.to_dict(), f, indent=2)


def _roll_daily(store: MetricsStore) -> MetricsStore:
    today = _today_key()
    if store.last_24h_date != today:
        store.last_24h_date = today
        store.last_24h = PoolMetrics()
    return store


def update_peaks(
    *,
    in_use: int,
    active_queries: int = 0,
    slow_queries: int = 0,
) -> MetricsStore:
    store = _roll_daily(_load_store())

    store.last_24h.db_pool_in_use_peak = max(store.last_24h.db_pool_in_use_peak, in_use)
    store.since_boot.db_pool_in_use_peak = max(store.since_boot.db_pool_in_use_peak, in_use)

    store.last_24h.active_queries_peak = max(store.last_24h.active_queries_peak, active_queries)
    store.since_boot.active_queries_peak = max(store.since_boot.active_queries_peak, active_queries)

    if slow_queries > 0:
        store.last_24h.slow_query_count += slow_queries
        store.since_boot.slow_query_count += slow_queries

    _save_store(store)
    return store


def record_pool_timeout(wait_seconds: float) -> MetricsStore:
    store = _roll_daily(_load_store())

    store.last_24h.db_pool_wait_count += 1
    store.since_boot.db_pool_wait_count += 1

    store.last_24h.db_pool_wait_seconds_sum += wait_seconds
    store.since_boot.db_pool_wait_seconds_sum += wait_seconds

    _save_store(store)
    return store


def get_metrics() -> MetricsStore:
    return _roll_daily(_load_store())
