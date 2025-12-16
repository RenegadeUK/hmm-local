"""
Database migrations for schema changes
"""
from sqlalchemy import text
from core.database import engine


async def run_migrations():
    """Run all pending migrations"""
    async with engine.begin() as conn:
        # Migration 1: Add last_executed_at and last_execution_context to automation_rules
        try:
            await conn.execute(text("""
                ALTER TABLE automation_rules 
                ADD COLUMN last_executed_at DATETIME
            """))
            print("✓ Added last_executed_at column to automation_rules")
        except Exception:
            # Column already exists
            pass
        
        try:
            await conn.execute(text("""
                ALTER TABLE automation_rules 
                ADD COLUMN last_execution_context JSON
            """))
            print("✓ Added last_execution_context column to automation_rules")
        except Exception:
            # Column already exists
            pass
        
        # Migration 2: Add firmware_version column to miners
        try:
            await conn.execute(text("""
                ALTER TABLE miners 
                ADD COLUMN firmware_version VARCHAR(100)
            """))
            print("✓ Added firmware_version column to miners")
        except Exception:
            # Column already exists
            pass
        
        # Migration 3: Create tuning_profiles table
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS tuning_profiles (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    miner_type VARCHAR(50) NOT NULL,
                    description VARCHAR(500),
                    settings JSON NOT NULL,
                    is_system BOOLEAN DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("✓ Created tuning_profiles table")
        except Exception:
            # Table already exists
            pass
        
        # Migration 4: Create alert_throttle table for notification throttling
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS alert_throttle (
                    id INTEGER PRIMARY KEY,
                    miner_id INTEGER NOT NULL,
                    alert_type VARCHAR(50) NOT NULL,
                    last_sent DATETIME NOT NULL,
                    send_count INTEGER DEFAULT 1,
                    UNIQUE(miner_id, alert_type)
                )
            """))
            print("✓ Created alert_throttle table")
        except Exception:
            # Table already exists
            pass
        
        # Migration 5: Add default alert configs for new alert types
        try:
            await conn.execute(text("""
                INSERT OR IGNORE INTO alert_config (alert_type, enabled, config, created_at, updated_at)
                VALUES 
                    ('pool_failover', 1, '{"cooldown_minutes": 30}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    ('health_prediction', 1, '{"cooldown_minutes": 240}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """))
            print("✓ Added new alert types: pool_failover, health_prediction")
        except Exception:
            # Already exists
            pass
