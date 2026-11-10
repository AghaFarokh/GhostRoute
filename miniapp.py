# =========================================================
# TELEGRAM MINI APP (read-only cycle dashboard)
# =========================================================
#
# Small aiohttp server that serves webapp/index.html and a JSON API
# authenticated with Telegram WebApp initData. It is exposed publicly
# through a cloudflared tunnel (see deploy/). It never returns private
# keys - only public cycle status information.

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

GET_CYCLES = web.AppKey("get_cycles")

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
# HANDLERS
# =========================================================

async def index(request):

    return web.FileResponse(WEBAPP_DIR / "index.html")

async def healthz(request):

    return web.json_response({"ok": True})

async def api_cycles(request):

    user = validate_init_data(
        request.headers.get("X-Telegram-Init-Data", ""),
        request.app[BOT_TOKEN],
    )

    if user is None:
        return web.json_response({"error": "unauthorized"}, status=401)

    cycles = await request.app[GET_CYCLES](user["id"], CYCLE_LIMIT)

    return web.json_response({
        "user_id": user["id"],
        "cycles": [serialize_cycle(c) for c in cycles],
    })

@web.middleware
async def security_headers(request, handler):

    response = await handler(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"

    return response

# =========================================================
# APP FACTORY / RUNNER
# =========================================================

def create_app(bot_token, get_cycles):
    """get_cycles(user_id, limit) -> awaitable list of cycle documents."""

    app = web.Application(middlewares=[security_headers])

    app[BOT_TOKEN] = bot_token

    app[GET_CYCLES] = get_cycles

    app.router.add_get("/", index)
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/api/cycles", api_cycles)

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
