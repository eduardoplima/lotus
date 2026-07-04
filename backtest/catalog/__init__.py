"""nautilus_trader ParquetDataCatalog access (§2).

The catalog is the backtest engine's data source. Postgres stays the system of
record for ingested data; this layer materializes the subset a backtest needs
(instrument definitions + bars) into local Parquet. nautilus reads only the
catalog, never a broker/vendor API at run time (§2).

Always write instrument definitions before their market data.
"""

from __future__ import annotations

from pathlib import Path

from core.config import settings
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.persistence.catalog import ParquetDataCatalog


def get_catalog(path: str | None = None) -> ParquetDataCatalog:
    """Open (creating if needed) the ParquetDataCatalog at `path` or config default."""
    root = Path(path or settings.catalog_path).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return ParquetDataCatalog(str(root))


def write_instruments(catalog: ParquetDataCatalog, instruments: list[Instrument]) -> None:
    if not instruments:
        raise ValueError("Refusing to write an empty instrument list — record the gap (§6.3).")
    catalog.write_data(instruments)


def write_bars(catalog: ParquetDataCatalog, bars: list[Bar]) -> None:
    if not bars:
        raise ValueError("Refusing to write zero bars — this is a hole to record, not fill (§6.3).")
    catalog.write_data(bars)


def load_bars(catalog: ParquetDataCatalog, bar_type: BarType) -> list[Bar]:
    """Read back bars of a given type from the catalog (point-in-time, ordered)."""
    return catalog.bars(bar_types=[str(bar_type)])
