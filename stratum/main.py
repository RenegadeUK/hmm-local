"""
HMM-Local Stratum Gateway (Scaffold)

Companion service that will host local Stratum endpoints for:
- BTC
- BCH
- DGB (SHA256d only)

This scaffold provides:
- TCP listeners with minimal Stratum v1 method handling
- Runtime worker/share stats
- HTTP API for health and stats

Node RPC/template integration is intentionally deferred to follow-up iterations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("hmm_local_stratum")

CONFIG_PATH = os.getenv("STRATUM_CONFIG_PATH", "/config/stratum_gateway.json")


@dataclass
class CoinConfig:
    coin: str
    algo: str
    stratum_port: int
    rpc_url: str
    rpc_user: str
    rpc_password: str


@dataclass
class CoinRuntimeStats:
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    connected_workers: int = 0
    total_connections: int = 0
    shares_submitted: int = 0
    shares_accepted: int = 0
    shares_rejected: int = 0
    last_share_at: str | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "connected_workers": self.connected_workers,
            "total_connections": self.total_connections,
            "shares_submitted": self.shares_submitted,
            "shares_accepted": self.shares_accepted,
            "shares_rejected": self.shares_rejected,
            "last_share_at": self.last_share_at,
        }


class StratumServer:
    """Minimal Stratum v1 TCP server scaffold for one coin."""

    def __init__(self, config: CoinConfig, bind_host: str = "0.0.0.0"):
        self.config = config
        self.bind_host = bind_host
        self.server: asyncio.AbstractServer | None = None
        self.stats = CoinRuntimeStats()
        self._sub_counter = 0

    async def start(self) -> None:
        self.server = await asyncio.start_server(
            self._handle_client,
            host=self.bind_host,
            port=self.config.stratum_port,
        )
        logger.info(
            "Started %s stratum listener on %s:%s (algo=%s)",
            self.config.coin,
            self.bind_host,
            self.config.stratum_port,
            self.config.algo,
        )

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Stopped %s stratum listener", self.config.coin)

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        self.stats.connected_workers += 1
        self.stats.total_connections += 1
        logger.info("%s client connected: %s", self.config.coin, peer)

        try:
            while not reader.at_eof():
                raw = await reader.readline()
                if not raw:
                    break

                message = raw.decode("utf-8", errors="ignore").strip()
                if not message:
                    continue

                try:
                    req = json.loads(message)
                except json.JSONDecodeError:
                    await self._write_json(writer, self._error(None, -32700, "Parse error"))
                    continue

                response = await self._handle_request(req)
                if response is not None:
                    await self._write_json(writer, response)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("%s client handler error (%s): %s", self.config.coin, peer, exc)
        finally:
            self.stats.connected_workers = max(0, self.stats.connected_workers - 1)
            writer.close()
            await writer.wait_closed()
            logger.info("%s client disconnected: %s", self.config.coin, peer)

    async def _handle_request(self, req: dict[str, Any]) -> dict[str, Any] | None:
        req_id = req.get("id")
        method = req.get("method")

        if method == "mining.subscribe":
            self._sub_counter += 1
            sub_id = f"{self.config.coin.lower()}-sub-{self._sub_counter}"
            return {
                "id": req_id,
                "result": [
                    [["mining.notify", sub_id], ["mining.set_difficulty", sub_id]],
                    f"{self.config.coin.lower()}-ex1",
                    4,
                ],
                "error": None,
            }

        if method == "mining.authorize":
            return {"id": req_id, "result": True, "error": None}

        if method == "mining.extranonce.subscribe":
            return {"id": req_id, "result": True, "error": None}

        if method == "mining.submit":
            self.stats.shares_submitted += 1
            self.stats.shares_accepted += 1
            self.stats.last_share_at = datetime.now(timezone.utc).isoformat()
            # NOTE: scaffold behavior accepts shares; validation against templates deferred.
            return {"id": req_id, "result": True, "error": None}

        return self._error(req_id, -32601, f"Method not found: {method}")

    async def _write_json(self, writer: asyncio.StreamWriter, payload: dict[str, Any]) -> None:
        writer.write((json.dumps(payload) + "\n").encode("utf-8"))
        await writer.drain()

    @staticmethod
    def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "id": req_id,
            "result": None,
            "error": [code, message, None],
        }


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _load_coin_configs() -> dict[str, CoinConfig]:
    dgb_algo = os.getenv("DGB_ALGO", "sha256d").strip().lower()
    if dgb_algo != "sha256d":
        logger.warning("DGB_ALGO=%s is unsupported; forcing sha256d", dgb_algo)
        dgb_algo = "sha256d"

    return {
        "BTC": CoinConfig(
            coin="BTC",
            algo="sha256d",
            stratum_port=_env_int("BTC_STRATUM_PORT", 3333),
            rpc_url=os.getenv("BTC_RPC_URL", "http://host.docker.internal:8332"),
            rpc_user=os.getenv("BTC_RPC_USER", ""),
            rpc_password=os.getenv("BTC_RPC_PASSWORD", ""),
        ),
        "BCH": CoinConfig(
            coin="BCH",
            algo="sha256d",
            stratum_port=_env_int("BCH_STRATUM_PORT", 3334),
            rpc_url=os.getenv("BCH_RPC_URL", "http://host.docker.internal:8333"),
            rpc_user=os.getenv("BCH_RPC_USER", ""),
            rpc_password=os.getenv("BCH_RPC_PASSWORD", ""),
        ),
        "DGB": CoinConfig(
            coin="DGB",
            algo=dgb_algo,
            stratum_port=_env_int("DGB_STRATUM_PORT", 3335),
            rpc_url=os.getenv("DGB_RPC_URL", "http://host.docker.internal:14022"),
            rpc_user=os.getenv("DGB_RPC_USER", ""),
            rpc_password=os.getenv("DGB_RPC_PASSWORD", ""),
        ),
    }


def _serialize_config(configs: dict[str, CoinConfig]) -> dict[str, Any]:
    return {
        coin: {
            "rpc_url": cfg.rpc_url,
            "rpc_user": cfg.rpc_user,
            "rpc_password": cfg.rpc_password,
            "stratum_port": cfg.stratum_port,
            "algo": cfg.algo,
        }
        for coin, cfg in configs.items()
    }


def _load_overrides_from_disk(configs: dict[str, CoinConfig]) -> dict[str, CoinConfig]:
    if not os.path.exists(CONFIG_PATH):
        return configs

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)

        for coin in ("BTC", "BCH", "DGB"):
            if coin not in payload:
                continue
            row = payload[coin] or {}
            cfg = configs[coin]
            cfg.rpc_url = str(row.get("rpc_url") or cfg.rpc_url)
            cfg.rpc_user = str(row.get("rpc_user") or cfg.rpc_user)
            cfg.rpc_password = str(row.get("rpc_password") or cfg.rpc_password)
            if row.get("stratum_port"):
                try:
                    cfg.stratum_port = int(row["stratum_port"])
                except (TypeError, ValueError):
                    logger.warning("Invalid %s stratum_port override: %s", coin, row.get("stratum_port"))

        # DGB is SHA256d only.
        configs["DGB"].algo = "sha256d"
        return configs
    except Exception as exc:
        logger.error("Failed loading stratum config overrides (%s): %s", CONFIG_PATH, exc)
        return configs


def _save_overrides_to_disk(configs: dict[str, CoinConfig]) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(_serialize_config(configs), f, indent=2)


app = FastAPI(title="HMM-Local Stratum Gateway", version="0.1.0")

_BIND_HOST = os.getenv("STRATUM_BIND_HOST", "0.0.0.0")
_CONFIGS = _load_overrides_from_disk(_load_coin_configs())
_SERVERS: dict[str, StratumServer] = {
    coin: StratumServer(config=cfg, bind_host=_BIND_HOST)
    for coin, cfg in _CONFIGS.items()
}


async def _restart_servers() -> None:
    for server in _SERVERS.values():
        await server.stop()
    for coin, cfg in _CONFIGS.items():
        _SERVERS[coin] = StratumServer(config=cfg, bind_host=_BIND_HOST)
    for server in _SERVERS.values():
        await server.start()


@app.on_event("startup")
async def startup_event() -> None:
    for server in _SERVERS.values():
        await server.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    for server in _SERVERS.values():
        await server.stop()


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "healthy",
        "service": "hmm-local-stratum",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "coins": {
            coin: {
                "algo": server.config.algo,
                "stratum_port": server.config.stratum_port,
            }
            for coin, server in _SERVERS.items()
        },
    }


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
        return """
<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>HMM Local Stratum</title>
    <style>
        body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; background: #0f172a; color: #e2e8f0; }
        .wrap { max-width: 980px; margin: 24px auto; padding: 0 16px; }
        .card { background: #111827; border: 1px solid #334155; border-radius: 12px; padding: 16px; margin-bottom: 16px; }
        h1 { margin: 0 0 12px; font-size: 24px; }
        h2 { margin: 0 0 12px; font-size: 18px; }
        .grid { display: grid; grid-template-columns: 120px 1fr 1fr 1fr; gap: 8px; align-items: center; }
        label { color: #94a3b8; font-size: 13px; }
        input { width: 100%; padding: 8px; border-radius: 8px; border: 1px solid #475569; background: #0b1220; color: #e2e8f0; }
        button { background: #2563eb; color: white; border: 0; padding: 10px 14px; border-radius: 8px; cursor: pointer; }
        button.secondary { background: #334155; }
        .row { display: flex; gap: 8px; margin-top: 12px; }
        pre { background: #020617; border: 1px solid #334155; border-radius: 8px; padding: 10px; overflow: auto; }
        .muted { color: #94a3b8; font-size: 13px; }
    </style>
</head>
<body>
    <div class=\"wrap\">
        <div class=\"card\">
            <h1>HMM Local Stratum Gateway</h1>
            <div class=\"muted\">DGB is locked to SHA256d. Save applies immediately and restarts listeners.</div>
        </div>

        <div class=\"card\">
            <h2>RPC Configuration</h2>
            <div class=\"grid\" style=\"font-weight:600;\"><div>Coin</div><div>RPC URL</div><div>RPC User</div><div>RPC Password</div></div>
            <div class=\"grid\" style=\"margin-top:8px;\">
                <label>BTC</label><input id=\"BTC_rpc_url\" /><input id=\"BTC_rpc_user\" /><input id=\"BTC_rpc_password\" type=\"password\" />
                <label>BCH</label><input id=\"BCH_rpc_url\" /><input id=\"BCH_rpc_user\" /><input id=\"BCH_rpc_password\" type=\"password\" />
                <label>DGB</label><input id=\"DGB_rpc_url\" /><input id=\"DGB_rpc_user\" /><input id=\"DGB_rpc_password\" type=\"password\" />
            </div>
            <div class=\"row\">
                <button onclick=\"saveConfig()\">Save + Restart Listeners</button>
                <button class=\"secondary\" onclick=\"loadConfig()\">Reload</button>
            </div>
            <div id=\"status\" class=\"muted\" style=\"margin-top:8px;\"></div>
        </div>

        <div class=\"card\">
            <h2>Live Stats</h2>
            <pre id=\"stats\">loading...</pre>
        </div>
    </div>

    <script>
        async function loadConfig() {
            const r = await fetch('/config');
            const cfg = await r.json();
            for (const coin of ['BTC','BCH','DGB']) {
                document.getElementById(`${coin}_rpc_url`).value = cfg[coin].rpc_url || '';
                document.getElementById(`${coin}_rpc_user`).value = cfg[coin].rpc_user || '';
                document.getElementById(`${coin}_rpc_password`).value = cfg[coin].rpc_password || '';
            }
            document.getElementById('status').textContent = 'Config loaded';
        }

        async function saveConfig() {
            const payload = {};
            for (const coin of ['BTC','BCH','DGB']) {
                payload[coin] = {
                    rpc_url: document.getElementById(`${coin}_rpc_url`).value,
                      rpc_user: document.getElementById(`${coin}_rpc_user`).value,
                      rpc_password: document.getElementById(`${coin}_rpc_password`).value,
                };
            }
            const r = await fetch('/config', {
                method: 'POST',
                headers: { 'content-type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!r.ok) {
                const err = await r.text();
                document.getElementById('status').textContent = `Save failed: ${err}`;
                return;
            }
            document.getElementById('status').textContent = 'Saved and listeners restarted';
            await loadStats();
        }

        async function loadStats() {
            const r = await fetch('/stats');
            const s = await r.json();
            document.getElementById('stats').textContent = JSON.stringify(s, null, 2);
        }

        loadConfig();
        loadStats();
        setInterval(loadStats, 5000);
    </script>
</body>
</html>
"""


@app.get("/config")
async def get_config() -> dict[str, Any]:
        return _serialize_config(_CONFIGS)


@app.post("/config")
async def update_config(payload: dict[str, Any]) -> dict[str, Any]:
        for coin in ("BTC", "BCH", "DGB"):
                if coin not in payload:
                        continue
                row = payload[coin] or {}
                cfg = _CONFIGS[coin]
                if "rpc_url" in row:
                        cfg.rpc_url = str(row.get("rpc_url") or "")
                if "rpc_user" in row:
                        cfg.rpc_user = str(row.get("rpc_user") or "")
                if "rpc_password" in row:
                        cfg.rpc_password = str(row.get("rpc_password") or "")

        _CONFIGS["DGB"].algo = "sha256d"

        try:
                _save_overrides_to_disk(_CONFIGS)
                await _restart_servers()
        except Exception as exc:
                logger.error("Failed applying config update: %s", exc)
                raise HTTPException(status_code=500, detail=f"config_update_failed: {exc}") from exc

        return {"ok": True, "config": _serialize_config(_CONFIGS)}


@app.get("/stats")
async def stats() -> dict[str, Any]:
    return {
        "service": "hmm-local-stratum",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "coins": {
            coin: {
                "algo": server.config.algo,
                "stratum_port": server.config.stratum_port,
                "rpc_url": server.config.rpc_url,
                **server.stats.snapshot(),
            }
            for coin, server in _SERVERS.items()
        },
    }


@app.get("/stats/{coin}")
async def stats_coin(coin: str) -> dict[str, Any]:
    normalized = coin.upper()
    if normalized not in _SERVERS:
        raise HTTPException(status_code=404, detail=f"Unknown coin: {coin}")

    server = _SERVERS[normalized]
    return {
        "coin": normalized,
        "algo": server.config.algo,
        "stratum_port": server.config.stratum_port,
        "rpc_url": server.config.rpc_url,
        **server.stats.snapshot(),
    }
