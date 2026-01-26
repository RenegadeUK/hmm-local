"""
Miner Anomaly Detection System - Phase A: Rules + Robust Statistics

Deterministic baseline tracking and rule-based anomaly detection.
ML (Isolation Forest) in Phase B.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
import statistics

from core.database import (
    AsyncSessionLocal, Miner, Telemetry, MinerBaseline, HealthEvent
)

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Baseline windows
BASELINE_WINDOW_24H = 24  # hours
BASELINE_WINDOW_7D = 168  # hours

# Anomaly thresholds (percentages)
THRESHOLD_HASHRATE_DROP = 15  # %
THRESHOLD_EFFICIENCY_DRIFT = 20  # % increase in W/TH
THRESHOLD_TEMP_MARGIN = 10  # degrees C above baseline
THRESHOLD_REJECT_RATE = 5  # % reject rate
THRESHOLD_POWER_SPIKE = 15  # % increase without hashrate increase

# Health score weights
WEIGHT_HASHRATE = 30
WEIGHT_EFFICIENCY = 25
WEIGHT_TEMPERATURE = 20
WEIGHT_REJECTS = 15
WEIGHT_POWER = 10

# Minimum data requirements
MIN_SAMPLES_FOR_BASELINE = 60  # Need at least 1 hour of data


# ============================================================================
# ROBUST STATISTICS
# ============================================================================

def calculate_median_mad(values: List[float]) -> Tuple[float, float]:
    """
    Calculate median and MAD (Median Absolute Deviation).
    More robust to outliers than mean/std.
    
    Returns:
        (median, mad)
    """
    if not values:
        return (0.0, 0.0)
    
    median = statistics.median(values)
    absolute_deviations = [abs(x - median) for x in values]
    mad = statistics.median(absolute_deviations)
    
    return (median, mad)


def is_anomalous(current_value: float, median: float, mad: float, threshold_factor: float = 3.0) -> bool:
    """
    Check if value is anomalous using MAD-based threshold.
    
    Args:
        current_value: Current metric value
        median: Baseline median
        mad: Baseline MAD
        threshold_factor: How many MADs away = anomaly (default 3.0)
    
    Returns:
        True if anomalous
    """
    if mad == 0:
        # No variance in baseline - any deviation is suspicious
        return abs(current_value - median) > (median * 0.01)  # 1% tolerance
    
    deviation = abs(current_value - median)
    return deviation > (threshold_factor * mad)


# ============================================================================
# BASELINE CALCULATION
# ============================================================================

async def compute_baselines_for_miner(
    db: AsyncSession,
    miner_id: int,
    window_hours: int = BASELINE_WINDOW_24H
) -> Dict[str, Tuple[float, float]]:
    """
    Compute robust baselines for a miner using median + MAD.
    
    Returns:
        Dict[metric_name, (median, mad)]
    """
    logger.info(f"Computing {window_hours}h baselines for miner {miner_id}")
    
    # Get miner to check type
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    if not miner:
        logger.warning(f"Miner {miner_id} not found")
        return {}
    
    # Get recent telemetry
    cutoff = datetime.utcnow() - timedelta(hours=window_hours)
    result = await db.execute(
        select(Telemetry)
        .where(
            and_(
                Telemetry.miner_id == miner_id,
                Telemetry.timestamp >= cutoff,
                Telemetry.hashrate.isnot(None),
                Telemetry.hashrate > 0
            )
        )
        .order_by(Telemetry.timestamp.desc())
    )
    telemetry_records = result.scalars().all()
    
    if len(telemetry_records) < MIN_SAMPLES_FOR_BASELINE:
        logger.warning(f"Insufficient data for miner {miner_id}: {len(telemetry_records)} samples")
        return {}
    
    # Extract metrics per mode (if mode tracking exists)
    metrics_by_mode: Dict[Optional[str], Dict[str, List[float]]] = {}
    
    for record in telemetry_records:
        mode = record.mode  # Can be None
        
        if mode not in metrics_by_mode:
            metrics_by_mode[mode] = {
                "hashrate_mean": [],
                "power_mean": [],
                "w_per_th": [],
                "temp_mean": [],
                "reject_rate": []
            }
        
        # Hashrate
        if record.hashrate and record.hashrate > 0:
            # Convert to TH/s for consistency
            hashrate_ths = _convert_to_ths(record.hashrate, record.hashrate_unit or "GH/s")
            metrics_by_mode[mode]["hashrate_mean"].append(hashrate_ths)
            
            # W/TH (only if we have power)
            if record.power_watts and record.power_watts > 0:
                w_per_th = record.power_watts / hashrate_ths
                metrics_by_mode[mode]["w_per_th"].append(w_per_th)
                metrics_by_mode[mode]["power_mean"].append(record.power_watts)
        
        # Temperature
        if record.temperature:
            metrics_by_mode[mode]["temp_mean"].append(record.temperature)
        
        # Reject rate
        if record.shares_accepted is not None and record.shares_rejected is not None:
            total_shares = record.shares_accepted + record.shares_rejected
            if total_shares > 0:
                reject_rate = (record.shares_rejected / total_shares) * 100
                metrics_by_mode[mode]["reject_rate"].append(reject_rate)
    
    # Calculate baselines for each mode
    baselines = {}
    
    for mode, metrics in metrics_by_mode.items():
        mode_key = mode if mode else "None"
        
        for metric_name, values in metrics.items():
            if len(values) >= MIN_SAMPLES_FOR_BASELINE:
                median, mad = calculate_median_mad(values)
                key = f"{mode_key}_{metric_name}"
                baselines[key] = (median, mad)
                
                logger.info(
                    f"Miner {miner_id} [{mode_key}] {metric_name}: "
                    f"median={median:.2f}, mad={mad:.2f}, samples={len(values)}"
                )
    
    return baselines


async def update_baselines_for_all_miners(db: AsyncSession):
    """Update baselines for all enabled miners"""
    logger.info("Updating baselines for all miners")
    
    result = await db.execute(
        select(Miner).where(Miner.enabled == True)
    )
    miners = result.scalars().all()
    
    for miner in miners:
        # Compute 24h baselines
        baselines_24h = await compute_baselines_for_miner(db, miner.id, BASELINE_WINDOW_24H)
        
        # Store in database
        for key, (median, mad) in baselines_24h.items():
            parts = key.rsplit("_", 1)
            if len(parts) == 2:
                mode_str, metric_name = parts
                mode = None if mode_str == "None" else mode_str
                
                # Upsert baseline
                result = await db.execute(
                    select(MinerBaseline)
                    .where(
                        and_(
                            MinerBaseline.miner_id == miner.id,
                            MinerBaseline.mode == mode,
                            MinerBaseline.metric_name == metric_name,
                            MinerBaseline.window_hours == BASELINE_WINDOW_24H
                        )
                    )
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    existing.median_value = median
                    existing.mad_value = mad
                    existing.sample_count = len(baselines_24h)
                    existing.updated_at = datetime.utcnow()
                else:
                    baseline = MinerBaseline(
                        miner_id=miner.id,
                        mode=mode,
                        metric_name=metric_name,
                        median_value=median,
                        mad_value=mad,
                        sample_count=len(baselines_24h),
                        window_hours=BASELINE_WINDOW_24H
                    )
                    db.add(baseline)
    
    await db.commit()
    logger.info("Baseline update complete")


# ============================================================================
# RULE-BASED ANOMALY DETECTION
# ============================================================================

async def check_miner_health(db: AsyncSession, miner_id: int) -> Optional[Dict]:
    """
    Check miner health using deterministic rules.
    
    Returns:
        {
            "health_score": 0-100,
            "reasons": {"REASON_CODE": {"current": x, "expected": "y ± z"}, ...},
            "mode": "current_mode"
        }
    """
    # Get miner
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    if not miner or not miner.enabled:
        return None
    
    # Get latest telemetry (last 5 minutes)
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    result = await db.execute(
        select(Telemetry)
        .where(
            and_(
                Telemetry.miner_id == miner_id,
                Telemetry.timestamp >= cutoff
            )
        )
        .order_by(Telemetry.timestamp.desc())
    )
    recent_telemetry = result.scalars().all()
    
    if not recent_telemetry:
        logger.warning(f"No recent telemetry for miner {miner_id}")
        return {
            "health_score": 0,
            "reasons": {"SENSOR_MISSING": {"message": "No telemetry in last 5 minutes"}},
            "mode": None
        }
    
    # Get current mode
    current_mode = recent_telemetry[0].mode
    mode_key = current_mode if current_mode else "None"
    
    # Get baselines for this mode
    result = await db.execute(
        select(MinerBaseline)
        .where(
            and_(
                MinerBaseline.miner_id == miner_id,
                MinerBaseline.mode == current_mode,
                MinerBaseline.window_hours == BASELINE_WINDOW_24H
            )
        )
    )
    baselines_records = result.scalars().all()
    
    baselines = {
        b.metric_name: (b.median_value, b.mad_value)
        for b in baselines_records
    }
    
    if not baselines:
        logger.warning(f"No baselines for miner {miner_id} mode {mode_key}")
        return {
            "health_score": 50,
            "reasons": {"INSUFFICIENT_DATA": {"message": "No baseline data available"}},
            "mode": current_mode
        }
    
    # Calculate current metrics
    hashrates = [_convert_to_ths(t.hashrate, t.hashrate_unit or "GH/s") 
                 for t in recent_telemetry if t.hashrate and t.hashrate > 0]
    powers = [t.power_watts for t in recent_telemetry if t.power_watts and t.power_watts > 0]
    temps = [t.temperature for t in recent_telemetry if t.temperature]
    
    current_hashrate = statistics.mean(hashrates) if hashrates else None
    current_power = statistics.mean(powers) if powers else None
    current_temp = statistics.mean(temps) if temps else None
    current_w_per_th = (current_power / current_hashrate) if (current_power and current_hashrate and current_hashrate > 0) else None
    
    # Calculate reject rate
    total_accepted = sum(t.shares_accepted or 0 for t in recent_telemetry)
    total_rejected = sum(t.shares_rejected or 0 for t in recent_telemetry)
    total_shares = total_accepted + total_rejected
    current_reject_rate = (total_rejected / total_shares * 100) if total_shares > 0 else 0
    
    # Run checks
    reasons = {}
    health_score = 100.0
    
    # Check 1: Hashrate drop
    if current_hashrate and "hashrate_mean" in baselines:
        median_hr, mad_hr = baselines["hashrate_mean"]
        drop_pct = ((median_hr - current_hashrate) / median_hr) * 100 if median_hr > 0 else 0
        
        if drop_pct > THRESHOLD_HASHRATE_DROP:
            reasons["HASHRATE_DROP"] = {
                "current": round(current_hashrate, 2),
                "expected": f"{median_hr:.2f} ± {mad_hr:.2f} TH/s",
                "drop_pct": round(drop_pct, 1)
            }
            health_score -= WEIGHT_HASHRATE * (drop_pct / 100)
    
    # Check 2: Efficiency drift
    if current_w_per_th and "w_per_th" in baselines:
        median_eff, mad_eff = baselines["w_per_th"]
        drift_pct = ((current_w_per_th - median_eff) / median_eff) * 100 if median_eff > 0 else 0
        
        if drift_pct > THRESHOLD_EFFICIENCY_DRIFT:
            reasons["EFFICIENCY_DRIFT"] = {
                "current": round(current_w_per_th, 1),
                "expected": f"{median_eff:.1f} ± {mad_eff:.1f} W/TH",
                "increase_pct": round(drift_pct, 1)
            }
            health_score -= WEIGHT_EFFICIENCY * (drift_pct / 100)
    
    # Check 3: Temperature
    if current_temp and "temp_mean" in baselines:
        median_temp, mad_temp = baselines["temp_mean"]
        
        if current_temp > (median_temp + THRESHOLD_TEMP_MARGIN):
            reasons["TEMP_HIGH"] = {
                "current": round(current_temp, 1),
                "expected": f"{median_temp:.1f} ± {mad_temp:.1f} °C",
                "over_baseline": round(current_temp - median_temp, 1)
            }
            health_score -= WEIGHT_TEMPERATURE * ((current_temp - median_temp) / 100)
    
    # Check 4: Reject rate
    if current_reject_rate > THRESHOLD_REJECT_RATE:
        reasons["REJECT_RATE_SPIKE"] = {
            "current_pct": round(current_reject_rate, 2),
            "threshold_pct": THRESHOLD_REJECT_RATE,
            "total_shares": total_shares
        }
        health_score -= WEIGHT_REJECTS * (current_reject_rate / 100)
    
    # Check 5: Power spike without hashrate increase
    if current_power and current_hashrate and "power_mean" in baselines and "hashrate_mean" in baselines:
        median_power, _ = baselines["power_mean"]
        median_hr, _ = baselines["hashrate_mean"]
        
        power_increase_pct = ((current_power - median_power) / median_power) * 100 if median_power > 0 else 0
        hashrate_change_pct = ((current_hashrate - median_hr) / median_hr) * 100 if median_hr > 0 else 0
        
        if power_increase_pct > THRESHOLD_POWER_SPIKE and hashrate_change_pct < 5:
            reasons["POWER_SPIKE"] = {
                "current_watts": round(current_power, 1),
                "expected_watts": round(median_power, 1),
                "increase_pct": round(power_increase_pct, 1),
                "hashrate_change_pct": round(hashrate_change_pct, 1)
            }
            health_score -= WEIGHT_POWER * (power_increase_pct / 100)
    
    # Clamp health score
    health_score = max(0, min(100, health_score))
    
    return {
        "health_score": round(health_score, 1),
        "reasons": reasons,
        "mode": current_mode
    }


async def check_all_miners_health(db: AsyncSession):
    """Check health for all enabled miners and store events"""
    logger.info("Checking health for all miners")
    
    result = await db.execute(
        select(Miner).where(Miner.enabled == True)
    )
    miners = result.scalars().all()
    
    for miner in miners:
        health_data = await check_miner_health(db, miner.id)
        
        if health_data:
            # Store health event
            event = HealthEvent(
                miner_id=miner.id,
                health_score=health_data["health_score"],
                reasons=health_data["reasons"],
                mode=health_data["mode"]
            )
            db.add(event)
            
            if health_data["reasons"]:
                logger.warning(
                    f"Miner {miner.name} (ID {miner.id}) health: {health_data['health_score']}/100 - "
                    f"Issues: {list(health_data['reasons'].keys())}"
                )
    
    await db.commit()
    logger.info("Health check complete")


# ============================================================================
# UTILITIES
# ============================================================================

def _convert_to_ths(hashrate: float, unit: str) -> float:
    """Convert hashrate to TH/s"""
    unit = unit.upper()
    if "KH" in unit:
        return hashrate / 1_000_000_000
    elif "MH" in unit:
        return hashrate / 1_000_000
    elif "GH" in unit:
        return hashrate / 1_000
    elif "TH" in unit:
        return hashrate
    else:
        return hashrate / 1_000  # Assume GH/s if unknown
