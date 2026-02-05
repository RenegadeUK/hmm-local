"""
Dashboard Pool Service

Orchestrates fetching dashboard data from pool plugins.
Handles caching, error recovery, and multi-pool aggregation.
"""
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from core.database import Pool, BlockFound
from integrations.pool_registry import PoolRegistry
from integrations.base_pool import DashboardTileData

logger = logging.getLogger(__name__)

# Cache dashboard data for 30 seconds
_POOL_DASHBOARD_CACHE: Dict[str, tuple[float, DashboardTileData]] = {}
_POOL_DASHBOARD_CACHE_TTL = 30.0


class DashboardPoolService:
    """
    Service for fetching and caching pool dashboard data.
    """
    
    @staticmethod
    async def get_pool_dashboard_data(
        db: AsyncSession,
        pool_id: Optional[str] = None
    ) -> Dict[str, DashboardTileData]:
        """
        Get dashboard data for all active pools (or specific pool).
        
        Args:
            db: Database session
            pool_id: Optional - get data for specific pool only
        
        Returns:
            Dict mapping pool_id -> DashboardTileData
        """
        # Get active pools from database
        query = select(Pool).where(Pool.enabled == True)
        if pool_id:
            query = query.where(Pool.id == pool_id)
        
        result = await db.execute(query)
        pools = result.scalars().all()
        
        if not pools:
            logger.debug("No active pools found for dashboard")
            return {}
        
        dashboard_data = {}
        
        for pool in pools:
            # Check cache first
            cache_key = f"{pool.id}"
            cached = _POOL_DASHBOARD_CACHE.get(cache_key)
            
            if cached:
                cached_at, cached_data = cached
                if (datetime.utcnow().timestamp() - cached_at) < _POOL_DASHBOARD_CACHE_TTL:
                    dashboard_data[str(pool.id)] = cached_data
                    continue
            
            # Fetch fresh data from plugin
            try:
                tile_data = await DashboardPoolService._fetch_pool_data(pool, db)
                
                if tile_data:
                    # Cache it
                    _POOL_DASHBOARD_CACHE[cache_key] = (
                        datetime.utcnow().timestamp(),
                        tile_data
                    )
                    dashboard_data[str(pool.id)] = tile_data
                else:
                    logger.warning(f"No dashboard data returned for pool {pool.name}")
            
            except Exception as e:
                logger.error(f"Failed to fetch dashboard data for pool {pool.name}: {e}")
                # Return error state
                dashboard_data[str(pool.id)] = DashboardTileData(
                    health_status=False,
                    health_message=f"Error: {str(e)[:100]}",
                    currency=getattr(pool, 'coin', None) or "UNKNOWN"
                )
        
        return dashboard_data
    
    @staticmethod
    async def _fetch_pool_data(pool: Pool, db: AsyncSession) -> Optional[DashboardTileData]:
        """
        Fetch dashboard data from a pool using its plugin.
        
        Args:
            pool: Pool database model
            db: Database session for querying our blocks
        
        Returns:
            DashboardTileData or None
        """
        # Get pool type (from pool_type field or detect)
        pool_type = pool.pool_type
        
        if not pool_type or pool_type == "unknown":
            # Try to detect pool type
            pool_type = await PoolRegistry.detect_pool_type(pool.url, pool.port)
            
            if pool_type == "unknown":
                logger.warning(f"Could not detect pool type for {pool.url}:{pool.port}")
                return None
        
        # Get plugin integration
        if not pool_type:
            return None
        
        integration = PoolRegistry.get(pool_type)
        
        if not integration:
            logger.warning(f"No plugin found for pool type: {pool_type}")
            return None
        
        # Parse pool config JSON (if exists)
        pool_config = pool.pool_config or {}
        
        # Get username/worker from config or pool fields
        username = pool_config.get("username") or pool.user
        
        # Call plugin's dashboard method
        try:
            # Detect coin from pool config, or try to detect from port/URL
            coin = pool_config.get("coin")
            
            if not coin:
                # Try to detect coin from port (for Solopool and other multi-coin pools)
                if hasattr(integration, '_get_coin_from_port'):
                    coin = integration._get_coin_from_port(pool.port)
                
                # Fallback: try to parse from pool name or URL
                if not coin:
                    pool_identifier = f"{pool.name} {pool.url}".upper()
                    for test_coin in ["DGB", "BCH", "BTC", "BC2", "LTC"]:
                        if test_coin in pool_identifier:
                            coin = test_coin
                            break
                
                # Final fallback
                if not coin:
                    coin = "BTC"
            
            dashboard_data = await integration.get_dashboard_data(
                url=pool.url,
                coin=coin,
                username=username,
                **pool_config
            )
            
            # Override blocks_found_24h with OUR actual blocks from database
            if dashboard_data:
                cutoff = datetime.utcnow() - timedelta(hours=24)
                
                # Query blocks found by our miners on this pool in last 24h
                blocks_query = select(func.count(BlockFound.id)).where(
                    BlockFound.pool_name == pool.name,
                    BlockFound.coin == coin.upper(),
                    BlockFound.timestamp >= cutoff
                )
                result = await db.execute(blocks_query)
                our_blocks_24h = result.scalar() or 0
                
                # Replace with our actual count
                dashboard_data.blocks_found_24h = our_blocks_24h
                logger.debug(f"Pool {pool.name}: Found {our_blocks_24h} blocks by our miners in last 24h")
            
            return dashboard_data
        
        except NotImplementedError:
            logger.warning(f"Pool plugin {pool_type} does not implement get_dashboard_data()")
            return None
        
        except Exception as e:
            logger.error(f"Error calling plugin {pool_type}.get_dashboard_data(): {e}")
            raise
    
    @staticmethod
    async def invalidate_cache(pool_id: Optional[str] = None):
        """
        Invalidate cached dashboard data.
        
        Args:
            pool_id: Optional - clear specific pool only, or all if None
        """
        if pool_id:
            cache_key = f"{pool_id}"
            if cache_key in _POOL_DASHBOARD_CACHE:
                del _POOL_DASHBOARD_CACHE[cache_key]
                logger.debug(f"Invalidated cache for pool {pool_id}")
        else:
            _POOL_DASHBOARD_CACHE.clear()
            logger.debug("Cleared all pool dashboard cache")
    
    @staticmethod
    async def get_platform_tiles(
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Get PLATFORM TILES - consolidated data across ALL pools.
        
        These are the top 4 tiles on the dashboard showing aggregate view.
        
        Returns:
            Dict with 4 platform tiles:
            - tile_1_health: Overall pool health status
            - tile_2_network: Consolidated network stats
            - tile_3_shares: Combined shares across all pools
            - tile_4_blocks: Total blocks/earnings across all pools
        """
        pool_data = await DashboardPoolService.get_pool_dashboard_data(db)
        
        if not pool_data:
            return {
                "tile_1_health": {
                    "total_pools": 0,
                    "healthy_pools": 0,
                    "unhealthy_pools": 0,
                    "avg_latency_ms": None,
                    "status": "no_pools"
                },
                "tile_2_network": {
                    "total_pool_hashrate": 0.0,
                    "total_network_difficulty": 0.0,
                    "avg_pool_percentage": 0.0,
                    "estimated_time_to_block": None
                },
                "tile_3_shares": {
                    "total_valid": 0,
                    "total_invalid": 0,
                    "total_stale": 0,
                    "avg_reject_rate": 0.0
                },
                "tile_4_blocks": {
                    "total_blocks_24h": 0,
                    "total_earnings_24h": 0.0,
                    "currencies": []
                }
            }
        
        # TILE 1: Health - aggregate health across all pools
        healthy_count = sum(1 for d in pool_data.values() if d.health_status)
        unhealthy_count = len(pool_data) - healthy_count
        latencies = [d.latency_ms for d in pool_data.values() if d.latency_ms is not None]
        avg_latency = sum(latencies) / len(latencies) if latencies else None
        
        overall_status = "healthy" if unhealthy_count == 0 else "degraded" if healthy_count > 0 else "unhealthy"
        
        # TILE 2: Network - combined network stats
        total_pool_hashrate = sum(d.pool_hashrate or 0.0 for d in pool_data.values())
        network_diffs = [d.network_difficulty for d in pool_data.values() if d.network_difficulty]
        total_network_diff = sum(network_diffs) if network_diffs else 0.0
        pool_percentages = [d.pool_percentage for d in pool_data.values() if d.pool_percentage]
        avg_pool_pct = sum(pool_percentages) / len(pool_percentages) if pool_percentages else 0.0
        
        # TILE 3: Shares - combined shares data
        total_valid = sum(d.shares_valid or 0 for d in pool_data.values())
        total_invalid = sum(d.shares_invalid or 0 for d in pool_data.values())
        total_stale = sum(d.shares_stale or 0 for d in pool_data.values())
        reject_rates = [d.reject_rate for d in pool_data.values() if d.reject_rate is not None]
        avg_reject = sum(reject_rates) / len(reject_rates) if reject_rates else 0.0
        
        # TILE 4: Blocks - combined earnings/blocks
        total_blocks = sum(d.blocks_found_24h or 0 for d in pool_data.values())
        earnings = [d.estimated_earnings_24h for d in pool_data.values() if d.estimated_earnings_24h]
        total_earnings = sum(earnings) if earnings else 0.0
        currencies = list(set(d.currency for d in pool_data.values() if d.currency))
        
        return {
            "tile_1_health": {
                "total_pools": len(pool_data),
                "healthy_pools": healthy_count,
                "unhealthy_pools": unhealthy_count,
                "avg_latency_ms": round(avg_latency, 1) if avg_latency else None,
                "status": overall_status
            },
            "tile_2_network": {
                "total_pool_hashrate": round(total_pool_hashrate, 2),
                "total_network_difficulty": round(total_network_diff, 2),
                "avg_pool_percentage": round(avg_pool_pct, 2),
                "estimated_time_to_block": None  # Would need complex calculation
            },
            "tile_3_shares": {
                "total_valid": total_valid,
                "total_invalid": total_invalid,
                "total_stale": total_stale,
                "avg_reject_rate": round(avg_reject, 2)
            },
            "tile_4_blocks": {
                "total_blocks_24h": total_blocks,
                "total_earnings_24h": round(total_earnings, 4) if total_earnings else None,
                "currencies": currencies
            }
        }
