"""
Hardware health prediction service
Analyzes telemetry trends to predict potential issues
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import statistics

from core.database import Telemetry, Miner


class HealthPrediction:
    """Health prediction for a miner"""
    def __init__(self, miner_id: int, miner_name: str):
        self.miner_id = miner_id
        self.miner_name = miner_name
        self.predictions = []
        self.risk_score = 0  # 0-100, higher is worse
    
    def add_prediction(self, issue: str, severity: str, confidence: float, details: str):
        """Add a prediction"""
        self.predictions.append({
            "issue": issue,
            "severity": severity,  # low, medium, high, critical
            "confidence": confidence,  # 0.0-1.0
            "details": details
        })
        
        # Update risk score
        severity_weights = {"low": 10, "medium": 25, "high": 50, "critical": 100}
        risk_contribution = severity_weights.get(severity, 0) * confidence
        self.risk_score = min(100, self.risk_score + risk_contribution)
    
    def to_dict(self):
        return {
            "miner_id": self.miner_id,
            "miner_name": self.miner_name,
            "risk_score": round(self.risk_score, 1),
            "predictions": self.predictions
        }


class HealthPredictionService:
    """Service for predicting hardware health issues"""
    
    @staticmethod
    async def predict_hardware_issues(miner_id: int, db: AsyncSession) -> Optional[HealthPrediction]:
        """Analyze telemetry trends and predict potential issues"""
        
        # Get miner
        result = await db.execute(select(Miner).where(Miner.id == miner_id))
        miner = result.scalar_one_or_none()
        
        if not miner:
            return None
        
        prediction = HealthPrediction(miner.id, miner.name)
        
        # Get 7 days of telemetry for trend analysis
        cutoff_7d = datetime.utcnow() - timedelta(days=7)
        result = await db.execute(
            select(Telemetry)
            .where(Telemetry.miner_id == miner_id)
            .where(Telemetry.timestamp >= cutoff_7d)
            .order_by(Telemetry.timestamp)
        )
        telemetry_records = result.scalars().all()
        
        if len(telemetry_records) < 100:
            return prediction  # Not enough data for prediction
        
        # Analyze temperature trend
        await HealthPredictionService._analyze_temperature_trend(
            telemetry_records, prediction, miner.miner_type
        )
        
        # Analyze hashrate stability
        await HealthPredictionService._analyze_hashrate_trend(
            telemetry_records, prediction
        )
        
        # Analyze power consumption trend
        await HealthPredictionService._analyze_power_trend(
            telemetry_records, prediction
        )
        
        # Analyze reject rate trend
        await HealthPredictionService._analyze_reject_trend(
            telemetry_records, prediction
        )
        
        # Analyze uptime pattern
        await HealthPredictionService._analyze_uptime_pattern(
            telemetry_records, prediction
        )
        
        return prediction
    
    @staticmethod
    async def _analyze_temperature_trend(records: List[Telemetry], prediction: HealthPrediction, miner_type: str):
        """Analyze temperature trends"""
        temps = [r.temperature for r in records if r.temperature is not None]
        
        if len(temps) < 50:
            return
        
        # Calculate trend (linear regression approximation)
        recent_temps = temps[-168:]  # Last 7 days worth (assuming 1 per hour)
        if len(recent_temps) < 24:
            return
        
        # Split into first half and second half
        mid = len(recent_temps) // 2
        first_half_avg = statistics.mean(recent_temps[:mid])
        second_half_avg = statistics.mean(recent_temps[mid:])
        temp_increase = second_half_avg - first_half_avg
        
        # Check for rising temperature trend
        if temp_increase > 3:
            confidence = min(1.0, temp_increase / 10)
            prediction.add_prediction(
                "Rising Temperature Trend",
                "medium" if temp_increase < 5 else "high",
                confidence,
                f"Temperature increased by {temp_increase:.1f}°C over the past week. May indicate cooling issues or increased ambient temperature."
            )
        
        # Check if approaching thermal limits - use miner-type-aware thresholds
        max_temp = max(recent_temps)
        
        # Use same thresholds as alert system
        if 'avalon' in miner_type.lower():
            thermal_limit = 95  # Avalon Nano designed for higher temps
        elif 'nerdqaxe' in miner_type.lower():
            thermal_limit = 75  # NerdQaxe moderate threshold
        elif 'bitaxe' in miner_type.lower():
            thermal_limit = 70  # Bitaxe lower threshold
        else:
            thermal_limit = 75  # Generic fallback
        
        if max_temp > thermal_limit - 10:
            confidence = (max_temp - (thermal_limit - 10)) / 10
            prediction.add_prediction(
                "Approaching Thermal Limit",
                "high" if max_temp > thermal_limit - 5 else "medium",
                confidence,
                f"Max temperature {max_temp:.1f}°C is approaching limit of {thermal_limit}°C. Consider improving cooling."
            )
    
    @staticmethod
    async def _analyze_hashrate_trend(records: List[Telemetry], prediction: HealthPrediction):
        """Analyze hashrate stability and trends"""
        hashrates = [r.hashrate for r in records if r.hashrate is not None and r.hashrate > 0]
        
        if len(hashrates) < 50:
            return
        
        recent_hashrates = hashrates[-168:]
        if len(recent_hashrates) < 24:
            return
        
        # Calculate coefficient of variation (std dev / mean)
        mean_hashrate = statistics.mean(recent_hashrates)
        if mean_hashrate > 0:
            std_dev = statistics.stdev(recent_hashrates)
            cv = (std_dev / mean_hashrate) * 100
            
            # High variability indicates instability
            if cv > 20:
                confidence = min(1.0, cv / 40)
                prediction.add_prediction(
                    "Hashrate Instability",
                    "medium" if cv < 30 else "high",
                    confidence,
                    f"Hashrate varies by {cv:.1f}%. Unstable performance may indicate hardware issues or network problems."
                )
        
        # Check for declining trend
        mid = len(recent_hashrates) // 2
        first_half_avg = statistics.mean(recent_hashrates[:mid])
        second_half_avg = statistics.mean(recent_hashrates[mid:])
        
        if first_half_avg > 0:
            decline_pct = ((first_half_avg - second_half_avg) / first_half_avg) * 100
            
            if decline_pct > 5:
                confidence = min(1.0, decline_pct / 20)
                prediction.add_prediction(
                    "Declining Hashrate",
                    "high" if decline_pct > 15 else "medium",
                    confidence,
                    f"Hashrate declined by {decline_pct:.1f}% over the past week. May indicate hardware degradation."
                )
    
    @staticmethod
    async def _analyze_power_trend(records: List[Telemetry], prediction: HealthPrediction):
        """Analyze power consumption trends"""
        powers = [r.power_watts for r in records if r.power_watts is not None and r.power_watts > 0]
        
        if len(powers) < 50:
            return
        
        recent_powers = powers[-168:]
        if len(recent_powers) < 24:
            return
        
        # Check for unusual power increase
        mid = len(recent_powers) // 2
        first_half_avg = statistics.mean(recent_powers[:mid])
        second_half_avg = statistics.mean(recent_powers[mid:])
        
        if first_half_avg > 0:
            increase_pct = ((second_half_avg - first_half_avg) / first_half_avg) * 100
            
            if increase_pct > 10:
                confidence = min(1.0, increase_pct / 30)
                prediction.add_prediction(
                    "Increasing Power Consumption",
                    "medium" if increase_pct < 20 else "high",
                    confidence,
                    f"Power consumption increased by {increase_pct:.1f}% without corresponding hashrate increase. May indicate inefficiency."
                )
    
    @staticmethod
    async def _analyze_reject_trend(records: List[Telemetry], prediction: HealthPrediction):
        """Analyze share reject rate trends"""
        # Calculate reject rates from consecutive records
        reject_rates = []
        for i in range(1, len(records)):
            prev = records[i-1]
            curr = records[i]
            
            if prev.shares_accepted is not None and curr.shares_accepted is not None:
                accepted_delta = curr.shares_accepted - prev.shares_accepted
                rejected_delta = (curr.shares_rejected or 0) - (prev.shares_rejected or 0)
                
                if accepted_delta + rejected_delta > 0:
                    reject_rate = (rejected_delta / (accepted_delta + rejected_delta)) * 100
                    reject_rates.append(reject_rate)
        
        if len(reject_rates) < 24:
            return
        
        recent_rejects = reject_rates[-168:]
        avg_reject_rate = statistics.mean(recent_rejects)
        
        if avg_reject_rate > 2:
            confidence = min(1.0, avg_reject_rate / 10)
            prediction.add_prediction(
                "Elevated Reject Rate",
                "high" if avg_reject_rate > 5 else "medium",
                confidence,
                f"Average reject rate of {avg_reject_rate:.2f}% is elevated. May indicate network latency or miner instability."
            )
    
    @staticmethod
    async def _analyze_uptime_pattern(records: List[Telemetry], prediction: HealthPrediction):
        """Analyze uptime patterns for frequent restarts"""
        # Check for gaps in telemetry (indicating offline periods)
        gaps = []
        for i in range(1, len(records)):
            time_diff = (records[i].timestamp - records[i-1].timestamp).total_seconds()
            if time_diff > 300:  # More than 5 minutes gap
                gaps.append(time_diff / 60)  # Convert to minutes
        
        if len(gaps) > 5:
            avg_gap = statistics.mean(gaps)
            confidence = min(1.0, len(gaps) / 20)
            prediction.add_prediction(
                "Frequent Disconnections",
                "high" if len(gaps) > 10 else "medium",
                confidence,
                f"Detected {len(gaps)} disconnections in the past week (avg {avg_gap:.0f} min). May indicate power or network issues."
            )
