"""
Migration: Create telemetry aggregation tables

Creates TelemetryHourly and TelemetryDaily tables for storing aggregated
telemetry data to reduce AI context window size by 56x-789x.

Run this migration before starting the aggregation scheduler job.
"""

import sqlite3
import sys

def migrate(db_path: str = "/config/data.db"):
    """Create telemetry aggregation tables"""
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if tables already exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='telemetry_hourly'")
        if cursor.fetchone():
            print("✓ telemetry_hourly table already exists")
        else:
            print("Creating telemetry_hourly table...")
            cursor.execute("""
                CREATE TABLE telemetry_hourly (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    miner_id INTEGER NOT NULL,
                    hour_start DATETIME NOT NULL,
                    uptime_minutes INTEGER NOT NULL,
                    avg_hashrate REAL,
                    min_hashrate REAL,
                    max_hashrate REAL,
                    hashrate_unit TEXT DEFAULT 'GH/s',
                    avg_temperature REAL,
                    peak_temperature REAL,
                    total_kwh REAL,
                    total_energy_cost REAL,
                    shares_accepted INTEGER,
                    shares_rejected INTEGER,
                    reject_rate_pct REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE INDEX ix_telemetry_hourly_miner_id 
                ON telemetry_hourly(miner_id)
            """)
            
            cursor.execute("""
                CREATE INDEX ix_telemetry_hourly_hour_start 
                ON telemetry_hourly(hour_start)
            """)
            
            cursor.execute("""
                CREATE INDEX ix_telemetry_hourly_miner_hour 
                ON telemetry_hourly(miner_id, hour_start)
            """)
            
            print("✓ Created telemetry_hourly table")
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='telemetry_daily'")
        if cursor.fetchone():
            print("✓ telemetry_daily table already exists")
        else:
            print("Creating telemetry_daily table...")
            cursor.execute("""
                CREATE TABLE telemetry_daily (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    miner_id INTEGER NOT NULL,
                    date DATETIME NOT NULL,
                    uptime_minutes INTEGER NOT NULL,
                    uptime_percentage REAL,
                    avg_hashrate REAL,
                    min_hashrate REAL,
                    max_hashrate REAL,
                    hashrate_unit TEXT DEFAULT 'GH/s',
                    avg_temperature REAL,
                    peak_temperature REAL,
                    total_kwh REAL,
                    total_energy_cost REAL,
                    shares_accepted INTEGER,
                    shares_rejected INTEGER,
                    reject_rate_pct REAL,
                    health_score REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE INDEX ix_telemetry_daily_miner_id 
                ON telemetry_daily(miner_id)
            """)
            
            cursor.execute("""
                CREATE INDEX ix_telemetry_daily_date 
                ON telemetry_daily(date)
            """)
            
            cursor.execute("""
                CREATE INDEX ix_telemetry_daily_miner_date 
                ON telemetry_daily(miner_id, date)
            """)
            
            print("✓ Created telemetry_daily table")
        
        conn.commit()
        print("\n✓ Migration completed successfully")
        return True
        
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/config/data.db"
    success = migrate(db_path)
    sys.exit(0 if success else 1)
