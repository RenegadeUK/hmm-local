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
        
        # Migration 6: Add luck_percentage column to pool_health
        try:
            await conn.execute(text("""
                ALTER TABLE pool_health 
                ADD COLUMN luck_percentage REAL
            """))
            print("✓ Added luck_percentage column to pool_health")
        except Exception:
            # Column already exists
            pass
        
        # Migration 7: Create pool_strategies table
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS pool_strategies (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    strategy_type VARCHAR(50) NOT NULL,
                    enabled BOOLEAN DEFAULT 0,
                    pool_ids JSON NOT NULL,
                    config JSON NOT NULL,
                    current_pool_index INTEGER DEFAULT 0,
                    last_switch DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("✓ Created pool_strategies table")
        except Exception:
            pass
        
        # Migration 8: Create pool_strategy_logs table
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS pool_strategy_logs (
                    id INTEGER PRIMARY KEY,
                    strategy_id INTEGER NOT NULL,
                    from_pool_id INTEGER,
                    to_pool_id INTEGER,
                    reason VARCHAR(255) NOT NULL,
                    miners_affected INTEGER DEFAULT 0,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("✓ Created pool_strategy_logs table")
        except Exception:
            pass
        
        # Migration 9: Add priority column to pools
        try:
            await conn.execute(text("""
                ALTER TABLE pools 
                ADD COLUMN priority INTEGER DEFAULT 0
            """))
            print("✓ Added priority column to pools")
        except Exception:
            # Column already exists
            pass
        
        # Migration 10: Create miner_pool_slots table for Avalon Nano pool caching
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS miner_pool_slots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    miner_id INTEGER NOT NULL,
                    slot_number INTEGER NOT NULL,
                    pool_id INTEGER,
                    pool_url VARCHAR(255) NOT NULL,
                    pool_port INTEGER NOT NULL,
                    pool_user VARCHAR(255) NOT NULL,
                    is_active BOOLEAN DEFAULT 0,
                    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(miner_id, slot_number)
                )
            """))
            print("✓ Created miner_pool_slots table")
        except Exception:
            pass
        
        # Migration 11: Add miner_ids column to pool_strategies
        try:
            await conn.execute(text("""
                ALTER TABLE pool_strategies 
                ADD COLUMN miner_ids JSON DEFAULT '[]'
            """))
            print("✓ Added miner_ids column to pool_strategies")
        except Exception:
            # Column already exists
            pass
        
        # Migration 12: Create audit_logs table
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    user VARCHAR(100) DEFAULT 'system' NOT NULL,
                    action VARCHAR(50) NOT NULL,
                    resource_type VARCHAR(50) NOT NULL,
                    resource_id INTEGER,
                    resource_name VARCHAR(255),
                    changes JSON,
                    ip_address VARCHAR(45),
                    user_agent VARCHAR(255),
                    status VARCHAR(20) DEFAULT 'success' NOT NULL,
                    error_message VARCHAR(500)
                )
            """))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_logs_resource_type ON audit_logs(resource_type)"))
            print("✓ Created audit_logs table")
        except Exception:
            pass
