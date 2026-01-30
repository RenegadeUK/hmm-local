"""
PostgreSQL Migration Service
Handles testing connections and migrating data from SQLite to PostgreSQL
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text, inspect, select, Column
from sqlalchemy.sql import sqltypes
from core.config import app_config, settings
from core.database import Base, get_database_url

logger = logging.getLogger(__name__)


def convert_sqlite_value(value, column_type):
    """
    Convert SQLite values to PostgreSQL-compatible types
    
    Args:
        value: The value from SQLite
        column_type: SQLAlchemy column type (optional)
        
    Returns:
        Converted value suitable for PostgreSQL
    """
    if value is None:
        return None
    
    # If column_type is provided, use it for targeted conversion
    if column_type is not None:
        # Convert boolean (SQLite stores as 0/1 integers)
        if isinstance(column_type, (sqltypes.Boolean,)):
            return bool(value)
        
        # Convert datetime (SQLite stores as strings)
        if isinstance(column_type, (sqltypes.DateTime, sqltypes.TIMESTAMP)):
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value.replace(' ', 'T'))
                except:
                    try:
                        if '.' in value:
                            value = value.split('.')[0]
                        return datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                    except Exception as e:
                        logger.warning(f"Failed to parse datetime '{value}': {e}")
                        return None
            elif isinstance(value, datetime):
                return value
    
    # Fallback: Infer type from value itself (when pg_columns not available)
    # Detect datetime strings (format: YYYY-MM-DD HH:MM:SS[.ffffff])
    if isinstance(value, str) and len(value) >= 19:
        if value[4] == '-' and value[7] == '-' and value[10] == ' ' and value[13] == ':' and value[16] == ':':
            try:
                return datetime.fromisoformat(value.replace(' ', 'T'))
            except:
                try:
                    if '.' in value:
                        value = value.split('.')[0]
                    return datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                except:
                    pass
    
    # Don't auto-convert 0/1 to boolean - too risky (would break IDs, counts, etc.)
    # PostgreSQL column type must be available for boolean conversion
    
    return value



class MigrationService:
    """Service for PostgreSQL migration operations"""
    
    @staticmethod
    async def test_postgresql_connection(host: str, port: int, database: str, username: str, password: str) -> Dict[str, Any]:
        """
        Test PostgreSQL connection with provided credentials
        
        Returns:
            {
                "success": bool,
                "message": str,
                "version": str (if successful)
            }
        """
        connection_url = f"postgresql+asyncpg://{username}:{password}@{host}:{port}/{database}"
        
        try:
            engine = create_async_engine(connection_url, echo=False, pool_pre_ping=True)
            
            async with engine.begin() as conn:
                result = await conn.execute(text("SELECT version()"))
                version = result.scalar()
                
            await engine.dispose()
            
            return {
                "success": True,
                "message": "Connection successful",
                "version": version
            }
            
        except Exception as e:
            logger.error(f"PostgreSQL connection test failed: {e}")
            return {
                "success": False,
                "message": f"Connection failed: {str(e)}",
                "version": None
            }
    
    @staticmethod
    async def get_table_names(engine) -> list:
        """Get list of all table names in database"""
        async with engine.begin() as conn:
            def get_tables(conn):
                inspector = inspect(conn)
                return inspector.get_table_names()
            
            tables = await conn.run_sync(get_tables)
            return tables
    
    @staticmethod
    async def count_rows(engine, table_name: str) -> int:
        """Count rows in a table"""
        try:
            async with engine.begin() as conn:
                result = await conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                count = result.scalar()
                return count
        except Exception as e:
            logger.error(f"Failed to count rows in {table_name}: {e}")
            return 0
    
    @staticmethod
    async def migrate_data(progress_callback=None) -> Dict[str, Any]:
        """
        Migrate all data from SQLite to PostgreSQL
        
        Args:
            progress_callback: Optional async function(table_name, progress_pct, message)
        
        Returns:
            {
                "success": bool,
                "message": str,
                "tables_migrated": int,
                "total_rows": int,
                "errors": list
            }
        """
        from core.scheduler import scheduler
        from apscheduler.schedulers.base import STATE_RUNNING
        
        errors = []
        tables_migrated = 0
        total_rows = 0
        
        # Pause scheduler during migration to prevent concurrent writes
        scheduler_was_running = scheduler.scheduler.state == STATE_RUNNING
        if scheduler_was_running:
            if progress_callback:
                await progress_callback("scheduler", 0, "Pausing background jobs...")
            scheduler.scheduler.pause()
            logger.info("Scheduler paused for migration")
        
        try:
            # Create engines for both databases
            sqlite_url = f"sqlite+aiosqlite:///{settings.DB_PATH}"
            sqlite_engine = create_async_engine(sqlite_url, echo=False)
            
            pg_config = app_config.get("database.postgresql", {})
            pg_url = f"postgresql+asyncpg://{pg_config['username']}:{pg_config['password']}@{pg_config['host']}:{pg_config['port']}/{pg_config['database']}"
            pg_engine = create_async_engine(pg_url, echo=False, pool_pre_ping=True)
            
            # Create all tables in PostgreSQL
            if progress_callback:
                await progress_callback("schema", 0, "Creating PostgreSQL schema...")
            
            async with pg_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            if progress_callback:
                await progress_callback("schema", 100, "Schema created successfully")
            
            # Get list of tables to migrate
            tables = await MigrationService.get_table_names(sqlite_engine)
            
            if not tables:
                return {
                    "success": False,
                    "message": "No tables found in SQLite database",
                    "tables_migrated": 0,
                    "total_rows": 0,
                    "errors": []
                }
            
            # Tables that don't exist in PostgreSQL schema (skip these)
            skip_tables = {
                'monero_hashrate_snapshots',
                'monero_solo_effort', 
                'monero_solo_settings',
                'p2pool_transactions',
                'supportxmr_snapshots'
            }
            
            # Migrate each table
            for idx, table_name in enumerate(tables):
                try:
                    # Skip tables that don't exist in PostgreSQL
                    if table_name in skip_tables:
                        logger.info(f"Skipping table {table_name} (not in PostgreSQL schema)")
                        if progress_callback:
                            await progress_callback(table_name, 100, f"{table_name}: skipped (not in schema)")
                        continue
                    
                    if progress_callback:
                        progress = int((idx / len(tables)) * 100)
                        await progress_callback(table_name, progress, f"Migrating {table_name}...")
                    
                    # Count rows in source
                    row_count = await MigrationService.count_rows(sqlite_engine, table_name)
                    
                    if row_count == 0:
                        if progress_callback:
                            await progress_callback(table_name, 100, f"{table_name}: 0 rows (skipped)")
                        continue
                    
                    # Get PostgreSQL column types directly using asyncpg
                    pg_columns = {}
                    try:
                        import asyncpg
                        pg_config = app_config.get("database.postgresql", {})
                        pg_conn_temp = await asyncpg.connect(
                            host=pg_config['host'],
                            port=pg_config['port'],
                            database=pg_config['database'],
                            user=pg_config['username'],
                            password=pg_config['password']
                        )
                        try:
                            # Query information_schema for column types
                            rows = await pg_conn_temp.fetch(
                                """
                                SELECT column_name, data_type 
                                FROM information_schema.columns 
                                WHERE table_name = $1 AND table_schema = 'public'
                                """,
                                table_name
                            )
                            for row in rows:
                                col_name = row['column_name']
                                data_type = row['data_type']
                                # Map PostgreSQL type names to SQLAlchemy types for conversion
                                if data_type == 'boolean':
                                    pg_columns[col_name] = sqltypes.Boolean()
                                elif data_type in ('timestamp without time zone', 'timestamp with time zone'):
                                    pg_columns[col_name] = sqltypes.DateTime()
                                elif data_type == 'date':
                                    pg_columns[col_name] = sqltypes.Date()
                                else:
                                    pg_columns[col_name] = None
                        finally:
                            await pg_conn_temp.close()
                    except Exception as e:
                        logger.warning(f"Could not get PostgreSQL columns for {table_name}: {e}")
                    
                    # Read all data from SQLite
                    async with sqlite_engine.begin() as conn:
                        result = await conn.execute(text(f"SELECT * FROM {table_name}"))
                        rows = result.fetchall()
                        columns = list(result.keys())
                    
                    # Write to PostgreSQL
                    if rows:
                        # Use direct asyncpg connection for proper parameter binding
                        import asyncpg
                        pg_config = app_config.get("database.postgresql", {})
                        
                        logger.info(f"Connecting to PostgreSQL for {table_name} with {len(rows)} rows")
                        
                        pg_conn = await asyncpg.connect(
                            host=pg_config['host'],
                            port=pg_config['port'],
                            database=pg_config['database'],
                            user=pg_config['username'],
                            password=pg_config['password']
                        )
                        
                        try:
                            # Filter out legacy columns that don't exist in PostgreSQL schema
                            legacy_columns = {'health_check_history'}  # Add more as needed
                            valid_columns = [col for col in columns if col not in legacy_columns]
                            
                            logger.info(f"Columns for {table_name}: {valid_columns}")
                            
                            # Build INSERT statement with quoted column names (handles reserved words like "user")
                            cols = ", ".join([f'"{col}"' for col in valid_columns])
                            placeholders = ", ".join([f"${i+1}" for i in range(len(valid_columns))])
                            insert_sql = f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})"
                            
                            logger.info(f"Insert SQL for {table_name}: {insert_sql}")
                            
                            # Insert rows one by one with type conversion
                            inserted_count = 0
                            failed_count = 0
                            for row in rows:
                                row_dict = dict(zip(columns, row))
                                # Convert types - apply to ALL values
                                converted_values = []
                                for col in valid_columns:
                                    value = row_dict.get(col)
                                    # Get PostgreSQL column type if available
                                    col_type = pg_columns.get(col)
                                    # Always convert - handles datetime strings, booleans, etc.
                                    value = convert_sqlite_value(value, col_type)
                                    converted_values.append(value)
                                
                                try:
                                    await pg_conn.execute(insert_sql, *converted_values)
                                    inserted_count += 1
                                except Exception as row_error:
                                    # Log individual row errors
                                    failed_count += 1
                                    if failed_count <= 3:  # Only log first 3 errors per table
                                        logger.error(f"Failed to insert row {failed_count} in {table_name}: {row_error}")
                            
                            logger.info(f"✅ Inserted {inserted_count}/{len(rows)} rows into {table_name} (failed: {failed_count})")
                        except Exception as table_error:
                            logger.error(f"❌ Table-level error for {table_name}: {table_error}")
                            raise
                        finally:
                            await pg_conn.close()
                        
                        tables_migrated += 1
                        total_rows += len(rows)
                        
                        if progress_callback:
                            await progress_callback(table_name, 100, f"{table_name}: {len(rows)} rows migrated")
                    
                except Exception as e:
                    error_msg = f"Failed to migrate {table_name}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    if progress_callback:
                        await progress_callback(table_name, 100, f"{table_name}: ERROR - {str(e)}")
            
            # Close engines
            await sqlite_engine.dispose()
            await pg_engine.dispose()
            
            if progress_callback:
                await progress_callback("complete", 100, "Migration completed")
            
            return {
                "success": len(errors) == 0,
                "message": f"Migrated {tables_migrated} tables with {total_rows} total rows",
                "tables_migrated": tables_migrated,
                "total_rows": total_rows,
                "errors": errors
            }
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return {
                "success": False,
                "message": f"Migration failed: {str(e)}",
                "tables_migrated": tables_migrated,
                "total_rows": total_rows,
                "errors": errors + [str(e)]
            }
        finally:
            # If migration failed, resume scheduler so system isn't stuck paused
            # If migration succeeded, user will switch DB and reboot (scheduler starts fresh)
            from apscheduler.schedulers.base import STATE_RUNNING
            if scheduler_was_running and scheduler.scheduler.state != STATE_RUNNING:
                scheduler.scheduler.resume()
                logger.info("Scheduler resumed after migration")
    
    @staticmethod
    async def validate_migration() -> Dict[str, Any]:
        """
        Validate that PostgreSQL data matches SQLite
        
        Returns:
            {
                "success": bool,
                "message": str,
                "tables_compared": int,
                "mismatches": list
            }
        """
        mismatches = []
        tables_compared = 0
        
        try:
            # Create engines
            sqlite_url = f"sqlite+aiosqlite:///{settings.DB_PATH}"
            sqlite_engine = create_async_engine(sqlite_url, echo=False)
            
            pg_config = app_config.get("database.postgresql", {})
            pg_url = f"postgresql+asyncpg://{pg_config['username']}:{pg_config['password']}@{pg_config['host']}:{pg_config['port']}/{pg_config['database']}"
            pg_engine = create_async_engine(pg_url, echo=False, pool_pre_ping=True)
            
            # Get tables
            tables = await MigrationService.get_table_names(sqlite_engine)
            
            for table_name in tables:
                sqlite_count = await MigrationService.count_rows(sqlite_engine, table_name)
                pg_count = await MigrationService.count_rows(pg_engine, table_name)
                
                tables_compared += 1
                
                if sqlite_count != pg_count:
                    mismatches.append({
                        "table": table_name,
                        "sqlite_rows": sqlite_count,
                        "postgresql_rows": pg_count
                    })
            
            await sqlite_engine.dispose()
            await pg_engine.dispose()
            
            if mismatches:
                return {
                    "success": False,
                    "message": f"Found {len(mismatches)} table(s) with row count mismatches",
                    "tables_compared": tables_compared,
                    "mismatches": mismatches
                }
            else:
                return {
                    "success": True,
                    "message": f"All {tables_compared} tables validated successfully",
                    "tables_compared": tables_compared,
                    "mismatches": []
                }
                
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return {
                "success": False,
                "message": f"Validation failed: {str(e)}",
                "tables_compared": tables_compared,
                "mismatches": mismatches
            }
    
    @staticmethod
    def switch_to_postgresql():
        """Switch active database to PostgreSQL in config"""
        app_config.set("database.active", "postgresql")
        logger.info("Switched active database to PostgreSQL")
    
    @staticmethod
    def switch_to_sqlite():
        """Switch active database to SQLite in config"""
        app_config.set("database.active", "sqlite")
        logger.info("Switched active database to SQLite")
