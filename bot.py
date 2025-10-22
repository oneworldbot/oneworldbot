#!/usr/bin/env python3
"""OneWorldBot - minimal implementation

Features implemented:
- /start (supports referral via start param)
- /balance
- /tasks (list and claim simple tasks)
- /referral (shows referral code/link)
- /dice (send dice and reward by value)
- /quiz (simple quiz with buttons)

Token is read from the TELEGRAM_TOKEN environment variable. If not set,
the bot will attempt to read `token.txt` (not recommended).

Storage: SQLite database `oneworld.db` in the workspace.
"""

import os
import logging
import sqlite3
import random
import string
from functools import wraps
from decimal import Decimal

from dotenv import load_dotenv
from deep_translator import GoogleTranslator
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
)
from threading import Thread, Event
import time
import web3_utils

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "oneworld.db")
# Economics
# Total supply: 1,000,000,000,000 OWC (one trillion)
TOTAL_SUPPLY = 1_000_000_000_000
# Initial airdrop per new user (adjustable)
INITIAL_AIRDROP = 1000



def get_token():
    token = os.environ.get("TELEGRAM_TOKEN")
    if token:
        return token.strip()
    # fallback to token.txt (workspace convenience only)
    fallback = os.path.join(os.path.dirname(__file__), "token.txt")
    if os.path.exists(fallback):
        with open(fallback, "r") as f:
            return f.read().strip()
    return None


def with_db(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        try:
            result = func(conn, *args, **kwargs)
            conn.commit()
            return result
        finally:
            conn.close()

    return wrapper


@with_db
def init_db(conn):
    cur = conn.cursor()
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        user_id INTEGER UNIQUE,
        username TEXT,
        language TEXT,
        balance INTEGER DEFAULT 0,
        ref_code TEXT UNIQUE,
        referred_by INTEGER
    )
    """
    )
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS user_tasks (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        task_name TEXT,
        UNIQUE(user_id, task_name)
    )
    """
    )
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        amount INTEGER,
        reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    )
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS storage (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        capacity INTEGER DEFAULT 0
    )
    """
    )
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        tier TEXT,
        expires_at TIMESTAMP
    )
    """
    )
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS presale_orders (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        amount INTEGER,
        cost INTEGER,
        status TEXT DEFAULT 'booked',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    )
    # ensure treasury user (user_id = 0) exists with TOTAL_SUPPLY
    cur.execute("SELECT id FROM users WHERE user_id = 0")
    if not cur.fetchone():
        cur.execute("INSERT INTO users (user_id, username, language, balance, ref_code) VALUES (?, ?, ?, ?, ?)", (0, 'treasury', 'en', TOTAL_SUPPLY, None))


def translate(text: str, target_lang: str) -> str:
    if not target_lang or target_lang.startswith("en"):
        return text
    try:
        return GoogleTranslator(source='auto', target=target_lang[:2]).translate(text)
    except Exception:
        return text


@with_db
def ensure_user(conn, user):
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE user_id = ?", (user.id,))
    row = cur.fetchone()
    if row:
        return
    # generate ref code
    code = _generate_ref_code(conn)
    cur.execute(
        "INSERT INTO users (user_id, username, language, balance, ref_code) VALUES (?, ?, ?, ?, ?)",
        (user.id, user.username or "", user.language_code or "en", 0, code),
    )
    # airdrop from treasury if available
    try:
        cur.execute("SELECT balance FROM users WHERE user_id = 0")
        t = cur.fetchone()
        if t and t[0] >= INITIAL_AIRDROP:
            cur.execute("UPDATE users SET balance = balance - ? WHERE user_id = 0", (INITIAL_AIRDROP,))
            cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (INITIAL_AIRDROP, user.id))
            cur.execute("INSERT INTO transactions (user_id, amount, reason) VALUES (?, ?, ?)", (user.id, INITIAL_AIRDROP, 'airdrop'))
            cur.execute("INSERT INTO transactions (user_id, amount, reason) VALUES (?, ?, ?)", (0, -INITIAL_AIRDROP, 'airdrop_out'))
    except Exception:
        pass


def _generate_ref_code(conn):
    cur = conn.cursor()
    while True:
        code = "".join(random.choices(string.ascii_letters + string.digits, k=6))
        cur.execute("SELECT id FROM users WHERE ref_code = ?", (code,))
        if not cur.fetchone():
            return code


@with_db
def add_balance(conn, user_id: int, amount: int):
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    cur.execute("INSERT INTO transactions (user_id, amount, reason) VALUES (?, ?, ?)", (user_id, amount, 'adjust'))


@with_db
def get_balance(conn, user_id: int) -> int:
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else 0


@with_db
def get_storage_capacity(conn, user_id: int) -> int:
    cur = conn.cursor()
    cur.execute("SELECT capacity FROM storage WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else 0


@with_db
def get_treasury_and_circulating(conn):
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id = 0")
    t = cur.fetchone()
    treasury = t[0] if t else 0
    cur.execute("SELECT SUM(balance) FROM users WHERE user_id != 0")
    s = cur.fetchone()
    circulating = s[0] if s and s[0] else 0
    return treasury, circulating


def supply_cmd(update: Update, context: CallbackContext):
    treasury, circulating = get_treasury_and_circulating()
    text = f"Total supply: {TOTAL_SUPPLY}\nTreasury: {treasury}\nCirculating: {circulating}"
    update.message.reply_text(translate(text, update.effective_user.language_code or "en"))


@with_db
def add_storage(conn, user_id: int, capacity: int):
    cur = conn.cursor()
    cur.execute("SELECT id FROM storage WHERE user_id = ?", (user_id,))
    if cur.fetchone():
        cur.execute("UPDATE storage SET capacity = capacity + ? WHERE user_id = ?", (capacity, user_id))
    else:
        cur.execute("INSERT INTO storage (user_id, capacity) VALUES (?, ?)", (user_id, capacity))
    cur.execute("INSERT INTO transactions (user_id, amount, reason) VALUES (?, ?, ?)", (user_id, -capacity * 1, 'buy_storage'))


@with_db
def record_transaction(conn, user_id: int, amount: int, reason: str):
    cur = conn.cursor()
    cur.execute("INSERT INTO transactions (user_id, amount, reason) VALUES (?, ?, ?)", (user_id, amount, reason))


@with_db
def pop_pending_deposits(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, reason FROM transactions WHERE reason LIKE 'deposit_pending:%'")
    rows = cur.fetchall()
    return rows


@with_db
def mark_deposit_processed(conn, tx_hash: str, credited_amount: int, user_id: int):
    cur = conn.cursor()
    cur.execute("INSERT INTO transactions (user_id, amount, reason) VALUES (?, ?, ?)", (user_id, credited_amount, f"deposit_confirmed:{tx_hash}"))
    cur.execute("DELETE FROM transactions WHERE reason = ?", (f"deposit_pending:{tx_hash}",))


def deposit_watcher(stop_event: Event, poll_interval: int = 10):
    """Background loop: look for deposit_pending transactions and verify them on-chain."""
    # initialize web3 if possible
    web3_ok = web3_utils.init_web3()
    if not web3_ok:
        logger.info("web3 not initialized; deposit_watcher disabled until env configured")
        return
    w3 = web3_utils.get_w3()
    treasury = (os.environ.get("TREASURY_ADDRESS") or "").lower()
    owc_per_bnb = int(os.environ.get("OWC_PER_BNB", "10000"))
    logger.info("deposit_watcher started")
    while not stop_event.is_set():
        try:
            rows = pop_pending_deposits()
            for r in rows:
                tid, user_id, reason = r
                # reason = deposit_pending:<tx_hash>
                if not reason.startswith("deposit_pending:"):
                    continue
                tx_hash = reason.split(":", 1)[1]
                try:
                    tx = w3.eth.get_transaction(tx_hash)
                except Exception:
                    # tx not found yet
                    continue
                # verify destination
                to_addr = tx.to.lower() if tx.to else ""
                if treasury and to_addr != treasury:
                    logger.info(f"TX {tx_hash} to {to_addr} not treasury; skipping")
                    continue
                # verify receipt (mined)
                try:
                    receipt = w3.eth.get_transaction_receipt(tx_hash)
                except Exception:
                    continue
                if receipt and getattr(receipt, 'status', 1) != 1:
                    logger.info(f"TX {tx_hash} failed in receipt")
                    continue
                # compute BNB amount
                value_wei = int(tx.value)
                bnb_amount = value_wei / 1e18
                credited = int(bnb_amount * owc_per_bnb)
                if credited <= 0:
                    logger.info(f"TX {tx_hash} has zero value; skipping")
                    # remove pending maybe? skip for now
                    continue
                # credit user
                add_balance(user_id, credited)
                mark_deposit_processed(tx_hash, credited, user_id)
                logger.info(f"Credited user {user_id} with {credited} OWC for tx {tx_hash}")
        except Exception:
            logger.exception("Error in deposit_watcher loop")
        time.sleep(poll_interval)


@with_db
def mark_task(conn, user_id: int, task_name: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO user_tasks (user_id, task_name) VALUES (?, ?)", (user_id, task_name))
        return True
    except sqlite3.IntegrityError:
        return False


def start(update: Update, context: CallbackContext):
    user = update.effective_user
    ensure_user(user)
    args = context.args
    welcome = (
        "Welcome to OneWorldBot! Earn OWC by completing tasks, playing games and referring friends."
    )
    # handle referral parameter: /start <code>
    if args:
        code = args[0]
        _handle_referral_claim(user.id, code)
        welcome = "Welcome! Referral applied when possible. " + welcome

    text = translate(welcome, user.language_code or "en")
    update.message.reply_text(text)


def _handle_referral_claim(new_user_id: int, ref_code: str):
    # attach referred_by and give small bonus to both
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE ref_code = ?", (ref_code,))
        row = cur.fetchone()
        if not row:
            return False
        referrer_user_id = row[0]
        # set referred_by for new user if not set
        cur.execute("SELECT referred_by FROM users WHERE user_id = ?", (new_user_id,))
        r = cur.fetchone()
        if r and r[0]:
            return False
        cur.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referrer_user_id, new_user_id))
        # give small bonus
        cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (50, referrer_user_id))
        cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (50, new_user_id))
        conn.commit()
        return True
    finally:
        conn.close()


def balance_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    bal = get_balance(user.id)
    text = f"Your balance: {bal} OWC"
    update.message.reply_text(translate(text, user.language_code or "en"))


def tasks_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    tasks = [
        ("join_channel", "Join the channel (+20 OWC)"),
        ("like_post", "Like a post (+10 OWC)"),
        ("comment_post", "Comment on a post (+15 OWC)"),
    ]
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"task:{key}")]
        for key, label in tasks
    ]
    # add a menu button
    buttons.append([InlineKeyboardButton("Main Menu", callback_data="menu:main")])
    update.message.reply_text(translate("Available tasks:", user.language_code or "en"), reply_markup=InlineKeyboardMarkup(buttons))


def menu_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    buttons = [
        [InlineKeyboardButton("Balance", callback_data="menu:balance")],
        [InlineKeyboardButton("Tasks", callback_data="menu:tasks")],
        [InlineKeyboardButton("Games", callback_data="menu:games")],
        [InlineKeyboardButton("Store", callback_data="menu:store")],
    ]
    update.message.reply_text(translate("Main Menu:", user.language_code or "en"), reply_markup=InlineKeyboardMarkup(buttons))


def slots_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    # simple slot machine: three wheels with symbols
    symbols = ['🍒', '🔔', '🍋', '⭐', '7️⃣']
    result = [random.choice(symbols) for _ in range(3)]
    text = "|" + "|".join(result) + "|"
    # determine reward
    reward = 0
    if result[0] == result[1] == result[2]:
        reward = 200
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        reward = 50
    else:
        reward = 0
    if reward > 0:
        add_balance(user.id, reward)
        text += f"\nYou won {reward} OWC!"
    else:
        text += "\nNo win, try again."
    update.message.reply_text(translate(text, user.language_code or "en"))


def roulette_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    # user can place bet like: /roulette 7 10  (number 0-36 and bet amount)
    args = context.args
    if len(args) < 2:
        update.message.reply_text(translate("Usage: /roulette <number 0-36> <bet_amount>", user.language_code or "en"))
        return
    try:
        number = int(args[0])
        bet = int(args[1])
    except ValueError:
        update.message.reply_text(translate("Invalid number or bet.", user.language_code or "en"))
        return
    bal = get_balance(user.id)
    if bet <= 0 or bal < bet:
        update.message.reply_text(translate("Insufficient balance for that bet.", user.language_code or "en"))
        return
    # spin
    spin = random.randint(0, 36)
    if spin == number:
        payout = bet * 35
        add_balance(user.id, payout)
        update.message.reply_text(translate(f"Roulette: {spin}. You hit! Payout: {payout} OWC", user.language_code or "en"))
    else:
        add_balance(user.id, -bet)
        update.message.reply_text(translate(f"Roulette: {spin}. You lost {bet} OWC.", user.language_code or "en"))


def referral_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT ref_code FROM users WHERE user_id = ?", (user.id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        update.message.reply_text(translate("No referral code found.", user.language_code or "en"))
        return
    ref_code = row[0]
    try:
        bot_username = context.bot.get_me().username
    except Exception:
        bot_username = "<your_bot_username>"
    link = f"https://t.me/{bot_username}?start={ref_code}"
    text = f"Your referral code: {ref_code}\nShare this link: {link}"
    update.message.reply_text(translate(text, user.language_code or "en"))


def deposit_cmd(update: Update, context: CallbackContext):
    # show treasury/deposit instructions
    deposit_address = os.environ.get("TREASURY_ADDRESS") or "(set TREASURY_ADDRESS in .env)"
    text = (
        "To deposit BNB for purchasing OWC, send BNB to the project treasury address:\n"
        f"{deposit_address}\n\n"
        "After sending, use /deposit_confirm <tx_hash> to notify the bot."
    )
    update.message.reply_text(translate(text, update.effective_user.language_code or "en"))


@with_db
def create_presale_order(conn, user_id: int, amount: int, cost: int):
    cur = conn.cursor()
    cur.execute("INSERT INTO presale_orders (user_id, amount, cost, status) VALUES (?, ?, ?, ?)", (user_id, amount, cost, 'booked'))
    return cur.lastrowid


def presale_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    # options: book packages
    items = [
        (10, "Book 10 OWC (cost 10 USD)"),
        (50, "Book 50 OWC (cost 50 USD)"),
        (100, "Book 100 OWC (cost 100 USD)"),
    ]
    buttons = [[InlineKeyboardButton(label, callback_data=f"presale:{amt}")] for amt, label in items]
    update.message.reply_text(translate("Presale - choose package:", user.language_code or "en"), reply_markup=InlineKeyboardMarkup(buttons))


def deposit_confirm_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    args = context.args
    if not args:
        update.message.reply_text(translate("Usage: /deposit_confirm <tx_hash>", user.language_code or "en"))
        return
    tx = args[0]
    # record a pending transaction for manual verification
    record_transaction(user.id, 0, f"deposit_pending:{tx}")
    update.message.reply_text(translate("Deposit recorded. Admin will verify and credit your account.", user.language_code or "en"))


def _is_admin(user_id: int) -> bool:
    admins = os.environ.get("ADMIN_IDS", "").split(",")
    try:
        return str(user_id) in [a.strip() for a in admins if a.strip()]
    except Exception:
        return False


def admin_list_orders_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    if not _is_admin(user.id):
        update.message.reply_text("Not authorized")
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, amount, cost, status FROM presale_orders ORDER BY created_at DESC LIMIT 50")
    rows = cur.fetchall()
    conn.close()
    text = "Presale orders:\n" + "\n".join([f"#{r[0]} user:{r[1]} amt:{r[2]} cost:{r[3]} status:{r[4]}" for r in rows])
    update.message.reply_text(text)


def admin_release_order_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    if not _is_admin(user.id):
        update.message.reply_text("Not authorized")
        return
    args = context.args
    if not args:
        update.message.reply_text("Usage: /admin_release_order <order_id>")
        return
    oid = int(args[0])
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id, amount, status FROM presale_orders WHERE id = ?", (oid,))
    row = cur.fetchone()
    if not row:
        update.message.reply_text("Order not found")
        conn.close()
        return
    if row[2] != 'booked':
        update.message.reply_text("Order not in booked state")
        conn.close()
        return
    buyer_id = row[0]
    amt = row[1]
    # credit buyer internal balance (we assume 1 USD per OWC and caller verified receipt)
    add_balance(buyer_id, amt)
    cur.execute("UPDATE presale_orders SET status = 'released' WHERE id = ?", (oid,))
    conn.commit()
    conn.close()
    update.message.reply_text(f"Order {oid} released and credited {amt} OWC")




def callback_query(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data or ""
    user = query.from_user
    # presale callbacks
    if data.startswith("presale:"):
        amt = int(data.split(":", 1)[1])
        # price: 1 USD per OWC during presale (example)
        cost = amt * 1
        order_id = create_presale_order(user.id, amt, cost)
        query.answer(translate(f"Presale booked: {amt} OWC (order #{order_id}). Send BNB to treasury and confirm.", user.language_code or "en"))
        query.edit_message_text(translate(f"You booked {amt} OWC. Order id: {order_id}.\nSend BNB to treasury and use /deposit_confirm <tx_hash> to confirm.", user.language_code or "en"))
        return
    if data.startswith("task:"):
        task = data.split(":", 1)[1]
        claimed = mark_task(user.id, task)
        if not claimed:
            query.answer(translate("You already claimed this task.", user.language_code or "en"))
            return
        # award amounts per task
        reward_map = {"join_channel": 20, "like_post": 10, "comment_post": 15}
        amount = reward_map.get(task, 5)
        add_balance(user.id, amount)
        query.answer(translate(f"Task claimed! +{amount} OWC", user.language_code or "en"))
        query.edit_message_text(translate(f"Task '{task}' claimed. You got +{amount} OWC.", user.language_code or "en"))
    elif data.startswith("quiz:"):
        payload = data.split(":", 2)
        # payload: quiz:question_id:option
        if len(payload) >= 3:
            qid = payload[1]
            opt = payload[2]
            # very simple hardcoded quiz
            correct = "b"
            if opt == correct:
                add_balance(user.id, 30)
                query.answer(translate("Correct! +30 OWC", user.language_code or "en"))
                query.edit_message_text(translate("Correct! You earned 30 OWC.", user.language_code or "en"))
            else:
                query.answer(translate("Wrong answer.", user.language_code or "en"))
                query.edit_message_text(translate("Wrong answer. Try again later.", user.language_code or "en"))


def dice_cmd(update: Update, context: CallbackContext):
    msg = update.message.reply_dice()
    # value is available in msg.dice.value
    value = getattr(msg.dice, "value", random.randint(1, 6))
    reward = 0
    if value >= 5:
        reward = 25
    elif value >= 3:
        reward = 10
    else:
        reward = 5
    add_balance(update.effective_user.id, reward)
    update.message.reply_text(translate(f"You rolled {value}. You got +{reward} OWC.", update.effective_user.language_code or "en"))


def quiz_cmd(update: Update, context: CallbackContext):
    # simple quiz
    question = "What is 2 + 2?"
    buttons = [
        [InlineKeyboardButton("3", callback_data="quiz:1:a")],
        [InlineKeyboardButton("4", callback_data="quiz:1:b")],
        [InlineKeyboardButton("5", callback_data="quiz:1:c")],
    ]
    update.message.reply_text(translate(question, update.effective_user.language_code or "en"), reply_markup=InlineKeyboardMarkup(buttons))


def store_cmd(update: Update, context: CallbackContext):
    # show store items: storage, subscription tiers
    items = [
        ("storage_100", "Buy 100 storage (cost 100 OWC)"),
        ("sub_basic", "Subscribe Basic (30 days) - cost 500 OWC"),
        ("sub_premium", "Subscribe Premium (30 days) - cost 1200 OWC"),
    ]
    buttons = [[InlineKeyboardButton(label, callback_data=f"buy:{key}")] for key, label in items]
    update.message.reply_text(translate("Store:", update.effective_user.language_code or "en"), reply_markup=InlineKeyboardMarkup(buttons))


def buy_storage_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    # quick buy example: /buy_storage 100
    args = context.args
    if not args:
        update.message.reply_text(translate("Usage: /buy_storage <amount>", user.language_code or "en"))
        return
    try:
        amt = int(args[0])
    except ValueError:
        update.message.reply_text(translate("Amount must be a number.", user.language_code or "en"))
        return
    price_per_unit = 1  # 1 OWC per storage unit for example
    cost = amt * price_per_unit
    bal = get_balance(user.id)
    if bal < cost:
        update.message.reply_text(translate("Insufficient balance.", user.language_code or "en"))
        return
    add_balance(user.id, -cost)
    add_storage(user.id, amt)
    update.message.reply_text(translate(f"Purchased {amt} storage for {cost} OWC.", user.language_code or "en"))


def subscribe_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    args = context.args
    if not args:
        update.message.reply_text(translate("Usage: /subscribe <basic|premium>", user.language_code or "en"))
        return
    tier = args[0].lower()
    cost_map = {"basic": 500, "premium": 1200}
    if tier not in cost_map:
        update.message.reply_text(translate("Unknown tier.", user.language_code or "en"))
        return
    cost = cost_map[tier]
    bal = get_balance(user.id)
    if bal < cost:
        update.message.reply_text(translate("Insufficient balance.", user.language_code or "en"))
        return
    add_balance(user.id, -cost)
    # naive subscription insert
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO subscriptions (user_id, tier, expires_at) VALUES (?, ?, datetime('now', '+30 days'))", (user.id, tier))
    conn.commit()
    conn.close()
    update.message.reply_text(translate(f"Subscribed to {tier} for 30 days.", user.language_code or "en"))


def share_cmd(update: Update, context: CallbackContext):
    # award for sharing (very basic)
    user = update.effective_user
    add_balance(user.id, 10)
    update.message.reply_text(translate("Thanks for sharing! You got +10 OWC.", user.language_code or "en"))


def convert_cmd(update: Update, context: CallbackContext):
    # convert OWC to currency at OWC_EXCHANGE_RATE
    rate = int(os.environ.get("OWC_EXCHANGE_RATE", "100"))
    bal = get_balance(update.effective_user.id)
    if bal <= 0:
        update.message.reply_text(translate("No balance to convert.", update.effective_user.language_code or "en"))
        return
    value = Decimal(bal) / Decimal(rate)
    update.message.reply_text(translate(f"{bal} OWC = {value} units at rate {rate}.", update.effective_user.language_code or "en"))


def main():
    token = get_token()
    if not token:
        print("Error: TELEGRAM_TOKEN not set and token.txt missing. Set TELEGRAM_TOKEN environment variable.")
        return

    init_db()
    # initialize web3 early so we know whether deposit watcher can run
    try:
        web3_ok = web3_utils.init_web3()
        logger.info(f"web3 initialized: {web3_ok}")
    except Exception:
        logger.exception("Failed to initialize web3 at startup")
    updater = Updater(token, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("balance", balance_cmd))
    dp.add_handler(CommandHandler("tasks", tasks_cmd))
    dp.add_handler(CommandHandler("referral", referral_cmd))
    dp.add_handler(CommandHandler("dice", dice_cmd))
    dp.add_handler(CommandHandler("quiz", quiz_cmd))
    dp.add_handler(CommandHandler("store", store_cmd))
    dp.add_handler(CommandHandler("buy_storage", buy_storage_cmd))
    dp.add_handler(CommandHandler("subscribe", subscribe_cmd))
    dp.add_handler(CommandHandler("share", share_cmd))
    dp.add_handler(CommandHandler("convert", convert_cmd))
    dp.add_handler(CommandHandler("supply", supply_cmd))
    dp.add_handler(CommandHandler("deposit", deposit_cmd))
    dp.add_handler(CommandHandler("presale", presale_cmd))
    dp.add_handler(CommandHandler("deposit_confirm", deposit_confirm_cmd))
    dp.add_handler(CommandHandler("admin_list_orders", admin_list_orders_cmd))
    dp.add_handler(CommandHandler("admin_release_order", admin_release_order_cmd))
    dp.add_handler(CallbackQueryHandler(callback_query))

    print("Starting OneWorldBot...")
    # start deposit watcher thread if web3 config present
    stop_event = Event()
    watcher_thread = Thread(target=deposit_watcher, args=(stop_event, 15), daemon=True)
    watcher_thread.start()

    updater.start_polling()
    try:
        updater.idle()
    finally:
        stop_event.set()
        watcher_thread.join(timeout=5)


if __name__ == "__main__":
    main()
