"""
Health scoring system for miners
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import HealthScore, Telemetry, Miner


class HealthScoringService:
    """Calculate health scores for miners based on telemetry"""
    
    @staticmethod
    async def calculate_health_score(
        miner_id: int,
        db: AsyncSession,
        hours: int = 24
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate comprehensive health score for a miner
        
        Returns:
            Dict with scores (0-100) for uptime, temperature, hashrate, reject_rate, and overall
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        # Get telemetry data
        result = await db.execute(
            select(Telemetry)
            .where(Telemetry.miner_id == miner_id)
            .where(Telemetry.timestamp >= cutoff_time)
            .order_by(Telemetry.timestamp.asc())
        )
        telemetry_data = result.scalars().all()
        
        if not telemetry_data:
            return None
        
        # Get miner type for temperature threshold
        result = await db.execute(select(Miner).where(Miner.id == miner_id))
        miner = result.scalar_one_or_none()
        miner_type = miner.miner_type if miner else None
        
        # Calculate individual scores
        uptime_score = HealthScoringService._calculate_uptime_score(telemetry_data, hours)
        temperature_score = HealthScoringService._calculate_temperature_score(telemetry_data, miner_type)
        hashrate_score = HealthScoringService._calculate_hashrate_score(telemetry_data)
        reject_rate_score = HealthScoringService._calculate_reject_rate_score(telemetry_data)
        
        # Check if temperature data is available (some miners may not report it)
        has_temp_data = any(t.temperature is not None for t in telemetry_data)
        
        # Calculate weighted overall score
        # Adjust weights if temperature data is unavailable
        if has_temp_data:
            # Standard weights for ASIC miners with temperature sensors
            overall_score = (
                uptime_score * 0.3 +
                temperature_score * 0.25 +
                hashrate_score * 0.25 +
                reject_rate_score * 0.20
            )
        else:
            # Adjusted weights for CPU miners without temperature data
            # Redistribute temperature weight to other metrics
            overall_score = (
                uptime_score * 0.4 +      # Increased from 0.3
                hashrate_score * 0.35 +   # Increased from 0.25
                reject_rate_score * 0.25  # Increased from 0.20
            )
            temperature_score = None  # Don't show temperature score if no data
        
        result = {
            "overall_score": round(overall_score, 2),
            "uptime_score": round(uptime_score, 2),
            "hashrate_score": round(hashrate_score, 2),
            "reject_rate_score": round(reject_rate_score, 2),
            "data_points": len(telemetry_data),
            "period_hours": hours
        }
        
        # Only include temperature score if data is available
        if temperature_score is not None:
            result["temperature_score"] = round(temperature_score, 2)
        
        return result
    
    @staticmethod
    def _calculate_uptime_score(telemetry_data: list, expected_hours: int) -> float:
        """
        Calculate uptime score based on data availability
        Score: 100 = perfect data coverage, 0 = no data
        """
        if not telemetry_data:
            return 0.0
        
        # Expected data points (one every 30 seconds)
        expected_points = expected_hours * 120  # 120 points per hour
        actual_points = len(telemetry_data)
        
        # Calculate coverage percentage
        coverage = min(actual_points / expected_points, 1.0) * 100
        
        # Check for gaps (offline periods)
        gaps = 0
        for i in range(1, len(telemetry_data)):
            time_diff = (telemetry_data[i].timestamp - telemetry_data[i-1].timestamp).seconds
            if time_diff > 60:  # Gap > 1 minute
                gaps += 1
        
        # Penalize for gaps
        gap_penalty = min(gaps * 2, 30)  # Max 30 point penalty
        
        return max(coverage - gap_penalty, 0)
    
    @staticmethod
    def _calculate_temperature_score(telemetry_data: list, miner_type: str = None) -> float:
        """
        Calculate temperature score
        Score: 100 = optimal, decreases as temp increases
        
        Different thresholds for different miner types:
        - Avalon Nano: designed for up to 90°C
        - Others: optimal below 75°C
        
        Returns 100.0 (perfect score) if no temperature data available
        """
        temps = [t.temperature for t in telemetry_data if t.temperature is not None]
        
        if not temps:
            return 100.0  # Perfect score if no data (don't penalize CPU miners)
        
        avg_temp = sum(temps) / len(temps)
        max_temp = max(temps)
        
        # Different temperature scales based on miner type
        if miner_type and 'avalon' in miner_type.lower():
            # Avalon Nano: <70°C = 100, 70-80°C = 90, 80-90°C = 75, 90-95°C = 60, 95+°C = 40
            if avg_temp < 70:
                score = 100
            elif avg_temp < 80:
                score = 100 - ((avg_temp - 70) * 1)
            elif avg_temp < 90:
                score = 90 - ((avg_temp - 80) * 1.5)
            elif avg_temp < 95:
                score = 75 - ((avg_temp - 90) * 3)
            else:
                score = max(40 - ((avg_temp - 95) * 2), 0)
            
            # Penalize for extreme spikes (>100°C)
            if max_temp > 100:
                score = score * 0.8
        elif miner_type and 'bitaxe' in miner_type.lower():
            # Bitaxe: <55°C = 100, 55-65°C = 85, 65-70°C = 60, 70+°C = 40
            if avg_temp < 55:
                score = 100
            elif avg_temp < 65:
                score = 100 - ((avg_temp - 55) * 1.5)
            elif avg_temp < 70:
                score = 85 - ((avg_temp - 65) * 5)
            else:
                score = max(40 - ((avg_temp - 70) * 2), 0)
            
            # Penalize for spikes (>75°C)
            if max_temp > 75:
                score = score * 0.8
        elif miner_type and 'nerdqaxe' in miner_type.lower():
            # NerdQaxe: <60°C = 100, 60-70°C = 85, 70-75°C = 60, 75+°C = 40
            if avg_temp < 60:
                score = 100
            elif avg_temp < 70:
                score = 100 - ((avg_temp - 60) * 1.5)
            elif avg_temp < 75:
                score = 85 - ((avg_temp - 70) * 5)
            else:
                score = max(40 - ((avg_temp - 75) * 2), 0)
            
            # Penalize for spikes (>80°C)
            if max_temp > 80:
                score = score * 0.8
        else:
            # Generic fallback: <60°C = 100, 60-70°C = 80, 70-80°C = 60, 80+°C = 40
            if avg_temp < 60:
                score = 100
            elif avg_temp < 70:
                score = 100 - ((avg_temp - 60) * 2)
            elif avg_temp < 80:
                score = 80 - ((avg_temp - 70) * 2)
            else:
                score = max(40 - ((avg_temp - 80) * 1), 0)
            
            # Penalize for spikes (>85°C)
            if max_temp > 85:
                score = score * 0.8
        
        return max(score, 0)
    
    @staticmethod
    def _calculate_hashrate_score(telemetry_data: list) -> float:
        """
        Calculate hashrate stability score
        Score: 100 = very stable, decreases with variance
        """
        hashrates = [t.hashrate for t in telemetry_data if t.hashrate is not None and t.hashrate > 0]
        
        if len(hashrates) < 5:
            return 50.0  # Neutral if insufficient data
        
        avg_hashrate = sum(hashrates) / len(hashrates)
        
        # Calculate coefficient of variation (CV)
        variance = sum((h - avg_hashrate) ** 2 for h in hashrates) / len(hashrates)
        std_dev = variance ** 0.5
        cv = (std_dev / avg_hashrate) * 100 if avg_hashrate > 0 else 0
        
        # Score based on stability
        # CV < 5% = excellent (100), 5-10% = good (80), 10-20% = fair (60), >20% = poor (40)
        if cv < 5:
            score = 100
        elif cv < 10:
            score = 100 - ((cv - 5) * 4)
        elif cv < 20:
            score = 80 - ((cv - 10) * 2)
        else:
            score = max(60 - ((cv - 20) * 1), 20)
        
        return max(score, 0)
    
    @staticmethod
    def _calculate_reject_rate_score(telemetry_data: list) -> float:
        """
        Calculate reject rate score
        Score: 100 = <1%, decreases as reject rate increases
        """
        # Get first and last telemetry to calculate delta
        if len(telemetry_data) < 2:
            return 100.0  # Assume good if no data
        
        first = telemetry_data[0]
        last = telemetry_data[-1]
        
        if not first.shares_accepted or not last.shares_accepted:
            return 100.0
        
        accepted_delta = last.shares_accepted - first.shares_accepted
        rejected_delta = (last.shares_rejected or 0) - (first.shares_rejected or 0)
        
        if accepted_delta <= 0:
            return 100.0
        
        total_shares = accepted_delta + rejected_delta
        reject_rate = (rejected_delta / total_shares) * 100 if total_shares > 0 else 0
        
        # Score based on reject rate
        # <1% = 100, 1-3% = 85, 3-5% = 70, 5-10% = 50, >10% = 30
        if reject_rate < 1:
            score = 100
        elif reject_rate < 3:
            score = 100 - ((reject_rate - 1) * 7.5)
        elif reject_rate < 5:
            score = 85 - ((reject_rate - 3) * 7.5)
        elif reject_rate < 10:
            score = 70 - ((reject_rate - 5) * 4)
        else:
            score = max(50 - ((reject_rate - 10) * 2), 0)
        
        return max(score, 0)
    
    @staticmethod
    async def get_health_trend(
        miner_id: int,
        db: AsyncSession,
        days: int = 7
    ) -> list:
        """Get health score trend over time"""
        cutoff_time = datetime.utcnow() - timedelta(days=days)
        
        result = await db.execute(
            select(HealthScore)
            .where(HealthScore.miner_id == miner_id)
            .where(HealthScore.timestamp >= cutoff_time)
            .order_by(HealthScore.timestamp.asc())
        )
        scores = result.scalars().all()
        
        result_list = []
        for score in scores:
            score_dict = {
                "timestamp": score.timestamp.isoformat(),
                "overall_score": score.overall_score,
                "uptime_score": score.uptime_score,
                "hashrate_score": score.hashrate_score,
                "reject_rate_score": score.reject_rate_score
            }
            # Only include temperature_score if available
            if score.temperature_score is not None:
                score_dict["temperature_score"] = score.temperature_score
            result_list.append(score_dict)
        
        return result_list


async def record_health_scores(db: AsyncSession):
    """Record health scores for all active miners (called by scheduler)"""
    result = await db.execute(select(Miner).where(Miner.enabled == True))
    miners = result.scalars().all()
    
    for miner in miners:
        try:
            score_data = await HealthScoringService.calculate_health_score(miner.id, db, hours=24)
            
            if score_data:
                health_score = HealthScore(
                    miner_id=miner.id,
                    timestamp=datetime.utcnow(),
                    overall_score=score_data["overall_score"],
                    uptime_score=score_data["uptime_score"],
                    temperature_score=score_data.get("temperature_score"),  # Optional for some miners
                    hashrate_score=score_data["hashrate_score"],
                    reject_rate_score=score_data["reject_rate_score"],
                    details={"period_hours": 24, "data_points": score_data["data_points"]}
                )
                db.add(health_score)
        
        except Exception as e:
            print(f"❌ Failed to calculate health score for {miner.name}: {e}")
    
    await db.commit()
