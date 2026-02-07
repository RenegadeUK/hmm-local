"""
Pool Driver and Configuration Loader

This module loads pool drivers from /config/drivers/ and pool configs from /config/pools/.
It provides a unified interface for the rest of the application to work with pools.
"""
import os
import yaml
import importlib.util
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

from integrations.base_pool import BasePoolIntegration, PoolTemplate

logger = logging.getLogger(__name__)


class PoolConfig:
    """Represents a single pool configuration loaded from YAML"""
    
    def __init__(self, config_id: str, data: Dict[str, Any]):
        self.config_id = config_id  # Filename without .yaml
        self.driver = data.get("driver")
        self.display_name = data.get("display_name")
        self.description = data.get("description")
        self.url = data.get("url")
        self.port = data.get("port")
        self.coin = data.get("coin")
        self.region = data.get("region")
        self.mining_model = data.get("mining_model")
        self.fee_percent = data.get("fee_percent", 0.0)
        self.requires_auth = data.get("requires_auth", False)
        self.supports_shares = data.get("supports_shares", False)
        self.supports_earnings = data.get("supports_earnings", False)
        self.supports_balance = data.get("supports_balance", False)
        
    def to_template(self) -> PoolTemplate:
        """Convert to PoolTemplate for API compatibility"""
        from integrations.base_pool import MiningModel
        
        return PoolTemplate(
            template_id=self.config_id,
            display_name=self.display_name,
            url=self.url,
            port=self.port,
            coin=self.coin,
            mining_model=MiningModel(self.mining_model),
            region=self.region,
            requires_auth=self.requires_auth,
            supports_shares=self.supports_shares,
            supports_earnings=self.supports_earnings,
            supports_balance=self.supports_balance,
            description=self.description,
            fee_percent=self.fee_percent
        )


class PoolDriverLoader:
    """
    Loads pool drivers from /config/drivers/ and pool configs from /config/pools/.
    Provides unified access to all available pools.
    """
    
    def __init__(self, config_path: str = "/config"):
        self.config_path = Path(config_path)
        self.drivers_path = self.config_path / "drivers"
        self.pools_path = self.config_path / "pools"
        
        self.drivers: Dict[str, BasePoolIntegration] = {}  # driver_type -> instance
        self.pool_configs: Dict[str, PoolConfig] = {}  # config_id -> PoolConfig
        
    def load_all(self):
        """Load all drivers and pool configurations"""
        self.load_drivers()
        self.load_pool_configs()
        
    def load_drivers(self):
        """Dynamically load all Python files from /config/drivers/"""
        if not self.drivers_path.exists():
            logger.warning(f"Drivers directory not found: {self.drivers_path}")
            return
        
        logger.info(f"Loading pool drivers from {self.drivers_path}")
        
        for file_path in self.drivers_path.glob("*_driver.py"):
            try:
                # Load the Python module
                spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # Find BasePoolIntegration subclasses
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and 
                            issubclass(attr, BasePoolIntegration) and 
                            attr is not BasePoolIntegration):
                            
                            # Instantiate the driver
                            driver_instance = attr()
                            driver_type = getattr(driver_instance, 'driver_type', None) or \
                                         getattr(driver_instance, 'pool_type', None)
                            
                            if driver_type:
                                self.drivers[driver_type] = driver_instance
                                logger.info(f"✅ Loaded driver: {driver_type} from {file_path.name}")
                            else:
                                logger.warning(f"⚠️  Driver in {file_path.name} missing driver_type attribute")
                    
            except Exception as e:
                import traceback
                logger.error(f"❌ Failed to load driver {file_path.name}: {e}")
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
        
        logger.info(f"Loaded {len(self.drivers)} pool drivers: {list(self.drivers.keys())}")
    
    def load_pool_configs(self):
        """Load all YAML files from /config/pools/"""
        if not self.pools_path.exists():
            logger.warning(f"Pools directory not found: {self.pools_path}")
            return
        
        logger.info(f"Loading pool configs from {self.pools_path}")
        
        for file_path in self.pools_path.glob("*.yaml"):
            try:
                with open(file_path, 'r') as f:
                    data = yaml.safe_load(f)
                    
                if not data:
                    logger.warning(f"⚠️  Empty config file: {file_path.name}")
                    continue
                
                config_id = file_path.stem  # Filename without .yaml
                pool_config = PoolConfig(config_id, data)
                
                # Validate driver exists
                if pool_config.driver not in self.drivers:
                    logger.error(f"❌ Pool config {config_id} references unknown driver: {pool_config.driver}")
                    continue
                
                self.pool_configs[config_id] = pool_config
                logger.info(f"✅ Loaded pool config: {config_id} (driver: {pool_config.driver})")
                
            except Exception as e:
                logger.error(f"❌ Failed to load pool config {file_path.name}: {e}")
        
        logger.info(f"Loaded {len(self.pool_configs)} pool configs")
    
    def get_driver(self, driver_type: str) -> Optional[BasePoolIntegration]:
        """Get driver instance by type"""
        return self.drivers.get(driver_type)
    
    def get_pool_config(self, config_id: str) -> Optional[PoolConfig]:
        """Get pool configuration by ID"""
        return self.pool_configs.get(config_id)
    
    def get_all_pool_templates(self) -> List[PoolTemplate]:
        """Get all pool configs as PoolTemplate objects (for API compatibility)"""
        return [config.to_template() for config in self.pool_configs.values()]
    
    def get_templates_by_coin(self, coin: str) -> List[PoolTemplate]:
        """Filter pool templates by coin"""
        return [
            config.to_template() 
            for config in self.pool_configs.values() 
            if config.coin == coin
        ]
    
    def get_templates_by_driver(self, driver_type: str) -> List[PoolTemplate]:
        """Filter pool templates by driver type"""
        return [
            config.to_template() 
            for config in self.pool_configs.values() 
            if config.driver == driver_type
        ]


# Global instance
_pool_loader: Optional[PoolDriverLoader] = None


def init_pool_loader(config_path: str = "/config"):
    """Initialize the global pool loader"""
    global _pool_loader
    _pool_loader = PoolDriverLoader(config_path)
    _pool_loader.load_all()
    return _pool_loader


def get_pool_loader() -> PoolDriverLoader:
    """Get the global pool loader instance"""
    global _pool_loader
    if _pool_loader is None:
        raise RuntimeError("Pool loader not initialized. Call init_pool_loader() first.")
    return _pool_loader
