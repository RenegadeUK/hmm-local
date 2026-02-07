"""
Network Discovery Service for Miners
Scans local network for supported mining hardware
"""
import asyncio
import socket
import ipaddress
import logging
from typing import List, Dict, Any
import aiohttp
import json

logger = logging.getLogger(__name__)


class MinerDiscoveryService:
    """Service for discovering miners on the local network"""
    
    # Common HTTP ports for Bitaxe/NerdQaxe
    HTTP_PORTS = [80, 8080]
    
    # cgminer API port for Avalon Nano
    CGMINER_PORT = 4028
    
    @staticmethod
    async def discover_miners(network_cidr: str = None, timeout: float = 2.0) -> List[Dict[str, Any]]:
        """
        Discover miners on the network
        
        Args:
            network_cidr: Network CIDR (e.g., "192.168.1.0/24"). If None, auto-detect
            timeout: Timeout for each connection attempt in seconds
            
        Returns:
            List of discovered miners with their details
        """
        if not network_cidr:
            network_cidr = MinerDiscoveryService._get_local_network()
            if not network_cidr:
                logger.error("Could not determine local network")
                return []
        
        logger.info(f"Starting miner discovery on network: {network_cidr}")
        
        discovered = []
        network = ipaddress.ip_network(network_cidr, strict=False)
        
        # Scan hosts in batches to avoid overwhelming the network
        batch_size = 50
        hosts = list(network.hosts())
        
        for i in range(0, len(hosts), batch_size):
            batch = hosts[i:i + batch_size]
            batch_tasks = [
                MinerDiscoveryService._scan_host(str(host), timeout)
                for host in batch
            ]
            
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, dict) and result:
                    discovered.append(result)
        
        logger.info(f"Discovery complete. Found {len(discovered)} miners")
        return discovered
    
    @staticmethod
    async def _scan_host(ip: str, timeout: float) -> Dict[str, Any]:
        """Scan a single host for mining hardware"""
        
        # Try Avalon Nano (cgminer API)
        avalon = await MinerDiscoveryService._check_cgminer(ip, timeout)
        if avalon:
            return avalon
        
        # Try Bitaxe/NerdQaxe (HTTP API)
        for port in MinerDiscoveryService.HTTP_PORTS:
            bitaxe = await MinerDiscoveryService._check_bitaxe(ip, port, timeout)
            if bitaxe:
                return bitaxe
        
        return {}
    
    @staticmethod
    async def _check_cgminer(ip: str, timeout: float) -> Dict[str, Any]:
        """Check if host is running cgminer API (Avalon Nano)"""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, MinerDiscoveryService.CGMINER_PORT),
                timeout=timeout
            )
            
            # Send 'version' command
            command = json.dumps({"command": "version"}) + "\n"
            writer.write(command.encode())
            await writer.drain()
            
            response = await asyncio.wait_for(reader.read(4096), timeout=timeout)
            writer.close()
            await writer.wait_closed()
            
            if response:
                data = json.loads(response.decode().strip('\x00'))
                
                # Check if it's an Avalon device - check PROD or MODEL fields
                if 'VERSION' in data and len(data.get('VERSION', [])) > 0:
                    version_info = data['VERSION'][0]
                    prod = version_info.get('PROD', '').lower()
                    model = version_info.get('MODEL', '').lower()
                    
                    # Check if it's an Avalon device (Nano3, Nano3s, etc)
                    if 'avalon' in prod or 'avalon' in model or 'nano' in prod or 'nano' in model:
                        return {
                            'ip': ip,
                            'port': MinerDiscoveryService.CGMINER_PORT,
                            'type': 'avalon_nano',
                            'name': f"Avalon Nano ({ip})",
                            'details': {
                                'product': version_info.get('PROD', 'Unknown'),
                                'model': version_info.get('MODEL', 'Unknown'),
                                'cgminer': version_info.get('CGMiner', 'Unknown'),
                                'api_version': version_info.get('API', 'Unknown')
                            }
                        }
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, json.JSONDecodeError):
            pass
        except Exception as e:
            logger.debug(f"Error checking cgminer at {ip}: {e}")
        
        return {}
    
    @staticmethod
    async def _check_bitaxe(ip: str, port: int, timeout: float) -> Dict[str, Any]:
        """Check if host is running Bitaxe/NerdQaxe HTTP API"""
        try:
            async with aiohttp.ClientSession() as session:
                # Try to get system info
                url = f"http://{ip}:{port}/api/system/info"
                
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Determine miner type from response
                        device_model = data.get('ASICModel', '').lower()
                        hostname = data.get('hostname', '').lower()
                        
                        miner_type = 'bitaxe'
                        if 'nerd' in hostname or 'qaxe' in device_model:
                            miner_type = 'nerdqaxe'
                        
                        return {
                            'ip': ip,
                            'port': port,
                            'type': miner_type,
                            'name': f"{data.get('hostname', miner_type.title())} ({ip})",
                            'details': {
                                'hostname': data.get('hostname'),
                                'asic_model': data.get('ASICModel'),
                                'version': data.get('version'),
                                'mac': data.get('macAddr')
                            }
                        }
        except (asyncio.TimeoutError, aiohttp.ClientError, json.JSONDecodeError):
            pass
        except Exception as e:
            logger.debug(f"Error checking HTTP API at {ip}:{port}: {e}")
        
        return {}
    
    @staticmethod
    def _get_local_network() -> str:
        """Auto-detect local network CIDR"""
        try:
            # Get local IP address
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            
            # Assume /24 subnet (common for home networks)
            # More sophisticated detection could use netifaces library
            ip_parts = local_ip.split('.')
            network = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.0/24"
            
            logger.info(f"Auto-detected local network: {network}")
            return network
            
        except Exception as e:
            logger.error(f"Failed to auto-detect network: {e}")
            return None
    
    @staticmethod
    async def verify_miner_connection(miner_type: str, ip: str, port: int) -> bool:
        """
        Verify that a miner is still reachable
        
        Args:
            miner_type: Type of miner (avalon_nano, bitaxe, nerdqaxe)
            ip: IP address
            port: Port number
            
        Returns:
            True if miner is reachable, False otherwise
        """
        try:
            if miner_type == 'avalon_nano':
                result = await MinerDiscoveryService._check_cgminer(ip, timeout=3.0)
                return bool(result)
            else:
                result = await MinerDiscoveryService._check_bitaxe(ip, port, timeout=3.0)
                return bool(result)
        except Exception as e:
            logger.error(f"Error verifying miner connection at {ip}:{port}: {e}")
            return False
