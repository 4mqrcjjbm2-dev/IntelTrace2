import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest

from brain import Brain
from storage import Storage
from tools import coin_id, fetch_prices, fmt_money, format_price, parse_when

TZ = ZoneInfo("America/Toronto")


# ---------- tools ----------

def test_coin_id_aliases():
    assert coin_id("BTC") == "bitcoin"
    assert coin_id(" eth ") == "ethereum"
    assert coin_id("pepe") == "pepe"


def test_fmt_money():
    assert fmt_money(64512.3) == "64 512,30"
    assert fmt_money(0.0000123) == "0,000012"
    assert fmt_money(None) == "?"


def test_format_price():
    line = format_price("BTC", {"cad": 90000.0, "usd": 65000.5, "change_24h": -1.234})
    assert line == "BTC : 90 000,00 $ CA (65 000,50 $ US) · 24 h : -1,2 %"


def test_parse_when():
    now = datetime(2026, 10, 18, 12, 0, tzinfo=TZ)
    due = parse_when("2026-10-18T14:30", TZ, now)
    assert due == datetime(2026, 10, 18, 14, 30, tzinfo=TZ)
    with pytest.raises(ValueError, match="passée"):
        parse_when("2026-10-18T11:00", TZ, now)
    with pytest.raises(ValueError, match="Format"):
        parse_when("demain 9h", TZ, now)
    with pytest.raises(ValueError, match="un an"):
        parse_when("2028-01-01T09:00", TZ, now)


def test_fetch_prices_parses_coingecko():
    def handler(request):
        assert request.url.params["ids"] == "bitcoin,inconnu"
        return httpx.Response(200, json={"bitcoin": {"cad": 90000, "usd": 65000, "usd_24h_change": 2.5}})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await fetch_prices(["btc", "inconnu"], client=c)

    prices = asyncio.run(run())
    assert prices == {"BTC": {"cad": 90000, "usd": 65000, "change_24h": 2.5}}


# ---------- storage ----------

def test_history_starts_with_user(tmp_path):
    s = Storage(tmp_path / "t.db")
    for i in range(3):
        s.add_turn(1, "user", f"q{i}")
        s.add_turn(1, "assistant", f"r{i}")
    h = s.recent_history(1, limit=3)  # coupe au milieu : doit commencer par user
    assert [m["role"] for m in h] == ["user", "assistant"]
    assert h[0]["content"] == "q2"
    s.clear_history(1)
    assert s.recent_history(1) == []


def test_reminders_roundtrip(tmp_path):
    s = Storage(tmp_path / "t.db")
    due = datetime(2030, 1, 1, 14, 0, tzinfo=timezone.utc)
    rid = s.add_reminder(7, due, "Appeler Marc")
    assert s.pending_reminders(7)[0] == {"id": rid, "chat_id": 7, "due_utc": due, "message": "Appeler Marc"}
    assert not s.delete_reminder(8, rid)  # pas le bon chat
    s.mark_sent(rid)
    assert s.pending_reminders() == []
    assert not s.delete_reminder(7, rid)


# ---------- brain : boucle d'outils avec un faux client ----------

class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def resp(stop, *blocks):
    return SimpleNamespace(stop_reason=stop, content=list(blocks))


def test_brain_reminder_tool_loop(tmp_path):
    store = Storage(tmp_path / "t.db")
    created = []
    when = (datetime.now(TZ) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    client = FakeClient([
        resp("tool_use",
             SimpleNamespace(type="text", text="Je note ça."),
             SimpleNamespace(type="tool_use", id="t1", name="creer_rappel", input={"quand": when, "message": "Appeler Marc"})),
        resp("end_turn", SimpleNamespace(type="text", text="C'est noté pour dans 2 h.")),
    ])
    brain = Brain(client, store, TZ, on_reminder=lambda c, d, m: created.append((c, d, m)) or 42)

    text = asyncio.run(brain.reply(5, "rappelle-moi dans 2 h d'appeler Marc"))

    assert text == "C'est noté pour dans 2 h."
    assert created[0][0] == 5 and created[0][2] == "Appeler Marc"
    assert created[0][1].tzinfo == timezone.utc
    second = client.calls[1]
    result = second["messages"][-1]["content"][0]
    assert result["tool_use_id"] == "t1" and '"id": 42' in result["content"]
    assert second["fallbacks"] == "default"
    assert store.recent_history(5)[-1] == {"role": "assistant", "content": "C'est noté pour dans 2 h."}


def test_brain_tool_error_and_refusal(tmp_path):
    store = Storage(tmp_path / "t.db")
    client = FakeClient([
        resp("tool_use", SimpleNamespace(type="tool_use", id="t1", name="creer_rappel", input={"quand": "2000-01-01T00:00", "message": "x"})),
        resp("refusal"),
    ])
    brain = Brain(client, store, TZ, model="claude-haiku-5-5", on_reminder=lambda *a: 1)
    text = asyncio.run(brain.reply(5, "test"))
    err = client.calls[1]["messages"][-1]["content"][0]
    assert err["is_error"] is True and "passée" in err["content"]
    assert "fallbacks" not in client.calls[0]
    assert text == "Je peux pas t'aider avec ça."


# ---------- 3Commas ----------

import hashlib
import hmac

from threecommas import ThreeCommas, format_bots, format_deals, sign


def test_3c_signature_and_request():
    seen = {}

    def handler(request):
        seen["path"] = request.url.raw_path.decode()
        seen["headers"] = request.headers
        return httpx.Response(200, json=[{"pair": "USDT_BTC", "bot_name": "DCA BTC", "actual_profit_percentage": "-1.5",
                                          "actual_usd_profit": "-3.2", "completed_safety_orders_count": 2, "max_safety_orders": 5}])

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await ThreeCommas("KEY", "SECRET", client=c).active_deals()

    deals = asyncio.run(run())
    assert seen["path"] == "/public/api/ver1/deals?scope=active&limit=50"
    assert seen["headers"]["APIKEY"] == "KEY"
    expected = hmac.new(b"SECRET", seen["path"].encode(), hashlib.sha256).hexdigest()
    assert seen["headers"]["Signature"] == expected == sign("SECRET", seen["path"])
    text = format_deals(deals)
    assert "USDT_BTC (DCA BTC) : -1,50 %, -3,20 $ US · ordres de sécurité 2/5" in text
    assert "Total non réalisé : -3,20 $ US" in text


def test_3c_bad_key_and_bots_format():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(401))) as c:
            return await ThreeCommas("K", "S", client=c).bots()

    with pytest.raises(PermissionError):
        asyncio.run(run())
    out = format_bots([{"name": "Grid ETH", "is_enabled": True, "pairs": ["USDT_ETH"], "active_deals_count": 1,
                        "finished_deals_profit_usd": "12.5"}, {"name": "Vieux", "is_enabled": False}])
    assert out.startswith("1 bot(s) actif(s) sur 2")
    assert "Grid ETH (actif) · USDT_ETH · trades ouverts : 1 · profit réalisé : +12,50 $ US" in out
    assert format_deals([]) == "Aucun trade ouvert sur 3Commas."


def test_brain_exposes_3c_tool_only_when_configured(tmp_path):
    store = Storage(tmp_path / "t.db")
    names = lambda b: [t.get("name") for t in b.tools]
    assert "trois_commas" not in names(Brain(FakeClient([]), store, TZ))
    assert "trois_commas" in names(Brain(FakeClient([]), store, TZ, threecommas=object()))
