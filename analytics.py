import hashlib
import logging

from config import EXPLORER_SIGNING_SECRET
from db import get_conn

logger = logging.getLogger(__name__)


def _hash_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    return hashlib.sha256((ip + EXPLORER_SIGNING_SECRET).encode("utf-8")).hexdigest()


def log_visit(
    chain_id: int | None,
    chain_slug: str,
    tx_hash: str,
    token_valid: bool,
    referrer: str | None,
    user_agent: str | None,
    ip: str | None,
):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO visits
                        (chain_id, chain_slug, tx_hash, token_valid, referrer, user_agent, ip_hash)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        chain_id,
                        chain_slug,
                        tx_hash,
                        1 if token_valid else 0,
                        (referrer or "")[:255] or None,
                        (user_agent or "")[:255] or None,
                        _hash_ip(ip),
                    ),
                )
    except Exception as e:
        # A logging failure must never break the redirect page.
        logger.error("log_visit failed: %s", e)
