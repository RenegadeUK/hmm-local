"""\
BTC Stack (CKPool) Local Stratum Driver

Targets a "btc-stack" style single-container deployment:
- Bitcoin Core node (bitcoind + bitcoin-cli)
- CKPool stratum endpoint (default port 3333)
- Manager API (default port 8083) providing health/metrics at /api/v1/*

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

__version__ = "1.0.1"


class BTCStackIntegration(BasePoolIntegration):
    pool_type = "btc_stack"
    display_name = "BTC Stack (Local CKPool Stratum)"
    driver_version = __version__
    documentation_url = "https://github.com/RenegadeUK/hmm-local"
    supports_coins = ["BTC"]
    requires_api_key = False

    DEFAULT_STRATUM_PORT = 3333
    DEFAULT_MANAGER_PORT = 8083
    HTTP_TIMEOUT_S = 4.0
    TCP_TIMEOUT_S = 3.0

    def get_pool_templates(self) -> List[PoolTemplate]:
        return [
            PoolTemplate(
                template_id="btc_stack_local_btc",
                display_name="BTC Stack BTC (Local)",
                url="192.168.1.100",
                port=self.DEFAULT_STRATUM_PORT,
                coin="BTC",
                mining_model=MiningModel.SOLO,
                region="Local",
                requires_auth=False,
                supports_shares=False,
                supports_earnings=False,
                supports_balance=False,
                description="Local BTC stack CKPool stratum endpoint (edit URL to your host/IP)",
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
        base = self._manager_base_url(url, None)
        payload = await self._http_get_json(f"{base}/api/v1/ready")
        if payload and isinstance(payload, dict):
            ready = payload.get("ready")
            if ready is True or payload.get("ok") is True:
                return True
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
            status.additional_info["manager_ready"] = ready.get("ready") if "ready" in ready else ready.get("ok")
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

        return PoolStats(
            hashrate=None,
            active_workers=None,
            blocks_found=blocks_found,
            network_difficulty=difficulty,
            additional_stats=additional,
        )

    async def get_blocks(self, url: str, coin: str, hours: int = 24, **kwargs) -> List[PoolBlock]:
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
            health_message=None if health.is_healthy else (health.error_message or "Unhealthy"),
            latency_ms=health.latency_ms,
            network_difficulty=stats.network_difficulty if stats else None,
            blocks_found_24h=stats.blocks_found if stats else None,
            currency=coin.upper() if coin else None,
            last_updated=datetime.utcnow(),
        )

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

        return tile
