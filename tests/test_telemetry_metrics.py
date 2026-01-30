import json
from pathlib import Path

from core import telemetry_metrics
from core.config import settings


def _set_paths(tmp_path: Path):
    settings.CONFIG_DIR = tmp_path
    telemetry_metrics.METRICS_PATH = tmp_path / "telemetry_metrics.json"


def test_telemetry_metrics_peaks(tmp_path):
    _set_paths(tmp_path)

    telemetry_metrics.update_concurrency_peak(4)
    telemetry_metrics.update_backlog(7)

    metrics = telemetry_metrics.get_metrics()

    assert metrics.last_24h.peak_concurrency == 4
    assert metrics.last_24h.max_backlog == 7
    assert metrics.since_boot.peak_concurrency == 4
    assert metrics.since_boot.max_backlog == 7

    assert telemetry_metrics.METRICS_PATH.exists()
    data = json.loads(telemetry_metrics.METRICS_PATH.read_text())
    assert "last_24h" in data
    assert "since_boot" in data
