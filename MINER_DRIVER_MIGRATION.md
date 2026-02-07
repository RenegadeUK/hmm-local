# Miner Driver System Migration Plan

**Version:** 1.0.0  
**Date:** 7 February 2026  
**Status:** Planning Phase

---

## Table of Contents

1. [Overview](#overview)
2. [Current State Analysis](#current-state-analysis)
3. [Target Architecture](#target-architecture)
4. [Implementation Phases](#implementation-phases)
5. [File-by-File Changes](#file-by-file-changes)
6. [Testing Strategy](#testing-strategy)
7. [Migration Path](#migration-path)
8. [Rollout Plan](#rollout-plan)

---

## Overview

### Objective
Migrate the hardcoded miner adapter system to a dynamic driver-based plugin architecture, matching the pool driver system pattern we successfully implemented.

### Why This Matters
- **Extensibility:** Community can add new miner types without code changes
- **Maintainability:** Consistent architecture across pools + miners
- **Updateability:** Deploy adapter fixes without container rebuilds
- **Testability:** Load mock adapters for testing
- **User Experience:** Users can install/update miner support via UI

### Lessons from Pool Migration
- ✅ Dynamic loading works great (no performance impact)
- ✅ Version tracking enables smooth updates
- ✅ Users appreciate the update UI
- ⚠️ Must update BOTH `bundled_config/` AND `/config/` directories
- ⚠️ Need comprehensive error logging with tracebacks

---

## Current State Analysis

### Existing Adapters (Hardcoded)

```
app/adapters/
├── __init__.py              # Exports all adapters
├── base.py                  # BaseMinerAdapter interface (~100 lines)
├── avalon_nano.py           # Avalon Nano 3/3S (~600 lines)
├── bitaxe.py                # Bitaxe 601 (~400 lines)
├── nerdqaxe.py              # NerdQaxe++ (~350 lines)
├── nmminer.py               # NMMiner ESP32 (~300 lines)
└── xmrig.py                 # XMRig (REMOVED in recent migration)
```

### Current Import Pattern

**Discovery System:**
```python
# app/core/discovery.py
from adapters.avalon_nano import AvalonNanoAdapter
from adapters.bitaxe import BitaxeAdapter
from adapters.nerdqaxe import NerdQaxeAdapter
from adapters.nmminer import NMMinerAdapter
```

**Telemetry Collection:**
```python
# app/core/scheduler.py
from adapters.avalon_nano import AvalonNanoAdapter
from adapters.bitaxe import BitaxeAdapter
# ... etc
```

**API Endpoints:**
```python
# app/api/miners.py
from adapters import get_adapter_for_miner
```

### Problems with Current System

1. **Hardcoded Imports:** Can't add new miners without code changes
2. **No Versioning:** Can't track adapter updates
3. **No Plugin System:** Community can't contribute adapters
4. **Tight Coupling:** Adapters embedded in application code
5. **Update Process:** Requires full container rebuild for fixes

---

## Target Architecture

### Directory Structure

```
bundled_config/
└── miner_drivers/
    ├── README.md                    # Driver development guide
    ├── TEMPLATE_miner_driver.py     # Template for new drivers
    ├── avalon_nano_driver.py        # Avalon Nano 3/3S driver
    ├── bitaxe_driver.py             # Bitaxe 601 driver
    ├── nerdqaxe_driver.py           # NerdQaxe++ driver
    └── nmminer_driver.py            # NMMiner ESP32 driver

/config/
└── miner_drivers/                   # Runtime drivers (user can modify)
    ├── avalon_nano_driver.py
    ├── bitaxe_driver.py
    ├── nerdqaxe_driver.py
    └── nmminer_driver.py
```

### Base Interface

**`app/adapters/base.py` (Enhanced):**
```python
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List

__version__ = "1.0.0"  # Interface version


class BaseMinerAdapter(ABC):
    """
    Base interface for all miner drivers.
    
    All miner drivers MUST inherit from this class and implement
    the abstract methods.
    """
    
    # Driver metadata (REQUIRED)
    driver_type: str = None         # e.g., "avalon_nano", "bitaxe"
    driver_version: str = "1.0.0"   # Driver version (semantic versioning)
    display_name: str = None        # Human-readable name
    manufacturer: str = None        # Miner manufacturer
    supported_models: List[str] = []  # e.g., ["Nano 3", "Nano 3S"]
    
    # Connection details
    connection_type: str = None     # "http", "tcp", "udp"
    default_port: int = None
    
    @abstractmethod
    async def connect(self, ip: str, port: int = None) -> bool:
        """Test connection to miner. Returns True if successful."""
        pass
    
    @abstractmethod
    async def get_telemetry(self) -> Dict[str, Any]:
        """
        Get current telemetry data.
        
        MUST return dict with keys:
        - hashrate (float): Hashrate in H/s
        - temperature (float): Temperature in Celsius
        - power (float): Power consumption in watts
        - uptime (int): Uptime in seconds
        - mode (str): Current power mode (if applicable)
        """
        pass
    
    @abstractmethod
    async def get_pool_info(self) -> Dict[str, Any]:
        """
        Get current pool configuration.
        
        MUST return dict with keys:
        - pool_url (str)
        - pool_user (str)
        - pool_pass (str)
        """
        pass
    
    @abstractmethod
    async def set_mode(self, mode: str) -> bool:
        """
        Set power mode (e.g., "low", "med", "high", "eco", "turbo").
        Returns True if successful.
        """
        pass
    
    @abstractmethod
    async def restart(self) -> bool:
        """Restart the miner. Returns True if command sent successfully."""
        pass
    
    # Optional methods (provide default implementations)
    
    async def set_pool(self, url: str, user: str, password: str) -> bool:
        """
        Set pool configuration.
        Default: Not implemented (return False)
        """
        return False
    
    async def get_version_info(self) -> Dict[str, str]:
        """
        Get miner firmware version.
        Default: Returns empty dict
        """
        return {}
    
    def supports_tuning(self) -> bool:
        """Does this miner support tuning profiles?"""
        return False
    
    def get_supported_modes(self) -> List[str]:
        """Get list of supported power modes."""
        return []
```

### Driver Loader

**`app/core/miner_driver_loader.py` (New File):**
```python
"""
Miner Driver Loader

Dynamically loads miner drivers from /config/miner_drivers/
Similar to pool_loader.py but for miner adapters.
"""
import os
import importlib.util
import logging
from typing import Dict, Optional, List
from pathlib import Path

from adapters.base import BaseMinerAdapter

logger = logging.getLogger(__name__)


class MinerDriverLoader:
    """
    Loads miner drivers from /config/miner_drivers/
    Provides unified access to all available miner adapters.
    """
    
    def __init__(self, config_path: str = "/config"):
        self.config_path = Path(config_path)
        self.drivers_path = self.config_path / "miner_drivers"
        self.drivers: Dict[str, BaseMinerAdapter] = {}  # driver_type -> instance
        
    def load_drivers(self):
        """Dynamically load all Python files from /config/miner_drivers/"""
        if not self.drivers_path.exists():
            logger.warning(f"Miner drivers directory not found: {self.drivers_path}")
            return
        
        logger.info(f"Loading miner drivers from {self.drivers_path}")
        
        for file_path in self.drivers_path.glob("*_driver.py"):
            try:
                # Load the Python module
                spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # Find BaseMinerAdapter subclasses
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and 
                            issubclass(attr, BaseMinerAdapter) and 
                            attr is not BaseMinerAdapter):
                            
                            # Instantiate the driver
                            driver_instance = attr()
                            driver_type = driver_instance.driver_type
                            
                            if driver_type:
                                self.drivers[driver_type] = driver_instance
                                version = getattr(driver_instance, 'driver_version', 'unknown')
                                logger.info(f"✅ Loaded miner driver: {driver_type} v{version} from {file_path.name}")
                            else:
                                logger.warning(f"⚠️  Driver in {file_path.name} missing driver_type attribute")
                    
            except Exception as e:
                import traceback
                logger.error(f"❌ Failed to load miner driver {file_path.name}: {e}")
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
        
        logger.info(f"Loaded {len(self.drivers)} miner drivers: {list(self.drivers.keys())}")
    
    def get_driver(self, driver_type: str) -> Optional[BaseMinerAdapter]:
        """Get driver instance by type"""
        return self.drivers.get(driver_type)
    
    def get_all_drivers(self) -> Dict[str, BaseMinerAdapter]:
        """Get all loaded drivers"""
        return self.drivers.copy()
    
    def get_driver_info(self) -> List[Dict[str, Any]]:
        """Get metadata for all loaded drivers"""
        return [
            {
                "driver_type": driver.driver_type,
                "version": driver.driver_version,
                "display_name": driver.display_name,
                "manufacturer": driver.manufacturer,
                "models": driver.supported_models,
                "connection_type": driver.connection_type,
            }
            for driver in self.drivers.values()
        ]


# Global instance
_miner_loader: Optional[MinerDriverLoader] = None


def init_miner_loader(config_path: str = "/config"):
    """Initialize the global miner loader"""
    global _miner_loader
    _miner_loader = MinerDriverLoader(config_path)
    _miner_loader.load_drivers()
    return _miner_loader


def get_miner_loader() -> MinerDriverLoader:
    """Get the global miner loader instance"""
    global _miner_loader
    if _miner_loader is None:
        raise RuntimeError("Miner loader not initialized. Call init_miner_loader() first.")
    return _miner_loader
```

---

## Implementation Phases

### Phase 1: Foundation Setup (~6 hours)

**Objective:** Create infrastructure without breaking existing code

#### 1.1 Enhance Base Interface
- [ ] Add `driver_type`, `driver_version`, `display_name` to `BaseMinerAdapter`
- [ ] Add `manufacturer`, `supported_models`, `connection_type`
- [ ] Document all abstract methods clearly
- [ ] Add version `__version__ = "1.0.0"` to `base.py`

#### 1.2 Create Driver Loader
- [ ] Create `app/core/miner_driver_loader.py`
- [ ] Implement `MinerDriverLoader` class (copy pattern from `pool_loader.py`)
- [ ] Add global instance functions (`init_miner_loader`, `get_miner_loader`)
- [ ] Add comprehensive error logging with tracebacks

#### 1.3 Setup Directory Structure
- [ ] Create `bundled_config/miner_drivers/`
- [ ] Copy all existing adapters to `bundled_config/miner_drivers/`
- [ ] Rename files: `avalon_nano.py` → `avalon_nano_driver.py`
- [ ] Add `driver_type`, `driver_version` to each driver
- [ ] Create `TEMPLATE_miner_driver.py` with full documentation

#### 1.4 Initialize on Startup
- [ ] Add `init_miner_loader()` call to `app/main.py` startup
- [ ] Add logging: "🔌 Loading miner drivers..."
- [ ] Ensure it runs BEFORE scheduler starts

**Deliverable:** System loads drivers but doesn't use them yet (existing code still works)

---

### Phase 2: Core System Refactor (~12 hours)

**Objective:** Replace all hardcoded imports with driver loader calls

#### 2.1 Discovery System (`app/core/discovery.py`)

**Current:**
```python
from adapters.avalon_nano import AvalonNanoAdapter
from adapters.bitaxe import BitaxeAdapter

async def detect_miner_type(ip: str) -> Optional[str]:
    # Try each adapter
    if await AvalonNanoAdapter.detect(ip):
        return "avalon_nano"
    if await BitaxeAdapter.detect(ip):
        return "bitaxe"
```

**New:**
```python
from core.miner_driver_loader import get_miner_loader

async def detect_miner_type(ip: str) -> Optional[str]:
    loader = get_miner_loader()
    
    for driver_type, driver in loader.get_all_drivers().items():
        try:
            if await driver.connect(ip):
                return driver_type
        except Exception as e:
            logger.debug(f"Driver {driver_type} failed to connect to {ip}: {e}")
    
    return None
```

**Changes Required:**
- [ ] Remove all `from adapters.X` imports
- [ ] Use `get_miner_loader().get_driver(miner_type)` everywhere
- [ ] Update `_check_avalon_nano()`, `_check_bitaxe()`, etc. to generic pattern
- [ ] Update `verify_miner_connection()` to use drivers

#### 2.2 Telemetry Collection (`app/core/scheduler.py`)

**Current:**
```python
from adapters.avalon_nano import AvalonNanoAdapter

async def collect_telemetry():
    for miner in miners:
        if miner.miner_type == "avalon_nano":
            adapter = AvalonNanoAdapter(miner.ip, miner.port)
            data = await adapter.get_telemetry()
```

**New:**
```python
from core.miner_driver_loader import get_miner_loader

async def collect_telemetry():
    loader = get_miner_loader()
    
    for miner in miners:
        driver = loader.get_driver(miner.miner_type)
        if not driver:
            logger.warning(f"No driver found for miner type: {miner.miner_type}")
            continue
        
        # Create instance with connection details
        adapter = driver.__class__()
        await adapter.connect(miner.ip, miner.port)
        data = await adapter.get_telemetry()
```

**Changes Required:**
- [ ] Remove adapter imports
- [ ] Use driver loader for all adapters
- [ ] Update `_collect_telemetry_for_miner()` function
- [ ] Handle missing drivers gracefully

#### 2.3 Bulk Operations (`app/api/bulk.py`)

**Changes Required:**
- [ ] Remove adapter imports
- [ ] Update `set_mode_bulk()` to use driver loader
- [ ] Update `restart_bulk()` to use driver loader
- [ ] Update `set_pool_bulk()` to use driver loader

#### 2.4 Individual Miner Operations (`app/api/miners.py`)

**Changes Required:**
- [ ] Remove `from adapters import get_adapter_for_miner`
- [ ] Use `get_miner_loader().get_driver(miner.miner_type)` instead
- [ ] Update `set_mode()` endpoint
- [ ] Update `restart_miner()` endpoint
- [ ] Update `set_pool()` endpoint
- [ ] Update `get_miner_details()` endpoint

#### 2.5 Adapter Helper Functions (`app/adapters/__init__.py`)

**Current:**
```python
def get_adapter_for_miner(miner):
    if miner.miner_type == "avalon_nano":
        return AvalonNanoAdapter(miner.ip, miner.port)
    elif miner.miner_type == "bitaxe":
        return BitaxeAdapter(miner.ip, miner.port)
```

**New:**
```python
def get_adapter_for_miner(miner):
    """
    DEPRECATED: Use get_miner_loader().get_driver() instead.
    Kept for backward compatibility during migration.
    """
    from core.miner_driver_loader import get_miner_loader
    
    loader = get_miner_loader()
    driver = loader.get_driver(miner.miner_type)
    
    if not driver:
        raise ValueError(f"No driver found for miner type: {miner.miner_type}")
    
    # Create instance
    adapter = driver.__class__()
    # Note: Need to call connect() separately
    return adapter
```

**Changes Required:**
- [ ] Add deprecation warning
- [ ] Update to use driver loader
- [ ] Eventually remove this function entirely

---

### Phase 3: Driver Management UI (~4 hours)

#### 3.1 Backend API (`app/api/miner_driver_management.py`)

**New File - Endpoints:**
```python
@router.get("/drivers")
async def list_miner_drivers():
    """List all available miner drivers with versions"""
    pass

@router.get("/drivers/check-updates")
async def check_driver_updates():
    """Compare bundled vs config versions"""
    pass

@router.post("/drivers/update/{driver_name}")
async def update_miner_driver(driver_name: str):
    """Copy driver from bundled to config"""
    pass

@router.post("/drivers/update-all")
async def update_all_miner_drivers():
    """Update all drivers that have updates available"""
    pass
```

**Implementation:**
- [ ] Copy pattern from `app/api/driver_management.py` (pool drivers)
- [ ] Adapt for miner drivers
- [ ] Add version comparison logic
- [ ] Add file copy operations

#### 3.2 Frontend UI (`ui-react/src/pages/MinerDriverUpdates.tsx`)

**New React Page - Features:**
- Table showing all miner drivers
- Current version vs. available version
- "Update" button per driver
- "Update All" button
- Status indicators (up-to-date, update available, error)
- Warning: "Container restart required after updates"

**Implementation:**
- [ ] Copy `DriverUpdates.tsx` pattern
- [ ] Adapt API calls for `/api/miner-drivers/*` endpoints
- [ ] Update breadcrumbs and navigation
- [ ] Add to Settings menu

---

### Phase 4: Testing & Polish (~2 hours)

#### 4.1 Functional Testing

**Test Cases:**
- [ ] All 4 miner types still connect
- [ ] Telemetry collection works
- [ ] Mode switching works (Avalon, Bitaxe, NerdQaxe)
- [ ] Pool switching works (Avalon)
- [ ] Restart works
- [ ] Bulk operations work
- [ ] Discovery finds all miners
- [ ] Driver updates UI works

#### 4.2 Error Handling

**Edge Cases:**
- [ ] Missing driver file
- [ ] Driver fails to load (syntax error)
- [ ] Driver missing required attributes
- [ ] Version conflicts
- [ ] Partial update failures

#### 4.3 Documentation

**Updates Required:**
- [ ] Update `docs/first-run-deployment.md` with driver system
- [ ] Create `bundled_config/miner_drivers/README.md`
- [ ] Document `TEMPLATE_miner_driver.py` thoroughly
- [ ] Update API documentation
- [ ] Add migration guide for users

---

## File-by-File Changes

### Files to Create

| File | Purpose | Lines |
|------|---------|-------|
| `app/core/miner_driver_loader.py` | Driver loader system | ~200 |
| `app/api/miner_driver_management.py` | Driver update API | ~250 |
| `bundled_config/miner_drivers/README.md` | Driver dev guide | ~100 |
| `bundled_config/miner_drivers/TEMPLATE_miner_driver.py` | Driver template | ~400 |
| `bundled_config/miner_drivers/avalon_nano_driver.py` | Avalon driver | ~600 |
| `bundled_config/miner_drivers/bitaxe_driver.py` | Bitaxe driver | ~400 |
| `bundled_config/miner_drivers/nerdqaxe_driver.py` | NerdQaxe driver | ~350 |
| `bundled_config/miner_drivers/nmminer_driver.py` | NMMiner driver | ~300 |
| `ui-react/src/pages/MinerDriverUpdates.tsx` | Update UI | ~400 |

**Total New Code: ~3,000 lines**

### Files to Modify

| File | Changes | Complexity |
|------|---------|------------|
| `app/adapters/base.py` | Add metadata fields | Low |
| `app/adapters/__init__.py` | Deprecate helper | Low |
| `app/main.py` | Add init_miner_loader() call | Low |
| `app/core/discovery.py` | Replace imports, use loader | Medium |
| `app/core/scheduler.py` | Replace imports, use loader | High |
| `app/api/miners.py` | Replace adapter calls | Medium |
| `app/api/bulk.py` | Replace adapter calls | Medium |
| `app/api/operations.py` | Replace adapter calls | Low |
| `app/api/settings.py` | Add driver info endpoint | Low |
| `ui-react/src/components/Layout.tsx` | Add menu item | Low |

**Total Files Modified: ~10**

---

## Testing Strategy

### Unit Tests

```python
# tests/test_miner_driver_loader.py

async def test_load_avalon_driver():
    loader = MinerDriverLoader("/config")
    loader.load_drivers()
    
    driver = loader.get_driver("avalon_nano")
    assert driver is not None
    assert driver.driver_type == "avalon_nano"
    assert driver.driver_version is not None

async def test_driver_telemetry():
    loader = MinerDriverLoader("/config")
    loader.load_drivers()
    
    driver = loader.get_driver("bitaxe")
    adapter = driver.__class__()
    await adapter.connect("10.0.0.100", 80)
    
    data = await adapter.get_telemetry()
    assert "hashrate" in data
    assert "temperature" in data
```

### Integration Tests

```python
# tests/integration/test_discovery_with_drivers.py

async def test_discover_avalon_nano():
    init_miner_loader()
    
    result = await detect_miner_type("10.0.0.50")
    assert result == "avalon_nano"

async def test_telemetry_collection_with_drivers():
    init_miner_loader()
    
    # Mock miner in database
    miner = await create_test_miner(miner_type="bitaxe")
    
    # Collect telemetry
    await collect_telemetry()
    
    # Verify data was stored
    telemetry = await get_latest_telemetry(miner.id)
    assert telemetry is not None
```

### Manual Testing Checklist

- [ ] Connect to each miner type via discovery
- [ ] View telemetry in dashboard
- [ ] Switch modes on Avalon
- [ ] Switch modes on Bitaxe
- [ ] Restart miner
- [ ] Update single driver via UI
- [ ] Update all drivers via UI
- [ ] Restart container and verify drivers reload

---

## Migration Path

### For Development

1. **Branch:** Create `feature/miner-driver-system`
2. **Phase 1:** Build infrastructure (non-breaking)
3. **Test:** Verify drivers load but existing code works
4. **Phase 2:** Refactor core system (breaking changes)
5. **Test:** Comprehensive testing of all miner operations
6. **Phase 3:** Add UI
7. **Merge:** To main after full testing

### For Production Deployments

**Option A: Automatic Migration (Recommended)**
```python
# In app/main.py startup

async def migrate_adapters_to_drivers():
    """One-time migration: copy adapters to driver directory"""
    drivers_path = Path("/config/miner_drivers")
    bundled_path = Path("/app/bundled_config/miner_drivers")
    
    if not drivers_path.exists():
        logger.info("🔄 Migrating adapters to driver system...")
        drivers_path.mkdir(parents=True, exist_ok=True)
        
        for bundled_file in bundled_path.glob("*_driver.py"):
            target_file = drivers_path / bundled_file.name
            shutil.copy2(bundled_file, target_file)
            logger.info(f"  ✓ Copied {bundled_file.name}")
        
        logger.info("✅ Migration complete")
```

**Option B: Manual Update (UI)**
- User sees "4 new miner drivers available"
- Click "Install All Drivers"
- System copies from bundled to config
- Restart container

---

## Rollout Plan

### Pre-Release (v0.9.x)

- [ ] Complete Phase 1 (foundation)
- [ ] Internal testing
- [ ] Deploy to development environment

### Release Candidate (v1.0.0-rc1)

- [ ] Complete Phase 2 (refactor)
- [ ] Complete Phase 3 (UI)
- [ ] Deploy to staging
- [ ] Community beta testing

### Production Release (v1.0.0)

- [ ] All tests passing
- [ ] Documentation complete
- [ ] Migration tested on live systems
- [ ] GitHub Actions build successful
- [ ] Deploy to production

### Post-Release

- [ ] Monitor for driver loading errors
- [ ] Collect feedback on driver update UX
- [ ] Create community guide for contributing drivers
- [ ] Build example driver for custom hardware

---

## Risk Assessment

### High Risk Areas

**Telemetry Collection**
- Risk: Scheduler crashes if driver fails
- Mitigation: Comprehensive try/catch, fallback to skip miner

**Discovery System**
- Risk: Can't detect miners with new driver system
- Mitigation: Extensive testing with real hardware

**Bulk Operations**
- Risk: Partial failures if some drivers don't load
- Mitigation: Track failures, report to user

### Low Risk Areas

- UI changes (additive, no breaking changes)
- Driver loader (isolated, doesn't affect existing code initially)
- Documentation updates

---

## Success Criteria

### Functional Requirements
- [ ] All 4 miner types connect and collect telemetry
- [ ] Discovery finds miners automatically
- [ ] Mode switching works for all miners
- [ ] Pool switching works for Avalon
- [ ] Restart works for all miners
- [ ] Driver updates work via UI
- [ ] Zero performance degradation

### Non-Functional Requirements
- [ ] Code is well-documented
- [ ] Driver template is comprehensive
- [ ] Migration is seamless for users
- [ ] Error messages are helpful
- [ ] Logs show clear driver loading status

---

## Future Enhancements

### v1.1: Community Drivers
- Driver marketplace in UI
- Import drivers from GitHub
- Driver safety validation
- Driver signing/verification

### v1.2: Advanced Features
- Driver hot-reload (no restart required)
- Driver A/B testing
- Driver rollback on failure
- Driver performance metrics

### v1.3: Developer Tools
- Driver development CLI
- Driver testing framework
- Mock hardware simulator
- Driver debugging tools

---

## Appendix A: Driver Template Example

```python
"""
Template Miner Driver
Copy this file to create a new miner driver.

Steps:
1. Copy TEMPLATE_miner_driver.py to yourdevice_driver.py
2. Replace "template" with your device name
3. Update driver_type, display_name, manufacturer
4. Implement all abstract methods
5. Test thoroughly
6. Place in /config/miner_drivers/
7. Restart container
"""

__version__ = "1.0.0"

import logging
import aiohttp
from typing import Optional, Dict, Any, List

from adapters.base import BaseMinerAdapter

logger = logging.getLogger(__name__)


class TemplateMinerDriver(BaseMinerAdapter):
    """Template miner driver - replace with your implementation."""
    
    # Driver metadata (REQUIRED)
    driver_type = "template"  # Unique identifier (lowercase, no spaces)
    driver_version = "1.0.0"  # Semantic versioning
    display_name = "Template Miner"  # Human-readable name
    manufacturer = "ACME Corp"  # Manufacturer name
    supported_models = ["Model X", "Model Y"]  # List of supported models
    
    # Connection details
    connection_type = "http"  # "http", "tcp", or "udp"
    default_port = 80
    
    def __init__(self):
        self.ip = None
        self.port = None
        self.session = None
    
    async def connect(self, ip: str, port: int = None) -> bool:
        """
        Test connection to miner.
        
        Returns:
            True if connection successful, False otherwise
        """
        self.ip = ip
        self.port = port or self.default_port
        
        try:
            # Example: HTTP GET request
            self.session = aiohttp.ClientSession()
            async with self.session.get(
                f"http://{self.ip}:{self.port}/api/info",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                return response.status == 200
        
        except Exception as e:
            logger.debug(f"Connection failed: {e}")
            return False
    
    async def get_telemetry(self) -> Dict[str, Any]:
        """
        Get current telemetry data.
        
        MUST return dict with keys:
        - hashrate (float): Hashrate in H/s (NOT TH/s or GH/s)
        - temperature (float): Temperature in Celsius
        - power (float): Power consumption in watts
        - uptime (int): Uptime in seconds
        - mode (str): Current power mode
        """
        async with self.session.get(
            f"http://{self.ip}:{self.port}/api/telemetry"
        ) as response:
            data = await response.json()
            
            return {
                "hashrate": float(data["hashrate"]),  # Convert to H/s!
                "temperature": float(data["temp"]),
                "power": float(data["power_watts"]),
                "uptime": int(data["uptime_seconds"]),
                "mode": data.get("mode", "unknown")
            }
    
    async def get_pool_info(self) -> Dict[str, Any]:
        """Get current pool configuration."""
        async with self.session.get(
            f"http://{self.ip}:{self.port}/api/pool"
        ) as response:
            data = await response.json()
            
            return {
                "pool_url": data["url"],
                "pool_user": data["user"],
                "pool_pass": data["pass"]
            }
    
    async def set_mode(self, mode: str) -> bool:
        """
        Set power mode.
        
        Args:
            mode: One of self.get_supported_modes()
        """
        async with self.session.post(
            f"http://{self.ip}:{self.port}/api/mode",
            json={"mode": mode}
        ) as response:
            return response.status == 200
    
    async def restart(self) -> bool:
        """Restart the miner."""
        async with self.session.post(
            f"http://{self.ip}:{self.port}/api/restart"
        ) as response:
            return response.status == 200
    
    async def set_pool(self, url: str, user: str, password: str) -> bool:
        """Set pool configuration."""
        async with self.session.post(
            f"http://{self.ip}:{self.port}/api/pool",
            json={
                "url": url,
                "user": user,
                "pass": password
            }
        ) as response:
            return response.status == 200
    
    def get_supported_modes(self) -> List[str]:
        """Get list of supported power modes."""
        return ["low", "medium", "high"]
    
    def supports_tuning(self) -> bool:
        """Does this miner support tuning profiles?"""
        return False
    
    async def close(self):
        """Clean up resources."""
        if self.session:
            await self.session.close()
```

---

## Appendix B: Comparison with Pool Driver System

| Aspect | Pool Drivers | Miner Drivers |
|--------|-------------|---------------|
| **Base Class** | `BasePoolIntegration` | `BaseMinerAdapter` |
| **Loader** | `PoolDriverLoader` | `MinerDriverLoader` |
| **Directory** | `/config/drivers/` | `/config/miner_drivers/` |
| **Bundled** | `bundled_config/drivers/` | `bundled_config/miner_drivers/` |
| **Naming** | `*_driver.py` | `*_driver.py` |
| **Versioning** | `__version__` | `driver_version` |
| **UI Path** | `/settings/driver-updates` | `/settings/miner-driver-updates` |
| **API Path** | `/api/drivers/*` | `/api/miner-drivers/*` |
| **Usage** | Dashboard tiles, stats | Telemetry, control |
| **Frequency** | Low (API calls) | High (every 30s) |

---

## Questions for Decision

1. **Should we deprecate old adapter imports immediately or gradually?**
   - Immediate: Cleaner, faster migration
   - Gradual: Safer, backward compatible

2. **Should miner drivers be hot-reloadable without restart?**
   - Pros: Better UX
   - Cons: More complex, potential state issues

3. **Should we version the `BaseMinerAdapter` interface itself?**
   - Allows interface evolution
   - Drivers declare which version they support

4. **Should drivers be sandboxed for security?**
   - Prevents malicious drivers
   - Adds complexity

---

**End of Document**

*Ready to begin Phase 1 implementation when approved.*
