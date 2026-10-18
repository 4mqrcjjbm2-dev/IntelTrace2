"""3Commas en lecture seule : bots et trades (deals) ouverts.

Authentification : en-têtes APIKEY et Signature, où Signature = HMAC-SHA256(secret, chemin + requête).
"""

import hashlib
import hmac
from urllib.parse import urlencode

import httpx

BASE = "https://api.3commas.io"
PREFIX = "/public/api"


def sign(secret, path_and_query):
    return hmac.new(secret.encode(), path_and_query.encode(), hashlib.sha256).hexdigest()


class ThreeCommas:
    def __init__(self, api_key, api_secret, client=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.client = client

    async def _request(self, method, path, params=None):
        uri = PREFIX + path + ("?" + urlencode(params) if params else "")
        headers = {"APIKEY": self.api_key, "Signature": sign(self.api_secret, uri)}
        own = self.client is None
        client = self.client or httpx.AsyncClient(timeout=15)
        try:
            r = await client.request(method, BASE + uri, headers=headers)
        finally:
            if own:
                await client.aclose()
        if r.status_code in (401, 403):
            raise PermissionError("3Commas refuse la clé API. Vérifie la clé, le secret et la permission de lecture.")
        r.raise_for_status()
        return r.json()

    async def _get(self, path, params=None):
        return await self._request("GET", path, params)

    async def active_deals(self):
        return await self._get("/ver1/deals", {"scope": "active", "limit": 50})

    async def bots(self):
        return await self._get("/ver1/bots", {"limit": 50})

    # Écriture : utilisé seulement par l'interrupteur d'urgence (clé avec permission « Bots write »).
    async def disable_bot(self, bot_id):
        return await self._request("POST", f"/ver1/bots/{int(bot_id)}/disable")

    async def enable_bot(self, bot_id):
        return await self._request("POST", f"/ver1/bots/{int(bot_id)}/enable")


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(value):
    v = _num(value)
    return "?" if v is None else f"{v:+.2f} %".replace(".", ",")


def _usd(value):
    v = _num(value)
    return "?" if v is None else f"{v:+.2f} $ US".replace(".", ",")


def format_deals(deals):
    if not deals:
        return "Aucun trade ouvert sur 3Commas."
    lines = [f"{len(deals)} trade(s) ouvert(s) :"]
    total = 0.0
    for d in deals:
        profit = _num(d.get("actual_usd_profit"))
        total += profit or 0.0
        so = ""
        if d.get("max_safety_orders") is not None:
            so = f" · ordres de sécurité {d.get('completed_safety_orders_count', 0)}/{d.get('max_safety_orders')}"
        lines.append(
            f"- {d.get('pair', '?')} ({d.get('bot_name') or 'bot'}) : "
            f"{_pct(d.get('actual_profit_percentage'))}, {_usd(profit)}{so}"
        )
    lines.append(f"Total non réalisé : {_usd(total)}")
    return "\n".join(lines)


def format_bots(bots):
    if not bots:
        return "Aucun bot sur 3Commas."
    on = [b for b in bots if b.get("is_enabled")]
    lines = [f"{len(on)} bot(s) actif(s) sur {len(bots)} :"]
    for b in bots:
        state = "actif" if b.get("is_enabled") else "arrêté"
        pairs = ", ".join(b.get("pairs") or []) or "?"
        lines.append(
            f"- {b.get('name', '?')} ({state}) · {pairs} · trades ouverts : {b.get('active_deals_count', 0)}"
            f" · profit réalisé : {_usd(b.get('finished_deals_profit_usd'))}"
        )
    return "\n".join(lines)
