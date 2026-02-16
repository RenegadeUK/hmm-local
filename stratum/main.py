"""HMM-Local Stratum Gateway.

⚠️ INCOMPLETE
- DGB now supports live RPC template polling + job notify broadcasts.
- Share validation / block submission are still scaffold behavior.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import struct
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("hmm_local_stratum")

CONFIG_PATH = os.getenv("STRATUM_CONFIG_PATH", "/config/stratum_gateway.json")
RPC_TIMEOUT_SECONDS = float(os.getenv("RPC_TIMEOUT_SECONDS", "8"))
DGB_TEMPLATE_POLL_SECONDS = float(os.getenv("DGB_TEMPLATE_POLL_SECONDS", "3"))
DGB_EXTRANONCE1_SIZE = 4
DGB_EXTRANONCE2_SIZE = 4
DGB_STATIC_DIFFICULTY = float(os.getenv("DGB_STATIC_DIFFICULTY", "512"))
STRATUM_DEBUG_SHARES = os.getenv("STRATUM_DEBUG_SHARES", "true").strip().lower() == "true"
STRATUM_COMPAT_ACCEPT_VARIANTS = (
    os.getenv("STRATUM_COMPAT_ACCEPT_VARIANTS", "true").strip().lower() == "true"
)
STALE_JOB_GRACE_SECONDS = int(os.getenv("STALE_JOB_GRACE_SECONDS", "30"))
STALE_JOB_GRACE_COUNT = int(os.getenv("STALE_JOB_GRACE_COUNT", "4"))
HMM_STRATUM_TRACE_DEBUG = os.getenv("HMM_STRATUM_TRACE_DEBUG", "0").strip() == "1"
try:
    STRATUM_VERSION_ROLLING_SERVER_MASK = (
        int(os.getenv("STRATUM_VERSION_ROLLING_SERVER_MASK", "0x1fffe000"), 0) & 0xFFFFFFFF
    )
except ValueError:
    STRATUM_VERSION_ROLLING_SERVER_MASK = 0x1FFFE000

# Bitcoin diff1 target (big-endian human form)
DIFF1_TARGET_HEX = "00000000ffff0000000000000000000000000000000000000000000000000000"
DIFF1_TARGET_INT = int.from_bytes(bytes.fromhex(DIFF1_TARGET_HEX), "big")

# Hard safety assertions to prevent broken target constants.
assert DIFF1_TARGET_INT.bit_length() > 200
assert ("0x" + f"{DIFF1_TARGET_INT:064x}").startswith("0xffff0000") is False
assert DIFF1_TARGET_INT == int("00000000ffff0000000000000000000000000000000000000000000000000000", 16)

# Keep legacy name used by older code paths.
TARGET_1 = DIFF1_TARGET_INT


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
    current_job_id: str | None = None
    chain_height: int | None = None
    template_height: int | None = None
    last_template_at: str | None = None
    rpc_last_ok_at: str | None = None
    rpc_last_error: str | None = None
    share_reject_reasons: dict[str, int] = field(default_factory=dict)
    block_candidates: int = 0
    blocks_accepted: int = 0
    blocks_rejected: int = 0
    last_block_submit_result: str | None = None
    best_share_difficulty: float | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "connected_workers": self.connected_workers,
            "total_connections": self.total_connections,
            "shares_submitted": self.shares_submitted,
            "shares_accepted": self.shares_accepted,
            "shares_rejected": self.shares_rejected,
            "last_share_at": self.last_share_at,
            "current_job_id": self.current_job_id,
            "chain_height": self.chain_height,
            "template_height": self.template_height,
            "last_template_at": self.last_template_at,
            "rpc_last_ok_at": self.rpc_last_ok_at,
            "rpc_last_error": self.rpc_last_error,
            "share_reject_reasons": self.share_reject_reasons,
            "block_candidates": self.block_candidates,
            "blocks_accepted": self.blocks_accepted,
            "blocks_rejected": self.blocks_rejected,
            "last_block_submit_result": self.last_block_submit_result,
            "best_share_difficulty": self.best_share_difficulty,
        }


@dataclass
class ClientSession:
    subscribed: bool = False
    authorized: bool = False
    worker_name: str | None = None
    extranonce1: str | None = None
    difficulty: float = DGB_STATIC_DIFFICULTY
    version_mask: int = 0


@dataclass
class ActiveJob:
    job_id: str
    prevhash: str
    prevhash_be: str
    coinb1: str
    coinb2: str
    merkle_branch: list[str]
    version: str
    nbits: str
    ntime: str
    clean_jobs: bool
    template_height: int | None = None
    target_1: int = TARGET_1
    tx_datas: list[str] = field(default_factory=list)

    def notify_params(self) -> list[Any]:
        return [
            self.job_id,
            self.prevhash,
            self.coinb1,
            self.coinb2,
            self.merkle_branch,
            self.version,
            self.nbits,
            self.ntime,
            self.clean_jobs,
        ]


@dataclass
class ShareTrace:
    cid: str
    ts: str
    coin: str
    worker: str
    job_id: str
    ex1: str
    ex2: str
    ntime: str
    nonce: str
    base_version: str | None = None
    submitted_version: str | None = None
    version_mask: str | None = None
    final_version: str | None = None
    prevhash: str | None = None
    merkle_root: str | None = None
    nbits: str | None = None
    ntime_job: str | None = None
    header_hex: str | None = None
    hash_hex: str | None = None
    hash_int_big: int | None = None
    hash_int_little: int | None = None
    assigned_diff: float | None = None
    share_target_int: int | None = None
    share_target_hex: str | None = None
    computed_diff: float | None = None
    meets_target: bool | None = None
    meets_network: bool | None = None
    reject_reason: str | None = None
    stale: bool = False
    server_response_time_ms: float | None = None
    stored: bool = False

    def to_summary(self) -> dict[str, Any]:
        return {
            "cid": self.cid,
            "ts": self.ts,
            "coin": self.coin,
            "worker": self.worker,
            "job_id": self.job_id,
            "ex1": self.ex1,
            "ex2": self.ex2,
            "ntime": self.ntime,
            "nonce": self.nonce,
            "base_version": self.base_version,
            "submitted_version": self.submitted_version,
            "version_mask": self.version_mask,
            "final_version": self.final_version,
            "hash_hex": self.hash_hex,
            "assigned_diff": self.assigned_diff,
            "computed_diff": self.computed_diff,
            "meets_target": self.meets_target,
            "meets_network": self.meets_network,
            "reject_reason": self.reject_reason,
            "stale": self.stale,
            "server_response_time_ms": self.server_response_time_ms,
        }


class RpcClient:
    def __init__(self, config: CoinConfig):
        self.config = config

    async def call(self, method: str, params: list[Any] | None = None) -> Any:
        payload = {
            "jsonrpc": "1.0",
            "id": f"{self.config.coin}-{uuid.uuid4().hex[:8]}",
            "method": method,
            "params": params or [],
        }
        async with httpx.AsyncClient(timeout=RPC_TIMEOUT_SECONDS) as client:
            request_kwargs: dict[str, Any] = {"json": payload}
            if self.config.rpc_user:
                request_kwargs["auth"] = (self.config.rpc_user, self.config.rpc_password)

            resp = await client.post(self.config.rpc_url, **request_kwargs)
            resp.raise_for_status()
            data = resp.json()
            if data.get("error"):
                raise RuntimeError(str(data.get("error")))
            return data.get("result")


class StratumServer:
    """Minimal Stratum v1 server with notify broadcast support."""

    def __init__(
        self,
        config: CoinConfig,
        bind_host: str = "0.0.0.0",
        rpc_client: RpcClient | None = None,
    ):
        self.config = config
        self.bind_host = bind_host
        self.rpc_client = rpc_client
        self.server: asyncio.AbstractServer | None = None
        self.stats = CoinRuntimeStats()
        self._sub_counter = 0
        self._extranonce_counter = 0
        self._clients: set[asyncio.StreamWriter] = set()
        self._sessions: dict[asyncio.StreamWriter, ClientSession] = {}
        self._active_job: ActiveJob | None = None
        self._submitted_share_keys: set[str] = set()
        self._last_share_debug: dict[str, Any] | None = None
        self._recent_jobs_per_worker: dict[str, deque[tuple[str, float]]] = {}
        self._share_traces_global: deque[ShareTrace] = deque(maxlen=5000)
        self._share_traces_by_worker: dict[str, deque[ShareTrace]] = {}
        self._share_traces_inflight: dict[str, ShareTrace] = {}

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

    async def set_job(self, job: ActiveJob) -> None:
        self._active_job = job
        self._submitted_share_keys.clear()
        self.stats.current_job_id = job.job_id
        self.stats.template_height = job.template_height
        self.stats.last_template_at = datetime.now(timezone.utc).isoformat()
        self._add_job_to_known_workers(job.job_id)
        self._log_kv(
            "template_create",
            coin=self.config.coin,
            job_id=job.job_id,
            height=job.template_height,
            version=job.version,
            nbits=job.nbits,
            ntime=job.ntime,
        )
        await self.broadcast_notify(job.notify_params())

    async def broadcast_notify(self, notify_params: list[Any]) -> None:
        payload = {
            "id": None,
            "method": "mining.notify",
            "params": notify_params,
        }

        disconnected: list[asyncio.StreamWriter] = []
        for writer in self._clients:
            try:
                await self._write_json(writer, payload)
            except Exception:
                disconnected.append(writer)

        for writer in disconnected:
            self._clients.discard(writer)

        job_id = str(notify_params[0]) if notify_params else ""
        for writer in self._clients:
            session = self._sessions.get(writer)
            self._log_kv(
                "notify_tx",
                coin=self.config.coin,
                worker=(session.worker_name if session and session.worker_name else "unknown"),
                job_id=job_id,
            )

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        self._clients.add(writer)
        self._sessions[writer] = ClientSession()
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

                session = self._sessions.get(writer, ClientSession())
                response = await self._handle_request(req, writer, session)
                if response is not None:
                    await self._write_json(writer, response)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("%s client handler error (%s): %s", self.config.coin, peer, exc)
        finally:
            self._clients.discard(writer)
            self._sessions.pop(writer, None)
            self.stats.connected_workers = max(0, self.stats.connected_workers - 1)
            writer.close()
            await writer.wait_closed()
            logger.info("%s client disconnected: %s", self.config.coin, peer)

    async def _handle_request(
        self,
        req: dict[str, Any],
        writer: asyncio.StreamWriter,
        session: ClientSession,
    ) -> dict[str, Any] | None:
        req_id = req.get("id")
        method = req.get("method")

        if method == "mining.subscribe":
            session.subscribed = True
            self._extranonce_counter += 1
            session.extranonce1 = f"{self._extranonce_counter & 0xFFFFFFFF:08x}"
            self._sub_counter += 1
            sub_id = f"{self.config.coin.lower()}-sub-{self._sub_counter}"
            return {
                "id": req_id,
                "result": [
                    [["mining.notify", sub_id], ["mining.set_difficulty", sub_id]],
                    session.extranonce1,
                    DGB_EXTRANONCE2_SIZE,
                ],
                "error": None,
            }

        if method == "mining.authorize":
            params = req.get("params") or []
            if params:
                session.worker_name = str(params[0])
            session.authorized = True
            session.difficulty = DGB_STATIC_DIFFICULTY
            self._log_assigned_difficulty(session.difficulty)

            # Static baseline difficulty for initial phase.
            await self._write_json(
                writer,
                {"id": None, "method": "mining.set_difficulty", "params": [session.difficulty]},
            )

            # If we already have a live job, push it immediately.
            if self._active_job:
                if session.worker_name:
                    self._track_worker_job(session.worker_name, self._active_job.job_id)
                await self._write_json(
                    writer,
                    {"id": None, "method": "mining.notify", "params": self._active_job.notify_params()},
                )

            return {"id": req_id, "result": True, "error": None}

        if method == "mining.extranonce.subscribe":
            return {"id": req_id, "result": True, "error": None}

        if method == "mining.configure":
            params = req.get("params") or []
            requested_extensions = params[0] if len(params) > 0 and isinstance(params[0], list) else []
            ext_options = params[1] if len(params) > 1 and isinstance(params[1], dict) else {}

            result: dict[str, Any] = {}
            if "version-rolling" in requested_extensions:
                mask_hex = str(ext_options.get("version-rolling.mask") or "0").strip().lower()
                try:
                    if mask_hex.startswith("0x"):
                        miner_mask = int(mask_hex, 16) & 0xFFFFFFFF
                    elif any(ch in "abcdef" for ch in mask_hex):
                        miner_mask = int(mask_hex, 16) & 0xFFFFFFFF
                    else:
                        miner_mask = int(mask_hex, 10) & 0xFFFFFFFF
                except ValueError:
                    miner_mask = 0

                negotiated_mask = miner_mask & STRATUM_VERSION_ROLLING_SERVER_MASK

                session.version_mask = negotiated_mask
                result["version-rolling"] = True
                result["version-rolling.mask"] = f"{negotiated_mask:08x}"
                logger.info(
                    "%s negotiated version rolling: worker=%s miner_mask=%08x server_mask=%08x negotiated_mask=%08x",
                    self.config.coin,
                    session.worker_name or "unknown",
                    miner_mask,
                    STRATUM_VERSION_ROLLING_SERVER_MASK,
                    session.version_mask,
                )

            return {"id": req_id, "result": result, "error": None}

        if method == "mining.submit":
            start_perf = time.perf_counter()
            self.stats.shares_submitted += 1
            self.stats.last_share_at = datetime.now(timezone.utc).isoformat()

            if not session.subscribed:
                return self._reject_share(req_id, "not_subscribed")
            if not session.authorized:
                return self._reject_share(req_id, "not_authorized")

            params = req.get("params")
            if not isinstance(params, list) or len(params) < 5:
                return self._reject_share(req_id, "invalid_params")

            worker_name, job_id, extranonce2, ntime, nonce = params[:5]
            submitted_version: str | None = None
            if len(params) >= 6:
                submitted_version = str(params[5]).lower()
            extranonce2 = self._normalize_extranonce2(str(extranonce2))
            ntime = str(ntime).lower()
            nonce = str(nonce).lower()

            worker_name_str = str(worker_name)
            submitted_job_id = str(job_id)
            ex1_for_cid = session.extranonce1 or ""
            cid = self._build_share_cid(
                worker=worker_name_str,
                job_id=submitted_job_id,
                extranonce1=ex1_for_cid,
                extranonce2=str(extranonce2),
                ntime=str(ntime),
                nonce=str(nonce),
            )
            trace = ShareTrace(
                cid=cid,
                ts=datetime.now(timezone.utc).isoformat(),
                coin=self.config.coin,
                worker=worker_name_str,
                job_id=submitted_job_id,
                ex1=ex1_for_cid,
                ex2=str(extranonce2),
                ntime=str(ntime),
                nonce=str(nonce),
                submitted_version=submitted_version,
                assigned_diff=float(session.difficulty),
            )
            self._share_traces_inflight[cid] = trace
            self._log_share_rx(trace)

            current_job_id = self.stats.current_job_id
            if current_job_id:
                self._track_worker_job(worker_name_str, str(current_job_id))
            if not current_job_id or (
                submitted_job_id != str(current_job_id)
                and not self._is_recent_job_for_worker(worker_name_str, submitted_job_id)
            ):
                trace.stale = True
                self._finalize_trace(trace, result="REJECT", reason="stale_job", start_perf=start_perf)
                return self._reject_share(
                    req_id,
                    "stale_job",
                    {
                        "worker": worker_name_str,
                        "job_id": submitted_job_id,
                        "current_job_id": str(current_job_id),
                    },
                )

            if len(str(extranonce2)) != DGB_EXTRANONCE2_SIZE * 2:
                self._finalize_trace(trace, result="REJECT", reason="bad_extranonce2_size", start_perf=start_perf)
                return self._reject_share(
                    req_id,
                    "bad_extranonce2_size",
                    {
                        "worker": str(worker_name),
                        "extranonce2": str(extranonce2),
                        "expected_hex_len": DGB_EXTRANONCE2_SIZE * 2,
                        "actual_hex_len": len(str(extranonce2)),
                    },
                )

            if not self._is_hex_len(str(extranonce2), DGB_EXTRANONCE2_SIZE):
                self._finalize_trace(trace, result="REJECT", reason="invalid_extranonce2", start_perf=start_perf)
                return self._reject_share(
                    req_id,
                    "invalid_extranonce2",
                    {
                        "worker": str(worker_name),
                        "extranonce2": str(extranonce2),
                    },
                )

            if not self._is_hex_len(str(ntime), 4):
                self._finalize_trace(trace, result="REJECT", reason="invalid_ntime", start_perf=start_perf)
                return self._reject_share(req_id, "invalid_ntime")

            if not self._is_hex_len(str(nonce), 4):
                self._finalize_trace(trace, result="REJECT", reason="invalid_nonce", start_perf=start_perf)
                return self._reject_share(req_id, "invalid_nonce")

            if submitted_version is not None and not self._is_hex_len(submitted_version, 4):
                self._finalize_trace(trace, result="REJECT", reason="invalid_version", start_perf=start_perf)
                return self._reject_share(
                    req_id,
                    "invalid_version",
                    {
                        "worker": str(worker_name),
                        "version": submitted_version,
                    },
                )

            version_key = submitted_version or ""
            share_key = f"{job_id}:{extranonce2}:{ntime}:{nonce}:{version_key}"
            if share_key in self._submitted_share_keys:
                self._finalize_trace(trace, result="REJECT", reason="duplicate_share", start_perf=start_perf)
                return self._reject_share(req_id, "duplicate_share")

            job = self._active_job
            if not job:
                self._finalize_trace(trace, result="REJECT", reason="no_active_job", start_perf=start_perf)
                return self._reject_share(req_id, "no_active_job")

            trace.base_version = str(job.version).lower()
            trace.version_mask = f"{session.version_mask:08x}"
            trace.prevhash = str(job.prevhash)
            trace.nbits = str(job.nbits)
            trace.ntime_job = str(job.ntime)

            if submitted_version is not None and session.version_mask == 0:
                if submitted_version != str(job.version).lower():
                    self._finalize_trace(trace, result="REJECT", reason="invalid_version", start_perf=start_perf)
                    return self._reject_share(
                        req_id,
                        "invalid_version",
                        {
                            "worker": worker_name_str,
                            "job_id": submitted_job_id,
                            "base_version": str(job.version).lower(),
                            "submitted_version": submitted_version,
                            "version_mask": f"{session.version_mask:08x}",
                        },
                    )

            try:
                share_result = self._evaluate_share(
                    job=job,
                    session=session,
                    extranonce2=str(extranonce2),
                    ntime=str(ntime),
                    nonce=str(nonce),
                    submitted_version=submitted_version,
                    version_mask=session.version_mask,
                )
            except ValueError as exc:
                msg = str(exc)
                self._capture_share_debug(
                    reason="invalid_ntime_window" if "ntime" in msg else "invalid_share",
                    worker_name=str(worker_name),
                    job_id=str(job_id),
                    extranonce2=str(extranonce2),
                    ntime=str(ntime),
                    nonce=str(nonce),
                    session=session,
                    job=job,
                    submitted_version=submitted_version,
                    version_mask=session.version_mask,
                    extra={"error": msg},
                )
                if "ntime" in msg:
                    self._finalize_trace(trace, result="REJECT", reason="invalid_ntime_window", start_perf=start_perf)
                    return self._reject_share(req_id, "invalid_ntime_window")
                if "version" in msg:
                    self._finalize_trace(trace, result="REJECT", reason="invalid_version", start_perf=start_perf)
                    return self._reject_share(req_id, "invalid_version")
                self._finalize_trace(trace, result="REJECT", reason="invalid_share", start_perf=start_perf)
                return self._reject_share(req_id, "invalid_share")
            except Exception as exc:
                self._capture_share_debug(
                    reason="share_eval_failed",
                    worker_name=str(worker_name),
                    job_id=str(job_id),
                    extranonce2=str(extranonce2),
                    ntime=str(ntime),
                    nonce=str(nonce),
                    session=session,
                    job=job,
                    submitted_version=submitted_version,
                    version_mask=session.version_mask,
                    extra={"error": str(exc)},
                )
                logger.warning("%s share evaluation failed: %s", self.config.coin, exc)
                self._finalize_trace(trace, result="REJECT", reason="share_eval_failed", start_perf=start_perf)
                return self._reject_share(req_id, "share_eval_failed")

            trace.final_version = str(share_result.get("effective_version_hex") or "")
            trace.merkle_root = str(share_result.get("merkle_root_hex") or "")
            trace.header_hex = str(share_result.get("header_hex") or "")
            trace.hash_hex = str(share_result.get("hash_hex_be") or "")
            hash_int_big_raw = share_result.get("hash_int_big")
            hash_int_little_raw = share_result.get("hash_int_little")
            share_target_raw = share_result.get("share_target")
            share_diff_raw = share_result.get("share_difficulty")

            trace.hash_int_big = int(hash_int_big_raw) if hash_int_big_raw is not None else None
            trace.hash_int_little = int(hash_int_little_raw) if hash_int_little_raw is not None else None
            trace.share_target_int = int(share_target_raw) if share_target_raw is not None else None
            trace.share_target_hex = (
                f"{int(share_target_raw):064x}" if share_target_raw is not None else None
            )
            trace.computed_diff = float(share_diff_raw) if share_diff_raw is not None else None
            trace.meets_target = bool(share_result.get("meets_share_target"))
            trace.meets_network = bool(share_result.get("meets_network_target"))

            self._log_share_eval(trace)
            self._log_share_debug_block(trace, network_target=share_result.get("network_target"))
            self._store_share_trace(trace)

            if not share_result["meets_share_target"]:
                self._capture_share_debug(
                    reason="low_difficulty_share",
                    worker_name=worker_name_str,
                    job_id=submitted_job_id,
                    extranonce2=str(extranonce2),
                    ntime=str(ntime),
                    nonce=str(nonce),
                    session=session,
                    job=job,
                    submitted_version=submitted_version,
                    version_mask=session.version_mask,
                    share_result=share_result,
                )
                if STRATUM_DEBUG_SHARES:
                    alt_variants = share_result.get("alt_difficulty_variants") or {}
                    alt_variants_text = ", ".join(
                        f"{k}={float(v):.6e}" for k, v in alt_variants.items()
                    )
                    logger.warning(
                        "%s low difficulty share: worker=%s job_id=%s ex2=%s ntime=%s nonce=%s "
                        "share_diff=%.6e target_diff=%.6f hash=%s hash_int=%s share_target=%s "
                        "hash_int_big=%s hash_int_little=%s meets_big=%s meets_little=%s computed_diff_big=%.6f alt=[%s]",
                        self.config.coin,
                        str(worker_name),
                        str(job_id),
                        str(extranonce2),
                        str(ntime),
                        str(nonce),
                        float(share_result["share_difficulty"]),
                        float(session.difficulty),
                        str(share_result["block_hash"]),
                        str(share_result["hash_int"]),
                        str(share_result["share_target"]),
                        str(share_result.get("hash_int_big")),
                        str(share_result.get("hash_int_little")),
                        bool(share_result.get("meets_big")),
                        bool(share_result.get("meets_little")),
                        float(share_result.get("computed_diff_big") or 0.0),
                        alt_variants_text,
                    )
                    logger.warning(
                        "%s reject-trace: job_id=%s ex1=%s ex2=%s ntime=%s nonce=%s base_version=%s "
                        "submitted_version=%s version_mask=%s final_version=%s prevhash=%s "
                        "coinbase_sha256d=%s merkle_root=%s header_hex_prefix=%s hash_hex=%s "
                        "assigned_diff=%s computed_diff=%s hash_int_big=%s hash_int_little=%s "
                        "diff1_target_hex=%s share_target_hex=%s hash_le_hex=%s share_target_int=%s meets_target=%s",
                        self.config.coin,
                        submitted_job_id,
                        str(session.extranonce1),
                        str(extranonce2),
                        str(ntime),
                        str(nonce),
                        str(share_result.get("base_version_hex")),
                        str(share_result.get("submitted_version_hex")),
                        str(share_result.get("version_mask_hex")),
                        str(share_result.get("effective_version_hex")),
                        str(share_result.get("prevhash_hex")),
                        str(share_result.get("coinbase_hash_hex")),
                        str(share_result.get("merkle_root_hex")),
                        str(share_result.get("header_hex") or "")[:152],
                        str(share_result.get("hash_hex_be")),
                        float(session.difficulty),
                        float(share_result.get("share_difficulty") or 0.0),
                        int(share_result.get("hash_int_big") or 0),
                        int(share_result.get("hash_int_little") or 0),
                        DIFF1_TARGET_HEX,
                        int(share_result.get("share_target") or 0).to_bytes(32, "big").hex(),
                        str(share_result.get("hash_le_hex") or ""),
                        int(share_result.get("share_target") or 0),
                        bool(share_result.get("meets_share_target")),
                    )
                self._finalize_trace(
                    trace,
                    result="REJECT",
                    reason="low_difficulty_share",
                    start_perf=start_perf,
                )
                return self._reject_share(req_id, "low_difficulty_share")

            self._submitted_share_keys.add(share_key)

            self.stats.shares_accepted += 1
            matched_variant = share_result.get("matched_variant")
            if matched_variant:
                logger.info(
                    "%s accepted share via compatibility variant: %s (worker=%s job_id=%s)",
                    self.config.coin,
                    matched_variant,
                    str(worker_name),
                    str(job_id),
                )
            share_diff = float(share_result["share_difficulty"])
            if self.stats.best_share_difficulty is None or share_diff > self.stats.best_share_difficulty:
                self.stats.best_share_difficulty = share_diff

            if share_result["meets_network_target"] and self.rpc_client:
                self.stats.block_candidates += 1
                block_hex = share_result["block_hex"]
                try:
                    submit_result = await self.rpc_client.call("submitblock", [block_hex])
                    if submit_result in (None, "", "null"):
                        self.stats.blocks_accepted += 1
                        self.stats.last_block_submit_result = "accepted"
                        logger.info(
                            "%s block candidate accepted (job=%s hash=%s)",
                            self.config.coin,
                            job.job_id,
                            share_result["block_hash"],
                        )
                    else:
                        self.stats.blocks_rejected += 1
                        self.stats.last_block_submit_result = str(submit_result)
                        logger.warning(
                            "%s block candidate rejected by node: %s",
                            self.config.coin,
                            submit_result,
                        )
                except Exception as exc:
                    self.stats.blocks_rejected += 1
                    self.stats.last_block_submit_result = f"submit_error: {exc}"
                    logger.error("%s submitblock failed: %s", self.config.coin, exc)

            self._finalize_trace(trace, result="ACCEPT", reason=None, start_perf=start_perf)
            return {"id": req_id, "result": True, "error": None}

        return self._error(req_id, -32601, f"Method not found: {method}")

    def _log_assigned_difficulty(self, diff: float) -> None:
        share_target_int = target_from_difficulty(diff)
        diff_check = DIFF1_TARGET_INT / max(share_target_int, 1)
        logger.info(
            "%s difficulty sanity: assigned_diff=%s share_target=%064x diff_check≈%.12f",
            self.config.coin,
            diff,
            share_target_int,
            diff_check,
        )

    def _cleanup_recent_jobs(self, worker_name: str) -> None:
        now = time.time()
        q = self._recent_jobs_per_worker.get(worker_name)
        if not q:
            return
        while q and (now - q[0][1]) > STALE_JOB_GRACE_SECONDS:
            q.popleft()
        if not q:
            self._recent_jobs_per_worker.pop(worker_name, None)

    def _track_worker_job(self, worker_name: str, job_id: str) -> None:
        self._cleanup_recent_jobs(worker_name)
        q = self._recent_jobs_per_worker.setdefault(worker_name, deque(maxlen=STALE_JOB_GRACE_COUNT))
        now = time.time()
        if q and q[-1][0] == job_id:
            q[-1] = (job_id, now)
        else:
            q.append((job_id, now))

    def _add_job_to_known_workers(self, job_id: str) -> None:
        for session in self._sessions.values():
            if session.worker_name:
                self._track_worker_job(session.worker_name, job_id)

    def _is_recent_job_for_worker(self, worker_name: str, job_id: str) -> bool:
        self._cleanup_recent_jobs(worker_name)
        q = self._recent_jobs_per_worker.get(worker_name)
        if not q:
            return False
        return any(existing_job_id == job_id for existing_job_id, _ in q)

    def _build_share_cid(
        self,
        *,
        worker: str,
        job_id: str,
        extranonce1: str,
        extranonce2: str,
        ntime: str,
        nonce: str,
    ) -> str:
        return (
            f"{self.config.coin}:{worker}:{job_id}:{extranonce1}:{extranonce2}:{ntime}:{nonce}"
        )

    def _worker_trace_deque(self, worker: str) -> deque[ShareTrace]:
        traces = self._share_traces_by_worker.get(worker)
        if traces is None:
            traces = deque(maxlen=200)
            self._share_traces_by_worker[worker] = traces
        return traces

    def _store_share_trace(self, trace: ShareTrace) -> None:
        if trace.stored:
            return
        self._share_traces_global.append(trace)
        self._worker_trace_deque(trace.worker).append(trace)
        trace.stored = True

    @staticmethod
    def _kv_str(value: Any) -> str:
        if value is None:
            return "-"
        s = str(value)
        return s.replace(" ", "_")

    def _log_kv(self, event: str, **fields: Any) -> None:
        parts = [event]
        for key, value in fields.items():
            parts.append(f"{key}={self._kv_str(value)}")
        logger.info(" ".join(parts))

    def _log_share_rx(self, trace: ShareTrace) -> None:
        self._log_kv(
            "share_rx",
            cid=trace.cid,
            coin=trace.coin,
            worker=trace.worker,
            job_id=trace.job_id,
            ex1=trace.ex1,
            ex2=trace.ex2,
            ntime=trace.ntime,
            nonce=trace.nonce,
            v_sub=trace.submitted_version,
            diff_assigned=trace.assigned_diff,
        )

    def _log_share_eval(self, trace: ShareTrace) -> None:
        self._log_kv(
            "share_eval",
            cid=trace.cid,
            final_version=trace.final_version,
            prevhash=trace.prevhash,
            merkle=trace.merkle_root,
            hash=trace.hash_hex,
            hash_int_big=trace.hash_int_big,
            hash_int_little=trace.hash_int_little,
            target=trace.share_target_int,
            diff_calc=trace.computed_diff,
            meets_target=trace.meets_target,
            meets_network=trace.meets_network,
        )

    def _log_share_result(self, trace: ShareTrace, result: str) -> None:
        self._log_kv(
            "share_result",
            cid=trace.cid,
            result=result,
            reason=trace.reject_reason,
            diff_calc=trace.computed_diff,
            target_diff=trace.assigned_diff,
            rtt_ms=(f"{trace.server_response_time_ms:.3f}" if trace.server_response_time_ms is not None else None),
        )

    def _log_share_debug_block(self, trace: ShareTrace, network_target: int | None = None) -> None:
        if not HMM_STRATUM_TRACE_DEBUG:
            return
        logger.info(
            "share_debug cid=%s\n"
            "  version(base/sub/mask/final)=%s/%s/%s/%s\n"
            "  prevhash=%s\n"
            "  merkle_root=%s\n"
            "  ntime=%s nbits=%s nonce=%s\n"
            "  header_hex=%s\n"
            "  share_target_hex=%s\n"
            "  network_target_hex=%s",
            trace.cid,
            trace.base_version,
            trace.submitted_version,
            trace.version_mask,
            trace.final_version,
            trace.prevhash,
            trace.merkle_root,
            trace.ntime,
            trace.nbits,
            trace.nonce,
            trace.header_hex,
            trace.share_target_hex,
            (f"{network_target:064x}" if network_target is not None else "-"),
        )

    def _finalize_trace(self, trace: ShareTrace, *, result: str, reason: str | None, start_perf: float) -> None:
        trace.reject_reason = reason
        trace.server_response_time_ms = (time.perf_counter() - start_perf) * 1000.0
        self._store_share_trace(trace)
        self._log_share_result(trace, result)
        self._share_traces_inflight.pop(trace.cid, None)

    def get_last_shares(self, worker: str | None = None, n: int = 50) -> list[dict[str, Any]]:
        n = max(1, min(n, 500))
        if worker:
            traces = list(self._share_traces_by_worker.get(worker, deque()))
            return [t.to_summary() for t in traces[-n:]]
        traces = list(self._share_traces_global)
        return [t.to_summary() for t in traces[-n:]]

    @staticmethod
    def _is_hex_len(value: str, byte_len: int) -> bool:
        if len(value) != byte_len * 2:
            return False
        try:
            int(value, 16)
            return True
        except ValueError:
            return False

    @staticmethod
    def _normalize_extranonce2(value: str) -> str:
        raw = (value or "").strip().lower()
        if raw.startswith("0x"):
            raw = raw[2:]

        # Compatibility: accept shorter miner values by left-padding to configured size.
        expected_hex_len = DGB_EXTRANONCE2_SIZE * 2
        if len(raw) < expected_hex_len:
            raw = raw.rjust(expected_hex_len, "0")
        return raw

    def _reject_share(
        self,
        req_id: Any,
        reason: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.stats.shares_rejected += 1
        self.stats.share_reject_reasons[reason] = self.stats.share_reject_reasons.get(reason, 0) + 1
        if context:
            logger.warning("%s share rejected: %s (%s)", self.config.coin, reason, context)
        return {
            "id": req_id,
            "result": False,
            "error": [20, f"Share rejected: {reason}", None],
        }

    @staticmethod
    def _int_to_hex256(value: int | None) -> str | None:
        if value is None:
            return None
        return f"{int(value) & ((1 << 256) - 1):064x}"

    def _capture_share_debug(
        self,
        *,
        reason: str,
        worker_name: str,
        job_id: str,
        extranonce2: str,
        ntime: str,
        nonce: str,
        submitted_version: str | None = None,
        version_mask: int = 0,
        session: ClientSession,
        job: ActiveJob,
        share_result: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "coin": self.config.coin,
            "reason": reason,
            "submit": {
                "worker": worker_name,
                "job_id": job_id,
                "extranonce1": session.extranonce1,
                "extranonce2": extranonce2,
                "ntime": ntime,
                "nonce": nonce,
                "submitted_version": submitted_version,
                "version_mask": f"{version_mask & 0xFFFFFFFF:08x}",
                "assigned_difficulty": session.difficulty,
            },
            "job": {
                "current_job_id": self.stats.current_job_id,
                "version": job.version,
                "prevhash": job.prevhash,
                "prevhash_be": job.prevhash_be,
                "nbits": job.nbits,
                "ntime": job.ntime,
                "coinb1": job.coinb1,
                "coinb2": job.coinb2,
                "merkle_branch": list(job.merkle_branch),
                "target_1": job.target_1,
                "target_1_hex": self._int_to_hex256(job.target_1),
            },
        }

        if share_result:
            payload["evaluation"] = {
                "matched_variant": share_result.get("matched_variant"),
                "hash_int": share_result.get("hash_int"),
                "hash_hex": share_result.get("block_hash"),
                "share_target": share_result.get("share_target"),
                "share_target_hex": self._int_to_hex256(share_result.get("share_target")),
                "network_target": share_result.get("network_target"),
                "network_target_hex": self._int_to_hex256(share_result.get("network_target")),
                "share_difficulty": share_result.get("share_difficulty"),
                "meets_share_target": share_result.get("meets_share_target"),
                "meets_network_target": share_result.get("meets_network_target"),
                "effective_version_hex": share_result.get("effective_version_hex"),
                "alt_difficulty_variants": share_result.get("alt_difficulty_variants", {}),
                "block_hex_prefix": (share_result.get("block_hex") or "")[:200],
            }

        if extra:
            payload["extra"] = extra

        self._last_share_debug = payload

    def _evaluate_share(
        self,
        *,
        job: ActiveJob,
        session: ClientSession,
        extranonce2: str,
        ntime: str,
        nonce: str,
        submitted_version: str | None = None,
        version_mask: int = 0,
    ) -> dict[str, Any]:
        if not session.extranonce1:
            raise ValueError("session extranonce1 missing")

        ntime_int = int(ntime, 16)
        job_ntime_int = int(job.ntime, 16)
        if ntime_int < (job_ntime_int - 600) or ntime_int > (job_ntime_int + 7200):
            raise ValueError("ntime out of acceptable range")

        job_version_int = int(job.version, 16) & 0xFFFFFFFF
        submitted_version_int = int(submitted_version, 16) & 0xFFFFFFFF if submitted_version else None
        mask_int = version_mask & 0xFFFFFFFF

        final_version_candidates: dict[str, int] = {}
        if submitted_version_int is None:
            final_version_candidates["canonical"] = job_version_int
        elif mask_int != 0:
            final_version_candidates["canonical"] = (
                (job_version_int & (~mask_int & 0xFFFFFFFF))
                | (submitted_version_int & mask_int)
            ) & 0xFFFFFFFF

            # Compatibility path: some miners send submit version value with
            # opposite byte order.
            submitted_version_swapped = struct.unpack(">I", struct.pack("<I", submitted_version_int)
            )[0]
            final_version_candidates["submit_version_bswap32"] = (
                (job_version_int & (~mask_int & 0xFFFFFFFF))
                | (submitted_version_swapped & mask_int)
            ) & 0xFFFFFFFF
        else:
            if submitted_version_int != job_version_int:
                raise ValueError("invalid_version")
            final_version_candidates["canonical"] = job_version_int

        coinbase_bytes = build_coinbase(job.coinb1, session.extranonce1, extranonce2, job.coinb2)
        merkle_root_bytes = build_merkle_root(coinbase_bytes, job.merkle_branch)
        share_target = target_from_difficulty(max(session.difficulty, 0.000001))
        network_target = _target_from_nbits(job.nbits)

        ntime_bytes_le = struct.pack("<I", ntime_int)
        ntime_bytes_raw = bytes.fromhex(ntime)
        nbits_bytes_le = struct.pack("<I", int(job.nbits, 16))
        nbits_bytes_raw = bytes.fromhex(job.nbits)
        nonce_bytes_le = struct.pack("<I", int(nonce, 16))
        nonce_bytes_raw = bytes.fromhex(nonce)

        prevhash_from_be_reversed = bytes.fromhex(job.prevhash_be)[::-1]
        prevhash_notify_direct = bytes.fromhex(job.prevhash)
        merkle_display = merkle_root_bytes
        merkle_internal = merkle_root_bytes[::-1]

        def _assemble_header(
            version_int: int,
            prevhash_bytes: bytes,
            merkle_bytes: bytes,
            *,
            version_raw: bool,
            ntime_raw: bool,
            nbits_raw: bool,
            nonce_raw: bool,
        ) -> bytes:
            version_bytes = (
                bytes.fromhex(f"{version_int & 0xFFFFFFFF:08x}")
                if version_raw
                else struct.pack("<I", version_int)
            )
            h = (
                version_bytes
                + prevhash_bytes
                + merkle_bytes
                + (ntime_bytes_raw if ntime_raw else ntime_bytes_le)
                + (nbits_bytes_raw if nbits_raw else nbits_bytes_le)
                + (nonce_bytes_raw if nonce_raw else nonce_bytes_le)
            )
            if len(h) != 80:
                raise ValueError("invalid header length")
            return h

        variants: dict[str, tuple[bytes, bytes, int, int, float, bool, bool]] = {}

        candidate_headers: dict[str, bytes] = {}
        for version_name, version_int in final_version_candidates.items():
            for version_raw in (False, True):
                for ntime_raw in (False, True):
                    for nbits_raw in (False, True):
                        for nonce_raw in (False, True):
                            mode_suffix = (
                                f"ver={'raw' if version_raw else 'le'}"
                                f";ntime={'raw' if ntime_raw else 'le'}"
                                f";nbits={'raw' if nbits_raw else 'le'}"
                                f";nonce={'raw' if nonce_raw else 'le'}"
                            )
                            prefix = f"{version_name}:{mode_suffix}"
                            candidate_headers[f"{prefix}"] = _assemble_header(
                                version_int,
                                prevhash_from_be_reversed,
                                merkle_internal,
                                version_raw=version_raw,
                                ntime_raw=ntime_raw,
                                nbits_raw=nbits_raw,
                                nonce_raw=nonce_raw,
                            )
                            candidate_headers[f"{prefix}:prevhash_notify_direct"] = _assemble_header(
                                version_int,
                                prevhash_notify_direct,
                                merkle_internal,
                                version_raw=version_raw,
                                ntime_raw=ntime_raw,
                                nbits_raw=nbits_raw,
                                nonce_raw=nonce_raw,
                            )
                            candidate_headers[f"{prefix}:merkle_direct"] = _assemble_header(
                                version_int,
                                prevhash_from_be_reversed,
                                merkle_display,
                                version_raw=version_raw,
                                ntime_raw=ntime_raw,
                                nbits_raw=nbits_raw,
                                nonce_raw=nonce_raw,
                            )
                            candidate_headers[
                                f"{prefix}:prevhash_notify_direct_merkle_direct"
                            ] = _assemble_header(
                                version_int,
                                prevhash_notify_direct,
                                merkle_display,
                                version_raw=version_raw,
                                ntime_raw=ntime_raw,
                                nbits_raw=nbits_raw,
                                nonce_raw=nonce_raw,
                            )

        for name, candidate_header in candidate_headers.items():
            hbin, hbig = hash_header(candidate_header)
            hlittle = int.from_bytes(hbin, "little")
            sdiff = difficulty_from_hash(hbin)
            meets_share_variant = meets_share(hbin, share_target)
            meets_network = hlittle <= network_target
            variants[name] = (
                candidate_header,
                hbin,
                hbig,
                hlittle,
                sdiff,
                meets_share_variant,
                meets_network,
            )

        selected_name = "canonical:ver=le;ntime=le;nbits=le;nonce=le"
        if not variants[selected_name][5] and STRATUM_COMPAT_ACCEPT_VARIANTS:
            pass_variants = [name for name, row in variants.items() if row[5]]
            if pass_variants:
                selected_name = max(pass_variants, key=lambda n: variants[n][4])

        header_bytes, header_hash_bin, hash_int_big, hash_int_little, share_difficulty, meets_share_target, meets_network_target = variants[selected_name]
        meets_little = hash_int_little <= share_target
        meets_big = hash_int_big <= share_target

        alt_difficulty_variants = {
            name: float(row[4]) for name, row in variants.items() if name != selected_name
        }
        matched_variant = selected_name if selected_name != "canonical" else None
        selected_version_label = selected_name.split(":", 1)[0]
        final_version_int = final_version_candidates.get(selected_version_label, final_version_candidates["canonical"])

        tx_count = _encode_varint(1 + len(job.tx_datas))
        block_hex = header_bytes.hex() + tx_count.hex() + coinbase_bytes.hex() + "".join(job.tx_datas)

        return {
            "hash_int": hash_int_little,
            "block_hash": header_hash_bin.hex(),
            "hash_hex_be": header_hash_bin.hex(),
            "hash_int_big": hash_int_big,
            "hash_int_little": hash_int_little,
            "hash_le_hex": header_hash_bin[::-1].hex(),
            "meets_share_target": meets_share_target,
            "meets_network_target": meets_network_target,
            "meets_big": meets_big,
            "meets_little": meets_little,
            "share_target": share_target,
            "network_target": network_target,
            "block_hex": block_hex,
            "header_hex": header_bytes.hex(),
            "coinbase_hex": coinbase_bytes.hex(),
            "coinbase_hash_hex": sha256d(coinbase_bytes).hex(),
            "merkle_root_hex": merkle_root_bytes.hex(),
            "share_difficulty": share_difficulty,
            "computed_diff_big": share_difficulty,
            "alt_difficulty_variants": alt_difficulty_variants,
            "matched_variant": matched_variant,
            "effective_version_hex": f"{final_version_int:08x}",
            "base_version_hex": f"{job_version_int:08x}",
            "submitted_version_hex": (
                f"{submitted_version_int:08x}" if submitted_version_int is not None else None
            ),
            "version_mask_hex": f"{mask_int:08x}",
            "prevhash_hex": job.prevhash_be,
            "meets_target": meets_share_target,
        }

    async def _write_json(self, writer: asyncio.StreamWriter, payload: dict[str, Any]) -> None:
        if writer is None:
            return
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

        configs["DGB"].algo = "sha256d"
        return configs
    except Exception as exc:
        logger.error("Failed loading stratum config overrides (%s): %s", CONFIG_PATH, exc)
        return configs


def _save_overrides_to_disk(configs: dict[str, CoinConfig]) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(_serialize_config(configs), f, indent=2)


def _swap_endian_words_32(hex_data: str) -> str:
    """Swap byte order within each 4-byte word (Stratum prevhash convention)."""
    raw = bytes.fromhex(hex_data)
    if len(raw) != 32:
        raise ValueError("expected 32-byte hash")
    return b"".join(raw[i : i + 4][::-1] for i in range(0, 32, 4)).hex()


def sha256d(b: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def build_coinbase(
    coinb1_hex: str,
    extranonce1_hex: str,
    extranonce2_hex: str,
    coinb2_hex: str,
) -> bytes:
    # IMPORTANT: extranonce2 is appended as raw bytes exactly as provided.
    coinbase = (
        bytes.fromhex(coinb1_hex)
        + bytes.fromhex(extranonce1_hex)
        + bytes.fromhex(extranonce2_hex)
        + bytes.fromhex(coinb2_hex)
    )
    assert isinstance(coinbase, bytes)
    assert len(coinbase) > 0
    return coinbase


def build_merkle_root(coinbase_bytes: bytes, merkle_branch_hex_list: list[str]) -> bytes:
    assert isinstance(coinbase_bytes, bytes)
    assert len(coinbase_bytes) > 0

    # Internal merkle math uses little-endian hash bytes.
    root = sha256d(coinbase_bytes)
    for branch_hex in merkle_branch_hex_list:
        branch = bytes.fromhex(branch_hex)
        if len(branch) != 32:
            raise ValueError("invalid merkle branch hash length")
        # Notify merkle branches are already provided in the same little-endian
        # byte convention used by the internal merkle accumulator.
        root = sha256d(root + branch)

    assert len(root) == 32
    # Return display-order bytes for logging/callers; header builder will
    # convert back to little-endian placement.
    return root[::-1]


def build_header(
    final_version_int: int,
    prevhash_hex: str,
    merkle_root_bytes: bytes,
    ntime_hex: str,
    nbits_hex: str,
    nonce_hex: str,
) -> bytes:
    assert 0 <= final_version_int <= 0xFFFFFFFF
    assert len(merkle_root_bytes) == 32

    prevhash_be_bytes = bytes.fromhex(prevhash_hex)
    assert len(prevhash_be_bytes) == 32
    prevhash_le_bytes = prevhash_be_bytes[::-1]
    merkle_root_le_bytes = merkle_root_bytes[::-1]

    ntime_int = int(ntime_hex, 16)
    nbits_int = int(nbits_hex, 16)
    nonce_int = int(nonce_hex, 16)

    header = (
        struct.pack("<I", final_version_int)
        + prevhash_le_bytes
        + merkle_root_le_bytes
        + struct.pack("<I", ntime_int)
        + struct.pack("<I", nbits_int)
        + struct.pack("<I", nonce_int)
    )
    assert len(header) == 80
    return header


def hash_header(header_bytes: bytes) -> tuple[bytes, int]:
    assert len(header_bytes) == 80
    hash_bytes = sha256d(header_bytes)
    hash_int_big = int.from_bytes(hash_bytes, "big")
    return hash_bytes, hash_int_big


def validate_share(hash_int_big: int, share_target_int: int) -> bool:
    return hash_int_big <= share_target_int


def _sha256d(payload: bytes) -> bytes:
    return sha256d(payload)


def _target_from_nbits(nbits_hex: str) -> int:
    compact = int(nbits_hex, 16)
    exponent = compact >> 24
    mantissa = compact & 0x007FFFFF

    if exponent <= 3:
        target = mantissa >> (8 * (3 - exponent))
    else:
        target = mantissa << (8 * (exponent - 3))

    return max(0, min(target, (1 << 256) - 1))


def _difficulty_to_target(difficulty: float, target_1: int = TARGET_1) -> int:
    # Keep legacy helper name for compatibility; use canonical diff1 target math.
    return target_from_difficulty(difficulty)


def target_from_difficulty(diff: float) -> int:
    """
    Return share target as LITTLE-ENDIAN integer.
    """
    if diff <= 0:
        raise ValueError("diff must be > 0")

    # integer diff fast path
    d_int = int(round(diff))
    if abs(diff - d_int) <= 1e-9:
        return DIFF1_TARGET_INT // d_int

    # fractional diff safe path
    getcontext().prec = 80
    return int(Decimal(DIFF1_TARGET_INT) / Decimal(str(diff)))


def meets_share(hash256_bytes: bytes, share_target_int: int) -> bool:
    """
    Compare SHA256d digest using little-endian integer (Bitcoin PoW convention).
    """
    h = int.from_bytes(hash256_bytes, "little")
    return h <= share_target_int


def difficulty_from_hash(hash256_bytes: bytes) -> float:
    """
    Compute actual share difficulty from hash (little-endian).
    """
    getcontext().prec = 80
    h = int.from_bytes(hash256_bytes, "little")
    if h == 0:
        return float("inf")
    return float(Decimal(DIFF1_TARGET_INT) / Decimal(h))


def _encode_varint(value: int) -> bytes:
    if value < 0xFD:
        return bytes([value])
    if value <= 0xFFFF:
        return b"\xfd" + value.to_bytes(2, "little")
    if value <= 0xFFFFFFFF:
        return b"\xfe" + value.to_bytes(4, "little")
    return b"\xff" + value.to_bytes(8, "little")


def _scriptnum_encode(value: int) -> bytes:
    if value == 0:
        return b""
    result = bytearray()
    neg = value < 0
    value = abs(value)
    while value:
        result.append(value & 0xFF)
        value >>= 8
    if result[-1] & 0x80:
        result.append(0x80 if neg else 0x00)
    elif neg:
        result[-1] |= 0x80
    return bytes(result)


def _push_data(data: bytes) -> bytes:
    if len(data) < 0x4C:
        return bytes([len(data)]) + data
    raise ValueError("pushdata too long for scaffold")


def _build_dgb_coinbase_parts(tpl: dict[str, Any]) -> tuple[str, str]:
    coinbase_value = int(tpl.get("coinbasevalue", 0))
    height = int(tpl.get("height", 0))
    script_pubkey_hex = os.getenv("DGB_COINBASE_SCRIPT_PUBKEY", "51").strip() or "51"
    script_pubkey = bytes.fromhex(script_pubkey_hex)

    height_script = _push_data(_scriptnum_encode(height))
    tag_script = _push_data(b"HMM-DGB")

    script_prefix = height_script + tag_script
    script_suffix = b""

    script_sig_len = len(script_prefix) + DGB_EXTRANONCE1_SIZE + DGB_EXTRANONCE2_SIZE + len(script_suffix)
    script_sig_len_enc = _encode_varint(script_sig_len)

    version = (1).to_bytes(4, "little")
    vin_count = _encode_varint(1)
    prevout = b"\x00" * 32 + (0xFFFFFFFF).to_bytes(4, "little")

    sequence = (0xFFFFFFFF).to_bytes(4, "little")
    vout_count = _encode_varint(1)
    value = coinbase_value.to_bytes(8, "little", signed=False)
    script_pubkey_len = _encode_varint(len(script_pubkey))
    locktime = (0).to_bytes(4, "little")

    coinb1 = (
        version
        + vin_count
        + prevout
        + script_sig_len_enc
        + script_prefix
    )
    coinb2 = (
        script_suffix
        + sequence
        + vout_count
        + value
        + script_pubkey_len
        + script_pubkey
        + locktime
    )

    return coinb1.hex(), coinb2.hex()


def _build_coinbase_merkle_branch(tpl: dict[str, Any], coinbase_hash: bytes) -> list[str]:
    tx_hashes: list[bytes] = []
    for tx in tpl.get("transactions", []):
        tx_hex = tx.get("txid") or tx.get("hash")
        if isinstance(tx_hex, str) and len(tx_hex) == 64:
            tx_hashes.append(bytes.fromhex(tx_hex)[::-1])

    level = [coinbase_hash] + tx_hashes
    if not level:
        return []

    index = 0
    branch: list[str] = []

    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])

        sibling = index ^ 1
        branch.append(level[sibling].hex())

        next_level: list[bytes] = []
        for i in range(0, len(level), 2):
            next_level.append(_sha256d(level[i] + level[i + 1]))

        level = next_level
        index //= 2

    return branch


def _dgb_job_from_template(tpl: dict[str, Any], target_1: int = TARGET_1) -> ActiveJob:
    job_id = uuid.uuid4().hex[:16]
    prevhash_be = str(tpl["previousblockhash"])
    prevhash = _swap_endian_words_32(prevhash_be)
    version = f"{int(tpl['version']) & 0xFFFFFFFF:08x}"
    nbits = str(tpl["bits"])
    ntime = f"{int(tpl['curtime']) & 0xFFFFFFFF:08x}"

    coinb1, coinb2 = _build_dgb_coinbase_parts(tpl)
    dummy_ex1 = "00" * DGB_EXTRANONCE1_SIZE
    dummy_ex2 = "00" * DGB_EXTRANONCE2_SIZE
    coinbase_hash = _sha256d(bytes.fromhex(coinb1 + dummy_ex1 + dummy_ex2 + coinb2))
    merkle_branch = _build_coinbase_merkle_branch(tpl, coinbase_hash)

    return ActiveJob(
        job_id=job_id,
        prevhash=prevhash,
        prevhash_be=prevhash_be,
        coinb1=coinb1,
        coinb2=coinb2,
        merkle_branch=merkle_branch,
        version=version,
        nbits=nbits,
        ntime=ntime,
        clean_jobs=True,
        template_height=tpl.get("height"),
        target_1=target_1,
        tx_datas=[str(tx.get("data", "")) for tx in tpl.get("transactions", []) if tx.get("data")],
    )


app = FastAPI(title="HMM-Local Stratum Gateway", version="0.2.0")

_BIND_HOST = os.getenv("STRATUM_BIND_HOST", "0.0.0.0")
_CONFIGS = _load_overrides_from_disk(_load_coin_configs())
_SERVERS: dict[str, StratumServer] = {
    coin: StratumServer(config=cfg, bind_host=_BIND_HOST, rpc_client=RpcClient(cfg))
    for coin, cfg in _CONFIGS.items()
}
_DGB_POLLER_TASK: asyncio.Task | None = None


async def _rpc_test_coin(coin: str) -> dict[str, Any]:
    normalized = coin.upper()
    if normalized not in _CONFIGS:
        raise HTTPException(status_code=404, detail=f"Unknown coin: {coin}")

    cfg = _CONFIGS[normalized]
    client = RpcClient(cfg)

    try:
        chain = await client.call("getblockchaininfo")
        mining = await client.call("getmininginfo")
        if normalized == "DGB":
            gbt = await client.call("getblocktemplate", [{"rules": ["segwit"]}, "sha256d"])
        else:
            gbt = await client.call("getblocktemplate", [{"rules": ["segwit"]}])
        return {
            "ok": True,
            "coin": normalized,
            "chain": chain.get("chain"),
            "blocks": chain.get("blocks"),
            "headers": chain.get("headers"),
            "initialblockdownload": chain.get("initialblockdownload"),
            "networkhashps": mining.get("networkhashps"),
            "template_height": gbt.get("height"),
        }
    except Exception as exc:
        return {"ok": False, "coin": normalized, "error": str(exc)}


async def _dgb_template_poller() -> None:
    cfg = _CONFIGS["DGB"]
    server = _SERVERS["DGB"]
    client = RpcClient(cfg)
    last_template_sig: str | None = None

    logger.info("Starting DGB template poller (%ss)", DGB_TEMPLATE_POLL_SECONDS)
    while True:
        try:
            chain = await client.call("getblockchaininfo")
            tpl = await client.call("getblocktemplate", [{"rules": ["segwit"]}, "sha256d"])

            server.stats.rpc_last_ok_at = datetime.now(timezone.utc).isoformat()
            server.stats.rpc_last_error = None
            server.stats.chain_height = chain.get("blocks")

            template_sig = (
                f"{tpl.get('previousblockhash')}:{tpl.get('curtime')}:{tpl.get('bits')}:{tpl.get('pow_algo')}"
            )
            if template_sig != last_template_sig:
                last_template_sig = template_sig
                # Stratum share difficulty uses Bitcoin diff1 target baseline.
                # Network block validity still uses nBits-derived network target.
                job = _dgb_job_from_template(tpl, target_1=TARGET_1)
                await server.set_job(job)
                logger.info("DGB new template -> job %s (height=%s)", job.job_id, tpl.get("height"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            server.stats.rpc_last_error = str(exc)
            logger.warning("DGB template poll failed: %s", exc)

        await asyncio.sleep(DGB_TEMPLATE_POLL_SECONDS)


async def _restart_servers() -> None:
    global _DGB_POLLER_TASK

    if _DGB_POLLER_TASK:
        _DGB_POLLER_TASK.cancel()
        try:
            await _DGB_POLLER_TASK
        except asyncio.CancelledError:
            pass
        _DGB_POLLER_TASK = None

    for server in _SERVERS.values():
        await server.stop()

    for coin, cfg in _CONFIGS.items():
        _SERVERS[coin] = StratumServer(config=cfg, bind_host=_BIND_HOST, rpc_client=RpcClient(cfg))

    for server in _SERVERS.values():
        await server.start()

    _DGB_POLLER_TASK = asyncio.create_task(_dgb_template_poller())


def _difficulty_self_test() -> None:
    sample_diff = 512.0
    share_target_int = target_from_difficulty(sample_diff)
    diff_check = DIFF1_TARGET_INT / max(share_target_int, 1)
    logger.info(
        "difficulty self-test: assigned_diff=%s share_target_hex=%064x diff_check≈%.12f",
        sample_diff,
        share_target_int,
        diff_check,
    )


@app.on_event("startup")
async def startup_event() -> None:
    _difficulty_self_test()
    await _restart_servers()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    global _DGB_POLLER_TASK

    if _DGB_POLLER_TASK:
        _DGB_POLLER_TASK.cancel()
        try:
            await _DGB_POLLER_TASK
        except asyncio.CancelledError:
            pass

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
    <link rel=\"icon\" type=\"image/svg+xml\" href=\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0%25' stop-color='%230b1220'/%3E%3Cstop offset='100%25' stop-color='%231e3a8a'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='64' height='64' rx='14' fill='url(%23g)'/%3E%3Cpath d='M17 22h30l-8 10 8 10H17l8-10z' fill='%2338bdf8'/%3E%3Ccircle cx='49' cy='20' r='6' fill='%2322d3ee'/%3E%3C/svg%3E\">
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
        <button class=\"secondary\" onclick=\"testDgbRpc()\">Test DGB RPC</button>
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
      for (const coin of ['BTC', 'BCH', 'DGB']) {
        document.getElementById(`${coin}_rpc_url`).value = cfg[coin].rpc_url || '';
        document.getElementById(`${coin}_rpc_user`).value = cfg[coin].rpc_user || '';
        document.getElementById(`${coin}_rpc_password`).value = cfg[coin].rpc_password || '';
      }
      document.getElementById('status').textContent = 'Config loaded';
    }

    async function saveConfig() {
      const payload = {};
      for (const coin of ['BTC', 'BCH', 'DGB']) {
        payload[coin] = {
          rpc_url: document.getElementById(`${coin}_rpc_url`).value,
          rpc_user: document.getElementById(`${coin}_rpc_user`).value,
          rpc_password: document.getElementById(`${coin}_rpc_password`).value,
        };
      }

      const r = await fetch('/config', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!r.ok) {
        document.getElementById('status').textContent = `Save failed: ${await r.text()}`;
        return;
      }
      document.getElementById('status').textContent = 'Saved and listeners restarted';
      await loadStats();
    }

    async function testDgbRpc() {
      const r = await fetch('/rpc/test/DGB');
      const result = await r.json();
      document.getElementById('status').textContent = result.ok
        ? `DGB RPC OK (height ${result.blocks}, template ${result.template_height})`
        : `DGB RPC failed: ${result.error}`;
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


@app.get("/rpc/test/{coin}")
async def rpc_test(coin: str) -> dict[str, Any]:
    return await _rpc_test_coin(coin)


@app.get("/debug/last-share/{coin}")
async def debug_last_share(coin: str) -> dict[str, Any]:
    normalized = coin.upper()
    if normalized not in _SERVERS:
        raise HTTPException(status_code=404, detail=f"Unknown coin: {coin}")

    server = _SERVERS[normalized]
    if not server._last_share_debug:
        return {"ok": False, "coin": normalized, "message": "No captured share debug yet"}

    return {"ok": True, "coin": normalized, "data": server._last_share_debug}


@app.get("/debug/last-shares")
async def debug_last_shares(worker: Optional[str] = None, n: int = 50) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for coin, server in _SERVERS.items():
        for row in server.get_last_shares(worker=worker, n=n):
            rows.append({"coin": coin, **row})

    rows.sort(key=lambda r: r.get("ts") or "")
    if len(rows) > n:
        rows = rows[-n:]

    return {"ok": True, "worker": worker, "count": len(rows), "shares": rows}


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
