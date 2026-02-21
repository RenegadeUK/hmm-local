"""\
DGB Stack (CKPool) Local Stratum Driver

This pool driver targets the "dgb-stack" single-container deployment:
- CKPool stratum endpoint (default port 3335)
- Manager API (default port 8085) providing health/metrics at /api/v1/*

The driver:
- Performs a direct TCP connect health check to the stratum endpoint.
- Optionally enriches stats using the manager API when reachable.

Notes:
- This is a LOCAL pool integration; it does not require an API key.
- If the manager API is unreachable, health still works via stratum TCP.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from integrations.base_pool import (
    BasePoolIntegration,
    DashboardTileData,
    MiningModel,
    PoolHealthStatus,
    PoolStats,
    PoolTemplate,
    PoolBlock,
)

logger = logging.getLogger(__name__)

__version__ = "1.0.0"


class DGBStackIntegration(BasePoolIntegration):
    """Integration for the DGB stack CKPool stratum + manager API."""

    pool_type = "dgb_stack"
    display_name = "DGB Stack (Local CKPool Stratum)"
    driver_version = __version__
    documentation_url = "https://github.com/RenegadeUK/hmm-local"
    supports_coins = ["DGB"]
    requires_api_key = False

    DEFAULT_STRATUM_PORT = 3335
    DEFAULT_MANAGER_PORT = 8085
    HTTP_TIMEOUT_S = 4.0
    TCP_TIMEOUT_S = 3.0

    def get_pool_templates(self) -> List[PoolTemplate]:
        # This is a local deployment; provide a single template that users can
        # point at their host/IP (they can also create YAML configs directly).
        return [
            PoolTemplate(
                template_id="dgb_stack_local_dgb",
                display_name="DGB Stack DGB (Local)",
                url="192.168.1.100",
                port=self.DEFAULT_STRATUM_PORT,
                coin="DGB",
                mining_model=MiningModel.SOLO,
                region="Local",
                requires_auth=False,
                supports_shares=False,
                supports_earnings=False,
                supports_balance=False,
                description="Local DGB stack CKPool stratum endpoint (edit URL to your host/IP)",
                fee_percent=0.0,
            )
        ]

    def _manager_base_url(self, url: str, manager_port: Optional[int] = None) -> str:
        clean_url = url.replace("http://", "").replace("https://", "").split("/")[0]
        clean_url = clean_url.split(":")[0]
        port = int(manager_port or self.DEFAULT_MANAGER_PORT)
        return f"http://{clean_url}:{port}"

    async def _http_get_json(self, full_url: str) -> Optional[dict[str, Any]]:
        timeout = aiohttp.ClientTimeout(total=self.HTTP_TIMEOUT_S)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(full_url) as resp:
                    if resp.status != 200:
                        return None
                    return await resp.json()
        except Exception:
            return None

    async def _tcp_check(self, url: str, port: int) -> tuple[bool, Optional[float], Optional[str]]:
        start = time.time()
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(url, int(port)),
                timeout=self.TCP_TIMEOUT_S,
            )
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            latency_ms = (time.time() - start) * 1000
            return True, latency_ms, None
        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            return False, latency_ms, str(e)

    async def detect(self, url: str, port: int) -> bool:
        # Prefer positive identification via manager API when available.
        base = self._manager_base_url(url, None)
        payload = await self._http_get_json(f"{base}/api/v1/ready")
        if payload and isinstance(payload, dict):
            # DGB stack /api/v1/ready returns a JSON object with a "ready" boolean.
            if payload.get("ready") is True:
                return True

        # Fall back to heuristic: default local stratum port.
        return int(port) == self.DEFAULT_STRATUM_PORT

    async def get_health(self, url: str, port: int, **kwargs) -> PoolHealthStatus:
        manager_port = kwargs.get("manager_port")

        ok, latency_ms, err = await self._tcp_check(url, int(port))
        status = PoolHealthStatus(
            is_healthy=ok,
            latency_ms=latency_ms,
            error_message=None if ok else (err or "stratum TCP check failed"),
            additional_info={},
        )

        base = self._manager_base_url(url, manager_port)
        ready = await self._http_get_json(f"{base}/api/v1/ready")
        if ready and isinstance(ready, dict):
            status.additional_info["manager_ready"] = ready.get("ready")
            status.additional_info["manager_port"] = int(manager_port or self.DEFAULT_MANAGER_PORT)
            services = ready.get("services")
            if isinstance(services, dict):
                status.additional_info["services"] = services

        return status

    async def get_network_difficulty(self, coin: str, **kwargs) -> Optional[float]:
        url = kwargs.get("url")
        if not url:
            return None

        manager_port = kwargs.get("manager_port")
        base = self._manager_base_url(str(url), manager_port)

        mining = await self._http_get_json(f"{base}/api/v1/node/mining")
        if not mining or not isinstance(mining, dict):
            return None

        if mining.get("ok") is not True:
            return None

        data = mining.get("data")
        if not isinstance(data, dict):
            return None

        diff = data.get("difficulty")
        try:
            return float(diff) if diff is not None else None
        except Exception:
            return None

    async def get_pool_stats(self, url: str, coin: str, **kwargs) -> Optional[PoolStats]:
        manager_port = kwargs.get("manager_port")
        base = self._manager_base_url(url, manager_port)

        metrics = await self._http_get_json(f"{base}/api/v1/ckpool/metrics")
        difficulty = await self.get_network_difficulty(coin, url=url, manager_port=manager_port)

        additional: Dict[str, Any] = {}
        blocks_found: Optional[int] = None
        hashrate: Any = None
        active_workers: Optional[int] = None

        if metrics and isinstance(metrics, dict):
            shares = metrics.get("shares")
            if isinstance(shares, dict):
                additional["shares"] = shares
            blocks = metrics.get("blocks")
            if isinstance(blocks, dict):
                additional["blocks"] = blocks
                found = blocks.get("found")
                if isinstance(found, int):
                    blocks_found = found
            auth = metrics.get("auth")
            if isinstance(auth, dict):
                additional["auth"] = auth
            best_share_diff = metrics.get("best_share_diff")
            if best_share_diff is not None:
                additional["best_share_diff"] = best_share_diff
            connectivity = metrics.get("connectivity")
            if isinstance(connectivity, dict):
                additional["connectivity"] = connectivity

            summary = metrics.get("summary")
            if isinstance(summary, dict):
                additional["summary"] = summary
                # hashrate dict is compatible with HMM's unit-aware formatter
                hashrate_candidate = summary.get("hashrate")
                if isinstance(hashrate_candidate, dict):
                    hashrate = hashrate_candidate
                workers_candidate = summary.get("workers")
                if isinstance(workers_candidate, int):
                    active_workers = workers_candidate

        return PoolStats(
            hashrate=hashrate,
            active_workers=active_workers,
            blocks_found=blocks_found,
            network_difficulty=difficulty,
            additional_stats=additional,
        )

    async def get_blocks(self, url: str, coin: str, hours: int = 24, **kwargs) -> List[PoolBlock]:
        # CKPool manager API currently only exposes aggregate metrics, not a block list.
        return []

    async def get_dashboard_data(
        self,
        url: str,
        coin: str,
        username: Optional[str] = None,
        **kwargs,
    ) -> Optional[DashboardTileData]:
        port_raw = kwargs.get("port") or kwargs.get("stratum_port")
        try:
            stratum_port = int(port_raw) if port_raw is not None else self.DEFAULT_STRATUM_PORT
        except Exception:
            stratum_port = self.DEFAULT_STRATUM_PORT

        health = await self.get_health(url, stratum_port, **kwargs)
        stats = await self.get_pool_stats(url, coin, **kwargs)

        tile = DashboardTileData(
            health_status=bool(health.is_healthy),
            health_message="OK" if health.is_healthy else (health.error_message or "Unhealthy"),
            latency_ms=health.latency_ms,
            network_difficulty=stats.network_difficulty if stats else None,
            blocks_found_24h=stats.blocks_found if stats else None,
            currency=coin.upper() if coin else None,
            last_updated=datetime.utcnow(),
        )

        if stats and stats.hashrate is not None:
            tile.pool_hashrate = stats.hashrate

        if stats and isinstance(stats.additional_stats, dict):
            shares = stats.additional_stats.get("shares")
            if isinstance(shares, dict):
                tile.shares_valid = shares.get("accepted")
                tile.shares_invalid = shares.get("rejected")
                tile.shares_stale = shares.get("stale")

                try:
                    accepted = int(tile.shares_valid or 0)
                    rejected = int(tile.shares_invalid or 0)
                    stale = int(tile.shares_stale or 0)
                    total = accepted + rejected + stale
                    tile.reject_rate = round((rejected / total) * 100.0, 2) if total > 0 else 0.0
                except Exception:
                    pass

            # If we only have ckpool summary shares (no per-share log lines), use the summary.
            summary = stats.additional_stats.get("summary")
            if isinstance(summary, dict) and (tile.shares_valid is None or int(tile.shares_valid or 0) == 0):
                summary_shares = summary.get("shares")
                if isinstance(summary_shares, int):
                    tile.shares_valid = summary_shares

        return tile
