"""Outils de CARO : prix crypto (CoinGecko, lecture seulement) et heure des rappels."""

from datetime import datetime, timedelta

import httpx

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"

# Symboles courants vers les identifiants CoinGecko.
ALIASES = {
    "btc": "bitcoin",
    "eth": "ethereum",
    "sol": "solana",
    "xrp": "ripple",
    "ada": "cardano",
    "doge": "dogecoin",
    "ltc": "litecoin",
    "dot": "polkadot",
    "bnb": "binancecoin",
    "usdt": "tether",
    "usdc": "usd-coin",
    "avax": "avalanche-2",
    "link": "chainlink",
    "trx": "tron",
    "xlm": "stellar",
}


def coin_id(symbol):
    s = symbol.strip().lower()
    return ALIASES.get(s, s)


async def fetch_prices(symbols, client=None):
    """Retourne {symbole: {"cad": float, "usd": float, "change_24h": float | None}} pour les symboles connus."""
    ids = {coin_id(s): s.strip().upper() for s in symbols if s.strip()}
    if not ids:
        return {}
    params = {
        "ids": ",".join(ids),
        "vs_currencies": "cad,usd",
        "include_24hr_change": "true",
    }
    own = client is None
    client = client or httpx.AsyncClient(timeout=10)
    try:
        r = await client.get(COINGECKO_URL, params=params)
        r.raise_for_status()
        data = r.json()
    finally:
        if own:
            await client.aclose()
    out = {}
    for cid, sym in ids.items():
        d = data.get(cid)
        if not d or "usd" not in d:
            continue
        out[sym] = {
            "cad": d.get("cad"),
            "usd": d.get("usd"),
            "change_24h": d.get("usd_24h_change"),
        }
    return out


def fmt_money(value):
    """Format québécois : 64 512,30 (espace fine pour les milliers, virgule décimale)."""
    if value is None:
        return "?"
    decimals = 2 if value >= 1 else 6
    s = f"{value:,.{decimals}f}"
    return s.replace(",", " ").replace(".", ",")


def format_price(symbol, p):
    line = f"{symbol} : {fmt_money(p['cad'])} $ CA ({fmt_money(p['usd'])} $ US)"
    ch = p.get("change_24h")
    if ch is not None:
        line += f" · 24 h : {ch:+.1f} %".replace(".", ",")
    return line


MAX_AHEAD = timedelta(days=366)


def parse_when(quand, tz, now=None):
    """Lit une heure locale AAAA-MM-JJTHH:MM et la retourne en datetime avec fuseau.

    Lève ValueError si le format est mauvais, si l'heure est passée ou si elle est à plus d'un an.
    """
    now = now or datetime.now(tz)
    try:
        naive = datetime.strptime(quand.strip(), "%Y-%m-%dT%H:%M")
    except ValueError:
        raise ValueError("Format attendu : AAAA-MM-JJTHH:MM, en heure locale.")
    due = naive.replace(tzinfo=tz)
    if due <= now:
        raise ValueError("Cette heure est déjà passée.")
    if due - now > MAX_AHEAD:
        raise ValueError("Un rappel peut être au plus un an à l'avance.")
    return due
