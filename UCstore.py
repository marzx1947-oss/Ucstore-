# UCstore.py — Cleaned, formatted and slightly optimized version
# NOTE: Replace TOKEN with your bot token before running.

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import asyncio
import datetime
import json
import os
import random
import string

# -------------------- Config --------------------
TOKEN = "8524676045:AAHXHO6tYovrMAAGxAQZUi2Z-TGFBUPeMyY"
ADMIN_IDS = [8436218638]
USERS_FILE = "users.json"
ORDERS_FILE = "orders.json"

ITEMS = {
    1: {"name": "60 UC", "price": 10},
    2: {"name": "325 UC", "price": 50},
    3: {"name": "660 UC", "price": 100},
    4: {"name": "1800 UC", "price": 250},
    5: {"name": "3850 UC", "price": 500},
    6: {"name": "8100 UC", "price": 1000},
}

ADMIN_INFO = (
    "UCstore — ин боти расмии фурӯши UC барои PUBG Mobile ва дигар хидматҳои рақамии бозӣ мебошад."
)

VISA_NUMBER = "4439200020432471"
FREE_UC_CHANNEL = "@marzbon_chanel"

# -------------------- Persistence --------------------

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


users_data = load_json(USERS_FILE, {})  # key: user_id (str) -> info
orders = load_json(ORDERS_FILE, [])  # list of orders

# Runtime structures (not persisted)
user_carts = {}
user_wishlist = {}
broadcast_mode = {}

# -------------------- Helpers --------------------

def generate_user_code(length: int = 6) -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def _create_order_record(user_id: str, total: int, extra=None) -> dict:
    order_id = random.randint(10000, 99999)
    order = {
        "id": order_id,
        "user_id": user_id,
        "user_name": users_data.get(user_id, {}).get("name", ""),
        "username": users_data.get(user_id, {}).get("username", ""),
        "phone": users_data.get(user_id, {}).get("phone", ""),
        "total": total,
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "pending",
        "extra": extra or {},
    }
    orders.append(order)
    save_all()
    return order


# -------------------- Handlers --------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Entry point. Ask for phone contact if user not registered.
    if not update.message:
        return

    user = update.message.from_user
    user_id = str(user.id)

    # If already registered, show menu
    if user_id in users_data:
        await update.message.reply_text(f"👋 Салом, {user.first_name}!")
        await show_main_menu(update.message.chat, user_id)
        return

    # Ask for contact
    contact_button = KeyboardButton("📱 Ворид шудан бо рақам", request_contact=True)
    reply_markup = ReplyKeyboardMarkup([[contact_button]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "🔐 Барои истифодаи бот рақами телефони худро фиристед:", reply_markup=reply_markup
    )


async def get_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Save contact and create user record
    contact = update.message.contact
    if not contact:
        await update.message.reply_text("⚠️ Лутфан контакт фиристед.")
        return

    user = update.message.from_user
    user_id = str(user.id)

    user_code = generate_user_code(6)
    users_data[user_id] = {
        "id": user.id,
        "name": user.first_name or "",
        "username": user.username or "",
        "phone": contact.phone_number,
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "free_uc": 0,
        "last_claim": None,
        "last_daily_uc": None,
        "code": user_code,
    }
    save_all()

    # Handle inviter stored in user_data (if /start payload was used)
    inviter = context.user_data.get("invited_by")
    if inviter and inviter != user_id and inviter in users_data:
        users_data[inviter]["free_uc"] = users_data[inviter].get("free_uc", 0) + 2
        save_all()
        try:
            await context.bot.send_message(
                int(inviter),
                f"🎉 Шумо 2 UC барои даъват кардани корбари нав гирифтед!
👤 @{user.username or user.first_name}"
            )
        except Exception:
            pass

    # Notify admins
    for admin in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin,
                (
                    f"👤 Корбари нав сабт шуд!

"
                    f"🧑 Ном: {user.first_name}
"
                    f"📱 Рақам: {contact.phone_number}
"
                    f"🔗 @{user.username or '—'}
"
                    f"🔑 Код: {user_code}"
                ),
            )
        except Exception:
            pass

    await update.message.reply_text(
        f"✅ Шумо бо муваффақият ворид шудед!!
🔑 Код шумо: {user_code}", reply_markup=ReplyKeyboardRemove()
    )
    await show_main_menu(update.message.chat, user_id)


async def show_main_menu(chat, user_id: str):
    buttons = [
        ["🛍 Каталог", "❤️ Дилхоҳҳо"],
        ["🛒 Сабад", "💬 Профили админ"],
        ["ℹ Маълумот", "🎁 UC ройгон"],
    ]
    if int(user_id) in ADMIN_IDS:
        buttons.append(["👑 Панели админ"])

    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)
    await chat.send_message("Менюи асосӣ:", reply_markup=reply_markup)


# Catalog handlers
async def catalog_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # works with both message and callback
    target = update.message or (update.callback_query and update.callback_query.message)
    if not target:
        return

    buttons = []
    row = []
    for i, item in ITEMS.items():
        row.append(InlineKeyboardButton(f"{item['name']} — {item['price']} TJS", callback_data=f"select_{i}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("⬅️ Бозгашт", callback_data="back_main")])

    await target.reply_text("🛍 Каталог:", reply_markup=InlineKeyboardMarkup(buttons))


async def select_item_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        item_id = int(query.data.split("_")[1])
    except Exception:
        await query.message.reply_text("⚠️ Мушкил дар интихоби маҳсулот.")
        return

    item = ITEMS.get(item_id)
    if not item:
        await query.message.reply_text("Маҳсулот пайдо нашуд.")
        return

    buttons = [
        [InlineKeyboardButton("🛒 Илова ба сабад", callback_data=f"addcart_{item_id}"),
         InlineKeyboardButton("❤️ Ба дилхоҳҳо", callback_data=f"addwish_{item_id}")],
        [InlineKeyboardButton("⬅️ Бозгашт", callback_data="back_main")],
    ]
    await query.message.reply_text(f"🛍 {item['name']} — {item['price']} TJS", reply_markup=InlineKeyboardMarkup(buttons))


async def addcart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    try:
        item_id = int(query.data.split("_")[1])
    except Exception:
        return
    user_carts.setdefault(user_id, {})
    user_carts[user_id][item_id] = user_carts[user_id].get(item_id, 0) + 1
    await query.message.reply_text(f"✅ {ITEMS[item_id]['name']} ба сабад илова шуд!")


async def addwish_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    try:
        item_id = int(query.data.split("_")[1])
    except Exception:
        return
    user_wishlist.setdefault(user_id, set()).add(item_id)
    await query.message.reply_text(f"❤️ {ITEMS[item_id]['name']} ба дилхоҳҳо илова шуд!")


async def open_wishlist_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    wishlist = user_wishlist.get(user_id, set())
    if not wishlist:
        await update.message.reply_text("❤️ Дилхоҳҳо холист.")
        return

    for i in list(wishlist):
        item = ITEMS.get(i)
        if not item:
            continue
        buttons = [
            [InlineKeyboardButton("🛒 Ба сабад", callback_data=f"addcart_{i}"),
             InlineKeyboardButton("🗑️ Хок кардан", callback_data=f"removewish_{i}")]
        ]
        await update.message.reply_text(f"❤️ {item['name']} — {item['price']} TJS", reply_markup=InlineKeyboardMarkup(buttons))


async def removewish_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🗑️ Аз дилхоҳҳо ҳазф шуд!")
    user_id = str(query.from_user.id)
    try:
        item_id = int(query.data.split("_")[1])
    except Exception:
        return
    if user_id in user_wishlist:
        user_wishlist[user_id].discard(item_id)
    try:
        await query.message.delete()
    except Exception:
        pass


# Cart and checkout
async def show_cart_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    cart = user_carts.get(user_id, {})
    if not cart:
        await update.message.reply_text("🛒 Сабад холист.")
        return
    text = "🛍 Маҳсулоти шумо:
"
    total = 0
    for i, qty in cart.items():
        item = ITEMS.get(i)
        if not item:
            continue
        subtotal = item["price"] * qty
        total += subtotal
        text += f"- {item['name']} x{qty} = {subtotal} TJS
"
    text += f"
💰 Ҳамагӣ: {total} TJS"

    buttons = [
        [InlineKeyboardButton("📦 Фармоиш додан", callback_data="checkout"),
         InlineKeyboardButton("🗑️ Пок кардан", callback_data="clear_cart")],
        [InlineKeyboardButton("⬅️ Бозгашт", callback_data="back_main")],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def clear_cart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🧹 Сабад тоза шуд!")
    user_id = str(query.from_user.id)
    user_carts[user_id] = {}


async def checkout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    cart = user_carts.get(user_id, {})
    if not cart:
        await query.message.reply_text("🛒 Сабад холист.")
        return

    await query.message.reply_text("🎮 Лутфан ID-и бозии худро ворид кунед (фақат рақамҳо):")
    context.user_data["awaiting_game_id"] = True
    context.user_data["pending_order_total"] = sum(ITEMS[i]["price"] * q for i, q in cart.items())


async def get_game_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_game_id"):
        return
    game_id = update.message.text.strip()
    if not game_id.isdigit():
        await update.message.reply_text("⚠️ Лутфан танҳо рақам ворид кунед (ID-и бозӣ бояд рақам бошад).")
        return
    context.user_data["awaiting_game_id"] = False

    user_id = str(update.message.from_user.id)
    total = context.user_data.pop("pending_order_total", 0)
    order = _create_order_record(user_id, total)
    order["game_id"] = game_id
    save_all()

    for admin in ADMIN_IDS:
        try:
            buttons = [
                [
                    InlineKeyboardButton("✅ Тасдиқ", callback_data=f"admin_confirm_{order['id']}"),
                    InlineKeyboardButton("❌ Рад", callback_data=f"admin_reject_{order['id']}"),
                ]
            ]
            await context.bot.send_message(
                admin,
                (
                    f"📦 Фармоиши нав №{order['id']} аз @{order['username'] or order['user_name']}
"
                    f"🎮 ID: {game_id}
"
                    f"📱 {order['phone']}
"
                    f"💰 {order['total']} TJS
"
                    f"🕒 {order['time']}"
                ),
                reply_markup=InlineKeyboardMarkup(buttons),
            )
        except Exception:
            pass

    await update.message.reply_text(
        f"✅ Фармоиши шумо №{order['id']} сабт шуд!
🎮 ID-и шумо: {game_id}
Мунтазир шавед барои тасдиқ аз админ."
    )
    user_carts[user_id] = {}


# Payment flow handlers
async def receive_payment_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    matching = None
    for o in reversed(orders):
        if str(o.get("user_id")) == user_id and o.get("status") == "awaiting_payment":
            matching = o
            break

    if not matching:
        await update.message.reply_text("⚠️ Ҳеҷ фармоиши интизори пардохт ёфт нашуд. Лутфан аз админ тасдиқ гиред.")
        return

    if not update.message.photo:
        await update.message.reply_text("⚠️ Лутфан скриншот (photo) фиристед.")
        return

    photo = update.message.photo[-1]
    file_id = photo.file_id

    matching["status"] = "proof_sent"
    matching["payment_proof_file_id"] = file_id
    save_all()

    for admin in ADMIN_IDS:
        buttons = [
            [
                InlineKeyboardButton("✅ Қабул", callback_data=f"payment_accept_{matching['id']}_{user_id}"),
                InlineKeyboardButton("❌ Рад", callback_data=f"payment_reject_{matching['id']}_{user_id}"),
            ]
        ]
        try:
            await context.bot.send_photo(
                chat_id=admin,
                photo=file_id,
                caption=(
                    f"📸 Скриншоти пардохт аз @{update.message.from_user.username or update.message.from_user.first_name}
"
                    f"📦 Фармоиш №{matching['id']}
💰 {matching.get('total','—')} TJS"
                ),
                reply_markup=InlineKeyboardMarkup(buttons),
            )
        except Exception:
            pass

    await update.message.reply_text("✅ Скриншот қабул шуд! Мунтазир шавед, то админ онро тасдиқ кунад.")


async def callback_payment_accept_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("payment_accept_"):
        parts = data.split("_")
        try:
            order_id = int(parts[2])
            user_id = int(parts[3])
        except Exception:
            await query.message.reply_text("⚠️ Формати маълумот нодуруст аст.")
            return
        for o in orders:
            if o["id"] == order_id and str(o["user_id"]) == str(user_id):
                o["status"] = "confirmed"
                save_all()
                try:
                    await context.bot.send_message(int(user_id), f"✅ Пардохти шумо барои фармоиши №{order_id} қабул шуд! Ташаккур.")
                except Exception:
                    pass
                await query.message.reply_text(f"✅ Пардохти фармоиш №{order_id} тасдиқ шуд.")
                return
        await query.message.reply_text("Фармоиш ёфт нашуд.")

    elif data.startswith("payment_reject_"):
        parts = data.split("_")
        try:
            order_id = int(parts[2])
            user_id = int(parts[3])
        except Exception:
            await query.message.reply_text("⚠️ Формати маълумот нодуруст аст.")
            return
        for o in orders:
            if o["id"] == order_id and str(o["user_id"]) == str(user_id):
                o["status"] = "rejected"
                save_all()
                try:
                    await context.bot.send_message(int(user_id), f"❌ Пардохти шумо барои фармоиши №{order_id} рад шуд. Лутфан бо админ тамос гиред.")
                except Exception:
                    pass
                await query.message.reply_text(f"❌ Пардохти фармоиш №{order_id} рад шуд.")
                return
        await query.message.reply_text("Фармоиш ёфт нашуд.")


# Free UC system
async def free_uc_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.message.chat if update.message else update.callback_query.message.chat
    from_user = update.message.from_user if update.message else update.callback_query.from_user
    user_id = str(from_user.id)

    if user_id not in users_data:
        await chat.send_message("⚠️ Аввал /start кунед.")
        return

    # Check subscription (best-effort; may fail for private channels)
    subscribed = False
    try:
        member = await context.bot.get_chat_member(FREE_UC_CHANNEL, int(user_id))
        subscribed = member.status in ["member", "administrator", "creator"]
    except Exception:
        subscribed = False

    buttons = []
    if subscribed:
        buttons.append([InlineKeyboardButton("🎲 Гирифтани UC-и рӯзона", callback_data="daily_uc")])
        buttons.append([InlineKeyboardButton("📊 UC-и ҷамъшуда", callback_data="my_uc")])
        buttons.append([
            InlineKeyboardButton("🎁 60 UC", callback_data="claim_60"),
            InlineKeyboardButton("🎁 325 UC", callback_data="claim_325"),
        ])
    else:
        channel_url = f"https://t.me/{FREE_UC_CHANNEL.lstrip('@')}"
        buttons.append([InlineKeyboardButton("📢 Обуна шудан", url=channel_url)])
        buttons.append([InlineKeyboardButton("🔄 Санҷиш", callback_data="check_sub_ucfree")])

    buttons.append([InlineKeyboardButton("🔗 Даъвати дӯстон", callback_data="invite_link")])
    await chat.send_message("🎁 Менюи UC ройгон:", reply_markup=InlineKeyboardMarkup(buttons))


async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await free_uc_menu(update, context)


async def daily_uc_roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
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
            if (now - last_dt).total_seconds() < 24 * 3600:
                remaining = int((24 * 3600 - (now - last_dt).total_seconds()) // 3600)
                await q.message.reply_text(f"⏳ Шумо аллакай UC гирифтед. Ба шумо боз {remaining} соат мондааст.")
                return
        except Exception:
            pass

    roll = random.choices([1, 2, 3, 4, 5], weights=[70, 20, 7, 2, 1])[0]
    user["free_uc"] = user.get("free_uc", 0) + roll
    user["last_daily_uc"] = now.strftime("%Y-%m-%d %H:%M:%S")
    users_data[user_id] = user
    save_all()
    await q.message.reply_text(f"🎉 Шумо {roll} UC гирифтед!
📊 Ҳамагӣ: {user['free_uc']} UC")


async def my_uc_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = str(q.from_user.id)
    user = users_data.get(user_id, {})
    amount = user.get("free_uc", 0)
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 60 UC", callback_data="claim_60")],
        [InlineKeyboardButton("🎁 325 UC", callback_data="claim_325")],
    ])
    await q.message.reply_text(f"📊 Шумо доред: {amount} UC", reply_markup=btn)


async def claim_uc_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    needed = 60 if data == "claim_60" else 325 if data == "claim_325" else None
    if not needed:
        return
    user_id = str(q.from_user.id)
    user = users_data.get(user_id, {})
    if user.get("free_uc", 0) < needed:
        await q.message.reply_text(f"❌ Шумо UC кофӣ надоред. Шумо доред: {user.get('free_uc', 0)} UC")
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

    user["free_uc"] = max(0, user.get("free_uc", 0) - amount)
    users_data[user_id] = user
    save_all()

    order_id = random.randint(10000, 99999)
    order = {
        "id": order_id,
        "user_id": user_id,
        "username": user.get("username"),
        "phone": user.get("phone"),
        "total": 0,
        "type": "free_uc",
        "pack": amount,
        "game_id": t,
        "status": "pending",
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    orders.append(order)
    save_all()

    for admin in ADMIN_IDS:
        try:
            btn = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Тасдиқ", callback_data=f"admin_confirm_free_{order_id}"),
                    InlineKeyboardButton("❌ Рад", callback_data=f"admin_reject_free_{order_id}"),
                ]
            ])
            await context.bot.send_message(
                admin,
                f"📦 Фармоиши UC ройгон №{order_id}
👤 @{order['username']}
🎮 ID: {t}
🎁 Пакет: {amount} UC",
                reply_markup=btn,
            )
        except Exception:
            pass

    await update.message.reply_text(f"🎁 Дархости {amount} UC ба админ фиристода шуд! (Фармоиш №{order_id})")


async def admin_confirm_free(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        order_id = int(q.data.split("_")[-1])
    except Exception:
        return
    for o in orders:
        if o["id"] == order_id and o.get("type") == "free_uc":
            if o["status"] != "pending":
                await q.message.reply_text(f"Фармоиш аллакай дар ҳолати: {o['status']}")
                return
            o["status"] = "confirmed"
            save_all()
            try:
                await context.bot.send_message(int(o["user_id"]), f"✅ Дархости UC (№{order_id}) тасдиқ шуд! Ташаккур.")
            except Exception:
                pass
            await q.message.reply_text("✅ Тасдиқ шуд.")
            return
    await q.message.reply_text("Фармоиш ёфт нашуд.")


async def admin_reject_free(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        order_id = int(q.data.split("_")[-1])
    except Exception:
        return
    for o in orders:
        if o["id"] == order_id and o.get("type") == "free_uc":
            o["status"] = "rejected"
            save_all()
            try:
                await context.bot.send_message(int(o["user_id"]), f"❌ Дархост (№{order_id}) рад шуд. Лутфан бо админ тамос гиред.")
            except Exception:
                pass
            await q.message.reply_text("❌ Рад шуд.")
            return
    await q.message.reply_text("Фармоиш ёфт нашуд.")


# Admin confirm/reject for paid orders
async def admin_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        order_id = int(query.data.split("_")[-1])
    except Exception:
        return
    for o in orders:
        if o["id"] == order_id:
            if o["status"] != "pending":
                await query.message.reply_text(f"Фармоиш аллакай дар ҳолати: {o['status']}")
                return
            o["status"] = "awaiting_payment"
            save_all()
            try:
                await context.bot.send_message(
                    int(o["user_id"]),
                    f"💳 Барои анҷом додани пардохт, лутфан ба рақами VISA зер пардохт кунед:

🔹 {VISA_NUMBER}

Пас аз пардохт, скриншоти тасдиқро ба ин ҷо фиристед 📸",
                )
            except Exception:
                pass
            await query.message.reply_text(f"📨 Рақами VISA ба @{o['username'] or o['user_name']} фиристода шуд.")
            return
    await query.message.reply_text("Фармоиш ёфт нашуд.")


async def admin_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        order_id = int(query.data.split("_")[-1])
    except Exception:
        return
    for o in orders:
        if o["id"] == order_id:
            if o["status"] != "pending":
                await query.message.reply_text(f"Фармоиш аллакай дар ҳолати: {o['status']}")
                return
            o["status"] = "rejected"
            save_all()
            try:
                await context.bot.send_message(int(o["user_id"]), f"❌ Фармоиши шумо №{o['id']} рад шуд. Лутфан бо админ тамос гиред.")
            except Exception:
                pass
            await query.message.reply_text(f"❌ Фармоиш №{order_id} рад шуд.")
            return
    await query.message.reply_text("Фармоиш ёфт нашуд.")


# Invite link
async def invite_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = q.from_user
    uid = str(user.id)
    try:
        bot = await context.bot.get_me()
        bot_username = bot.username
    except Exception:
        await q.message.reply_text("⚠️ Хато: бот номи худро ёфта натавонист.")
        return
    invite_url = f"https://t.me/{bot_username}?start=invite_{uid}"
    await q.message.reply_text(
        "🔗 Ин линкро ба дӯстонат фирист:

" + invite_url + "

Ҳар дӯсте, ки сабт мешавад → ту 2 UC мегирӣ!"
    )


# Admin panel (single implementation)
async def admin_panel_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = str(query.from_user.id)

    if data == "admin_panel":
        keyboard = [
            [InlineKeyboardButton("👤 Корбарон", callback_data="admin_users")],
            [InlineKeyboardButton("📦 Заказҳо", callback_data="admin_orders")],
            [InlineKeyboardButton("📢 Расонидани паём", callback_data="admin_broadcast")],
            [InlineKeyboardButton("⬅️ Бозгашт", callback_data="back_main")],
        ]
        await query.message.edit_text(
            "⚙️ *Панели Администратор*
Дар ин ҷо ту тамоми мағоза ва корбарҳоро идора мекунӣ.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if data == "admin_users":
        if not users_data:
            text = "📋 Ҳоло ҳеҷ корбар нест."
        else:
            text = "📋 *Рӯйхати корбарон:*

"
            for uid, u in users_data.items():
                text += f"• {u.get('name','—')} — {u.get('phone','—')} (id: {uid})
"
        await query.message.edit_text(
            text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Бозгашт", callback_data="admin_panel")]])
        )
        return

    if data == "admin_orders":
        if not orders:
            text = "❗ Ҳоло ҳеҷ заказ нест."
        else:
            text = "📦 *Рӯйхати заказҳо:*

"
            for o in orders:
                text += f"#{o['id']} — @{o.get('username') or o.get('user_name','-')} — {o.get('total', o.get('pack',0))} — {o['status']}
"
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Бозгашт", callback_data="admin_panel")]]))
        return

    if data == "admin_broadcast":
        broadcast_mode[user_id] = True
        await query.message.edit_text("✏️ Ҳозир матни паёмро навис — ман онро ба *ҳама корбарҳо* мефиристам.", parse_mode="Markdown")
        return


# Text handler
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = str(update.message.from_user.id)

    # Broadcast mode
    if broadcast_mode.get(user_id):
        msg = text
        count = 0
        for uid in list(users_data.keys()):
            try:
                await context.bot.send_message(int(uid), f"📣 Паём аз админ:

{msg}")
                count += 1
            except Exception:
                pass
        await update.message.reply_text(f"✅ Паём ба {count} корбар фиристода шуд.")
        broadcast_mode[user_id] = False
        return

    # Menu commands
    if text == "🛍 Каталог":
        await catalog_handler(update, context)
    elif text == "❤️ Дилхоҳҳо":
        await open_wishlist_from_text(update, context)
    elif text == "🛒 Сабад":
        await show_cart_from_text(update, context)
    elif text == "ℹ Маълумот":
        await update.message.reply_text(ADMIN_INFO)
    elif text == "💬 Профили админ":
        await update.message.reply_text(
            "Барои тамос бо админ зер кунед:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Профили админ", url=f"tg://user?id={ADMIN_IDS[0]}")]]),
        )
    elif text == "👑 Панели админ" and int(user_id) in ADMIN_IDS:
        buttons = [
            [InlineKeyboardButton("📋 Рӯйхати корбарон", callback_data="admin_users"), InlineKeyboardButton("📦 Фармоишҳо", callback_data="admin_orders")],
            [InlineKeyboardButton("📣 Паём ба корбарон", callback_data="admin_broadcast")],
            [InlineKeyboardButton("⬅️ Бозгашт", callback_data="back_main")],
        ]
        await update.message.reply_text("👑 Панели админ:", reply_markup=InlineKeyboardMarkup(buttons))
    elif text == "🎁 UC ройгон":
        await free_uc_menu(update, context)
    else:
        await update.message.reply_text("🤖 Лутфан аз тугмаҳои меню истифода баред.")


# Text router for awaiting inputs
async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_game_id"):
        await get_game_id(update, context)
        return
    if "awaiting_free_id" in context.user_data:
        await get_free_uc_id(update, context)
        return
    await handle_text(update, context)


# Callback router
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return
    data = query.data

    # Admin panel shortcuts
    if data in ["admin_panel", "admin_users", "admin_orders", "admin_broadcast", "back_admin"]:
        await admin_panel_main(update, context)
        return

    # Catalog and cart
    if data.startswith("select_"):
        await select_item_callback(update, context)
    elif data.startswith("addcart_"):
        await addcart_callback(update, context)
    elif data.startswith("addwish_"):
        await addwish_callback(update, context)
    elif data.startswith("removewish_"):
        await removewish_callback(update, context)
    elif data == "clear_cart":
        await clear_cart_callback(update, context)
    elif data == "checkout":
        await checkout_callback(update, context)
    elif data == "back_main":
        uid = str(query.from_user.id)
        await show_main_menu(query.message.chat, uid)

    # Admin store confirm/reject
    elif data.startswith("admin_confirm_"):
        await admin_confirm_callback(update, context)
    elif data.startswith("admin_reject_"):
        await admin_reject_callback(update, context)

    # Payment accept/reject
    elif data.startswith("payment_accept_") or data.startswith("payment_reject_"):
        await callback_payment_accept_reject(update, context)

    # Free UC callbacks
    elif data == "check_sub_ucfree":
        await check_sub_callback(update, context)
    elif data == "daily_uc":
        await daily_uc_roll(update, context)
    elif data == "my_uc":
        await my_uc_info(update, context)
    elif data in ["claim_60", "claim_325"]:
        await claim_uc_button(update, context)
    elif data.startswith("admin_confirm_free_"):
        await admin_confirm_free(update, context)
    elif data.startswith("admin_reject_free_"):
        await admin_reject_free(update, context)
    elif data == "invite_link":
        await invite_link_callback(update, context)
    else:
        await query.answer()


# Commands
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🆘 Фармонҳо: /start, /help, /about, /users (админ)")


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ADMIN_INFO)


async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if int(update.message.from_user.id) not in ADMIN_IDS:
        await update.message.reply_text("🚫 Танҳо админ!")
        return
    if not users_data:
        await update.message.reply_text("Ҳеҷ корбар сабт нашудааст.")
        return
    text = "📋 Рӯйхати корбарон:

"
    for u in users_data.values():
        text += f"👤 {u.get('name','—')} — {u.get('phone','—')} (id: {u.get('id')})
"
    await update.message.reply_text(text)


# Extra command wrappers
async def catalog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await catalog_handler(update, context)


async def cart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_cart_from_text(update, context)


async def wishlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await open_wishlist_from_text(update, context)


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ADMIN_INFO)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = int(update.message.from_user.id)
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("🚫 Танҳо админ!")
        return
    buttons = [
        [InlineKeyboardButton("📋 Рӯйхати корбарон", callback_data="admin_users"), InlineKeyboardButton("📦 Фармоишҳо", callback_data="admin_orders")],
        [InlineKeyboardButton("📣 Паём ба корбарон", callback_data="admin_broadcast")],
        [InlineKeyboardButton("⬅️ Бозгашт", callback_data="back_main")],
    ]
    await update.message.reply_text("👑 Панели админ:", reply_markup=InlineKeyboardMarkup(buttons))


# Main

def main():
    if TOKEN == "REPLACE_WITH_YOUR_BOT_TOKEN":
        print("Please set TOKEN in the script before running.")
        return

    app = ApplicationBuilder().token(TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("users", users_command))

    # Extra commands
    app.add_handler(CommandHandler("catalog", catalog_command))
    app.add_handler(CommandHandler("cart", cart_command))
    app.add_handler(CommandHandler("wishlist", wishlist_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("admin", admin_command))

    # Contact handler
    app.add_handler(MessageHandler(filters.CONTACT, get_contact))

    # CallbackQuery
    app.add_handler(CallbackQueryHandler(callback_router))

    # Photos
    app.add_handler(MessageHandler(filters.PHOTO, receive_payment_photo))

    # Text messages
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_router))

    print("✅ UCstore бот фаъол шуд!")
    app.run_polling()


if __name__ == "__main__":
    main()
