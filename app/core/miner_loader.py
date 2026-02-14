"""
Miner Driver Loader

Dynamically loads miner drivers from /config/drivers/miners/
Similar architecture to pool_loader.py
"""
import importlib.util
import logging
from typing import Dict, Optional, List
from pathlib import Path

from adapters.base import MinerAdapter

logger = logging.getLogger(__name__)


class MinerDriverLoader:
    """
    Loads miner drivers from /config/drivers/miners/
    Provides unified access to all available miner types
    """
    
    def __init__(self, config_path: str = "/config"):
        self.config_path = Path(config_path)
        self.drivers_path = self.config_path / "drivers" / "miners"
        
        # driver_type -> adapter_class mapping
        self.drivers: Dict[str, type] = {}
        # driver_type -> loaded python module
        self.driver_modules: Dict[str, object] = {}
    
    def load_all(self):
        """Load all miner drivers"""
        self.load_drivers()
    
    def load_drivers(self):
        """Dynamically load all Python files from /config/drivers/miners/"""
        if not self.drivers_path.exists():
            logger.warning(f"Miner drivers directory not found: {self.drivers_path}")
            return
        
        logger.info(f"Loading miner drivers from {self.drivers_path}")
        
        for file_path in self.drivers_path.glob("*_driver.py"):
            try:
                # Skip template files
                if "template" in file_path.stem.lower():
                    logger.debug(f"Skipping template file: {file_path.name}")
                    continue
                
                # Load the Python module
                spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # Find MinerAdapter subclasses
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and 
                            issubclass(attr, MinerAdapter) and 
                            attr is not MinerAdapter):
                            
                            # Get miner_type from class attribute
                            miner_type = getattr(attr, 'miner_type', None)
                            
                            if miner_type:
                                self.drivers[miner_type] = attr
                                self.driver_modules[miner_type] = module
                                logger.info(f"✅ Loaded driver: {miner_type} from {file_path.name}")
                            else:
                                logger.warning(f"⚠️  Driver class {attr_name} in {file_path.name} missing miner_type attribute")
                    
            except Exception as e:
                import traceback
                logger.error(f"❌ Failed to load driver {file_path.name}: {e}")
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
        
        logger.info(f"Loaded {len(self.drivers)} miner drivers: {list(self.drivers.keys())}")
    
    def get_driver(self, miner_type: str) -> Optional[type]:
        """Get driver class by miner type"""
        return self.drivers.get(miner_type)
    
    def get_supported_types(self) -> List[str]:
        """Get list of all supported miner types"""
        return list(self.drivers.keys())

    def get_driver_module(self, miner_type: str):
        """Get loaded module object by miner type"""
        return self.driver_modules.get(miner_type)
    
    def create_adapter(
        self,
        miner_type: str,
        miner_id: int,
        miner_name: str,
        ip_address: str,
        port: Optional[int] = None,
        config: Optional[Dict] = None
    ) -> Optional[MinerAdapter]:
        """
        Factory function to create appropriate miner adapter
        
        Args:
            miner_type: Type of miner (avalon_nano, bitaxe, nerdqaxe, nmminer, etc.)
            miner_id: Database ID of the miner
            miner_name: Name of the miner
            ip_address: IP address of the miner
            port: Optional port override
            config: Optional configuration dictionary
        
        Returns:
            MinerAdapter instance or None if type not found
        """
        # Special handling for NMMiner (uses shared UDP listener)
        if miner_type == "nmminer":
            from adapters import get_scheduler_service
            scheduler = get_scheduler_service()
            if scheduler and ip_address in scheduler.nmminer_adapters:
                return scheduler.nmminer_adapters[ip_address]
            else:
                logger.warning(f"NMMiner adapter not found for {ip_address} - UDP listener may not be running")
                # Fallback to creating a placeholder adapter
                adapter_class = self.drivers.get(miner_type)
                if adapter_class:
                    return adapter_class(miner_id, miner_name, ip_address, port, config)
        
        adapter_class = self.drivers.get(miner_type)
        
        if not adapter_class:
            logger.error(f"Unknown miner type: {miner_type}")
            return None
        
        return adapter_class(miner_id, miner_name, ip_address, port, config)


# Global instance
_miner_loader: Optional[MinerDriverLoader] = None


def init_miner_loader(config_path: str = "/config"):
    """Initialize the global miner loader"""
    global _miner_loader
    _miner_loader = MinerDriverLoader(config_path)
    _miner_loader.load_all()
    return _miner_loader


def get_miner_loader() -> MinerDriverLoader:
    """Get the global miner loader instance"""
    global _miner_loader
    if _miner_loader is None:
        raise RuntimeError("Miner loader not initialized. Call init_miner_loader() first.")
    return _miner_loader
