"""
SQLite database setup and models
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Float, DateTime, JSON, Boolean
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
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Telemetry(Base):
    """Miner telemetry data"""
    __tablename__ = "telemetry"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    miner_id: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    hashrate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    power_watts: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    shares_accepted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shares_rejected: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pool_in_use: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Additional miner-specific data


class EnergyPrice(Base):
    """Octopus Agile energy pricing"""
    __tablename__ = "energy_prices"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    region: Mapped[str] = mapped_column(String(1), index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime, index=True)
    valid_to: Mapped[datetime] = mapped_column(DateTime)
    price_pence: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    message: Mapped[str] = mapped_column(String(500))
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


class HealthScore(Base):
    """Miner health scores over time"""
    __tablename__ = "health_scores"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    miner_id: Mapped[int] = mapped_column(Integer, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    overall_score: Mapped[float] = mapped_column(Float)  # 0-100
    uptime_score: Mapped[float] = mapped_column(Float)  # 0-100
    temperature_score: Mapped[float] = mapped_column(Float)  # 0-100
    hashrate_score: Mapped[float] = mapped_column(Float)  # 0-100
    reject_rate_score: Mapped[float] = mapped_column(Float)  # 0-100
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


# Database engine and session
DATABASE_URL = f"sqlite+aiosqlite:///{settings.DB_PATH}"
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """Get database session"""
    async with AsyncSessionLocal() as session:
        yield session
