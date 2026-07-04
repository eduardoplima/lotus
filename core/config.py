"""Application settings, loaded from environment / .env.

Every external knob lives here so nothing load-bearing is hard-coded silently.
In particular the dealer-sign convention (§6.1) is an explicit parameter, never
an implicit assumption buried in the compute layer.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DealerSignConvention(StrEnum):
    """How dealer positioning is *assumed* when signing gamma exposure.

    This is a modeled assumption, not an observable (§6.1). Open interest does
    not reveal which side dealers hold; every GEX/wall number rests on this.
    """

    LONG_CALLS_SHORT_PUTS = "long_calls_short_puts"
    SHORT_CALLS_LONG_PUTS = "short_calls_long_puts"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # PostgreSQL (async SQLAlchemy URL).
    database_url: str = Field(
        default="postgresql+asyncpg://lotus:lotus@127.0.0.1:5432/lotus",
        alias="DATABASE_URL",
    )

    # Interactive Brokers Gateway/TWS.
    # Ports: Gateway live 4001 / paper 4002; TWS live 7496 / paper 7497.
    # This install talks to a *live-account* Gateway on 4001 but is used for
    # READ-ONLY historical data only — no order-routing/exec is wired (§15).
    # Anything that could place an order must run against a paper endpoint.
    ib_host: str = Field(default="127.0.0.1", alias="IB_HOST")
    ib_port: int = Field(default=4001, alias="IB_PORT")
    ib_client_id: int = Field(default=1, alias="IB_CLIENT_ID")

    # nautilus_trader ParquetDataCatalog root — the backtest data source (§2).
    # Materialized from IBKR/Postgres; never committed (gitignored).
    catalog_path: str = Field(default="./data/catalog", alias="CATALOG_PATH")

    # Crypto market data — public REST, no auth required for market data.
    # Binance returns HTTP 451 from geo-restricted IPs (US etc.); run ingestion
    # from a non-restricted egress (this host is in Brazil — fine).
    binance_base_url: str = Field(default="https://api.binance.com", alias="BINANCE_BASE_URL")
    hyperliquid_base_url: str = Field(
        default="https://api.hyperliquid.xyz", alias="HYPERLIQUID_BASE_URL"
    )

    # Load-bearing assumption (§6.1) — conservative explicit default.
    dealer_sign_convention: DealerSignConvention = Field(
        default=DealerSignConvention.LONG_CALLS_SHORT_PUTS,
        alias="DEALER_SIGN_CONVENTION",
    )


settings = Settings()
