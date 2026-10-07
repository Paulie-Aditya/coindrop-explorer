"""
MySQL connection pool shared across the app (same DB as coindrop-api / the bot).

Usage:
    from db import get_conn

    with get_conn() as conn:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("SELECT ...")
            rows = cur.fetchall()

The `with get_conn()` context manager returns the connection to
the pool automatically on exit -- no manual close needed.
"""

import mysql.connector.pooling
from config import DB_HOST, DB_USER, DB_PASS, DB_NAME, DB_POOL_SIZE

_pool: mysql.connector.pooling.MySQLConnectionPool | None = None


def _init():
    global _pool
    _pool = mysql.connector.pooling.MySQLConnectionPool(
        pool_name          = "coindrop_explorer",
        pool_size          = DB_POOL_SIZE,
        pool_reset_session = True,
        host               = DB_HOST,
        user               = DB_USER,
        password           = DB_PASS,
        database           = DB_NAME,
        autocommit         = True,
        charset            = "utf8mb4",
    )


def get_conn() -> mysql.connector.pooling.PooledMySQLConnection:
    global _pool
    if _pool is None:
        _init()
    return _pool.get_connection()
