"""
Migration: Add energy_cost column to telemetry table

This migration adds the energy_cost column to store the calculated cost
at the time of telemetry capture, based on power consumption and Agile pricing.

Run this migration before deploying the updated scheduler code.
"""

import sqlite3
import sys
from pathlib import Path

def migrate(db_path: str = "/config/data.db"):
    """Add energy_cost column to telemetry table"""
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(telemetry)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'energy_cost' in columns:
            print("✓ energy_cost column already exists")
            return True
        
        # Add the column (SQLite only supports adding nullable columns)
        print("Adding energy_cost column to telemetry table...")
        cursor.execute("""
            ALTER TABLE telemetry 
            ADD COLUMN energy_cost REAL
        """)
        
        conn.commit()
        print("✓ Migration completed successfully")
        
        # Verify
        cursor.execute("PRAGMA table_info(telemetry)")
        columns = [row[1] for row in cursor.fetchall()]
        assert 'energy_cost' in columns, "Column was not added"
        
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
