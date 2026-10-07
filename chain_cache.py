"""
Read-only cache of coin -> chain display info from the shared `currencies` and
`chains` tables (the same rows coindrop-api and the bot already populate).

URLs are keyed by the withdrawn coin's symbol (`/ltc/<tx>`, `/solusdc/<tx>`):
`currencies.symbol` is UNIQUE, and the bot/backend always know the symbol of a
withdrawal, so no slug map has to be kept in sync across repos.

Loaded at startup; an unknown symbol triggers at most one reload per
RELOAD_COOLDOWN seconds, so a coin listed after startup works without a restart.
"""

import logging
import time

from db import get_conn

logger = logging.getLogger(__name__)

RELOAD_COOLDOWN = 60

# lowercase symbol -> {"symbol", "decimals", "chain_id", "chain_name", "explorer_url", "chain_type", "rpc_url"}
COINS: dict[str, dict] = {}
_last_load = 0.0


def load():
    global COINS, _last_load
    _last_load = time.monotonic()
    try:
        with get_conn() as conn:
            with conn.cursor(dictionary=True) as cur:
                cur.execute(
                    """
                    SELECT c.symbol, c.decimals, c.chain_id,
                           ch.name AS chain_name, ch.explorer_url, ch.chain_type, ch.rpc_url
                    FROM currencies c
                    JOIN chains ch ON ch.id = c.chain_id
                    """
                )
                rows = cur.fetchall()
    except Exception as e:
        logger.error("chain_cache.load() failed, keeping previous/empty cache: %s", e)
        return

    COINS = {
        row["symbol"].lower(): {
            "symbol": row["symbol"],
            "decimals": row["decimals"],
            "chain_id": row["chain_id"],
            "chain_name": row["chain_name"],
            "explorer_url": row["explorer_url"] or "",
            "chain_type": row["chain_type"],
            "rpc_url": row["rpc_url"] or "",
        }
        for row in rows
    }
    logger.info("chain_cache: loaded %d coins", len(COINS))


def get(slug: str) -> dict | None:
    coin = COINS.get(slug.lower())
    if coin is None and time.monotonic() - _last_load > RELOAD_COOLDOWN:
        load()
        coin = COINS.get(slug.lower())
    return coin
