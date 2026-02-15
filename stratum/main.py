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
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

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

# Bitcoin-style target1 constant for SHA256 PoW difficulty calculations.
TARGET_1 = int("00000000FFFF0000000000000000000000000000000000000000000000000000", 16)


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

            # Static baseline difficulty for initial phase.
            await self._write_json(
                writer,
                {"id": None, "method": "mining.set_difficulty", "params": [session.difficulty]},
            )

            # If we already have a live job, push it immediately.
            if self._active_job:
                await self._write_json(
                    writer,
                    {"id": None, "method": "mining.notify", "params": self._active_job.notify_params()},
                )

            return {"id": req_id, "result": True, "error": None}

        if method == "mining.extranonce.subscribe":
            return {"id": req_id, "result": True, "error": None}

        if method == "mining.submit":
            self.stats.shares_submitted += 1
            self.stats.last_share_at = datetime.now(timezone.utc).isoformat()

            if not session.subscribed:
                return self._reject_share(req_id, "not_subscribed")
            if not session.authorized:
                return self._reject_share(req_id, "not_authorized")

            params = req.get("params")
            if not isinstance(params, list) or len(params) < 5:
                return self._reject_share(req_id, "invalid_params")

            _, job_id, extranonce2, ntime, nonce = params[:5]
            extranonce2 = str(extranonce2).lower()
            ntime = str(ntime).lower()
            nonce = str(nonce).lower()

            current_job_id = self.stats.current_job_id
            if not current_job_id or str(job_id) != str(current_job_id):
                return self._reject_share(req_id, "stale_job")

            if len(str(extranonce2)) != DGB_EXTRANONCE2_SIZE * 2:
                return self._reject_share(req_id, "bad_extranonce2_size")

            if not self._is_hex_len(str(extranonce2), 2):
                return self._reject_share(req_id, "invalid_extranonce2")

            if not self._is_hex_len(str(ntime), 8):
                return self._reject_share(req_id, "invalid_ntime")

            if not self._is_hex_len(str(nonce), 8):
                return self._reject_share(req_id, "invalid_nonce")

            share_key = f"{job_id}:{extranonce2}:{ntime}:{nonce}"
            if share_key in self._submitted_share_keys:
                return self._reject_share(req_id, "duplicate_share")

            job = self._active_job
            if not job:
                return self._reject_share(req_id, "no_active_job")

            try:
                share_result = self._evaluate_share(
                    job=job,
                    session=session,
                    extranonce2=str(extranonce2),
                    ntime=str(ntime),
                    nonce=str(nonce),
                )
            except ValueError as exc:
                msg = str(exc)
                if "ntime" in msg:
                    return self._reject_share(req_id, "invalid_ntime_window")
                return self._reject_share(req_id, "invalid_share")
            except Exception as exc:
                logger.warning("%s share evaluation failed: %s", self.config.coin, exc)
                return self._reject_share(req_id, "share_eval_failed")

            if not share_result["meets_share_target"]:
                return self._reject_share(req_id, "low_difficulty_share")

            self._submitted_share_keys.add(share_key)

            self.stats.shares_accepted += 1
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

            return {"id": req_id, "result": True, "error": None}

        return self._error(req_id, -32601, f"Method not found: {method}")

    @staticmethod
    def _is_hex_len(value: str, byte_len: int) -> bool:
        if len(value) != byte_len * 2:
            return False
        try:
            int(value, 16)
            return True
        except ValueError:
            return False

    def _reject_share(self, req_id: Any, reason: str) -> dict[str, Any]:
        self.stats.shares_rejected += 1
        self.stats.share_reject_reasons[reason] = self.stats.share_reject_reasons.get(reason, 0) + 1
        return {
            "id": req_id,
            "result": False,
            "error": [20, f"Share rejected: {reason}", None],
        }

    def _evaluate_share(
        self,
        *,
        job: ActiveJob,
        session: ClientSession,
        extranonce2: str,
        ntime: str,
        nonce: str,
    ) -> dict[str, Any]:
        if not session.extranonce1:
            raise ValueError("session extranonce1 missing")

        # Build coinbase from parts and compute merkle root.
        coinbase_hex = job.coinb1 + session.extranonce1 + extranonce2 + job.coinb2
        coinbase_hash = _sha256d(bytes.fromhex(coinbase_hex))

        merkle_root = coinbase_hash
        for branch_hex in job.merkle_branch:
            merkle_root = _sha256d(merkle_root + bytes.fromhex(branch_hex))

        # Build block header (80 bytes)
        ntime_int = int(ntime, 16)
        job_ntime_int = int(job.ntime, 16)
        if ntime_int < (job_ntime_int - 600) or ntime_int > (job_ntime_int + 7200):
            raise ValueError("ntime out of acceptable range")

        header = (
            bytes.fromhex(job.version)[::-1]
            + bytes.fromhex(job.prevhash_be)[::-1]
            + merkle_root
            + bytes.fromhex(ntime)[::-1]
            + bytes.fromhex(job.nbits)[::-1]
            + bytes.fromhex(nonce)[::-1]
        )

        header_hash_bin = _sha256d(header)
        hash_int = int.from_bytes(header_hash_bin, byteorder="little")

        share_target = _difficulty_to_target(max(session.difficulty, 0.000001))
        network_target = _target_from_nbits(job.nbits)
        share_difficulty = TARGET_1 / max(hash_int, 1)

        tx_count = _encode_varint(1 + len(job.tx_datas))
        block_hex = header.hex() + tx_count.hex() + coinbase_hex + "".join(job.tx_datas)

        return {
            "hash_int": hash_int,
            "block_hash": header_hash_bin[::-1].hex(),
            "meets_share_target": hash_int <= share_target,
            "meets_network_target": hash_int <= network_target,
            "block_hex": block_hex,
            "share_difficulty": share_difficulty,
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


def _sha256d(payload: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(payload).digest()).digest()


def _target_from_nbits(nbits_hex: str) -> int:
    compact = int(nbits_hex, 16)
    exponent = compact >> 24
    mantissa = compact & 0x007FFFFF

    if exponent <= 3:
        target = mantissa >> (8 * (3 - exponent))
    else:
        target = mantissa << (8 * (exponent - 3))

    return max(0, min(target, (1 << 256) - 1))


def _difficulty_to_target(difficulty: float) -> int:
    return int(TARGET_1 / difficulty)


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


def _dgb_job_from_template(tpl: dict[str, Any]) -> ActiveJob:
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
            tpl = await client.call("getblocktemplate", [{"rules": ["segwit"]}])

            server.stats.rpc_last_ok_at = datetime.now(timezone.utc).isoformat()
            server.stats.rpc_last_error = None
            server.stats.chain_height = chain.get("blocks")

            template_sig = f"{tpl.get('previousblockhash')}:{tpl.get('curtime')}:{tpl.get('bits')}"
            if template_sig != last_template_sig:
                last_template_sig = template_sig
                job = _dgb_job_from_template(tpl)
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


@app.on_event("startup")
async def startup_event() -> None:
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
