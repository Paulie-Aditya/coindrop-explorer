import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

import config
from db import get_conn

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")
security = HTTPBasic()


def require_admin(credentials: HTTPBasicCredentials = Depends(security)):
    user_ok = secrets.compare_digest(credentials.username, config.ADMIN_USER)
    pass_ok = secrets.compare_digest(credentials.password, config.ADMIN_PASS)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


@router.get("/stats", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
async def stats(request: Request):
    with get_conn() as conn:
        with conn.cursor(dictionary=True) as cur:
            cur.execute(
                """
                SELECT DATE(created_at) AS day, chain_slug,
                       COUNT(*) AS visits,
                       SUM(token_valid) AS verified
                FROM visits
                WHERE created_at >= NOW() - INTERVAL 14 DAY
                GROUP BY DATE(created_at), chain_slug
                ORDER BY day DESC, visits DESC
                """
            )
            by_chain_day = cur.fetchall()

            cur.execute(
                """
                SELECT chain_slug, tx_hash, COUNT(*) AS visits
                FROM visits
                WHERE created_at >= NOW() - INTERVAL 14 DAY
                GROUP BY chain_slug, tx_hash
                ORDER BY visits DESC
                LIMIT 20
                """
            )
            top_tx = cur.fetchall()

            cur.execute(
                """
                SELECT
                    SUM(token_valid = 1) AS verified_count,
                    SUM(token_valid = 0) AS unverified_count
                FROM visits
                WHERE created_at >= NOW() - INTERVAL 14 DAY
                """
            )
            totals = cur.fetchone() or {}

    return templates.TemplateResponse(
        "admin_stats.html",
        {
            "request": request,
            "by_chain_day": by_chain_day,
            "top_tx": top_tx,
            "verified_count": totals.get("verified_count") or 0,
            "unverified_count": totals.get("unverified_count") or 0,
        },
    )
