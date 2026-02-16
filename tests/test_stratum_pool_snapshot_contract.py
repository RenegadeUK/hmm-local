from __future__ import annotations

import runpy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine


ROOT = Path(__file__).resolve().parents[1]
STRATUM_MAIN = ROOT / "stratum" / "main.py"
MOD = runpy.run_path(str(STRATUM_MAIN))


def _seed_minimal_dgb_snapshot_data(ds) -> None:
    now = datetime.now(timezone.utc)
    minute_ts = now.replace(second=0, microsecond=0)

    with ds.engine.begin() as conn:
        ds.metadata.create_all(conn)

        conn.execute(
            ds.hashrate_snapshots.insert(),
            [
                {
                    "ts": minute_ts,
                    "coin": "DGB",
                    "worker": "__pool__",
                    "window_minutes": 15,
                    "accepted_shares": 100,
                    "accepted_diff_sum": 409600.0,
                    "est_hashrate_hs": 1.95e12,
                    "created_at": now,
                },
                {
                    "ts": minute_ts,
                    "coin": "DGB",
                    "worker": "workerA",
                    "window_minutes": 15,
                    "accepted_shares": 60,
                    "accepted_diff_sum": 245760.0,
                    "est_hashrate_hs": 1.2e12,
                    "created_at": now,
                },
            ],
        )

        conn.execute(
            ds.network_snapshots.insert(),
            {
                "ts": now,
                "coin": "DGB",
                "chain_height": 123,
                "template_height": 124,
                "job_id": "job123",
                "bits": "19073ad2",
                "network_target": "00" * 32,
                "network_difficulty": 1000000.0,
                "network_hash_ps": 8.0e12,
                "template_previous_blockhash": "00" * 32,
                "template_curtime": int(now.timestamp()),
                "template_changed": True,
                "created_at": now,
            },
        )

        conn.execute(
            ds.kpi_snapshots.insert(),
            {
                "ts": minute_ts,
                "coin": "DGB",
                "window_minutes": 15,
                "pool_hashrate_hs": 1.95e12,
                "network_hash_ps": 8.0e12,
                "network_difficulty": 1000000.0,
                "share_accept_count": 100,
                "share_reject_count": 3,
                "share_reject_rate_pct": 2.9126,
                "block_accept_count_24h": 0,
                "block_reject_count_24h": 0,
                "block_accept_rate_pct_24h": None,
                "expected_time_to_block_sec": 2200.0,
                "pool_share_of_network_pct": 24.375,
                "created_at": now,
            },
        )

        conn.execute(
            ds.share_metrics.insert(),
            [
                {
                    "ts": now - timedelta(minutes=1),
                    "coin": "DGB",
                    "worker": "workerA",
                    "job_id": "job123",
                    "assigned_diff": 4096.0,
                    "computed_diff": 5120.0,
                    "accepted": False,
                    "reject_reason": "low_difficulty_share",
                },
                {
                    "ts": now - timedelta(minutes=2),
                    "coin": "DGB",
                    "worker": "workerA",
                    "job_id": "job123",
                    "assigned_diff": 4096.0,
                    "computed_diff": 5200.0,
                    "accepted": False,
                    "reject_reason": "duplicate_share",
                },
            ],
        )


def test_pool_snapshot_contract_and_freshness_fields() -> None:
    ds = MOD["_DATASTORE"]
    old_enabled = ds.enabled
    old_engine = ds.engine

    try:
        ds.enabled = True
        ds.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        _seed_minimal_dgb_snapshot_data(ds)

        payload = MOD["_build_pool_snapshot_sync"]("DGB", window_minutes=15)

        assert payload["ok"] is True
        assert payload["coin"] == "DGB"
        assert payload["workers"]["count"] >= 1

        quality = payload["quality"]
        assert "data_freshness_seconds" in quality
        assert "has_required_inputs" in quality
        assert "stale" in quality
        assert quality["has_required_inputs"] is True
        assert quality["readiness"] == "ready"
        assert quality["missing_inputs"] == []

        # Validate strict response model compatibility.
        model = MOD["PoolSnapshotResponse"].model_validate(payload)
        assert model.coin == "DGB"
    finally:
        if ds.engine is not None:
            ds.engine.dispose()
        ds.enabled = old_enabled
        ds.engine = old_engine


def test_pool_snapshot_marks_unready_when_inputs_missing() -> None:
    ds = MOD["_DATASTORE"]
    old_enabled = ds.enabled
    old_engine = ds.engine

    try:
        ds.enabled = True
        ds.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        with ds.engine.begin() as conn:
            ds.metadata.create_all(conn)

        payload = MOD["_build_pool_snapshot_sync"]("BTC", window_minutes=15)
        quality = payload["quality"]

        assert quality["has_required_inputs"] is False
        assert quality["stale"] is True
        assert quality["readiness"] == "unready"
        assert set(quality["missing_inputs"]) == {"hashrate", "network", "kpi"}
    finally:
        if ds.engine is not None:
            ds.engine.dispose()
        ds.enabled = old_enabled
        ds.engine = old_engine


def test_pool_snapshot_routes_have_response_models() -> None:
    app = MOD["app"]
    route_models = {
        route.path: getattr(route, "response_model", None)
        for route in app.routes
        if hasattr(route, "path")
    }

    assert route_models.get("/api/pool-snapshot/{coin}") is MOD["PoolSnapshotResponse"]
    assert route_models.get("/api/pool-snapshot") is MOD["PoolSnapshotCollectionResponse"]
