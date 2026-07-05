"""Bulk-acquire Binance SPOT 5m klines from data.binance.vision (Phase 2).

Per the approved registration (sha256 34d3cfba…): monthly archives for the frozen
universe, earliest month → 2026-06 (holdout end). Originals + checksums are kept
immutable in data/raw/binance/{SYMBOL}/; curated UTC Parquet goes to
data/curated/binance/{SYMBOL}_5m.parquet.

Integrity:
  * every archive's .CHECKSUM (sha256) is verified — mismatch is a hard error;
  * timestamps are normalized: 2025+ archives use MICROSECONDS, earlier ones
    MILLISECONDS (verified first-hand in preflight); threshold 1e14 discriminates;
  * duplicate timestamps are an error (recorded, not silently dropped);
  * resumable: verified archives already on disk are not re-downloaded.

Kline CSV columns (data.binance.vision spot klines):
  0 open_time, 1 open, 2 high, 3 low, 4 close, 5 volume(base), 6 close_time,
  7 quote_volume, 8 n_trades, 9 taker_buy_base, 10 taker_buy_quote, 11 ignore
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import io
import logging
import sys
import zipfile
from pathlib import Path

import httpx
import pandas as pd

logger = logging.getLogger("lotus.research.acquire_binance")

BASE = "https://data.binance.vision/data/spot/monthly/klines"
RAW = Path("data/raw/binance")
CURATED = Path("data/curated/binance")
END_MONTH = (2026, 6)  # inclusive — holdout ends 2026-06-30 per registration

UNIVERSE_START = {
    "BTCUSDT": (2017, 8),
    "ETHUSDT": (2017, 8),
    "BNBUSDT": (2017, 11),
    "ADAUSDT": (2018, 4),
    "SOLUSDT": (2020, 8),
}

CONCURRENCY = 6


def months(start: tuple[int, int], end: tuple[int, int]):
    y, m = start
    while (y, m) <= end:
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


async def fetch_archive(client: httpx.AsyncClient, symbol: str, y: int, m: int) -> Path | None:
    """Download + checksum-verify one monthly archive. Returns local path or None
    if the archive does not exist (pre-listing months)."""
    name = f"{symbol}-5m-{y:04d}-{m:02d}.zip"
    dest = RAW / symbol / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.with_suffix(".zip.OK").exists():
        return dest  # already verified — resumable

    url = f"{BASE}/{symbol}/5m/{name}"
    r = await client.get(url)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    blob = r.content

    rc = await client.get(url + ".CHECKSUM")
    rc.raise_for_status()
    expected = rc.text.split()[0].strip()
    actual = hashlib.sha256(blob).hexdigest()
    if actual != expected:
        raise RuntimeError(f"CHECKSUM MISMATCH for {name}: expected {expected}, got {actual}")

    dest.write_bytes(blob)
    dest.with_suffix(".zip.OK").write_text(expected)
    return dest


def parse_archive(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as zf:
        with zf.open(zf.namelist()[0]) as fh:
            df = pd.read_csv(
                io.TextIOWrapper(fh),
                header=None,
                usecols=[0, 1, 2, 3, 4, 5, 7, 8],
                names=[
                    "open_time",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "quote_volume",
                    "n_trades",
                ],
            )
    # µs (2025+) vs ms (earlier): µs epoch values exceed 1e14 by many orders.
    unit_divisor = 1_000_000 if df["open_time"].iloc[0] > 1e14 else 1_000
    df["ts"] = pd.to_datetime(df.pop("open_time") // unit_divisor, unit="s", utc=True)
    return df.set_index("ts").sort_index()


DAILY_BASE = "https://data.binance.vision/data/spot/daily/klines"


async def fetch_daily_archive(client: httpx.AsyncClient, symbol: str, day: dt.date) -> Path | None:
    """Fallback for months whose monthly archive is not yet published."""
    name = f"{symbol}-5m-{day.isoformat()}.zip"
    dest = RAW / symbol / "daily" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.with_suffix(".zip.OK").exists():
        return dest
    url = f"{DAILY_BASE}/{symbol}/5m/{name}"
    r = await client.get(url)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    blob = r.content
    rc = await client.get(url + ".CHECKSUM")
    rc.raise_for_status()
    expected = rc.text.split()[0].strip()
    actual = hashlib.sha256(blob).hexdigest()
    if actual != expected:
        raise RuntimeError(f"CHECKSUM MISMATCH for {name}")
    dest.write_bytes(blob)
    dest.with_suffix(".zip.OK").write_text(expected)
    return dest


async def acquire_symbol(client: httpx.AsyncClient, symbol: str) -> dict:
    sem = asyncio.Semaphore(CONCURRENCY)

    async def _one(y: int, m: int):
        async with sem:
            return await fetch_archive(client, symbol, y, m)

    month_list = list(months(UNIVERSE_START[symbol], END_MONTH))
    paths = await asyncio.gather(*(_one(y, m) for y, m in month_list))
    # Months with no monthly archive yet (e.g. the most recent one): fill with
    # daily archives so the registered window is honored.
    missing = [ym for ym, p in zip(month_list, paths, strict=True) if p is None]
    for y, m in missing:
        ndays = (dt.date(y + (m == 12), (m % 12) + 1, 1) - dt.date(y, m, 1)).days
        daily = await asyncio.gather(
            *(fetch_daily_archive(client, symbol, dt.date(y, m, d + 1)) for d in range(ndays))
        )
        got = [p for p in daily if p is not None]
        logger.info(
            "%s %04d-%02d: monthly missing, %d/%d daily archives", symbol, y, m, len(got), ndays
        )
        paths.extend(got)
    paths = [p for p in paths if p is not None]
    if not paths:
        raise RuntimeError(
            f"no archives retrieved for {symbol} — recording the gap, not filling it"
        )

    frames = [parse_archive(p) for p in sorted(paths)]
    df = pd.concat(frames)
    dupes = int(df.index.duplicated().sum())
    if dupes:
        raise RuntimeError(f"{symbol}: {dupes} duplicate timestamps across archives — investigate")
    df = df.sort_index()

    CURATED.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240 — one-shot script
    out = CURATED / f"{symbol}_5m.parquet"
    df.to_parquet(out)
    return {
        "symbol": symbol,
        "archives": len(paths),
        "rows": len(df),
        "first": str(df.index[0]),
        "last": str(df.index[-1]),
        "zero_volume_bars": int((df["volume"] == 0).sum()),
    }


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    async with httpx.AsyncClient(timeout=120.0) as client:
        for symbol in UNIVERSE_START:
            info = await acquire_symbol(client, symbol)
            print(f"DONE {info}", flush=True)
    stamp = dt.datetime.now(tz=dt.UTC).isoformat()
    (CURATED / "ACQUIRED_AT.txt").write_text(f"{stamp}\n")  # noqa: ASYNC240 — one-shot script
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
