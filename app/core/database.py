"""
SQLite database setup and models
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Float, DateTime, JSON, Boolean, Index, Text
from datetime import datetime
from typing import Optional
from core.config import settings


class Base(DeclarativeBase):
    """Base class for all models"""
    pass


class Miner(Base):
    """Miner configuration and state"""
    __tablename__ = "miners"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    miner_type: Mapped[str] = mapped_column(String(50))  # avalon_nano, bitaxe, nerdqaxe, nmminer
    ip_address: Mapped[str] = mapped_column(String(45))
    port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    firmware_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    manual_power_watts: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # User-provided power estimate for miners without auto-detection
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    last_mode_change: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # Track when mode was last changed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Pool(Base):
    """Mining pool configuration"""
    __tablename__ = "pools"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(255))  # Hostname or IP address
    port: Mapped[int] = mapped_column(Integer)
    user: Mapped[str] = mapped_column(String(255))
    password: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)  # For load balancing weight
    network_difficulty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # DGB network difficulty
    network_difficulty_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    best_share: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Current best share in round
    best_share_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # When best_share last improved
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HighDiffShare(Base):
    """High difficulty shares leaderboard (ASIC miners only)"""
    __tablename__ = "high_diff_shares"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    miner_id: Mapped[int] = mapped_column(Integer, index=True)
    miner_name: Mapped[str] = mapped_column(String(100))  # Snapshot in case miner renamed
    miner_type: Mapped[str] = mapped_column(String(50))  # avalon_nano, bitaxe, nerdqaxe
    coin: Mapped[str] = mapped_column(String(10))  # BTC, BCH, BC2, DGB
    pool_name: Mapped[str] = mapped_column(String(100))  # Pool name at time of share
    difficulty: Mapped[float] = mapped_column(Float, index=True)  # Share difficulty
    network_difficulty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Network difficulty at time
    was_block_solve: Mapped[bool] = mapped_column(Boolean, default=False)  # True if share_diff >= network_diff
    hashrate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Miner hashrate at time
    hashrate_unit: Mapped[str] = mapped_column(String(10), default="GH/s")
    miner_mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # eco/std/turbo/oc/low/med/high
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    
    __table_args__ = (
        Index('idx_difficulty_timestamp', 'difficulty', 'timestamp'),
    )


class BlockFound(Base):
    """Blocks solved by miners (Coin Hunter leaderboard)"""
    __tablename__ = "blocks_found"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    miner_id: Mapped[int] = mapped_column(Integer, index=True)
    miner_name: Mapped[str] = mapped_column(String(100))  # Snapshot in case miner renamed
    miner_type: Mapped[str] = mapped_column(String(50))  # avalon_nano, bitaxe, nerdqaxe
    coin: Mapped[str] = mapped_column(String(10), index=True)  # BTC, BCH, BC2, DGB
    pool_name: Mapped[str] = mapped_column(String(100))  # Pool name
    difficulty: Mapped[float] = mapped_column(Float)  # Share difficulty that solved the block
    network_difficulty: Mapped[float] = mapped_column(Float)  # Network difficulty at time
    block_height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Block height if available
    block_reward: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Block reward if available
    hashrate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Miner hashrate at time
    hashrate_unit: Mapped[str] = mapped_column(String(10), default="GH/s")
    miner_mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # eco/std/turbo/oc/low/med/high
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/confirmed/orphaned
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    
    __table_args__ = (
        Index('idx_miner_coin', 'miner_id', 'coin'),
    )


class MinerPoolSlot(Base):
    """Cached pool slot configuration for Avalon Nano miners (3 slots per miner)"""
    __tablename__ = "miner_pool_slots"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    miner_id: Mapped[int] = mapped_column(Integer, index=True)
    slot_number: Mapped[int] = mapped_column(Integer)  # 0, 1, 2 for Avalon Nano
    pool_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # References Pool.id if matched
    pool_url: Mapped[str] = mapped_column(String(255))
    pool_port: Mapped[int] = mapped_column(Integer)
    pool_user: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)  # Currently selected slot
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Unique constraint: one entry per miner per slot
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )


class Telemetry(Base):
    """Miner telemetry data"""
    __tablename__ = "telemetry"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    miner_id: Mapped[int] = mapped_column(Integer, index=True)  # Added index for performance
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    hashrate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hashrate_unit: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # KH/s, MH/s, GH/s, TH/s - no default, must be set explicitly
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    power_watts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    energy_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Cost in pence for this 1-minute period (power_watts / 60 / 1000 * agile_price)
    shares_accepted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shares_rejected: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pool_in_use: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # low/med/high/eco/turbo/oc captured at poll time
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Additional miner-specific data
    
    # Composite index for common query pattern (miner_id + timestamp)
    __table_args__ = (
        Index('ix_telemetry_miner_timestamp', 'miner_id', 'timestamp'),
    )


class TelemetryHourly(Base):
    """Hourly aggregated miner telemetry data"""
    __tablename__ = "telemetry_hourly"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    miner_id: Mapped[int] = mapped_column(Integer, index=True)
    hour_start: Mapped[datetime] = mapped_column(DateTime, index=True)  # Start of hour (YYYY-MM-DD HH:00:00)
    uptime_minutes: Mapped[int] = mapped_column(Integer)  # Number of 1-minute records in this hour
    avg_hashrate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_hashrate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_hashrate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hashrate_unit: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, default="GH/s")
    avg_temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    peak_temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Sum of power consumption
    total_energy_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Sum of energy_cost in pence
    shares_accepted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shares_rejected: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reject_rate_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_telemetry_hourly_miner_hour', 'miner_id', 'hour_start'),
    )


class TelemetryDaily(Base):
    """Daily aggregated miner telemetry data"""
    __tablename__ = "telemetry_daily"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    miner_id: Mapped[int] = mapped_column(Integer, index=True)
    date: Mapped[datetime] = mapped_column(DateTime, index=True)  # Date (YYYY-MM-DD 00:00:00)
    uptime_minutes: Mapped[int] = mapped_column(Integer)  # Total minutes of uptime for the day
    uptime_percentage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # % of 1440 minutes
    avg_hashrate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_hashrate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_hashrate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hashrate_unit: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, default="GH/s")
    avg_temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    peak_temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_energy_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Sum in pence
    shares_accepted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shares_rejected: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reject_rate_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    health_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0-100 health score
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_telemetry_daily_miner_date', 'miner_id', 'date'),
    )


class EnergyPrice(Base):
    """Octopus Agile energy pricing"""
    __tablename__ = "energy_prices"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    region: Mapped[str] = mapped_column(String(1), index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime, index=True)
    valid_to: Mapped[datetime] = mapped_column(DateTime)
    price_pence: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgileForecastSlot(Base):
    """Future Agile price forecast slots from AgilePredict"""
    __tablename__ = "agile_forecast_slots"

    id: Mapped[int] = mapped_column(primary_key=True)
    region: Mapped[str] = mapped_column(String(1), index=True)
    slot_start: Mapped[datetime] = mapped_column(DateTime, index=True)
    slot_end: Mapped[datetime] = mapped_column(DateTime)
    price_pred_pence: Mapped[float] = mapped_column(Float)
    price_low_pence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_high_pence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    forecast_created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_agile_forecast_region_slot', 'region', 'slot_start', unique=True),
    )


class AutomationRule(Base):
    """Automation rules"""
    __tablename__ = "automation_rules"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    trigger_type: Mapped[str] = mapped_column(String(50))  # price_threshold, time_window, miner_offline, etc.
    trigger_config: Mapped[dict] = mapped_column(JSON)
    action_type: Mapped[str] = mapped_column(String(50))  # apply_mode, switch_pool, alert, etc.
    action_config: Mapped[dict] = mapped_column(JSON)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    last_executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_execution_context: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Event(Base):
    """System events and alerts"""
    __tablename__ = "events"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    event_type: Mapped[str] = mapped_column(String(50))  # info, warning, error, alert
    source: Mapped[str] = mapped_column(String(100))  # miner_id, automation_rule_id, system
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class CryptoPrice(Base):
    """Cached cryptocurrency prices"""
    __tablename__ = "crypto_prices"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    coin_id: Mapped[str] = mapped_column(String(50), unique=True)  # bitcoin, bitcoin-cash, digibyte
    price_gbp: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(50))  # coingecko, coincap, binance
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NotificationConfig(Base):
    """Notification channel configuration"""
    __tablename__ = "notification_config"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    channel_type: Mapped[str] = mapped_column(String(20))  # telegram, discord
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict] = mapped_column(JSON)  # bot_token, chat_id for Telegram; webhook_url for Discord
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AlertConfig(Base):
    """Alert type configuration"""
    __tablename__ = "alert_config"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_type: Mapped[str] = mapped_column(String(50), unique=True)  # miner_offline, high_temp, pool_failure, etc.
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # thresholds, timeouts, etc.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NotificationLog(Base):
    """Log of sent notifications"""
    __tablename__ = "notification_log"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    channel_type: Mapped[str] = mapped_column(String(20))
    alert_type: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(String(1000))
    success: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)


class AlertThrottle(Base):
    """Track alert sending to prevent spam"""
    __tablename__ = "alert_throttle"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    miner_id: Mapped[int] = mapped_column(Integer, index=True)
    alert_type: Mapped[str] = mapped_column(String(50), index=True)
    last_sent: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    send_count: Mapped[int] = mapped_column(Integer, default=1)  # Track how many times sent


class HealthScore(Base):
    """Miner health scores over time"""
    __tablename__ = "health_scores"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    miner_id: Mapped[int] = mapped_column(Integer, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    overall_score: Mapped[float] = mapped_column(Float)  # 0-100
    uptime_score: Mapped[float] = mapped_column(Float)  # 0-100
    temperature_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0-100, nullable for miners without temp sensors
    hashrate_score: Mapped[float] = mapped_column(Float)  # 0-100
    reject_rate_score: Mapped[float] = mapped_column(Float)  # 0-100
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class PoolHealth(Base):
    """Pool health monitoring"""
    __tablename__ = "pool_health"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    pool_id: Mapped[int] = mapped_column(Integer, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    response_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_reachable: Mapped[bool] = mapped_column(Boolean, default=True)
    reject_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Percentage
    shares_accepted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shares_rejected: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    health_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0-100
    luck_percentage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Pool luck %
    error_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)


class PoolHealthHourly(Base):
    """Hourly aggregated pool health data"""
    __tablename__ = "pool_health_hourly"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    pool_id: Mapped[int] = mapped_column(Integer, index=True)
    hour_start: Mapped[datetime] = mapped_column(DateTime, index=True)  # Start of hour (YYYY-MM-DD HH:00:00)
    checks_count: Mapped[int] = mapped_column(Integer)  # Number of checks in this hour
    avg_response_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_response_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    uptime_checks: Mapped[int] = mapped_column(Integer)  # Number of successful checks
    uptime_percentage: Mapped[float] = mapped_column(Float)  # % of checks that were reachable
    avg_health_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Average 0-100 score
    avg_reject_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_shares_accepted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_shares_rejected: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_pool_health_hourly_pool_hour', 'pool_id', 'hour_start'),
    )


class PoolHealthDaily(Base):
    """Daily aggregated pool health data"""
    __tablename__ = "pool_health_daily"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    pool_id: Mapped[int] = mapped_column(Integer, index=True)
    date: Mapped[datetime] = mapped_column(DateTime, index=True)  # Date (YYYY-MM-DD 00:00:00)
    checks_count: Mapped[int] = mapped_column(Integer)  # Total checks for the day
    avg_response_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_response_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    uptime_checks: Mapped[int] = mapped_column(Integer)  # Successful checks
    uptime_percentage: Mapped[float] = mapped_column(Float)  # Daily availability %
    avg_health_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_reject_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_shares_accepted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_shares_rejected: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    downtime_minutes: Mapped[int] = mapped_column(Integer, default=0)  # Estimated downtime
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_pool_health_daily_pool_date', 'pool_id', 'date'),
    )


class HourlyMinerAnalytics(Base):
    """Hourly aggregated miner analytics combining power, hash work, and performance metrics"""
    __tablename__ = "hourly_miner_analytics"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    miner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    pool_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Which pool active during hour
    coin: Mapped[str] = mapped_column(String(10), nullable=False)  # 'BTC', 'XMR'
    hour_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # Dominant mode (most frequent during hour)
    mode_changes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Number of mode transitions this hour
    mode_distribution: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Minutes per mode: {"high": 30, "low": 30}
    tuning_profile_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Hash work metrics
    total_hashes_gh: Mapped[float] = mapped_column(Float, nullable=False)  # Gigahashes completed this hour
    avg_hashrate_gh: Mapped[float] = mapped_column(Float, nullable=False)
    peak_hashrate_gh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_hashrate_gh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    uptime_seconds: Mapped[int] = mapped_column(Integer, nullable=False)  # Actual mining time
    
    # Share statistics
    shares_accepted: Mapped[int] = mapped_column(Integer, default=0)
    shares_rejected: Mapped[int] = mapped_column(Integer, default=0)
    share_difficulty_avg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    best_share_difficulty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Closest to block
    
    # Network context
    network_difficulty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    block_height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Power and thermal metrics
    avg_power_watts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_power_watts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_power_watts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_chip_temp_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_chip_temp_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Derived efficiency metrics
    watts_per_gh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Power efficiency
    hashes_per_share: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Share efficiency
    reject_rate_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_hourly_analytics_miner_hour', 'miner_id', 'hour_start'),
        Index('ix_hourly_analytics_coin_hour', 'coin', 'hour_start'),
        Index('ix_hourly_analytics_pool_hour', 'pool_id', 'hour_start'),
    )


class DailyMinerAnalytics(Base):
    """Daily aggregated miner analytics for long-term trend analysis"""
    __tablename__ = "daily_miner_analytics"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    miner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    coin: Mapped[str] = mapped_column(String(10), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    
    # Hash work aggregates
    total_hashes_th: Mapped[float] = mapped_column(Float, nullable=False)  # Terahashes for the day
    avg_hashrate_gh: Mapped[float] = mapped_column(Float, nullable=False)
    peak_hashrate_gh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    uptime_hours: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Share statistics
    total_shares_accepted: Mapped[int] = mapped_column(Integer, default=0)
    total_shares_rejected: Mapped[int] = mapped_column(Integer, default=0)
    avg_reject_rate_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    best_share_difficulty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Power aggregates
    avg_power_watts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_power_watts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_energy_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Thermal aggregates
    avg_temp_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_temp_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Efficiency aggregates
    avg_watts_per_gh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Mode distribution (JSON: {"low": 8, "med": 12, "high": 4} hours per mode)
    mode_distribution: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_daily_analytics_miner_date', 'miner_id', 'date'),
        Index('ix_daily_analytics_coin_date', 'coin', 'date'),
    )


class TuningProfile(Base):
    """Saved tuning/overclocking profiles"""
    __tablename__ = "tuning_profiles"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    miner_type: Mapped[str] = mapped_column(String(50))  # avalon_nano, bitaxe, nerdqaxe
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    settings: Mapped[dict] = mapped_column(JSON)  # frequency, voltage, mode, etc
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)  # System presets vs user-created
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PoolStrategy(Base):
    """Pool switching strategy configuration"""
    __tablename__ = "pool_strategies"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    strategy_type: Mapped[str] = mapped_column(String(50))  # round_robin, load_balance, failover
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    pool_ids: Mapped[list] = mapped_column(JSON)  # List of pool IDs in strategy
    miner_ids: Mapped[list] = mapped_column(JSON, default=list)  # List of miner IDs assigned to this strategy (empty = all miners)
    config: Mapped[dict] = mapped_column(JSON)  # Strategy-specific config
    current_pool_index: Mapped[int] = mapped_column(Integer, default=0)  # For round-robin
    last_switch: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PoolStrategyLog(Base):
    """Log of pool strategy switches"""
    __tablename__ = "pool_strategy_logs"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(Integer, index=True)
    from_pool_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    to_pool_id: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(255))
    miners_affected: Mapped[int] = mapped_column(Integer, default=0)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class AuditLog(Base):
    """Audit log for tracking configuration changes"""
    __tablename__ = "audit_logs"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    user: Mapped[str] = mapped_column(String(100), default="system")  # Future: actual user auth
    action: Mapped[str] = mapped_column(String(50), index=True)  # create, update, delete, execute
    resource_type: Mapped[str] = mapped_column(String(50), index=True)  # miner, pool, strategy, automation, etc
    resource_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    resource_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    changes: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # before/after values
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="success")  # success, failure
    error_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)


class CustomDashboard(Base):
    """Custom dashboard configurations"""
    __tablename__ = "custom_dashboards"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    layout: Mapped[dict] = mapped_column(JSON)  # Grid layout configuration
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DashboardWidget(Base):
    """Widgets for custom dashboards"""
    __tablename__ = "dashboard_widgets"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    dashboard_id: Mapped[int] = mapped_column(Integer, index=True)
    widget_type: Mapped[str] = mapped_column(String(50))  # miner_stats, energy_price, pool_health, chart, etc
    config: Mapped[dict] = mapped_column(JSON)  # Widget-specific configuration
    position: Mapped[dict] = mapped_column(JSON)  # {x, y, w, h} for grid layout
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DailyMinerStats(Base):
    """Daily aggregated miner statistics for long-term analytics"""
    __tablename__ = "daily_miner_stats"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    miner_id: Mapped[int] = mapped_column(Integer, index=True)
    date: Mapped[datetime] = mapped_column(DateTime, index=True)  # Date at midnight UTC
    
    # Hashrate stats
    avg_hashrate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_hashrate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_hashrate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hashrate_unit: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, default="GH/s")
    
    # Temperature stats (ASIC only)
    avg_temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Power stats (ASIC only)
    avg_power: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Uptime
    uptime_percent: Mapped[float] = mapped_column(Float, default=0.0)
    offline_minutes: Mapped[int] = mapped_column(Integer, default=0)
    
    # Shares
    total_shares_accepted: Mapped[int] = mapped_column(Integer, default=0)
    total_shares_rejected: Mapped[int] = mapped_column(Integer, default=0)
    reject_rate_percent: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Economics
    energy_cost_gbp: Mapped[float] = mapped_column(Float, default=0.0)
    earnings_gbp: Mapped[float] = mapped_column(Float, default=0.0)
    profit_gbp: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Metadata
    data_points: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Unique constraint: one entry per miner per day
    __table_args__ = ({'sqlite_autoincrement': True},)


class DailyPoolStats(Base):
    """Daily aggregated pool statistics"""
    __tablename__ = "daily_pool_stats"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    pool_id: Mapped[int] = mapped_column(Integer, index=True)
    date: Mapped[datetime] = mapped_column(DateTime, index=True)
    
    # Pool performance
    blocks_found: Mapped[int] = mapped_column(Integer, default=0)
    total_shares_submitted: Mapped[int] = mapped_column(Integer, default=0)
    avg_luck_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Health
    avg_health_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    uptime_percent: Mapped[float] = mapped_column(Float, default=100.0)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = ({'sqlite_autoincrement': True},)


class MonthlyMinerStats(Base):
    """Monthly rollup of miner statistics"""
    __tablename__ = "monthly_miner_stats"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    miner_id: Mapped[int] = mapped_column(Integer, index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    month: Mapped[int] = mapped_column(Integer, index=True)  # 1-12
    
    # Aggregated from daily stats
    avg_hashrate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hashrate_unit: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    total_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    uptime_percent: Mapped[float] = mapped_column(Float, default=0.0)
    
    total_shares_accepted: Mapped[int] = mapped_column(Integer, default=0)
    total_shares_rejected: Mapped[int] = mapped_column(Integer, default=0)
    reject_rate_percent: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Economics
    total_energy_cost_gbp: Mapped[float] = mapped_column(Float, default=0.0)
    total_earnings_gbp: Mapped[float] = mapped_column(Float, default=0.0)
    total_profit_gbp: Mapped[float] = mapped_column(Float, default=0.0)
    
    days_active: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = ({'sqlite_autoincrement': True},)


class AgileStrategy(Base):
    """Agile Solo Mining Strategy configuration and state"""
    __tablename__ = "agile_strategy"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    current_price_band: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # off, dgb_high, dgb_med, dgb_low, bch, btc
    current_band_sort_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Track specific band by sort_order
    hysteresis_counter: Mapped[int] = mapped_column(Integer, default=0)  # 2-slot delay for upgrading bands
    last_action_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_price_checked: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # p/kWh
    last_aggregation_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # When telemetry was last aggregated
    state_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Additional state tracking
    champion_mode_enabled: Mapped[bool] = mapped_column(Boolean, default=False)  # Enable champion mode for Band 5
    current_champion_miner_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Current champion (most efficient miner)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgileStrategyBand(Base):
    """Configurable price bands for Agile Solo Strategy"""
    __tablename__ = "agile_strategy_bands"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(Integer, index=True)  # FK to AgileStrategy
    min_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Minimum price (p/kWh), None for lowest band
    max_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Maximum price (p/kWh), None for highest band
    target_coin: Mapped[str] = mapped_column(String(10))  # OFF, DGB, BCH, BTC
    bitaxe_mode: Mapped[str] = mapped_column(String(20))  # managed_externally, eco, standard, turbo, oc
    nerdqaxe_mode: Mapped[str] = mapped_column(String(20))  # managed_externally, eco, std, turbo, oc
    avalon_nano_mode: Mapped[str] = mapped_column(String(20))  # managed_externally, low, med, high
    sort_order: Mapped[int] = mapped_column(Integer, default=0)  # Display order (0-based)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Ensure bands are unique per strategy and sort order
    __table_args__ = (
        Index('ix_strategy_bands_unique', 'strategy_id', 'sort_order', unique=True),
    )


class MinerStrategy(Base):
    """Links miners to Agile Solo Strategy"""
    __tablename__ = "miner_strategy"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    miner_id: Mapped[int] = mapped_column(Integer, index=True)
    strategy_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Ensure one record per miner
    __table_args__ = (
        Index('ix_miner_strategy_unique', 'miner_id', unique=True),
    )


# Database engine and session
def get_database_url() -> str:
    """Get database URL based on active configuration"""
    from core.config import app_config
    import logging
    logger = logging.getLogger(__name__)
    
    active_db = app_config.get("database.active", "sqlite")
    
    logger.info(f"🗄️ Database configuration: active='{active_db}'")
    
    if active_db == "postgresql":
        pg_config = app_config.get("database.postgresql", {})
        host = pg_config.get("host", "localhost")
        port = pg_config.get("port", 5432)
        database = pg_config.get("database", "hmm")
        username = pg_config.get("username", "hmm_user")
        password = pg_config.get("password", "")
        
        if not password:
            logger.warning("⚠️ PostgreSQL selected but no password configured, falling back to SQLite")
            return f"sqlite+aiosqlite:///{settings.DB_PATH}"
        
        logger.info(f"🐘 Using PostgreSQL: {username}@{host}:{port}/{database}")
        return f"postgresql+asyncpg://{username}:{password}@{host}:{port}/{database}"
    else:
        # Default to SQLite
        logger.info(f"💾 Using SQLite: {settings.DB_PATH}")
        return f"sqlite+aiosqlite:///{settings.DB_PATH}"

# Create engine with database-specific settings
def create_engine_for_database():
    db_url = get_database_url()
    
    if "sqlite" in db_url:
        # SQLite-specific settings
        engine = create_async_engine(
            db_url,
            echo=False,
            connect_args={
                "timeout": 30,
                "check_same_thread": False
            },
            pool_pre_ping=True
        )
        
        # Enable WAL mode for SQLite
        from sqlalchemy import event
        @event.listens_for(engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()
    else:
        # PostgreSQL settings
        engine = create_async_engine(
            db_url,
            echo=False,
            pool_size=40,  # Connection pool size
            max_overflow=20,  # Allow burst connections
            pool_timeout=5,  # Fail fast when pool is exhausted
            pool_pre_ping=True
        )
    
    return engine

# Create engine and session maker
# These are initialized when the module is imported
engine = create_engine_for_database()
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Metric(Base):
    """Pre-computed metrics for fast querying"""
    __tablename__ = "metrics"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    metric_type: Mapped[str] = mapped_column(String(50), index=True)  # energy_cost, hashrate, pool_health, etc
    entity_type: Mapped[Optional[str]] = mapped_column(String(20), index=True, nullable=True)  # miner, pool, system
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)  # Miner ID, Pool ID, or NULL
    period: Mapped[str] = mapped_column(String(20), index=True)  # hourly, daily, weekly, monthly
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)  # Start of period
    value_json: Mapped[dict] = mapped_column(JSON)  # Flexible metric-specific data
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)  # When calculated
    
    __table_args__ = (
        Index('idx_metric_lookup', 'metric_type', 'entity_type', 'entity_id', 'period', 'timestamp'),
    )


class HomeAssistantConfig(Base):
    """Home Assistant integration configuration"""
    __tablename__ = "homeassistant_config"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), default="Home Assistant")
    base_url: Mapped[str] = mapped_column(String(255))  # e.g., http://homeassistant.local:8123
    access_token: Mapped[str] = mapped_column(String(500))  # Long-Lived Access Token
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    keepalive_enabled: Mapped[bool] = mapped_column(Boolean, default=False)  # Monitor HA connectivity and send alerts
    keepalive_last_check: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # Last keepalive check
    keepalive_last_success: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # Last successful check
    keepalive_downtime_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # When downtime began
    keepalive_alerts_sent: Mapped[int] = mapped_column(Integer, default=0)  # Number of alerts sent for current downtime
    last_test: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_test_success: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class HomeAssistantDevice(Base):
    """Home Assistant devices tracked by HMM"""
    __tablename__ = "homeassistant_devices"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)  # e.g., switch.miner_power
    name: Mapped[str] = mapped_column(String(255))
    domain: Mapped[str] = mapped_column(String(50))  # switch, light, climate, etc.
    miner_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)  # Link to miner
    enrolled: Mapped[bool] = mapped_column(Boolean, default=False)  # Can automation control this?
    never_auto_control: Mapped[bool] = mapped_column(Boolean, default=False)  # Safety lock
    current_state: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # on, off, unavailable
    last_state_change: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_off_command_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # Track when OFF command was sent for reconciliation
    capabilities: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MinerBaseline(Base):
    """Statistical baselines for miner performance metrics (per miner, per mode)"""
    __tablename__ = "miner_baselines"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    miner_id: Mapped[int] = mapped_column(Integer, index=True)
    mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # low/med/high/eco/std/turbo/oc/None
    metric_name: Mapped[str] = mapped_column(String(50))  # hashrate_mean, power_mean, w_per_th, temp_mean, reject_rate
    median_value: Mapped[float] = mapped_column(Float)  # Median (robust center)
    mad_value: Mapped[float] = mapped_column(Float)  # Median Absolute Deviation (robust spread)
    sample_count: Mapped[int] = mapped_column(Integer)  # Number of samples used
    window_hours: Mapped[int] = mapped_column(Integer)  # Rolling window size (24h or 168h)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('ix_baseline_miner_mode_metric', 'miner_id', 'mode', 'metric_name'),
    )


class HealthEvent(Base):
    """Anomaly detection events with health scores and reason codes (historical)"""
    __tablename__ = "health_events"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    miner_id: Mapped[int] = mapped_column(Integer, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    health_score: Mapped[float] = mapped_column(Float)  # 0-100
    status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # healthy, warning, critical
    reasons: Mapped[dict] = mapped_column(JSON)  # Structured reason objects
    suggested_actions: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Array of action enums
    anomaly_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Isolation Forest score (0-1)
    mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # Mode at time of check
    
    __table_args__ = (
        Index('ix_health_miner_timestamp', 'miner_id', 'timestamp'),
    )


class MinerHealthCurrent(Base):
    """Current health state per miner (canonical output layer) - one row per miner"""
    __tablename__ = "miner_health_current"
    
    miner_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    health_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-100
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # healthy, warning, critical
    anomaly_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0.0-1.0 from ML
    reasons: Mapped[dict] = mapped_column(JSON, nullable=False)  # Array of structured reason objects
    suggested_actions: Mapped[dict] = mapped_column(JSON, nullable=False)  # Array of action enums
    mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """Get database session"""
    async with AsyncSessionLocal() as session:
        yield session
