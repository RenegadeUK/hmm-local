"""
Energy Optimization Service
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import Miner, EnergyPrice, Telemetry, Pool
from core.config import app_config


async def get_current_energy_price(db: AsyncSession) -> Optional[EnergyPrice]:
    """
    Get the current energy price for the configured region
    
    Args:
        db: Database session
    
    Returns:
        Current EnergyPrice object or None if not available
    """
    region = app_config.get("octopus_agile.region", "H")
    now = datetime.utcnow()
    
    result = await db.execute(
        select(EnergyPrice)
        .where(EnergyPrice.region == region)
        .where(EnergyPrice.valid_from <= now)
        .where(EnergyPrice.valid_to > now)
        .limit(1)
    )
    return result.scalar_one_or_none()


class EnergyOptimizationService:
    """Service for energy optimization and profitability calculations"""
    
    # Coin algorithm types
    ALGO_SHA256 = "SHA256"
    ALGO_RANDOMX = "RandomX"
    
    # Pool to coin mapping
    POOL_COINS = {
        "bch.solopool.org": {"coin": "BCH", "algo": ALGO_SHA256, "block_reward": 3.125, "block_time": 600},
        "dgb.solopool.org": {"coin": "DGB", "algo": ALGO_SHA256, "block_reward": 277.376, "block_time": 15},
        "btc.solopool.org": {"coin": "BTC", "algo": ALGO_SHA256, "block_reward": 3.125, "block_time": 600},
        "eu1.solopool.org": {"coin": "XMR", "algo": ALGO_RANDOMX, "block_reward": 0.6, "block_time": 120},
        "pool.braiins.com": {"coin": "BTC", "algo": ALGO_SHA256, "block_reward": 3.125, "block_time": 600},
    }
    
    @staticmethod
    async def calculate_profitability(
        miner_id: int,
        db: AsyncSession,
        hours: int = 24,
        coin_prices: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Calculate mining profitability (revenue - energy cost)
        
        Args:
            miner_id: Miner ID
            db: Database session
            hours: Time period in hours
            coin_prices: Dict of coin prices in GBP (e.g. {"BTC": 75000, "BCH": 350})
        
        Returns:
            Dict with profitability metrics
        """
        # Get miner
        result = await db.execute(select(Miner).where(Miner.id == miner_id))
        miner = result.scalar_one_or_none()
        
        if not miner:
            return {"error": "Miner not found"}
        
        # Get telemetry
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        result = await db.execute(
            select(Telemetry)
            .where(Telemetry.miner_id == miner_id)
            .where(Telemetry.timestamp >= cutoff)
            .order_by(Telemetry.timestamp.desc())
        )
        telemetry_data = result.scalars().all()
        
        if not telemetry_data:
            return {"error": "No telemetry data"}
        
        # Calculate energy cost
        energy_cost = await EnergyOptimizationService._calculate_energy_cost(
            miner_id, db, hours, telemetry_data
        )
        
        # Get current pool
        latest = telemetry_data[0]
        pool_in_use = latest.pool_in_use
        
        if not pool_in_use:
            return {
                "miner_id": miner_id,
                "miner_name": miner.name,
                "period_hours": hours,
                "energy_cost_gbp": energy_cost,
                "revenue_gbp": 0,
                "profit_gbp": -energy_cost,
                "roi_percent": -100,
                "error": "No active pool"
            }
        
        # Determine coin being mined
        coin_info = None
        for pool_domain, info in EnergyOptimizationService.POOL_COINS.items():
            if pool_domain in pool_in_use:
                coin_info = info
                break
        
        if not coin_info:
            return {
                "miner_id": miner_id,
                "miner_name": miner.name,
                "period_hours": hours,
                "energy_cost_gbp": energy_cost,
                "revenue_gbp": 0,
                "profit_gbp": -energy_cost,
                "roi_percent": -100,
                "error": "Unknown pool/coin"
            }
        
        # Calculate expected revenue
        avg_hashrate = sum(t.hashrate for t in telemetry_data if t.hashrate) / len(telemetry_data)
        
        # For pool mining (Braiins), use historical rewards if available
        # For solo mining, calculate theoretical earnings
        revenue_gbp = 0
        
        if coin_prices and coin_info["coin"] in coin_prices:
            coin_price = coin_prices[coin_info["coin"]]
            
            # Theoretical calculation for solo mining
            # This is highly probabilistic - actual earnings vary greatly
            if "solopool" in pool_in_use.lower():
                # Solo mining - very low probability
                # Calculate expected value but note it's theoretical
                revenue_gbp = 0  # Solo mining revenue is too variable to estimate
            else:
                # Pool mining - can estimate based on hashrate share
                # This is simplified - real calculation would need pool stats
                revenue_gbp = 0  # Requires pool API data
        
        profit_gbp = revenue_gbp - energy_cost
        roi_percent = ((profit_gbp / energy_cost) * 100) if energy_cost > 0 else 0
        
        return {
            "miner_id": miner_id,
            "miner_name": miner.name,
            "coin": coin_info["coin"],
            "period_hours": hours,
            "avg_hashrate_ghs": round(avg_hashrate, 2),
            "energy_cost_gbp": round(energy_cost, 2),
            "revenue_gbp": round(revenue_gbp, 2),
            "profit_gbp": round(profit_gbp, 2),
            "roi_percent": round(roi_percent, 2),
            "note": "Solo mining revenue is probabilistic and not estimated"
        }
    
    @staticmethod
    async def _calculate_energy_cost(
        miner_id: int,
        db: AsyncSession,
        hours: int,
        telemetry_data: List
    ) -> float:
        """Calculate energy cost in GBP for given period"""
        region = app_config.get("octopus_agile.region", "H")
        
        total_cost_pence = 0
        
        for telem in telemetry_data:
            if not telem.power_watts or telem.power_watts <= 0:
                continue
            
            # Find energy price for this timestamp
            result = await db.execute(
                select(EnergyPrice)
                .where(EnergyPrice.region == region)
                .where(EnergyPrice.valid_from <= telem.timestamp)
                .where(EnergyPrice.valid_to > telem.timestamp)
                .limit(1)
            )
            price = result.scalar_one_or_none()
            
            if price:
                interval_hours = 30 / 3600  # 30 second telemetry interval
                energy_kwh = (telem.power_watts / 1000) * interval_hours
                total_cost_pence += energy_kwh * price.price_pence
        
        return total_cost_pence / 100  # Convert to GBP
    
    @staticmethod
    async def get_price_forecast(
        db: AsyncSession,
        hours_ahead: int = 24
    ) -> List[Dict[str, Any]]:
        """Get energy price forecast for next N hours"""
        region = app_config.get("octopus_agile.region", "H")
        now = datetime.utcnow()
        end_time = now + timedelta(hours=hours_ahead)
        
        result = await db.execute(
            select(EnergyPrice)
            .where(EnergyPrice.region == region)
            .where(EnergyPrice.valid_from >= now)
            .where(EnergyPrice.valid_from < end_time)
            .order_by(EnergyPrice.valid_from)
        )
        prices = result.scalars().all()
        
        return [
            {
                "timestamp": p.valid_from.isoformat(),
                "price_pence": p.price_pence,
                "is_cheap": p.price_pence < 10,  # Below 10p/kWh
                "is_expensive": p.price_pence > 25  # Above 25p/kWh
            }
            for p in prices
        ]
    
    @staticmethod
    async def recommend_schedule(
        miner_id: int,
        db: AsyncSession,
        target_hours: int = 12
    ) -> Dict[str, Any]:
        """
        Recommend optimal mining schedule for next 24 hours
        
        Args:
            miner_id: Miner ID
            db: Database session
            target_hours: Number of hours to mine in 24h period
        
        Returns:
            Dict with recommended schedule
        """
        # Get price forecast
        forecast = await EnergyOptimizationService.get_price_forecast(db, 24)
        
        if not forecast:
            return {"error": "No price forecast available"}
        
        # Sort by price (cheapest first)
        sorted_prices = sorted(forecast, key=lambda x: x["price_pence"])
        
        # Select cheapest slots
        recommended_slots = sorted_prices[:target_hours * 2]  # *2 because 30min slots
        
        # Calculate savings
        avg_expensive = sum(p["price_pence"] for p in sorted_prices[-target_hours * 2:]) / (target_hours * 2)
        avg_cheap = sum(p["price_pence"] for p in recommended_slots) / len(recommended_slots)
        savings_percent = ((avg_expensive - avg_cheap) / avg_expensive) * 100 if avg_expensive > 0 else 0
        
        return {
            "miner_id": miner_id,
            "target_hours": target_hours,
            "recommended_slots": recommended_slots,
            "avg_price_pence": round(avg_cheap, 2),
            "vs_random_avg": round(sum(p["price_pence"] for p in forecast) / len(forecast), 2),
            "savings_percent": round(savings_percent, 2)
        }
    
    @staticmethod
    async def should_mine_now(
        db: AsyncSession,
        price_threshold: float = 15.0
    ) -> Dict[str, Any]:
        """
        Determine if current energy price is favorable for mining
        
        Args:
            db: Database session  
            price_threshold: Price threshold in pence/kWh
        
        Returns:
            Dict with recommendation
        """
        region = app_config.get("octopus_agile.region", "H")
        now = datetime.utcnow()
        
        # Get current price
        result = await db.execute(
            select(EnergyPrice)
            .where(EnergyPrice.region == region)
            .where(EnergyPrice.valid_from <= now)
            .where(EnergyPrice.valid_to > now)
            .limit(1)
        )
        current_price = result.scalar_one_or_none()
        
        if not current_price:
            return {"error": "No current price available"}
        
        # Get next slot
        result = await db.execute(
            select(EnergyPrice)
            .where(EnergyPrice.region == region)
            .where(EnergyPrice.valid_from >= now)
            .order_by(EnergyPrice.valid_from)
            .limit(1)
        )
        next_price = result.scalar_one_or_none()
        
        should_mine = current_price.price_pence <= price_threshold
        
        return {
            "should_mine": should_mine,
            "current_price_pence": current_price.price_pence,
            "threshold_pence": price_threshold,
            "next_price_pence": next_price.price_pence if next_price else None,
            "recommendation": "Mine now" if should_mine else "Wait for cheaper prices",
            "valid_until": current_price.valid_to.isoformat()
        }
