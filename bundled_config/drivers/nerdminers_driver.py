"""
NerdMiners.org Pool Integration
Public solo mining pool for Bitcoin with simple REST API
"""
import aiohttp
import logging
import re
from typing import Optional, List, Dict, Any
from datetime import datetime
from integrations.base_pool import (
    BasePoolIntegration,
    PoolHealthStatus,
    PoolBlock,
    PoolStats,
    DashboardTileData,
    PoolTemplate,
    MiningModel
)
from core.utils import format_hashrate

logger = logging.getLogger(__name__)

__version__ = "1.0.1"


class NerdMinersIntegration(BasePoolIntegration):
    """
    NerdMiners.org public solo pool integration.
    
    API Documentation: https://pool.nerdminers.org
    """
    
    pool_type = "nerdminers"
    display_name = "NerdMiners.org"
    driver_version = __version__
    documentation_url = "https://pool.nerdminers.org"
    supports_coins = ["BTC"]
    requires_api_key = False
    
    API_TIMEOUT = 10.0
    
    def get_pool_templates(self) -> List[PoolTemplate]:
        """Return NerdMiners pool template."""
        return [
            PoolTemplate(
                template_id="nerdminers_btc",
                display_name="NerdMiners.org BTC Solo",
                url="pool.nerdminers.org",
                port=3333,
                coin="BTC",
                mining_model=MiningModel.SOLO,
                region="Global",
                requires_auth=False,
                supports_shares=True,
                supports_earnings=False,
                supports_balance=False,
                description="Public solo mining pool for Bitcoin",
                fee_percent=0.0
            ),
        ]
    
    def _parse_hashrate(self, hashrate_str: str) -> float:
        """
        Parse hashrate string like "10.9253G" to GH/s.
        
        Examples: "829K" → 0.000829 GH/s, "10.9G" → 10.9 GH/s
        """
        if not hashrate_str:
            return 0.0
        
        try:
            match = re.match(r'([\d.]+)([KMGTP]?)', hashrate_str.upper())
            if not match:
                return 0.0
            
            value = float(match.group(1))
            unit = match.group(2) or ''
            
            multipliers = {
                '': 1.0,
                'K': 0.000001,
                'M': 0.001,
                'G': 1.0,
                'T': 1000.0,
                'P': 1000000.0
            }
            
            return value * multipliers.get(unit, 1.0)
        
        except Exception as e:
            logger.warning(f"Failed to parse hashrate '{hashrate_str}': {e}")
            return 0.0
    
    async def detect(self, url: str, port: int) -> bool:
        """Detect NerdMiners pool by checking pool status endpoint."""
        try:
            clean_url = url.replace("http://", "").replace("https://", "")
            api_url = f"https://{clean_url}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{api_url}/pool/pool.status",
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    if response.status == 200:
                        text = await response.text()
                        return '"Users":' in text and '"Workers":' in text
        except Exception as e:
            logger.debug(f"NerdMiners detection failed for {url}: {e}")
        
        return False
    
    async def get_health(self, url: str, port: int, **kwargs) -> PoolHealthStatus:
        """Check pool health via pool status endpoint."""
        try:
            clean_url = url.replace("http://", "").replace("https://", "")
            api_url = f"https://{clean_url}"
            
            start_time = datetime.utcnow()
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{api_url}/pool/pool.status",
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                    
                    if response.status != 200:
                        return PoolHealthStatus(
                            is_healthy=False,
                            response_time_ms=latency_ms,
                            error_message=f"HTTP {response.status}"
                        )
                    
                    return PoolHealthStatus(
                        is_healthy=True,
                        response_time_ms=latency_ms,
                        error_message=None
                    )
        
        except aiohttp.ClientError as e:
            return PoolHealthStatus(
                is_healthy=False,
                response_time_ms=None,
                error_message=f"Connection failed: {str(e)}"
            )
        except Exception as e:
            return PoolHealthStatus(
                is_healthy=False,
                response_time_ms=None,
                error_message=str(e)
            )
    
    async def get_network_difficulty(self, coin: str, **kwargs) -> Optional[float]:
        """NerdMiners pool doesn't provide network difficulty via API."""
        return None
    
    async def get_blocks(
        self,
        url: str,
        coin: str,
        username: Optional[str] = None,
        limit: int = 10,
        **kwargs
    ) -> List[PoolBlock]:
        """NerdMiners pool doesn't provide block history via API."""
        return []
    
    async def get_pool_stats(
        self,
        url: str,
        coin: str,
        username: Optional[str] = None,
        **kwargs
    ) -> Optional[PoolStats]:
        """Get general pool statistics."""
        try:
            clean_url = url.replace("http://", "").replace("https://", "")
            api_url = f"https://{clean_url}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{api_url}/pool/pool.status",
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    if response.status != 200:
                        return None
                    
                    text = await response.text()
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    
                    import json
                    data = [json.loads(line) for line in lines]
                    
                    users_data = data[0] if len(data) > 0 else {}
                    hashrate_data = data[1] if len(data) > 1 else {}
                    shares_data = data[2] if len(data) > 2 else {}
                    
                    pool_hashrate_str = hashrate_data.get("hashrate5m", hashrate_data.get("hashrate1m", "0"))
                    pool_hashrate_ghs = self._parse_hashrate(pool_hashrate_str)
                    
                    active_workers = users_data.get("Workers", 0) - users_data.get("Idle", 0) - users_data.get("Disconnected", 0)
                    
                    return PoolStats(
                        pool_hashrate=pool_hashrate_ghs,
                        active_workers=active_workers,
                        total_workers=users_data.get("Workers", 0),
                        shares_accepted=int(shares_data.get("accepted", 0)),
                        shares_rejected=int(shares_data.get("rejected", 0)),
                        coin=coin
                    )
        
        except Exception as e:
            logger.error(f"Failed to get pool stats from NerdMiners: {e}")
            return None
    
    async def get_dashboard_data(
        self,
        url: str,
        coin: str,
        username: Optional[str] = None,
        **kwargs
    ) -> Optional[DashboardTileData]:
        """Get all dashboard tile data."""
        try:
            clean_url = url.replace("http://", "").replace("https://", "")
            api_url = f"https://{clean_url}"
            
            async with aiohttp.ClientSession() as session:
                start_time = datetime.utcnow()
                
                async with session.get(
                    f"{api_url}/pool/pool.status",
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                    
                    if response.status != 200:
                        return DashboardTileData(
                            health_status=False,
                            health_message=f"HTTP {response.status}",
                            latency_ms=latency_ms,
                            currency=coin.upper()
                        )
                    
                    text = await response.text()
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    
                    import json
                    data = [json.loads(line) for line in lines]
                    
                    users_data = data[0] if len(data) > 0 else {}
                    hashrate_data = data[1] if len(data) > 1 else {}
                    shares_data = data[2] if len(data) > 2 else {}
                
                pool_hashrate_str = hashrate_data.get("hashrate5m", hashrate_data.get("hashrate1m", "0"))
                pool_hashrate_ghs = self._parse_hashrate(pool_hashrate_str)
                
                total_workers = users_data.get("Workers", 0)
                idle_workers = users_data.get("Idle", 0)
                disconnected_workers = users_data.get("Disconnected", 0)
                active_workers = total_workers - idle_workers - disconnected_workers
                
                shares_accepted = int(shares_data.get("accepted", 0))
                shares_rejected = int(shares_data.get("rejected", 0))
                shares_total = shares_accepted + shares_rejected
                reject_rate = 0.0
                if shares_total > 0:
                    reject_rate = (shares_rejected / shares_total) * 100
                
                user_hashrate_ghs = None
                user_workers = None
                user_shares = None
                
                if username:
                    try:
                        async with session.get(
                            f"{api_url}/users/{username}",
                            timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                        ) as user_response:
                            if user_response.status == 200:
                                user_data = await user_response.json()
                                
                                user_hashrate_str = user_data.get("hashrate5m", user_data.get("hashrate1m", "0"))
                                user_hashrate_ghs = self._parse_hashrate(user_hashrate_str)
                                
                                user_workers = user_data.get("workers", 0)
                                user_shares = int(user_data.get("shares", 0))
                    except Exception as e:
                        logger.warning(f"Failed to fetch user stats for {username}: {e}")
                
                if username and user_workers is not None:
                    health_message = f"{user_workers} your workers / {active_workers} pool workers online"
                else:
                    health_message = f"{active_workers} workers online"
                
                return DashboardTileData(
                    health_status=True,
                    health_message=health_message,
                    latency_ms=latency_ms,
                    
                    network_difficulty=None,
                    pool_hashrate=format_hashrate(user_hashrate_ghs * 1e9, "H/s") if user_hashrate_ghs else format_hashrate(pool_hashrate_ghs * 1e9, "H/s"),
                    estimated_time_to_block=None,
                    pool_percentage=None,
                    active_workers=user_workers if user_workers is not None else active_workers,
                    
                    shares_valid=user_shares if user_shares is not None else shares_accepted,
                    shares_invalid=shares_rejected if user_shares is None else 0,
                    shares_stale=0,
                    reject_rate=round(reject_rate, 2),
                    
                    blocks_found_24h=0,
                    currency=coin.upper(),
                    
                    last_updated=datetime.utcnow(),
                    supports_earnings=False,
                    supports_balance=False
                )
        
        except Exception as e:
            logger.error(f"Failed to get dashboard data from NerdMiners: {e}")
            return None
