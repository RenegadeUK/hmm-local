"""Stratum status API

Provides a hardware-focused view of local CKPool stratum stacks (DGB/BCH/BTC).

This intentionally does NOT rely on the dashboard tile model; it returns richer,
windowed stats (15m/24h/total) and recent CKPool events.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import Pool
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stratum", tags=["stratum"])


_POOL_TYPE_BY_COIN: dict[str, str] = {
    "DGB": "dgb_stack",
    "BCH": "bch_stack",
    "BTC": "btc_stack",
}

_DEFAULT_MANAGER_PORT_BY_POOL_TYPE: dict[str, int] = {
    "dgb_stack": 8085,
    "bch_stack": 8084,
    "btc_stack": 8083,
}


def _manager_base_url(pool: Pool) -> str:
    manager_port = None
    if isinstance(pool.pool_config, dict):
        manager_port = pool.pool_config.get("manager_port")

    port = int(manager_port or _DEFAULT_MANAGER_PORT_BY_POOL_TYPE.get(pool.pool_type, 0) or 0)
    if not port:
        raise HTTPException(status_code=400, detail=f"unknown manager port for pool_type={pool.pool_type}")

    host = str(pool.url).replace("http://", "").replace("https://", "").split("/")[0]
    host = host.split(":")[0]
    return f"http://{host}:{port}"


async def _get_json(client: httpx.AsyncClient, url: str, timeout_s: float = 5.0, retries: int = 1) -> Optional[dict[str, Any]]:
    attempts = max(1, retries + 1)
    for attempt in range(attempts):
        try:
            resp = await client.get(url, timeout=timeout_s)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}")
            data = resp.json()
            return data if isinstance(data, dict) else None
        except Exception as exc:
            if attempt >= attempts - 1:
                logger.warning("stratum fetch failed: url=%s err=%s", url, exc)
                return None
            await asyncio.sleep(0.25)
    return None


def _pick_events(events_payload: Optional[dict[str, Any]], limit: int = 50) -> list[dict[str, Any]]:
    if not events_payload or not isinstance(events_payload, dict):
        return []
    items = events_payload.get("events")
    if not isinstance(items, list):
        return []

    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "timestamp": item.get("timestamp"),
                "severity": item.get("severity"),
                "event_type": item.get("event_type"),
                "source": item.get("source"),
                "message": item.get("message"),
            }
        )
        if len(out) >= limit:
            break
    return out


@router.get("/{coin}")
async def get_stratum_status(coin: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    coin_upper = str(coin or "").upper()
    pool_type = _POOL_TYPE_BY_COIN.get(coin_upper)
    if not pool_type:
        raise HTTPException(status_code=400, detail="unsupported coin; expected DGB/BCH/BTC")

    result = await db.execute(
        select(Pool)
        .where(Pool.enabled == True, Pool.pool_type == pool_type)
        .order_by(Pool.id.asc())
    )
    pool = result.scalars().first()
    if not pool:
        raise HTTPException(status_code=404, detail=f"no enabled pool found for {coin_upper} ({pool_type})")

    base = _manager_base_url(pool)

    since = (datetime.utcnow() - timedelta(hours=6)).isoformat()

    async with httpx.AsyncClient() as client:
        ready_task = _get_json(client, f"{base}/api/v1/ready", timeout_s=4.0, retries=1)
        metrics_task = _get_json(client, f"{base}/api/v1/ckpool/metrics", timeout_s=6.0, retries=1)
        mining_task = _get_json(client, f"{base}/api/v1/node/mining", timeout_s=4.0, retries=0)
        events_task = _get_json(
            client,
            f"{base}/api/v1/events?since={since}&limit=200&order=desc",
            timeout_s=10.0,
            retries=0,
        )

        ready, metrics, mining, events_payload = await asyncio.gather(
            ready_task, metrics_task, mining_task, events_task
        )

    shares = (metrics or {}).get("shares") if isinstance(metrics, dict) else None
    summary = (metrics or {}).get("summary") if isinstance(metrics, dict) else None
    blocks = (metrics or {}).get("blocks") if isinstance(metrics, dict) else None

    def as_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except Exception:
            return None

    response: dict[str, Any] = {
        "timestamp": datetime.utcnow().isoformat(),
        "coin": coin_upper,
        "pool": {
            "id": pool.id,
            "name": pool.name,
            "pool_type": pool.pool_type,
            "stratum": {
                "host": pool.url,
                "port": pool.port,
            },
            "manager": {
                "base_url": base,
            },
        },
        "ready": ready,
        "node": {
            "mining": mining,
        },
        "ckpool": {
            "metrics": {
                "summary": summary,
                "shares": shares,
                "blocks": blocks,
            },
            "events": _pick_events(events_payload, limit=80),
        },
        "computed": {
            "workers_online": as_int((summary or {}).get("workers")) if isinstance(summary, dict) else None,
            "hashrate": (summary or {}).get("hashrate") if isinstance(summary, dict) else None,
            "shares_total": as_int((shares or {}).get("accepted")) if isinstance(shares, dict) else None,
            "shares_24h": as_int((shares or {}).get("accepted_24h")) if isinstance(shares, dict) else None,
            "shares_15m": as_int((shares or {}).get("accepted_15m")) if isinstance(shares, dict) else None,
            "workers_down_for_s": (summary or {}).get("workers_down_for_s") if isinstance(summary, dict) else None,
            "workers_min_15m": (summary or {}).get("workers_min_15m") if isinstance(summary, dict) else None,
            "workers_max_15m": (summary or {}).get("workers_max_15m") if isinstance(summary, dict) else None,
            "last_block_event": next(
                (
                    e
                    for e in _pick_events(events_payload, limit=200)
                    if e.get("event_type") == "block_found"
                ),
                None,
            ),
        },
    }

    return response
