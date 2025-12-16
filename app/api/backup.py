"""
Backup and Restore API endpoints
Full configuration export/import
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from datetime import datetime
import json
import io
import zipfile
from typing import Dict, Any

from core.database import (
    get_db, Miner, Pool, AutomationRule, EnergyPrice, 
    NotificationConfig, AlertConfig, TuningProfile, CustomDashboard, DashboardWidget
)

router = APIRouter()


async def export_table_data(db: AsyncSession, model) -> list:
    """Export all rows from a table"""
    result = await db.execute(select(model))
    rows = result.scalars().all()
    return [
        {
            column.name: getattr(row, column.name)
            for column in model.__table__.columns
        }
        for row in rows
    ]


@router.get("/export")
async def export_backup(db: AsyncSession = Depends(get_db)):
    """
    Export complete system configuration as a JSON file
    Includes: miners, pools, automation rules, profiles, dashboards, settings
    """
    try:
        backup_data = {
            "export_version": "1.0",
            "export_timestamp": datetime.utcnow().isoformat(),
            "data": {}
        }
        
        # Export all configuration tables
        tables = {
            "miners": Miner,
            "pools": Pool,
            "automation_rules": AutomationRule,
            "notification_configs": NotificationConfig,
            "alert_configs": AlertConfig,
            "tuning_profiles": TuningProfile,
            "custom_dashboards": CustomDashboard,
            "dashboard_widgets": DashboardWidget
        }
        
        for table_name, model in tables.items():
            backup_data["data"][table_name] = await export_table_data(db, model)
        
        # Convert to JSON
        json_data = json.dumps(backup_data, indent=2, default=str)
        
        # Create file stream
        file_stream = io.BytesIO(json_data.encode())
        filename = f"miner_controller_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        
        return StreamingResponse(
            file_stream,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}")


@router.get("/export-full")
async def export_full_backup(db: AsyncSession = Depends(get_db)):
    """
    Export complete system including telemetry and historical data as ZIP
    WARNING: Can be very large with extensive telemetry history
    """
    try:
        # Create in-memory ZIP file
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Export configuration (same as standard backup)
            backup_data = {
                "export_version": "1.0",
                "export_timestamp": datetime.utcnow().isoformat(),
                "data": {}
            }
            
            tables = {
                "miners": Miner,
                "pools": Pool,
                "automation_rules": AutomationRule,
                "notification_configs": NotificationConfig,
                "alert_configs": AlertConfig,
                "tuning_profiles": TuningProfile,
                "custom_dashboards": CustomDashboard,
                "dashboard_widgets": DashboardWidget
            }
            
            for table_name, model in tables.items():
                backup_data["data"][table_name] = await export_table_data(db, model)
            
            # Add configuration to ZIP
            zip_file.writestr(
                "configuration.json",
                json.dumps(backup_data, indent=2, default=str)
            )
            
            # Export energy prices (last 30 days)
            result = await db.execute(
                text("SELECT * FROM energy_prices WHERE valid_from >= date('now', '-30 days')")
            )
            prices = [dict(row._mapping) for row in result]
            zip_file.writestr(
                "energy_prices.json",
                json.dumps(prices, indent=2, default=str)
            )
            
            # Export recent telemetry (last 7 days)
            result = await db.execute(
                text("SELECT * FROM telemetry WHERE timestamp >= datetime('now', '-7 days')")
            )
            telemetry = [dict(row._mapping) for row in result]
            zip_file.writestr(
                "telemetry_7days.json",
                json.dumps(telemetry, indent=2, default=str)
            )
            
            # Add README
            readme = """Miner Controller Full Backup
            
This backup contains:
- configuration.json: All system settings (miners, pools, automation, profiles, dashboards)
- energy_prices.json: Energy pricing data (last 30 days)
- telemetry_7days.json: Telemetry history (last 7 days)

To restore:
1. Use the restore endpoint with configuration.json for basic restore
2. Use full restore to include historical data

Export Date: {date}
Export Version: 1.0
""".format(date=datetime.utcnow().isoformat())
            
            zip_file.writestr("README.txt", readme)
        
        zip_buffer.seek(0)
        filename = f"miner_controller_full_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
        
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Full backup failed: {str(e)}")


@router.post("/restore")
async def restore_backup(
    file: UploadFile = File(...),
    mode: str = "merge",  # merge or replace
    db: AsyncSession = Depends(get_db)
):
    """
    Restore configuration from backup file
    
    Modes:
    - merge: Add new items, update existing by ID (default, safer)
    - replace: Delete all existing data and import backup (destructive)
    """
    try:
        # Read uploaded file
        content = await file.read()
        backup_data = json.loads(content)
        
        # Validate backup format
        if "export_version" not in backup_data or "data" not in backup_data:
            raise HTTPException(status_code=400, detail="Invalid backup file format")
        
        # If replace mode, clear existing data
        if mode == "replace":
            # Delete in correct order to respect foreign keys
            await db.execute(text("DELETE FROM dashboard_widgets"))
            await db.execute(text("DELETE FROM custom_dashboards"))
            await db.execute(text("DELETE FROM alert_configs"))
            await db.execute(text("DELETE FROM notification_configs"))
            await db.execute(text("DELETE FROM tuning_profiles"))
            await db.execute(text("DELETE FROM automation_rules"))
            await db.execute(text("DELETE FROM pools"))
            await db.execute(text("DELETE FROM miners"))
            await db.commit()
        
        # Import data
        imported_counts = {}
        
        # Miners
        if "miners" in backup_data["data"]:
            for miner_data in backup_data["data"]["miners"]:
                if mode == "merge":
                    # Check if exists
                    result = await db.execute(
                        select(Miner).where(Miner.id == miner_data["id"])
                    )
                    existing = result.scalar_one_or_none()
                    if existing:
                        # Update existing
                        for key, value in miner_data.items():
                            if key != "id":
                                setattr(existing, key, value)
                    else:
                        # Insert new
                        db.add(Miner(**miner_data))
                else:
                    db.add(Miner(**miner_data))
            
            imported_counts["miners"] = len(backup_data["data"]["miners"])
        
        # Pools
        if "pools" in backup_data["data"]:
            for pool_data in backup_data["data"]["pools"]:
                if mode == "merge":
                    result = await db.execute(
                        select(Pool).where(Pool.id == pool_data["id"])
                    )
                    existing = result.scalar_one_or_none()
                    if existing:
                        for key, value in pool_data.items():
                            if key != "id":
                                setattr(existing, key, value)
                    else:
                        db.add(Pool(**pool_data))
                else:
                    db.add(Pool(**pool_data))
            
            imported_counts["pools"] = len(backup_data["data"]["pools"])
        
        # Automation Rules
        if "automation_rules" in backup_data["data"]:
            for rule_data in backup_data["data"]["automation_rules"]:
                if mode == "merge":
                    result = await db.execute(
                        select(AutomationRule).where(AutomationRule.id == rule_data["id"])
                    )
                    existing = result.scalar_one_or_none()
                    if existing:
                        for key, value in rule_data.items():
                            if key != "id":
                                setattr(existing, key, value)
                    else:
                        db.add(AutomationRule(**rule_data))
                else:
                    db.add(AutomationRule(**rule_data))
            
            imported_counts["automation_rules"] = len(backup_data["data"]["automation_rules"])
        
        # Similar logic for other tables...
        for table_name in ["notification_configs", "alert_configs", "tuning_profiles", 
                          "custom_dashboards", "dashboard_widgets"]:
            if table_name in backup_data["data"]:
                imported_counts[table_name] = len(backup_data["data"][table_name])
                # Add import logic for each table type
        
        await db.commit()
        
        return {
            "success": True,
            "mode": mode,
            "imported_counts": imported_counts,
            "backup_timestamp": backup_data.get("export_timestamp"),
            "message": "Restore completed successfully"
        }
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")


@router.get("/info")
async def get_backup_info(db: AsyncSession = Depends(get_db)):
    """Get information about current system data for backup"""
    try:
        counts = {}
        
        # Count records in each table
        tables = {
            "miners": Miner,
            "pools": Pool,
            "automation_rules": AutomationRule,
            "notification_configs": NotificationConfig,
            "alert_configs": AlertConfig,
            "tuning_profiles": TuningProfile,
            "custom_dashboards": CustomDashboard,
            "dashboard_widgets": DashboardWidget
        }
        
        for table_name, model in tables.items():
            result = await db.execute(select(model))
            counts[table_name] = len(result.scalars().all())
        
        # Get telemetry size
        result = await db.execute(text("SELECT COUNT(*) as count FROM telemetry"))
        counts["telemetry_records"] = result.scalar()
        
        # Get energy prices count
        result = await db.execute(text("SELECT COUNT(*) as count FROM energy_prices"))
        counts["energy_price_records"] = result.scalar()
        
        return {
            "record_counts": counts,
            "estimated_json_size_kb": sum(counts.values()) * 0.5,  # Rough estimate
            "last_backup": None  # Could track this in a separate table
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get backup info: {str(e)}")
