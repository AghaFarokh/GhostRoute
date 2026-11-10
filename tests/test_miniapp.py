import hashlib
import hmac
import json
import time
from datetime import datetime
from urllib.parse import urlencode

import pytest
from aiohttp.test_utils import TestClient, TestServer

import miniapp

TOKEN = "123456:TEST-TOKEN"


def make_init_data(user_id=42, token=TOKEN, auth_date=None, tamper=False):
    fields = {
        "auth_date": str(int(time.time()) if auth_date is None else auth_date),
        "query_id": "AAH",
        "user": json.dumps({"id": user_id, "first_name": "T"}),
    }
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    if tamper:
        fields["query_id"] = "EVIL"
    return urlencode(fields)


# ---------- validate_init_data ----------

def test_valid_init_data():
    user = miniapp.validate_init_data(make_init_data(7), TOKEN)
    assert user["id"] == 7


@pytest.mark.parametrize("bad", ["", "garbage", "a=1&hash=abc"])
def test_malformed_rejected(bad):
    assert miniapp.validate_init_data(bad, TOKEN) is None


def test_wrong_token_rejected():
    assert miniapp.validate_init_data(make_init_data(token="other:tok"), TOKEN) is None


def test_tampered_rejected():
    assert miniapp.validate_init_data(make_init_data(tamper=True), TOKEN) is None


def test_expired_rejected():
    old = int(time.time()) - miniapp.INIT_DATA_MAX_AGE - 10
    assert miniapp.validate_init_data(make_init_data(auth_date=old), TOKEN) is None


def test_future_auth_date_rejected():
    future = int(time.time()) + 3600
    assert miniapp.validate_init_data(make_init_data(auth_date=future), TOKEN) is None


# ---------- serialize_cycle ----------

def cycle_doc(status="active", current_hop=0):
    return {
        "_id": "abc123",
        "status": status,
        "current_hop": current_hop,
        "destination": "0xDEST",
        "wallets": [
            {"address": "0xW1", "key": "SECRET1"},
            {"address": "0xW2", "key": "SECRET2"},
        ],
        "transactions": ["tx"],
        "created_at": datetime(2026, 1, 2, 3, 4, 5),
        "expires_at": datetime(2026, 1, 2, 4, 4, 5),
    }


def test_serialize_never_leaks_keys():
    out = miniapp.serialize_cycle(cycle_doc())
    assert "SECRET" not in json.dumps(out)
    assert "wallets" not in out and "transactions" not in out
    assert out["deposit_address"] == "0xW1"
    assert out["created_at"] == "2026-01-02T03:04:05Z"


def test_serialize_hop_progress():
    assert miniapp.serialize_cycle(cycle_doc("active", 0))["current_hop"] == 1
    assert miniapp.serialize_cycle(cycle_doc("active", 5))["current_hop"] == 2
    assert miniapp.serialize_cycle(cycle_doc("completed", 2))["current_hop"] == 2


# ---------- HTTP ----------

@pytest.fixture
async def client():
    calls = []

    async def get_cycles(user_id, limit):
        calls.append((user_id, limit))
        return [cycle_doc()]

    app = miniapp.create_app(TOKEN, get_cycles)
    async with TestClient(TestServer(app)) as c:
        c.calls = calls
        yield c


async def test_healthz(client):
    r = await client.get("/healthz")
    assert r.status == 200 and (await r.json()) == {"ok": True}


async def test_index_served(client):
    r = await client.get("/")
    assert r.status == 200
    assert "GhostRoute" in await r.text()
    assert r.headers["X-Content-Type-Options"] == "nosniff"


async def test_api_requires_auth(client):
    r = await client.get("/api/cycles")
    assert r.status == 401
    r = await client.get("/api/cycles", headers={"X-Telegram-Init-Data": make_init_data(tamper=True)})
    assert r.status == 401
    assert client.calls == []


async def test_api_returns_only_own_cycles(client):
    r = await client.get("/api/cycles", headers={"X-Telegram-Init-Data": make_init_data(99)})
    assert r.status == 200
    body = await r.json()
    assert body["user_id"] == 99
    assert body["cycles"][0]["id"] == "abc123"
    assert "SECRET" not in json.dumps(body)
    assert client.calls == [(99, miniapp.CYCLE_LIMIT)]


# ---------- get_webapp_url ----------

def test_url_from_env(tmp_path):
    assert miniapp.get_webapp_url({"WEBAPP_URL": " https://x.example "}, tmp_path / "n") == "https://x.example"


def test_url_from_file(tmp_path):
    f = tmp_path / "u.txt"
    f.write_text("https://abc.trycloudflare.com\n")
    assert miniapp.get_webapp_url({}, f) == "https://abc.trycloudflare.com"


def test_url_missing_or_insecure(tmp_path):
    assert miniapp.get_webapp_url({}, tmp_path / "none") is None
    assert miniapp.get_webapp_url({"WEBAPP_URL": "http://insecure"}, tmp_path / "none") is None
