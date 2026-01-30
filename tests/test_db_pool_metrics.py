import json
from pathlib import Path

from core import db_pool_metrics
from core.config import settings


def _set_paths(tmp_path: Path):
    settings.CONFIG_DIR = tmp_path
    db_pool_metrics.METRICS_PATH = tmp_path / "db_pool_metrics.json"


def test_db_pool_metrics_peaks_and_timeouts(tmp_path):
    _set_paths(tmp_path)

    db_pool_metrics.update_peaks(in_use=3, active_queries=2, slow_queries=1)
    db_pool_metrics.record_pool_timeout(2.5)

    metrics = db_pool_metrics.get_metrics()

    assert metrics.last_24h.db_pool_in_use_peak == 3
    assert metrics.last_24h.active_queries_peak == 2
    assert metrics.last_24h.slow_query_count == 1
    assert metrics.last_24h.db_pool_wait_count == 1
    assert metrics.last_24h.db_pool_wait_seconds_sum >= 2.5

    assert metrics.since_boot.db_pool_in_use_peak == 3
    assert metrics.since_boot.active_queries_peak == 2
    assert metrics.since_boot.slow_query_count == 1
    assert metrics.since_boot.db_pool_wait_count == 1

    assert db_pool_metrics.METRICS_PATH.exists()
    data = json.loads(db_pool_metrics.METRICS_PATH.read_text())
    assert "last_24h" in data
    assert "since_boot" in data
