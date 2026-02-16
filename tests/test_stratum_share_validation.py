from __future__ import annotations

import runpy
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STRATUM_MAIN = ROOT / "stratum" / "main.py"
MOD = runpy.run_path(str(STRATUM_MAIN))


def test_extranonce2_is_appended_as_raw_hex_bytes() -> None:
    coinb1 = "aa"
    ex1 = "bb"
    ex2 = "07000000"
    coinb2 = "cc"

    coinbase = MOD["build_coinbase"](coinb1, ex1, ex2, coinb2)
    assert coinbase.hex() == "aabb07000000cc"

    # Guardrail against wrong int-pack behavior (byte-swapped extranonce2)
    wrong = bytes.fromhex(coinb1 + ex1) + struct.pack("<I", int(ex2, 16)) + bytes.fromhex(coinb2)
    assert coinbase != wrong


def test_captured_notify_submit_reconstruction_is_stable() -> None:
    # Captured sample (DGB)
    coinb1 = "01000000010000000000000000000000000000000000000000000000000000000000000000ffffffff150487b95e0107484d4d2d444742"
    coinb2 = "ffffffff019a85985006000000015100000000"
    extranonce1 = "00000002"
    extranonce2 = "02000000"
    notify_prevhash = "873a0d1d897d6b74b3a2eb7c8bd89e94092e8b1dc3d40b9b2dadd6d3afe0b124"
    ntime = "6992636c"
    nbits = "19073ad2"
    nonce = "01080198"

    job_version = 0x20000202
    submitted_version = 0x02B3A000
    final_version = (job_version | submitted_version) & 0xFFFFFFFF

    coinbase = MOD["build_coinbase"](coinb1, extranonce1, extranonce2, coinb2)
    merkle_root = MOD["build_merkle_root"](coinbase, [])
    header = MOD["build_header"](
        final_version,
        notify_prevhash,
        merkle_root,
        ntime,
        nbits,
        nonce,
    )
    hash_bytes, hash_int_big = MOD["hash_header"](header)

    # Stable reproducible harness values.
    assert len(header) == 80
    assert len(merkle_root) == 32
    assert hash_bytes.hex() == "0fff4a8679aa141ea21ff99511a7371304de270901e909fc6b446bba064e8b08"
    assert hash_int_big == 7235753084942753296180405043361390206233656511352140370034949997190070569736

    share_target = MOD["_difficulty_to_target"](512.0, MOD["TARGET_1"])
    assert MOD["validate_share"](hash_int_big, share_target) is False


def test_meets_share_little_endian_compare_true_false() -> None:
    assigned_diff = 512.0
    share_target_int = MOD["target_from_difficulty"](assigned_diff)

    # Known little-endian integer smaller than target should pass.
    hash_int_little_ok = share_target_int - 12345
    hash_bytes_ok = hash_int_little_ok.to_bytes(32, "little")
    assert MOD["meets_share"](hash_bytes_ok, share_target_int) is True

    # Known little-endian integer larger than target should fail.
    hash_int_little_bad = share_target_int + 12345
    hash_bytes_bad = hash_int_little_bad.to_bytes(32, "little")
    assert MOD["meets_share"](hash_bytes_bad, share_target_int) is False
