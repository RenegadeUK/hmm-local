from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path


# Ensure app/ is importable when tests run from repo root
APP_ROOT = Path(__file__).resolve().parents[1] / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


def test_derive_pool_warnings_semantics() -> None:
    from core.pool_warnings import derive_pool_warnings

    assert derive_pool_warnings(None, False) == ["driver_unresolved"]
    assert derive_pool_warnings("unknown", True) == ["driver_unresolved"]
    assert derive_pool_warnings("solopool", False) == ["driver_not_loaded"]
    assert derive_pool_warnings("solopool", True) == []


if "core.database" not in sys.modules:
    db_mod = types.ModuleType("core.database")

    class _Pool:  # pragma: no cover - import scaffold
        pass

    class _BlockFound:  # pragma: no cover - import scaffold
        pass

    db_mod.Pool = _Pool
    db_mod.BlockFound = _BlockFound
    sys.modules["core.database"] = db_mod

if "core.pool_loader" not in sys.modules:
    loader_mod = types.ModuleType("core.pool_loader")
    loader_mod.get_pool_loader = lambda: None
    sys.modules["core.pool_loader"] = loader_mod

from core.dashboard_pool_service import DashboardPoolService


class _FakePool:
    def __init__(self, pool_type: str = "unknown"):
        self.name = "Test Pool"
        self.url = "10.0.0.2"
        self.port = 3335
        self.pool_type = pool_type
        self.pool_config = {}


class _FakeDB:
    def __init__(self):
        self.commits = 0
        self.refreshes = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def refresh(self, _pool):
        self.refreshes += 1

    async def rollback(self):
        self.rollbacks += 1


class _Driver:
    def __init__(self, should_detect: bool):
        self._should_detect = should_detect
        self.calls = 0

    async def detect(self, _url: str, _port: int) -> bool:
        self.calls += 1
        return self._should_detect


class _SequenceDriver:
    def __init__(self, sequence: list[bool]):
        self._sequence = list(sequence)
        self.calls = 0

    async def detect(self, _url: str, _port: int) -> bool:
        self.calls += 1
        if not self._sequence:
            return False
        return self._sequence.pop(0)


class _Loader:
    def __init__(self, drivers):
        self.drivers = drivers


def test_recover_pool_driver_persists_detected_type() -> None:
    pool = _FakePool(pool_type="unknown")
    db = _FakeDB()
    loader = _Loader(
        {
            "hmm_local_stratum": _Driver(True),
            "solopool": _Driver(False),
        }
    )

    resolved = asyncio.run(DashboardPoolService._recover_pool_driver(pool, db, loader))

    assert resolved == "hmm_local_stratum"
    assert pool.pool_type == "hmm_local_stratum"
    assert pool.pool_config.get("driver") == "hmm_local_stratum"
    assert db.commits == 1
    assert db.refreshes == 1
    assert db.rollbacks == 0


def test_recover_pool_driver_marks_unknown_when_unresolved() -> None:
    pool = _FakePool(pool_type="unknown")
    db = _FakeDB()
    loader = _Loader({"solopool": _Driver(False)})

    resolved = asyncio.run(DashboardPoolService._recover_pool_driver(pool, db, loader))

    assert resolved is None
    assert pool.pool_type == "unknown"
    assert pool.pool_config.get("driver") == "unknown"
    assert db.commits == 1
    assert db.refreshes == 0
    assert db.rollbacks == 0


def test_recover_pool_driver_retries_and_recovers_after_transient_failure() -> None:
    pool = _FakePool(pool_type="unknown")
    db = _FakeDB()
    flaky_driver = _SequenceDriver([False, True])
    loader = _Loader({"hmm_local_stratum": flaky_driver})

    resolved = asyncio.run(DashboardPoolService._recover_pool_driver(pool, db, loader))

    assert resolved == "hmm_local_stratum"
    assert pool.pool_type == "hmm_local_stratum"
    assert pool.pool_config.get("driver") == "hmm_local_stratum"
    assert flaky_driver.calls == 2
    assert db.commits == 1
    assert db.refreshes == 1
