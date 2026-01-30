"""
PostgreSQL-specific optimizations (partitioning, materialized views, indexes)
These features only apply when using PostgreSQL and are safely skipped for SQLite.
"""
import logging
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def is_postgresql(session: AsyncSession) -> bool:
    """Check if current database is PostgreSQL"""
    from core.database import engine
    return 'postgresql' in str(engine.url)


async def setup_telemetry_partitioning(session: AsyncSession) -> None:
    """
    Set up monthly partitioning for telemetry table.
    PostgreSQL only - safely skipped for SQLite.
    """
    if not await is_postgresql(session):
        logger.info("Skipping partitioning (SQLite database)")
        return
    
    try:
        logger.info("Setting up telemetry partitioning...")
        
        # Check if table is already partitioned
        check_query = text("""
            SELECT COUNT(*) 
            FROM pg_partitioned_table 
            WHERE partrelid = 'telemetry'::regclass
        """)
        result = await session.execute(check_query)
        is_partitioned = result.scalar() > 0
        
        if is_partitioned:
            logger.info("✅ Telemetry table already partitioned")
            return
        
        # Note: Cannot convert existing table to partitioned.
        # This would need to be done during initial migration.
        # For now, just log that it should be done manually.
        logger.warning("⚠️ Telemetry table not partitioned. Run manual migration:")
        logger.warning("   1. Rename: ALTER TABLE telemetry RENAME TO telemetry_old;")
        logger.warning("   2. Create partitioned: CREATE TABLE telemetry (...) PARTITION BY RANGE (timestamp);")
        logger.warning("   3. Create partitions and migrate data")
        
    except Exception as e:
        logger.error(f"Error setting up partitioning: {e}")


async def create_monthly_partition(session: AsyncSession, year: int, month: int) -> bool:
    """
    Create a monthly partition for telemetry table.
    Returns True if partition was created, False if it already exists.
    """
    if not await is_postgresql(session):
        return False
    
    try:
        partition_name = f"telemetry_{year}_{month:02d}"
        
        # Check if partition exists
        check_query = text("""
            SELECT COUNT(*) 
            FROM pg_tables 
            WHERE tablename = :partition_name
        """)
        result = await session.execute(check_query, {"partition_name": partition_name})
        exists = result.scalar() > 0
        
        if exists:
            logger.debug(f"Partition {partition_name} already exists")
            return False
        
        # Calculate partition boundaries
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
        
        # Create partition
        create_query = text(f"""
            CREATE TABLE IF NOT EXISTS {partition_name} 
            PARTITION OF telemetry
            FOR VALUES FROM ('{start_date.isoformat()}') TO ('{end_date.isoformat()}')
        """)
        await session.execute(create_query)
        await session.commit()
        
        logger.info(f"✅ Created partition: {partition_name} ({start_date.date()} to {end_date.date()})")
        return True
        
    except Exception as e:
        logger.error(f"Error creating partition for {year}-{month:02d}: {e}")
        await session.rollback()
        return False


async def ensure_future_partitions(session: AsyncSession) -> None:
    """
    Ensure partitions exist for current month, next month, and month after.
    Called by scheduler monthly.
    """
    if not await is_postgresql(session):
        return
    
    try:
        now = datetime.utcnow()
        
        # Create partitions for current, next, and month after
        for offset in [0, 1, 2]:
            target_date = now + timedelta(days=30 * offset)
            await create_monthly_partition(session, target_date.year, target_date.month)
        
    except Exception as e:
        logger.error(f"Error ensuring future partitions: {e}")


async def create_dashboard_materialized_view(session: AsyncSession) -> None:
    """
    Create materialized view for dashboard aggregations.
    Pre-computes expensive queries for instant dashboard loading.
    """
    if not await is_postgresql(session):
        logger.info("Skipping materialized view (SQLite database)")
        return
    
    try:
        logger.info("Creating dashboard materialized view...")
        
        # Drop if exists
        await session.execute(text("DROP MATERIALIZED VIEW IF EXISTS dashboard_stats_mv"))
        
        # Create materialized view with latest telemetry stats per miner
        create_mv_query = text("""
            CREATE MATERIALIZED VIEW dashboard_stats_mv AS
            WITH latest_telemetry AS (
                SELECT DISTINCT ON (miner_id)
                    miner_id,
                    timestamp,
                    hashrate,
                    hashrate_unit,
                    temperature,
                    power_watts,
                    shares_accepted,
                    shares_rejected,
                    mode
                FROM telemetry
                ORDER BY miner_id, timestamp DESC
            ),
            hourly_stats AS (
                SELECT 
                    miner_id,
                    COUNT(*) as telemetry_count_1h,
                    AVG(hashrate) as avg_hashrate_1h,
                    AVG(temperature) as avg_temp_1h,
                    SUM(shares_accepted) as shares_1h,
                    SUM(shares_rejected) as rejects_1h
                FROM telemetry
                WHERE timestamp >= NOW() - INTERVAL '1 hour'
                GROUP BY miner_id
            ),
            daily_stats AS (
                SELECT 
                    miner_id,
                    AVG(hashrate) as avg_hashrate_24h,
                    SUM(energy_cost) as energy_cost_24h
                FROM telemetry
                WHERE timestamp >= NOW() - INTERVAL '24 hours'
                GROUP BY miner_id
            )
            SELECT 
                m.id as miner_id,
                m.name as miner_name,
                m.miner_type,
                m.enabled,
                m.current_mode,
                lt.timestamp as last_seen,
                lt.hashrate as current_hashrate,
                lt.hashrate_unit,
                lt.temperature as current_temperature,
                lt.power_watts as current_power,
                lt.shares_accepted as total_shares,
                lt.shares_rejected as total_rejects,
                hs.avg_hashrate_1h,
                hs.avg_temp_1h,
                hs.shares_1h,
                hs.rejects_1h,
                CASE 
                    WHEN hs.shares_1h + hs.rejects_1h > 0 
                    THEN (hs.rejects_1h::float / (hs.shares_1h + hs.rejects_1h) * 100)
                    ELSE 0 
                END as reject_rate_1h,
                ds.avg_hashrate_24h,
                ds.energy_cost_24h,
                EXTRACT(EPOCH FROM (NOW() - lt.timestamp)) as seconds_since_last_telemetry
            FROM miners m
            LEFT JOIN latest_telemetry lt ON m.id = lt.miner_id
            LEFT JOIN hourly_stats hs ON m.id = hs.miner_id
            LEFT JOIN daily_stats ds ON m.id = ds.miner_id
            WHERE m.enabled = true
        """)
        
        await session.execute(create_mv_query)
        
        # Create indexes on materialized view
        await session.execute(text("CREATE INDEX idx_dashboard_mv_miner_id ON dashboard_stats_mv(miner_id)"))
        await session.execute(text("CREATE INDEX idx_dashboard_mv_last_seen ON dashboard_stats_mv(last_seen)"))
        
        await session.commit()
        logger.info("✅ Created dashboard_stats_mv with indexes")
        
    except Exception as e:
        logger.error(f"Error creating materialized view: {e}")
        await session.rollback()


async def refresh_dashboard_materialized_view(session: AsyncSession) -> None:
    """
    Refresh dashboard materialized view.
    Should be called by scheduler every 5 minutes.
    """
    if not await is_postgresql(session):
        return
    
    try:
        await session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY dashboard_stats_mv"))
        await session.commit()
        logger.debug("Refreshed dashboard_stats_mv")
    except Exception as e:
        logger.error(f"Error refreshing materialized view: {e}")
        await session.rollback()


async def create_json_indexes(session: AsyncSession) -> None:
    """
    Create GIN indexes on JSON columns for faster searches.
    PostgreSQL only - uses GIN (Generalized Inverted Index).
    """
    if not await is_postgresql(session):
        logger.info("Skipping JSON indexes (SQLite database)")
        return
    
    try:
        logger.info("Creating JSON GIN indexes...")
        
        indexes = [
            # Telemetry data column (contains miner-specific extra data)
            ("CREATE INDEX IF NOT EXISTS idx_telemetry_data_gin ON telemetry USING GIN (data)", "telemetry.data"),
            
            # Miner config column
            ("CREATE INDEX IF NOT EXISTS idx_miner_config_gin ON miners USING GIN (config)", "miners.config"),
            
            # Automation rule conditions/actions
            ("CREATE INDEX IF NOT EXISTS idx_automation_condition_gin ON automation_rules USING GIN (condition)", "automation_rules.condition"),
            ("CREATE INDEX IF NOT EXISTS idx_automation_action_gin ON automation_rules USING GIN (action)", "automation_rules.action"),
            
            # Health events reasons
            ("CREATE INDEX IF NOT EXISTS idx_health_events_reasons_gin ON health_events USING GIN (reasons)", "health_events.reasons"),
        ]
        
        for query, description in indexes:
            try:
                await session.execute(text(query))
                logger.info(f"✅ Created GIN index: {description}")
            except Exception as e:
                logger.warning(f"Could not create index {description}: {e}")
        
        await session.commit()
        logger.info("JSON indexing complete")
        
    except Exception as e:
        logger.error(f"Error creating JSON indexes: {e}")
        await session.rollback()


async def create_partial_indexes(session: AsyncSession) -> None:
    """
    Create partial indexes for common query patterns.
    Only indexes rows that match specific conditions.
    """
    if not await is_postgresql(session):
        logger.info("Skipping partial indexes (SQLite database)")
        return
    
    try:
        logger.info("Creating partial indexes...")
        
        indexes = [
            # Only index enabled miners (most queries filter on this)
            ("CREATE INDEX IF NOT EXISTS idx_miners_enabled ON miners(id) WHERE enabled = true", 
             "miners.enabled=true"),
            
            # Only index recent telemetry (most queries use last 24h-7d)
            ("CREATE INDEX IF NOT EXISTS idx_telemetry_recent ON telemetry(miner_id, timestamp) WHERE timestamp >= NOW() - INTERVAL '7 days'",
             "telemetry recent (7 days)"),
            
            # Only index active automation rules
            ("CREATE INDEX IF NOT EXISTS idx_automation_active ON automation_rules(id) WHERE enabled = true",
             "automation_rules.enabled=true"),
            
            # Only index recent pool health checks
            ("CREATE INDEX IF NOT EXISTS idx_pool_health_recent ON pool_health(pool_id, timestamp) WHERE timestamp >= NOW() - INTERVAL '30 days'",
             "pool_health recent (30 days)"),
        ]
        
        for query, description in indexes:
            try:
                await session.execute(text(query))
                logger.info(f"✅ Created partial index: {description}")
            except Exception as e:
                logger.warning(f"Could not create partial index {description}: {e}")
        
        await session.commit()
        logger.info("Partial indexing complete")
        
    except Exception as e:
        logger.error(f"Error creating partial indexes: {e}")
        await session.rollback()


async def create_covering_indexes(session: AsyncSession) -> None:
    """
    Create covering indexes (INCLUDE columns) for index-only scans.
    Avoids table lookups by including all needed columns in the index.
    """
    if not await is_postgresql(session):
        logger.info("Skipping covering indexes (SQLite database)")
        return
    
    try:
        logger.info("Creating covering indexes...")
        
        indexes = [
            # Dashboard query: needs miner_id + timestamp + all display columns
            ("""CREATE INDEX IF NOT EXISTS idx_telemetry_dashboard 
                ON telemetry(miner_id, timestamp DESC) 
                INCLUDE (hashrate, temperature, power_watts, shares_accepted, shares_rejected, mode)""",
             "telemetry dashboard covering index"),
            
            # Miner list query: needs enabled + all display columns
            ("""CREATE INDEX IF NOT EXISTS idx_miners_list 
                ON miners(enabled) 
                INCLUDE (name, miner_type, current_mode, ip_address)""",
             "miners list covering index"),
        ]
        
        for query, description in indexes:
            try:
                await session.execute(text(query))
                logger.info(f"✅ Created covering index: {description}")
            except Exception as e:
                logger.warning(f"Could not create covering index {description}: {e}")
        
        await session.commit()
        logger.info("Covering indexes complete")
        
    except Exception as e:
        logger.error(f"Error creating covering indexes: {e}")
        await session.rollback()


async def setup_notify_triggers(session: AsyncSession) -> None:
    """
    Create PostgreSQL NOTIFY triggers for real-time updates.
    Sends notifications when telemetry/miner state changes.
    """
    if not await is_postgresql(session):
        logger.info("Skipping NOTIFY triggers (SQLite database)")
        return
    
    try:
        logger.info("Creating NOTIFY triggers...")
        
        # Telemetry insert trigger
        await session.execute(text("""
            CREATE OR REPLACE FUNCTION notify_telemetry_change()
            RETURNS trigger AS $$
            BEGIN
                PERFORM pg_notify('telemetry_update', json_build_object(
                    'miner_id', NEW.miner_id,
                    'timestamp', NEW.timestamp,
                    'hashrate', NEW.hashrate,
                    'temperature', NEW.temperature
                )::text);
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """))
        
        await session.execute(text("""
            DROP TRIGGER IF EXISTS telemetry_notify_trigger ON telemetry
        """))
        
        await session.execute(text("""
            CREATE TRIGGER telemetry_notify_trigger
            AFTER INSERT ON telemetry
            FOR EACH ROW
            EXECUTE FUNCTION notify_telemetry_change()
        """))
        
        # Miner state change trigger
        await session.execute(text("""
            CREATE OR REPLACE FUNCTION notify_miner_change()
            RETURNS trigger AS $$
            BEGIN
                IF (TG_OP = 'UPDATE' AND (
                    OLD.enabled != NEW.enabled OR 
                    OLD.current_mode != NEW.current_mode
                )) OR TG_OP = 'INSERT' THEN
                    PERFORM pg_notify('miner_update', json_build_object(
                        'miner_id', NEW.id,
                        'name', NEW.name,
                        'enabled', NEW.enabled,
                        'current_mode', NEW.current_mode
                    )::text);
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """))
        
        await session.execute(text("""
            DROP TRIGGER IF EXISTS miner_notify_trigger ON miners
        """))
        
        await session.execute(text("""
            CREATE TRIGGER miner_notify_trigger
            AFTER INSERT OR UPDATE ON miners
            FOR EACH ROW
            EXECUTE FUNCTION notify_miner_change()
        """))
        
        await session.commit()
        logger.info("✅ Created NOTIFY triggers for telemetry and miners")
        
    except Exception as e:
        logger.error(f"Error creating NOTIFY triggers: {e}")
        await session.rollback()


async def initialize_postgres_optimizations(session: AsyncSession) -> None:
    """
    Initialize all PostgreSQL optimizations.
    Called once at startup if using PostgreSQL.
    """
    if not await is_postgresql(session):
        logger.info("Using SQLite - skipping PostgreSQL optimizations")
        return
    
    logger.info("🚀 Initializing PostgreSQL optimizations...")
    
    # 1. Set up partitioning (informational only - needs manual migration)
    await setup_telemetry_partitioning(session)
    
    # 2. Ensure partitions exist
    await ensure_future_partitions(session)
    
    # 3. Create materialized view
    await create_dashboard_materialized_view(session)
    
    # 4. Create JSON indexes
    await create_json_indexes(session)
    
    # 5. Create partial indexes
    await create_partial_indexes(session)
    
    # 6. Create covering indexes
    await create_covering_indexes(session)
    
    # 7. Set up NOTIFY triggers
    await setup_notify_triggers(session)
    
    logger.info("✅ PostgreSQL optimizations complete")
