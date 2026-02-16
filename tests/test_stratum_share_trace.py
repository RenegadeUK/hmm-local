from __future__ import annotations

import logging
import runpy
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STRATUM_MAIN = ROOT / "stratum" / "main.py"
MOD = runpy.run_path(str(STRATUM_MAIN))


def _make_server():
    cfg = MOD["CoinConfig"](
        coin="DGB",
        algo="sha256d",
        stratum_port=3335,
        rpc_url="http://127.0.0.1:14022",
        rpc_user="",
        rpc_password="",
    )
    return MOD["StratumServer"](config=cfg, bind_host="127.0.0.1", rpc_client=None)


def _make_trace(server, cid: str, worker: str = "w"):
    return MOD["ShareTrace"](
        cid=cid,
        ts=datetime.now(timezone.utc).isoformat(),
        coin="DGB",
        worker=worker,
        job_id="job1",
        ex1="00000001",
        ex2="00000000",
        ntime="6992636c",
        nonce="01080198",
    )


def test_cid_generation_stability() -> None:
    server = _make_server()
    cid1 = server._build_share_cid(
        worker="worker1",
        job_id="jobA",
        extranonce1="00000001",
        extranonce2="00000000",
        ntime="6992636c",
        nonce="01080198",
    )
    cid2 = server._build_share_cid(
        worker="worker1",
        job_id="jobA",
        extranonce1="00000001",
        extranonce2="00000000",
        ntime="6992636c",
        nonce="01080198",
    )
    assert cid1 == cid2


def test_ring_buffer_size_limits() -> None:
    server = _make_server()
    for i in range(6000):
        trace = _make_trace(server, cid=f"cid-{i}", worker="workerA")
        server._store_share_trace(trace)

    assert len(server._share_traces_global) == 5000
    assert len(server._share_traces_by_worker["workerA"]) == 200


def test_logging_functions_tolerate_missing_optional_fields(caplog) -> None:
    server = _make_server()
    trace = _make_trace(server, cid="cid-missing")
    # leave optional fields as None
    with caplog.at_level(logging.INFO):
        server._log_share_eval(trace)
        server._log_share_result(trace, "REJECT")

    assert any("share_eval" in rec.message for rec in caplog.records)
    assert any("share_result" in rec.message for rec in caplog.records)


def test_debug_dump_gated_by_env_flag(caplog) -> None:
    server = _make_server()
    trace = _make_trace(server, cid="cid-debug")

    globals_ref = server._log_share_debug_block.__globals__
    old_value = globals_ref["HMM_STRATUM_TRACE_DEBUG"]
    try:
        globals_ref["HMM_STRATUM_TRACE_DEBUG"] = False
        with caplog.at_level(logging.INFO):
            server._log_share_debug_block(trace, network_target=1)
        assert not any("share_debug cid=cid-debug" in rec.message for rec in caplog.records)

        caplog.clear()
        globals_ref["HMM_STRATUM_TRACE_DEBUG"] = True
        with caplog.at_level(logging.INFO):
            server._log_share_debug_block(trace, network_target=1)
        assert any("share_debug cid=cid-debug" in rec.message for rec in caplog.records)
    finally:
        globals_ref["HMM_STRATUM_TRACE_DEBUG"] = old_value


def test_submit_eval_reject_logs_same_cid(caplog) -> None:
    import asyncio

    server = _make_server()

    writer = object()
    session = MOD["ClientSession"](
        subscribed=True,
        authorized=True,
        worker_name="workerX",
        extranonce1="00000001",
        difficulty=512.0,
    )
    server._sessions[writer] = session

    job = MOD["ActiveJob"](
        job_id="job-test",
        prevhash="00" * 32,
        prevhash_be="00" * 32,
        coinb1="01000000",
        coinb2="ffffffff",
        merkle_branch=[],
        version="20000202",
        nbits="19073ad2",
        ntime="6992636c",
        clean_jobs=True,
        target_1=MOD["TARGET_1"],
        tx_datas=[],
    )
    server._active_job = job
    server.stats.current_job_id = job.job_id

    req = {
        "id": 1,
        "method": "mining.submit",
        "params": [
            "workerX",
            "job-test",
            "00000000",
            "6992636c",
            "01080198",
            "20000202",
        ],
    }

    cid = server._build_share_cid(
        worker="workerX",
        job_id="job-test",
        extranonce1="00000001",
        extranonce2="00000000",
        ntime="6992636c",
        nonce="01080198",
    )

    with caplog.at_level(logging.INFO):
        asyncio.run(server._handle_request(req, writer, session))

    msgs = [r.message for r in caplog.records]
    assert any(f"share_rx cid={cid}" in m for m in msgs)
    assert any(f"share_eval cid={cid}" in m for m in msgs)
    assert any(f"share_result cid={cid}" in m for m in msgs)
