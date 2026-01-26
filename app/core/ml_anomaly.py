"""
Miner Anomaly Detection System - Phase B: Isolation Forest ML

Hybrid approach:
- Per-type models for immediate use (day 0)
- Per-miner models for higher accuracy (after sufficient data)
- Fallback logic: per-miner → type → skip
"""
import logging
import pickle
import joblib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
import numpy as np

try:
    from sklearn.ensemble import IsolationForest
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logging.warning("scikit-learn not installed, ML anomaly detection disabled")

from core.database import Miner, Telemetry, MinerBaseline
from core.config import settings

logger = logging.getLogger(__name__)

# Model storage paths
MODELS_DIR = Path(settings.CONFIG_DIR) / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Training thresholds
MIN_SAMPLES_TYPE_MODEL = 5000  # Minimum samples to train type model
MIN_SAMPLES_PER_MINER = 5000  # Minimum samples for per-miner model
MIN_SAMPLES_PER_MODE = 1000  # Minimum samples per mode
MIN_DAYS_PER_MINER = 7  # Minimum days of history for per-miner model

# Isolation Forest hyperparameters
CONTAMINATION = 0.05  # Expected % of outliers (5%)
N_ESTIMATORS = 100
RANDOM_STATE = 42

# Retraining triggers
BASELINE_SHIFT_THRESHOLD = 0.15  # 15% shift triggers retrain
FALSE_POSITIVE_THRESHOLD = 0.20  # 20% FP rate triggers retrain


def _get_type_model_path(miner_type: str) -> Path:
    """Get path for type-level model"""
    return MODELS_DIR / f"{miner_type}.pkl"


def _get_miner_model_path(miner_id: int) -> Path:
    """Get path for per-miner model"""
    return MODELS_DIR / f"miner_{miner_id}.pkl"


def _get_metadata_path(model_path: Path) -> Path:
    """Get path for model metadata"""
    return model_path.with_suffix(".meta")


async def _extract_features(telemetry_records: List[Telemetry]) -> np.ndarray:
    """
    Extract feature matrix from telemetry records.
    
    Features (normalized per-mode):
    - hashrate (TH/s)
    - power (W)
    - w_per_th (efficiency)
    - temperature (C)
    - reject_rate (%)
    """
    if not telemetry_records:
        return np.array([])
    
    features = []
    
    for record in telemetry_records:
        # Convert hashrate to TH/s
        hashrate_ths = _convert_to_ths(record.hashrate, record.hashrate_unit or "GH/s")
        
        # Calculate efficiency
        w_per_th = (record.power_watts / hashrate_ths) if (record.power_watts and hashrate_ths > 0) else None
        
        # Calculate reject rate
        total_shares = (record.shares_accepted or 0) + (record.shares_rejected or 0)
        reject_rate = ((record.shares_rejected or 0) / total_shares * 100) if total_shares > 0 else 0
        
        # Only include records with complete data
        if hashrate_ths and record.power_watts and w_per_th and record.temperature:
            features.append([
                hashrate_ths,
                record.power_watts,
                w_per_th,
                record.temperature,
                reject_rate
            ])
    
    return np.array(features)


async def train_type_model(
    db: AsyncSession,
    miner_type: str,
    window_days: int = 30
) -> Optional[Dict]:
    """
    Train Isolation Forest model for a miner type.
    
    Returns:
        Model metadata dict or None if insufficient data
    """
    if not SKLEARN_AVAILABLE:
        logger.warning("scikit-learn not available, skipping ML training")
        return None
    
    logger.info(f"Training type model for {miner_type}")
    
    # Get all miners of this type
    result = await db.execute(
        select(Miner).where(
            and_(
                Miner.miner_type == miner_type,
                Miner.enabled == True
            )
        )
    )
    miners = result.scalars().all()
    
    if not miners:
        logger.warning(f"No miners of type {miner_type}")
        return None
    
    # Get telemetry from all miners of this type
    miner_ids = [m.id for m in miners]
    cutoff = datetime.utcnow() - timedelta(days=window_days)
    
    result = await db.execute(
        select(Telemetry)
        .where(
            and_(
                Telemetry.miner_id.in_(miner_ids),
                Telemetry.timestamp >= cutoff,
                Telemetry.hashrate.isnot(None),
                Telemetry.hashrate > 0
            )
        )
    )
    telemetry_records = result.scalars().all()
    
    if len(telemetry_records) < MIN_SAMPLES_TYPE_MODEL:
        logger.warning(
            f"Insufficient data for {miner_type}: {len(telemetry_records)} samples "
            f"(need {MIN_SAMPLES_TYPE_MODEL})"
        )
        return None
    
    # Extract features
    X = await _extract_features(telemetry_records)
    
    if len(X) < MIN_SAMPLES_TYPE_MODEL:
        logger.warning(f"Insufficient complete records for {miner_type}: {len(X)}")
        return None
    
    # Train Isolation Forest
    model = IsolationForest(
        contamination=CONTAMINATION,
        n_estimators=N_ESTIMATORS,
        random_state=RANDOM_STATE,
        n_jobs=-1
    )
    
    model.fit(X)
    
    # Save model
    model_path = _get_type_model_path(miner_type)
    joblib.dump(model, model_path)
    
    # Save metadata
    metadata = {
        "miner_type": miner_type,
        "trained_at": datetime.utcnow().isoformat(),
        "sample_count": len(X),
        "window_days": window_days,
        "contamination": CONTAMINATION,
        "n_estimators": N_ESTIMATORS,
        "feature_names": ["hashrate_ths", "power_watts", "w_per_th", "temp", "reject_rate"]
    }
    
    meta_path = _get_metadata_path(model_path)
    with open(meta_path, "wb") as f:
        pickle.dump(metadata, f)
    
    logger.info(
        f"✅ Trained {miner_type} model: {len(X)} samples from {len(miner_ids)} miners"
    )
    
    return metadata


async def train_miner_model(
    db: AsyncSession,
    miner_id: int,
    window_days: int = 30
) -> Optional[Dict]:
    """
    Train Isolation Forest model for a specific miner.
    
    Returns:
        Model metadata dict or None if insufficient data
    """
    if not SKLEARN_AVAILABLE:
        return None
    
    logger.info(f"Training per-miner model for miner {miner_id}")
    
    # Get miner
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    if not miner:
        logger.warning(f"Miner {miner_id} not found")
        return None
    
    # Check age threshold
    miner_age_days = (datetime.utcnow() - miner.created_at).days
    if miner_age_days < MIN_DAYS_PER_MINER:
        logger.info(
            f"Miner {miner_id} too young: {miner_age_days} days "
            f"(need {MIN_DAYS_PER_MINER})"
        )
        return None
    
    # Get telemetry
    cutoff = datetime.utcnow() - timedelta(days=window_days)
    
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
    )
    telemetry_records = result.scalars().all()
    
    if len(telemetry_records) < MIN_SAMPLES_PER_MINER:
        logger.info(
            f"Insufficient data for miner {miner_id}: {len(telemetry_records)} samples "
            f"(need {MIN_SAMPLES_PER_MINER})"
        )
        return None
    
    # Check mode coverage (if miner has modes)
    modes = set(r.mode for r in telemetry_records if r.mode)
    if modes:
        mode_counts = {
            mode: sum(1 for r in telemetry_records if r.mode == mode)
            for mode in modes
        }
        
        insufficient_modes = [
            mode for mode, count in mode_counts.items()
            if count < MIN_SAMPLES_PER_MODE
        ]
        
        if insufficient_modes:
            logger.info(
                f"Miner {miner_id} has insufficient samples in modes: {insufficient_modes}"
            )
            return None
    
    # Extract features
    X = await _extract_features(telemetry_records)
    
    if len(X) < MIN_SAMPLES_PER_MINER:
        logger.warning(f"Insufficient complete records for miner {miner_id}: {len(X)}")
        return None
    
    # Train Isolation Forest
    model = IsolationForest(
        contamination=CONTAMINATION,
        n_estimators=N_ESTIMATORS,
        random_state=RANDOM_STATE,
        n_jobs=-1
    )
    
    model.fit(X)
    
    # Save model
    model_path = _get_miner_model_path(miner_id)
    joblib.dump(model, model_path)
    
    # Save metadata
    metadata = {
        "miner_id": miner_id,
        "miner_type": miner.miner_type,
        "trained_at": datetime.utcnow().isoformat(),
        "sample_count": len(X),
        "window_days": window_days,
        "mode_coverage": {mode: count for mode, count in mode_counts.items()} if modes else {},
        "contamination": CONTAMINATION,
        "n_estimators": N_ESTIMATORS,
        "feature_names": ["hashrate_ths", "power_watts", "w_per_th", "temp", "reject_rate"]
    }
    
    meta_path = _get_metadata_path(model_path)
    with open(meta_path, "wb") as f:
        pickle.dump(metadata, f)
    
    logger.info(
        f"✅ Trained miner {miner_id} model: {len(X)} samples, modes={list(modes)}"
    )
    
    return metadata


async def predict_anomaly_score(
    db: AsyncSession,
    miner_id: int,
    recent_telemetry: List[Telemetry]
) -> Optional[float]:
    """
    Predict anomaly score using hybrid model approach.
    
    Fallback logic:
    1. Try per-miner model
    2. Fall back to type model
    3. Return None if no model available
    
    Returns:
        Anomaly score (0.0-1.0) or None
        - 0.0 = normal
        - 1.0 = highly anomalous
    """
    if not SKLEARN_AVAILABLE:
        return None
    
    # Get miner
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    if not miner:
        return None
    
    # Extract features from recent telemetry
    X = await _extract_features(recent_telemetry)
    if len(X) == 0:
        return None
    
    # Take average of recent samples (last 5 minutes typically)
    X_avg = X.mean(axis=0).reshape(1, -1)
    
    # Try per-miner model first
    miner_model_path = _get_miner_model_path(miner_id)
    if miner_model_path.exists():
        try:
            model = joblib.load(miner_model_path)
            # Isolation Forest returns -1 (anomaly) or 1 (normal)
            # decision_function returns anomaly scores (lower = more anomalous)
            score = model.decision_function(X_avg)[0]
            
            # Normalize to 0.0-1.0 range (higher = more anomalous)
            # decision_function range is roughly [-0.5, 0.5]
            # We invert and scale to [0, 1]
            normalized_score = max(0.0, min(1.0, (-score + 0.5)))
            
            logger.debug(f"Miner {miner_id} anomaly score (per-miner): {normalized_score:.3f}")
            return normalized_score
        except Exception as e:
            logger.warning(f"Failed to load per-miner model for {miner_id}: {e}")
    
    # Fall back to type model
    type_model_path = _get_type_model_path(miner.miner_type)
    if type_model_path.exists():
        try:
            model = joblib.load(type_model_path)
            score = model.decision_function(X_avg)[0]
            normalized_score = max(0.0, min(1.0, (-score + 0.5)))
            
            logger.debug(f"Miner {miner_id} anomaly score (type model): {normalized_score:.3f}")
            return normalized_score
        except Exception as e:
            logger.warning(f"Failed to load type model for {miner.miner_type}: {e}")
    
    # No model available
    logger.debug(f"No ML model available for miner {miner_id}")
    return None


async def train_all_models(db: AsyncSession):
    """
    Train all type models and per-miner models.
    Called by weekly scheduler job.
    """
    if not SKLEARN_AVAILABLE:
        logger.warning("scikit-learn not available, skipping ML training")
        return
    
    logger.info("🤖 Starting ML model training (all types + per-miner)")
    
    # Get all unique miner types
    result = await db.execute(
        select(Miner.miner_type)
        .where(Miner.enabled == True)
        .distinct()
    )
    miner_types = [row[0] for row in result.all()]
    
    # Train type models
    type_models_trained = 0
    for miner_type in miner_types:
        metadata = await train_type_model(db, miner_type)
        if metadata:
            type_models_trained += 1
    
    logger.info(f"✅ Trained {type_models_trained}/{len(miner_types)} type models")
    
    # Train per-miner models (only for miners with sufficient data)
    result = await db.execute(
        select(Miner).where(Miner.enabled == True)
    )
    miners = result.scalars().all()
    
    miner_models_trained = 0
    for miner in miners:
        metadata = await train_miner_model(db, miner.id)
        if metadata:
            miner_models_trained += 1
    
    logger.info(f"✅ Trained {miner_models_trained}/{len(miners)} per-miner models")
    logger.info("🤖 ML model training complete")


async def check_retrain_triggers(db: AsyncSession, miner_id: int) -> bool:
    """
    Check if miner model needs retraining based on events.
    
    Triggers:
    - Firmware update
    - Config change
    - Sustained baseline shift >15%
    - False positive spike >20%
    
    Returns:
        True if retrain needed
    """
    # Check if model exists
    model_path = _get_miner_model_path(miner_id)
    if not model_path.exists():
        return False
    
    # Get model metadata
    meta_path = _get_metadata_path(model_path)
    if not meta_path.exists():
        return False
    
    try:
        with open(meta_path, "rb") as f:
            metadata = pickle.load(f)
    except Exception as e:
        logger.error(f"Failed to load metadata for miner {miner_id}: {e}")
        return False
    
    trained_at = datetime.fromisoformat(metadata["trained_at"])
    
    # Check for firmware updates (stored in Miner.firmware_version)
    result = await db.execute(select(Miner).where(Miner.id == miner_id))
    miner = result.scalar_one_or_none()
    if not miner:
        return False
    
    # Check baseline shifts (compare current vs model training time)
    # This would require storing baselines at training time
    # For now, skip this check (can be added later)
    
    return False


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
