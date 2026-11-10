"""BotActions (main.py) against an in-memory fake DB - no network, no Telegram."""

import importlib
import os
import sys
from datetime import datetime, timedelta

import pytest
from bson import ObjectId
from cryptography.fernet import Fernet

import miniapp

ADMIN = 1
OWNER = 100
OTHER = 200
PRIV = "0x" + "11" * 32


class Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction):
        self.docs.sort(key=lambda d: d.get(key), reverse=direction < 0)
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, n):
        return self.docs[:n]

    def __aiter__(self):
        self._it = iter(list(self.docs))
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


def matches(doc, q):
    return all(doc.get(k) == v for k, v in q.items())


class Result:
    def __init__(self, n):
        self.modified_count = n


class Collection:
    def __init__(self):
        self.docs = []

    async def find_one(self, q):
        return next((d for d in self.docs if matches(d, q)), None)

    def find(self, q=None):
        return Cursor([d for d in self.docs if matches(d, q or {})])

    async def update_one(self, q, upd, upsert=False):
        d = await self.find_one(q)
        if d is None and upsert:
            d = dict(q)
            self.docs.append(d)
        if d is not None:
            d.update(upd["$set"])

    async def update_many(self, q, upd):
        hit = [d for d in self.docs if matches(d, q)]
        for d in hit:
            d.update(upd["$set"])
        return Result(len(hit))

    async def count_documents(self, q):
        return len([d for d in self.docs if matches(d, q)])


class FakeDB:
    def __init__(self):
        self.cycles, self.users, self.config = Collection(), Collection(), Collection()


class FakeBot:
    def __init__(self):
        self.sent = []
        self.fail = False

    async def send_message(self, chat_id, text, **kw):
        if self.fail:
            raise RuntimeError("blocked")
        self.sent.append((chat_id, text))

    async def send_chat_action(self, chat_id, action):
        if self.fail:
            raise RuntimeError("blocked")


@pytest.fixture(scope="module")
def main_mod():
    from web3 import Web3
    from web3.eth import Eth

    os.environ.update(
        TELEGRAM_BOT_TOKEN="123456:ABC-DEF",
        MONGO_URI="mongodb://127.0.0.1:1",
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        ADMIN_IDS=str(ADMIN),
    )
    mp = pytest.MonkeyPatch()
    mp.setattr(Web3, "is_connected", lambda self, *a, **k: True)
    mp.setattr(Eth, "chain_id", property(lambda self: 56))
    sys.modules.pop("main", None)
    mod = importlib.import_module("main")
    yield mod
    mp.undo()
    sys.modules.pop("main", None)


@pytest.fixture
def env(main_mod):
    main_mod.db = FakeDB()
    main_mod.bot = FakeBot()
    main_mod.user_setups.clear()
    main_mod.user_panels.clear()
    main_mod.last_action.clear()
    main_mod.monitor_tasks.clear()
    main_mod.active_cycles.clear()
    return main_mod, main_mod.BotActions()


def add_cycle(mod, user_id=OWNER, status="active", **kw):
    doc = {
        "_id": ObjectId(), "user_id": user_id, "status": status, "chat_id": user_id,
        "wallets": [{"address": "0xW1", "key": mod.encrypt_key("rawkey")}],
        "created_at": datetime.utcnow(), "destination": "0xD", "current_hop": 0, **kw,
    }
    mod.db.cycles.docs.append(doc)
    return str(doc["_id"])


def code(exc):
    return exc.value.code


async def test_setup_defaults_and_updates(env):
    mod, a = env
    s = await a.get_setup(OWNER)
    assert (s["hops"], s["expiry_minutes"], s["lang"], s["destination"]) == (2, 30, "fa", None)
    s = await a.update_setup(OWNER, {"hops": 5, "lang": "en"})
    assert s["hops"] == 5 and s["lang"] == "en"
    assert mod.user_setups[OWNER]["hops"] == 5


async def test_destination_must_be_valid_address(env):
    _, a = env
    with pytest.raises(miniapp.ApiError) as e:
        await a.update_setup(OWNER, {"destination": "not-an-address"})
    assert code(e) == "invalid_address"


async def test_cycle_actions_enforce_ownership(env):
    mod, a = env
    cid = add_cycle(mod, user_id=OWNER)
    for action in ("cancel", "extend", "relaunch"):
        with pytest.raises(miniapp.ApiError) as e:
            await a.cycle_action(OTHER, cid, action)
        assert code(e) == "cycle_not_found"
    assert mod.db.cycles.docs[0]["status"] == "active"


async def test_cancel_and_status_rules(env):
    mod, a = env
    cid = add_cycle(mod, status="active")
    assert (await a.cycle_action(OWNER, cid, "cancel"))["status"] == "cancelled"
    with pytest.raises(miniapp.ApiError) as e:
        await a.cycle_action(OWNER, cid, "cancel")
    assert code(e) == "already_done"
    with pytest.raises(miniapp.ApiError) as e:
        await a.cycle_action(OWNER, cid, "extend")
    assert code(e) == "cannot_extend"


async def test_extend_adds_an_hour_and_reactivates(env):
    mod, a = env
    exp = datetime.utcnow() + timedelta(minutes=10)
    cid = add_cycle(mod, status="expired", expires_at=exp)
    r = await a.cycle_action(OWNER, cid, "extend")
    assert r["status"] == "active"
    assert mod.db.cycles.docs[0]["expires_at"] - exp == timedelta(hours=1)


async def test_relaunch_only_for_expired(env):
    mod, a = env
    cid = add_cycle(mod, status="active")
    with pytest.raises(miniapp.ApiError) as e:
        await a.cycle_action(OWNER, cid, "relaunch")
    assert code(e) == "only_expired"


async def test_invalid_cycle_id(env):
    _, a = env
    with pytest.raises(miniapp.ApiError) as e:
        await a.cycle_action(OWNER, "zzz", "cancel")
    assert code(e) == "invalid_cycle"


async def test_cancel_all_only_touches_own_active(env):
    mod, a = env
    add_cycle(mod, OWNER, "active")
    add_cycle(mod, OWNER, "completed")
    other = add_cycle(mod, OTHER, "active")
    assert await a.cancel_all(OWNER) == 1
    assert next(d for d in mod.db.cycles.docs if str(d["_id"]) == other)["status"] == "active"


async def test_start_requires_destination_and_reachable_chat(env):
    mod, a = env
    with pytest.raises(miniapp.ApiError) as e:
        await a.start_cycle(OWNER)
    assert code(e) == "set_wallet_first"
    mod.last_action.clear()
    mod.user_setups[OWNER]["destination"] = "0xD"
    mod.bot.fail = True
    with pytest.raises(miniapp.ApiError) as e:
        await a.start_cycle(OWNER)
    assert code(e) == "start_bot_first"
    assert mod.db.cycles.docs == []  # nothing created if keys can't be delivered


async def test_start_is_rate_limited(env):
    mod, a = env
    with pytest.raises(miniapp.ApiError):
        await a.start_cycle(OWNER)
    with pytest.raises(miniapp.ApiError) as e:
        await a.start_cycle(OWNER)
    assert code(e) == "rate_limited"


async def test_admin_cancel_notifies_user(env):
    mod, a = env
    cid = add_cycle(mod, OWNER, "active")
    await a.admin_cancel(ADMIN, cid)
    assert mod.db.cycles.docs[0]["status"] == "cancelled"
    assert mod.bot.sent and mod.bot.sent[0][0] == OWNER


async def test_admin_details_go_to_admin_chat_only(env):
    mod, a = env
    cid = add_cycle(mod, OWNER)
    await a.admin_send_details(ADMIN, cid)
    chat, text = mod.bot.sent[0]
    assert chat == ADMIN and "rawkey" in text


async def test_admin_summary_and_lists(env):
    mod, a = env
    add_cycle(mod, OWNER, "active")
    add_cycle(mod, OTHER, "failed")
    s = await a.admin_summary()
    assert (s["active"], s["total"], s["master_address"]) == (1, 2, None)
    assert len(await a.admin_cycles(None, 10)) == 2
    assert len(await a.admin_cycles("failed", 10)) == 1


async def test_set_master_validation_and_encryption(env):
    mod, a = env
    addr = mod.w3.eth.account.from_key(PRIV).address
    with pytest.raises(miniapp.ApiError) as e:
        await a.admin_set_master(ADMIN, "bad", PRIV)
    assert code(e) == "invalid_address"
    with pytest.raises(miniapp.ApiError) as e:
        await a.admin_set_master(ADMIN, addr, "nope")
    assert code(e) == "invalid_key"
    other = mod.w3.eth.account.from_key("0x" + "22" * 32).address
    with pytest.raises(miniapp.ApiError) as e:
        await a.admin_set_master(ADMIN, other, PRIV)
    assert code(e) == "key_mismatch"
    assert mod.db.config.docs == []
    await a.admin_set_master(ADMIN, addr, PRIV)
    stored = mod.db.config.docs[0]
    assert stored["master_address"] == addr
    assert stored["master_key"] != PRIV and mod.decrypt_key(stored["master_key"]) == PRIV
