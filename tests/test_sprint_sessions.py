"""Sprint session/feature logic: DST handling, no-lookahead, HAC sanity."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from research.sessions import add_signal, crypto_session_table, us_session_table
from research.stats import hac_mean_t, ols_hac


def _synthetic_us_day(day: str, base: float) -> pd.DataFrame:
    """One RTH day of 5m bars (09:30–15:55 NY), UTC index, linear drift."""
    ny = pd.date_range(f"{day} 09:30", f"{day} 15:55", freq="5min", tz="America/New_York")
    prices = base + np.linspace(0, 1.0, len(ny))
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices + 0.1,
            "low": prices - 0.1,
            "close": prices + 0.05,
            "volume": 1000.0,
        },
        index=ny.tz_convert("UTC"),
    )


def test_us_session_features_across_dst_transition() -> None:
    # 2024-03-08 (EST, UTC-5) and 2024-03-11 (EDT, UTC-4) straddle the US
    # spring-forward weekend — the 09:30 NY bar is 14:30 UTC before, 13:30 after.
    bars = pd.concat(
        [_synthetic_us_day("2024-03-08", 100.0), _synthetic_us_day("2024-03-11", 102.0)]
    )
    table = us_session_table(bars)
    assert len(table) == 2  # both sessions detected despite the UTC shift
    # r1 covers 09:30→10:00: with 78 bars per day and 1.0 total drift the
    # 09:55 close ≈ open + 5/77 + 0.05.
    row = table.iloc[1]
    assert row["open_0930"] == pytest.approx(102.0)
    assert row["gap"] == pytest.approx(102.0 / table.iloc[0]["session_close"] - 1)
    assert row["r1_from_prev_close"] == pytest.approx(
        row["close_0955"] / table.iloc[0]["session_close"] - 1
    )


def test_crypto_session_features() -> None:
    utc = pd.date_range("2024-01-01 00:00", "2024-01-02 23:55", freq="5min", tz="UTC")
    prices = 100 + np.arange(len(utc)) * 0.01
    bars = pd.DataFrame(
        {"open": prices, "high": prices, "low": prices, "close": prices, "volume": 1.0}, index=utc
    )
    table = crypto_session_table(bars)
    assert len(table) == 2
    # entry is the 00:30 bar open — strictly after open+30
    assert table.iloc[0]["entry_open"] == pytest.approx(100 + 6 * 0.01)


def test_signal_threshold_excludes_current_session() -> None:
    # 61 sessions of |r1|=1bp, then one huge 5% session. If the percentile
    # window leaked the current session, the huge value would raise its own
    # threshold; excluded, the session must be flagged.
    n = 61
    idx = pd.date_range("2024-01-01", periods=n + 1, freq="D")
    r1 = np.full(n + 1, 0.0001)
    r1[-1] = 0.05
    table = pd.DataFrame({"r1_from_open": r1}, index=idx)
    out = add_signal(table)
    assert bool(out["flag"].iloc[-1]) is True
    # and the threshold used on the last day comes from the *previous* window
    assert out["signal_threshold"].iloc[-1] == pytest.approx(0.0001)


def test_hac_equals_ols_t_with_zero_lags_iid() -> None:
    rng = np.random.default_rng(7)
    x = rng.normal(size=500)
    y = 0.5 * x + rng.normal(size=500)
    res = ols_hac(x, y, lags=0)
    # classical OLS t for comparison
    X = np.column_stack([np.ones(500), x])
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    resid = y - X @ beta
    sigma2 = resid @ resid / (500 - 2)
    se = np.sqrt(sigma2 * np.linalg.inv(X.T @ X)[1, 1])
    t_classical = beta[1] / se
    assert res.t_hac == pytest.approx(t_classical, rel=0.02)
    assert res.beta == pytest.approx(0.5, abs=0.1)


def test_hac_mean_t_detects_positive_mean() -> None:
    rng = np.random.default_rng(11)
    y = rng.normal(loc=0.5, scale=1.0, size=400)
    mu, t, n = hac_mean_t(y)
    assert mu == pytest.approx(0.5, abs=0.15)
    assert t > 5
