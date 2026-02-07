"""
Dynamic plugin loader for pool integrations.

⚠️  DEPRECATED: This legacy plugin system is being replaced by the driver system.
    New pools should be added as drivers in /config/drivers/ instead.
    This module remains for backward compatibility only.

Scans /config/plugins/ directory and loads pool plugins at runtime.
This enables users to add/remove pool plugins without rebuilding the Docker container.

Plugin Structure:
    /config/plugins/
        my_pool/
            __init__.py
            plugin.py          # Must contain a class inheriting from BasePoolIntegration
            README.md          # Optional: Plugin documentation
            requirements.txt   # Optional: Additional dependencies

Plugin Requirements:
    - Must inherit from BasePoolIntegration
    - Must implement all abstract methods
    - Must provide get_pool_templates() returning List[PoolTemplate]
"""

import sys
import importlib.util
import logging
from pathlib import Path
from typing import List, Dict, Optional
import traceback

from integrations.base_pool import BasePoolIntegration

logger = logging.getLogger(__name__)


class PluginLoadError(Exception):
    """Raised when a plugin fails to load."""
    pass


class PluginLoader:
    """
    Dynamically loads pool plugins from the configured directory.
    
    ⚠️  DEPRECATED: This loader is for the legacy plugin system.
    New pools should use the driver system (/config/drivers/).
    
    This loader scans the plugin directory and imports Python modules.
    Plugins are loaded but not registered with any registry.
    """
    
    def __init__(self, plugins_dir: Path, enabled_plugins: Optional[List[str]] = None):
        """
        Initialize the plugin loader.
        
        Args:
            plugins_dir: Path to the plugins directory (e.g., /config/plugins/)
            enabled_plugins: List of plugin names to load. If None, loads all.
        """
        self.plugins_dir = plugins_dir
        self.enabled_plugins = enabled_plugins
        self.loaded_plugins: Dict[str, BasePoolIntegration] = {}
        self.failed_plugins: Dict[str, str] = {}
        
    def load_all_plugins(self) -> Dict[str, BasePoolIntegration]:
        """
        Load all enabled plugins from the plugins directory.
        
        Returns:
            Dictionary of successfully loaded plugins {plugin_name: plugin_instance}
        """
        if not self.plugins_dir.exists():
            logger.warning(f"Plugins directory does not exist: {self.plugins_dir}")
            logger.info(f"Creating plugins directory: {self.plugins_dir}")
            self.plugins_dir.mkdir(parents=True, exist_ok=True)
            return {}
        
        if not self.plugins_dir.is_dir():
            logger.error(f"Plugins path is not a directory: {self.plugins_dir}")
            return {}
        
        # Scan for plugin directories
        plugin_dirs = [d for d in self.plugins_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
        
        if not plugin_dirs:
            logger.info(f"No plugin directories found in {self.plugins_dir}")
            return {}
        
        logger.info(f"Scanning {len(plugin_dirs)} plugin directories...")
        
        for plugin_dir in plugin_dirs:
            plugin_name = plugin_dir.name
            
            # Check if plugin is enabled
            if self.enabled_plugins is not None and plugin_name not in self.enabled_plugins:
                logger.debug(f"Skipping disabled plugin: {plugin_name}")
                continue
            
            try:
                self._load_plugin(plugin_dir, plugin_name)
            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                self.failed_plugins[plugin_name] = error_msg
                logger.error(f"Failed to load plugin '{plugin_name}': {error_msg}")
                logger.debug(traceback.format_exc())
        
        # Log summary
        if self.loaded_plugins:
            logger.info(f"✓ Successfully loaded {len(self.loaded_plugins)} plugin(s): {', '.join(self.loaded_plugins.keys())}")
        
        if self.failed_plugins:
            logger.warning(f"⚠ Failed to load {len(self.failed_plugins)} plugin(s): {', '.join(self.failed_plugins.keys())}")
        
        return self.loaded_plugins
    
    def _load_plugin(self, plugin_dir: Path, plugin_name: str):
        """
        Load a single plugin from its directory.
        
        Args:
            plugin_dir: Path to the plugin directory
            plugin_name: Name of the plugin
        
        Raises:
            PluginLoadError: If the plugin cannot be loaded
        """
        # Look for plugin.py file
        plugin_file = plugin_dir / "plugin.py"
        
        if not plugin_file.exists():
            raise PluginLoadError(f"Plugin file not found: {plugin_file}")
        
        # Dynamically import the plugin module
        module_name = f"plugins.{plugin_name}.plugin"
        spec = importlib.util.spec_from_file_location(module_name, plugin_file)
        
        if spec is None or spec.loader is None:
            raise PluginLoadError(f"Failed to load module spec for {plugin_file}")
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            raise PluginLoadError(f"Failed to execute module: {e}")
        
        # Validate plugin structure
        self._validate_plugin(module, plugin_name)
        
        # Find and instantiate the plugin class
        plugin_instance = self._instantiate_plugin(module, plugin_name)
        
        if plugin_instance:
            # Note: PoolRegistry registration removed - legacy system deprecated
            # New pools should use the driver system in /config/drivers/
            self.loaded_plugins[plugin_name] = plugin_instance
            logger.info(f"✓ Loaded legacy plugin: {plugin_name} ({plugin_instance.display_name})")
            logger.warning(f"⚠️  Plugin '{plugin_name}' uses deprecated plugin system - migrate to driver system")
    
    def _validate_plugin(self, module, plugin_name: str):
        """
        Validate that the plugin module has the required structure.
        
        Args:
            module: The imported plugin module
            plugin_name: Name of the plugin
        
        Raises:
            PluginLoadError: If validation fails
        """
        # Check if module has any classes inheriting from BasePoolIntegration
        has_pool_integration = False
        
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and 
                issubclass(attr, BasePoolIntegration) and 
                attr is not BasePoolIntegration):
                has_pool_integration = True
                break
        
        if not has_pool_integration:
            raise PluginLoadError(
                f"Plugin does not contain a class inheriting from BasePoolIntegration"
            )
    
    def _instantiate_plugin(self, module, plugin_name: str) -> Optional[BasePoolIntegration]:
        """
        Find and instantiate the pool integration class from the module.
        
        Args:
            module: The imported plugin module
            plugin_name: Name of the plugin
        
        Returns:
            Instantiated plugin, or None if not found
        
        Raises:
            PluginLoadError: If instantiation fails
        """
        # Find the BasePoolIntegration subclass
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            
            if (isinstance(attr, type) and 
                issubclass(attr, BasePoolIntegration) and 
                attr is not BasePoolIntegration):
                
                try:
                    # Instantiate the plugin
                    instance = attr()
                    
                    # Validate required methods are implemented
                    required_methods = ['get_pool_templates', 'detect', 'get_dashboard_data']
                    for method_name in required_methods:
                        if not hasattr(instance, method_name):
                            raise PluginLoadError(f"Plugin missing required method: {method_name}")
                    
                    # Validate get_pool_templates returns data
                    try:
                        templates = instance.get_pool_templates()
                        if not templates:
                            logger.warning(f"Plugin '{plugin_name}' has no templates (get_pool_templates returned empty)")
                    except Exception as e:
                        raise PluginLoadError(f"get_pool_templates() failed: {e}")
                    
                    return instance
                    
                except Exception as e:
                    raise PluginLoadError(f"Failed to instantiate plugin class {attr_name}: {e}")
        
        return None
    
    def get_loaded_plugins(self) -> Dict[str, BasePoolIntegration]:
        """Get dictionary of successfully loaded plugins."""
        return self.loaded_plugins
    
    def get_failed_plugins(self) -> Dict[str, str]:
        """Get dictionary of failed plugins with error messages."""
        return self.failed_plugins
    
    def reload_plugin(self, plugin_name: str) -> bool:
        """
        Reload a specific plugin (hot reload).
        
        Args:
            plugin_name: Name of the plugin to reload
        
        Returns:
            True if reload was successful, False otherwise
        """
        plugin_dir = self.plugins_dir / plugin_name
        
        if not plugin_dir.exists():
            logger.error(f"Plugin directory not found: {plugin_dir}")
            return False
        
        # Unregister old plugin if it exists
        if plugin_name in self.loaded_plugins:
            old_plugin = self.loaded_plugins[plugin_name]
            logger.info(f"Reloading plugin: {plugin_name}")
        
        try:
            # Remove from loaded/failed
            self.loaded_plugins.pop(plugin_name, None)
            self.failed_plugins.pop(plugin_name, None)
            
            # Reload
            self._load_plugin(plugin_dir, plugin_name)
            return True
            
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            self.failed_plugins[plugin_name] = error_msg
            logger.error(f"Failed to reload plugin '{plugin_name}': {error_msg}")
            return False


def load_plugins_from_config(config: dict) -> Dict[str, BasePoolIntegration]:
    """
    Load plugins based on configuration.
    
    Args:
        config: Configuration dictionary with 'plugins' section
    
    Returns:
        Dictionary of loaded plugins
    """
    plugins_config = config.get("plugins", {})
    
    if not plugins_config.get("enabled", True):
        logger.info("Plugin system is disabled in configuration")
        return {}
    
    plugins_dir = Path(plugins_config.get("directory", "/config/plugins"))
    enabled_plugins = plugins_config.get("enabled_plugins")
    
    loader = PluginLoader(plugins_dir, enabled_plugins)
    return loader.load_all_plugins()
