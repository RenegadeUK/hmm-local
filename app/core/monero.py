"""
Monero P2Pool monitoring service - auto-detects P2Pool pools and tracks payouts
"""
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Set
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import app_config
from core.database import P2PoolTransaction, Pool

logger = logging.getLogger(__name__)


class MoneroWalletService:
    """Service for monitoring Monero wallet transactions from P2Pool"""
    
    @staticmethod
    def is_p2pool_pool(pool_url: str, pool_port: int) -> bool:
        """Check if a pool is a P2Pool instance"""
        # P2Pool mini uses port 3333, main uses 3333
        # Common local IPs or p2pool in the hostname
        if pool_port == 3333:
            if "p2pool" in pool_url.lower():
                return True
            # Check for local/private IPs
            if pool_url.startswith("10.") or pool_url.startswith("192.168.") or pool_url.startswith("172."):
                return True
        return False
    
    @staticmethod
    async def get_p2pool_wallets(db: AsyncSession) -> Set[str]:
        """Get all unique wallet addresses from P2Pool pools"""
        result = await db.execute(
            select(Pool).where(Pool.enabled == True)
        )
        pools = result.scalars().all()
        
        wallets = set()
        for pool in pools:
            if MoneroWalletService.is_p2pool_pool(pool.url, pool.port):
                # P2Pool uses wallet address as the "user" field
                if pool.user and len(pool.user) == 95:  # Monero address length
                    wallets.add(pool.user)
                    logger.debug(f"Found P2Pool wallet from pool {pool.name}: {pool.user[:10]}...")
        
        return wallets
    
    @staticmethod
    async def fetch_transactions(
        wallet_address: str,
        view_key: str,
        node_url: str,
        start_height: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Fetch P2Pool payouts using mini.p2pool.observer API
        
        No view key needed - just wallet address
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Use P2Pool Observer API - mini sidechain
                url = f"https://mini.p2pool.observer/api/payouts/{wallet_address}"
                
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return MoneroWalletService._parse_p2pool_payouts(data)
                    else:
                        logger.warning(f"Failed to fetch P2Pool payouts: HTTP {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error fetching P2Pool payouts: {e}")
            return []
    
    @staticmethod
    def _parse_p2pool_payouts(data: List) -> List[Dict[str, Any]]:
        """Parse P2Pool payout data from API response"""
        transactions = []
        
        if not isinstance(data, list):
            return transactions
        
        for payout in data:
            try:
                tx = {
                    "tx_hash": payout.get("coinbase_id", ""),
                    "amount_xmr": float(payout.get("coinbase_reward", 0)) / 1e12,  # Convert from atomic units
                    "block_height": int(payout.get("main_height", 0)),
                    "timestamp": datetime.fromtimestamp(int(payout.get("timestamp", 0))),
                    "unlock_time": int(payout.get("including_height", 0)) + 60,  # Monero unlocks after 60 blocks
                    "confirmations": 10  # Assume confirmed if in API
                }
                transactions.append(tx)
            except Exception as e:
                logger.error(f"Error parsing P2Pool payout: {e}")
                continue
        
        return transactions
    
    @staticmethod
    async def sync_transactions(db: AsyncSession) -> int:
        """
        Sync new transactions from all P2Pool wallets (auto-detected from pools)
        Returns number of new transactions found
        """
        # Get all P2Pool wallet addresses from configured pools
        wallets = await MoneroWalletService.get_p2pool_wallets(db)
        
        if not wallets:
            logger.debug("No P2Pool pools configured")
            return 0
        
        total_new = 0
        
        for wallet_address in wallets:
            try:
                # Get last known block height for this wallet
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
                    None,  # view_key not needed
                    None,  # node_url not needed
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
                    total_new += new_count
                    logger.info(f"✓ Synced {new_count} new P2Pool transaction(s) for ...{wallet_address[-8:]}")
            
            except Exception as e:
                logger.error(f"Failed to sync P2Pool wallet ...{wallet_address[-8:]}: {e}")
                continue
        
        if total_new > 0:
            await db.commit()
        
        return total_new
    
    @staticmethod
    async def get_24h_earnings(db: AsyncSession, wallet_address: Optional[str] = None) -> float:
        """
        Calculate 24h earnings in XMR for a specific wallet or all wallets
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        
        query = select(P2PoolTransaction).where(P2PoolTransaction.timestamp >= cutoff_time)
        
        if wallet_address:
            query = query.where(P2PoolTransaction.wallet_address == wallet_address)
        
        result = await db.execute(query)
        transactions = result.scalars().all()
        
        total_xmr = sum(tx.amount_xmr for tx in transactions)
        return total_xmr
    
    @staticmethod
    async def get_total_balance(db: AsyncSession, wallet_address: Optional[str] = None) -> float:
        """
        Calculate total received balance in XMR (sum of all incoming transactions)
        This represents all-time rewards, doesn't account for withdrawals
        """
        query = select(P2PoolTransaction)
        
        if wallet_address:
            query = query.where(P2PoolTransaction.wallet_address == wallet_address)
        
        result = await db.execute(query)
        transactions = result.scalars().all()
        
        total_xmr = sum(tx.amount_xmr for tx in transactions)
        return total_xmr
    
    @staticmethod
    async def get_current_balance(wallet_address: str) -> float:
        """
        Get current balance from sum of all P2Pool payouts for a specific wallet
        Note: This doesn't account for withdrawals - shows total mined
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Use P2Pool Observer API
                url = f"https://mini.p2pool.observer/api/payouts/{wallet_address}"
                
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Sum all payouts
                        total_atomic = sum(payout.get("coinbase_reward", 0) for payout in data)
                        balance_xmr = float(total_atomic) / 1e12
                        return balance_xmr
                    else:
                        logger.warning(f"Failed to fetch P2Pool balance: HTTP {response.status}")
                        return 0.0
        except Exception as e:
            logger.error(f"Error fetching P2Pool balance: {e}")
            return 0.0
    
    @staticmethod
    async def get_stats(db: AsyncSession) -> Dict[str, Any]:
        """
        Get comprehensive P2Pool stats for all configured wallets
        """
        # Get all P2Pool wallets from pools
        wallets = await MoneroWalletService.get_p2pool_wallets(db)
        
        if not wallets:
            return {
                "enabled": False,
                "wallets": [],
                "wallet_address": None,
                "full_wallet_address": None,
                "total_balance_xmr": 0.0,
                "total_earnings_24h_xmr": 0.0,
                "transaction_count": 0,
                "last_payout": None
            }
        
        wallet_stats = []
        total_balance = 0.0
        total_24h = 0.0
        total_tx_count = 0
        latest_payout = None
        
        for wallet_address in wallets:
            # Get all transactions for this wallet
            result = await db.execute(
                select(P2PoolTransaction)
                .where(P2PoolTransaction.wallet_address == wallet_address)
                .order_by(P2PoolTransaction.timestamp.desc())
            )
            all_transactions = result.scalars().all()
            
            # Calculate stats
            wallet_total = sum(tx.amount_xmr for tx in all_transactions)
            
            cutoff_24h = datetime.utcnow() - timedelta(hours=24)
            recent = [tx for tx in all_transactions if tx.timestamp >= cutoff_24h]
            wallet_24h = sum(tx.amount_xmr for tx in recent)
            
            wallet_stats.append({
                "address": wallet_address,
                "balance_xmr": wallet_total,
                "earnings_24h_xmr": wallet_24h,
                "transaction_count": len(all_transactions),
                "last_payout": all_transactions[0].timestamp if all_transactions else None
            })
            
            total_balance += wallet_total
            total_24h += wallet_24h
            total_tx_count += len(all_transactions)
            
            if all_transactions and (not latest_payout or all_transactions[0].timestamp > latest_payout):
                latest_payout = all_transactions[0].timestamp
        
        # Get first wallet address for display (truncated and full)
        first_wallet = list(wallets)[0] if wallets else None
        wallet_display = f"{first_wallet[:8]}...{first_wallet[-8:]}" if first_wallet else None
        
        return {
            "enabled": True,
            "wallets": wallet_stats,
            "wallet_address": wallet_display,
            "full_wallet_address": first_wallet,
            "total_balance_xmr": round(total_balance, 6),
            "total_earnings_24h_xmr": round(total_24h, 6),
            "transaction_count": total_tx_count,
            "last_payout": latest_payout.isoformat() if latest_payout else None
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
        # Get wallet stats (existing functionality - now auto-detected)
        wallet_stats = await MoneroWalletService.get_stats(db)
        
        # Get API stats if enabled
        local_stats = await P2PoolAPIService.fetch_local_stats()
        pool_stats = await P2PoolAPIService.fetch_pool_stats()
        
        result = {
            "enabled": wallet_stats.get("enabled", False) or P2PoolAPIService.is_api_enabled(),
            "wallet_enabled": wallet_stats.get("enabled", False),
            "api_enabled": P2PoolAPIService.is_api_enabled(),
            
            # Wallet tracking (blockchain) - now from auto-detected pools
            "wallet_address": wallet_stats.get("wallet_address"),  # Truncated for display
            "full_wallet_address": wallet_stats.get("full_wallet_address"),  # Full address for links
            "balance_xmr": wallet_stats.get("total_balance_xmr", 0),
            "total_received_xmr": wallet_stats.get("total_balance_xmr", 0),
            "earnings_24h_xmr": wallet_stats.get("total_earnings_24h_xmr", 0),
            "transaction_count": wallet_stats.get("transaction_count", 0),
            "last_payout": wallet_stats.get("last_payout"),
            "confirmed_balance": wallet_stats.get("total_balance_xmr", 0),
            
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
