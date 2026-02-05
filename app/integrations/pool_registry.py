"""
Pool Registry - Centralized pool plugin management

This module provides automatic discovery and registration of pool plugins.
"""
from typing import Dict, Optional, List, Type
import logging
from integrations.base_pool import BasePoolIntegration

logger = logging.getLogger(__name__)


class PoolRegistry:
    """
    Central registry for all pool integrations.
    Plugins automatically register themselves when imported.
    """
    
    _pools: Dict[str, BasePoolIntegration] = {}
    _initialized: bool = False
    
    @classmethod
    def register(cls, pool: BasePoolIntegration):
        """
        Register a pool integration.
        
        Args:
            pool: Instance of a pool integration
        """
        if pool.pool_type in cls._pools:
            logger.warning(f"Pool type '{pool.pool_type}' already registered, overwriting")
        
        cls._pools[pool.pool_type] = pool
        logger.info(f"Registered pool integration: {pool.display_name} ({pool.pool_type})")
    
    @classmethod
    def get(cls, pool_type: str) -> Optional[BasePoolIntegration]:
        """
        Get a pool integration by type.
        
        Args:
            pool_type: Pool type identifier
            
        Returns:
            Pool integration instance or None
        """
        cls._ensure_initialized()
        return cls._pools.get(pool_type)
    
    @classmethod
    def list_all(cls) -> Dict[str, BasePoolIntegration]:
        """
        Get all registered pool integrations.
        
        Returns:
            Dict mapping pool_type to integration instance
        """
        cls._ensure_initialized()
        return cls._pools.copy()
    
    @classmethod
    async def detect_pool_type(cls, url: str, port: int) -> Optional[str]:
        """
        Auto-detect pool type from URL and port.
        Tries each registered integration's detect() method.
        
        Args:
            url: Pool URL or IP address
            port: Stratum port
            
        Returns:
            Pool type string or None if not detected
        """
        cls._ensure_initialized()
        
        for pool_type, pool in cls._pools.items():
            try:
                if await pool.detect(url, port):
                    logger.info(f"Detected pool type '{pool_type}' for {url}:{port}")
                    return pool_type
            except Exception as e:
                logger.debug(f"Pool detection error for '{pool_type}': {e}")
        
        logger.warning(f"Could not detect pool type for {url}:{port}")
        return None
    
    @classmethod
    def get_supported_coins(cls, pool_type: str) -> List[str]:
        """
        Get list of coins supported by a pool type.
        
        Args:
            pool_type: Pool type identifier
            
        Returns:
            List of coin symbols (empty list = all coins supported)
        """
        pool = cls.get(pool_type)
        if pool:
            return pool.supports_coins
        return []
    
    @classmethod
    def _ensure_initialized(cls):
        """Lazy-load all pool plugins"""
        if cls._initialized:
            return
        
        cls._initialized = True
        
        # Import all pool plugins to trigger registration
        try:
            from integrations.pools import solopool_plugin
            from integrations.pools import braiins_plugin
            from integrations.pools import mmfp_plugin
        except ImportError as e:
            logger.warning(f"Failed to import some pool plugins: {e}")
    
    @classmethod
    def get_pool_info(cls) -> List[Dict]:
        """
        Get information about all registered pools for UI display.
        
        Returns:
            List of dicts with pool metadata
        """
        cls._ensure_initialized()
        
        return [
            {
                "pool_type": pool_type,
                "display_name": pool.display_name,
                "documentation_url": pool.documentation_url,
                "supports_coins": pool.supports_coins,
                "requires_api_key": pool.requires_api_key,
                "config_schema": pool.get_config_schema()
            }
            for pool_type, pool in cls._pools.items()
        ]
