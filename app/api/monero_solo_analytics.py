"""
Monero Solo Mining Analytics API
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta
from typing import Optional

from core.database import (
    get_db, 
    MoneroSoloSettings,
    MoneroSoloEffort,
    MoneroBlock,
    MoneroWalletTransaction,
    MoneroHashrateSnapshot
)
from core.monero_solo import MoneroSoloService

router = APIRouter()


@router.get("/analytics/monero-solo")
async def get_monero_solo_analytics(
    db: AsyncSession = Depends(get_db)
):
    """Get Monero solo mining analytics data"""
    service = MoneroSoloService(db)
    settings = await service.get_or_create_settings()
    
    if not settings.enabled:
        return {
            "enabled": False,
            "message": "Monero solo mining is not enabled"
        }
    
    # Time ranges matching CKPool pattern
    now = datetime.utcnow()
    hashrate_start = now - timedelta(hours=24)  # 24 hours for hashrate
    blocks_start = now - timedelta(days=365)  # 12 months for blocks/effort
    
    # Get current hashrate
    hashrate_data = await service.aggregate_hashrate()
    
    # Format hashrate for display (XMRig adapter returns KH/s)
    total_hashrate_khs = hashrate_data["total_hashrate"]
    if total_hashrate_khs >= 1_000_000:
        hashrate_formatted = f"{total_hashrate_khs / 1_000_000:.2f} GH/s"
    elif total_hashrate_khs >= 1_000:
        hashrate_formatted = f"{total_hashrate_khs / 1_000:.2f} MH/s"
    else:
        hashrate_formatted = f"{total_hashrate_khs:.2f} KH/s"
    
    # Get current effort
    effort_stmt = select(MoneroSoloEffort).order_by(
        MoneroSoloEffort.updated_at.desc()
    ).limit(1)
    result = await db.execute(effort_stmt)
    latest_effort = result.scalar_one_or_none()
    # TODO: Calculate effort_percent from total_hashes / network_difficulty
    current_effort = 0.0  # Stub until network difficulty tracking is implemented
    
    # Count total blocks
    blocks_stmt = select(func.count(MoneroBlock.id))
    result = await db.execute(blocks_stmt)
    blocks_count = result.scalar() or 0
    
    # Get 24h earnings
    period_earnings_stmt = select(func.sum(MoneroWalletTransaction.amount_xmr)).where(
        MoneroWalletTransaction.timestamp >= hashrate_start
    )
    result = await db.execute(period_earnings_stmt)
    period_earnings = result.scalar() or 0.0
    
    # Get all-time earnings
    total_earnings_stmt = select(func.sum(MoneroWalletTransaction.amount_xmr))
    result = await db.execute(total_earnings_stmt)
    total_earnings = result.scalar() or 0.0
    
    # Get hashrate history (24 hours)
    hashrate_stmt = select(MoneroHashrateSnapshot).where(
        MoneroHashrateSnapshot.timestamp >= hashrate_start
    ).order_by(MoneroHashrateSnapshot.timestamp)
    result = await db.execute(hashrate_stmt)
    hashrate_history = result.scalars().all()
    
    # Get blocks for effort history (12 months)
    blocks_effort_stmt = select(MoneroBlock).where(
        MoneroBlock.timestamp >= blocks_start
    ).order_by(MoneroBlock.timestamp)
    result = await db.execute(blocks_effort_stmt)
    effort_blocks = result.scalars().all()
    
    # Get recent blocks (last 50, indefinite retention)
    blocks_stmt = select(MoneroBlock).order_by(
        MoneroBlock.block_height.desc()
    ).limit(50)
    result = await db.execute(blocks_stmt)
    blocks = result.scalars().all()
    
    # Get recent transactions (last 50, indefinite retention)
    transactions_stmt = select(MoneroWalletTransaction).order_by(
        MoneroWalletTransaction.timestamp.desc()
    ).limit(50)
    result = await db.execute(transactions_stmt)
    transactions = result.scalars().all()
    
    return {
        "enabled": True,
        "worker_count": hashrate_data["worker_count"],
        "current_hashrate_formatted": hashrate_formatted,
        "current_effort_percent": float(current_effort),
        "blocks_found": blocks_count,
        "period_earnings_xmr": float(period_earnings),
        "total_earnings_xmr": float(total_earnings),
        "hashrate_history": [
            {
                "timestamp": h.timestamp.isoformat(),
                "hashrate": float(h.total_hashrate),
                "worker_count": h.worker_count
            }
            for h in hashrate_history
        ],
        "effort_history": [
            {
                "timestamp": b.timestamp.isoformat(),
                "effort_percent": float(b.effort_percent),
                "block_height": b.block_height,
                "reward_xmr": float(b.reward_xmr)
            }
            for b in effort_blocks
        ],
        "blocks": [
            {
                "block_height": b.block_height,
                "block_hash": b.block_hash,
                "timestamp": b.timestamp.isoformat(),
                "reward_xmr": float(b.reward_xmr),
                "difficulty": float(b.difficulty)
            }
            for b in blocks
        ],
        "transactions": [
            {
                "tx_hash": t.tx_hash,
                "timestamp": t.timestamp.isoformat(),
                "amount_xmr": float(t.amount_xmr),
                "block_height": t.block_height,
                "tx_type": t.tx_type,
                "is_block_reward": t.is_block_reward
            }
            for t in transactions
        ]
    }
