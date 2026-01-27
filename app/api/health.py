"""
API endpoints for miner anomaly detection and health monitoring
"""
import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from typing import List, Optional

from core.database import AsyncSessionLocal, Miner, HealthEvent, MinerBaseline, MinerHealthCurrent

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


@router.get("/all")
async def get_all_miners_health(db: AsyncSession = Depends(get_db)):
    """Get latest health status for all miners"""
    # Get all miners
    result = await db.execute(
        select(Miner).where(Miner.enabled == True)
    )
    miners = result.scalars().all()
    
    health_data = []
    
    for miner in miners:
        # Get latest health event
        result = await db.execute(
            select(HealthEvent)
            .where(HealthEvent.miner_id == miner.id)
            .order_by(desc(HealthEvent.timestamp))
            .limit(1)
        )
        event = result.scalar_one_or_none()
        
        if event:
            health_data.append({
                "miner_id": miner.id,
                "miner_name": miner.name,
                "miner_type": miner.miner_type,
                "timestamp": event.timestamp.isoformat(),
                "health_score": event.health_score,
                "reasons": event.reasons,
                "anomaly_score": event.anomaly_score,
                "mode": event.mode,
                "has_issues": len(event.reasons) > 0
            })
    
    return {
        "total_miners": len(miners),
        "monitored_miners": len(health_data),
        "miners": health_data
    }


@router.get("/{miner_id}")
async def get_miner_health(
    miner_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get latest health status for a miner with full details"""
    # Get miner info
    miner_result = await db.execute(
        select(Miner).where(Miner.id == miner_id)
    )
    miner = miner_result.scalar_one_or_none()
    
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")
    
    # Get latest health event
    result = await db.execute(
        select(HealthEvent)
        .where(HealthEvent.miner_id == miner_id)
        .order_by(desc(HealthEvent.timestamp))
        .limit(1)
    )
    event = result.scalar_one_or_none()
    
    if not event:
        raise HTTPException(status_code=404, detail="No health data available")
    
    # Get suggested actions from health event if available
    from core.anomaly_detection import SUGGESTED_ACTIONS
    suggested_actions = []
    if event.reasons:
        reason_codes = []
        for reason in event.reasons:
            if isinstance(reason, dict) and 'code' in reason:
                reason_codes.append(reason['code'])
        
        for code in reason_codes:
            if code in SUGGESTED_ACTIONS:
                suggested_actions.extend(SUGGESTED_ACTIONS[code])
    
    return {
        "miner_id": miner.id,
        "miner_name": miner.name,
        "miner_type": miner.miner_type,
        "health_score": event.health_score,
        "status": event.status if hasattr(event, 'status') else _get_status_from_score(event.health_score),
        "anomaly_score": event.anomaly_score,
        "reasons": event.reasons or [],
        "suggested_actions": list(set(suggested_actions)),  # dedupe
        "mode": event.mode,
        "last_check": event.timestamp.isoformat()
    }


def _get_status_from_score(score: int) -> str:
    """Derive status from health score"""
    if score >= 80:
        return "healthy"
    elif score >= 60:
        return "warning"
    else:
        return "critical"


@router.get("/{miner_id}/history")
async def get_miner_health_history(
    miner_id: int,
    hours: int = 24,
    db: AsyncSession = Depends(get_db)
):
    """Get health history for a miner"""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    result = await db.execute(
        select(HealthEvent)
        .where(
            and_(
                HealthEvent.miner_id == miner_id,
                HealthEvent.timestamp >= cutoff
            )
        )
        .order_by(HealthEvent.timestamp)
    )
    events = result.scalars().all()
    
    return [
        {
            "timestamp": event.timestamp.isoformat(),
            "health_score": event.health_score,
            "anomaly_score": event.anomaly_score,
            "status": event.status if hasattr(event, 'status') else _get_status_from_score(event.health_score)
        }
        for event in events
    ]
    result = await db.execute(
        select(HealthEvent)
        .where(
            and_(
                HealthEvent.miner_id == miner_id,
                HealthEvent.timestamp >= cutoff
            )
        )
        .order_by(HealthEvent.timestamp.desc())
    )
    events = result.scalars().all()
    
    return {
        "miner_id": miner_id,
        "hours": hours,
        "event_count": len(events),
        "events": [
            {
                "timestamp": e.timestamp.isoformat(),
                "health_score": e.health_score,
                "reasons": e.reasons,
                "anomaly_score": e.anomaly_score,
                "mode": e.mode
            }
            for e in events
        ]
    }


@router.get("/baselines/{miner_id}")
async def get_miner_baselines(
    miner_id: int,
    mode: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get performance baselines for a miner"""
    query = select(MinerBaseline).where(MinerBaseline.miner_id == miner_id)
    
    if mode is not None:
        query = query.where(MinerBaseline.mode == mode)
    
    result = await db.execute(query)
    baselines = result.scalars().all()
    
    if not baselines:
        raise HTTPException(status_code=404, detail="No baseline data available")
    
    return {
        "miner_id": miner_id,
        "mode": mode,
        "baselines": [
            {
                "metric_name": b.metric_name,
                "mode": b.mode,
                "median_value": b.median_value,
                "mad_value": b.mad_value,
                "sample_count": b.sample_count,
                "window_hours": b.window_hours,
                "updated_at": b.updated_at.isoformat()
            }
            for b in baselines
        ]
    }


@router.post("/baselines/update")
async def trigger_baseline_update(db: AsyncSession = Depends(get_db)):
    """Manually trigger baseline recalculation for all miners"""
    from core.anomaly_detection import update_baselines_for_all_miners
    
    try:
        await update_baselines_for_all_miners(db)
        return {"status": "success", "message": "Baselines updated"}
    except Exception as e:
        logger.error(f"Failed to update baselines: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check")
async def trigger_health_check(db: AsyncSession = Depends(get_db)):
    """Manually trigger health check for all miners"""
    from core.anomaly_detection import check_all_miners_health
    
    try:
        await check_all_miners_health(db)
        return {"status": "success", "message": "Health check completed"}
    except Exception as e:
        logger.error(f"Failed to check health: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ml/train")
async def trigger_ml_training(db: AsyncSession = Depends(get_db)):
    """Manually trigger ML model training for all miners"""
    from core.ml_anomaly import train_all_models
    
    try:
        await train_all_models(db)
        return {"status": "success", "message": "ML model training completed"}
    except Exception as e:
        logger.error(f"Failed to train ML models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ml/models")
async def list_ml_models():
    """List all trained ML models"""
    from core.ml_anomaly import MODELS_DIR
    import pickle
    
    models = []
    
    if not MODELS_DIR.exists():
        return {"models": []}
    
    for model_file in MODELS_DIR.glob("*.pkl"):
        meta_file = model_file.with_suffix(".meta")
        
        if meta_file.exists():
            try:
                with open(meta_file, "rb") as f:
                    metadata = pickle.load(f)
                
                models.append({
                    "name": model_file.stem,
                    "type": "per-miner" if model_file.stem.startswith("miner_") else "type",
                    "trained_at": metadata.get("trained_at"),
                    "sample_count": metadata.get("sample_count"),
                    "window_days": metadata.get("window_days")
                })
            except Exception as e:
                logger.error(f"Failed to read metadata for {model_file}: {e}")
    
    return {"models": models, "total": len(models)}

# ============================================================================
# PHASE C: CANONICAL MINER HEALTH ENDPOINTS (Output Layer)
# ============================================================================

@router.get("/miners/{miner_id}")
async def get_current_miner_health(
    miner_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get current canonical MinerHealth for a specific miner"""
    result = await db.execute(
        select(MinerHealthCurrent).where(MinerHealthCurrent.miner_id == miner_id)
    )
    current = result.scalar_one_or_none()
    
    if not current:
        raise HTTPException(status_code=404, detail="No health data available for this miner")
    
    # Return canonical MinerHealth object
    return {
        "miner_id": current.miner_id,
        "timestamp": current.timestamp.isoformat(),
        "health_score": current.health_score,
        "status": current.status,
        "anomaly_score": current.anomaly_score,
        "reasons": current.reasons,  # Array of structured reason objects
        "suggested_actions": current.suggested_actions,  # Array of action strings
        "mode": current.mode
    }


@router.get("/miners")
async def get_all_miners_health(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get current canonical MinerHealth for all miners
    
    Query parameters:
    - status: Filter by status ("healthy", "warning", "critical")
    """
    query = select(MinerHealthCurrent)
    
    # Apply status filter if provided
    if status:
        if status not in ["healthy", "warning", "critical"]:
            raise HTTPException(status_code=400, detail="Invalid status. Must be: healthy, warning, or critical")
        query = query.where(MinerHealthCurrent.status == status)
    
    result = await db.execute(query.order_by(MinerHealthCurrent.health_score))  # Worst first
    miners = result.scalars().all()
    
    # Get miner names for enrichment
    miner_ids = [m.miner_id for m in miners]
    result = await db.execute(select(Miner).where(Miner.id.in_(miner_ids)))
    miner_map = {m.id: m.name for m in result.scalars().all()}
    
    # Build canonical response
    return {
        "miners": [
            {
                "miner_id": m.miner_id,
                "miner_name": miner_map.get(m.miner_id, "Unknown"),
                "timestamp": m.timestamp.isoformat(),
                "health_score": m.health_score,
                "status": m.status,
                "anomaly_score": m.anomaly_score,
                "reasons": m.reasons,
                "suggested_actions": m.suggested_actions,
                "mode": m.mode,
                "updated_at": m.updated_at.isoformat()
            }
            for m in miners
        ],
        "total": len(miners),
        "filtered_by_status": status
    }