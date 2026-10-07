import re
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import chain_cache
import chain_status
import config
from analytics import log_visit
from coins import icon_for
from signing import verify_token

router = APIRouter(tags=["tx"])
templates = Jinja2Templates(directory="templates")

# Hashes/signatures across every supported chain are base58, hex (optionally 0x-),
# or base64url -- anything else is either a typo or someone probing the
# destination URL we build from it.
TX_HASH_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")

# Chain types whose withdrawal the bot only reports (and so only links) after
# it has confirmed on-chain success -- see CoinDrop/helper.py process_withdrawal:
# EVM waits for a receipt with status 1, SOL/SPL for confirm_transaction, XRP
# for submit_and_wait (validated, tesSUCCESS), XLM's Horizon submit returns
# after ledger close. A signed link on these chains is therefore already
# confirmed even when no live lookup can answer.
CONFIRMED_BEFORE_LINK = {"EVM", "SOL", "XRP", "XLM"}


def format_units(raw, decimals: int) -> str | None:
    """Base units (as the bot/backend store them) -> human amount, e.g. "1,250.5"."""
    try:
        value = Decimal(str(raw)).scaleb(-int(decimals))
    except (InvalidOperation, TypeError, ValueError):
        return None
    text = f"{value:,.{int(decimals)}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


@router.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("https://coindrop.cc", status_code=302)


@router.get("/api/status/{coin}/{tx_hash}")
async def tx_status(coin: str, tx_hash: str):
    """Live status from the chain's public explorer; polled by the tx page."""
    info = chain_cache.get(coin) if TX_HASH_RE.match(tx_hash) else None
    if info is None:
        return JSONResponse({"state": "unavailable"}, status_code=404)
    st = await chain_status.get_status(info["chain_id"], tx_hash, info.get("rpc_url"))
    return JSONResponse(st.to_dict(), headers={"Cache-Control": "no-store"})


@router.get("/{coin}/{tx_hash}", response_class=HTMLResponse)
async def view_tx(request: Request, coin: str, tx_hash: str, d: str | None = None):
    referrer = request.headers.get("referer")
    user_agent = request.headers.get("user-agent")
    client_ip = request.client.host if request.client else None

    info = chain_cache.get(coin) if TX_HASH_RE.match(tx_hash) else None
    if info is None:
        log_visit(None, coin[:20], tx_hash[:128], False, referrer, user_agent, client_ip)
        return templates.TemplateResponse(
            request,
            "unsupported.html",
            {"coin_slug": coin, "tx_hash": tx_hash},
            status_code=404,
        )

    chain_id = info["chain_id"]
    payload = verify_token(d, config.EXPLORER_SIGNING_SECRET) if d else None

    # Bind the token to this exact URL -- a valid token for a different tx/coin
    # must not be trusted here, even though its signature checks out.
    verified = bool(
        payload
        and payload.get("chain_id") == chain_id
        and payload.get("tx_hash") == tx_hash
        and str(payload.get("currency", "")).lower() == coin.lower()
    )

    log_visit(chain_id, coin.lower(), tx_hash, verified, referrer, user_agent, client_ip)

    context = {
        "coin_slug": coin.lower(),
        "symbol": info["symbol"],
        "icon": icon_for(info["symbol"]),
        "chain_name": info["chain_name"],
        "tx_hash": tx_hash,
        "destination_url": f"{info['explorer_url']}{tx_hash}" if info["explorer_url"] else None,
        "verified": verified,
        "confirmed_at_send": verified and info["chain_type"] in CONFIRMED_BEFORE_LINK,
    }
    if verified:
        context.update(
            {
                "amount": format_units(payload.get("amount"), info["decimals"]),
                "fee": format_units(payload.get("fee"), info["decimals"]),
                "to_address": payload.get("to_address"),
            }
        )

    return templates.TemplateResponse(request, "interstitial.html", context)
