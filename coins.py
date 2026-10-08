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
    # High-volume EVM/Solana token batch (asset-count expansion, 2026-10-08)
    # -- mirrors coindrop-web's COIN_ICONS for this batch. POL deliberately
    # excluded: config.CURRENCY_ALIASES on the bot already maps
    # "POL" -> "MATIC" (Polygon's ticker migration), so it's the same
    # currency as MATIC above, not a second one.
    "USD1": "usd1.png",
    "UNI": "uni.png",
    "USDG": "usdg.png",
    "ENA": "ena.png",
    "LINK": "link.png",
    "AAVE": "aave.png",
    "XAUT": "xaut.png",
    "USDS": "usds.png",
    "SAND": "sand.png",
    "WLD": "wld.png",
    "DAI": "dai.png",
    "QNT": "qnt.png",
    "PEPE": "pepe.png",
    "RAY": "ray.png",
    "PENGU": "pengu.png",
    "TRUMP": "trump.png",
    "ONDO": "ondo.png",
    "PAXG": "paxg.png",
    "ARB": "arb.png",
    "INJ": "inj.png",
    "FDUSD": "fdusd.png",
    "MET": "met.png",
    "ORCA": "orca.png",
    "FET": "fet.png",
    "U": "u.png",
    "ASTER": "aster.png",
    "ZRO": "zro.png",
    "JUP": "jup.png",
    "RENDER": "render.png",
    "WBT": "wbt.png",
    "PYUSD": "pyusd.png",
    "LIT": "lit.png",
    "VIRTUAL": "virtual.png",
    "NMR": "nmr.png",
    "SHIB": "shib.png",
    "ICP": "icp.png",
    "CAKE": "cake.png",
    "HTX": "htx.png",
    "OKB": "okb.png",
    "PENDLE": "pendle.png",
    "CRV": "crv.png",
    "LDO": "ldo.png",
    "ETHFI": "ethfi.png",
    "WIF": "wif.png",
    "STRK": "strk.png",
    "USDE": "usde.png",
    "BONK": "bonk.png",
    "MANA": "mana.png",
    "CAP": "cap.png",
    "JTO": "jto.png",
}


def icon_for(symbol: str) -> str | None:
    filename = COIN_ICONS.get(symbol.upper())
    return f"/static/coins/{filename}" if filename else None
