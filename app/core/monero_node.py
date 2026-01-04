"""
Monero Node RPC Service
Handles communication with Monero node (monerod) RPC interface
"""
import aiohttp
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class MoneroNodeRPC:
    """Interface to Monero node JSON-RPC API"""
    
    def __init__(self, host: str, port: int, username: Optional[str] = None, password: Optional[str] = None):
        """
        Initialize Monero node RPC client
        
        Args:
            host: Node IP address or hostname
            port: RPC port (18081 for mainnet, 18089 for stagenet)
            username: Optional RPC username for authentication
            password: Optional RPC password for authentication
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.base_url = f"http://{host}:{port}"
        self.timeout = aiohttp.ClientTimeout(total=10)
        
    async def json_rpc_request(self, method: str, params: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """
        Make JSON-RPC 2.0 request to Monero node
        
        Args:
            method: RPC method name
            params: Optional method parameters
            
        Returns:
            Response dictionary or None on error
        """
        payload = {
            "jsonrpc": "2.0",
            "id": "0",
            "method": method
        }
        
        if params:
            payload["params"] = params
            
        auth = None
        if self.username and self.password:
            auth = aiohttp.BasicAuth(self.username, self.password)
            
        try:
            async with aiohttp.ClientSession(timeout=self.timeout, auth=auth) as session:
                async with session.post(f"{self.base_url}/json_rpc", json=payload) as response:
                    if response.status != 200:
                        logger.error(f"Monero node RPC error: HTTP {response.status}")
                        return None
                        
                    data = await response.json()
                    
                    if "error" in data:
                        error = data["error"]
                        logger.error(f"Monero node RPC error: {error.get('message', 'Unknown error')}")
                        return None
                        
                    return data.get("result")
                    
        except aiohttp.ClientError as e:
            logger.error(f"Monero node RPC connection error: {e}")
            return None
        except Exception as e:
            logger.error(f"Monero node RPC unexpected error: {e}")
            return None
            
    async def get_info(self) -> Optional[Dict[str, Any]]:
        """
        Get general node information
        
        Returns:
            Dictionary with network stats:
            - height: Current blockchain height
            - difficulty: Current network difficulty
            - target: Block time target (seconds)
            - tx_count: Total transaction count
            - outgoing_connections_count: Peer connections
            - etc.
        """
        return await self.json_rpc_request("get_info")
        
    async def get_last_block_header(self) -> Optional[Dict[str, Any]]:
        """
        Get the last block header
        
        Returns:
            Dictionary with block header info:
            - height: Block height
            - hash: Block hash
            - timestamp: Block timestamp
            - reward: Block reward in atomic units
            - difficulty: Block difficulty
            - etc.
        """
        result = await self.json_rpc_request("get_last_block_header")
        return result.get("block_header") if result else None
        
    async def get_block_header_by_height(self, height: int) -> Optional[Dict[str, Any]]:
        """
        Get block header for specific height
        
        Args:
            height: Block height to query
            
        Returns:
            Dictionary with block header info (same structure as get_last_block_header)
        """
        result = await self.json_rpc_request("get_block_header_by_height", {"height": height})
        return result.get("block_header") if result else None
        
    async def get_block_count(self) -> Optional[int]:
        """
        Get current blockchain height
        
        Returns:
            Current block height or None on error
        """
        result = await self.json_rpc_request("get_block_count")
        return result.get("count") if result else None
        
    async def test_connection(self) -> bool:
        """
        Test if node is reachable and responding
        
        Returns:
            True if connection successful, False otherwise
        """
        result = await self.get_info()
        return result is not None
        
    async def get_difficulty(self) -> Optional[int]:
        """
        Get current network difficulty
        
        Returns:
            Network difficulty or None on error
        """
        info = await self.get_info()
        return info.get("difficulty") if info else None
        
    async def get_network_hashrate(self) -> Optional[float]:
        """
        Calculate estimated network hashrate from difficulty and target
        
        Returns:
            Estimated network hashrate in H/s or None on error
        """
        info = await self.get_info()
        if not info:
            return None
            
        difficulty = info.get("difficulty")
        target = info.get("target", 120)  # Default 120 seconds for Monero
        
        if difficulty and target:
            # Hashrate = difficulty / target time
            return float(difficulty) / float(target)
            
        return None
