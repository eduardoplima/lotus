"""Reproducibility helpers (§6.3)."""

from __future__ import annotations

from core.provenance import config_hash, git_sha


def test_config_hash_is_deterministic_and_order_independent() -> None:
    a = config_hash("sma", {"fast": 10, "slow": 30}, {"symbol": "MES"})
    b = config_hash("sma", {"slow": 30, "fast": 10}, {"symbol": "MES"})  # key order flipped
    c = config_hash("sma", {"fast": 11, "slow": 30}, {"symbol": "MES"})  # a param changed
    assert a == b  # sorted keys → stable
    assert a != c  # different config → different hash
    assert len(a) == 64  # sha-256 hex


def test_git_sha_returns_a_string() -> None:
    sha = git_sha()
    assert isinstance(sha, str) and sha  # 'unknown' outside a repo, else a real SHA
