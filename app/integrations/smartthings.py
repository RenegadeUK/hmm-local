"""
SmartThings REST API Integration
Direct control of SmartThings devices, bypassing Home Assistant
"""
import asyncio
import httpx
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime

from .base import IntegrationAdapter, DeviceInfo, DeviceState

logger = logging.getLogger(__name__)


class SmartThingsIntegration(IntegrationAdapter):
    """SmartThings platform adapter"""
    
    BASE_URL = "https://api.smartthings.com/v1"
    
    def __init__(self, access_token: str, timeout: float = 10.0, retries: int = 3):
        """
        Initialize SmartThings integration
        
        Args:
            access_token: Personal Access Token from SmartThings
            timeout: Request timeout in seconds
            retries: Number of retry attempts for transient failures
        """
        self.token = access_token
        self.timeout = timeout
        self.retries = max(1, retries)
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    async def _request(self, method: str, path: str, json: Optional[dict] = None) -> Optional[httpx.Response]:
        """Execute API request with retry logic"""
        url = f"{self.BASE_URL}{path}"
        timeout = httpx.Timeout(self.timeout)

        for attempt in range(1, self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.request(
                        method,
                        url,
                        headers=self.headers,
                        json=json
                    )
                    response.raise_for_status()
                    return response
            except asyncio.CancelledError:
                logger.warning(f"SmartThings request cancelled: {method} {url}")
                return None
            except (httpx.TimeoutException, httpx.TransportError) as e:
                if attempt < self.retries:
                    backoff = 0.5 * (2 ** (attempt - 1))
                    logger.warning(
                        f"SmartThings request failed (attempt {attempt}/{self.retries}): {method} {url} - {e}"
                    )
                    await asyncio.sleep(backoff)
                    continue
                logger.error(f"SmartThings request failed after {self.retries} attempts: {method} {url} - {e}")
                return None
            except httpx.HTTPStatusError as e:
                logger.error(f"SmartThings API error: {method} {url} - {e.response.status_code} {e.response.text}")
                return None
            except Exception as e:
                logger.error(f"SmartThings request error: {method} {url} - {e}")
                return None
    
    async def test_connection(self) -> bool:
        """Test connection to SmartThings API"""
        response = await self._request("GET", "/devices")
        if not response:
            logger.error("SmartThings connection test failed")
            return False
        try:
            data = response.json()
            device_count = len(data.get("items", []))
            logger.info(f"Connected to SmartThings: {device_count} devices available")
            return True
        except Exception as e:
            logger.error(f"Failed to parse SmartThings response: {e}")
            return False
    
    async def discover_devices(self, domain: Optional[str] = None) -> List[DeviceInfo]:
        """
        Discover all devices in SmartThings
        
        Args:
            domain: Optional filter (e.g., "switch" to only get switches)
        """
        response = await self._request("GET", "/devices")
        if not response:
            return []
        
        try:
            data = response.json()
            devices = []
            
            for device in data.get("items", []):
                device_id = device.get("deviceId")
                name = device.get("label") or device.get("name", "Unknown Device")
                
                # Get device capabilities
                capabilities = []
                for component in device.get("components", []):
                    for capability in component.get("capabilities", []):
                        cap_id = capability.get("id")
                        if cap_id:
                            capabilities.append(cap_id)
                
                # Determine domain from capabilities
                device_domain = self._determine_domain(capabilities)
                
                # Filter by domain if requested
                if domain and device_domain != domain:
                    continue
                
                devices.append(DeviceInfo(
                    entity_id=device_id,
                    name=name,
                    domain=device_domain,
                    platform="smartthings",
                    capabilities=capabilities
                ))
            
            logger.info(f"Discovered {len(devices)} SmartThings devices")
            return devices
            
        except Exception as e:
            logger.error(f"Failed to discover SmartThings devices: {e}")
            return []
    
    def _determine_domain(self, capabilities: List[str]) -> str:
        """Determine device domain from capabilities"""
        if "switch" in capabilities:
            return "switch"
        elif "switchLevel" in capabilities:
            return "dimmer"
        elif "colorControl" in capabilities:
            return "light"
        elif "thermostat" in capabilities:
            return "thermostat"
        elif "lock" in capabilities:
            return "lock"
        elif "contactSensor" in capabilities:
            return "sensor"
        elif "motionSensor" in capabilities:
            return "sensor"
        else:
            return "unknown"
    
    async def get_device_status(self, device_id: str) -> Optional[DeviceState]:
        """
        Get current status of a device
        
        Args:
            device_id: SmartThings device ID
        """
        response = await self._request("GET", f"/devices/{device_id}/status")
        if not response:
            return None
        
        try:
            data = response.json()
            
            # Extract switch state from main component
            components = data.get("components", {})
            main_component = components.get("main", {})
            switch_capability = main_component.get("switch", {})
            switch_state = switch_capability.get("switch", {}).get("value", "unknown")
            
            # Get device name
            device_response = await self._request("GET", f"/devices/{device_id}")
            device_name = "Unknown"
            if device_response:
                device_data = device_response.json()
                device_name = device_data.get("label") or device_data.get("name", "Unknown")
            
            return DeviceState(
                entity_id=device_id,
                name=device_name,
                state=switch_state,
                attributes=data,
                last_updated=datetime.utcnow()
            )
            
        except Exception as e:
            logger.error(f"Failed to get SmartThings device status: {e}")
            return None
    
    async def turn_on(self, device_id: str) -> bool:
        """
        Turn a device on
        
        Args:
            device_id: SmartThings device ID
        """
        command = {
            "commands": [
                {
                    "component": "main",
                    "capability": "switch",
                    "command": "on"
                }
            ]
        }
        
        response = await self._request("POST", f"/devices/{device_id}/commands", json=command)
        if response:
            logger.info(f"SmartThings: Turned ON device {device_id}")
            return True
        else:
            logger.error(f"SmartThings: Failed to turn ON device {device_id}")
            return False
    
    async def turn_off(self, device_id: str) -> bool:
        """
        Turn a device off
        
        Args:
            device_id: SmartThings device ID
        """
        command = {
            "commands": [
                {
                    "component": "main",
                    "capability": "switch",
                    "command": "off"
                }
            ]
        }
        
        response = await self._request("POST", f"/devices/{device_id}/commands", json=command)
        if response:
            logger.info(f"SmartThings: Turned OFF device {device_id}")
            return True
        else:
            logger.error(f"SmartThings: Failed to turn OFF device {device_id}")
            return False
    
    async def set_level(self, device_id: str, level: int) -> bool:
        """
        Set dimmer/light level (0-100)
        
        Args:
            device_id: SmartThings device ID
            level: Level percentage (0-100)
        """
        command = {
            "commands": [
                {
                    "component": "main",
                    "capability": "switchLevel",
                    "command": "setLevel",
                    "arguments": [level]
                }
            ]
        }
        
        response = await self._request("POST", f"/devices/{device_id}/commands", json=command)
        if response:
            logger.info(f"SmartThings: Set device {device_id} level to {level}%")
            return True
        else:
            logger.error(f"SmartThings: Failed to set device {device_id} level")
            return False
