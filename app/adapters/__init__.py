"""
Adapter factory and registry - now uses dynamic miner loader
"""
from typing import Dict, Optional
from adapters.base import MinerAdapter

# Global reference to scheduler service for accessing shared NMMiner adapters
_scheduler_service = None

def set_scheduler_service(service):
    """Set the scheduler service reference for adapter access"""
    global _scheduler_service
    _scheduler_service = service

def get_scheduler_service():
    """Get the scheduler service reference"""
    return _scheduler_service


def create_adapter(
    miner_type: str,
    miner_id: int,
    miner_name: str,
    ip_address: str,
    port: Optional[int] = None,
    config: Optional[Dict] = None
) -> Optional[MinerAdapter]:
    """
    Factory function to create appropriate miner adapter using dynamic loader.
    
    Args:
        miner_type: Type of miner (avalon_nano, bitaxe, nerdqaxe, nmminer)
        miner_id: Database ID of the miner
        miner_name: Name of the miner
        ip_address: IP address of the miner
        port: Optional port override
        config: Optional configuration dictionary
    
    Returns:
        MinerAdapter instance or None if type not found
    """
    from core.miner_loader import get_miner_loader
    
    try:
        loader = get_miner_loader()
        return loader.create_adapter(miner_type, miner_id, miner_name, ip_address, port, config)
    except RuntimeError:
        # Miner loader not initialized yet - fallback to error
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Miner loader not initialized - call init_miner_loader() first")
        return None


def get_adapter(miner) -> Optional[MinerAdapter]:
    """
    Get adapter for a Miner database object.
    
    Args:
        miner: Miner database model instance
    
    Returns:
        MinerAdapter instance or None if type not supported
    """
    return create_adapter(
        miner_type=miner.miner_type,
        miner_id=miner.id,
        miner_name=miner.name,
        ip_address=miner.ip_address,
        port=miner.port,
        config=miner.config
    )


def get_supported_types() -> list:
    """Get list of supported miner types from dynamic loader"""
    from core.miner_loader import get_miner_loader
    
    try:
        loader = get_miner_loader()
        return loader.get_supported_types()
    except RuntimeError:
            # Fallback to baseline hardcoded types during early startup
        return ["avalon_nano", "bitaxe", "nerdqaxe", "nmminer"]
