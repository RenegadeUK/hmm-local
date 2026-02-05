#!/usr/bin/env python3
"""
SQLite to PostgreSQL Migration Script for HMM-Local

This script migrates your existing SQLite database to PostgreSQL.
Run this BEFORE switching to PostgreSQL in docker-compose.

Usage:
    python migrate_to_postgres.py

Environment variables:
    POSTGRES_HOST: PostgreSQL host (default: postgres)
    POSTGRES_PORT: PostgreSQL port (default: 5432)
    POSTGRES_DB: Database name (default: hmm)
    POSTGRES_USER: Database user (default: hmm_user)
    POSTGRES_PASSWORD: Database password (required)
    SQLITE_PATH: Path to SQLite database (default: ./config/data.db)
"""

import os
import sys
import asyncio
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from sqlalchemy import create_engine, text, MetaData, Table
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


async def migrate():
    """Migrate data from SQLite to PostgreSQL"""
    
    # Get configuration
    sqlite_path = os.getenv("SQLITE_PATH", "./config/data.db")
    pg_host = os.getenv("POSTGRES_HOST", "localhost")
    pg_port = os.getenv("POSTGRES_PORT", "5432")
    pg_db = os.getenv("POSTGRES_DB", "hmm")
    pg_user = os.getenv("POSTGRES_USER", "hmm_user")
    pg_password = os.getenv("POSTGRES_PASSWORD")
    
    if not pg_password:
        print("❌ ERROR: POSTGRES_PASSWORD environment variable is required")
        print("   Set it with: export POSTGRES_PASSWORD='your_password'")
        sys.exit(1)
    
    if not Path(sqlite_path).exists():
        print(f"❌ ERROR: SQLite database not found at: {sqlite_path}")
        sys.exit(1)
    
    print("=" * 80)
    print("SQLite → PostgreSQL Migration")
    print("=" * 80)
    print(f"Source: {sqlite_path}")
    print(f"Target: {pg_user}@{pg_host}:{pg_port}/{pg_db}")
    print()
    
    # Connect to SQLite
    sqlite_url = f"sqlite:///{sqlite_path}"
    sqlite_engine = create_engine(sqlite_url)
    
    # Connect to PostgreSQL
    pg_url = f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"
    pg_async_url = f"postgresql+asyncpg://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"
    pg_engine = create_engine(pg_url)
    pg_async_engine = create_async_engine(pg_async_url)
    
    try:
        # Test PostgreSQL connection
        print("🔌 Testing PostgreSQL connection...")
        with pg_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ PostgreSQL connection successful")
        
        # Get table list from SQLite
        print("\n📋 Reading SQLite schema...")
        metadata = MetaData()
        metadata.reflect(bind=sqlite_engine)
        tables = list(metadata.tables.keys())
        print(f"✅ Found {len(tables)} tables: {', '.join(tables)}")
        
        # Create tables in PostgreSQL (using SQLAlchemy models)
        print("\n🏗️  Creating PostgreSQL schema...")
        from core.database import Base
        async with pg_async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("✅ Schema created")
        
        # Migrate data table by table
        print("\n📦 Migrating data...")
        for table_name in tables:
            print(f"   Migrating {table_name}...", end=" ", flush=True)
            
            # Read from SQLite
            with sqlite_engine.connect() as sqlite_conn:
                result = sqlite_conn.execute(text(f"SELECT * FROM {table_name}"))
                rows = result.fetchall()
                column_names = result.keys()
            
            if not rows:
                print(f"(empty)")
                continue
            
            # Write to PostgreSQL
            with pg_engine.connect() as pg_conn:
                # Disable foreign key checks temporarily
                pg_conn.execute(text("SET session_replication_role = 'replica';"))
                
                for row in rows:
                    # Build INSERT statement
                    columns = ", ".join(column_names)
                    placeholders = ", ".join([f":{col}" for col in column_names])
                    sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
                    
                    # Convert row to dict
                    row_dict = dict(zip(column_names, row))
                    
                    try:
                        pg_conn.execute(text(sql), row_dict)
                    except Exception as e:
                        print(f"\n   ⚠️  Error inserting row: {e}")
                        continue
                
                # Re-enable foreign key checks
                pg_conn.execute(text("SET session_replication_role = 'origin';"))
                pg_conn.commit()
            
            print(f"✅ {len(rows)} rows")
        
        # Reset sequences for auto-increment columns
        print("\n🔢 Resetting sequences...")
        with pg_engine.connect() as pg_conn:
            for table_name in tables:
                try:
                    pg_conn.execute(text(f"""
                        SELECT setval(pg_get_serial_sequence('{table_name}', 'id'),
                               COALESCE((SELECT MAX(id) FROM {table_name}), 1))
                    """))
                except:
                    pass  # Table doesn't have auto-increment id
            pg_conn.commit()
        print("✅ Sequences reset")
        
        print("\n" + "=" * 80)
        print("✅ Migration completed successfully!")
        print("=" * 80)
        print("\nNext steps:")
        print("1. Update config/config.yaml:")
        print("   database:")
        print("     active: postgresql")
        print("2. Stop the container: docker-compose down")
        print("3. Start with PostgreSQL: docker-compose up -d")
        print()
        
    except Exception as e:
        print(f"\n❌ ERROR: Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        sqlite_engine.dispose()
        pg_engine.dispose()
        await pg_async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
