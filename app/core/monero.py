"""
Monero wallet monitoring service for P2Pool and other XMR mining pools
"""
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import app_config
from core.database import P2PoolTransaction

logger = logging.getLogger(__name__)


class MoneroWalletService:
    """Service for monitoring Monero wallet transactions via daemon RPC"""
    
    @staticmethod
    def is_enabled() -> bool:
        """Check if P2Pool wallet monitoring is enabled"""
        return app_config.get("p2pool_enabled", False)
    
    @staticmethod
    def get_wallet_address() -> Optional[str]:
        """Get configured wallet address"""
        return app_config.get("p2pool_wallet_address")
    
    @staticmethod
    def get_view_key() -> Optional[str]:
        """Get configured private view key"""
        return app_config.get("p2pool_view_key")
    
    @staticmethod
    def get_node_url() -> str:
        """Get configured Monero node URL"""
        return app_config.get("p2pool_node_url", "http://localhost:18081")
    
    @staticmethod
    async def fetch_transactions(
        wallet_address: str,
        view_key: str,
        node_url: str,
        start_height: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Fetch transactions for a wallet using the daemon RPC
        
        Uses the /get_payments RPC call which requires view key to decrypt outputs
        """
        try:
            # For Monero, we need to use a block explorer API or run monero-wallet-rpc
            # Since we have daemon RPC, we'll use xmrchain.net API as a bridge
            async with aiohttp.ClientSession() as session:
                # Use xmrchain.net API to get transactions with view key
                url = f"https://xmrchain.net/api/outputsblocks"
                params = {
                    "address": wallet_address,
                    "viewkey": view_key,
                    "limit": 100,
                    "mempool": 0
                }
                
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return MoneroWalletService._parse_transactions(data)
                    else:
                        logger.warning(f"Failed to fetch transactions: HTTP {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error fetching Monero transactions: {e}")
            return []
    
    @staticmethod
    def _parse_transactions(data: Dict) -> List[Dict[str, Any]]:
        """Parse transaction data from API response"""
        transactions = []
        
        if not isinstance(data, dict):
            return transactions
        
        # Parse outputs/blocks data structure
        outputs = data.get("outputs", [])
        
        for output in outputs:
            try:
                tx = {
                    "tx_hash": output.get("tx_hash", ""),
                    "amount_xmr": float(output.get("amount", 0)) / 1e12,  # Convert from atomic units
                    "block_height": int(output.get("block_no", 0)),
                    "timestamp": datetime.fromtimestamp(int(output.get("timestamp", 0))),
                    "unlock_time": int(output.get("unlock_time", 0)),
                    "confirmations": int(output.get("confirmations", 0))
                }
                transactions.append(tx)
            except Exception as e:
                logger.error(f"Error parsing transaction: {e}")
                continue
        
        return transactions
    
    @staticmethod
    async def sync_transactions(db: AsyncSession) -> int:
        """
        Sync new transactions from the wallet
        Returns number of new transactions found
        """
        if not MoneroWalletService.is_enabled():
            return 0
        
        wallet_address = MoneroWalletService.get_wallet_address()
        view_key = MoneroWalletService.get_view_key()
        node_url = MoneroWalletService.get_node_url()
        
        if not wallet_address or not view_key:
            logger.warning("P2Pool enabled but wallet address or view key not configured")
            return 0
        
        # Get last known block height
        result = await db.execute(
            select(P2PoolTransaction)
            .where(P2PoolTransaction.wallet_address == wallet_address)
            .order_by(P2PoolTransaction.block_height.desc())
            .limit(1)
        )
        last_tx = result.scalar_one_or_none()
        start_height = last_tx.block_height if last_tx else 0
        
        # Fetch new transactions
        transactions = await MoneroWalletService.fetch_transactions(
            wallet_address,
            view_key,
            node_url,
            start_height
        )
        
        new_count = 0
        for tx_data in transactions:
            # Check if transaction already exists
            result = await db.execute(
                select(P2PoolTransaction)
                .where(P2PoolTransaction.tx_hash == tx_data["tx_hash"])
            )
            existing = result.scalar_one_or_none()
            
            if not existing:
                # Add new transaction
                new_tx = P2PoolTransaction(
                    wallet_address=wallet_address,
                    tx_hash=tx_data["tx_hash"],
                    amount_xmr=tx_data["amount_xmr"],
                    block_height=tx_data["block_height"],
                    confirmations=tx_data["confirmations"],
                    timestamp=tx_data["timestamp"],
                    unlock_time=tx_data["unlock_time"],
                    is_confirmed=tx_data["confirmations"] >= 10
                )
                db.add(new_tx)
                new_count += 1
            else:
                # Update confirmations
                existing.confirmations = tx_data["confirmations"]
                existing.is_confirmed = tx_data["confirmations"] >= 10
        
        if new_count > 0:
            await db.commit()
            logger.info(f"✓ Synced {new_count} new P2Pool transactions")
        
        return new_count
    
    @staticmethod
    async def get_24h_earnings(db: AsyncSession) -> float:
        """
        Calculate 24h earnings in XMR
        """
        if not MoneroWalletService.is_enabled():
            return 0.0
        
        wallet_address = MoneroWalletService.get_wallet_address()
        if not wallet_address:
            return 0.0
        
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        
        result = await db.execute(
            select(P2PoolTransaction)
            .where(P2PoolTransaction.wallet_address == wallet_address)
            .where(P2PoolTransaction.timestamp >= cutoff_time)
        )
        transactions = result.scalars().all()
        
        total_xmr = sum(tx.amount_xmr for tx in transactions)
        return total_xmr
    
    @staticmethod
    async def get_total_balance(db: AsyncSession) -> float:
        """
        Calculate total received balance in XMR (sum of all incoming transactions)
        This represents all-time rewards, doesn't account for withdrawals
        """
        if not MoneroWalletService.is_enabled():
            return 0.0
        
        wallet_address = MoneroWalletService.get_wallet_address()
        if not wallet_address:
            return 0.0
        
        result = await db.execute(
            select(P2PoolTransaction)
            .where(P2PoolTransaction.wallet_address == wallet_address)
        )
        transactions = result.scalars().all()
        
        total_xmr = sum(tx.amount_xmr for tx in transactions)
        return total_xmr
    
    @staticmethod
    async def get_current_balance() -> float:
        """
        Get actual current spendable balance from blockchain
        This queries the live balance accounting for withdrawals
        """
        if not MoneroWalletService.is_enabled():
            return 0.0
        
        wallet_address = MoneroWalletService.get_wallet_address()
        view_key = MoneroWalletService.get_view_key()
        
        if not wallet_address or not view_key:
            return 0.0
        
        try:
            async with aiohttp.ClientSession() as session:
                # Use xmrchain.net API to get current balance
                url = "https://xmrchain.net/api/balance"
                params = {
                    "address": wallet_address,
                    "viewkey": view_key
                }
                
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Balance is returned in atomic units (piconero)
                        balance_atomic = data.get("total_received", 0) - data.get("total_sent", 0)
                        balance_xmr = float(balance_atomic) / 1e12
                        return max(0.0, balance_xmr)  # Ensure non-negative
                    else:
                        logger.warning(f"Failed to fetch balance: HTTP {response.status}")
                        return 0.0
        except Exception as e:
            logger.error(f"Error fetching Monero balance: {e}")
            return 0.0
    
    @staticmethod
    async def get_stats(db: AsyncSession) -> Dict[str, Any]:
        """
        Get comprehensive P2Pool wallet stats
        """
        if not MoneroWalletService.is_enabled():
            return {
                "enabled": False,
                "wallet_address": None,
                "balance_xmr": 0.0,
                "earnings_24h_xmr": 0.0,
                "transaction_count": 0,
                "last_payout": None
            }
        
        wallet_address = MoneroWalletService.get_wallet_address()
        if not wallet_address:
            return {
                "enabled": True,
                "wallet_address": None,
                "balance_xmr": 0.0,
                "earnings_24h_xmr": 0.0,
                "transaction_count": 0,
                "last_payout": None
            }
        
        # Get all transactions
        result = await db.execute(
            select(P2PoolTransaction)
            .where(P2PoolTransaction.wallet_address == wallet_address)
            .order_by(P2PoolTransaction.timestamp.desc())
        )
        all_transactions = result.scalars().all()
        
        # Calculate stats
        total_received_xmr = sum(tx.amount_xmr for tx in all_transactions)
        
        # Get actual current balance from blockchain
        current_balance = await MoneroWalletService.get_current_balance()
        
        cutoff_24h = datetime.utcnow() - timedelta(hours=24)
        earnings_24h = [tx for tx in all_transactions if tx.timestamp >= cutoff_24h]
        earnings_24h_xmr = sum(tx.amount_xmr for tx in earnings_24h)
        
        last_payout_tx = all_transactions[0] if all_transactions else None
        last_payout = last_payout_tx.timestamp.isoformat() if last_payout_tx else None
        
        return {
            "enabled": True,
            "wallet_address": wallet_address[:10] + "..." + wallet_address[-10:],  # Truncated for display
            "balance_xmr": round(current_balance, 6),  # Current spendable balance
            "total_received_xmr": round(total_received_xmr, 6),  # All-time rewards
            "earnings_24h_xmr": round(earnings_24h_xmr, 6),
            "transaction_count": len(all_transactions),
            "last_payout": last_payout,
            "confirmed_balance": round(sum(tx.amount_xmr for tx in all_transactions if tx.is_confirmed), 6)
        }
    
    @staticmethod
    def format_xmr(amount: float) -> str:
        """Format XMR amount for display"""
        return f"{amount:.6f} XMR"


class P2PoolAPIService:
    """Service for fetching local P2Pool mining statistics via API"""
    
    @staticmethod
    def is_api_enabled() -> bool:
        """Check if P2Pool API integration is enabled"""
        return app_config.get("p2pool_api_enabled", False)
    
    @staticmethod
    def get_api_url() -> str:
        """Get configured P2Pool API URL"""
        return app_config.get("p2pool_api_url", "")
    
    @staticmethod
    async def fetch_local_stats() -> Optional[Dict[str, Any]]:
        """Fetch local miner statistics from P2Pool API"""
        if not P2PoolAPIService.is_api_enabled():
            return None
        
        api_url = P2PoolAPIService.get_api_url()
        if not api_url:
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{api_url}/api/log/local/stratum/tail/1",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("success") and data.get("lines"):
                            import json
                            stats = json.loads(data["lines"][0])
                            return stats
                    return None
        except Exception as e:
            logger.error(f"Failed to fetch P2Pool local stats: {e}")
            return None
    
    @staticmethod
    async def fetch_pool_stats() -> Optional[Dict[str, Any]]:
        """Fetch pool-wide statistics from P2Pool API"""
        if not P2PoolAPIService.is_api_enabled():
            return None
        
        api_url = P2PoolAPIService.get_api_url()
        if not api_url:
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{api_url}/api/log/pool/stats/tail/1",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("success") and data.get("lines"):
                            import json
                            stats = json.loads(data["lines"][0])
                            return stats.get("pool_statistics", {})
                    return None
        except Exception as e:
            logger.error(f"Failed to fetch P2Pool pool stats: {e}")
            return None
    
    @staticmethod
    def format_hashrate(hashrate: float) -> str:
        """Format hashrate for display"""
        if hashrate >= 1_000_000_000:
            return f"{hashrate / 1_000_000_000:.2f} GH/s"
        elif hashrate >= 1_000_000:
            return f"{hashrate / 1_000_000:.2f} MH/s"
        elif hashrate >= 1_000:
            return f"{hashrate / 1_000:.2f} KH/s"
        else:
            return f"{hashrate:.0f} H/s"
    
    @staticmethod
    async def get_combined_stats(db: AsyncSession) -> Dict[str, Any]:
        """Get combined wallet + API stats for dashboard"""
        # Get wallet stats (existing functionality)
        wallet_stats = await MoneroWalletService.get_stats(db)
        
        # Get full wallet address for external links (not truncated)
        full_wallet_address = MoneroWalletService.get_wallet_address()
        
        # Get API stats if enabled
        local_stats = await P2PoolAPIService.fetch_local_stats()
        pool_stats = await P2PoolAPIService.fetch_pool_stats()
        
        result = {
            "enabled": wallet_stats.get("enabled", False) or P2PoolAPIService.is_api_enabled(),
            "wallet_enabled": wallet_stats.get("enabled", False),
            "api_enabled": P2PoolAPIService.is_api_enabled(),
            
            # Wallet tracking (blockchain)
            "wallet_address": wallet_stats.get("wallet_address"),  # Truncated for display
            "full_wallet_address": full_wallet_address,  # Full address for links
            "balance_xmr": wallet_stats.get("balance_xmr", 0),
            "total_received_xmr": wallet_stats.get("total_received_xmr", 0),
            "earnings_24h_xmr": wallet_stats.get("earnings_24h_xmr", 0),
            "transaction_count": wallet_stats.get("transaction_count", 0),
            "last_payout": wallet_stats.get("last_payout"),
            "confirmed_balance": wallet_stats.get("confirmed_balance", 0),
            
            # Local miner stats (P2Pool API)
            "workers": None,
            "local_hashrate": None,
            "local_hashrate_formatted": None,
            "shares_found": None,
            "shares_failed": None,
            "current_effort": None,
            "last_share_timestamp": None,
            
            # Pool stats (P2Pool API)
            "pool_hashrate": None,
            "pool_hashrate_formatted": None,
            "pool_miners": None
        }
        
        if local_stats:
            result["workers"] = local_stats.get("connections", 0)
            result["local_hashrate"] = local_stats.get("hashrate_15m", 0)
            result["local_hashrate_formatted"] = P2PoolAPIService.format_hashrate(local_stats.get("hashrate_15m", 0))
            result["shares_found"] = local_stats.get("shares_found", 0)
            result["shares_failed"] = local_stats.get("shares_failed", 0)
            result["current_effort"] = local_stats.get("current_effort", 0)
            result["last_share_timestamp"] = local_stats.get("last_share_found_time")
        
        if pool_stats:
            result["pool_hashrate"] = pool_stats.get("hashRate", 0)
            result["pool_hashrate_formatted"] = P2PoolAPIService.format_hashrate(pool_stats.get("hashRate", 0))
            result["pool_miners"] = pool_stats.get("miners", 0)
        
        return result
