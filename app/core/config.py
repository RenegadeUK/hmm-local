"""
Configuration management using /config volume
"""
import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
import yaml


class Settings(BaseSettings):
    """Application settings from environment variables"""
    WEB_PORT: int = 8080
    TZ: str = "UTC"
    PUID: int = 1000
    PGID: int = 1000
    
    # Internal paths
    CONFIG_DIR: Path = Path("/config")
    CONFIG_FILE: Path = Path("/config/config.yaml")
    DB_PATH: Path = Path("/config/data.db")
    LOG_DIR: Path = Path("/config/logs")
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()


class AppConfig:
    """Application configuration from config.yaml"""
    
    def __init__(self):
        self.config_path = settings.CONFIG_FILE
        self._config = {}
        self.load()
    
    def load(self):
        """Load configuration from YAML file"""
        # Ensure config directory exists
        settings.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
        
        if self.config_path.exists():
            with open(self.config_path, 'r') as f:
                self._config = yaml.safe_load(f) or {}
        else:
            # Create default config
            self._config = self._get_default_config()
            self.save()
    
    def save(self):
        """Save configuration to YAML file"""
        with open(self.config_path, 'w') as f:
            yaml.dump(self._config, f, default_flow_style=False)
    
    def _get_default_config(self) -> dict:
        """Get default configuration structure"""
        return {
            "mqtt": {
                "enabled": False,
                "broker": "localhost",
                "port": 1883,
                "topic_prefix": "miner",
                "username": "",
                "password": ""
            },
            "octopus_agile": {
                "enabled": False,
                "region": "H"  # Default to Southern England
            },
            "miners": [],
            "pools": []
        }
    
    def get(self, key: str, default=None):
        """Get configuration value by key"""
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default
    
    def set(self, key: str, value):
        """Set configuration value by key"""
        keys = key.split('.')
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
        self.save()


app_config = AppConfig()


def save_config(key: str, value):
    """
    Helper function to update and save configuration
    
    Args:
        key: Dot-notation key (e.g. "octopus_agile.region")
        value: Value to set
    """
    app_config.set(key, value)
