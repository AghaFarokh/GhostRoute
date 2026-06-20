# =========================================================
# IMPORTS
# =========================================================

import asyncio
import logging
import math
import os
import time
import uuid

from asyncio import Lock
from datetime import datetime, timedelta
from decimal import Decimal

import qrcode

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from aiogram.utils.keyboard import InlineKeyboardBuilder

from bson import ObjectId
from bson.errors import InvalidId

from cryptography.fernet import Fernet

from dotenv import load_dotenv

import lang as _lang

from motor.motor_asyncio import AsyncIOMotorClient

from py_crypto_hd_wallet import (
    HdWalletBipFactory,
    HdWalletBip44Coins,
    HdWalletBipWordsNum,
    HdWalletBipDataTypes,
)

from web3 import Web3
from web3.exceptions import TimeExhausted

# =========================================================
# ENV
# =========================================================

load_dotenv()

API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ENC_KEY = os.getenv("ENCRYPTION_KEY")
ADMIN_IDS = {
    int(uid.strip())
    for uid in os.getenv("ADMIN_IDS", "").split(",")
    if uid.strip().isdigit()
}

RPCS = [

    "https://bsc-dataseed.binance.org/",

    "https://bsc-dataseed1.defibit.io/",

    "https://bsc-dataseed1.ninicoin.io/",
]

# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(

    level=logging.INFO,

    format="%(asctime)s | %(levelname)s | %(message)s"
)

# =========================================================
# TELEGRAM
# =========================================================

bot = Bot(token=API_TOKEN)

dp = Dispatcher()

# =========================================================
# DATABASE
# =========================================================

db_client = AsyncIOMotorClient(MONGO_URI)

db = db_client.usdt_hop_bot

# =========================================================
# ENCRYPTION
# =========================================================

cipher = Fernet(
    ENC_KEY.encode()
)

# =========================================================
# WEB3
# =========================================================

w3 = None

for rpc in RPCS:

    try:

        provider = Web3.HTTPProvider(rpc)

        temp = Web3(provider)

        if temp.is_connected():

            if temp.eth.chain_id != 56:
                continue

            w3 = temp

            logging.info(f"Connected RPC: {rpc}")

            break

    except:
        pass

if not w3:
    raise Exception("No working RPC")

# =========================================================
# USDT
# =========================================================

USDT_ADDRESS = Web3.to_checksum_address(
    "0x55d398326f99059fF775485246999027B3197955"
)

USDT_ABI = """
[
    {
        "constant":true,
        "inputs":[
            {
                "name":"_owner",
                "type":"address"
            }
        ],
        "name":"balanceOf",
        "outputs":[
            {
                "name":"balance",
                "type":"uint256"
            }
        ],
        "type":"function"
    },

    {
        "constant":false,

        "inputs":[
            {
                "name":"_to",
                "type":"address"
            },

            {
                "name":"_value",
                "type":"uint256"
            }
        ],

        "name":"transfer",

        "outputs":[
            {
                "name":"success",
                "type":"bool"
            }
        ],

        "type":"function"
    }
]
"""

usdt_contract = w3.eth.contract(

    address=USDT_ADDRESS,

    abi=USDT_ABI
)

# =========================================================
# DAI + PANCAKESWAP V3 ROUTER
# =========================================================

DAI_ADDRESS = Web3.to_checksum_address(
    "0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3"
)

PANCAKE_V3_ROUTER = Web3.to_checksum_address(
    "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4"
)

SWAP_BATCH_WEI = 500 * 10**18   # max 500 USDT/DAI per swap tx

ERC20_FULL_ABI = """
[
    {
        "constant": true,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": false,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "success", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": false,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "success", "type": "bool"}],
        "type": "function"
    }
]
"""

dai_contract = w3.eth.contract(
    address=DAI_ADDRESS,
    abi=ERC20_FULL_ABI
)

usdt_contract_full = w3.eth.contract(
    address=USDT_ADDRESS,
    abi=ERC20_FULL_ABI
)

PANCAKE_V3_ROUTER_ABI = """
[
    {
        "inputs": [{
            "components": [
                {"name": "tokenIn",           "type": "address"},
                {"name": "tokenOut",          "type": "address"},
                {"name": "fee",               "type": "uint24"},
                {"name": "recipient",         "type": "address"},
                {"name": "amountIn",          "type": "uint256"},
                {"name": "amountOutMinimum",  "type": "uint256"},
                {"name": "sqrtPriceLimitX96", "type": "uint160"}
            ],
            "name": "params",
            "type": "tuple"
        }],
        "name": "exactInputSingle",
        "outputs": [{"name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function"
    }
]
"""

pancake_router = w3.eth.contract(
    address=PANCAKE_V3_ROUTER,
    abi=PANCAKE_V3_ROUTER_ABI
)

# =========================================================
# GLOBALS
# =========================================================

master_nonce_lock = Lock()

active_cycles = {}

monitor_tasks = {}

user_panels = {}

user_setups = {}

last_action = {}

admin_panels = {}

cycle_expiry = {}  # cycle_key -> datetime UTC expiry

def t(user_id, key):
    return _lang.get(user_id, key, user_setups)

# =========================================================
# FSM
# =========================================================

class SetupState(StatesGroup):

    waiting_wallet = State()

class AdminState(StatesGroup):

    waiting_master_address = State()

    waiting_master_key = State()

    waiting_cycle_id_view = State()

    waiting_cycle_id_cancel = State()

# =========================================================
# SECURITY
# =========================================================

def is_admin(user_id):

    return user_id in ADMIN_IDS

def rate_limit(user_id, seconds=2):

    now = time.time()

    last = last_action.get(user_id, 0)

    if now - last < seconds:
        return False

    last_action[user_id] = now

    return True

def ensure_user_setup(user_id):

    if user_id not in user_setups:

        user_setups[user_id] = {

            "hops": 2,

            "destination": None,

            "status": "Idle",

            "expiry_minutes": 30,

            "lang": "fa"
        }

# =========================================================
# ENCRYPTION
# =========================================================

def encrypt_key(key):

    return cipher.encrypt(
        key.encode()
    ).decode()

def decrypt_key(enc):

    return cipher.decrypt(
        enc.encode()
    ).decode()

# =========================================================
# DATABASE
# =========================================================

async def setup_database():

    await db.cycles.create_index("status")

    await db.cycles.create_index("user_id")

    await db.cycles.create_index("created_at")

    await db.users.create_index("user_id", unique=True)

# =========================================================
# HELPERS
# =========================================================

def human_usdt(amount):

    return round(
        amount / 10**18,
        4
    )

def progress(current, total):

    return (
        "🟩" * current
        + "⬜" * (total - current)
    )

# =========================================================
# WALLET GENERATOR
# =========================================================

def generate_wallets(count):

    wallets = []

    factory = HdWalletBipFactory(
        HdWalletBip44Coins.BINANCE_SMART_CHAIN
    )

    for _ in range(count):

        session = str(uuid.uuid4())

        wallet = factory.CreateRandom(
            session,
            HdWalletBipWordsNum.WORDS_NUM_24
        )

        wallet.Generate(addr_num=1)

        data = wallet.GetData(HdWalletBipDataTypes.ADDRESS)[0].ToDict()

        wallets.append({

            "address":
            Web3.to_checksum_address(
                data["address"]
            ),

            "key":
            encrypt_key(
                data["raw_priv"]
            )
        })

    return wallets

# =========================================================
# NONCE
# =========================================================

async def get_nonce(address):

    return await asyncio.to_thread(
        w3.eth.get_transaction_count,
        address,
        "pending"
    )

# =========================================================
# RECEIPT
# =========================================================

async def wait_receipt(
    tx_hash,
    timeout=300
):

    try:

        receipt = await asyncio.to_thread(
            w3.eth.wait_for_transaction_receipt,
            tx_hash,
            timeout
        )

        if receipt.status != 1:
            raise Exception("TX reverted")

        return receipt

    except TimeExhausted:

        await asyncio.sleep(10)

        try:

            receipt = await asyncio.to_thread(
                w3.eth.get_transaction_receipt,
                tx_hash
            )

            return receipt

        except:

            raise Exception(
                f"TX timeout {tx_hash.hex()}"
            )

# =========================================================
# RETRY
# =========================================================

async def retry_async(
    func,
    retries=3,
    delay=3
):

    last_error = None

    for attempt in range(retries):

        try:

            return await func()

        except Exception as e:

            last_error = e

            logging.warning(
                f"Retry {attempt+1}/{retries}: {e}"
            )

            await asyncio.sleep(delay)

    raise last_error

# =========================================================
# STATUS
# =========================================================

async def append_status(
    msg,
    logs,
    text
):

    logs.append(text)

    logs[:] = logs[-50:]

    content = "\n\n".join(logs)

    if len(content) > 3900:
        content = content[-3900:]

    try:

        await asyncio.sleep(1)

        await msg.edit_text(content)

    except:
        pass

# =========================================================
# GAS
# =========================================================

async def estimate_usdt_gas(
    sender,
    recipient,
    amount
):

    gas = await asyncio.to_thread(
        usdt_contract.functions.transfer(
            recipient,
            amount
        ).estimate_gas,
        {"from": sender}
    )

    return int(gas * 1.2)

# =========================================================
# APPROVE TOKEN
# =========================================================

async def approve_token(wallet, token_contract, spender, amount):

    async def action():

        sender_addr = wallet["address"]

        priv = decrypt_key(wallet["key"])

        nonce = await get_nonce(sender_addr)

        gas_price = int(w3.eth.gas_price * 1.3)

        tx = token_contract.functions.approve(
            spender, amount
        ).build_transaction({
            "chainId": 56,
            "nonce": nonce,
            "gas": int(60_000 * 1.2),
            "gasPrice": gas_price,
        })

        signed = w3.eth.account.sign_transaction(tx, priv)

        tx_hash = await asyncio.to_thread(
            w3.eth.send_raw_transaction, signed.raw_transaction
        )

        await wait_receipt(tx_hash)

        return tx_hash.hex()

    return await retry_async(action)

# =========================================================
# SWAP (single batch, PancakeSwap V3)
# =========================================================

async def _swap_single(wallet, token_in, token_out, amount_in):
    """One exactInputSingle call. Returns tx hash."""

    async def action():

        sender_addr = wallet["address"]

        priv = decrypt_key(wallet["key"])

        nonce = await get_nonce(sender_addr)

        gas_price = int(w3.eth.gas_price * 1.3)

        # 0.5% slippage — generous for stable pairs
        amount_out_min = amount_in * 995 // 1000

        tx = pancake_router.functions.exactInputSingle({
            "tokenIn":           token_in,
            "tokenOut":          token_out,
            "fee":               100,        # 0.01% stable pool
            "recipient":         sender_addr,
            "amountIn":          amount_in,
            "amountOutMinimum":  amount_out_min,
            "sqrtPriceLimitX96": 0,
        }).build_transaction({
            "chainId":  56,
            "nonce":    nonce,
            "gas":      int(300_000 * 1.2),
            "gasPrice": gas_price,
            "value":    0,
        })

        signed = w3.eth.account.sign_transaction(tx, priv)

        tx_hash = await asyncio.to_thread(
            w3.eth.send_raw_transaction, signed.raw_transaction
        )

        await wait_receipt(tx_hash)

        return tx_hash.hex()

    return await retry_async(action)

async def swap_usdt_to_dai(wallet, total_amount):
    """Swap USDT → DAI in ≤500 USDT batches. Returns list of tx hashes."""

    txs = []

    remaining = total_amount

    while remaining > 0:

        batch = min(remaining, SWAP_BATCH_WEI)

        tx = await _swap_single(
            wallet, USDT_ADDRESS, DAI_ADDRESS, batch
        )

        txs.append(tx)

        remaining -= batch

    return txs

async def swap_dai_to_usdt(wallet, total_amount):
    """Swap DAI → USDT in ≤500 DAI batches. Returns list of tx hashes."""

    txs = []

    remaining = total_amount

    while remaining > 0:

        batch = min(remaining, SWAP_BATCH_WEI)

        tx = await _swap_single(
            wallet, DAI_ADDRESS, USDT_ADDRESS, batch
        )

        txs.append(tx)

        remaining -= batch

    return txs

# =========================================================
# TRANSFER DAI
# =========================================================

async def transfer_dai(sender, recipient, amount):

    async def action():

        sender_addr = sender["address"]

        priv = decrypt_key(sender["key"])

        nonce = await get_nonce(sender_addr)

        gas_price = int(w3.eth.gas_price * 1.3)

        gas = await asyncio.to_thread(
            dai_contract.functions.transfer(
                recipient, amount
            ).estimate_gas,
            {"from": sender_addr}
        )

        tx = dai_contract.functions.transfer(
            recipient, amount
        ).build_transaction({
            "chainId":  56,
            "nonce":    nonce,
            "gas":      int(gas * 1.2),
            "gasPrice": gas_price,
        })

        signed = w3.eth.account.sign_transaction(tx, priv)

        tx_hash = await asyncio.to_thread(
            w3.eth.send_raw_transaction, signed.raw_transaction
        )

        await wait_receipt(tx_hash)

        return tx_hash.hex()

    return await retry_async(action)

# =========================================================
# MASTER CONFIG
# =========================================================

async def get_master_config():

    config = await db.config.find_one({
        "type": "admin"
    })

    if not config:

        raise Exception(
            "Master wallet not configured"
        )

    return config

# =========================================================
# FUND FIRST HOP
# =========================================================

async def fund_first_hop(
    target,
    hops,
    usdt_amount
):

    async def action():

        config = await get_master_config()

        master_addr = config["master_address"]

        master_key = decrypt_key(
            config["master_key"]
        )

        # Live gas price + 10% buffer
        gas_price = int(w3.eth.gas_price * 1.1)

        # Swap batches needed at hop 0 (USDT→DAI)
        n_batches = max(1, math.ceil(usdt_amount / SWAP_BATCH_WEI))

        # Gas units per operation (multipliers match actual tx functions):
        #   approve:          60_000 * 1.2 * 1.3
        #   swap (V3):       300_000 * 1.2 * 1.3
        #   DAI transfer:     65_000 * 1.2 * 1.3
        #   BNB sweep tx:     21_000 * 1.2 * 1.3
        #   BNB sweep reserve:21_000 * 1.3  (left in wallet for next sweep)

        GAS_APPROVE = int(60_000  * 1.2 * 1.3)   # 93_600
        GAS_SWAP    = int(300_000 * 1.2 * 1.3)   # 468_000
        GAS_DAI     = int(65_000  * 1.2 * 1.3)   # 101_400
        GAS_BNB     = int(21_000  * 1.2 * 1.3) + int(21_000 * 1.3)  # 60_060

        # Hop 0: approve + n_batches swaps + DAI transfer + BNB sweep forward
        hop0 = GAS_APPROVE + n_batches * GAS_SWAP + GAS_DAI + GAS_BNB

        # Middle hops (between hop 0 and last): DAI transfer + BNB sweep
        middle = max(0, hops - 2) * (GAS_DAI + GAS_BNB)

        # Last hop gas is topped up separately by top_up_gas_if_needed

        total_gas = hop0 + middle

        amount = total_gas * gas_price

        async with master_nonce_lock:

            nonce = await get_nonce(
                master_addr
            )

            tx = {

                "chainId": 56,

                "nonce": nonce,

                "to": target,

                "value": amount,

                "gas": 21000,

                "gasPrice": gas_price
            }

            signed = w3.eth.account.sign_transaction(
                tx,
                master_key
            )

            tx_hash = await asyncio.to_thread(
                w3.eth.send_raw_transaction,
                signed.raw_transaction
            )

        await wait_receipt(tx_hash)

        return tx_hash.hex()

    return await retry_async(action)

# =========================================================
# TOP UP GAS (safety net for last hop)
# =========================================================

async def top_up_gas_if_needed(wallet_addr, needed_wei):
    """Send BNB from master to wallet if balance < needed_wei."""

    balance = await asyncio.to_thread(
        w3.eth.get_balance,
        wallet_addr
    )

    if balance >= needed_wei:
        return None

    config = await get_master_config()

    master_addr = config["master_address"]

    master_key = decrypt_key(config["master_key"])

    gas_price = int(w3.eth.gas_price * 1.1)

    # Send the shortfall plus the cost of this top-up tx itself
    topup = needed_wei - balance + int(21_000 * gas_price)

    async with master_nonce_lock:

        nonce = await get_nonce(master_addr)

        tx = {
            "chainId": 56,
            "nonce": nonce,
            "to": wallet_addr,
            "value": topup,
            "gas": 21000,
            "gasPrice": gas_price
        }

        signed = w3.eth.account.sign_transaction(tx, master_key)

        tx_hash = await asyncio.to_thread(
            w3.eth.send_raw_transaction,
            signed.raw_transaction
        )

    await wait_receipt(tx_hash)

    logging.info(
        f"Gas top-up {w3.from_wei(topup, 'ether')} BNB → {wallet_addr}"
    )

    return tx_hash.hex()

# =========================================================
# TRANSFER USDT
# =========================================================

async def transfer_usdt(
    sender,
    recipient,
    amount
):

    async def action():

        sender_addr = sender["address"]

        priv = decrypt_key(
            sender["key"]
        )

        nonce = await get_nonce(
            sender_addr
        )

        gas_price = int(
            w3.eth.gas_price * 1.3
        )

        gas = await estimate_usdt_gas(
            sender_addr,
            recipient,
            amount
        )

        tx = usdt_contract.functions.transfer(
            recipient,
            amount
        ).build_transaction({

            "chainId": 56,

            "nonce": nonce,

            "gas": gas,

            "gasPrice": gas_price
        })

        signed = w3.eth.account.sign_transaction(
            tx,
            priv
        )

        tx_hash = await asyncio.to_thread(
            w3.eth.send_raw_transaction,
            signed.raw_transaction
        )

        await wait_receipt(tx_hash)

        return tx_hash.hex()

    return await retry_async(action)

# =========================================================
# TRANSFER BNB
# =========================================================

async def transfer_remaining_bnb(
    sender,
    recipient
):

    async def action():

        sender_addr = sender["address"]

        priv = decrypt_key(
            sender["key"]
        )

        nonce = await get_nonce(
            sender_addr
        )

        gas_price = int(
            w3.eth.gas_price * 1.3
        )

        balance = await asyncio.to_thread(
            w3.eth.get_balance,
            sender_addr
        )

        # Cost to send this BNB sweep tx + 20% buffer
        gas_cost = int(21000 * gas_price * 1.2)

        # Dynamic reserve: 1 extra sweep worth of gas, scales with network price
        reserve = int(21000 * gas_price)

        amount = balance - gas_cost - reserve

        if amount <= 0:

            logging.warning(
                f"Skip BNB sweep {sender_addr}"
            )

            return None

        tx = {

            "chainId": 56,

            "nonce": nonce,

            "to": recipient,

            "value": amount,

            "gas": 21000,

            "gasPrice": gas_price
        }

        signed = w3.eth.account.sign_transaction(
            tx,
            priv
        )

        tx_hash = await asyncio.to_thread(
            w3.eth.send_raw_transaction,
            signed.raw_transaction
        )

        await wait_receipt(tx_hash)

        return tx_hash.hex()

    return await retry_async(action)

# =========================================================
# QR
# =========================================================

async def send_qr(chat_id, address):

    img = qrcode.make(address)

    path = f"/tmp/{uuid.uuid4()}.png"

    img.save(path)

    await bot.send_photo(

        chat_id,

        FSInputFile(path),

        caption=f"Send USDT:\n\n`{address}`",

        parse_mode="Markdown"
    )

    try:
        os.remove(path)
    except:
        pass

# =========================================================
# UI
# =========================================================

def build_keyboard(user_id):

    ensure_user_setup(user_id)

    setup = user_setups[user_id]

    wallet_btn = (
        t(user_id, "btn_wallet_set")
        if setup["destination"]
        else t(user_id, "btn_wallet_unset")
    )

    expiry_min = setup.get("expiry_minutes", 30)

    kb = InlineKeyboardBuilder()

    kb.row(

        InlineKeyboardButton(
            text="➖",
            callback_data="minus"
        ),

        InlineKeyboardButton(
            text=f"{setup['hops']} {t(user_id, 'hops_btn')}",
            callback_data="noop"
        ),

        InlineKeyboardButton(
            text="➕",
            callback_data="plus"
        )
    )

    kb.row(

        InlineKeyboardButton(
            text=t(user_id, "btn_time_minus"),
            callback_data="time_minus"
        ),

        InlineKeyboardButton(
            text=f"⏱️ {expiry_min}{t(user_id, 'time_unit')}",
            callback_data="noop"
        ),

        InlineKeyboardButton(
            text=t(user_id, "btn_time_plus"),
            callback_data="time_plus"
        )
    )

    kb.row(

        InlineKeyboardButton(
            text=wallet_btn,
            callback_data="wallet"
        )
    )

    kb.row(

        InlineKeyboardButton(
            text=t(user_id, "btn_start"),
            callback_data="start"
        )
    )

    kb.row(

        InlineKeyboardButton(
            text=t(user_id, "btn_history"),
            callback_data="history"
        ),

        InlineKeyboardButton(
            text=t(user_id, "btn_cancel_all"),
            callback_data="cancel"
        )
    )

    kb.row(

        InlineKeyboardButton(
            text=t(user_id, "btn_info"),
            callback_data="info"
        ),

        InlineKeyboardButton(
            text=t(user_id, "btn_lang"),
            callback_data="lang_toggle"
        )
    )

    if is_admin(user_id):

        kb.row(

            InlineKeyboardButton(
                text=t(user_id, "btn_admin"),
                callback_data="admin_panel"
            )
        )

    return kb.as_markup()

# =========================================================
# PANEL
# =========================================================

async def render_panel(user_id):

    ensure_user_setup(user_id)

    setup = user_setups[user_id]

    hops = setup["hops"]

    fee = hops * 0.5

    expiry_min = setup.get("expiry_minutes", 30)

    text = (
        f"🔄 {t(user_id, 'panel_header')}\n"
        f"{'─' * 24}\n\n"
        f"🔢 {t(user_id, 'hops')}: {hops}     "
        f"💰 {t(user_id, 'fee')}: {fee} USDT\n"
        f"⏱️ {t(user_id, 'expiry')}: {expiry_min} {t(user_id, 'min')}\n\n"
        f"💼 {t(user_id, 'wallet_label')}:\n"
        f"{setup['destination'] or t(user_id, 'wallet_not_set')}\n\n"
        f"📡 {t(user_id, 'status_label')}: "
        f"{t(user_id, 'status_idle')}"
    )

    kb = build_keyboard(user_id)

    panel = user_panels.get(user_id)

    if panel:

        try:

            await bot.edit_message_text(

                chat_id=panel["chat_id"],

                message_id=panel["message_id"],

                text=text,

                reply_markup=kb
            )

            return

        except:
            pass

    # No stored panel or edit failed — send a fresh one.
    # For private chats chat_id == user_id.
    sent = await bot.send_message(
        user_id,
        text,
        reply_markup=kb
    )

    user_panels[user_id] = {
        "chat_id": sent.chat.id,
        "message_id": sent.message_id
    }

# =========================================================
# ADMIN PANEL
# =========================================================

def build_admin_keyboard():

    kb = InlineKeyboardBuilder()

    kb.row(

        InlineKeyboardButton(
            text="⚙️ Set Master Wallet",
            callback_data="admin_set_master"
        )
    )

    kb.row(

        InlineKeyboardButton(
            text="📋 All Cycles",
            callback_data="admin_cycles_all"
        ),

        InlineKeyboardButton(
            text="🟢 Active",
            callback_data="admin_cycles_active"
        ),

        InlineKeyboardButton(
            text="🔴 Failed",
            callback_data="admin_cycles_failed"
        )
    )

    kb.row(

        InlineKeyboardButton(
            text="🔍 View Cycle",
            callback_data="admin_view_cycle"
        ),

        InlineKeyboardButton(
            text="❌ Cancel Cycle",
            callback_data="admin_cancel_cycle_btn"
        )
    )

    kb.row(

        InlineKeyboardButton(
            text="🔙 Back to Panel",
            callback_data="admin_back"
        )
    )

    return kb.as_markup()

async def render_admin_panel(chat_id):

    config = await db.config.find_one({"type": "admin"})

    master = (
        config["master_address"]
        if config
        else "❌ Not Set"
    )

    active_count = await db.cycles.count_documents({
        "status": "active"
    })

    total_count = await db.cycles.count_documents({})

    user_count = await db.users.count_documents({})

    text = (
        "🔑 ADMIN PANEL\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💳 Master Wallet:\n`{master}`\n\n"
        f"👥 Total Users: {user_count}\n"
        f"🔄 Active Cycles: {active_count}\n"
        f"📊 Total Cycles: {total_count}"
    )

    kb = build_admin_keyboard()

    panel = admin_panels.get(chat_id)

    if panel:

        try:

            await bot.edit_message_text(

                chat_id=chat_id,

                message_id=panel["message_id"],

                text=text,

                reply_markup=kb,

                parse_mode="Markdown"
            )

            return

        except Exception as e:

            logging.warning(f"Admin panel edit failed: {e}")

    sent = await bot.send_message(
        chat_id,
        text,
        reply_markup=kb,
        parse_mode="Markdown"
    )

    admin_panels[chat_id] = {
        "message_id": sent.message_id
    }

# =========================================================
# MONITOR
# =========================================================

async def monitor_cycle(
    chat_id,
    cycle_id,
    user_id
):

    cycle_key = str(cycle_id)

    if cycle_key in active_cycles:
        return

    active_cycles[cycle_key] = True

    logs = ["🚀 Cycle started"]

    msg = await bot.send_message(chat_id, logs[0])

    try:

        cycle_object = ObjectId(cycle_id)

        cycle = await db.cycles.find_one({
            "_id": cycle_object
        })

        if not cycle:
            raise Exception("Cycle not found")

        # Load expiry into memory (extension updates this dict live).
        # If the stored expiry is already in the past (e.g. relaunch of old
        # expired cycle), reset to 30 min from now so the loop doesn't
        # exit immediately.
        expires_at = (
            cycle.get("expires_at")
            or datetime.utcnow() + timedelta(minutes=30)
        )

        if expires_at < datetime.utcnow():
            expires_at = datetime.utcnow() + timedelta(minutes=30)
            await db.cycles.update_one(
                {"_id": cycle_object},
                {"$set": {"expires_at": expires_at}}
            )

        if cycle_key not in cycle_expiry:
            cycle_expiry[cycle_key] = expires_at

        config = await get_master_config()

        wallets = cycle["wallets"]

        destination = cycle["destination"]

        start_hop = cycle.get(
            "current_hop",
            0
        )

        master = config["master_address"]

        hops = len(wallets)

        fee_usdt = (
            Decimal(hops)
            * Decimal("0.5")
        )

        fee_units = int(
            fee_usdt * Decimal("1000000000000000000")
        )

        for i in range(
            start_hop,
            len(wallets)
        ):

            wallet = wallets[i]

            current = wallet["address"]

            await db.cycles.update_one(

                {"_id": cycle_object},

                {
                    "$set": {
                        "current_hop": i
                    }
                }
            )

            await append_status(
                msg,
                logs,
                f"""
Hop:
{i+1}/{len(wallets)}

{progress(i+1, len(wallets))}

Wallet:
{current}
"""
            )

            detected = 0

            if i == 0:

                # Hop 0: wait until expires_at (dynamic — updated live on extension)
                exp_str = cycle_expiry[cycle_key].strftime("%H:%M UTC")

                await append_status(
                    msg,
                    logs,
                    f"⏰ Expires at {exp_str}"
                )

                while datetime.utcnow() < cycle_expiry.get(
                    cycle_key, datetime.utcnow()
                ):

                    balance = await asyncio.to_thread(
                        usdt_contract.functions.balanceOf(
                            current
                        ).call
                    )

                    if balance > 0:

                        detected = balance

                        break

                    await asyncio.sleep(15)

            else:

                # Hops > 0 carry DAI, not USDT.
                # 60s gives ample time for the RPC node to reflect the
                # confirmed transfer — 15s was too tight on lagging nodes.
                timeout = 60
                interval = 2

                start = time.time()

                while time.time() - start < timeout:

                    balance = await asyncio.to_thread(
                        dai_contract.functions.balanceOf(
                            current
                        ).call
                    )

                    if balance > 0:

                        detected = balance

                        break

                    await asyncio.sleep(interval)

            if detected == 0:

                await db.cycles.update_one(

                    {"_id": cycle_object},

                    {
                        "$set": {
                            "status": "expired"
                        }
                    }
                )

                if i == 0:

                    kb = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text=t(user_id, "btn_relaunch"),
                                    callback_data=f"relaunch:{cycle_id}"
                                ),
                                InlineKeyboardButton(
                                    text=t(user_id, "btn_extend"),
                                    callback_data=f"extend_cycle:{cycle_id}"
                                )
                            ]
                        ]
                    )

                    await bot.send_message(
                        chat_id,
                        "⏰ Cycle expired — no deposit received within the expiry window.",
                        reply_markup=kb
                    )

                return

            human = human_usdt(
                detected
            )

            token_label = "USDT" if i == 0 else "DAI"

            await append_status(
                msg,
                logs,
                f"""
✅ Deposit:
{human} {token_label}
"""
            )

            # =====================================================
            # MINIMUM CHECK — must be > fee, and checked BEFORE
            # gas is funded so master loses nothing on bad deposits
            # =====================================================

            if i == 0 and detected <= fee_units:

                await db.cycles.update_one(
                    {"_id": cycle_object},
                    {"$set": {"status": "failed",
                               "error": "deposit_below_fee"}}
                )

                await append_status(
                    msg,
                    logs,
                    f"❌ Deposit too low\n\n"
                    f"Received: {human_usdt(detected)} USDT\n"
                    f"Minimum:  >{fee_usdt} USDT (cycle fee)\n\n"
                    f"No gas was spent. Use your hop 1 "
                    f"private key to recover the deposited amount."
                )

                return

            # =====================================================
            # FIRST HOP GAS
            # =====================================================

            if i == 0:

                tx = await fund_first_hop(
                    current,
                    hops,
                    detected
                )

                await append_status(
                    msg,
                    logs,
                    f"""
⛽ Gas funded

https://bscscan.com/tx/{tx}
"""
                )

            last = (
                i == len(wallets) - 1
            )

            # =====================================================
            # FINAL HOP
            # =====================================================

            if last:

                # Read actual DAI balance to compute swap batches
                dai_bal = await asyncio.to_thread(
                    dai_contract.functions.balanceOf(current).call
                )

                n_batches_last = max(1, math.ceil(dai_bal / SWAP_BATCH_WEI))

                gas_price_now = int(w3.eth.gas_price * 1.3)

                # Budget: approve + all swap batches + 2 USDT transfers (fee + final)
                needed = int((
                    int(60_000  * 1.2) +
                    n_batches_last * int(300_000 * 1.2) +
                    int(55_000  * 1.2) * 2
                ) * gas_price_now)

                topup_tx = await top_up_gas_if_needed(
                    current,
                    needed
                )

                if topup_tx:

                    await append_status(
                        msg,
                        logs,
                        f"""
⛽ Gas topped up

https://bscscan.com/tx/{topup_tx}
"""
                    )

                # Approve DAI for the PancakeSwap V3 router
                approve_tx = await approve_token(
                    wallet,
                    dai_contract,
                    PANCAKE_V3_ROUTER,
                    dai_bal
                )

                await append_status(
                    msg,
                    logs,
                    f"""
✅ DAI approved

https://bscscan.com/tx/{approve_tx}
"""
                )

                # Swap DAI → USDT in ≤500 DAI batches
                swap_txs = await swap_dai_to_usdt(wallet, dai_bal)

                for stx in swap_txs:

                    await append_status(
                        msg,
                        logs,
                        f"""
🔄 DAI→USDT swap

https://bscscan.com/tx/{stx}
"""
                    )

                # Send fee in USDT to master
                fee_tx = await transfer_usdt(
                    wallet,
                    master,
                    fee_units
                )

                await append_status(
                    msg,
                    logs,
                    f"""
💰 Fee Sent:
{fee_usdt} USDT

https://bscscan.com/tx/{fee_tx}
"""
                )

                await asyncio.sleep(3)

                remaining = await asyncio.to_thread(
                    usdt_contract.functions.balanceOf(
                        current
                    ).call
                )

                if remaining <= 0:

                    raise Exception(
                        "No remaining USDT after DAI→USDT swap"
                    )

                # Ensure gas for the final USDT transfer
                needed_for_one = int(55_000 * 1.2 * gas_price_now)

                topup_tx2 = await top_up_gas_if_needed(
                    current,
                    needed_for_one
                )

                if topup_tx2:

                    await append_status(
                        msg,
                        logs,
                        f"""
⛽ Gas topped up

https://bscscan.com/tx/{topup_tx2}
"""
                    )

                final_tx = await transfer_usdt(
                    wallet,
                    destination,
                    remaining
                )

                await append_status(
                    msg,
                    logs,
                    f"""
💸 Final Sent:
{human_usdt(remaining)} USDT

https://bscscan.com/tx/{final_tx}
"""
                )

                await asyncio.sleep(3)

                bnb_tx = await transfer_remaining_bnb(
                    wallet,
                    master
                )

                if bnb_tx:

                    await append_status(
                        msg,
                        logs,
                        f"""
⛽ BNB Returned

https://bscscan.com/tx/{bnb_tx}
"""
                    )

            # =====================================================
            # NORMAL HOP (hop 0 swaps USDT→DAI; middle hops forward DAI)
            # =====================================================

            else:

                target = wallets[i+1]["address"]

                if i == 0:

                    # Approve USDT for the PancakeSwap V3 router
                    approve_tx = await approve_token(
                        wallet,
                        usdt_contract_full,
                        PANCAKE_V3_ROUTER,
                        detected
                    )

                    await append_status(
                        msg,
                        logs,
                        f"""
✅ USDT approved

https://bscscan.com/tx/{approve_tx}
"""
                    )

                    # Swap USDT → DAI in ≤500 USDT batches
                    swap_txs = await swap_usdt_to_dai(wallet, detected)

                    for stx in swap_txs:

                        await append_status(
                            msg,
                            logs,
                            f"""
🔄 USDT→DAI swap

https://bscscan.com/tx/{stx}
"""
                        )

                    # Read actual DAI received
                    dai_amount = await asyncio.to_thread(
                        dai_contract.functions.balanceOf(current).call
                    )

                    # Transfer DAI to next wallet
                    dai_tx = await transfer_dai(wallet, target, dai_amount)

                    await append_status(
                        msg,
                        logs,
                        f"""
💸 DAI Moved

https://bscscan.com/tx/{dai_tx}
"""
                    )

                else:

                    # Middle hop: forward DAI to next wallet
                    dai_tx = await transfer_dai(wallet, target, detected)

                    await append_status(
                        msg,
                        logs,
                        f"""
💸 DAI Moved

https://bscscan.com/tx/{dai_tx}
"""
                    )

                await asyncio.sleep(3)

                bnb_tx = await transfer_remaining_bnb(
                    wallet,
                    target
                )

                if bnb_tx:

                    await append_status(
                        msg,
                        logs,
                        f"""
⛽ BNB Moved

https://bscscan.com/tx/{bnb_tx}
"""
                    )

            await asyncio.sleep(2)

        await db.cycles.update_one(

            {"_id": cycle_object},

            {
                "$set": {
                    "status": "completed",
                    "current_hop": len(wallets)
                }
            }
        )

        await append_status(
            msg,
            logs,
            "🎉 COMPLETED"
        )

    except asyncio.CancelledError:

        try:

            await db.cycles.update_one(

                {"_id": ObjectId(cycle_id)},

                {
                    "$set": {
                        "status": "cancelled"
                    }
                }
            )

        except:
            pass

        try:
            await append_status(
                msg,
                logs,
                "🚫 Cycle cancelled"
            )
        except:
            pass

    except Exception as e:

        logging.exception(e)

        try:

            await db.cycles.update_one(

                {"_id": ObjectId(cycle_id)},

                {
                    "$set": {
                        "status": "failed",
                        "error": str(e)
                    }
                }
            )

        except:
            pass

        await append_status(
            msg,
            logs,
            f"❌ {str(e)}"
        )

    finally:

        active_cycles.pop(
            cycle_key,
            None
        )

        monitor_tasks.pop(
            cycle_key,
            None
        )

        cycle_expiry.pop(
            cycle_key,
            None
        )

# =========================================================
# START
# =========================================================

@dp.message(Command("start"))
async def start(message: types.Message):

    user_id = message.from_user.id

    user_setups[user_id] = {

        "hops": 2,

        "destination": None,

        "status": "Idle",

        "expiry_minutes": 30,

        "lang": "fa"
    }

    # Track new users and notify admins
    existing = await db.users.find_one({"user_id": user_id})

    if not existing:

        username   = message.from_user.username or ""
        first_name = message.from_user.first_name or ""
        last_name  = message.from_user.last_name  or ""

        await db.users.insert_one({
            "user_id":    user_id,
            "username":   username,
            "first_name": first_name,
            "last_name":  last_name,
            "joined_at":  datetime.utcnow()
        })

        name_str = f"{first_name} {last_name}".strip() or str(user_id)
        uname_str = f"@{username}" if username else "—"

        notify_text = (
            "👤 *کاربر جدید / New User*\n"
            "━━━━━━━━━━━━━━━\n"
            f"🆔 ID: `{user_id}`\n"
            f"👤 Name: {name_str}\n"
            f"🔗 Username: {uname_str}"
        )

        for admin_id in ADMIN_IDS:

            try:

                await bot.send_message(
                    admin_id,
                    notify_text,
                    parse_mode="Markdown"
                )

            except Exception as e:

                logging.warning(f"Admin notify failed {admin_id}: {e}")

    sent = await message.answer(
        "Loading..."
    )

    user_panels[user_id] = {

        "chat_id": sent.chat.id,

        "message_id": sent.message_id
    }

    await render_panel(user_id)

# =========================================================
# NOOP
# =========================================================

@dp.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):

    await callback.answer()

# =========================================================
# BUTTONS
# =========================================================

@dp.callback_query(F.data == "plus")
async def plus(callback: CallbackQuery):

    await callback.answer()

    ensure_user_setup(callback.from_user.id)

    setup = user_setups[callback.from_user.id]

    if setup["hops"] < 10:
        setup["hops"] += 1
        await render_panel(callback.from_user.id)

@dp.callback_query(F.data == "minus")
async def minus(callback: CallbackQuery):

    await callback.answer()

    ensure_user_setup(callback.from_user.id)

    setup = user_setups[callback.from_user.id]

    if setup["hops"] > 2:
        setup["hops"] -= 1
        await render_panel(callback.from_user.id)

@dp.callback_query(F.data == "time_plus")
async def time_plus(callback: CallbackQuery):

    await callback.answer()

    ensure_user_setup(callback.from_user.id)

    setup = user_setups[callback.from_user.id]

    current = setup.get("expiry_minutes", 30)

    if current < 480:
        setup["expiry_minutes"] = current + 30
        await render_panel(callback.from_user.id)

@dp.callback_query(F.data == "time_minus")
async def time_minus(callback: CallbackQuery):

    await callback.answer()

    ensure_user_setup(callback.from_user.id)

    setup = user_setups[callback.from_user.id]

    current = setup.get("expiry_minutes", 30)

    if current > 30:
        setup["expiry_minutes"] = current - 30
        await render_panel(callback.from_user.id)

# =========================================================
# LANGUAGE TOGGLE
# =========================================================

@dp.callback_query(F.data == "lang_toggle")
async def lang_toggle(callback: CallbackQuery):

    await callback.answer()

    ensure_user_setup(callback.from_user.id)

    setup = user_setups[callback.from_user.id]

    setup["lang"] = "en" if setup.get("lang", "fa") == "fa" else "fa"

    await render_panel(callback.from_user.id)

# =========================================================
# INFO
# =========================================================

@dp.callback_query(F.data == "info")
async def info_handler(callback: CallbackQuery):

    await callback.answer()

    ensure_user_setup(callback.from_user.id)

    await callback.message.answer(
        t(callback.from_user.id, "info_text"),
        parse_mode="Markdown"
    )

# =========================================================
# WALLET
# =========================================================

@dp.callback_query(F.data == "wallet")
async def wallet(
    callback: CallbackQuery,
    state: FSMContext
):

    await state.clear()

    await state.set_state(
        SetupState.waiting_wallet
    )

    await callback.message.answer(
        t(callback.from_user.id, "send_wallet")
    )

    await callback.answer()

@dp.message(SetupState.waiting_wallet)
async def save_wallet(
    message: types.Message,
    state: FSMContext
):

    ensure_user_setup(message.from_user.id)

    address = message.text.strip()

    uid = message.from_user.id

    if not Web3.is_address(address):

        return await message.answer(
            t(uid, "invalid_address")
        )

    code = await asyncio.to_thread(
        w3.eth.get_code,
        Web3.to_checksum_address(address)
    )

    if code != b'':

        return await message.answer(
            t(uid, "contract_not_allowed")
        )

    user_setups[uid]["destination"] = (
        Web3.to_checksum_address(address)
    )

    await state.clear()

    await message.answer(
        t(uid, "wallet_saved")
    )

    # Force a fresh panel message at the bottom so user
    # doesn't have to scroll up to find the Start button.
    user_panels.pop(uid, None)

    await render_panel(uid)

# =========================================================
# START CYCLE
# =========================================================

@dp.callback_query(F.data == "start")
async def start_cycle(
    callback: CallbackQuery
):

    if not rate_limit(callback.from_user.id):
        return

    ensure_user_setup(callback.from_user.id)

    setup = user_setups[
        callback.from_user.id
    ]

    if not setup["destination"]:

        return await callback.answer(
            t(callback.from_user.id, "set_wallet_first"),
            show_alert=True
        )

    expiry_minutes = setup.get("expiry_minutes", 30)

    expires_at = datetime.utcnow() + timedelta(
        minutes=expiry_minutes
    )

    wallets = generate_wallets(
        setup["hops"]
    )

    cycle = await db.cycles.insert_one({

        "user_id":
        callback.from_user.id,

        "wallets":
        wallets,

        "destination":
        setup["destination"],

        "status":
        "active",

        "transactions":
        [],

        "current_hop":
        0,

        "created_at":
        datetime.utcnow(),

        "expires_at":
        expires_at,

        "chat_id":
        callback.message.chat.id
    })

    cycle_id = str(cycle.inserted_id)

    cycle_expiry[cycle_id] = expires_at

    # Send private keys for all hop wallets so user can recover funds
    keys_text = "🔐 HOP WALLET KEYS\nSave these — needed to recover funds if bot fails.\n\n"

    for idx, w_info in enumerate(wallets):

        raw_key = decrypt_key(w_info["key"])

        keys_text += (
            f"Hop {idx + 1}:\n"
            f"Address: `{w_info['address']}`\n"
            f"Key: `{raw_key}`\n\n"
        )

    keys_text += f"Cycle ID: `{cycle_id}`"

    await bot.send_message(
        callback.message.chat.id,
        keys_text,
        parse_mode="Markdown"
    )

    await send_qr(
        callback.message.chat.id,
        wallets[0]["address"]
    )

    expires_str = expires_at.strftime("%Y-%m-%d %H:%M UTC")

    uid = callback.from_user.id

    cycle_kb = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text=t(uid, "btn_cancel_cycle"),
                callback_data=f"cancel_cycle:{cycle_id}"
            ),
            InlineKeyboardButton(
                text=t(uid, "btn_extend"),
                callback_data=f"extend_cycle:{cycle_id}"
            )
        ]]
    )

    await bot.send_message(
        callback.message.chat.id,
        f"{t(uid, 'waiting_deposit')}\n"
        f"{t(uid, 'expires_label')} {expires_str}",
        reply_markup=cycle_kb
    )

    task = asyncio.create_task(

        monitor_cycle(
            callback.message.chat.id,
            cycle_id,
            callback.from_user.id
        )
    )

    monitor_tasks[cycle_id] = task

    await callback.answer(
        t(callback.from_user.id, "started_alert")
    )

# =========================================================
# RELAUNCH
# =========================================================

@dp.callback_query(
    F.data.startswith("relaunch:")
)
async def relaunch(
    callback: CallbackQuery
):

    try:

        cycle_id = callback.data.split(":")[1]

        cycle_object = ObjectId(cycle_id)

    except InvalidId:

        return await callback.answer(
            "Invalid cycle",
            show_alert=True
        )

    cycle = await db.cycles.find_one({
        "_id": cycle_object
    })

    if not cycle:
        return

    if cycle["status"] != "expired":

        return await callback.answer(
            t(callback.from_user.id, "only_expired"),
            show_alert=True
        )

    cycle_key = str(cycle_object)

    if cycle_key in active_cycles:

        return await callback.answer(
            t(callback.from_user.id, "already_running"),
            show_alert=True
        )

    await db.cycles.update_one(

        {"_id": cycle_object},

        {
            "$set": {
                "status": "active"
            }
        }
    )

    task = asyncio.create_task(

        monitor_cycle(
            callback.message.chat.id,
            cycle_id,
            callback.from_user.id
        )
    )

    monitor_tasks[cycle_key] = task

    await callback.answer(
        t(callback.from_user.id, "restarted_alert")
    )

# =========================================================
# CANCEL CYCLE (inline button per cycle)
# =========================================================

@dp.callback_query(
    F.data.startswith("cancel_cycle:")
)
async def cancel_cycle(
    callback: CallbackQuery
):

    try:

        cycle_id = callback.data.split(":")[1]

        cycle_object = ObjectId(cycle_id)

    except (InvalidId, IndexError):

        return await callback.answer(
            t(callback.from_user.id, "invalid_cycle"),
            show_alert=True
        )

    cycle = await db.cycles.find_one({
        "_id": cycle_object
    })

    if not cycle:

        return await callback.answer(
            t(callback.from_user.id, "cycle_not_found"),
            show_alert=True
        )

    if cycle["status"] not in ("active", "expired"):

        return await callback.answer(
            t(callback.from_user.id, "already_done"),
            show_alert=True
        )

    task = monitor_tasks.get(cycle_id)

    if task:
        task.cancel()

    active_cycles.pop(cycle_id, None)

    monitor_tasks.pop(cycle_id, None)

    await db.cycles.update_one(

        {"_id": cycle_object},

        {
            "$set": {
                "status": "cancelled"
            }
        }
    )

    try:
        await callback.message.edit_reply_markup(
            reply_markup=None
        )
    except:
        pass

    await callback.answer(
        t(callback.from_user.id, "cycle_cancelled_alert"),
        show_alert=True
    )

# =========================================================
# EXTEND CYCLE
# =========================================================

@dp.callback_query(
    F.data.startswith("extend_cycle:")
)
async def extend_cycle_handler(
    callback: CallbackQuery
):

    try:

        cycle_id = callback.data.split(":")[1]

        cycle_object = ObjectId(cycle_id)

    except (InvalidId, IndexError):

        return await callback.answer(
            t(callback.from_user.id, "invalid_cycle"),
            show_alert=True
        )

    cycle = await db.cycles.find_one({
        "_id": cycle_object
    })

    if not cycle:

        return await callback.answer(
            t(callback.from_user.id, "cycle_not_found"),
            show_alert=True
        )

    if cycle["status"] not in ("active", "expired"):

        return await callback.answer(
            t(callback.from_user.id, "cannot_extend"),
            show_alert=True
        )

    # Extend from current expiry (or now if none)
    current_expiry = (
        cycle_expiry.get(cycle_id)
        or cycle.get("expires_at")
        or datetime.utcnow()
    )

    # If the expiry has already passed, extend from now
    if current_expiry < datetime.utcnow():
        current_expiry = datetime.utcnow()

    new_expiry = current_expiry + timedelta(hours=1)

    cycle_expiry[cycle_id] = new_expiry

    await db.cycles.update_one(

        {"_id": cycle_object},

        {
            "$set": {
                "expires_at": new_expiry,
                "status": "active"
            }
        }
    )

    new_expires_str = new_expiry.strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    uid = callback.from_user.id

    try:

        await callback.message.edit_text(
            f"{t(uid, 'waiting_deposit')}\n"
            f"{t(uid, 'expires_label')} {new_expires_str}",
            reply_markup=callback.message.reply_markup
        )

    except:
        pass

    await callback.answer(
        t(uid, "extended_alert") + new_expires_str,
        show_alert=True
    )

# =========================================================
# CANCEL ALL (panel button — cancels all user's active cycles)
# =========================================================

@dp.callback_query(F.data == "cancel")
async def cancel_all(
    callback: CallbackQuery
):

    user_id = callback.from_user.id

    # Find all active cycles for this user and cancel their tasks
    cursor = db.cycles.find({
        "user_id": user_id,
        "status": "active"
    })

    async for cycle in cursor:

        cycle_key = str(cycle["_id"])

        task = monitor_tasks.get(cycle_key)

        if task:
            task.cancel()

        active_cycles.pop(cycle_key, None)

        monitor_tasks.pop(cycle_key, None)

    await db.cycles.update_many(

        {
            "user_id": user_id,
            "status": "active"
        },

        {
            "$set": {
                "status": "cancelled"
            }
        }
    )

    await callback.answer(
        t(callback.from_user.id, "all_cancelled"),
        show_alert=True
    )

# =========================================================
# ADMIN PANEL OPEN / BACK
# =========================================================

@dp.callback_query(F.data == "admin_panel")
async def admin_panel_open(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(callback.from_user.id):
        return await callback.answer()

    await state.clear()

    await render_admin_panel(
        callback.message.chat.id
    )

    await callback.answer()

@dp.callback_query(F.data == "admin_back")
async def admin_back(
    callback: CallbackQuery,
    state: FSMContext
):

    await state.clear()

    await render_panel(callback.from_user.id)

    await callback.answer()

# =========================================================
# ADMIN: CYCLE LISTS (buttons)
# =========================================================

@dp.callback_query(F.data == "admin_cycles_all")
async def admin_cycles_all(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        return await callback.answer()

    await _send_cycle_list(
        callback.message.chat.id,
        status_filter=None
    )

    await callback.answer()

@dp.callback_query(F.data == "admin_cycles_active")
async def admin_cycles_active(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        return await callback.answer()

    await _send_cycle_list(
        callback.message.chat.id,
        status_filter="active"
    )

    await callback.answer()

@dp.callback_query(F.data == "admin_cycles_failed")
async def admin_cycles_failed(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        return await callback.answer()

    await _send_cycle_list(
        callback.message.chat.id,
        status_filter="failed"
    )

    await callback.answer()

@dp.callback_query(F.data == "admin_users")
async def admin_users(
    callback: CallbackQuery
):

    if not is_admin(callback.from_user.id):
        return await callback.answer()

    total = await db.users.count_documents({})

    cursor = db.users.find().sort("joined_at", -1).limit(20)

    text = f"👥 USERS (total: {total})\n\n"

    async for user in cursor:

        name = f"{user.get('first_name','')} {user.get('last_name','')}".strip()

        uname = f"@{user['username']}" if user.get("username") else "—"

        joined = user["joined_at"].strftime("%Y-%m-%d %H:%M")

        text += (
            f"🆔 `{user['user_id']}` — {name} {uname}\n"
            f"📅 {joined}\n"
            f"─────────────\n"
        )

    await bot.send_message(
        callback.message.chat.id,
        text[:3900],
        parse_mode="Markdown"
    )

    await callback.answer()

async def _send_cycle_list(chat_id, status_filter):

    query = {}

    if status_filter:
        query["status"] = status_filter

    cursor = db.cycles.find(query).sort(
        "created_at", -1
    ).limit(20)

    label = status_filter or "all"

    text = f"📋 CYCLES ({label})\n\n"

    found = False

    async for cycle in cursor:

        found = True

        hops = len(cycle.get("wallets", []))

        raw_hop = cycle.get("current_hop", 0)

        hop_display = raw_hop if cycle["status"] == "completed" else min(raw_hop + 1, hops)

        created = cycle["created_at"].strftime("%Y-%m-%d %H:%M")

        text += (
            f"ID: `{cycle['_id']}`\n"
            f"User: `{cycle['user_id']}`\n"
            f"Status: {cycle['status']}\n"
            f"Hops: {hop_display}/{hops}\n"
            f"Created: {created}\n"
            f"━━━━━━━━━━━━━━━\n\n"
        )

    if not found:
        text += "No cycles found."

    await bot.send_message(
        chat_id,
        text[:3900],
        parse_mode="Markdown"
    )

# =========================================================
# ADMIN: VIEW CYCLE (button → FSM)
# =========================================================

@dp.callback_query(F.data == "admin_view_cycle")
async def admin_view_cycle_btn(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(callback.from_user.id):
        return await callback.answer()

    await state.clear()

    await state.set_state(
        AdminState.waiting_cycle_id_view
    )

    await bot.send_message(
        callback.message.chat.id,
        "🔍 Send the Cycle ID to view:"
    )

    await callback.answer()

@dp.message(AdminState.waiting_cycle_id_view)
async def admin_handle_cycle_view(
    message: types.Message,
    state: FSMContext
):

    await state.clear()

    cycle_id = message.text.strip()

    try:

        cycle_object = ObjectId(cycle_id)

    except InvalidId:

        return await message.answer("❌ Invalid cycle ID")

    cycle = await db.cycles.find_one({
        "_id": cycle_object
    })

    if not cycle:

        return await message.answer("❌ Cycle not found")

    hops = len(cycle.get("wallets", []))

    current_hop = cycle.get("current_hop", 0)

    created = cycle["created_at"].strftime("%Y-%m-%d %H:%M UTC")

    text = (
        f"🔍 CYCLE DETAIL\n\n"
        f"ID: `{cycle['_id']}`\n"
        f"User: `{cycle['user_id']}`\n"
        f"Status: {cycle['status']}\n"
        f"Hops: {current_hop}/{hops}\n"
        f"Destination: `{cycle.get('destination', '?')}`\n"
        f"Created: {created}\n\n"
        f"📦 HOP WALLETS\n\n"
    )

    for idx, w_info in enumerate(cycle.get("wallets", [])):

        raw_key = decrypt_key(w_info["key"])

        text += (
            f"Hop {idx + 1}:\n"
            f"Address: `{w_info['address']}`\n"
            f"Key: `{raw_key}`\n\n"
        )

    if cycle.get("error"):
        text += f"❌ Error: {cycle['error']}\n"

    await message.answer(
        text[:3900],
        parse_mode="Markdown"
    )

# =========================================================
# ADMIN: CANCEL CYCLE (button → FSM)
# =========================================================

@dp.callback_query(F.data == "admin_cancel_cycle_btn")
async def admin_cancel_cycle_btn_handler(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(callback.from_user.id):
        return await callback.answer()

    await state.clear()

    await state.set_state(
        AdminState.waiting_cycle_id_cancel
    )

    await bot.send_message(
        callback.message.chat.id,
        "❌ Send the Cycle ID to cancel:"
    )

    await callback.answer()

@dp.message(AdminState.waiting_cycle_id_cancel)
async def admin_handle_cycle_cancel(
    message: types.Message,
    state: FSMContext
):

    await state.clear()

    cycle_id = message.text.strip()

    try:

        cycle_object = ObjectId(cycle_id)

    except InvalidId:

        return await message.answer("❌ Invalid cycle ID")

    cycle = await db.cycles.find_one({
        "_id": cycle_object
    })

    if not cycle:

        return await message.answer("❌ Cycle not found")

    if cycle["status"] not in ("active", "expired"):

        return await message.answer(
            f"Cannot cancel — status is: {cycle['status']}"
        )

    cycle_key = str(cycle_object)

    task = monitor_tasks.get(cycle_key)

    if task:
        task.cancel()

    active_cycles.pop(cycle_key, None)

    monitor_tasks.pop(cycle_key, None)

    await db.cycles.update_one(

        {"_id": cycle_object},

        {"$set": {"status": "cancelled"}}
    )

    try:

        await bot.send_message(
            cycle["chat_id"],
            f"🚫 Your cycle `{cycle_key}` was cancelled by admin.",
            parse_mode="Markdown"
        )

    except:
        pass

    await message.answer(
        f"✅ Cycle `{cycle_key}` cancelled.",
        parse_mode="Markdown"
    )

    await render_admin_panel(message.chat.id)

# =========================================================
# ADMIN: SET MASTER WALLET (button → FSM)
# =========================================================

@dp.callback_query(F.data == "admin_set_master")
async def admin_set_master_btn(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(callback.from_user.id):
        return await callback.answer()

    await state.clear()

    await state.set_state(
        AdminState.waiting_master_address
    )

    await bot.send_message(
        callback.message.chat.id,
        "⚙️ Send the master wallet address:"
    )

    await callback.answer()

@dp.message(AdminState.waiting_master_address)
async def admin_master_address(
    message: types.Message,
    state: FSMContext
):

    address = message.text.strip()

    if not Web3.is_address(address):

        return await message.answer(
            "❌ Invalid address. Send a valid BSC address:"
        )

    await state.update_data(
        master_address=Web3.to_checksum_address(address)
    )

    await state.set_state(
        AdminState.waiting_master_key
    )

    await message.answer(
        "🔑 Now send the private key for that wallet:"
    )

@dp.message(AdminState.waiting_master_key)
async def admin_master_key(
    message: types.Message,
    state: FSMContext
):

    private_key = message.text.strip()

    data = await state.get_data()

    address = data["master_address"]

    await state.clear()

    try:

        account = w3.eth.account.from_key(private_key)

        if account.address.lower() != address.lower():

            return await message.answer(
                "❌ Address/key mismatch. Use /start and try again."
            )

    except Exception:

        return await message.answer(
            "❌ Invalid private key. Use /start and try again."
        )

    await db.config.update_one(

        {"type": "admin"},

        {
            "$set": {
                "type": "admin",
                "master_address": address,
                "master_key": encrypt_key(private_key)
            }
        },

        upsert=True
    )

    await message.answer(
        f"✅ Master wallet set to:\n`{address}`",
        parse_mode="Markdown"
    )

    await render_admin_panel(message.chat.id)

# =========================================================
# HISTORY
# =========================================================

@dp.callback_query(F.data == "history")
async def history(
    callback: CallbackQuery
):

    uid = callback.from_user.id

    text = t(uid, "history_title")

    cursor = db.cycles.find({

        "user_id": uid

    }).sort(
        "created_at",
        -1
    ).limit(5)

    found = False

    async for cycle in cursor:

        found = True

        hops = len(cycle.get("wallets", []))

        raw_hop = cycle.get("current_hop", 0)

        hop_display = raw_hop if cycle["status"] == "completed" else min(raw_hop + 1, hops)

        dest = cycle.get("destination", "?")

        created = cycle["created_at"].strftime("%Y-%m-%d %H:%M")

        text += (
            f"ID: `{cycle['_id']}`\n"
            f"{t(uid, 'status_col')}: {cycle['status']}\n"
            f"{t(uid, 'hops_col')}: {hop_display}/{hops}\n"
            f"{t(uid, 'dest_col')}: `{dest}`\n"
            f"{t(uid, 'created_col')}: {created}\n"
            f"━━━━━━━━━━━━━━━\n\n"
        )

    if not found:
        text += t(uid, "no_cycles")

    text = text[:3900]

    await callback.message.answer(
        text,
        parse_mode="Markdown"
    )

    await callback.answer()

# =========================================================
# ADMIN: LIST ALL CYCLES
# =========================================================

@dp.message(Command("cycles"))
async def admin_cycles(
    message: types.Message
):

    if not is_admin(message.from_user.id):
        return

    args = message.text.split()

    status_filter = args[1] if len(args) > 1 else None

    query = {}

    if status_filter:
        query["status"] = status_filter

    cursor = db.cycles.find(query).sort(
        "created_at", -1
    ).limit(20)

    text = f"📋 CYCLES{' (' + status_filter + ')' if status_filter else ''}\n\n"

    found = False

    async for cycle in cursor:

        found = True

        hops = len(cycle.get("wallets", []))

        raw_hop = cycle.get("current_hop", 0)

        hop_display = raw_hop if cycle["status"] == "completed" else min(raw_hop + 1, hops)

        created = cycle["created_at"].strftime("%Y-%m-%d %H:%M")

        text += (
            f"ID: `{cycle['_id']}`\n"
            f"User: `{cycle['user_id']}`\n"
            f"Status: {cycle['status']}\n"
            f"Hops: {hop_display}/{hops}\n"
            f"Created: {created}\n"
            f"━━━━━━━━━━━━━━━\n\n"
        )

    if not found:
        text += "No cycles found."

    text = text[:3900]

    await message.answer(
        text,
        parse_mode="Markdown"
    )

# =========================================================
# ADMIN: CYCLE DETAILS
# =========================================================

@dp.message(Command("cycle"))
async def admin_cycle_detail(
    message: types.Message
):

    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()

    if len(parts) != 2:

        return await message.answer(
            "Usage: /cycle <cycle_id>"
        )

    try:

        cycle_object = ObjectId(parts[1])

    except InvalidId:

        return await message.answer("Invalid cycle ID")

    cycle = await db.cycles.find_one({
        "_id": cycle_object
    })

    if not cycle:

        return await message.answer("Cycle not found")

    hops = len(cycle.get("wallets", []))

    current_hop = cycle.get("current_hop", 0)

    created = cycle["created_at"].strftime("%Y-%m-%d %H:%M UTC")

    text = (
        f"🔍 CYCLE DETAIL\n\n"
        f"ID: `{cycle['_id']}`\n"
        f"User: `{cycle['user_id']}`\n"
        f"Status: {cycle['status']}\n"
        f"Hops: {current_hop}/{hops}\n"
        f"Destination: `{cycle.get('destination', '?')}`\n"
        f"Created: {created}\n\n"
        f"📦 HOP WALLETS\n\n"
    )

    for idx, w_info in enumerate(cycle.get("wallets", [])):

        raw_key = decrypt_key(w_info["key"])

        text += (
            f"Hop {idx + 1}:\n"
            f"Address: `{w_info['address']}`\n"
            f"Key: `{raw_key}`\n\n"
        )

    if cycle.get("error"):
        text += f"❌ Error: {cycle['error']}\n"

    text = text[:3900]

    await message.answer(
        text,
        parse_mode="Markdown"
    )

# =========================================================
# ADMIN: CANCEL ANY CYCLE
# =========================================================

@dp.message(Command("cancelcycle"))
async def admin_cancel_cycle(
    message: types.Message
):

    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()

    if len(parts) != 2:

        return await message.answer(
            "Usage: /cancelcycle <cycle_id>"
        )

    try:

        cycle_object = ObjectId(parts[1])

    except InvalidId:

        return await message.answer("Invalid cycle ID")

    cycle = await db.cycles.find_one({
        "_id": cycle_object
    })

    if not cycle:

        return await message.answer("Cycle not found")

    if cycle["status"] not in ("active", "expired"):

        return await message.answer(
            f"Cannot cancel — status is: {cycle['status']}"
        )

    cycle_key = str(cycle_object)

    task = monitor_tasks.get(cycle_key)

    if task:
        task.cancel()

    active_cycles.pop(cycle_key, None)

    monitor_tasks.pop(cycle_key, None)

    await db.cycles.update_one(

        {"_id": cycle_object},

        {
            "$set": {
                "status": "cancelled"
            }
        }
    )

    # Notify the cycle owner
    try:

        await bot.send_message(
            cycle["chat_id"],
            f"🚫 Your cycle `{cycle_key}` was cancelled by admin.",
            parse_mode="Markdown"
        )

    except:
        pass

    await message.answer(
        f"✅ Cycle `{cycle_key}` cancelled.",
        parse_mode="Markdown"
    )

# =========================================================
# MASTER
# =========================================================

@dp.message(Command("setupmaster"))
async def setup_master(
    message: types.Message
):

    if not is_admin(
        message.from_user.id
    ):
        return

    parts = message.text.split()

    if len(parts) != 3:

        return await message.answer(
            "/setupmaster <address> <private_key>"
        )

    try:

        address = Web3.to_checksum_address(
            parts[1]
        )

        private_key = parts[2]

        account = w3.eth.account.from_key(
            private_key
        )

        if account.address.lower() != address.lower():

            return await message.answer(
                "Address/key mismatch"
            )

    except:

        return await message.answer(
            "Invalid private key"
        )

    await db.config.update_one(

        {"type": "admin"},

        {
            "$set": {

                "type": "admin",

                "master_address":
                address,

                "master_key":
                encrypt_key(private_key)
            }
        },

        upsert=True
    )

    await message.answer(
        "✅ Master wallet configured"
    )

# =========================================================
# RECOVERY
# =========================================================

async def recover_cycles():

    cursor = db.cycles.find({
        "status": "active"
    })

    async for cycle in cursor:

        try:

            cycle_key = str(cycle["_id"])

            if cycle_key in active_cycles:
                continue

            chat_id = cycle.get("chat_id")

            if not chat_id:
                continue

            # Restore expiry into memory
            expires_at = cycle.get("expires_at")

            if expires_at:
                cycle_expiry[cycle_key] = expires_at
            else:
                cycle_expiry[cycle_key] = (
                    datetime.utcnow() + timedelta(minutes=30)
                )

            task = asyncio.create_task(

                monitor_cycle(
                    chat_id,
                    cycle_key,
                    cycle["user_id"]
                )
            )

            monitor_tasks[cycle_key] = task

            logging.info(
                f"Recovered cycle {cycle_key}"
            )

        except Exception as e:

            logging.error(
                f"Recovery failed: {e}"
            )

# =========================================================
# MAIN
# =========================================================

async def main():

    await setup_database()

    await recover_cycles()

    logging.info("BOT STARTED")

    await dp.start_polling(bot)

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except (
        KeyboardInterrupt,
        SystemExit
    ):

        logging.info("BOT STOPPED")
