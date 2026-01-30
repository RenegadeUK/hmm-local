"""
PostgreSQL Migration Service
Handles testing connections and migrating data from SQLite to PostgreSQL
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text, inspect, select
from core.config import app_config, settings
from core.database import Base, get_database_url

logger = logging.getLogger(__name__)


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
        errors = []
        tables_migrated = 0
        total_rows = 0
        
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
            
            # Migrate each table
            for idx, table_name in enumerate(tables):
                try:
                    if progress_callback:
                        progress = int((idx / len(tables)) * 100)
                        await progress_callback(table_name, progress, f"Migrating {table_name}...")
                    
                    # Count rows in source
                    row_count = await MigrationService.count_rows(sqlite_engine, table_name)
                    
                    if row_count == 0:
                        if progress_callback:
                            await progress_callback(table_name, 100, f"{table_name}: 0 rows (skipped)")
                        continue
                    
                    # Read all data from SQLite
                    async with sqlite_engine.begin() as conn:
                        result = await conn.execute(text(f"SELECT * FROM {table_name}"))
                        rows = result.fetchall()
                        columns = result.keys()
                    
                    # Write to PostgreSQL
                    if rows:
                        async with pg_engine.begin() as conn:
                            # Build INSERT statement
                            cols = ", ".join(columns)
                            placeholders = ", ".join([f":{col}" for col in columns])
                            insert_sql = f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})"
                            
                            # Convert rows to dict format
                            row_dicts = [dict(zip(columns, row)) for row in rows]
                            
                            # Batch insert
                            await conn.execute(text(insert_sql), row_dicts)
                        
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
