import os
import pg8000.native
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "ضع_توكن_البوت_هنا")
ADMIN_ID = 868999453
CHANNELS = ["@penguin_110", "@Crypto_Dragon13"]
REWARD_PER_REFERRAL = 0.02
MIN_WITHDRAW = 0.2

DB_HOST = "db.hdbbhhgnphtkiugtomvm.supabase.co"
DB_NAME = "postgres"
DB_USER = "postgres"
DB_PASS = os.getenv("DB_PASS", "a1s2d3f411@@#@&6")
DB_PORT = 6543

def get_db():
    return pg8000.native.Connection(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=DB_PORT,
        ssl_context=True
    )

def init_db():
    conn = get_db()
    conn.run('''CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        username TEXT,
        balance REAL DEFAULT 0,
        referrals INTEGER DEFAULT 0,
        referred_by BIGINT DEFAULT NULL,
        joined_at TEXT
    )''')
    conn.run('''CREATE TABLE IF NOT EXISTS withdrawals (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        amount REAL,
        wallet TEXT,
        status TEXT DEFAULT 'pending',
        requested_at TEXT
    )''')
    conn.close()

def get_user(user_id):
    conn = get_db()
    row = conn.run("SELECT * FROM users WHERE user_id=:uid", uid=user_id)
    conn.close()
    return row[0] if row else None

def add_user(user_id, username, referred_by=None):
    conn = get_db()
    conn.run(
        "INSERT INTO users (user_id, username, referred_by, joined_at) VALUES (:uid,:uname,:ref,:joined) ON CONFLICT DO NOTHING",
        uid=user_id, uname=username, ref=referred_by, joined=datetime.now().isoformat()
    )
    if referred_by and referred_by != user_id:
        conn.run(
            "UPDATE users SET balance=balance+:reward, referrals=referrals+1 WHERE user_id=:ref",
            reward=REWARD_PER_REFERRAL, ref=referred_by
        )
    conn.close()

def get_balance(user_id):
    conn = get_db()
    row = conn.run("SELECT balance, referrals FROM users WHERE user_id=:uid", uid=user_id)
    conn.close()
    return (row[0][0], row[0][1]) if row else (0, 0)

def add_withdrawal(user_id, amount, wallet):
    conn = get_db()
    conn.run(
        "INSERT INTO withdrawals (user_id, amount, wallet, requested_at) VALUES (:uid,:amt,:wallet,:req)",
        uid=user_id, amt=amount, wallet=wallet, req=datetime.now().isoformat()
    )
    conn.run("UPDATE users SET balance=balance-:amt WHERE user_id=:uid", amt=amount, uid=user_id)
    conn.close()

async def check_subscriptions(user_id, context):
    for channel in CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            return False
    return True

def reply_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🔗 رابط الإحالة"), KeyboardButton("💰 رصيدي")],
        [KeyboardButton("👥 إحالاتي"), KeyboardButton("💵 سحب")],
        [KeyboardButton("📋 شروط الاشتراك")],
        [KeyboardButton("📣 الدعم والإعلان")]
    ], resize_keyboard=True)

def subscription_keyboard():
    buttons = [[InlineKeyboardButton(f"📢 اشترك في {ch}", url=f"https://t.me/{ch.lstrip('@')}")] for ch in CHANNELS]
    buttons.append([InlineKeyboardButton("✅ تحققت من اشتراكي", callback_data="check_sub")])
    return InlineKeyboardMarkup(buttons)

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
            "👋 مرحباً بك!\n\n⚠️ يجب الاشتراك في القنوات التالية أولاً:",
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
            f"💰 رصيدك الحالي: {balance:.2f}$\n👥 عدد إحالاتك: {refs}",
            reply_markup=reply_keyboard()
        )
    elif text == "🔗 رابط الإحالة":
        bot_info = await context.bot.get_me()
        link = f"https://t.me/{bot_info.username}?start={user.id}"
        await update.message.reply_text(
            f"🔗 رابط إحالتك:\n\n`{link}`\n\nاربح {REWARD_PER_REFERRAL}$ لكل شخص يشترك!",
            parse_mode="Markdown", reply_markup=reply_keyboard()
        )
    elif text == "👥 إحالاتي":
        balance, refs = get_balance(user.id)
        await update.message.reply_text(
            f"👥 عدد إحالاتك: {refs}\n💵 إجمالي أرباحك: {refs * REWARD_PER_REFERRAL:.2f}$",
            reply_markup=reply_keyboard()
        )
    elif text == "💵 سحب":
        balance, _ = get_balance(user.id)
        if balance < MIN_WITHDRAW:
            await update.message.reply_text(
                f"❌ رصيدك {balance:.2f}$ أقل من الحد الأدنى ({MIN_WITHDRAW}$)\n"
                f"تحتاج {MIN_WITHDRAW - balance:.2f}$ إضافية.",
                reply_markup=reply_keyboard()
            )
        else:
            context.user_data["awaiting_wallet"] = True
            context.user_data["withdraw_amount"] = balance
            await update.message.reply_text(
                f"💵 رصيدك المتاح: {balance:.2f}$\n\n📩 أرسل عنوان محفظة TON:"
            )
    elif text == "📋 شروط الاشتراك":
        await update.message.reply_text(
            "📋 شروط الاشتراك:\n\n"
            f"• تحصل على {REWARD_PER_REFERRAL}$ لكل صديق\n"
            f"• الحد الأدنى للسحب: {MIN_WITHDRAW}$\n"
            "• يجب اشتراك الصديق في القنوات\n"
            "• السحب عبر محفظة TON فقط\n"
            "• طلبات السحب تُراجع خلال 24 ساعة",
            reply_markup=reply_keyboard()
        )
    elif text == "📣 الدعم والإعلان":
        await update.message.reply_text(
            "📣 للدعم والإعلان:\n👉 @Thepenguin133",
            reply_markup=reply_keyboard()
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    if query.data == "check_sub":
        subscribed = await check_subscriptions(user.id, context)
        if subscribed:
            await query.edit_message_text(f"✅ تم التحقق! أهلاً {user.first_name}")
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
                "❌ لم تشترك في جميع القنوات!\nاشترك ثم اضغط تحققت.",
                reply_markup=subscription_keyboard()
            )

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    conn = get_db()
    total_users = conn.run("SELECT COUNT(*) FROM users")[0][0]
    pending = conn.run("SELECT COUNT(*) FROM withdrawals WHERE status='pending'")[0][0]
    conn.close()
    await update.message.reply_text(
        f"📊 إحصائيات البوت:\n\n"
        f"👥 إجمالي المستخدمين: {total_users}\n"
        f"⏳ طلبات سحب معلقة: {pending}"
    )

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
