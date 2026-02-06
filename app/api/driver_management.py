"""
Driver Management API

Provides endpoints for checking, updating, and installing pool drivers.
"""
import logging
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import importlib.util
import sys

from core.database import get_db
from core.audit import log_audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/drivers", tags=["Driver Management"])

BUNDLED_DRIVERS_PATH = Path("/app/bundled_config/drivers")
CONFIG_DRIVERS_PATH = Path("/config/drivers")


class DriverInfo(BaseModel):
    """Information about a driver"""
    name: str  # e.g., "mmfp_driver.py"
    driver_type: str  # e.g., "mmfp"
    display_name: str  # e.g., "MMFP Solutions"
    current_version: Optional[str]  # Version in /config (None if not installed)
    available_version: str  # Version in bundled
    status: str  # "up_to_date", "update_available", "not_installed"
    description: Optional[str]


class DriverUpdateResponse(BaseModel):
    """Response from driver update/install operation"""
    success: bool
    message: str
    driver_name: str
    old_version: Optional[str]
    new_version: str


def load_driver_module(file_path: Path) -> Optional[Any]:
    """Load a driver module from file path"""
    try:
        spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    except Exception as e:
        logger.error(f"Failed to load driver module {file_path}: {e}")
    return None


def get_driver_version(module: Any) -> str:
    """Extract version from driver module"""
    # Try __version__ first
    if hasattr(module, '__version__'):
        return module.__version__
    
    # Try class attribute driver_version
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, type) and hasattr(attr, 'driver_version'):
            return attr.driver_version
    
    return "unknown"


def get_driver_info_from_module(module: Any) -> Dict[str, str]:
    """Extract driver metadata from module"""
    info = {
        "driver_type": "unknown",
        "display_name": "Unknown Driver",
        "description": None
    }
    
    # Find BasePoolIntegration subclass
    from integrations.base_pool import BasePoolIntegration
    
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (isinstance(attr, type) and 
            issubclass(attr, BasePoolIntegration) and 
            attr is not BasePoolIntegration):
            
            if hasattr(attr, 'pool_type'):
                info["driver_type"] = attr.pool_type
            if hasattr(attr, 'display_name'):
                info["display_name"] = attr.display_name
            if hasattr(attr, '__doc__'):
                info["description"] = attr.__doc__.strip() if attr.__doc__ else None
            break
    
    return info


@router.get("/status", response_model=List[DriverInfo])
async def get_driver_status():
    """
    Check status of all drivers - compare bundled vs deployed versions.
    
    Returns list of all bundled drivers with their current status:
    - up_to_date: Installed and matches bundled version
    - update_available: Installed but bundled version is newer
    - not_installed: Available in bundle but not in /config
    """
    drivers = []
    
    if not BUNDLED_DRIVERS_PATH.exists():
        logger.error(f"Bundled drivers path not found: {BUNDLED_DRIVERS_PATH}")
        return drivers
    
    # Iterate through all bundled drivers
    for bundled_file in BUNDLED_DRIVERS_PATH.glob("*_driver.py"):
        driver_name = bundled_file.name
        config_file = CONFIG_DRIVERS_PATH / driver_name
        
        # Load bundled driver module
        bundled_module = load_driver_module(bundled_file)
        if not bundled_module:
            logger.warning(f"Failed to load bundled driver: {driver_name}")
            continue
        
        available_version = get_driver_version(bundled_module)
        driver_metadata = get_driver_info_from_module(bundled_module)
        
        # Check if driver is installed in /config
        current_version = None
        status = "not_installed"
        
        if config_file.exists():
            config_module = load_driver_module(config_file)
            if config_module:
                current_version = get_driver_version(config_module)
                
                # Compare versions
                if current_version == available_version:
                    status = "up_to_date"
                elif current_version == "unknown":
                    status = "update_available"  # Old driver without version
                else:
                    # Simple version comparison (assumes semantic versioning)
                    try:
                        current_parts = [int(x) for x in current_version.split('.')]
                        available_parts = [int(x) for x in available_version.split('.')]
                        
                        if available_parts > current_parts:
                            status = "update_available"
                        else:
                            status = "up_to_date"
                    except:
                        # If version parsing fails, assume update available
                        status = "update_available"
        
        drivers.append(DriverInfo(
            name=driver_name,
            driver_type=driver_metadata["driver_type"],
            display_name=driver_metadata["display_name"],
            current_version=current_version,
            available_version=available_version,
            status=status,
            description=driver_metadata["description"]
        ))
    
    return drivers


@router.post("/update/{driver_name}", response_model=DriverUpdateResponse)
async def update_driver(driver_name: str, db: AsyncSession = Depends(get_db)):
    """
    Update a specific driver by copying from bundled to /config.
    
    Args:
        driver_name: Name of the driver file (e.g., "mmfp_driver.py")
    """
    # Validate driver name
    if not driver_name.endswith("_driver.py"):
        raise HTTPException(status_code=400, detail="Invalid driver name format")
    
    bundled_file = BUNDLED_DRIVERS_PATH / driver_name
    config_file = CONFIG_DRIVERS_PATH / driver_name
    
    if not bundled_file.exists():
        raise HTTPException(status_code=404, detail=f"Driver {driver_name} not found in bundle")
    
    # Get old version before update
    old_version = None
    if config_file.exists():
        old_module = load_driver_module(config_file)
        if old_module:
            old_version = get_driver_version(old_module)
    
    # Get new version
    new_module = load_driver_module(bundled_file)
    if not new_module:
        raise HTTPException(status_code=500, detail=f"Failed to load bundled driver {driver_name}")
    
    new_version = get_driver_version(new_module)
    
    try:
        # Ensure /config/drivers directory exists
        CONFIG_DRIVERS_PATH.mkdir(parents=True, exist_ok=True)
        
        # Copy driver file
        shutil.copy2(bundled_file, config_file)
        logger.info(f"Updated driver {driver_name} from {old_version or 'not installed'} to {new_version}")
        
        # Log audit event
        await log_audit(
            db=db,
            action="update" if old_version else "install",
            resource_type="driver",
            resource_name=driver_name,
            changes={
                "version": {
                    "before": old_version or "not installed",
                    "after": new_version
                }
            }
        )
        
        return DriverUpdateResponse(
            success=True,
            message=f"Driver {driver_name} updated successfully. Restart required to load new version.",
            driver_name=driver_name,
            old_version=old_version,
            new_version=new_version
        )
    
    except Exception as e:
        logger.error(f"Failed to update driver {driver_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-all")
async def update_all_drivers(db: AsyncSession = Depends(get_db)):
    """
    Update all drivers that have updates available.
    
    Returns summary of updated drivers.
    """
    status = await get_driver_status()
    
    updated = []
    failed = []
    
    for driver in status:
        if driver.status == "update_available":
            try:
                result = await update_driver(driver.name, db)
                updated.append({
                    "name": driver.name,
                    "old_version": result.old_version,
                    "new_version": result.new_version
                })
            except Exception as e:
                failed.append({
                    "name": driver.name,
                    "error": str(e)
                })
    
    return {
        "success": len(failed) == 0,
        "updated": updated,
        "failed": failed,
        "message": f"Updated {len(updated)} driver(s). {len(failed)} failed." if failed else f"Successfully updated {len(updated)} driver(s). Restart required."
    }


@router.post("/install/{driver_name}", response_model=DriverUpdateResponse)
async def install_driver(driver_name: str, db: AsyncSession = Depends(get_db)):
    """
    Install a new driver from bundle (same as update, but semantically different).
    
    Args:
        driver_name: Name of the driver file (e.g., "mmfp_driver.py")
    """
    # Installation is the same as updating - just copy from bundle
    return await update_driver(driver_name, db)
