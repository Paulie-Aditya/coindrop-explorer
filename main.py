"""
CoinDrop Explorer
=================

Lightweight interstitial between CoinDrop's "View Transaction" links and the
real chain explorer (Solscan/Etherscan/etc). Renders tx display data the bot
signs into the URL -- no chain RPC or third-party explorer API calls are made.

Run locally:
    uvicorn main:app --reload --port 8002

Production:
    uvicorn main:app --host 127.0.0.1 --port 8002 --workers 2
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import chain_cache
import chain_status
from routers.admin import router as admin_router
from routers.tx import router as tx_router

app = FastAPI(
    title="CoinDrop Explorer",
    docs_url=None,
    redoc_url=None,
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(admin_router)   # GET /admin/stats
app.include_router(tx_router)      # GET /{coin}/{tx_hash}


@app.on_event("startup")
async def on_startup():
    chain_cache.load()


@app.on_event("shutdown")
async def on_shutdown():
    await chain_status.close()


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok", "coins_loaded": len(chain_cache.COINS)}

