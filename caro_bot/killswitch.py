"""Interrupteur d'urgence : arrête pour vrai les bots de trading, après confirmation du propriétaire.

- 3Commas : désactive chaque bot actif (il n'ouvre plus de nouveaux trades ; les trades déjà ouverts continuent).
- Freqtrade : appelle /api/v1/stop (le bot arrête de trader).
Les bots arrêtés par l'interrupteur sont mémorisés pour que /reprendre ne redémarre que ceux-là.
"""

import logging

import httpx

log = logging.getLogger("caro.kill")


class Freqtrade:
    def __init__(self, url, user, password, client=None):
        self.url = url.rstrip("/")
        self.auth = (user, password)
        self.client = client

    async def _post(self, path):
        own = self.client is None
        client = self.client or httpx.AsyncClient(timeout=15)
        try:
            r = await client.post(self.url + path, auth=self.auth)
        finally:
            if own:
                await client.aclose()
        r.raise_for_status()
        return r.json() if r.content else {}

    async def stop(self):
        return await self._post("/api/v1/stop")

    async def start(self):
        return await self._post("/api/v1/start")


class KillSwitch:
    def __init__(self, store, threecommas=None, freqtrade=None):
        self.store = store
        self.threecommas = threecommas  # client 3Commas avec permission d'écriture sur les bots
        self.freqtrade = freqtrade

    @property
    def configured(self):
        return bool(self.threecommas or self.freqtrade)

    @property
    def active(self):
        return bool(self.store.get("kill_active", False))

    async def stop(self):
        lines, stopped = [], []
        if self.threecommas:
            try:
                bots = await self.threecommas.bots()
                for b in bots:
                    if not b.get("is_enabled"):
                        continue
                    try:
                        await self.threecommas.disable_bot(b["id"])
                        stopped.append(b["id"])
                        lines.append(f"3Commas : {b.get('name', b['id'])} désactivé")
                    except Exception as e:
                        lines.append(f"3Commas : ÉCHEC pour {b.get('name', b['id'])} ({e})")
                if not bots or not any(b.get("is_enabled") for b in bots):
                    lines.append("3Commas : aucun bot actif")
            except Exception as e:
                lines.append(f"3Commas : impossible de lire les bots ({e})")
        if self.freqtrade:
            try:
                await self.freqtrade.stop()
                lines.append("Freqtrade : arrêté")
            except Exception as e:
                lines.append(f"Freqtrade : ÉCHEC ({e})")
        previous = self.store.get("kill_3c_ids", [])
        self.store.set("kill_3c_ids", sorted(set(previous) | set(stopped)))
        self.store.set("kill_active", True)
        log.warning("Interrupteur d'urgence activé : %s", "; ".join(lines))
        return lines

    async def resume(self):
        lines = []
        ids = self.store.get("kill_3c_ids", [])
        if self.threecommas:
            for bot_id in ids:
                try:
                    await self.threecommas.enable_bot(bot_id)
                    lines.append(f"3Commas : bot {bot_id} réactivé")
                except Exception as e:
                    lines.append(f"3Commas : ÉCHEC pour le bot {bot_id} ({e})")
        if self.freqtrade:
            try:
                await self.freqtrade.start()
                lines.append("Freqtrade : redémarré")
            except Exception as e:
                lines.append(f"Freqtrade : ÉCHEC ({e})")
        self.store.set("kill_3c_ids", [])
        self.store.set("kill_active", False)
        log.warning("Interrupteur d'urgence désactivé : %s", "; ".join(lines))
        return lines or ["Rien à redémarrer"]
