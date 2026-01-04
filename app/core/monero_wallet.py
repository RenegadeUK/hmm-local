"""
Monero Wallet RPC Service
Handles communication with monero-wallet-rpc for tracking rewards
"""
import aiohttp
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

# Monero atomic units: 1 XMR = 1e12 atomic units
ATOMIC_UNITS_PER_XMR = 1_000_000_000_000


class MoneroWalletRPC:
    """Interface to Monero wallet RPC API"""
    
    def __init__(self, host: str, port: int, username: Optional[str] = None, password: Optional[str] = None):
        """
        Initialize Monero wallet RPC client
        
        Args:
            host: Wallet RPC IP address or hostname
            port: RPC port (18083 default for wallet-rpc)
            username: Optional RPC username for authentication
            password: Optional RPC password for authentication
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.base_url = f"http://{host}:{port}"
        self.timeout = aiohttp.ClientTimeout(total=30)  # Wallet operations can be slower
        
    async def json_rpc_request(self, method: str, params: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """
        Make JSON-RPC 2.0 request to wallet
        
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
                        logger.error(f"Wallet RPC error: HTTP {response.status}")
                        return None
                        
                    data = await response.json()
                    
                    if "error" in data:
                        error = data["error"]
                        logger.error(f"Wallet RPC error: {error.get('message', 'Unknown error')}")
                        return None
                        
                    return data.get("result")
                    
        except aiohttp.ClientError as e:
            logger.error(f"Wallet RPC connection error: {e}")
            return None
        except Exception as e:
            logger.error(f"Wallet RPC unexpected error: {e}")
            return None
            
    async def get_address(self) -> Optional[str]:
        """
        Get primary wallet address
        
        Returns:
            Wallet address string or None on error
        """
        result = await self.json_rpc_request("get_address", {"account_index": 0})
        if result and "address" in result:
            return result["address"]
        return None
        
    async def get_balance(self) -> Optional[Dict[str, Any]]:
        """
        Get wallet balance
        
        Returns:
            Dictionary with balance info:
            - balance: Total balance in atomic units
            - unlocked_balance: Unlocked balance in atomic units
            - balance_xmr: Total balance in XMR (calculated)
            - unlocked_balance_xmr: Unlocked balance in XMR (calculated)
        """
        result = await self.json_rpc_request("get_balance", {"account_index": 0})
        if not result:
            return None
            
        balance_atomic = result.get("balance", 0)
        unlocked_atomic = result.get("unlocked_balance", 0)
        
        return {
            "balance": balance_atomic,
            "unlocked_balance": unlocked_atomic,
            "balance_xmr": balance_atomic / ATOMIC_UNITS_PER_XMR,
            "unlocked_balance_xmr": unlocked_atomic / ATOMIC_UNITS_PER_XMR
        }
        
    async def get_transfers(self, 
                           transfer_type: str = "in", 
                           min_height: Optional[int] = None,
                           max_height: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Get wallet transfers (transactions)
        
        Args:
            transfer_type: Type of transfers ("in", "out", "pending", "failed", "pool")
            min_height: Optional minimum block height filter
            max_height: Optional maximum block height filter
            
        Returns:
            List of transfer dictionaries:
            - amount: Amount in atomic units
            - block_height: Block height
            - timestamp: Unix timestamp
            - txid: Transaction hash
            - type: Transfer type
            - etc.
        """
        params = {
            "in": transfer_type == "in",
            "out": transfer_type == "out",
            "pending": transfer_type == "pending",
            "failed": transfer_type == "failed",
            "pool": transfer_type == "pool",
            "account_index": 0
        }
        
        if min_height is not None:
            params["min_height"] = min_height
        if max_height is not None:
            params["max_height"] = max_height
            
        result = await self.json_rpc_request("get_transfers", params)
        
        if not result:
            return []
            
        # Return the specific transfer type list
        return result.get(transfer_type, [])
        
    async def get_incoming_transfers(self, min_height: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get incoming transfers (rewards)
        
        Args:
            min_height: Optional minimum block height to filter from
            
        Returns:
            List of incoming transfer dictionaries with calculated XMR amounts
        """
        transfers = await self.get_transfers("in", min_height=min_height)
        
        if not transfers:
            return []
            
        # Add calculated XMR amount to each transfer
        for transfer in transfers:
            amount_atomic = transfer.get("amount", 0)
            transfer["amount_xmr"] = amount_atomic / ATOMIC_UNITS_PER_XMR
            
        return transfers
        
    async def get_transfer_by_txid(self, txid: str) -> Optional[Dict[str, Any]]:
        """
        Get specific transfer by transaction ID
        
        Args:
            txid: Transaction hash
            
        Returns:
            Transfer dictionary or None if not found
        """
        result = await self.json_rpc_request("get_transfer_by_txid", {"txid": txid})
        
        if result and "transfer" in result:
            transfer = result["transfer"]
            amount_atomic = transfer.get("amount", 0)
            transfer["amount_xmr"] = amount_atomic / ATOMIC_UNITS_PER_XMR
            return transfer
            
        return None
        
    async def test_connection(self) -> bool:
        """
        Test if wallet is reachable and responding
        
        Returns:
            True if connection successful, False otherwise
        """
        # Try to get the wallet address as a simple test
        address = await self.get_address()
        return address is not None
        
    async def get_height(self) -> Optional[int]:
        """
        Get wallet sync height
        
        Returns:
            Current wallet height or None on error
        """
        result = await self.json_rpc_request("get_height")
        return result.get("height") if result else None
