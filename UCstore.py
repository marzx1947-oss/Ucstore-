# UCstore.py — Full merged version with Free UC, Referral, Captcha, Admin flows
# NOTE: Replace TOKEN with your bot token before running.
# This file includes:
# - User registration with contact + captcha (random add/sub)
# - Referral system: invite link ?start=invite_<user_id> gives inviter +2 UC when invitee completes registration
# - Free UC system: daily roll, view collected UC, claim 60/325 UC by sending game ID (8-15 digits)
#   * Upon claim: user's collected UC is deducted (held). Order sent to admins for confirm/reject.
#   * User gets message "Order accepted, will be credited within 12 hours"
#   * Admin can confirm -> user receives "UC credited" and order marked confirmed.
#   * Admin can reject -> user's collected UC is refunded and user notified.
# - Admin command /process_pending to auto-confirm free_uc orders older than 12 hours.
# - Store/catalog features minimal included.
# IMPORTANT: This script does not run background workers. /process_pending must be run by admin (or scheduled externally).

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
import asyncio, random, datetime, json, os, traceback

# -------------------- CONFIG --------------------
TOKEN = "8524676045:AAHXHO6tYovrMAAGxAQZUi2Z-TGFBUPeMyY"  # <-- replace
ADMIN_IDS = [8436218638]  # admin IDs
USERS_FILE = "users.json"
ORDERS_FILE = "orders.json"
FREE_UC_CHANNEL = "@marzbon_chanel"
BOT_USERNAME = "Ucstoretjbot"  # without @

# Product items (store)
ITEMS = {
    1: {"name": "60 UC", "price": 10},
    2: {"name": "325 UC", "price": 50},
    3: {"name": "660 UC", "price": 100},
    4: {"name": "1800 UC", "price": 250},
    5: {"name": "3850 UC", "price": 500},
    6: {"name": "8100 UC", "price": 1000},
}

ADMIN_INFO = """UCstore — платформаи фурӯши UC ва хидматҳои рақамии бозӣ.
Админ: @MARZBON_TJ
"""

VISA_NUMBER = "4439200020432471"

# -------------------- Persistence helpers --------------------
def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_all():
    save_json(USERS_FILE, users_data)
    save_json(ORDERS_FILE, orders)

users_data = load_json(USERS_FILE, {})   # user_id -> dict
orders = load_json(ORDERS_FILE, [])      # list of orders

# runtime
user_carts = {}
user_wishlist = {}
broadcast_mode = {}

# -------------------- Utilities --------------------
def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def parse_start_payload(text):
    # text like "/start invite_12345" or "/start"
    if not text:
        return None
    parts = text.split()
    if len(parts) >= 2:
        payload = parts[1]
        return payload
    return None

# -------------------- Registration & Captcha --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # handle /start and potential invite payload
    if not update.message:
        return
    text = update.message.text or ""
    payload = parse_start_payload(text)
    if payload and payload.startswith("invite_"):
        try:
            inviter_id = int(payload.split("_",1)[1])
            context.user_data["invite_from"] = str(inviter_id)
        except:
            pass
    # prompt for contact if not registered
    user = update.message.from_user
    if str(user.id) in users_data:
        await update.message.reply_text(f"👋 Салом, {user.first_name}!")
        await show_main_menu(update.message.chat, str(user.id))
        return

    contact_button = KeyboardButton("📱 Ворид шудан бо рақам", request_contact=True)
    await update.message.reply_text(
        "🔐 Барои истифодаи бот рақами телефони худро фиристед:",
        reply_markup=ReplyKeyboardMarkup([[contact_button]], resize_keyboard=True, one_time_keyboard=True)
    )

async def get_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # When user shares contact
    if not update.message or not update.message.contact:
        return
    contact = update.message.contact
    user = update.message.from_user
    user_id = str(user.id)

    # create user record with pending captcha
    users_data[user_id] = {
        "id": user.id,
        "name": user.first_name or "",
        "username": user.username or "",
        "phone": contact.phone_number,
        "date": now_str(),
        "free_uc": 0,
        "last_daily_uc": None,
        "invite_from": context.user_data.get("invite_from"),
    }
    save_all()

    # start captcha challenge
    await send_captcha_challenge(update, context)

async def send_captcha_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # send random add/sub question, store expected answer in context.user_data
    a = random.randint(1, 20)
    b = random.randint(1, 20)
    op = random.choice(["+", "-"])
    if op == "-" and b > a:
        a, b = b, a
    question = f"{a} {op} {b}"
    answer = a + b if op == "+" else a - b
    context.user_data["captcha_answer"] = str(answer)
    # send prompt
    if update.message:
        target = update.message
    elif update.callback_query:
        target = update.callback_query.message
    else:
        return
    await target.reply_text(f"🔐 Ҳамоҳангӣ барои амният — ҷавоби саволро нависед:\n{question} = ?")

async def handle_captcha_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # expects captcha_answer in context.user_data
    if "captcha_answer" not in context.user_data:
        return False
    text = (update.message.text or "").strip()
    if text == context.user_data["captcha_answer"]:
        # success: complete registration and reward inviter if any
        user = update.message.from_user
        user_id = str(user.id)
        # clear captcha
        context.user_data.pop("captcha_answer", None)
        # reward inviter if exists and not rewarded before
        invite_from = users_data.get(user_id, {}).get("invite_from")
        if invite_from:
            inviter = users_data.get(str(invite_from))
            if inviter:
                inviter.setdefault("free_uc", 0)
                inviter["free_uc"] = inviter.get("free_uc", 0) + 2
                save_all()
                # notify inviter
                try:
                    await context.bot.send_message(int(invite_from),
                        f"🎉 Шумо 2 UC барои даъват кардани @{user.username or user.first_name} гирифтед!")
                except:
                    pass
        # welcome and show menu
        await update.message.reply_text("✅ Шумо бо муваффақият сабт шудед! Ҳоло менюро бинед.")
        await show_main_menu(update.message.chat, user_id)
        return True
    else:
        # wrong answer, resend a new question
        await update.message.reply_text("❌ Ҷавоб нодуруст. Боз кӯшиш кунед.")
        await send_captcha_challenge(update, context)
        return False

# -------------------- Main Menu --------------------
async def show_main_menu(chat, user_id):
    buttons = [
        ["🛍 Каталог", "❤️ Дилхоҳҳо"],
        ["🛒 Сабад", "💬 Профили админ"],
        ["ℹ Маълумот", "🎁 UC ройгон"]
    ]
    if int(user_id) in ADMIN_IDS:
        buttons.append(["👑 Панели админ"])
    buttons.append(["🔗 Даъвати дӯстон"])
    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)
    try:
        await chat.send_message("Менюи асосӣ:", reply_markup=reply_markup)
    except:
        pass

# -------------------- Catalog/Cart (minimal) --------------------
async def catalog_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message if update.message else update.callback_query.message
    buttons = []
    row = []
    for i, item in ITEMS.items():
        row.append(InlineKeyboardButton(f"{item['name']} — {item['price']} TJS", callback_data=f"select_{i}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("⬅️ Бозгашт", callback_data="back_main")])
    await target.reply_text("🛍 Каталог:", reply_markup=InlineKeyboardMarkup(buttons))

async def select_item_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    item_id = int(q.data.split("_")[1])
    item = ITEMS.get(item_id)
    if not item:
        await q.message.reply_text("Маҳсулот нест.")
        return
    buttons = [
        [InlineKeyboardButton("🛒 Илова ба сабад", callback_data=f"addcart_{item_id}")],
        [InlineKeyboardButton("⬅️ Бозгашт", callback_data="back_main")]
    ]
    await q.message.reply_text(f"{item['name']} — {item['price']} TJS", reply_markup=InlineKeyboardMarkup(buttons))

# -------------------- Free UC System --------------------
async def free_uc_menu_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    src = update.message if update.message else update.callback_query.message
    user = src.from_user
    user_id = str(user.id)
    if user_id not in users_data:
        await src.reply_text("⚠️ Аввал /start кунед ва бақайдгирӣ кунед.")
        return
    # check subscription (best-effort)
    subscribed = False
    try:
        member = await context.bot.get_chat_member(FREE_UC_CHANNEL, int(user_id))
        subscribed = member.status in ("member", "creator", "administrator")
    except Exception:
        subscribed = False
    if not subscribed:
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Обуна шудан", url=f"https://t.me/{FREE_UC_CHANNEL.strip('@')}")],
            [InlineKeyboardButton("🔄 Санҷиш", callback_data="check_sub_ucfree")]
        ])
        await src.reply_text("📢 Барои истифодаи UC ройгон ба канали мо обуна шавед:", reply_markup=btn)
        return
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Гирифтани UC-и рӯзона", callback_data="daily_uc")],
        [InlineKeyboardButton("📊 UC-и ҷамъшуда", callback_data="my_uc")],
        [InlineKeyboardButton("🎁 60 UC", callback_data="claim_60")],
        [InlineKeyboardButton("🎁 325 UC", callback_data="claim_325")],
        [InlineKeyboardButton("🔗 Даъвати дӯстон", callback_data="invite_link")]
    ])
    await src.reply_text("🎁 Менюи UC ройгон:", reply_markup=btn)

async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await free_uc_menu_entry(update, context)

async def daily_uc_roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    user_id = str(q.from_user.id)
    user = users_data.get(user_id)
    if not user:
        await q.message.reply_text("⚠️ Аввал /start кунед.")
        return
    now = datetime.datetime.now()
    last = user.get("last_daily_uc")
    if last:
        try:
            last_dt = datetime.datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
            if (now - last_dt).total_seconds() < 24*3600:
                remaining = int((24*3600 - (now - last_dt).total_seconds())//3600)
                await q.message.reply_text(f"⏳ Шумо аллакай UC гирифтед. Ба шумо боз {remaining} соат мондааст.")
                return
        except:
            pass
    roll = random.choices([1,2,3,4,5], weights=[70,20,7,2,1])[0]
    user["free_uc"] = user.get("free_uc", 0) + roll
    user["last_daily_uc"] = now.strftime("%Y-%m-%d %H:%M:%S")
    users_data[user_id] = user
    save_all()
    await q.message.reply_text(f"🎉 Шумо {roll} UC гирифтед!\n📊 Ҳамагӣ: {user['free_uc']} UC")

async def my_uc_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = str(q.from_user.id)
    user = users_data.get(user_id, {})
    amount = user.get("free_uc", 0)
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 60 UC", callback_data="claim_60")],
        [InlineKeyboardButton("🎁 325 UC", callback_data="claim_325")]
    ])
    await q.message.reply_text(f"📊 Шумо доред: {amount} UC", reply_markup=btn)

async def claim_uc_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    if data == "claim_60":
        needed = 60
    elif data == "claim_325":
        needed = 325
    else:
        return
    user_id = str(q.from_user.id)
    user = users_data.get(user_id, {})
    if user.get("free_uc", 0) < needed:
        await q.message.reply_text(f"❌ Шумо UC кофӣ надоред. Шумо доред: {user.get('free_uc',0)} UC")
        return
    context.user_data["awaiting_free_id"] = needed
    await q.message.reply_text("🎮 Лутфан ID-и PUBG-ро ворид кунед (8–15 рақам):")

async def get_free_uc_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "awaiting_free_id" not in context.user_data:
        return
    t = update.message.text.strip()
    if not t.isdigit() or not (8 <= len(t) <= 15):
        await update.message.reply_text("⚠️ Танҳо рақам, аз 8 то 15 рақам! Лутфан дубора кӯшиш кунед.")
        return
    amount = context.user_data.pop("awaiting_free_id")
    user_id = str(update.message.from_user.id)
    user = users_data.get(user_id)
    if not user:
        await update.message.reply_text("⚠️ Аввал /start кунед.")
        return

    # Deduct collected UC
    user["free_uc"] = user.get("free_uc", 0) - amount
    if user["free_uc"] < 0:
        user["free_uc"] = 0
    users_data[user_id] = user
    save_all()

    # Create order for admin (free_uc)
    order_id = random.randint(10000,99999)
    order = {
        "id": order_id,
        "user_id": user_id,
        "username": user.get("username"),
        "phone": user.get("phone"),
        "total": 0,
        "type": "free_uc",
        "pack": amount,
        "game_id": t,
        "status": "pending_admin",
        "created_at": now_str(),
    }
    orders.append(order)
    save_all()

    # send to admins
    for admin in ADMIN_IDS:
        try:
            btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Тасдиқ", callback_data=f"admin_confirm_free_{order_id}"),
                 InlineKeyboardButton("❌ Рад", callback_data=f"admin_reject_free_{order_id}")]
            ])
            await context.bot.send_message(
                admin,
                f"📦 Дархости UC ройгон №{order_id}\n"
                f"👤 @{order['username']}\n"
                f"🎮 ID: {t}\n"
                f"🎁 Пакет: {amount} UC\n"
                f"⏱ Сохта шуд: {order['created_at']}",
                reply_markup=btn
            )
        except:
            pass

    await update.message.reply_text(f"✅ Дархости шумо барои {amount} UC сабт шуд. Фармоиш қабул шуд — дар давоми 12 соат UC ба ҳисоби шумо ворид мешавад.\n(Админ онро тасдиқ ё рад карда метавонад.)")

async def admin_confirm_free(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        order_id = int(q.data.split("_")[-1])
    except:
        return
    for o in orders:
        if o["id"] == order_id and o.get("type") == "free_uc":
            if o["status"] != "pending_admin":
                await q.message.reply_text(f"Фармоиш аллакай дар ҳолати: {o['status']}")
                return
            o["status"] = "confirmed"
            o["confirmed_at"] = now_str()
            save_all()
            try:
                uid = int(o["user_id"])
                await context.bot.send_message(uid, f"✅ Дархости UC (№{order_id}) тасдиқ шуд. {o['pack']} UC ба ҳисоби шумо ворид карда шуд.")
            except:
                pass
            await q.message.reply_text("✅ Тасдиқ шуд ва паём фиристода шуд.")
            return
    await q.message.reply_text("Фармоиш ёфт нашуд.")

async def admin_reject_free(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        order_id = int(q.data.split("_")[-1])
    except:
        return
    for o in orders:
        if o["id"] == order_id and o.get("type") == "free_uc":
            if o["status"] != "pending_admin":
                await q.message.reply_text(f"Фармоиш аллакай дар ҳолати: {o['status']}")
                return
            o["status"] = "rejected"
            o["rejected_at"] = now_str()
            save_all()
            # refund user's collected UC
            try:
                uid = str(o["user_id"])
                if uid in users_data:
                    users_data[uid]["free_uc"] = users_data[uid].get("free_uc",0) + o.get("pack",0)
                    save_all()
                    await context.bot.send_message(int(uid), f"❌ Дархости UC (№{order_id}) рад шуд. {o.get('pack',0)} UC ба ҳисоби шумо баргардонда шуд.")
            except:
                pass
            await q.message.reply_text("❌ Рад шуд ва корбар баргардонида шуд.")
            return
    await q.message.reply_text("Фармоиш ёфт нашуд.")

# Admin helper to process pending orders older than 12 hours (auto-confirm)
async def process_pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if int(update.message.from_user.id) not in ADMIN_IDS:
        await update.message.reply_text("🚫 Танҳо админ.")
        return
    now = datetime.datetime.now()
    processed = 0
    for o in orders:
        if o.get("type") == "free_uc" and o.get("status") == "pending_admin":
            created = o.get("created_at")
            try:
                created_dt = datetime.datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
            except:
                continue
            if (now - created_dt).total_seconds() >= 12 * 3600:
                # auto-confirm
                o["status"] = "confirmed"
                o["confirmed_at"] = now_str()
                try:
                    uid = int(o["user_id"])
                    await context.bot.send_message(uid, f"✅ Дархости UC (№{o['id']}) ба таври автоматӣ пас аз 12 соат тасдиқ шуд. {o.get('pack')} UC ба ҳисоби шумо ворид шуд.")
                except:
                    pass
                processed += 1
    if processed:
        save_all()
    await update.message.reply_text(f"✅ Иҷро шуд: {processed} фармоиш(ҳо) коркард шуданд.")

# -------------------- Invite link handler --------------------
async def invite_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        user = update.message.from_user
        uid = user.id
        link = f"https://t.me/{BOT_USERNAME}?start=invite_{uid}"
        await update.message.reply_text(f"🔗 Инро ба дустат фирист:\n{link}\n\nҲар дафъа дӯсти нав тавассути ин линк сабт шавад — шумо 2 UC мегиред.")

# -------------------- Receive payment photo (store) --------------------
async def receive_payment_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    matching = None
    for o in reversed(orders):
        if str(o.get("user_id")) == user_id and o.get("status") == "awaiting_payment":
            matching = o
            break
    if not matching:
        await update.message.reply_text("⚠️ Ҳеҷ фармоиши интизори пардохт ёфт нашуд.")
        return
    if not update.message.photo:
        await update.message.reply_text("⚠️ Лутфан скриншот фиристед.")
        return
    photo = update.message.photo[-1]
    file_id = photo.file_id
    matching["status"] = "proof_sent"
    matching["payment_proof_file_id"] = file_id
    save_all()
    for admin in ADMIN_IDS:
        try:
            btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Қабул", callback_data=f"payment_accept_{matching['id']}_{user_id}"),
                 InlineKeyboardButton("❌ Рад", callback_data=f"payment_reject_{matching['id']}_{user_id}")]
            ])
            await context.bot.send_photo(admin, file_id,
                caption=f"📸 Скриншоти пардохт барои фармоиш №{matching['id']}\n{matching.get('total','—')} TJS",
                reply_markup=btn)
        except:
            pass
    await update.message.reply_text("✅ Скриншот қабул шуд. Админ онро тафтиш мекунад.")

# -------------------- Callback router --------------------
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.data:
        return
    data = q.data
    if data.startswith("select_"):
        await select_item_callback(update, context)
    elif data.startswith("addcart_"):
        item_id = int(data.split("_")[1])
        uid = str(q.from_user.id)
        user_carts.setdefault(uid, {})
        user_carts[uid][item_id] = user_carts[uid].get(item_id,0) + 1
        await q.answer("✅ Илова шуд")
    elif data == "back_main":
        await show_main_menu(q.message.chat, str(q.from_user.id))
    elif data == "check_sub_ucfree":
        await check_sub_callback(update, context)
    elif data == "daily_uc":
        await daily_uc_roll(update, context)
    elif data == "my_uc":
        await my_uc_info(update, context)
    elif data in ("claim_60","claim_325"):
        await claim_uc_button(update, context)
    elif data.startswith("admin_confirm_free_"):
        await admin_confirm_free(update, context)
    elif data.startswith("admin_reject_free_"):
        await admin_reject_free(update, context)
    else:
        await q.answer()

# -------------------- Text handler --------------------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    user_id = str(update.message.from_user.id)
    if broadcast_mode.get(user_id):
        msg = text
        count = 0
        for uid in list(users_data.keys()):
            try:
                await context.bot.send_message(int(uid), f"📣 Паём аз админ:\n\n{msg}")
                count += 1
            except:
                pass
        await update.message.reply_text(f"✅ Паём ба {count} корбар фиристода шуд.")
        broadcast_mode[user_id] = False
        return
    if context.user_data.get("awaiting_game_id"):
        await get_game_id(update, context)
        return
    if "awaiting_free_id" in context.user_data:
        await get_free_uc_id(update, context)
        return
    if "captcha_answer" in context.user_data:
        await handle_captcha_answer(update, context)
        return
    if text == "🛍 Каталог":
        await catalog_handler(update, context)
    elif text == "🔗 Даъвати дӯстон":
        await invite_button_handler(update, context)
    elif text == "🎁 UC ройгон":
        await free_uc_menu_entry(update, context)
    elif text == "ℹ Маълумот":
        await update.message.reply_text(ADMIN_INFO)
    elif text == "👑 Панели админ" and int(user_id) in ADMIN_IDS:
        buttons = [
            [InlineKeyboardButton("📋 Рӯйхати корбарон", callback_data="admin_users"),
             InlineKeyboardButton("📦 Фармоишҳо", callback_data="admin_orders")],
            [InlineKeyboardButton("📣 Паём ба корбарон", callback_data="admin_broadcast")],
            [InlineKeyboardButton("⬅️ Бозгашт", callback_data="back_main")]
        ]
        await update.message.reply_text("👑 Панели админ:", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update.message.reply_text("🤖 Лутфан аз тугмаҳо истифода баред.")

# -------------------- Checkout minimal --------------------
async def checkout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = str(q.from_user.id)
    cart = user_carts.get(uid,{})
    if not cart:
        await q.message.reply_text("🛒 Сабад холист.")
        return
    await q.message.reply_text("🎮 Лутфан ID-и бозии худро ворид кунед (фақат рақамҳо):")
    context.user_data["awaiting_game_id"] = True
    context.user_data["pending_order_total"] = sum(ITEMS[i]["price"]*q for i,q in cart.items())

async def get_game_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_game_id"):
        return
    game_id = (update.message.text or "").strip()
    if not game_id.isdigit():
        await update.message.reply_text("⚠️ Танҳо рақам ворид кунед.")
        return
    context.user_data["awaiting_game_id"] = False
    uid = str(update.message.from_user.id)
    total = context.user_data.get("pending_order_total",0)
    order_id = random.randint(10000,99999)
    order = {
        "id": order_id,
        "user_id": uid,
        "username": users_data.get(uid,{}).get("username"),
        "phone": users_data.get(uid,{}).get("phone"),
        "total": total,
        "type": "store",
        "game_id": game_id,
        "status": "pending",
        "created_at": now_str()
    }
    orders.append(order)
    save_all()
    for admin in ADMIN_IDS:
        try:
            btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Тасдиқ", callback_data=f"admin_confirm_{order_id}"),
                 InlineKeyboardButton("❌ Рад", callback_data=f"admin_reject_{order_id}")]
            ])
            await context.bot.send_message(admin,
                f"📦 Фармоиши нав №{order_id}\n👤 @{order.get('username')}\n🎮 ID: {game_id}\n💰 {total} TJS",
                reply_markup=btn)
        except:
            pass
    await update.message.reply_text(f"✅ Фармоиши шумо №{order_id} сабт шуд! Мунтазир шавед барои тасдиқ аз админ.")
    user_carts[uid] = {}

# -------------------- Admin initial confirm/reject for store --------------------
async def admin_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    try:
        order_id = int(q.data.split("_")[-1])
    except:
        return
    for o in orders:
        if o["id"] == order_id:
            if o["status"] != "pending":
                await q.message.reply_text(f"Фармоиш дар ҳолати: {o['status']}")
                return
            o["status"] = "awaiting_payment"
            save_all()
            try:
                await context.bot.send_message(int(o["user_id"]),
                    f"💳 Барои анҷом додани пардохт, лутфан ба рақами VISA пардохт кунед: {VISA_NUMBER}\nПас аз пардохт скриншот фиристед.")
            except:
                pass
            await q.message.reply_text("📨 Рақами VISA ба корбар фиристода шуд.")
            return
    await q.message.reply_text("Фармоиш ёфт нашуд.")

async def admin_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    try:
        order_id = int(q.data.split("_")[-1])
    except:
        return
    for o in orders:
        if o["id"] == order_id:
            if o["status"] != "pending":
                await q.message.reply_text(f"Фармоиш дар ҳолати: {o['status']}")
                return
            o["status"] = "rejected"
            save_all()
            try:
                await context.bot.send_message(int(o["user_id"]),
                    f"❌ Фармоиши шумо №{order_id} рад шуд.")
            except:
                pass
            await q.message.reply_text("❌ Рад шуд.")
            return
    await q.message.reply_text("Фармоиш ёфт нашуд.")

# -------------------- Commands --------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Фармонҳо: /start, /help, /about, /process_pending (админ)")

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ADMIN_INFO)

async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if int(update.message.from_user.id) not in ADMIN_IDS:
        await update.message.reply_text("🚫 Танхо админ.")
        return
    text = "Рӯйхати корбарон:\n"
    for u in users_data.values():
        text += f"{u.get('id')} — {u.get('username')} — {u.get('phone')} — free_uc:{u.get('free_uc',0)}\n"
    await update.message.reply_text(text)

async def process_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_pending_command(update, context)

# -------------------- Main --------------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("users", users_command))
    app.add_handler(CommandHandler("process_pending", process_pending))
    app.add_handler(MessageHandler(filters.CONTACT, get_contact))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.PHOTO, receive_payment_photo))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
