"""FastAPI application for Lotus.

Read-only to the client (§10). Bind to 127.0.0.1 via the run command — this app
never binds 0.0.0.0 itself, and the recommended invocation is:

    uvicorn api.main:app --host 127.0.0.1 --port 8000

No CORS is opened: the front-end reaches the API through the Vite dev proxy in
development, keeping everything localhost-only (§10/§15).
"""

from __future__ import annotations

from core.config import settings
from fastapi import FastAPI

from api.routers import bars, health, instruments, research

app = FastAPI(
    title="Lotus",
    summary="Quant fund platform: market-data ingestion + falsification-first backtesting.",
    version="0.1.0",
)

API_PREFIX = "/api"
app.include_router(health.router, prefix=API_PREFIX)
app.include_router(instruments.router, prefix=API_PREFIX)
app.include_router(bars.router, prefix=API_PREFIX)
app.include_router(research.router, prefix=API_PREFIX)


@app.get(f"{API_PREFIX}/meta")
async def meta() -> dict[str, object]:
    """Surface the load-bearing dealer-sign assumption to any client (§6.2)."""
    return {
        "dealer_sign_convention": settings.dealer_sign_convention.value,
        "gex_is_assumption_dependent": True,
    }
