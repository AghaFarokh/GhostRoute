# =========================================================
# TELEGRAM MINI APP (full bot UI: user + admin)
# =========================================================
#
# Small aiohttp server that serves webapp/index.html and a JSON API
# authenticated with Telegram WebApp initData. It is exposed publicly
# through a cloudflared tunnel (see deploy/). Business logic lives in an
# injected `actions` object (see main.py); this module only does auth,
# validation and serialization. It never returns private keys - keys are
# only ever sent to the user's Telegram chat by the bot.

import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web

WEBAPP_DIR = Path(__file__).parent / "webapp"

INIT_DATA_MAX_AGE = 24 * 60 * 60

CYCLE_LIMIT = 20

BOT_TOKEN = web.AppKey("bot_token", str)

ACTIONS = web.AppKey("actions")

# =========================================================
# AUTH
# =========================================================

def validate_init_data(init_data, bot_token, max_age=INIT_DATA_MAX_AGE, now=None):
    """Return the Telegram user dict if initData is authentic, else None."""

    if not init_data or not bot_token:
        return None

    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        return None

    received_hash = pairs.pop("hash", None)

    if not received_hash:
        return None

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(pairs.items())
    )

    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()

    expected = hmac.new(
        secret, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, received_hash):
        return None

    try:
        auth_date = int(pairs.get("auth_date", ""))
    except ValueError:
        return None

    now = time.time() if now is None else now

    if now - auth_date > max_age or auth_date - now > 60:
        return None

    try:
        user = json.loads(pairs.get("user", ""))
    except ValueError:
        return None

    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        return None

    return user

# =========================================================
# SERIALIZATION
# =========================================================

def _iso(dt):

    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None

def serialize_cycle(cycle):
    """Public, key-free view of a cycle document."""

    wallets = cycle.get("wallets", [])

    hops = len(wallets)

    raw_hop = cycle.get("current_hop", 0)

    status = cycle.get("status", "unknown")

    current = raw_hop if status == "completed" else min(raw_hop + 1, hops)

    deposit = wallets[0].get("address") if wallets else None

    return {
        "id": str(cycle["_id"]),
        "status": status,
        "hops": hops,
        "current_hop": current,
        "destination": cycle.get("destination"),
        "deposit_address": deposit,
        "created_at": _iso(cycle.get("created_at")),
        "expires_at": _iso(cycle.get("expires_at")),
    }

# =========================================================
# ERRORS / VALIDATION
# =========================================================

class ApiError(Exception):

    def __init__(self, code, status=400):

        super().__init__(code)

        self.code = code

        self.status = status

MIN_HOPS, MAX_HOPS = 2, 10

MIN_EXPIRY, MAX_EXPIRY, EXPIRY_STEP = 30, 480, 30

CYCLE_STATUSES = {"active", "expired", "completed", "failed", "cancelled"}

CYCLE_ACTIONS = {"cancel", "extend", "relaunch"}

def parse_setup(body):
    """Validate a /api/setup body; return only the fields to change."""

    if not isinstance(body, dict):
        raise ApiError("bad_request")

    changes = {}

    if "hops" in body:

        hops = body["hops"]

        if type(hops) is not int or not MIN_HOPS <= hops <= MAX_HOPS:
            raise ApiError("bad_hops")

        changes["hops"] = hops

    if "expiry_minutes" in body:

        mins = body["expiry_minutes"]

        if (
            type(mins) is not int
            or not MIN_EXPIRY <= mins <= MAX_EXPIRY
            or mins % EXPIRY_STEP
        ):
            raise ApiError("bad_expiry")

        changes["expiry_minutes"] = mins

    if "lang" in body:

        if body["lang"] not in ("fa", "en"):
            raise ApiError("bad_lang")

        changes["lang"] = body["lang"]

    if "destination" in body:

        dest = body["destination"]

        if not isinstance(dest, str) or not 0 < len(dest.strip()) <= 64:
            raise ApiError("invalid_address")

        changes["destination"] = dest.strip()

    return changes

# =========================================================
# HANDLERS
# =========================================================

async def index(request):

    return web.FileResponse(WEBAPP_DIR / "index.html")

async def healthz(request):

    return web.json_response({"ok": True})

def _auth(request):

    user = validate_init_data(
        request.headers.get("X-Telegram-Init-Data", ""),
        request.app[BOT_TOKEN],
    )

    if user is None:
        raise ApiError("unauthorized", 401)

    return user["id"]

def _admin(request):

    uid = _auth(request)

    if not request.app[ACTIONS].is_admin(uid):
        raise ApiError("forbidden", 403)

    return uid

async def _json_body(request):

    try:
        return await request.json()
    except ValueError:
        raise ApiError("bad_request")

def _cycle_id(request):

    cycle_id = request.match_info["cycle_id"]

    if not (len(cycle_id) == 24 and all(c in "0123456789abcdef" for c in cycle_id)):
        raise ApiError("invalid_cycle")

    return cycle_id

def _status_filter(request):

    status = request.query.get("status")

    if status in (None, "", "all"):
        return None

    if status not in CYCLE_STATUSES:
        raise ApiError("bad_request")

    return status

async def api_state(request):

    uid = _auth(request)

    actions = request.app[ACTIONS]

    return web.json_response({
        "user_id": uid,
        "is_admin": actions.is_admin(uid),
        "version": actions.version,
        "source_url": actions.source_url,
        "setup": await actions.get_setup(uid),
    })

async def api_setup(request):

    uid = _auth(request)

    changes = parse_setup(await _json_body(request))

    setup = await request.app[ACTIONS].update_setup(uid, changes)

    return web.json_response({"setup": setup})

async def api_cycles(request):

    uid = _auth(request)

    cycles = await request.app[ACTIONS].list_cycles(uid, CYCLE_LIMIT)

    return web.json_response({
        "user_id": uid,
        "cycles": [serialize_cycle(c) for c in cycles],
    })

async def api_start(request):

    uid = _auth(request)

    return web.json_response(await request.app[ACTIONS].start_cycle(uid))

async def api_cancel_all(request):

    uid = _auth(request)

    count = await request.app[ACTIONS].cancel_all(uid)

    return web.json_response({"cancelled": count})

async def api_cycle_action(request):

    uid = _auth(request)

    action = request.match_info["action"]

    if action not in CYCLE_ACTIONS:
        raise ApiError("bad_request", 404)

    result = await request.app[ACTIONS].cycle_action(
        uid, _cycle_id(request), action
    )

    return web.json_response(result)

async def api_admin_summary(request):

    _admin(request)

    return web.json_response(await request.app[ACTIONS].admin_summary())

async def api_admin_cycles(request):

    _admin(request)

    cycles = await request.app[ACTIONS].admin_cycles(
        _status_filter(request), CYCLE_LIMIT * 2
    )

    return web.json_response({
        "cycles": [dict(serialize_cycle(c), user_id=c.get("user_id")) for c in cycles],
    })

async def api_admin_users(request):

    _admin(request)

    users = await request.app[ACTIONS].admin_users(CYCLE_LIMIT * 2)

    return web.json_response({
        "users": [
            {
                "user_id": u.get("user_id"),
                "name": f"{u.get('first_name', '')} {u.get('last_name', '')}".strip(),
                "username": u.get("username") or "",
                "joined_at": _iso(u.get("joined_at")),
            }
            for u in users
        ],
    })

async def api_admin_cancel(request):

    uid = _admin(request)

    await request.app[ACTIONS].admin_cancel(uid, _cycle_id(request))

    return web.json_response({"ok": True})

async def api_admin_details(request):

    uid = _admin(request)

    await request.app[ACTIONS].admin_send_details(uid, _cycle_id(request))

    return web.json_response({"ok": True})

async def api_admin_set_master(request):

    uid = _admin(request)

    body = await _json_body(request)

    if not isinstance(body, dict):
        raise ApiError("bad_request")

    address, key = body.get("address"), body.get("key")

    if not isinstance(address, str) or not isinstance(key, str) or len(key) > 128:
        raise ApiError("bad_request")

    await request.app[ACTIONS].admin_set_master(uid, address.strip(), key.strip())

    return web.json_response({"ok": True})

@web.middleware
async def security_headers(request, handler):

    try:
        response = await handler(request)
    except ApiError as e:
        response = web.json_response({"error": e.code}, status=e.status)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"

    return response

# =========================================================
# APP FACTORY / RUNNER
# =========================================================

def create_app(bot_token, actions):
    """actions: object implementing the interface used by the handlers above."""

    app = web.Application(
        middlewares=[security_headers],
        client_max_size=16 * 1024,
    )

    app[BOT_TOKEN] = bot_token

    app[ACTIONS] = actions

    app.router.add_get("/", index)
    app.router.add_get("/healthz", healthz)

    app.router.add_get("/api/state", api_state)
    app.router.add_post("/api/setup", api_setup)
    app.router.add_get("/api/cycles", api_cycles)
    app.router.add_post("/api/cycles", api_start)
    app.router.add_post("/api/cycles/cancel-all", api_cancel_all)
    app.router.add_post("/api/cycles/{cycle_id}/{action}", api_cycle_action)

    app.router.add_get("/api/admin/summary", api_admin_summary)
    app.router.add_get("/api/admin/cycles", api_admin_cycles)
    app.router.add_get("/api/admin/users", api_admin_users)
    app.router.add_post("/api/admin/cycles/{cycle_id}/cancel", api_admin_cancel)
    app.router.add_post("/api/admin/cycles/{cycle_id}/details", api_admin_details)
    app.router.add_post("/api/admin/set-master", api_admin_set_master)

    return app

async def start_server(app, host="127.0.0.1", port=18471):

    runner = web.AppRunner(app)

    await runner.setup()

    await web.TCPSite(runner, host, port).start()

    logging.info(f"MINI APP listening on {host}:{port}")

    return runner

# =========================================================
# PUBLIC URL (set by env or written by deploy/tunnel.sh)
# =========================================================

def get_webapp_url(env=None, url_file=None):

    env = os.environ if env is None else env

    url = (env.get("WEBAPP_URL") or "").strip()

    if not url:

        path = Path(url_file or env.get("WEBAPP_URL_FILE", "tunnel_url.txt"))

        try:
            url = path.read_text().strip()
        except OSError:
            url = ""

    return url if url.startswith("https://") else None
