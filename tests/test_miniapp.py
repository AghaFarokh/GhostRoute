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

ADMIN_ID = 1

CID = "a" * 24


class FakeActions:
    version = "vtest"
    source_url = "https://example.com/src"

    def __init__(self):
        self.calls = []
        self.setup = {"hops": 2, "destination": None, "expiry_minutes": 30, "lang": "fa", "info": "i"}

    def is_admin(self, uid):
        return uid == ADMIN_ID

    async def get_setup(self, uid):
        return dict(self.setup)

    async def update_setup(self, uid, changes):
        self.calls.append(("update_setup", uid, changes))
        self.setup.update(changes)
        return dict(self.setup)

    async def start_cycle(self, uid):
        self.calls.append(("start", uid))
        return {"id": CID, "status": "active"}

    async def list_cycles(self, uid, limit):
        self.calls.append(("list", uid, limit))
        return [cycle_doc()]

    async def cycle_action(self, uid, cycle_id, action):
        self.calls.append(("cycle_action", uid, cycle_id, action))
        if cycle_id == "b" * 24:
            raise miniapp.ApiError("cycle_not_found", 404)
        return {"status": "ok"}

    async def cancel_all(self, uid):
        self.calls.append(("cancel_all", uid))
        return 3

    async def admin_summary(self):
        return {"master_address": None, "users": 1, "active": 0, "total": 2}

    async def admin_cycles(self, status, limit):
        self.calls.append(("admin_cycles", status))
        return [dict(cycle_doc(), user_id=5)]

    async def admin_users(self, limit):
        return [{"user_id": 5, "first_name": "A", "last_name": "B", "username": "ab", "joined_at": datetime(2026, 1, 1)}]

    async def admin_cancel(self, uid, cycle_id):
        self.calls.append(("admin_cancel", uid, cycle_id))

    async def admin_send_details(self, uid, cycle_id):
        self.calls.append(("admin_details", uid, cycle_id))

    async def admin_set_master(self, uid, address, key):
        self.calls.append(("set_master", uid, address, key))


def hdr(uid=42, **kw):
    return {"X-Telegram-Init-Data": make_init_data(uid, **kw)}


@pytest.fixture
async def client():
    app = miniapp.create_app(TOKEN, FakeActions())
    async with TestClient(TestServer(app)) as c:
        c.actions = app[miniapp.ACTIONS]
        yield c


async def test_healthz(client):
    r = await client.get("/healthz")
    assert r.status == 200 and (await r.json()) == {"ok": True}


async def test_index_served(client):
    r = await client.get("/")
    assert r.status == 200
    assert "GhostRoute" in await r.text()
    assert r.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/state"), ("POST", "/api/setup"), ("GET", "/api/cycles"), ("POST", "/api/cycles"),
    ("POST", "/api/cycles/cancel-all"), ("POST", f"/api/cycles/{CID}/cancel"),
    ("GET", "/api/admin/summary"), ("GET", "/api/admin/cycles"), ("GET", "/api/admin/users"),
    ("POST", f"/api/admin/cycles/{CID}/cancel"), ("POST", "/api/admin/set-master"),
])
async def test_every_endpoint_requires_auth(client, method, path):
    r = await client.request(method, path)
    assert r.status == 401
    r = await client.request(method, path, headers=hdr(tamper=True))
    assert r.status == 401
    assert client.actions.calls == []


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/admin/summary"), ("GET", "/api/admin/cycles"), ("GET", "/api/admin/users"),
    ("POST", f"/api/admin/cycles/{CID}/cancel"), ("POST", f"/api/admin/cycles/{CID}/details"),
    ("POST", "/api/admin/set-master"),
])
async def test_admin_endpoints_forbidden_for_normal_user(client, method, path):
    r = await client.request(method, path, headers=hdr(42), json={"address": "a", "key": "k"})
    assert r.status == 403
    assert client.actions.calls == []


async def test_state_reports_admin_flag(client):
    assert (await (await client.get("/api/state", headers=hdr(42))).json())["is_admin"] is False
    body = await (await client.get("/api/state", headers=hdr(ADMIN_ID))).json()
    assert body["is_admin"] is True and body["version"] == "vtest"


async def test_cycles_scoped_to_caller_and_key_free(client):
    r = await client.get("/api/cycles", headers=hdr(99))
    body = await r.json()
    assert body["user_id"] == 99 and body["cycles"][0]["id"] == "abc123"
    assert "SECRET" not in json.dumps(body)
    assert ("list", 99, miniapp.CYCLE_LIMIT) in client.actions.calls


@pytest.mark.parametrize("body,code", [
    ({"hops": 1}, "bad_hops"), ({"hops": 11}, "bad_hops"), ({"hops": "3"}, "bad_hops"), ({"hops": True}, "bad_hops"),
    ({"expiry_minutes": 45}, "bad_expiry"), ({"expiry_minutes": 0}, "bad_expiry"), ({"expiry_minutes": 510}, "bad_expiry"),
    ({"lang": "de"}, "bad_lang"), ({"destination": ""}, "invalid_address"), ({"destination": 5}, "invalid_address"),
    ([1], "bad_request"),
])
async def test_setup_validation(client, body, code):
    r = await client.post("/api/setup", headers=hdr(), json=body)
    assert r.status == 400 and (await r.json())["error"] == code
    assert client.actions.calls == []


async def test_setup_applies_valid_changes(client):
    r = await client.post("/api/setup", headers=hdr(7), json={"hops": 5, "expiry_minutes": 60, "lang": "en", "evil": 1})
    assert r.status == 200
    assert client.actions.calls == [("update_setup", 7, {"hops": 5, "expiry_minutes": 60, "lang": "en"})]


async def test_setup_bad_json(client):
    r = await client.post("/api/setup", headers=hdr(), data="not json")
    assert r.status == 400


async def test_start_and_cancel_all(client):
    assert (await client.post("/api/cycles", headers=hdr(8))).status == 200
    r = await client.post("/api/cycles/cancel-all", headers=hdr(8))
    assert (await r.json()) == {"cancelled": 3}
    assert client.actions.calls == [("start", 8), ("cancel_all", 8)]


async def test_cycle_action_routes_and_validation(client):
    for action in ("cancel", "extend", "relaunch"):
        assert (await client.post(f"/api/cycles/{CID}/{action}", headers=hdr(3))).status == 200
    assert (await client.post(f"/api/cycles/{CID}/delete", headers=hdr(3))).status == 404
    assert (await client.post("/api/cycles/not-an-id/cancel", headers=hdr(3))).status == 400
    r = await client.post(f"/api/cycles/{'b' * 24}/cancel", headers=hdr(3))
    assert r.status == 404 and (await r.json())["error"] == "cycle_not_found"


async def test_admin_flow(client):
    h = hdr(ADMIN_ID)
    assert (await (await client.get("/api/admin/summary", headers=h)).json())["total"] == 2
    cycles = (await (await client.get("/api/admin/cycles?status=active", headers=h)).json())["cycles"]
    assert cycles[0]["user_id"] == 5 and "SECRET" not in json.dumps(cycles)
    assert (await client.get("/api/admin/cycles?status=bogus", headers=h)).status == 400
    users = (await (await client.get("/api/admin/users", headers=h)).json())["users"]
    assert users[0]["name"] == "A B" and users[0]["username"] == "ab"
    assert (await client.post(f"/api/admin/cycles/{CID}/cancel", headers=h)).status == 200
    assert (await client.post(f"/api/admin/cycles/{CID}/details", headers=h)).status == 200
    r = await client.post("/api/admin/set-master", headers=h, json={"address": "0xA", "key": "k"})
    assert r.status == 200
    assert (await client.post("/api/admin/set-master", headers=h, json={"address": 1, "key": "k"})).status == 400
    assert ("set_master", ADMIN_ID, "0xA", "k") in client.actions.calls
    assert ("admin_cycles", "active") in client.actions.calls


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
