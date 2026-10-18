import asyncio
from types import SimpleNamespace

import httpx
from aiohttp.test_utils import TestClient, TestServer

from server import Ctx, clean_trades, make_token, make_web_app, valid_token
from storage import Storage

H = {"X-Requested-With": "blackbox"}


class FakeKill:
    def __init__(self, configured=True):
        self.configured, self.active, self.calls = configured, False, []

    async def stop(self):
        self.calls.append("stop"); self.active = True
        return ["3Commas : DCA désactivé"]

    async def resume(self):
        self.calls.append("resume"); self.active = False
        return ["3Commas : bot 1 réactivé"]


class FakeBrain:
    def __init__(self):
        self.got = []

    async def reply(self, chat_id, text):
        self.got.append((chat_id, text))
        return "Salut, c'est CARO."


def make_ctx(tmp_path, **kw):
    base = dict(store=Storage(tmp_path / "t.db"), killswitch=FakeKill(), password="secret-123", secret=b"k" * 32, brain=FakeBrain(), app_chat_id=42)
    base.update(kw)
    return Ctx(**base)


def run(ctx, scenario):
    async def go():
        client = TestClient(TestServer(make_web_app(ctx)))
        await client.start_server()
        try:
            return await scenario(client)
        finally:
            await client.close()
    return asyncio.run(go())


async def login(client, pw="secret-123"):
    return await client.post("/api/login", json={"motdepasse": pw}, headers=H)


def test_token_roundtrip():
    t = make_token(b"s", now=1000)
    assert valid_token(b"s", t, now=2000)
    assert not valid_token(b"x", t, now=2000)
    assert not valid_token(b"s", t, now=1000 + 31 * 86400)
    assert not valid_token(b"s", "n'importe quoi")


def test_api_requires_login_and_header(tmp_path):
    ctx = make_ctx(tmp_path)

    async def sc(c):
        r = await c.get("/api/etat"); j = await r.json()
        assert j == {"serveur": True, "connecte": False}
        assert (await c.get("/api/bots")).status == 401
        assert (await c.post("/api/kill", json={"confirme": True}, headers=H)).status == 401
        assert (await c.post("/api/login", json={"motdepasse": "secret-123"})).status == 403  # sans en-tête
        assert (await login(c, "mauvais")).status == 401
        assert (await login(c)).status == 200
        j = await (await c.get("/api/etat")).json()
        assert j["connecte"] and j["interrupteur_branche"] and j["caro"]
        assert (await c.get("/api/sante")).status == 200
        page = await c.get("/")
        assert page.status == 200 and "BLACK BOX" in await page.text()
    run(ctx, sc)


def test_login_rate_limit(tmp_path):
    ctx = make_ctx(tmp_path)

    async def sc(c):
        for _ in range(10):
            await login(c, "non")
        return (await login(c)).status
    assert run(ctx, sc) == 429


def test_kill_needs_confirmation_and_notifies(tmp_path):
    notes = []

    async def notify(text):
        notes.append(text)
    ctx = make_ctx(tmp_path, notify=notify)

    async def sc(c):
        await login(c)
        assert (await c.post("/api/kill", json={}, headers=H)).status == 400
        j = await (await c.post("/api/kill", json={"confirme": True}, headers=H)).json()
        assert j["kill_actif"] is True and j["lignes"] == ["3Commas : DCA désactivé"]
        j = await (await c.post("/api/reprendre", json={"confirme": True}, headers=H)).json()
        assert j["kill_actif"] is False
    run(ctx, sc)
    assert ctx.killswitch.calls == ["stop", "resume"]
    assert notes[0].startswith("Interrupteur d'urgence ACTIVÉ")


def test_kill_not_configured(tmp_path):
    ctx = make_ctx(tmp_path, killswitch=FakeKill(configured=False))

    async def sc(c):
        await login(c)
        return (await c.post("/api/kill", json={"confirme": True}, headers=H)).status
    assert run(ctx, sc) == 400


def test_bougies_validates_and_caches(tmp_path):
    hits = []

    def handler(req):
        hits.append(str(req.url))
        return httpx.Response(200, json=[[1792339200000, 1, 2, 0.5, 1.5, 10]])
    ctx = make_ctx(tmp_path, http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    async def sc(c):
        await login(c)
        assert (await c.get("/api/bougies?symbole=DOGEUSD&intervalle=1hr")).status == 400
        j = await (await c.get("/api/bougies?symbole=solusd&intervalle=1hr")).json()
        await c.get("/api/bougies?symbole=SOLUSD&intervalle=1hr")
        return j
    j = run(ctx, sc)
    assert j["bougies"][0][4] == 1.5
    assert hits == ["https://api.gemini.com/v2/candles/solusd/1hr"]


def test_caro_and_trades(tmp_path):
    ctx = make_ctx(tmp_path)

    async def sc(c):
        await login(c)
        j = await (await c.post("/api/caro", json={"texte": "allo"}, headers=H)).json()
        assert j["reponse"] == "Salut, c'est CARO."
        bad = await c.post("/api/trades", json={"trades": [{"symbol": "SOL"}]}, headers=H)
        assert bad.status == 400
        ok = await c.post("/api/trades", json={"trades": [{"t": "2026-10-01T14:30:00Z", "symbol": "sol", "r": 1.8, "score": 4}]}, headers=H)
        assert (await ok.json())["nombre"] == 1
        return await (await c.get("/api/trades")).json()
    j = run(ctx, sc)
    assert ctx.brain.got == [(42, "allo")]
    assert j["trades"] == [{"t": "2026-10-01T14:30:00Z", "symbol": "SOL", "r": 1.8, "score": 4.0}]


def test_bots_without_3commas(tmp_path):
    ctx = make_ctx(tmp_path)

    async def sc(c):
        await login(c)
        return await (await c.get("/api/bots")).json()
    j = run(ctx, sc)
    assert j["bots"] == [] and "3Commas" in j["raison"]


def test_clean_trades_limits():
    assert clean_trades([{"t": "x", "pnl_pct": 2}]) == [{"t": "x", "symbol": "?", "pnl_pct": 2.0}]
