"""
Live transaction status, read from each chain's public block-explorer API.

Explorer APIs are tried first. Where a chain has none (Sui, Banano, Cascoin,
LitecoinII, ETH II, Cronos, and -- without keys -- BSC, Polygon, Base, Solana),
or the explorer is throttled/down/behind, the chain's own node is asked
instead: the same RPC/ElectrumX endpoints the bot sends withdrawals through.
Every provider was probed against real transactions on 2026-10-07; the notes
on each say what was verified.

Results are cached per process so a page that polls, or a link shared in a busy
channel, doesn't hammer anyone's explorer. Keyed explorers read their key from
the env and are skipped when it's unset.
"""

import asyncio
import json
import logging
import os
import random
import ssl
import time
from dataclasses import asdict, dataclass

import httpx

logger = logging.getLogger(__name__)

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
TRONSCAN_API_KEY = os.getenv("TRONSCAN_API_KEY", "")
SOLSCAN_API_KEY = os.getenv("SOLSCAN_API_KEY", "")
THREEXPL_API_KEY = os.getenv("THREEXPL_API_KEY", "")

TIMEOUT = httpx.Timeout(8.0)
HEADERS = {"User-Agent": "CoinDropExplorer/1.0 (+https://explorer.coindrop.cc)", "Accept": "application/json"}

# state: confirmed | pending | failed | not_found | unavailable
#   not_found  -- explorer hasn't seen it (yet); normal for a few seconds after broadcast
#   unavailable -- no provider for this chain, or the explorer errored/timed out


@dataclass
class TxStatus:
    state: str
    confirmations: int | None = None
    source: str | None = None  # explorer host the answer came from

    def to_dict(self) -> dict:
        return asdict(self)


UNAVAILABLE = TxStatus("unavailable")


class _NotFound(Exception):
    pass


async def _get_json(client: httpx.AsyncClient, url: str, **kw):
    r = await client.get(url, **kw)
    if r.status_code == 404:
        raise _NotFound
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------- providers --

async def _esplora(client, base: str, tx: str) -> TxStatus:
    """mempool.space/Blockstream API (btcscan.org, litecoinspace.org, bc3mempool).
    /tx/:id/status -> {"confirmed": bool, "block_height": n}. It answers
    {"confirmed": false} for *any* txid, so an unconfirmed answer is checked
    against /tx/:id, which 404s when the tx isn't in the mempool either."""
    st = await _get_json(client, f"{base}/tx/{tx}/status")
    if not st.get("confirmed"):
        r = await client.get(f"{base}/tx/{tx}")
        if r.status_code == 404:
            raise _NotFound
        r.raise_for_status()
        return TxStatus("pending", 0)
    tip = int((await client.get(f"{base}/blocks/tip/height")).text)
    return TxStatus("confirmed", max(1, tip - st["block_height"] + 1))


async def _iquidus(client, base: str, tx: str) -> TxStatus:
    """eIquidus explorers (SHIC, SMT, RIN, DC2). getrawtransaction&decrypt=1 is
    bitcoind's verbose tx -- "confirmations" once mined, absent in mempool.
    An unknown txid returns a plain-text error, not JSON."""
    r = await client.get(f"{base}/api/getrawtransaction", params={"txid": tx, "decrypt": 1})
    r.raise_for_status()
    try:
        data = r.json()
    except ValueError:
        raise _NotFound
    if not isinstance(data, dict) or data.get("txid") != tx:
        raise _NotFound
    confs = int(data.get("confirmations") or 0)
    return TxStatus("confirmed" if confs > 0 else "pending", confs)


async def _kerrigan(client, base: str, tx: str) -> TxStatus:
    """explorer.kerrigan.network's own API: /api/tx/:id is verbose getrawtransaction;
    unknown txids come back as HTTP 500 "No such mempool or blockchain transaction"."""
    r = await client.get(f"{base}/api/tx/{tx}")
    if r.status_code == 500 and "No such" in r.text:
        raise _NotFound
    r.raise_for_status()
    confs = int(r.json().get("confirmations") or 0)
    return TxStatus("confirmed" if confs > 0 else "pending", confs)


async def _dork(client, base: str, tx: str) -> TxStatus:
    """dorkexplorer.com /api/v1/txid/:id (the endpoint the bot's dork_helper uses).
    Unknown txids return a placeholder with timestamp "N/A". No confirmation
    count is exposed. Only the not-found shape has been seen live; a mined tx
    is assumed to carry a real timestamp."""
    data = await _get_json(client, f"{base}/api/v1/txid/{tx}")
    row = data[0] if isinstance(data, list) and data else {}
    if not row or row.get("timestamp") in (None, "", "N/A"):
        raise _NotFound
    return TxStatus("confirmed")


async def _etherscan_like(client, base: str, params: dict, tx: str, trust_tip: bool) -> TxStatus:
    """Etherscan-compatible proxy module (Etherscan V2, Routescan).
    Receipt null -> not yet mined (or unknown); status 0x0 -> reverted.
    Routescan's eth_blockNumber lags its own receipts, so with trust_tip=False
    the count is skipped and a mined tx just reads "confirmed"."""
    receipt = await _get_json(
        client, base, params={**params, "module": "proxy", "action": "eth_getTransactionReceipt", "txhash": tx}
    )
    if isinstance(receipt.get("result"), str):  # {"status":"0","result":"Missing/Invalid API Key"} etc.
        raise RuntimeError(receipt["result"])
    rec = receipt.get("result")
    if not rec:
        raise _NotFound
    if rec.get("status") == "0x0":
        return TxStatus("failed")
    confs = None
    if trust_tip:
        tip = await _get_json(client, base, params={**params, "module": "proxy", "action": "eth_blockNumber"})
        confs = max(1, int(tip["result"], 16) - int(rec["blockNumber"], 16) + 1)
    return TxStatus("confirmed", confs)


async def _evm(client, chain_id: int, tx: str) -> TxStatus:
    # Etherscan V2: one key for every chain, but the free tier only covers
    # Ethereum + Polygon (OP/BSC/Base/Avalanche need a paid plan).
    if ETHERSCAN_API_KEY:
        try:
            st = await _etherscan_like(
                client, "https://api.etherscan.io/v2/api",
                {"chainid": chain_id, "apikey": ETHERSCAN_API_KEY}, tx, trust_tip=True,
            )
            st.source = "etherscan.io"
            return st
        except _NotFound:
            raise
        except Exception as e:
            logger.info("etherscan chain %s unavailable (%s); trying routescan", chain_id, e)
    # Routescan: keyless, but only Ethereum + Avalanche respond on its free tier.
    if chain_id in (1, 43114):
        st = await _etherscan_like(
            client, f"https://api.routescan.io/v2/network/mainnet/evm/{chain_id}/etherscan/api",
            {}, tx, trust_tip=False,
        )
        st.source = "routescan.io"
        return st
    return await _threexpl(client, chain_id, tx)


async def _xrpscan(client, base: str, tx: str) -> TxStatus:
    """api.xrpscan.com/api/v1/tx/:hash -- only validated ledgers are indexed, so
    presence means final. tec* results are applied-but-failed."""
    data = await _get_json(client, f"{base}/api/v1/tx/{tx}")
    result = (data.get("meta") or {}).get("TransactionResult", "")
    return TxStatus("confirmed" if result == "tesSUCCESS" else "failed")


async def _stellar_expert(client, base: str, tx: str) -> TxStatus:
    """api.stellar.expert -- Stellar closes ledgers with immediate finality;
    a tx the explorer has is in a closed ledger."""
    await _get_json(client, f"{base}/explorer/public/tx/{tx}")
    return TxStatus("confirmed")


async def _blockchair_doge(client, base: str, tx: str) -> TxStatus:
    """api.blockchair.com dashboards: block_id -1 while in mempool; context.state
    is the tip height. Unknown tx -> data: [] (HTTP 200)."""
    data = await _get_json(client, f"{base}/dogecoin/dashboards/transaction/{tx}")
    rows = data.get("data")
    if not rows:
        raise _NotFound
    block = list(rows.values())[0]["transaction"]["block_id"]
    if block is None or block < 0:
        return TxStatus("pending", 0)
    return TxStatus("confirmed", max(1, data["context"]["state"] - block + 1))


async def _tronscan(client, base: str, tx: str) -> TxStatus:
    """apilist.tronscanapi.com/api/transaction-info with TRONSCAN_API_KEY (keyless
    is capped at 3 rps and was throttled in testing). Without a key, Tron goes
    to 3xpl instead, which is fully indexed for Tron."""
    if not TRONSCAN_API_KEY:
        return await _threexpl(client, 100011, tx)
    headers = {"TRON-PRO-API-KEY": TRONSCAN_API_KEY}
    data = await _get_json(client, f"{base}/api/transaction-info", params={"hash": tx}, headers=headers)
    if not data or not data.get("hash"):
        raise _NotFound
    if data.get("contractRet") not in (None, "SUCCESS"):
        return TxStatus("failed")
    return TxStatus("confirmed" if data.get("confirmed") else "pending", data.get("confirmations"))


async def _hyperion_wax(client, base: str, tx: str) -> TxStatus:
    """Hyperion (the bot's WAX history node). executed=false for unknown ids;
    irreversible once its block is at or below `lib`."""
    data = await _get_json(client, f"{base}/v2/history/get_transaction", params={"id": tx})
    actions = data.get("actions") or []
    if not data.get("executed") or not actions:
        raise _NotFound
    block = actions[0].get("block_num") or 0
    return TxStatus("confirmed" if block <= data.get("lib", 0) else "pending")


async def _solscan(client, base: str, tx: str) -> TxStatus:
    """Solscan Pro API v2 -- needs SOLSCAN_API_KEY (keyless returns 401, and the
    public site is behind Cloudflare). Not exercised with a real key yet."""
    if not SOLSCAN_API_KEY:
        return await _threexpl(client, 100002, tx)
    data = await _get_json(client, f"{base}/v2.0/transaction/detail", params={"tx": tx}, headers={"token": SOLSCAN_API_KEY})
    d = data.get("data") or {}
    if not d:
        raise _NotFound
    if d.get("status") not in (None, "Success", "success", 1):
        return TxStatus("failed")
    return TxStatus("confirmed")


# 3xpl (Blockchair's v3 API). Keyless use goes to sandbox-api.3xpl.com, which
# throttles hard (429s after a couple of quick calls) and on 2026-10-07 had only
# Optimism and Tron fully indexed -- BSC/Polygon/Base were 56-80% synced and
# Solana's index was broken, so recent txs there came back as unknown. Those
# four are therefore only routed to 3xpl when THREEXPL_API_KEY is set.
THREEXPL_SLUGS = {10: "optimism", 100011: "tron"}
THREEXPL_KEYED_SLUGS = {56: "bnb", 137: "polygon", 8453: "base", 100002: "solana"}


def _threexpl_slug(chain_id: int) -> str | None:
    if chain_id in THREEXPL_SLUGS:
        return THREEXPL_SLUGS[chain_id]
    if THREEXPL_API_KEY:
        return THREEXPL_KEYED_SLUGS.get(chain_id)
    return None


async def _threexpl(client, chain_id: int, tx: str) -> TxStatus:
    """GET /{chain}/transaction/{hash}?data=transaction,events. An unknown (or
    not-yet-indexed) hash still returns 200 with block=null, so pending and
    unknown can't be told apart -- both read as not_found. Every event carries a
    `failed` flag. No tip height in the response, so no confirmation count.
    The keyed host's auth param (`token`) hasn't been exercised with a real key."""
    slug = _threexpl_slug(chain_id)
    if slug is None:
        return UNAVAILABLE
    if THREEXPL_API_KEY:
        base, params = "https://api.3xpl.com", {"token": THREEXPL_API_KEY}
    else:
        base, params = "https://sandbox-api.3xpl.com", {}
    data = await _get_json(
        client, f"{base}/{slug}/transaction/{tx}",
        params={**params, "data": "transaction,events", "from": "all"},
    )
    body = data.get("data") or {}
    if not isinstance(body, dict) or not (body.get("transaction") or {}).get("block"):
        raise _NotFound
    events = [e for rows in (body.get("events") or {}).values() for e in (rows or [])]
    if any(e.get("failed") for e in events):
        return TxStatus("failed", source=httpx.URL(base).host)
    return TxStatus("confirmed", source=httpx.URL(base).host)


# -------------------------------------------------------- node providers --
# Used where no public explorer API exists, and as the fallback when an
# explorer is down/throttled or hasn't indexed the tx yet. These are the same
# nodes the bot sends withdrawals through (chains.rpc_url, or the hosts its
# helpers hardcode), so they add no new dependency -- but they're shared, so
# everything here goes through the same per-tx cache as the explorers.

# Fallback RPC URLs, tried in order after chains.rpc_url. publicnode refuses
# eth_getTransactionReceipt on BSC and Optimism without a token ("Archive
# requests require a personal token", seen 2026-10-07 even for latest-block
# txs), so those chains lead with the official public endpoints.
NODE_RPC = {
    1: ["https://ethereum-rpc.publicnode.com"],
    10: ["https://mainnet.optimism.io", "https://optimism-rpc.publicnode.com"],
    25: ["https://cronos-evm-rpc.publicnode.com", "https://evm.cronos.org"],
    56: ["https://bsc-dataseed.bnbchain.org", "https://bsc.publicnode.com"],
    137: ["https://polygon-bor-rpc.publicnode.com", "https://polygon-rpc.com"],
    8453: ["https://mainnet.base.org", "https://base-rpc.publicnode.com"],
    43114: ["https://avalanche-c-chain-rpc.publicnode.com", "https://api.avax.network/ext/bc/C/rpc"],
    20482: ["https://ethii.net/rpc"],
    100000: ["https://sui-rpc.publicnode.com", "https://fullnode.mainnet.sui.io"],
    100001: ["https://kaliumapi.appditto.com/api"],  # bot: helper.py banano_rpc
    100002: ["https://solana-rpc.publicnode.com", "https://api.mainnet-beta.solana.com"],
}
CAS_ELECTRUM_HOSTS = [  # bot: custom_coin_helpers/cascoin_helper.py
    ("electrum1.cascoin.net", 50002),
    ("electrum2.cascoin.net", 50002),
    ("electrum3.cascoin.net", 50002),
]
# bot: litecoinii_helper.py LC2_INDEX_API. Its /lc2/transaction route has been
# broken since 2026-09-26; this index route still returns confirmations.
LC2_INDEX_API = "http://explorer.doge2.org/dc2-lc2/api/explorer/lc2"


def _rpc_urls(chain_id: int, rpc_url: str | None) -> list[str]:
    urls = [rpc_url.rstrip("/")] if rpc_url and rpc_url.startswith("http") else []
    return urls + [u for u in NODE_RPC.get(chain_id, []) if u not in urls]


async def _jsonrpc(client, url: str, method: str, params: list):
    r = await client.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    r.raise_for_status()
    body = r.json()
    if body.get("error"):
        raise RuntimeError(body["error"])
    return body.get("result")


async def _node_evm(client, url: str, tx: str) -> TxStatus:
    """eth_getTransactionReceipt: null until mined (or unknown); status 0x0 = reverted."""
    rec = await _jsonrpc(client, url, "eth_getTransactionReceipt", [tx])
    if not rec:
        raise _NotFound
    if rec.get("status") == "0x0":
        return TxStatus("failed")
    tip = int(await _jsonrpc(client, url, "eth_blockNumber", []), 16)
    return TxStatus("confirmed", max(1, tip - int(rec["blockNumber"], 16) + 1))


async def _node_solana(client, url: str, tx: str) -> TxStatus:
    """getSignatureStatuses with history search -- null for unknown signatures;
    err set = failed; "processed" isn't final yet."""
    res = await _jsonrpc(client, url, "getSignatureStatuses", [[tx], {"searchTransactionHistory": True}])
    st = (res or {}).get("value", [None])[0]
    if not st:
        raise _NotFound
    if st.get("err"):
        return TxStatus("failed")
    if st.get("confirmationStatus") in ("confirmed", "finalized"):
        return TxStatus("confirmed")
    return TxStatus("pending")


async def _node_sui(client, url: str, tx: str) -> TxStatus:
    """sui_getTransactionBlock: errors with "Could not find" for unknown digests.
    Sui txs are final once executed, so a checkpointed tx is just confirmed."""
    try:
        res = await _jsonrpc(client, url, "sui_getTransactionBlock", [tx, {"showEffects": True}])
    except RuntimeError as e:
        if "find" in str(e).lower():
            raise _NotFound
        raise
    status = ((res or {}).get("effects") or {}).get("status", {}).get("status")
    if status == "failure":
        return TxStatus("failed")
    return TxStatus("confirmed" if res.get("checkpoint") else "pending")


async def _node_banano(client, url: str, tx: str) -> TxStatus:
    """Nano-protocol blocks_info -- {"error":"Block not found"} for unknown hashes;
    `confirmed` flips to "true" once the network votes on it (seconds)."""
    r = await client.post(url, json={"action": "blocks_info", "hashes": [tx], "json_block": True})
    r.raise_for_status()
    body = r.json()
    if "not found" in str(body.get("error", "")).lower():
        raise _NotFound
    block = (body.get("blocks") or {}).get(tx.upper()) or (body.get("blocks") or {}).get(tx)
    if not block:
        raise _NotFound
    return TxStatus("confirmed" if block.get("confirmed") == "true" else "pending")


async def _electrum_call(hosts, method: str, params: list):
    """One-shot Electrum request over TLS, trying hosts in random order (same
    approach as the bot's cascoin_helper._electrum_request)."""
    hosts = hosts[:]
    random.shuffle(hosts)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    last = None
    for host, port in hosts:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, ssl=ctx, limit=10 * 1024 * 1024), timeout=8
            )
            try:
                line = None
                for i, (m, p) in enumerate([("server.version", ["coindrop-explorer", "1.4"]), (method, params)]):
                    writer.write((json.dumps({"jsonrpc": "2.0", "id": i, "method": m, "params": p}) + "\n").encode())
                    await writer.drain()
                    line = await asyncio.wait_for(reader.readline(), timeout=8)
            finally:
                writer.close()
            return json.loads(line)
        except Exception as e:
            last = e
    raise RuntimeError(f"all electrum hosts failed: {last!r}")


async def _node_cascoin(client, base, tx: str) -> TxStatus:
    """ElectrumX blockchain.transaction.get verbose -- daemon error -5 ("No such
    mempool or blockchain transaction") for unknown txids."""
    body = await _electrum_call(CAS_ELECTRUM_HOSTS, "blockchain.transaction.get", [tx, True])
    if body.get("error"):
        if "No such" in str(body["error"]):
            raise _NotFound
        raise RuntimeError(body["error"])
    confs = int((body.get("result") or {}).get("confirmations") or 0)
    return TxStatus("confirmed" if confs > 0 else "pending", confs, source="electrum1.cascoin.net")


async def _node_lc2(client, base: str, tx: str) -> TxStatus:
    """LC2/DC2 project's index API -- unknown txids come back as HTTP 502
    {"error":"Address index HTTP 404"}."""
    r = await client.get(f"{base}/transaction/{tx}")
    if r.status_code in (404, 502) and "404" in r.text:
        raise _NotFound
    r.raise_for_status()
    confs = int(r.json().get("confirmations") or 0)
    return TxStatus("confirmed" if confs > 0 else "pending", confs)


async def _node(client, chain_id: int, tx: str, rpc_url: str | None) -> TxStatus | None:
    """Node lookup for chains that have one; None if this chain has no node path."""
    if chain_id in EVM_CHAINS:
        fn = _node_evm
    elif chain_id == 100002:
        fn = _node_solana
    elif chain_id == 100000:
        fn = _node_sui
    elif chain_id == 100001:
        fn = _node_banano
    else:
        return None
    last = None
    for url in _rpc_urls(chain_id, rpc_url):
        try:
            st = await fn(client, url, tx)
        except _NotFound:
            raise
        except Exception as e:  # throttled/refused/down -- next endpoint
            last = e
            continue
        st.source = st.source or httpx.URL(url).host
        return st
    if last is not None:
        raise last
    return None


# chain_id -> (provider, api base). Base URLs are the API hosts, which don't
# always match chains.explorer_url (e.g. Dork's API lives on dorkexplorer.com).
PROVIDERS = {
    100003: (_esplora, "https://btcscan.org/api"),
    100004: (_esplora, "https://litecoinspace.org/api"),
    100014: (_esplora, "https://bc3mempool.codefalcon.dev/api"),  # bot notes say Cloudflare-blocked from EC2
    100005: (_iquidus, "https://explorer.shibacoinshic.org"),
    100007: (_iquidus, "https://explorer.smartiecoin.com"),
    100012: (_iquidus, "https://explorer.rincoin.tech"),
    100017: (_iquidus, "http://explorer.doge2.org"),
    100013: (_kerrigan, "https://explorer.kerrigan.network"),
    100006: (_dork, "https://dorkexplorer.com"),
    100008: (_xrpscan, "https://api.xrpscan.com"),
    100018: (_stellar_expert, "https://api.stellar.expert"),
    100015: (_blockchair_doge, "https://api.blockchair.com"),
    100011: (_tronscan, "https://apilist.tronscanapi.com"),
    100009: (_hyperion_wax, "https://wax.eosusa.io"),
    100002: (_solscan, "https://pro-api.solscan.io"),
    # no public explorer API -- the node is the only source
    100010: (_node_cascoin, None),
    100016: (_node_lc2, LC2_INDEX_API),
}
EVM_CHAINS = {1, 10, 25, 56, 137, 8453, 43114, 20482}


# -------------------------------------------------------------------- cache --

# Seconds to reuse an answer. Final answers barely change; pending ones are
# what the page polls on.
_TTL = {"confirmed": 30, "failed": 3600, "pending": 10, "not_found": 10, "unavailable": 60}
_FINAL_TTL = 3600
_cache: dict[tuple[int, str], tuple[float, TxStatus]] = {}
_locks: dict[tuple[int, str], asyncio.Lock] = {}
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True)
    return _client


async def close():
    if _client is not None:
        await _client.aclose()


async def _explorer(client, chain_id: int, tx: str) -> TxStatus:
    if chain_id in EVM_CHAINS:
        return await _evm(client, chain_id, tx)
    provider = PROVIDERS.get(chain_id)
    if provider is None:
        return UNAVAILABLE
    fn, base = provider
    st = await fn(client, base, tx)
    if st.state not in ("unavailable", "not_found") and st.source is None and base:
        st.source = httpx.URL(base).host
    return st


async def _lookup(chain_id: int, tx: str, rpc_url: str | None = None) -> TxStatus:
    """Explorer first; the chain's node when the explorer has no answer
    (no API, throttled/down, or not indexed yet)."""
    client = _get_client()
    try:
        st = await _explorer(client, chain_id, tx)
    except _NotFound:
        st = TxStatus("not_found")
    except Exception as e:
        logger.warning("explorer lookup failed chain=%s tx=%s: %r", chain_id, tx, e)
        st = UNAVAILABLE
    if st.state not in ("unavailable", "not_found"):
        return st
    try:
        node_st = await _node(client, chain_id, tx, rpc_url)
    except _NotFound:
        node_st = TxStatus("not_found")
    except Exception as e:
        logger.warning("node lookup failed chain=%s tx=%s: %r", chain_id, tx, e)
        node_st = None
    return node_st if node_st is not None and node_st.state != "unavailable" else st


async def get_status(chain_id: int, tx: str, rpc_url: str | None = None) -> TxStatus:
    key = (chain_id, tx)
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]

    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:  # one upstream call per tx, however many viewers poll at once
        hit = _cache.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        st = await _lookup(chain_id, tx, rpc_url)
        ttl = _TTL[st.state]
        if st.state == "confirmed" and (st.confirmations is None or st.confirmations >= 6):
            ttl = _FINAL_TTL
        _cache[key] = (time.monotonic() + ttl, st)
        if len(_cache) > 5000:  # crude bound; entries are tiny
            cutoff = time.monotonic()
            for k in [k for k, (exp, _) in _cache.items() if exp < cutoff]:
                _cache.pop(k, None)
                _locks.pop(k, None)
    return st
