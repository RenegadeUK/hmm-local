"""
External integrations module - portable to HEMA
Provides interfaces for controlling external smart home devices and pool connections
"""
from .base import IntegrationAdapter, DeviceInfo, DeviceState
from .homeassistant import HomeAssistantIntegration
from .pool_registry import PoolRegistry

__all__ = [
    'IntegrationAdapter',
    'DeviceInfo',
    'DeviceState',
    'HomeAssistantIntegration',
    'PoolRegistry',
]
