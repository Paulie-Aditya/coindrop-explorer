"""
Coin symbol -> icon file under static/coins/.

Mirrors coindrop-web's src/assets/coins/index.ts (COIN_ICONS) -- icons are
copied from there, and the same name-not-ticker matching and bridged-asset
aliasing apply. Coins without an icon fall back to a monogram in the template.
"""

COIN_ICONS = {
    "BTC": "btc.png",
    "ETH": "eth.png",
    "USDT": "usdt.png",
    "BNB": "bnb.png",
    "XRP": "xrp.png",
    "USDC": "usdc.png",
    # same underlying asset, bridged to another chain -- same icon
    "POLUSDC": "usdc.png",
    "SOLUSDC": "usdc.png",
    "SOL": "sol.png",
    "TRX": "trx.png",
    "DOGE": "doge.png",
    "XLM": "xlm.jpg",
    "LTC": "ltc.png",
    "AVAX": "avax.png",
    "CRO": "cro.png",
    "WAXP": "waxp.png",
    "BAN": "ban.png",
    "SHIC": "shic.png",
    "MATIC": "matic.png",
    "DORK": "dork.webp",
    "BC3": "bc3.webp",
    "CTHULHU": "cthulhu.webp",
    "DC2": "dc2.webp",
    "ETHII": "eth2.png",
    "KRGN": "krgn.webp",
    "LC2": "lc2.png",
    "RIN": "rincoin.webp",
    "SHIT": "shit.webp",
    "SMT": "smt.webp",
    "SOLUSDT": "solusdt.png",
    "BUSD": "busd.png",
    "OP": "op.png",
    "BSDETH": "bsdeth.png",
    "CHOCTOPUS": "choctopus.jpg",
    "CAS": "cascoin.webp",
    "NOBA": "nobacoin.webp",
    "BMN": "bmn.webp",
    # ETH bridged to the Optimism chain -- same underlying asset, same icon
    "OPETH": "eth.png",
}


def icon_for(symbol: str) -> str | None:
    filename = COIN_ICONS.get(symbol.upper())
    return f"/static/coins/{filename}" if filename else None
