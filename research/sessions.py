"""Shared session/feature logic for the intraday-regime-momentum sprint.

One implementation used by Phases 3 (R1), 4 (H1) and 5 (H2 reconciliation), so
that the Nautilus-vs-pandas comparison is meaningful.

Conventions (frozen in registration sha256 34d3cfba…):
  * Bars are stamped at their OPEN time (IB `bar.date` and Binance `open_time`
    both are), 5-minute bars, tz-aware UTC index.
  * US session: RTH 09:30–16:00 America/New_York, DST-aware. Session id = NY date.
    - r1 (from open)  = close(09:55 bar) / open(09:30 bar) − 1  [09:30→10:00]
    - r1 (prev close) = close(09:55 bar) / prev session close − 1
    - gap             = open(09:30 bar) / prev session close − 1
    - last-30m return = close(15:55 bar) / open(15:30 bar) − 1  [15:30→16:00]
    - entry           = open of the 10:00 bar (first bar strictly after open+30)
    - exit            = close of the 15:55 bar (session close)
  * Crypto session: 00:00–24:00 UTC. Same construction with 00:00/00:25/00:30/
    23:30/23:55 bars; previous close == previous session's 23:55 close.
  * Timezone discipline: everything stored UTC; NY conversion only inside US
    session logic. No naive timestamps.

No lookahead: every feature at open+30 uses only bars whose OPEN time is
≤ open+25 (i.e. bars fully closed by open+30). The percentile filter uses the
trailing 60 sessions EXCLUDING the current one (shift(1)).
"""

from __future__ import annotations

import pandas as pd

NY = "America/New_York"

# Frozen parameters (registration §2).
X_MINUTES = 30
PCTL = 0.70
LOOKBACK_SESSIONS = 60


def us_session_table(bars_5m_utc: pd.DataFrame) -> pd.DataFrame:
    """Per-session feature table for a US RTH instrument (SPY/MES research series).

    Input: 5m bars, UTC tz-aware index (bar OPEN time), columns open/high/low/
    close/volume. RTH-only bars expected for SPY; for a 23h future the RTH
    window is selected here.
    """
    df = bars_5m_utc.copy()
    ny = df.index.tz_convert(NY)
    df["session"] = ny.date
    df["ny_time"] = ny.time

    t = pd.to_datetime
    t0930 = t("09:30").time()
    t0955 = t("09:55").time()
    t1000 = t("10:00").time()
    t1530 = t("15:30").time()
    t1555 = t("15:55").time()

    def pick(time_, col):
        s = df[df["ny_time"] == time_].set_index("session")[col]
        return s[~s.index.duplicated(keep="first")]

    out = pd.DataFrame(
        {
            "open_0930": pick(t0930, "open"),
            "close_0955": pick(t0955, "close"),
            "entry_open": pick(t1000, "open"),
            "open_1530": pick(t1530, "open"),
            "close_1555": pick(t1555, "close"),
        }
    )
    out = out.dropna(subset=["open_0930", "close_0955", "close_1555"])
    out["prev_close"] = out["close_1555"].shift(1)
    out["session_close"] = out["close_1555"]

    out["r1_from_open"] = out["close_0955"] / out["open_0930"] - 1
    out["r1_from_prev_close"] = out["close_0955"] / out["prev_close"] - 1
    out["gap"] = out["open_0930"] / out["prev_close"] - 1
    out["last30_ret"] = out["close_1555"] / out["open_1530"] - 1
    out["trade_ret_gross"] = out["close_1555"] / out["entry_open"] - 1
    out.index = pd.to_datetime(out.index)
    return out


def crypto_session_table(bars_5m_utc: pd.DataFrame) -> pd.DataFrame:
    """Per-session feature table for a 24/7 UTC instrument (Binance spot)."""
    df = bars_5m_utc.copy()
    df["session"] = df.index.date
    df["utc_time"] = df.index.time

    t = pd.to_datetime
    t0000 = t("00:00").time()
    t0025 = t("00:25").time()
    t0030 = t("00:30").time()
    t2330 = t("23:30").time()
    t2355 = t("23:55").time()

    def pick(time_, col):
        s = df[df["utc_time"] == time_].set_index("session")[col]
        return s[~s.index.duplicated(keep="first")]

    out = pd.DataFrame(
        {
            "open_0000": pick(t0000, "open"),
            "close_0025": pick(t0025, "close"),
            "entry_open": pick(t0030, "open"),
            "open_2330": pick(t2330, "open"),
            "close_2355": pick(t2355, "close"),
        }
    )
    out = out.dropna(subset=["open_0000", "close_0025", "close_2355"])
    out["prev_close"] = out["close_2355"].shift(1)
    out["session_close"] = out["close_2355"]

    # 24/7: previous close == session open (up to the 00:00 bar's open); a single
    # r1 variant exists (registration §1 R1b).
    out["r1_from_open"] = out["close_0025"] / out["open_0000"] - 1
    out["r1_from_prev_close"] = out["close_0025"] / out["prev_close"] - 1  # ≈ identical
    out["last30_ret"] = out["close_2355"] / out["open_2330"] - 1
    out["trade_ret_gross"] = out["close_2355"] / out["entry_open"] - 1
    out.index = pd.to_datetime(out.index)
    return out


def add_signal(table: pd.DataFrame, r1_col: str = "r1_from_open") -> pd.DataFrame:
    """Frozen classifier: flag iff |r1| ≥ trailing-60-session 70th pct (excl.
    current session); direction = sign(r1)."""
    out = table.copy()
    abs_r1 = out[r1_col].abs()
    thresh = abs_r1.rolling(LOOKBACK_SESSIONS, min_periods=LOOKBACK_SESSIONS).quantile(PCTL)
    out["signal_threshold"] = thresh.shift(1)  # excludes current session — no lookahead
    out["flag"] = abs_r1 >= out["signal_threshold"]
    out.loc[out["signal_threshold"].isna(), "flag"] = False
    out["direction"] = (out[r1_col] > 0).astype(int) * 2 - 1
    out.loc[out[r1_col] == 0, "direction"] = 0
    return out


def momentum_returns(table: pd.DataFrame, *, rt_cost: float, conditional: bool) -> pd.Series:
    """Per-session strategy net return on allocated notional.

    rt_cost: round-trip cost as a fraction of notional (both sides).
    conditional=True → trade only flagged sessions; else every session with a
    nonzero direction. Abstentions contribute 0.0 (total-capital convention).
    """
    active = table["flag"] if conditional else table["direction"] != 0
    gross = table["direction"] * table["trade_ret_gross"]
    net = gross - rt_cost
    return net.where(active & table["entry_open"].notna(), 0.0)
