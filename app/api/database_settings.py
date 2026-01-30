"""
Database Settings API
Endpoints for PostgreSQL configuration and migration
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import asyncio
import logging
from core.config import app_config
from core.migration import MigrationService

logger = logging.getLogger(__name__)
router = APIRouter()


class PostgreSQLConfig(BaseModel):
    """PostgreSQL connection configuration"""
    host: str = Field(..., min_length=1, description="PostgreSQL host")
    port: int = Field(5432, ge=1, le=65535, description="PostgreSQL port")
    database: str = Field(..., min_length=1, description="Database name")
    username: str = Field(..., min_length=1, description="Database username")
    password: str = Field("", description="Database password")


class DatabaseStatus(BaseModel):
    """Current database status"""
    active: str  # "sqlite" or "postgresql"
    postgresql_configured: bool
    postgresql_config: Optional[Dict[str, Any]] = None


@router.get("/database/status")
async def get_database_status() -> DatabaseStatus:
    """Get current database configuration status"""
    active_db = app_config.get("database.active", "sqlite")
    pg_config = app_config.get("database.postgresql", {})
    
    # Check if PostgreSQL is configured (has non-empty password)
    pg_configured = bool(pg_config.get("password"))
    
    # Sanitize password in response
    if pg_configured:
        pg_config_safe = pg_config.copy()
        pg_config_safe["password"] = "***" if pg_config_safe.get("password") else ""
    else:
        pg_config_safe = None
    
    return DatabaseStatus(
        active=active_db,
        postgresql_configured=pg_configured,
        postgresql_config=pg_config_safe
    )


@router.post("/database/postgresql/test")
async def test_postgresql_connection(config: PostgreSQLConfig):
    """Test PostgreSQL connection with provided credentials"""
    result = await MigrationService.test_postgresql_connection(
        host=config.host,
        port=config.port,
        database=config.database,
        username=config.username,
        password=config.password
    )
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    
    return result


@router.post("/database/postgresql/save")
async def save_postgresql_config(config: PostgreSQLConfig):
    """Save PostgreSQL configuration to config.yaml"""
    # First test the connection
    test_result = await MigrationService.test_postgresql_connection(
        host=config.host,
        port=config.port,
        database=config.database,
        username=config.username,
        password=config.password
    )
    
    if not test_result["success"]:
        raise HTTPException(status_code=400, detail=f"Connection test failed: {test_result['message']}")
    
    # Save to config
    app_config.set("database.postgresql", {
        "host": config.host,
        "port": config.port,
        "database": config.database,
        "username": config.username,
        "password": config.password
    })
    
    return {
        "success": True,
        "message": "PostgreSQL configuration saved successfully",
        "version": test_result.get("version")
    }


# Global migration state (in production, use Redis/database)
migration_state = {
    "running": False,
    "progress": [],
    "result": None
}


async def migration_progress_callback(table_name: str, progress: int, message: str):
    """Callback for migration progress updates"""
    migration_state["progress"].append({
        "table": table_name,
        "progress": progress,
        "message": message
    })


@router.post("/database/migrate/start")
async def start_migration():
    """Start database migration from SQLite to PostgreSQL"""
    global migration_state
    
    # Check if already running
    if migration_state["running"]:
        raise HTTPException(status_code=409, detail="Migration already in progress")
    
    # Check if PostgreSQL is configured
    pg_config = app_config.get("database.postgresql", {})
    if not pg_config.get("password"):
        raise HTTPException(status_code=400, detail="PostgreSQL not configured. Please save configuration first.")
    
    # Check if already on PostgreSQL
    active_db = app_config.get("database.active", "sqlite")
    if active_db == "postgresql":
        raise HTTPException(status_code=400, detail="Already using PostgreSQL database")
    
    # Reset state
    migration_state = {
        "running": True,
        "progress": [],
        "result": None
    }
    
    # Start migration in background
    asyncio.create_task(run_migration())
    
    return {
        "success": True,
        "message": "Migration started",
        "job_id": "migration_job"  # In production, use actual job ID
    }


async def run_migration():
    """Background task to run migration"""
    global migration_state
    
    try:
        result = await MigrationService.migrate_data(progress_callback=migration_progress_callback)
        migration_state["result"] = result
        migration_state["running"] = False
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        migration_state["result"] = {
            "success": False,
            "message": f"Migration failed: {str(e)}",
            "tables_migrated": 0,
            "total_rows": 0,
            "errors": [str(e)]
        }
        migration_state["running"] = False


@router.get("/database/migrate/status")
async def get_migration_status():
    """Get current migration status and progress"""
    return {
        "running": migration_state["running"],
        "progress": migration_state["progress"],
        "result": migration_state["result"]
    }


@router.post("/database/migrate/validate")
async def validate_migration():
    """Validate that PostgreSQL data matches SQLite"""
    # Check if migration completed
    if migration_state["result"] is None:
        raise HTTPException(status_code=400, detail="No migration has been run")
    
    if not migration_state["result"]["success"]:
        raise HTTPException(status_code=400, detail="Cannot validate failed migration")
    
    validation_result = await MigrationService.validate_migration()
    
    return validation_result


@router.post("/database/switch")
async def switch_database(target: str):
    """
    Switch active database
    
    Args:
        target: "sqlite" or "postgresql"
    """
    if target not in ["sqlite", "postgresql"]:
        raise HTTPException(status_code=400, detail="Invalid target. Must be 'sqlite' or 'postgresql'")
    
    current_db = app_config.get("database.active", "sqlite")
    
    if current_db == target:
        return {
            "success": True,
            "message": f"Already using {target} database",
            "restart_required": False
        }
    
    # If switching to PostgreSQL, verify it's configured and migrated
    if target == "postgresql":
        pg_config = app_config.get("database.postgresql", {})
        if not pg_config.get("password"):
            raise HTTPException(status_code=400, detail="PostgreSQL not configured")
        
        if migration_state["result"] is None or not migration_state["result"]["success"]:
            raise HTTPException(status_code=400, detail="Migration must be completed successfully before switching")
    
    # Switch database
    if target == "postgresql":
        MigrationService.switch_to_postgresql()
    else:
        MigrationService.switch_to_sqlite()
    
    return {
        "success": True,
        "message": f"Switched to {target} database",
        "restart_required": True
    }
