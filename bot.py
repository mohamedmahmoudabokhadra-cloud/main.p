import os
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# ========== الإعدادات ==========
BOT_TOKEN = os.getenv("BOT_TOKEN", "ضع_توكن_البوت_هنا")
ADMIN_ID = 868999453
CHANNELS = ["@penguin_110", "@Crypto_Dragon13"]
REWARD_PER_REFERRAL = 0.02
MIN_WITHDRAW = 0.2

# ========== قاعدة البيانات ==========
def init_db():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance REAL DEFAULT 0,
        referrals INTEGER DEFAULT 0,
        referred_by INTEGER DEFAULT NULL,
        joined_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        wallet TEXT,
        status TEXT DEFAULT 'pending',
        requested_at TEXT
    )''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def add_user(user_id, username, referred_by=None):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, referred_by, joined_at) VALUES (?,?,?,?)",
              (user_id, username, referred_by, datetime.now().isoformat()))
    if referred_by and referred_by != user_id:
        c.execute("UPDATE users SET balance=balance+?, referrals=referrals+1 WHERE user_id=?",
                  (REWARD_PER_REFERRAL, referred_by))
    conn.commit()
    conn.close()

def get_balance(user_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT balance, referrals FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row if row else (0, 0)

def add_withdrawal(user_id, amount, wallet):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("INSERT INTO withdrawals (user_id, amount, wallet, requested_at) VALUES (?,?,?,?)",
              (user_id, amount, wallet, datetime.now().isoformat()))
    c.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

# ========== التحقق من الاشتراك ==========
async def check_subscriptions(user_id, context):
    for channel in CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            return False
    return True

# ========== لوحة المفاتيح الثابتة (تحت) ==========
def reply_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🔗 رابط الإحالة"), KeyboardButton("💰 رصيدي")],
        [KeyboardButton("👥 إحالاتي"), KeyboardButton("💵 سحب")],
        [KeyboardButton("📋 شروط الاشتراك")],
        [KeyboardButton("📣 الدعم والإعلان")]
    ], resize_keyboard=True)

# ========== الأزرار المضمنة (فوق) ==========
def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 رابط الإحالة", callback_data="referral"),
         InlineKeyboardButton("💰 رصيدي", callback_data="balance")],
        [InlineKeyboardButton("👥 إحالاتي", callback_data="referrals"),
         InlineKeyboardButton("💵 سحب", callback_data="withdraw")],
        [InlineKeyboardButton("📋 شروط الاشتراك", callback_data="terms")],
        [InlineKeyboardButton("📣 الدعم والإعلان", callback_data="support")]
    ])

def subscription_keyboard():
    buttons = [[InlineKeyboardButton(f"📢 اشترك في {ch}", url=f"https://t.me/{ch.lstrip('@')}")] for ch in CHANNELS]
    buttons.append([InlineKeyboardButton("✅ تحققت من اشتراكي", callback_data="check_sub")])
    return InlineKeyboardMarkup(buttons)

# ========== الأوامر ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    referred_by = int(args[0]) if args and args[0].isdigit() else None

    if not get_user(user.id):
        add_user(user.id, user.username or user.first_name, referred_by)
        if referred_by and referred_by != user.id:
            try:
                await context.bot.send_message(
                    referred_by,
                    f"🎉 انضم شخص جديد عبر رابطك!\n💰 حصلت على +{REWARD_PER_REFERRAL}$"
                )
            except:
                pass

    subscribed = await check_subscriptions(user.id, context)
    if not subscribed:
        await update.message.reply_text(
            "👋 مرحباً بك!\n\n"
            "⚠️ يجب الاشتراك في القنوات التالية أولاً للمتابعة:",
            reply_markup=subscription_keyboard()
        )
        return

    await update.message.reply_text(
        f"👋 أهلاً {user.first_name}!\n\n"
        f"🤖 بوت penguin للإحالات\n"
        f"💰 اربح {REWARD_PER_REFERRAL}$ لكل صديق تدعوه!\n"
        f"📌 الحد الأدنى للسحب: {MIN_WITHDRAW}$",
        reply_markup=reply_keyboard()
    )

# ========== معالج الرسائل النصية (أزرار التحت) ==========
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    if context.user_data.get("awaiting_wallet"):
        wallet = text.strip()
        amount = context.user_data["withdraw_amount"]
        add_withdrawal(user.id, amount, wallet)
        context.user_data.pop("awaiting_wallet", None)
        context.user_data.pop("withdraw_amount", None)

        await update.message.reply_text(
            "✅ تم تقديم طلب السحب وسيتم مراجعته من قبل الإدارة.",
            reply_markup=reply_keyboard()
        )
        username = f"@{user.username}" if user.username else str(user.id)
        await context.bot.send_message(
            ADMIN_ID,
            f"💵 طلب سحب جديد!\n\n"
            f"👤 المستخدم: {username} ({user.id})\n"
            f"💰 المبلغ: {amount:.2f}$\n"
            f"🏦 محفظة TON:\n`{wallet}`",
            parse_mode="Markdown"
        )
        return

    if text == "💰 رصيدي":
        balance, refs = get_balance(user.id)
        await update.message.reply_text(
            f"💰 رصيدك الحالي: {balance:.2f}$\n"
            f"👥 عدد إحالاتك: {refs}",
            reply_markup=reply_keyboard()
        )

    elif text == "🔗 رابط الإحالة":
        bot_info = await context.bot.get_me()
        link = f"https://t.me/{bot_info.username}?start={user.id}"
        await update.message.reply_text(
            f"🔗 رابط إحالتك الخاص:\n\n`{link}`\n\n"
            f"شارك هذا الرابط واربح {REWARD_PER_REFERRAL}$ لكل شخص يشترك!",
            parse_mode="Markdown",
            reply_markup=reply_keyboard()
        )

    elif text == "👥 إحالاتي":
        balance, refs = get_balance(user.id)
        await update.message.reply_text(
            f"👥 عدد إحالاتك: {refs}\n"
            f"💵 إجمالي أرباحك: {refs * REWARD_PER_REFERRAL:.2f}$",
            reply_markup=reply_keyboard()
        )

    elif text == "💵 سحب":
        balance, _ = get_balance(user.id)
        if balance < MIN_WITHDRAW:
            await update.message.reply_text(
                f"❌ رصيدك {balance:.2f}$ أقل من الحد الأدنى للسحب ({MIN_WITHDRAW}$)\n"
                f"تحتاج {MIN_WITHDRAW - balance:.2f}$ إضافية.",
                reply_markup=reply_keyboard()
            )
        else:
            context.user_data["awaiting_wallet"] = True
            context.user_data["withdraw_amount"] = balance
            await update.message.reply_text(
                f"💵 رصيدك المتاح: {balance:.2f}$\n\n"
                "📩 أرسل عنوان محفظة TON الخاصة بك:"
            )

    elif text == "📋 شروط الاشتراك":
        await update.message.reply_text(
            "📋 شروط الاشتراك:\n\n"
            f"• تحصل على {REWARD_PER_REFERRAL}$ لكل صديق تدعوه\n"
            f"• الحد الأدنى للسحب: {MIN_WITHDRAW}$\n"
            "• يجب أن يكون الصديق مشتركاً في القنوات\n"
            "• السحب عبر محفظة TON فقط\n"
            "• طلبات السحب تُراجع خلال 24 ساعة",
            reply_markup=reply_keyboard()
        )

    elif text == "📣 الدعم والإعلان":
        await update.message.reply_text(
            "📣 للدعم والإعلان:\n👉 @Thepenguin133",
            reply_markup=reply_keyboard()
        )

# ========== معالج الأزرار المضمنة ==========
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if query.data == "check_sub":
        subscribed = await check_subscriptions(user.id, context)
        if subscribed:
            await query.edit_message_text(
                f"✅ تم التحقق! أهلاً {user.first_name}\n\n"
                f"💰 اربح {REWARD_PER_REFERRAL}$ لكل صديق تدعوه!",
            )
            await context.bot.send_message(
                user.id,
                f"👋 أهلاً {user.first_name}!\n\n"
                f"🤖 بوت penguin للإحالات\n"
                f"💰 اربح {REWARD_PER_REFERRAL}$ لكل صديق تدعوه!\n"
                f"📌 الحد الأدنى للسحب: {MIN_WITHDRAW}$",
                reply_markup=reply_keyboard()
            )
        else:
            await query.edit_message_text(
                "❌ لم تشترك في جميع القنوات بعد!\nاشترك ثم اضغط تحققت.",
                reply_markup=subscription_keyboard()
            )

# ========== أوامر الأدمن ==========
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'")
    pending = c.fetchone()[0]
    conn.close()
    await update.message.reply_text(
        f"📊 إحصائيات البوت:\n\n"
        f"👥 إجمالي المستخدمين: {total_users}\n"
        f"⏳ طلبات سحب معلقة: {pending}"
    )

# ========== التشغيل ==========
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    print("✅ البوت يعمل...")
    app.run_polling()

if __name__ == "__main__":
    main()
