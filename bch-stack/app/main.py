from datetime import datetime, timedelta
import asyncio
import logging
import base64
import json
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from typing import Any
import urllib.request
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel


app = FastAPI(title="BCH Local Stack Manager", version="0.1.0")

logger = logging.getLogger("bch_stack.manager")

CONFIG_ROOT = Path("/config")
NODE_CONF = CONFIG_ROOT / "node" / "bitcoin.conf"
CKPOOL_CONF = CONFIG_ROOT / "ckpool" / "ckpool.conf"
UI_SETTINGS = CONFIG_ROOT / "ui" / "settings.json"
APP_ROOT = Path(__file__).resolve().parent
FAVICON_FILE = APP_ROOT / "favicon.svg"
FAVICON_PNG_BYTES = base64.b64decode(
  "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAADFSURBVFhHY7Bu+vZ/oLCghPp/BnRBemIUB4A49MK0dYDzHjSf7vmvhCyvPw9FnkYOQFiqlPLtv3XxvP/SIL7+vP9myFGgP4/2DoBYCuFLh9z6b51SQ48oQHfArf+a+tDQQHIA0VHw9PlrOEaXQ8dPT3z6b9306f8WmFq8IRBKeweALaU0DZDuAIQlVMkFJDmACLXIdo46YOg5gBSMbs6oA4aHA9Dl0DExakcdMOqAUQeQ7ABq41EHDE4HDAQeHA5ADx56YwA1YvH+wVv7ZgAAAABJRU5ErkJggg=="
)


class ConfigUpdate(BaseModel):
    target: str
    content: str


def run_command(command: list[str], timeout: int = 20, retries: int = 0, retry_delay_seconds: float = 0.25) -> tuple[int, str, str]:
  attempts = retries + 1
  last_error = ""
  for attempt_index in range(attempts):
    try:
      process = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
      return process.returncode, process.stdout.strip(), process.stderr.strip()
    except subprocess.TimeoutExpired:
      last_error = f"timeout after {timeout}s"
    except Exception as exc:
      last_error = str(exc)

    if attempt_index < attempts - 1:
      time.sleep(retry_delay_seconds)

  return 1, "", last_error or "command failed"


def parse_supervisor_state(raw_state: str) -> dict[str, Any]:
  upper_state = raw_state.upper()
  known_states = ["RUNNING", "BACKOFF", "STARTING", "STOPPED", "FATAL", "EXITED", "UNKNOWN"]
  state_value = next((candidate for candidate in known_states if candidate in upper_state), "UNKNOWN")

  pid_value = None
  uptime_value = None

  pid_match = re.search(r"pid\s+(\d+)", raw_state, re.IGNORECASE)
  if pid_match:
    pid_value = int(pid_match.group(1))

  uptime_match = re.search(r"uptime\s+([^,]+)", raw_state, re.IGNORECASE)
  if uptime_match:
    uptime_value = uptime_match.group(1).strip()

  return {
    "raw": raw_state,
    "state": state_value,
    "pid": pid_value,
    "uptime": uptime_value,
  }


def structured_service_status(name: str) -> dict[str, Any]:
  code, output, error = run_command(["supervisorctl", "status", name], retries=1)
  if code != 0:
    return {
      "name": name,
      "ok": False,
      "state": "UNKNOWN",
      "raw": output or error,
      "detail": error or output,
      "pid": None,
      "uptime": None,
    }

  parsed_state = parse_supervisor_state(output)
  return {
    "name": name,
    "ok": True,
    "state": parsed_state["state"],
    "raw": parsed_state["raw"],
    "pid": parsed_state["pid"],
    "uptime": parsed_state["uptime"],
  }


def service_status(name: str) -> dict:
  code, out, err = run_command(["supervisorctl", "status", name])
  if code != 0:
    return {"name": name, "state": "unknown", "detail": err or out}
  return {"name": name, "state": out}


def run_bitcoin_cli(method: str) -> dict[str, Any]:
  code, output, error = run_command(
    ["bitcoin-cli", "-conf=/config/node/bitcoin.conf", "-datadir=/config/node", method],
    retries=1,
  )
  if code != 0:
    return {"ok": False, "error": error or output or "unknown error"}

  try:
    return {"ok": True, "data": json.loads(output)}
  except json.JSONDecodeError:
    return {"ok": False, "error": "invalid json from bitcoin-cli", "raw": output}


def read_json_file(path: Path) -> dict[str, Any]:
  if not path.exists():
    return {"ok": False, "error": "file not found", "path": str(path)}

  try:
    return {"ok": True, "data": json.loads(path.read_text(encoding="utf-8"))}
  except json.JSONDecodeError as exc:
    return {"ok": False, "error": f"invalid json: {exc}", "path": str(path)}


def read_log_tail(path: Path, lines: int) -> dict[str, Any]:
  if not path.exists():
    return {"ok": False, "error": "file not found", "path": str(path)}

  try:
    all_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return {
      "ok": True,
      "path": str(path),
      "lines": all_lines[-lines:],
      "total_lines": len(all_lines),
    }
  except Exception as exc:
    return {"ok": False, "error": str(exc), "path": str(path)}


def read_log_lines(path: Path) -> list[str]:
  if not path.exists():
    return []
  try:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()
  except Exception:
    return []


def parse_log_timestamp(line: str) -> datetime | None:
  timestamp_match = re.match(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)\]", line)
  if not timestamp_match:
    return None

  raw_value = timestamp_match.group(1)
  formats = ["%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"]
  for pattern in formats:
    try:
      return datetime.strptime(raw_value, pattern)
    except ValueError:
      continue
  return None


def classify_event(message: str) -> tuple[str, str]:
  upper = message.upper()
  if "CRITICAL" in upper or "FATAL" in upper:
    severity = "critical"
  elif "ERROR" in upper or "FAILED" in upper:
    severity = "error"
  elif "WARN" in upper or "WARNING" in upper:
    severity = "warning"
  else:
    severity = "info"

  if "BLOCK" in upper and ("FOUND" in upper or "SOLVED" in upper):
    event_type = "block_found"
  elif "AUTHORISED" in upper or "AUTHORI" in upper:
    event_type = "auth"
  elif "SHARE" in upper:
    event_type = "share"
  elif "CONNECT" in upper:
    event_type = "connectivity"
  else:
    event_type = "system"

  return severity, event_type


def extract_events_from_logs(lines: list[str], source: str, since: datetime | None = None) -> list[dict[str, Any]]:
  events: list[dict[str, Any]] = []
  for line in lines:
    timestamp = parse_log_timestamp(line)
    if timestamp is None:
      continue
    if since and timestamp <= since:
      continue

    message = re.sub(r"^\[[^\]]+\]\s*", "", line).strip()
    severity, event_type = classify_event(message)
    events.append(
      {
        "timestamp": timestamp.isoformat(),
        "source": source,
        "severity": severity,
        "event_type": event_type,
        "message": message,
      }
    )
  return events


def compute_ckpool_metrics() -> dict[str, Any]:
  stdout_lines = read_log_lines(CONFIG_ROOT / "logs" / "ckpool" / "ckpool.log")
  stderr_lines = read_log_lines(CONFIG_ROOT / "logs" / "ckpool" / "ckpool.err.log")
  all_lines = stdout_lines + stderr_lines

  now = datetime.utcnow()
  window_start = now - timedelta(hours=24)
  window_start_15m = now - timedelta(minutes=15)

  accepted_shares = 0
  rejected_shares = 0
  stale_shares = 0
  accepted_shares_24h = 0
  rejected_shares_24h = 0
  stale_shares_24h = 0
  accepted_shares_15m = 0
  rejected_shares_15m = 0
  stale_shares_15m = 0
  blocks_found = 0
  auth_success = 0
  auth_failed = 0
  best_share_diff: float | None = None

  summary: dict[str, Any] | None = None
  summary_samples: list[tuple[datetime, dict[str, Any]]] = []
  summary_line_re = re.compile(
    r"/\s+"
    r"(?P<hashrate>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>[KMGTP]?H/s)\s+"
    r"(?P<sps>[0-9]+(?:\.[0-9]+)?)\s*SPS\s+"
    r"(?P<users>[0-9]+)\s+users\s+"
    r"(?P<workers>[0-9]+)\s+workers\s+"
    r"(?P<shares>[0-9]+)\s+shares\s+"
    r"(?P<diff_pct>[0-9]+(?:\.[0-9]+)?)%\s+diff",
    re.IGNORECASE,
  )

  for line in all_lines:
    ts = parse_log_timestamp(line)
    upper = line.upper()
    if "ACCEPTED" in upper and "SHARE" in upper:
      accepted_shares += 1
      if ts and ts >= window_start:
        accepted_shares_24h += 1
      if ts and ts >= window_start_15m:
        accepted_shares_15m += 1
    if "REJECT" in upper and "SHARE" in upper:
      rejected_shares += 1
      if ts and ts >= window_start:
        rejected_shares_24h += 1
      if ts and ts >= window_start_15m:
        rejected_shares_15m += 1
    if "STALE" in upper and "SHARE" in upper:
      stale_shares += 1
      if ts and ts >= window_start:
        stale_shares_24h += 1
      if ts and ts >= window_start_15m:
        stale_shares_15m += 1
    if "BLOCK" in upper and ("FOUND" in upper or "SOLVED" in upper):
      blocks_found += 1
    if "AUTHORISED" in upper:
      auth_success += 1
    if "FAILED AUTHORISATION" in upper or "FAILED TO AUTHORISE" in upper:
      auth_failed += 1

    diff_match = re.search(r"BEST\s+DIFF(?:ERENCE)?[^0-9]*([0-9]+(?:\.[0-9]+)?)", upper)
    if diff_match:
      candidate = float(diff_match.group(1))
      if best_share_diff is None or candidate > best_share_diff:
        best_share_diff = candidate

  for line in stdout_lines[-6000:]:
    ts = parse_log_timestamp(line)
    if ts is None:
      continue
    match = summary_line_re.search(line)
    if not match:
      continue

    try:
      hashrate_value = float(match.group("hashrate"))
      hashrate_unit = str(match.group("unit"))
      sps_value = float(match.group("sps"))
      users_value = int(match.group("users"))
      workers_value = int(match.group("workers"))
      shares_value = int(match.group("shares"))
      diff_pct_value = float(match.group("diff_pct"))
    except Exception:
      continue

    summary_samples.append(
      (
        ts,
        {
          "hashrate": {
            "value": hashrate_value,
            "unit": hashrate_unit,
            "display": f"{hashrate_value:g} {hashrate_unit}",
          },
          "sps": sps_value,
          "users": users_value,
          "workers": workers_value,
          "shares": shares_value,
          "diff_pct": diff_pct_value,
        },
      )
    )

  if summary_samples:
    summary_samples.sort(key=lambda item: item[0])
    latest_ts, latest_summary = summary_samples[-1]
    summary = dict(latest_summary)

    target_ts = latest_ts - timedelta(hours=24)
    baseline = next((item for item in reversed(summary_samples) if item[0] <= target_ts), None)
    if baseline:
      baseline_shares = int(baseline[1].get("shares", 0))
      latest_shares = int(summary.get("shares", 0))
      delta = latest_shares - baseline_shares
      if delta >= 0:
        summary["shares_24h"] = delta

    target_15m = latest_ts - timedelta(minutes=15)
    baseline_15m = next((item for item in reversed(summary_samples) if item[0] <= target_15m), None)
    if baseline_15m:
      baseline_shares = int(baseline_15m[1].get("shares", 0))
      latest_shares = int(summary.get("shares", 0))
      delta = latest_shares - baseline_shares
      if delta >= 0:
        summary["shares_15m"] = delta

    # Warm-up fallback: use earliest -> latest until we have a full baseline.
    earliest_ts, earliest_summary = summary_samples[0]
    earliest_shares = int(earliest_summary.get("shares", 0))
    latest_shares = int(summary.get("shares", 0))
    if "shares_24h" not in summary and latest_shares >= earliest_shares:
      summary["shares_24h"] = latest_shares - earliest_shares
    if "shares_15m" not in summary and latest_shares >= earliest_shares:
      summary["shares_15m"] = latest_shares - earliest_shares

  recent_stderr = stderr_lines[-80:]
  recent_text = "\n".join(recent_stderr).upper()
  connector_ready = "CONNECTOR READY" in recent_text
  rpc_ready = "NO BITCOINDS ACTIVE" not in recent_text and "FAILED TO CONNECT SOCKET" not in recent_text

  shares_total = accepted_shares + rejected_shares + stale_shares
  shares_total_24h = accepted_shares_24h + rejected_shares_24h + stale_shares_24h
  shares_total_15m = accepted_shares_15m + rejected_shares_15m + stale_shares_15m

  if summary and shares_total_24h == 0:
    summary_delta = summary.get("shares_24h")
    if isinstance(summary_delta, int):
      accepted_shares_24h = summary_delta
      shares_total_24h = accepted_shares_24h

  if summary and shares_total_15m == 0:
    summary_delta = summary.get("shares_15m")
    if isinstance(summary_delta, int):
      accepted_shares_15m = summary_delta
      shares_total_15m = accepted_shares_15m

  if summary and shares_total == 0:
    accepted_shares = int(summary.get("shares", 0))
    shares_total = accepted_shares

  return {
    "timestamp": datetime.utcnow().isoformat(),
    "shares": {
      "accepted": accepted_shares,
      "rejected": rejected_shares,
      "stale": stale_shares,
      "total": shares_total,
      "accepted_24h": accepted_shares_24h,
      "rejected_24h": rejected_shares_24h,
      "stale_24h": stale_shares_24h,
      "total_24h": shares_total_24h,
      "accepted_15m": accepted_shares_15m,
      "rejected_15m": rejected_shares_15m,
      "stale_15m": stale_shares_15m,
      "total_15m": shares_total_15m,
    },
    "blocks": {
      "found": blocks_found,
    },
    "auth": {
      "success": auth_success,
      "failed": auth_failed,
    },
    "best_share_diff": best_share_diff,
    "summary": summary,
    "connectivity": {
      "connector_ready": connector_ready,
      "node_rpc_ready": rpc_ready,
    },
    "log_line_counts": {
      "stdout": len(stdout_lines),
      "stderr": len(stderr_lines),
    },
  }


def _parse_conf_kv(path: Path) -> dict[str, str]:
  if not path.exists():
    return {}
  raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
  out: dict[str, str] = {}
  for line in raw:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
      continue
    if "=" not in stripped:
      continue
    key, value = stripped.split("=", 1)
    out[key.strip()] = value.strip()
  return out


def _rpc_url_and_auth() -> tuple[str, str]:
  conf = _parse_conf_kv(NODE_CONF)
  host = conf.get("rpcconnect", "127.0.0.1")
  port = conf.get("rpcport", "8332")
  user = conf.get("rpcuser", "")
  password = conf.get("rpcpassword", "")
  return f"http://{host}:{port}", base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")


def _json_rpc_call(method: str) -> dict[str, Any]:
  url, auth = _rpc_url_and_auth()
  payload = json.dumps({"jsonrpc": "1.0", "id": "hmm", "method": method, "params": []}).encode("utf-8")
  req = urllib.request.Request(url, data=payload, method="POST")
  req.add_header("Content-Type", "application/json")
  req.add_header("Authorization", f"Basic {auth}")
  with urllib.request.urlopen(req, timeout=5) as resp:
    raw = resp.read().decode("utf-8", errors="replace")
  decoded = json.loads(raw)
  if decoded.get("error"):
    raise RuntimeError(str(decoded.get("error")))
  return decoded.get("result")


_NODE_CACHE_LOCK = threading.Lock()
_NODE_CACHE: dict[str, dict[str, Any]] = {
  "getblockchaininfo": {"ok": False, "data": None, "ts": None, "error": None},
  "getnetworkinfo": {"ok": False, "data": None, "ts": None, "error": None},
  "getmininginfo": {"ok": False, "data": None, "ts": None, "error": None},
}

_NODE_LAST_LOG_AT: dict[str, float] = {}


async def _refresh_node_cache_loop() -> None:
  while True:
    for method in ("getblockchaininfo", "getnetworkinfo", "getmininginfo"):
      try:
        result = await asyncio.to_thread(_json_rpc_call, method)
        with _NODE_CACHE_LOCK:
          _NODE_CACHE[method] = {"ok": True, "data": result, "ts": datetime.utcnow(), "error": None}
      except Exception as exc:
        with _NODE_CACHE_LOCK:
          prev = _NODE_CACHE.get(method) or {}
          _NODE_CACHE[method] = {
            "ok": bool(prev.get("ok")) and prev.get("data") is not None,
            "data": prev.get("data"),
            "ts": prev.get("ts"),
            "error": str(exc),
          }

        now_ts = time.time()
        last = _NODE_LAST_LOG_AT.get(method, 0.0)
        if (now_ts - last) >= 60.0:
          _NODE_LAST_LOG_AT[method] = now_ts
          logger.warning("node rpc refresh failed for %s: %s", method, exc)

    await asyncio.sleep(15)


def _get_cached_node(method: str) -> dict[str, Any]:
  with _NODE_CACHE_LOCK:
    entry = dict(_NODE_CACHE.get(method, {}))
  ts = entry.get("ts")
  age = None
  if isinstance(ts, datetime):
    age = (datetime.utcnow() - ts).total_seconds()
  return {
    "ok": bool(entry.get("ok")) and entry.get("data") is not None,
    "data": entry.get("data"),
    "cached": True,
    "age_seconds": age,
    "error": entry.get("error"),
  }


@app.on_event("startup")
async def _startup_background_refresh() -> None:
  asyncio.create_task(_refresh_node_cache_loop())


def summarize_events(events: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
  by_severity: dict[str, int] = {}
  by_type: dict[str, int] = {}
  by_source: dict[str, int] = {}

  for item in events:
    severity = str(item.get("severity", "unknown"))
    event_type = str(item.get("event_type", "unknown"))
    source = str(item.get("source", "unknown"))
    by_severity[severity] = by_severity.get(severity, 0) + 1
    by_type[event_type] = by_type.get(event_type, 0) + 1
    by_source[source] = by_source.get(source, 0) + 1

  return {
    "by_severity": by_severity,
    "by_type": by_type,
    "by_source": by_source,
  }


def node_sync_status() -> dict:
  result = run_bitcoin_cli("getblockchaininfo")
  if not result["ok"]:
    return {
      "ok": False,
      "error": result.get("error", "unknown error"),
    }

  data = result["data"]

  progress = float(data.get("verificationprogress", 0.0)) * 100
  return {
    "ok": True,
    "chain": data.get("chain", "unknown"),
    "blocks": data.get("blocks", 0),
    "headers": data.get("headers", 0),
    "initial_block_download": bool(data.get("initialblockdownload", True)),
    "verification_progress_pct": round(progress, 4),
  }


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def backup_file(path: Path) -> None:
    if not path.exists():
        return
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    backup_dir = CONFIG_ROOT / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"{path.name}.{timestamp}.bak"
    shutil.copy2(path, target)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
    "service": "bch-local-stack-manager",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/favicon.svg", include_in_schema=False)
def favicon() -> FileResponse:
  return FileResponse(FAVICON_FILE, media_type="image/svg+xml")


@app.get("/favicon.png", include_in_schema=False)
def favicon_png() -> Response:
  return Response(content=FAVICON_PNG_BYTES, media_type="image/png")


@app.get("/favicon.ico", include_in_schema=False)
def favicon_ico() -> RedirectResponse:
  return RedirectResponse(url="/favicon.png?v=4", status_code=307)


@app.get("/api/status")
def get_status() -> dict:
    return {
    "node": service_status("bitcoind"),
        "ckpool": service_status("ckpool"),
        "manager": service_status("manager"),
    "sync": node_sync_status(),
    }


@app.get("/api/v1/services")
def get_services_v1() -> dict:
  return {
    "timestamp": datetime.utcnow().isoformat(),
    "services": {
      "manager": structured_service_status("manager"),
      "bitcoind": structured_service_status("bitcoind"),
      "ckpool": structured_service_status("ckpool"),
    },
  }


@app.get("/api/v1/node/blockchain")
def get_node_blockchain_v1() -> dict:
  result = _get_cached_node("getblockchaininfo")
  return {
    "timestamp": datetime.utcnow().isoformat(),
    **result,
  }


@app.get("/api/v1/node/network")
def get_node_network_v1() -> dict:
  result = _get_cached_node("getnetworkinfo")
  return {
    "timestamp": datetime.utcnow().isoformat(),
    **result,
  }


@app.get("/api/v1/node/mining")
def get_node_mining_v1() -> dict:
  result = _get_cached_node("getmininginfo")
  return {
    "timestamp": datetime.utcnow().isoformat(),
    **result,
  }


@app.get("/api/v1/ckpool/config")
def get_ckpool_config_v1() -> dict:
  result = read_json_file(CKPOOL_CONF)
  return {
    "timestamp": datetime.utcnow().isoformat(),
    **result,
  }


@app.get("/api/v1/ckpool/logs")
def get_ckpool_logs_v1(lines: int = Query(default=120, ge=10, le=1000)) -> dict:
  return {
    "timestamp": datetime.utcnow().isoformat(),
    "stdout": read_log_tail(CONFIG_ROOT / "logs" / "ckpool" / "ckpool.log", lines),
    "stderr": read_log_tail(CONFIG_ROOT / "logs" / "ckpool" / "ckpool.err.log", lines),
  }


@app.get("/api/v1/ckpool/metrics")
def get_ckpool_metrics_v1() -> dict:
  return compute_ckpool_metrics()


@app.get("/api/v1/events")
def get_events_v1(
  since: str | None = Query(default=None),
  limit: int = Query(default=200, ge=1, le=2000),
  order: str = Query(default="asc", pattern="^(asc|desc)$"),
  severity: str | None = Query(default=None),
  event_type: str | None = Query(default=None),
  source_contains: str | None = Query(default=None),
) -> dict:
  since_dt: datetime | None = None
  if since:
    try:
      since_dt = datetime.fromisoformat(since)
    except ValueError:
      raise HTTPException(status_code=400, detail="invalid since timestamp; use ISO-8601")

  stdout_lines = read_log_lines(CONFIG_ROOT / "logs" / "ckpool" / "ckpool.log")
  stderr_lines = read_log_lines(CONFIG_ROOT / "logs" / "ckpool" / "ckpool.err.log")

  events = extract_events_from_logs(stdout_lines, "ckpool.stdout", since_dt)
  events.extend(extract_events_from_logs(stderr_lines, "ckpool.stderr", since_dt))
  events.sort(key=lambda item: item["timestamp"])

  if severity:
    severity_normalized = severity.lower()
    events = [item for item in events if str(item.get("severity", "")).lower() == severity_normalized]

  if event_type:
    event_type_normalized = event_type.lower()
    events = [item for item in events if str(item.get("event_type", "")).lower() == event_type_normalized]

  if source_contains:
    source_normalized = source_contains.lower()
    events = [item for item in events if source_normalized in str(item.get("source", "")).lower()]

  total_matching = len(events)
  latest_timestamp = max((item["timestamp"] for item in events), default=None)

  has_more = len(events) > limit
  if order == "desc":
    events.reverse()
    if has_more:
      events = events[:limit]
  else:
    if has_more:
      if since:
        events = events[:limit]
      else:
        events = events[-limit:]

  next_since = max((item["timestamp"] for item in events), default=None)
  return {
    "timestamp": datetime.utcnow().isoformat(),
    "count": len(events),
    "total_matching": total_matching,
    "has_more": has_more,
    "next_since": next_since,
    "latest_event_timestamp": latest_timestamp,
    "summary": summarize_events(events),
    "events": events,
  }


@app.get("/api/v1/events/cursor")
def get_events_cursor_v1(
  since: str | None = Query(default=None),
  limit: int = Query(default=200, ge=1, le=2000),
  order: str = Query(default="asc", pattern="^(asc|desc)$"),
  severity: str | None = Query(default=None),
  event_type: str | None = Query(default=None),
  source_contains: str | None = Query(default=None),
) -> dict:
  payload = get_events_v1(
    since=since,
    limit=limit,
    order=order,
    severity=severity,
    event_type=event_type,
    source_contains=source_contains,
  )
  return {
    "timestamp": payload.get("timestamp"),
    "count": payload.get("count", 0),
    "total_matching": payload.get("total_matching", 0),
    "has_more": payload.get("has_more", False),
    "next_since": payload.get("next_since"),
    "latest_event_timestamp": payload.get("latest_event_timestamp"),
    "summary": payload.get("summary", {}),
    "filters": {
      "since": since,
      "limit": limit,
      "order": order,
      "severity": severity,
      "event_type": event_type,
      "source_contains": source_contains,
    },
  }


def get_events_summary(since: str | None = None, limit: int = 200) -> dict[str, Any]:
  events_payload = get_events_v1(
    since=since,
    limit=limit,
    order="asc",
    severity=None,
    event_type=None,
    source_contains=None,
  )
  return {
    "timestamp": events_payload.get("timestamp"),
    "count": events_payload.get("count", 0),
    "total_matching": events_payload.get("total_matching", 0),
    "has_more": events_payload.get("has_more", False),
    "next_since": events_payload.get("next_since"),
    "latest_event_timestamp": events_payload.get("latest_event_timestamp"),
    "summary": events_payload.get("summary", {}),
  }


@app.get("/api/v1/capabilities")
def get_capabilities_v1() -> dict:
  return {
    "timestamp": datetime.utcnow().isoformat(),
    "api_version": "v1",
    "features": {
      "service_status": True,
      "node_blockchain": True,
      "node_network": True,
      "node_mining": True,
      "ckpool_config": True,
      "ckpool_log_tail": True,
      "worker_stats": True,
      "share_stream": False,
      "block_events": True,
      "event_feed": True,
      "ckpool_metrics": True,
      "event_filters": True,
      "snapshot_polling_cursor": True,
      "readiness": True,
      "events_cursor": True,
    },
  }


@app.get("/api/v1/ready")
def get_ready_v1() -> dict:
  services = {
    "manager": structured_service_status("manager"),
    "bitcoind": structured_service_status("bitcoind"),
    "ckpool": structured_service_status("ckpool"),
  }
  sync = node_sync_status()

  reasons: list[str] = []
  for service_name, state in services.items():
    if state.get("state") != "RUNNING":
      reasons.append(f"{service_name} not RUNNING")

  if not sync.get("ok", False):
    reasons.append("node sync unavailable")
  elif sync.get("initial_block_download", True):
    reasons.append("node in initial block download")

  ready = len(reasons) == 0
  return {
    "timestamp": datetime.utcnow().isoformat(),
    "ready": ready,
    "reasons": reasons,
    "services": services,
    "node_sync": sync,
  }


@app.get("/api/v1/snapshot")
def get_snapshot_v1(
  since: str | None = Query(default=None),
  limit: int = Query(default=100, ge=1, le=2000),
) -> dict:
  services = {
    "manager": structured_service_status("manager"),
    "bitcoind": structured_service_status("bitcoind"),
    "ckpool": structured_service_status("ckpool"),
  }
  blockchain = run_bitcoin_cli("getblockchaininfo")
  network = run_bitcoin_cli("getnetworkinfo")
  mining = run_bitcoin_cli("getmininginfo")
  ckpool_config = read_json_file(CKPOOL_CONF)

  events_payload = get_events_v1(
    since=since,
    limit=limit,
    order="asc",
    severity=None,
    event_type=None,
    source_contains=None,
  )

  return {
    "timestamp": datetime.utcnow().isoformat(),
    "services": services,
    "node": {
      "blockchain": blockchain,
      "network": network,
      "mining": mining,
      "sync": node_sync_status(),
    },
    "ckpool": {
      "config": ckpool_config,
      "metrics": compute_ckpool_metrics(),
    },
    "events": events_payload,
    "polling": {
      "since_used": since,
      "next_since": events_payload.get("next_since"),
      "has_more": events_payload.get("has_more"),
      "limit": limit,
    },
  }


@app.get("/api/v1/snapshot/compact")
def get_snapshot_compact_v1(
  since: str | None = Query(default=None),
  limit: int = Query(default=200, ge=1, le=2000),
) -> dict:
  services = {
    "manager": structured_service_status("manager"),
    "bitcoind": structured_service_status("bitcoind"),
    "ckpool": structured_service_status("ckpool"),
  }
  blockchain = run_bitcoin_cli("getblockchaininfo")
  network = run_bitcoin_cli("getnetworkinfo")
  mining = run_bitcoin_cli("getmininginfo")
  ckpool_config = read_json_file(CKPOOL_CONF)

  events_summary = get_events_summary(since=since, limit=limit)

  return {
    "timestamp": datetime.utcnow().isoformat(),
    "services": services,
    "node": {
      "blockchain": blockchain,
      "network": network,
      "mining": mining,
      "sync": node_sync_status(),
    },
    "ckpool": {
      "config": ckpool_config,
      "metrics": compute_ckpool_metrics(),
    },
    "events": events_summary,
    "polling": {
      "since_used": since,
      "next_since": events_summary.get("next_since"),
      "has_more": events_summary.get("has_more"),
      "limit": limit,
    },
  }


@app.get("/api/config")
def get_config() -> dict:
    return {
        "node": read_text(NODE_CONF),
        "ckpool": read_text(CKPOOL_CONF),
        "ui": read_text(UI_SETTINGS),
    }


@app.post("/api/config")
def update_config(payload: ConfigUpdate) -> dict:
    if payload.target == "node":
        path = NODE_CONF
    elif payload.target == "ckpool":
        path = CKPOOL_CONF
    elif payload.target == "ui":
        path = UI_SETTINGS
    else:
        raise HTTPException(status_code=400, detail="invalid config target")

    path.parent.mkdir(parents=True, exist_ok=True)
    backup_file(path)
    path.write_text(payload.content, encoding="utf-8")
    return {"success": True, "target": payload.target}


@app.post("/api/restart/{service_name}")
def restart_service(service_name: str) -> dict:
  allowed = {"bitcoind", "ckpool", "manager"}
  if service_name not in allowed:
    raise HTTPException(status_code=400, detail="invalid service")

  code, out, err = run_command(["supervisorctl", "restart", service_name])
  if code != 0:
    raise HTTPException(status_code=500, detail=err or out)
  return {"success": True, "service": service_name, "result": out}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
  return """
<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>BCH Local Stack</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: Arial, sans-serif; margin: 0; background:#111827; color:#e5e7eb; }
    .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
    h1 { margin: 0; font-size: 28px; }
    p { margin: 0 0 18px 0; color:#9ca3af; }
    h3 { margin: 0 0 10px 0; font-size: 16px; }
    .brand { display:flex; align-items:center; gap:12px; margin-bottom:8px; }
    .brand-logo { width:40px; height:40px; color:#e5e7eb; flex: 0 0 auto; }
    .brand-text { display:flex; flex-direction:column; }
    .brand-title { font-weight:700; font-size:20px; line-height:1.75rem; }
    .brand-bch { color:#f97316; font-size:11px; vertical-align:super; margin-left:2px; font-weight:700; }
    .brand-subtitle { font-size:12px; color:#9ca3af; }
    .tiles { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:12px; margin-bottom:16px; }
    .grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top: 16px; }
    .tile-label { color:#9ca3af; font-size:12px; margin-bottom:6px; text-transform: uppercase; letter-spacing: .04em; }
    .tile-value { font-size:20px; font-weight:700; line-height: 1.2; }
    .good { color:#22c55e; }
    .warn { color:#f59e0b; }
    .bad { color:#ef4444; }
    .card { border:1px solid #374151; border-radius:12px; padding:14px; background:#1f2937; box-shadow: 0 1px 2px rgba(0,0,0,.2); }
    .actions { display:flex; flex-wrap: wrap; gap:8px; margin-bottom: 10px; }
    .mini-grid { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:10px; margin-top: 10px; }
    .kv { display:flex; justify-content:space-between; gap:10px; font-size:13px; color:#cbd5e1; padding:4px 0; border-bottom:1px dashed #334155; }
    .kv:last-child { border-bottom:none; }
    .k { color:#94a3b8; }
    .v { font-weight:600; color:#e5e7eb; }
    details { margin-top: 10px; }
    summary { cursor:pointer; color:#93c5fd; font-size:13px; }
    button { padding:8px 12px; border-radius:8px; border:0; background:#2563eb; color:white; cursor:pointer; font-weight: 600; }
    button:hover { filter: brightness(1.06); }
    textarea { width:100%; height:240px; background:#0f172a; color:#e5e7eb; border:1px solid #334155; border-radius:8px; padding:10px; margin-bottom: 10px; }
    pre { background:#0f172a; border:1px solid #334155; border-radius:8px; padding:10px; overflow:auto; margin: 0; min-height: 130px; }
    @media (max-width: 1100px) { .tiles { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
    @media (max-width: 800px) {
      .container { padding: 14px; }
      .grid, .tiles { grid-template-columns:1fr; }
      .mini-grid { grid-template-columns:1fr; }
      h1 { font-size: 24px; }
    }
  </style>
</head>
<body>
  <div class="container">
  <div class="brand">
  <link rel="icon" type="image/png" sizes="32x32" href="/favicon.png?v=4" />
  <link rel="icon" type="image/svg+xml" sizes="any" href="/favicon.svg?v=4" />
  <link rel="shortcut icon" href="/favicon.ico?v=4" />
    <svg viewBox="0 0 100 100" class="brand-logo" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="10" y="10" width="80" height="80" rx="8" fill="currentColor" fill-opacity="0.1" />
      <path d="M20 30 H40 M60 30 H80 M20 50 H35 M65 50 H80 M20 70 H40 M60 70 H80" stroke="currentColor" stroke-width="2" stroke-opacity="0.3" />
      <path d="M35 35 V65 M35 50 H65 M65 35 V65" stroke="currentColor" stroke-width="6" stroke-linecap="round" stroke-linejoin="round" />
      <path d="M40 40 L30 30 M60 40 L70 30" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-opacity="0.6" />
      <circle cx="20" cy="30" r="2" fill="currentColor" fill-opacity="0.5" />
      <circle cx="80" cy="30" r="2" fill="currentColor" fill-opacity="0.5" />
      <circle cx="20" cy="50" r="2" fill="currentColor" fill-opacity="0.5" />
      <circle cx="80" cy="50" r="2" fill="currentColor" fill-opacity="0.5" />
      <circle cx="20" cy="70" r="2" fill="currentColor" fill-opacity="0.5" />
      <circle cx="80" cy="70" r="2" fill="currentColor" fill-opacity="0.5" />
    </svg>
    <div class="brand-text">
      <span class="brand-title">HMM Local<sup class="brand-bch">BCH</sup></span>
      <span class="brand-subtitle">Home Miner Manager</span>
    </div>
  </div>
  <p>BCH Local Stack Manager • Coin fixed to BCH, algo fixed to sha256d.</p>

  <div class=\"tiles\">
    <div class=\"card\"><div class=\"tile-label\">Manager</div><div id=\"tileManager\" class=\"tile-value\">-</div></div>
    <div class=\"card\"><div class=\"tile-label\">Node Sync</div><div id=\"tileSync\" class=\"tile-value\">-</div></div>
    <div class=\"card\"><div class=\"tile-label\">Blocks / Headers</div><div id=\"tileHeights\" class=\"tile-value\">-</div></div>
    <div class=\"card\"><div class=\"tile-label\">Stratum</div><div id=\"tileCkpool\" class=\"tile-value\">-</div></div>
  </div>

  <div class=\"card\">
    <div class="actions">
      <button onclick="refreshStatus()">Refresh Status</button>
      <button onclick="restartSvc('bitcoind')">Restart Node</button>
      <button onclick="restartSvc('ckpool')">Restart Ckpool</button>
    </div>
    <div class="tile-label">Auto refresh: every 5s</div>

    <div class="mini-grid">
      <div class="card">
        <div class="tile-label">Manager Service</div>
        <div class="kv"><span class="k">State</span><span id="managerStateValue" class="v">-</span></div>
        <div class="kv"><span class="k">PID</span><span id="managerPidValue" class="v">-</span></div>
        <div class="kv"><span class="k">Uptime</span><span id="managerUptimeValue" class="v">-</span></div>
      </div>
      <div class="card">
        <div class="tile-label">Node Service</div>
        <div class="kv"><span class="k">State</span><span id="nodeStateValue" class="v">-</span></div>
        <div class="kv"><span class="k">PID</span><span id="nodePidValue" class="v">-</span></div>
        <div class="kv"><span class="k">Uptime</span><span id="nodeUptimeValue" class="v">-</span></div>
      </div>
      <div class="card">
        <div class="tile-label">Stratum Service</div>
        <div class="kv"><span class="k">State</span><span id="ckpoolStateValue" class="v">-</span></div>
        <div class="kv"><span class="k">PID</span><span id="ckpoolPidValue" class="v">-</span></div>
        <div class="kv"><span class="k">Uptime</span><span id="ckpoolUptimeValue" class="v">-</span></div>
      </div>
    </div>

    <details>
      <summary>Raw JSON (debug)</summary>
      <pre id=\"status\">loading...</pre>
    </details>
  </div>

  <div class=\"grid\">
    <div class=\"card\">
      <h3>bitcoin.conf</h3>
      <textarea id=\"nodeCfg\"></textarea>
      <button onclick=\"saveCfg('node','nodeCfg')\">Save Node Config</button>
    </div>
    <div class=\"card\">
      <h3>ckpool.conf</h3>
      <textarea id=\"ckpoolCfg\"></textarea>
      <button onclick=\"saveCfg('ckpool','ckpoolCfg')\">Save Ckpool Config</button>
    </div>
  </div>

  <script>
    const REFRESH_MS = 5000;
    let refreshInProgress = false;

    function statusClass(value) {
      if ((value || '').includes('RUNNING')) return 'good';
      if ((value || '').includes('BACKOFF')) return 'warn';
      return 'bad';
    }

    function parseSupervisorState(stateText) {
      const text = stateText || '';
      const upper = text.toUpperCase();
      const knownStates = ['RUNNING', 'BACKOFF', 'STARTING', 'STOPPED', 'FATAL', 'EXITED', 'UNKNOWN'];
      const state = knownStates.find((value) => upper.includes(value)) || 'UNKNOWN';
      const pidMatch = text.match(/pid\\s+(\\d+)/i);
      const uptimeMatch = text.match(/uptime\\s+([^,]+)/i);
      return {
        state,
        pid: pidMatch ? pidMatch[1] : '-',
        uptime: uptimeMatch ? uptimeMatch[1] : '-',
      };
    }

    function setServiceDetails(prefix, serviceStateText) {
      const parsed = parseSupervisorState(serviceStateText);
      document.getElementById(prefix + 'StateValue').textContent = parsed.state;
      document.getElementById(prefix + 'PidValue').textContent = parsed.pid;
      document.getElementById(prefix + 'UptimeValue').textContent = parsed.uptime;
    }

    async function refreshStatus() {
      if (refreshInProgress) return;
      refreshInProgress = true;

      try {
        const res = await fetch('/api/status');
        const data = await res.json();

        const managerState = data.manager?.state || 'unknown';
        const nodeState = data.node?.state || 'unknown';
        const ckpoolState = data.ckpool?.state || 'unknown';
        const sync = data.sync || {};

        const managerEl = document.getElementById('tileManager');
        managerEl.className = 'tile-value ' + statusClass(managerState);
        managerEl.textContent = managerState.includes('RUNNING') ? 'RUNNING' : 'NOT READY';

        const ckpoolEl = document.getElementById('tileCkpool');
        ckpoolEl.className = 'tile-value ' + statusClass(ckpoolState);
        ckpoolEl.textContent = ckpoolState.includes('RUNNING') ? 'RUNNING' : 'NOT READY';

        setServiceDetails('manager', managerState);
        setServiceDetails('node', nodeState);
        setServiceDetails('ckpool', ckpoolState);

        const syncEl = document.getElementById('tileSync');
        if (!sync.ok) {
          syncEl.className = 'tile-value bad';
          syncEl.textContent = 'UNAVAILABLE';
        } else {
          syncEl.className = 'tile-value ' + (sync.initial_block_download ? 'warn' : 'good');
          const progress = Number(sync.verification_progress_pct || 0);
          syncEl.textContent = `${progress.toFixed(2)}%`;
        }

        const heightsEl = document.getElementById('tileHeights');
        if (!sync.ok) {
          heightsEl.className = 'tile-value bad';
          heightsEl.textContent = '-';
        } else {
          heightsEl.className = 'tile-value';
          const blocks = Number(sync.blocks || 0).toLocaleString();
          const headers = Number(sync.headers || 0).toLocaleString();
          heightsEl.textContent = `${blocks} / ${headers}`;
        }

        document.getElementById('status').textContent = JSON.stringify(data, null, 2);
      } finally {
        refreshInProgress = false;
      }
    }

    async function loadCfg() {
      const res = await fetch('/api/config');
      const data = await res.json();
      document.getElementById('nodeCfg').value = data.node || '';
      document.getElementById('ckpoolCfg').value = data.ckpool || '';
    }

    async function saveCfg(target, elementId) {
      const content = document.getElementById(elementId).value;
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({target, content})
      });
      if (!res.ok) {
        const e = await res.json();
        alert('Save failed: ' + (e.detail || 'unknown'));
        return;
      }
      alert('Saved ' + target + ' config');
    }

    async function restartSvc(name) {
      const res = await fetch('/api/restart/' + name, { method: 'POST' });
      if (!res.ok) {
        const e = await res.json();
        alert('Restart failed: ' + (e.detail || 'unknown'));
      }
      await refreshStatus();
    }

    refreshStatus();
    setInterval(refreshStatus, REFRESH_MS);
    loadCfg();
  </script>
  </div>
</body>
</html>
"""