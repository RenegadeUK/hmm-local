"""
Leaderboard API endpoints for high difficulty shares and coin hunter
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime

from core.database import get_db, BlockFound
from core.high_diff_tracker import get_leaderboard

router = APIRouter()


class LeaderboardEntry(BaseModel):
    """Single leaderboard entry"""
    rank: int
    miner_id: int
    miner_name: str
    miner_type: str
    coin: str
    pool_name: str
    difficulty: float
    difficulty_formatted: str  # e.g., "1.2M"
    network_difficulty: Optional[float]
    was_block_solve: bool
    percent_of_block: Optional[float]  # (share_diff / network_diff) * 100
    hashrate: Optional[float]
    hashrate_unit: str
    miner_mode: Optional[str]
    timestamp: datetime
    days_ago: int  # How many days ago this happened


class LeaderboardResponse(BaseModel):
    """Leaderboard API response"""
    entries: List[LeaderboardEntry]
    total_count: int
    filter_coin: Optional[str]
    filter_days: int


def format_difficulty(diff: float) -> str:
    """Format large difficulty numbers (e.g., 1234567 → 1.2M)"""
    if diff >= 1_000_000_000:
        return f"{diff/1_000_000_000:.1f}B"
    elif diff >= 1_000_000:
        return f"{diff/1_000_000:.1f}M"
    elif diff >= 1_000:
        return f"{diff/1_000:.1f}K"
    else:
        return f"{diff:.0f}"


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_high_diff_leaderboard(
    days: int = Query(90, ge=1, le=365, description="Number of days to look back"),
    coin: Optional[str] = Query(None, description="Filter by coin (BTC/BCH/DGB)"),
    limit: int = Query(10, ge=1, le=50, description="Number of entries to return"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get high difficulty share leaderboard
    
    - **days**: Number of days to look back (default 90)
    - **coin**: Filter by coin (BTC/BCH/DGB) or None for all
    - **limit**: Number of entries to return (default 10)
    """
    shares = await get_leaderboard(db, days=days, coin=coin, limit=limit)
    
    entries = []
    for rank, share in enumerate(shares, start=1):
        # Calculate days ago
        days_ago = (datetime.utcnow() - share.timestamp).days
        
        # Calculate percent of block if network diff available
        percent_of_block = None
        if share.network_difficulty and share.network_difficulty > 0:
            percent_of_block = (share.difficulty / share.network_difficulty) * 100
        
        entries.append(
            LeaderboardEntry(
                rank=rank,
                miner_id=share.miner_id,
                miner_name=share.miner_name,
                miner_type=share.miner_type,
                coin=share.coin,
                pool_name=share.pool_name,
                difficulty=share.difficulty,
                difficulty_formatted=format_difficulty(share.difficulty),
                network_difficulty=share.network_difficulty,
                was_block_solve=share.was_block_solve,
                percent_of_block=percent_of_block,
                hashrate=share.hashrate,
                hashrate_unit=share.hashrate_unit,
                miner_mode=share.miner_mode,
                timestamp=share.timestamp,
                days_ago=days_ago
            )
        )
    
    return LeaderboardResponse(
        entries=entries,
        total_count=len(entries),
        filter_coin=coin,
        filter_days=days
    )


class CoinHunterEntry(BaseModel):
    """Coin Hunter leaderboard entry"""
    rank: int
    miner_id: int
    miner_name: str
    miner_type: str
    btc_blocks: int
    bch_blocks: int
    dgb_blocks: int
    total_blocks: int
    total_score: int  # Weighted score: BTC=100, BCH=10, DGB=1


class CoinHunterResponse(BaseModel):
    """Coin Hunter leaderboard response"""
    entries: List[CoinHunterEntry]
    total_miners: int
    scoring: dict  # {"BTC": 100, "BCH": 10, "DGB": 1}


@router.get("/coin-hunter", response_model=CoinHunterResponse)
async def get_coin_hunter_leaderboard(
    db: AsyncSession = Depends(get_db)
):
    """
    Get Coin Hunter leaderboard - all-time blocks found with weighted scoring
    
    Scoring:
    - BTC block = 100 points
    - BCH block = 10 points
    - DGB block = 1 point
    """
    # Aggregate blocks by miner and coin
    query = select(
        BlockFound.miner_id,
        BlockFound.miner_name,
        BlockFound.miner_type,
        BlockFound.coin,
        func.count(BlockFound.id).label('block_count')
    ).group_by(
        BlockFound.miner_id,
        BlockFound.miner_name,
        BlockFound.miner_type,
        BlockFound.coin
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    # Build miner stats dictionary
    miner_stats = {}
    for row in rows:
        miner_id = row.miner_id
        if miner_id not in miner_stats:
            miner_stats[miner_id] = {
                'miner_name': row.miner_name,
                'miner_type': row.miner_type,
                'BTC': 0,
                'BCH': 0,
                'DGB': 0
            }
        miner_stats[miner_id][row.coin] = row.block_count
    
    # Calculate scores and rankings
    SCORING = {'BTC': 100, 'BCH': 10, 'DGB': 1}
    
    entries = []
    for miner_id, stats in miner_stats.items():
        btc = stats['BTC']
        bch = stats['BCH']
        dgb = stats['DGB']
        total_blocks = btc + bch + dgb
        total_score = (btc * SCORING['BTC']) + (bch * SCORING['BCH']) + (dgb * SCORING['DGB'])
        
        entries.append({
            'miner_id': miner_id,
            'miner_name': stats['miner_name'],
            'miner_type': stats['miner_type'],
            'btc_blocks': btc,
            'bch_blocks': bch,
            'dgb_blocks': dgb,
            'total_blocks': total_blocks,
            'total_score': total_score
        })
    
    # Sort by score descending
    entries.sort(key=lambda x: x['total_score'], reverse=True)
    
    # Add rankings
    ranked_entries = []
    for rank, entry in enumerate(entries, start=1):
        ranked_entries.append(
            CoinHunterEntry(
                rank=rank,
                miner_id=entry['miner_id'],
                miner_name=entry['miner_name'],
                miner_type=entry['miner_type'],
                btc_blocks=entry['btc_blocks'],
                bch_blocks=entry['bch_blocks'],
                dgb_blocks=entry['dgb_blocks'],
                total_blocks=entry['total_blocks'],
                total_score=entry['total_score']
            )
        )
    
    return CoinHunterResponse(
        entries=ranked_entries,
        total_miners=len(ranked_entries),
        scoring=SCORING
    )
