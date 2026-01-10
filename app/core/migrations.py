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
        
        # Migration 5: Removed (legacy alert types no longer used)
        # pool_failover and health_prediction alert types removed
        
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
        
        # Migration 13: Create custom_dashboards and dashboard_widgets tables
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS custom_dashboards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(100) NOT NULL,
                    description VARCHAR(500),
                    layout JSON NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("✓ Created custom_dashboards table")
        except Exception:
            pass
        
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS dashboard_widgets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dashboard_id INTEGER NOT NULL,
                    widget_type VARCHAR(50) NOT NULL,
                    config JSON NOT NULL,
                    position JSON NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (dashboard_id) REFERENCES custom_dashboards(id) ON DELETE CASCADE
                )
            """))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_dashboard_widgets_dashboard_id ON dashboard_widgets(dashboard_id)"))
            print("✓ Created dashboard_widgets table")
        except Exception:
            pass
        
        # Migration 14: Create cloud backup tables
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS cloud_backup_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider VARCHAR(50) NOT NULL,
                    enabled BOOLEAN DEFAULT 0,
                    config JSON NOT NULL,
                    schedule_enabled BOOLEAN DEFAULT 0,
                    schedule_frequency VARCHAR(20) DEFAULT 'daily',
                    schedule_time VARCHAR(5),
                    schedule_day INTEGER,
                    backup_type VARCHAR(20) DEFAULT 'standard',
                    retention_days INTEGER DEFAULT 30,
                    last_backup DATETIME,
                    last_backup_status VARCHAR(20),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("✓ Created cloud_backup_configs table")
        except Exception:
            pass
        
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS cloud_backup_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider VARCHAR(50) NOT NULL,
                    backup_type VARCHAR(20) NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    error_message VARCHAR(500),
                    file_size INTEGER,
                    duration REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_cloud_backup_logs_timestamp ON cloud_backup_logs(timestamp)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_cloud_backup_logs_provider ON cloud_backup_logs(provider)"))
            print("✓ Created cloud_backup_logs table")
        except Exception:
            pass
        
        # Migration 15: Add hashrate_unit column to telemetry for CPU miners (XMRig)
        try:
            await conn.execute(text("""
                ALTER TABLE telemetry 
                ADD COLUMN hashrate_unit VARCHAR(10) DEFAULT 'GH/s'
            """))
            print("✓ Added hashrate_unit column to telemetry (default: GH/s for ASIC miners, KH/s for CPU)")
        except Exception:
            # Column already exists
            pass
        
        # Migration 16: Create daily_miner_stats table for long-term analytics
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS daily_miner_stats (
                    id INTEGER PRIMARY KEY,
                    miner_id INTEGER NOT NULL,
                    date DATETIME NOT NULL,
                    avg_hashrate FLOAT,
                    min_hashrate FLOAT,
                    max_hashrate FLOAT,
                    hashrate_unit VARCHAR(10) DEFAULT 'GH/s',
                    avg_temperature FLOAT,
                    max_temperature FLOAT,
                    avg_power FLOAT,
                    total_kwh FLOAT,
                    uptime_percent FLOAT DEFAULT 0.0,
                    offline_minutes INTEGER DEFAULT 0,
                    total_shares_accepted INTEGER DEFAULT 0,
                    total_shares_rejected INTEGER DEFAULT 0,
                    reject_rate_percent FLOAT DEFAULT 0.0,
                    energy_cost_gbp FLOAT DEFAULT 0.0,
                    earnings_gbp FLOAT DEFAULT 0.0,
                    profit_gbp FLOAT DEFAULT 0.0,
                    data_points INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_daily_miner_stats_miner_id ON daily_miner_stats(miner_id)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_daily_miner_stats_date ON daily_miner_stats(date)
            """))
            await conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_miner_stats_unique 
                ON daily_miner_stats(miner_id, date)
            """))
            print("✓ Created daily_miner_stats table with indexes")
        except Exception:
            pass
        
        # Migration 17: Create daily_pool_stats table
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS daily_pool_stats (
                    id INTEGER PRIMARY KEY,
                    pool_id INTEGER NOT NULL,
                    date DATETIME NOT NULL,
                    blocks_found INTEGER DEFAULT 0,
                    total_shares_submitted INTEGER DEFAULT 0,
                    avg_luck_percent FLOAT,
                    avg_latency_ms FLOAT,
                    avg_health_score FLOAT,
                    uptime_percent FLOAT DEFAULT 100.0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_daily_pool_stats_pool_id ON daily_pool_stats(pool_id)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_daily_pool_stats_date ON daily_pool_stats(date)
            """))
            await conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_pool_stats_unique 
                ON daily_pool_stats(pool_id, date)
            """))
            print("✓ Created daily_pool_stats table with indexes")
        except Exception:
            pass
        
        # Migration 18: Create monthly_miner_stats table
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS monthly_miner_stats (
                    id INTEGER PRIMARY KEY,
                    miner_id INTEGER NOT NULL,
                    year INTEGER NOT NULL,
                    month INTEGER NOT NULL,
                    avg_hashrate FLOAT,
                    hashrate_unit VARCHAR(10),
                    total_kwh FLOAT,
                    uptime_percent FLOAT DEFAULT 0.0,
                    total_shares_accepted INTEGER DEFAULT 0,
                    total_shares_rejected INTEGER DEFAULT 0,
                    reject_rate_percent FLOAT DEFAULT 0.0,
                    total_energy_cost_gbp FLOAT DEFAULT 0.0,
                    total_earnings_gbp FLOAT DEFAULT 0.0,
                    total_profit_gbp FLOAT DEFAULT 0.0,
                    days_active INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_monthly_miner_stats_miner_id ON monthly_miner_stats(miner_id)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_monthly_miner_stats_year ON monthly_miner_stats(year)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_monthly_miner_stats_month ON monthly_miner_stats(month)
            """))
            await conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_monthly_miner_stats_unique 
                ON monthly_miner_stats(miner_id, year, month)
            """))
            print("✓ Created monthly_miner_stats table with indexes")
        except Exception:
            pass
        
        # Migration 19: Add last_mode_change column to miners for tracking mode changes
        try:
            await conn.execute(text("""
                ALTER TABLE miners 
                ADD COLUMN last_mode_change DATETIME
            """))
            print("✓ Added last_mode_change column to miners")
        except Exception:
            # Column already exists
            pass
        
        # Migration 20: Create p2pool_transactions table for Monero wallet tracking
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS p2pool_transactions (
                    id INTEGER PRIMARY KEY,
                    wallet_address VARCHAR(95) NOT NULL,
                    tx_hash VARCHAR(64) NOT NULL UNIQUE,
                    amount_xmr REAL NOT NULL,
                    block_height INTEGER NOT NULL,
                    confirmations INTEGER DEFAULT 0,
                    timestamp DATETIME NOT NULL,
                    unlock_time INTEGER DEFAULT 0,
                    is_confirmed BOOLEAN DEFAULT 0,
                    created_at DATETIME DEFAULT (datetime('now'))
                );
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_p2pool_wallet 
                ON p2pool_transactions(wallet_address);
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_p2pool_timestamp 
                ON p2pool_transactions(timestamp);
            """))
            print("✓ Created p2pool_transactions table with indexes")
        except Exception:
            pass

        
        # Migration: Add network_difficulty columns to pools table for CKPool
        try:
            await conn.execute(text("""
                ALTER TABLE pools 
                ADD COLUMN network_difficulty FLOAT
            """))
            print("✓ Added network_difficulty column to pools")
        except Exception:
            pass
        
        try:
            await conn.execute(text("""
                ALTER TABLE pools 
                ADD COLUMN network_difficulty_updated_at DATETIME
            """))
            print("✓ Added network_difficulty_updated_at column to pools")
        except Exception:
            pass
        
        # Migration: Add best_share tracking columns to pools table for CKPool
        try:
            await conn.execute(text("""
                ALTER TABLE pools 
                ADD COLUMN best_share FLOAT
            """))
            print("✓ Added best_share column to pools")
        except Exception:
            pass
        
        try:
            await conn.execute(text("""
                ALTER TABLE pools 
                ADD COLUMN best_share_updated_at DATETIME
            """))
            print("✓ Added best_share_updated_at column to pools")
        except Exception:
            pass
        
        # Migration 19: Add indexes to telemetry table for performance optimization
        # These indexes eliminate N+1 query problems and speed up common query patterns
        try:
            # Add single-column index on miner_id (for filtering by miner)
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_telemetry_miner_id 
                ON telemetry(miner_id)
            """))
            print("✓ Added index on telemetry.miner_id")
        except Exception as e:
            print(f"⚠️  Index on telemetry.miner_id may already exist: {e}")
        
        try:
            # Add composite index on (miner_id, timestamp) for efficient latest telemetry queries
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_telemetry_miner_timestamp 
                ON telemetry(miner_id, timestamp)
            """))
            print("✓ Added composite index on telemetry(miner_id, timestamp)")
        except Exception as e:
            print(f"⚠️  Composite index on telemetry(miner_id, timestamp) may already exist: {e}")
        
        # Migration 20: Add manual_power_watts to miners for XMRig/NMMiner power tracking (2026-01-02)
        try:
            await conn.execute(text("""
                ALTER TABLE miners 
                ADD COLUMN manual_power_watts INTEGER
            """))
            print("✓ Added manual_power_watts column to miners")
        except Exception:
            # Column already exists
            pass
        
        # Migration 21: Create ckpool_block_metrics table for 12-month analytics (2026-01-02)
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ckpool_block_metrics (
                    id INTEGER PRIMARY KEY,
                    pool_id INTEGER NOT NULL,
                    coin VARCHAR(10) NOT NULL,
                    timestamp DATETIME NOT NULL,
                    block_height INTEGER NOT NULL,
                    block_hash VARCHAR(100) NOT NULL,
                    effort_percent FLOAT DEFAULT 100.0,
                    time_to_block_seconds INTEGER,
                    confirmed_reward_coins FLOAT
                )
            """))
            print("✓ Created ckpool_block_metrics table")
        except Exception as e:
            print(f"⚠️  ckpool_block_metrics table may already exist: {e}")
        
        try:
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_ckpool_metrics_pool 
                ON ckpool_block_metrics(pool_id)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_ckpool_metrics_coin 
                ON ckpool_block_metrics(coin)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_ckpool_metrics_timestamp 
                ON ckpool_block_metrics(timestamp)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_ckpool_metrics_hash 
                ON ckpool_block_metrics(block_hash)
            """))
            print("✓ Created indexes on ckpool_block_metrics")
        except Exception as e:
            print(f"⚠️  Indexes on ckpool_block_metrics may already exist: {e}")
        
        # Migration: Create ckpool_hashrate_snapshots table
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ckpool_hashrate_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pool_id INTEGER NOT NULL,
                    coin VARCHAR(10) NOT NULL,
                    timestamp DATETIME NOT NULL,
                    hashrate_gh REAL NOT NULL,
                    workers INTEGER NOT NULL
                )
            """))
            print("✓ Created ckpool_hashrate_snapshots table")
        except Exception:
            pass
        
        # Migration: Add indexes to ckpool_hashrate_snapshots
        try:
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_ckpool_hashrate_pool_id ON ckpool_hashrate_snapshots(pool_id)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_ckpool_hashrate_coin ON ckpool_hashrate_snapshots(coin)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_ckpool_hashrate_timestamp ON ckpool_hashrate_snapshots(timestamp)
            """))
            print("✓ Created indexes on ckpool_hashrate_snapshots")
        except Exception:
            pass
        
        # Migration: Create monero_solo_settings table
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS monero_solo_settings (
                    id INTEGER PRIMARY KEY,
                    enabled BOOLEAN DEFAULT 0,
                    wallet_rpc_ip VARCHAR(45),
                    wallet_rpc_port INTEGER DEFAULT 18083,
                    wallet_rpc_user VARCHAR(255),
                    wallet_rpc_pass VARCHAR(255),
                    wallet_address VARCHAR(255),
                    last_sync DATETIME,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
            """))
            print("✓ Created monero_solo_settings table")
        except Exception:
            pass
        
        # Migration: Create monero_solo_effort table
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS monero_solo_effort (
                    id INTEGER PRIMARY KEY,
                    pool_id INTEGER NOT NULL,
                    total_hashes INTEGER DEFAULT 0,
                    round_start_time DATETIME NOT NULL,
                    last_block_height INTEGER DEFAULT 0,
                    last_reset DATETIME,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_monero_solo_effort_pool_id ON monero_solo_effort(pool_id)
            """))
            print("✓ Created monero_solo_effort table")
        except Exception:
            pass
        
        # Migration: Create monero_blocks table
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS monero_blocks (
                    id INTEGER PRIMARY KEY,
                    block_height INTEGER UNIQUE NOT NULL,
                    block_hash VARCHAR(64) NOT NULL,
                    timestamp DATETIME NOT NULL,
                    reward_atomic INTEGER NOT NULL,
                    reward_xmr REAL NOT NULL,
                    effort_percent REAL NOT NULL,
                    total_hashes INTEGER NOT NULL,
                    difficulty INTEGER NOT NULL,
                    pool_id INTEGER,
                    created_at DATETIME NOT NULL
                )
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_monero_blocks_height ON monero_blocks(block_height)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_monero_blocks_timestamp ON monero_blocks(timestamp)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_monero_blocks_pool_id ON monero_blocks(pool_id)
            """))
            print("✓ Created monero_blocks table")
        except Exception:
            pass
        
        # Migration: Create monero_wallet_transactions table
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS monero_wallet_transactions (
                    id INTEGER PRIMARY KEY,
                    tx_hash VARCHAR(64) UNIQUE NOT NULL,
                    block_height INTEGER NOT NULL,
                    amount_atomic INTEGER NOT NULL,
                    amount_xmr REAL NOT NULL,
                    timestamp DATETIME NOT NULL,
                    tx_type VARCHAR(20) NOT NULL,
                    is_block_reward BOOLEAN DEFAULT 0,
                    created_at DATETIME NOT NULL
                )
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_monero_wallet_tx_hash ON monero_wallet_transactions(tx_hash)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_monero_wallet_tx_height ON monero_wallet_transactions(block_height)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_monero_wallet_tx_timestamp ON monero_wallet_transactions(timestamp)
            """))
            print("✓ Created monero_wallet_transactions table")
        except Exception:
            pass
        
        # Migration: Create monero_hashrate_snapshots table
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS monero_hashrate_snapshots (
                    id INTEGER PRIMARY KEY,
                    timestamp DATETIME NOT NULL,
                    total_hashrate REAL NOT NULL,
                    worker_count INTEGER NOT NULL,
                    network_difficulty INTEGER NOT NULL,
                    current_effort REAL NOT NULL,
                    created_at DATETIME NOT NULL
                )
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_monero_hashrate_timestamp ON monero_hashrate_snapshots(timestamp)
            """))
            print("✓ Created monero_hashrate_snapshots table")
        except Exception:
            pass
        
        # Migration: Add pool_id to monero_solo_settings
        try:
            await conn.execute(text("""
                ALTER TABLE monero_solo_settings 
                ADD COLUMN pool_id INTEGER
            """))
            print("✓ Added pool_id column to monero_solo_settings")
        except Exception as e:
            # Column already exists - that's ok
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                pass  # Column exists, that's fine
            else:
                # Unexpected error - log it
                print(f"⚠️  Could not add pool_id to monero_solo_settings: {e}")
                raise  # Re-raise unexpected errors
        
        # Migration: Add last_block_check_height to monero_solo_settings
        try:
            await conn.execute(text("""
                ALTER TABLE monero_solo_settings 
                ADD COLUMN last_block_check_height INTEGER DEFAULT 0
            """))
            print("✓ Added last_block_check_height column to monero_solo_settings")
        except Exception as e:
            # Column already exists - that's ok
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                pass  # Column exists, that's fine
            else:
                # Unexpected error - log it
                print(f"⚠️  Could not add last_block_check_height to monero_solo_settings: {e}")
                raise  # Re-raise unexpected errors
        
        # Migration: Create agile_strategy table
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS agile_strategy (
                    id INTEGER PRIMARY KEY,
                    enabled BOOLEAN DEFAULT 0,
                    current_price_band VARCHAR(20),
                    hysteresis_counter INTEGER DEFAULT 0,
                    last_action_time DATETIME,
                    last_price_checked REAL,
                    state_data JSON,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("✓ Created agile_strategy table")
        except Exception:
            pass
        
        # Migration: Create miner_strategy table
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS miner_strategy (
                    id INTEGER PRIMARY KEY,
                    miner_id INTEGER NOT NULL,
                    strategy_enabled BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            await conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS ix_miner_strategy_unique ON miner_strategy(miner_id)
            """))
            print("✓ Created miner_strategy table")
        except Exception:
            pass
        
        # Migration: Create high_diff_shares table
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS high_diff_shares (
                    id INTEGER PRIMARY KEY,
                    miner_id INTEGER NOT NULL,
                    miner_name VARCHAR(100) NOT NULL,
                    miner_type VARCHAR(50) NOT NULL,
                    coin VARCHAR(10) NOT NULL,
                    pool_name VARCHAR(100) NOT NULL,
                    difficulty FLOAT NOT NULL,
                    network_difficulty FLOAT,
                    was_block_solve BOOLEAN DEFAULT 0,
                    hashrate FLOAT,
                    hashrate_unit VARCHAR(10) DEFAULT 'GH/s',
                    miner_mode VARCHAR(20),
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_high_diff_miner_id ON high_diff_shares(miner_id)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_high_diff_difficulty ON high_diff_shares(difficulty)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_high_diff_timestamp ON high_diff_shares(timestamp)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_difficulty_timestamp ON high_diff_shares(difficulty, timestamp)
            """))
            print("✓ Created high_diff_shares table")
        except Exception:
            pass
        
        # Migration: Create blocks_found table
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS blocks_found (
                    id INTEGER PRIMARY KEY,
                    miner_id INTEGER NOT NULL,
                    miner_name VARCHAR(100) NOT NULL,
                    miner_type VARCHAR(50) NOT NULL,
                    coin VARCHAR(10) NOT NULL,
                    pool_name VARCHAR(100) NOT NULL,
                    difficulty FLOAT NOT NULL,
                    network_difficulty FLOAT NOT NULL,
                    block_height INTEGER,
                    block_reward FLOAT,
                    hashrate FLOAT,
                    hashrate_unit VARCHAR(10) DEFAULT 'GH/s',
                    miner_mode VARCHAR(20),
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_blocks_found_miner_id ON blocks_found(miner_id)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_blocks_found_coin ON blocks_found(coin)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_blocks_found_timestamp ON blocks_found(timestamp)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_miner_coin ON blocks_found(miner_id, coin)
            """))
            print("✓ Created blocks_found table")
        except Exception:
            pass
        
        # Migration 24: Remove obsolete alert types
        try:
            await conn.execute(text("""
                DELETE FROM alert_config 
                WHERE alert_type IN (
                    'miner_offline', 
                    'high_reject_rate', 
                    'pool_failure', 
                    'low_hashrate', 
                    'pool_failover', 
                    'health_prediction'
                )
            """))
            await conn.execute(text("""
                DELETE FROM alert_throttle 
                WHERE alert_type IN (
                    'miner_offline', 
                    'high_reject_rate', 
                    'pool_failure', 
                    'low_hashrate', 
                    'pool_failover', 
                    'health_prediction'
                )
            """))
            print("✓ Removed obsolete alert types")
        except Exception:
            pass        
        # Migration: Drop CKPool tables (decommissioned 2026-01-03)
        try:
            await conn.execute(text("DROP TABLE IF EXISTS ckpool_hashrate_snapshots"))
            await conn.execute(text("DROP TABLE IF EXISTS ckpool_block_metrics"))
            await conn.execute(text("DROP TABLE IF EXISTS ckpool_blocks"))
            print("✓ Dropped CKPool tables (decommissioned)")
        except Exception as e:
            print(f"⚠️  Failed to drop CKPool tables: {e}")
        
        # Migration: Drop monero_wallet_transactions table (decommissioned 2026-01-07)
        try:
            await conn.execute(text("DROP TABLE IF EXISTS monero_wallet_transactions"))
            print("✓ Dropped monero_wallet_transactions table (decommissioned)")
        except Exception as e:
            print(f"⚠️  Failed to drop monero_wallet_transactions table: {e}")
        
        # Migration: Ensure AgileStrategyBand table exists and initialize default bands
        try:
            # Table will be created by init_db(), but we need to populate it for existing strategies
            from sqlalchemy.ext.asyncio import AsyncSession
            from core.database import AsyncSessionLocal, AgileStrategy
            from core.agile_bands import ensure_strategy_bands
            
            async with AsyncSessionLocal() as session:
                from sqlalchemy import select
                result = await session.execute(select(AgileStrategy))
                strategies = result.scalars().all()
                
                for strategy in strategies:
                    await ensure_strategy_bands(session, strategy.id)
                
                if strategies:
                    print(f"✓ Initialized/verified bands for {len(strategies)} agile strategies")
        except Exception as e:
            print(f"⚠️  Failed to initialize agile strategy bands: {e}")

