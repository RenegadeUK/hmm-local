"""
Adapter factory and registry
"""
from typing import Dict, Optional
from adapters.base import MinerAdapter
from adapters.avalon_nano import AvalonNanoAdapter
from adapters.bitaxe import BitaxeAdapter
from adapters.nerdqaxe import NerdQaxeAdapter
from adapters.nmminer import NMMinerAdapter
from adapters.xmrig import XMRigAdapter


ADAPTER_REGISTRY = {
    "avalon_nano": AvalonNanoAdapter,
    "bitaxe": BitaxeAdapter,
    "nerdqaxe": NerdQaxeAdapter,
    "nmminer": NMMinerAdapter,
    "xmrig": XMRigAdapter
}


def create_adapter(
    miner_type: str,
    miner_id: int,
    miner_name: str,
    ip_address: str,
    port: Optional[int] = None,
    config: Optional[Dict] = None
) -> Optional[MinerAdapter]:
    """
    Factory function to create appropriate miner adapter.
    
    Args:
        miner_type: Type of miner (avalon_nano, bitaxe, nerdqaxe, nmminer, xmrig)
        miner_id: Database ID of the miner
        miner_name: Name of the miner
        ip_address: IP address of the miner
        port: Optional port override
        config: Optional configuration dictionary
    
    Returns:
        MinerAdapter instance or None if type not found
    """
    adapter_class = ADAPTER_REGISTRY.get(miner_type)
    
    if not adapter_class:
        print(f"❌ Unknown miner type: {miner_type}")
        return None
    
    return adapter_class(miner_id, miner_name, ip_address, port, config)


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
    """Get list of supported miner types"""
    return list(ADAPTER_REGISTRY.keys())
