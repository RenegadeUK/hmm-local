from __future__ import annotations

import asyncio
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

import pytest


APP_ROOT = Path(__file__).resolve().parents[1] / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


if "core.config" not in sys.modules:
    config_mod = types.ModuleType("core.config")

    class _Config:
        @staticmethod
        def get(_key, default=None):
            return default

        @staticmethod
        def set(_key, _value):
            return None

        @staticmethod
        def save():
            return None

    config_mod.app_config = _Config()
    sys.modules["core.config"] = config_mod


if "core.utils" not in sys.modules:
    utils_mod = types.ModuleType("core.utils")
    utils_mod.format_hashrate = lambda value, unit="TH": f"{value}{unit}"
    sys.modules["core.utils"] = utils_mod


if "core.database" not in sys.modules:
    db_mod = types.ModuleType("core.database")

    class _Miner:
        pass

    class _Telemetry:
        pass

    class _Event:
        pass

    class _CryptoPrice:
        pass

    async def _get_db():
        yield None

    class _AsyncSessionLocal:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, _query):
            class _Scalars:
                @staticmethod
                def all():
                    return []

            class _Result:
                @staticmethod
                def scalars():
                    return _Scalars()

            return _Result()

    db_mod.get_db = _get_db
    db_mod.Miner = _Miner
    db_mod.Telemetry = _Telemetry
    db_mod.Event = _Event
    db_mod.CryptoPrice = _CryptoPrice
    db_mod.AsyncSessionLocal = _AsyncSessionLocal
    sys.modules["core.database"] = db_mod


import api.settings as settings_module


class _FakeCryptoPrice:
    def __init__(self, coin_id: str, price_gbp: float, source: str = "coingecko"):
        self.coin_id = coin_id
        self.price_gbp = price_gbp
        self.source = source
        self.updated_at = datetime.utcnow() - timedelta(minutes=5)


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _query):
        return _FakeResult(self._rows)


class _FakeAsyncSessionLocal:
    def __init__(self, rows):
        self._session = _FakeSession(rows)

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_crypto_prices_uses_bitcoinii_key(monkeypatch: pytest.MonkeyPatch):
    rows = [
        _FakeCryptoPrice("bitcoin", 95000.0),
        _FakeCryptoPrice("bitcoin-cash", 460.0),
        _FakeCryptoPrice("bitcoinii", 0.59),
        _FakeCryptoPrice("bellscoin", 0.04),
        _FakeCryptoPrice("digibyte", 0.01),
    ]

    monkeypatch.setattr(settings_module, "select", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(settings_module, "AsyncSessionLocal", lambda: _FakeAsyncSessionLocal(rows))

    result = asyncio.run(settings_module.get_crypto_prices())

    assert result["success"] is True
    assert result["bitcoinii"] == pytest.approx(0.59)
    assert "bellscoin" not in result
