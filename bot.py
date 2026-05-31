import os
import asyncpg
import asyncio
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
DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:a1s2d3f411@@#@&6@db.hdbbhhgnphtkiugtomvm.supabase.co:5432/postgres")

async def get_db():
    return await asyncpg.connect(DB_URL)

async def init_db():
    conn = await get_db()
    await conn.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        username TEXT,
        balance REAL DEFAULT 0,
        referrals INTEGER DEFAULT 0,
        referred_by BIGINT DEFAULT NULL,
        joined_at TEXT
    )''')
    await conn.execute('''CREATE TABLE IF NOT EXISTS withdrawals (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        amount REAL,
        wallet TEXT,
        status TEXT DEFAULT 'pending',
        requested_at TEXT
    )''')
    await conn.close()

async def get_user(user_id):
    conn = await get_db()
    row = await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
    await conn.close()
    return row

async def add_user(user_id, username, referred_by=None):
    conn = await get_db()
    await conn.execute(
        "INSERT INTO users (user_id, username, referred_by, joined_at) VALUES ($1,$2,$3,$4) ON CONFLICT DO NOTHING",
        user_id, username, referred_by, datetime.now().isoformat()
    )
    if referred_by and referred_by != user_id:
        await conn.execute(
            "UPDATE users SET balance=balance+$1, referrals=referrals+1 WHERE user_id=$2",
            REWARD_PER_REFERRAL, referred_by
        )
    await conn.close()

async def get_balance(user_id):
    conn = await get_db()
    row = await conn.fetchrow("SELECT balance, referrals FROM users WHERE user_id=$1", user_id)
    await conn.close()
    return (row['balance'], row['referrals']) if row else (0, 0)

async def add_withdrawal(user_id, amount, wallet):
    conn = await get_db()
    await conn.execute(
        "INSERT INTO withdrawals (user_id, amount, wallet, requested_at) VALUES ($1,$2,$3,$4)",
        user_id, amount, wallet, datetime.now().isoformat()
    )
    await conn.execute("UPDATE users SET balance=balance-$1 WHERE user_id=$2", amount, user_id)
    await conn.close()

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
    if not await get_user(user.id):
        await add_user(user.id, user.username or user.first_name, referred_by)
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
        await add_withdrawal(user.id, amount, wallet)
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
        balance, refs = await get_balance(user.id)
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
        balance, refs = await get_balance(user.id)
        await update.message.reply_text(
            f"👥 عدد إحالاتك: {refs}\n💵 إجمالي أرباحك: {refs * REWARD_PER_REFERRAL:.2f}$",
            reply_markup=reply_keyboard()
        )
    elif text == "💵 سحب":
        balance, _ = await get_balance(user.id)
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
    conn = await get_db()
    total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
    pending = await conn.fetchval("SELECT COUNT(*) FROM withdrawals WHERE status='pending'")
    await conn.close()
    await update.message.reply_text(
        f"📊 إحصائيات البوت:\n\n"
        f"👥 إجمالي المستخدمين: {total_users}\n"
        f"⏳ طلبات سحب معلقة: {pending}"
    )

def main():
    asyncio.get_event_loop().run_until_complete(init_db())
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    print("✅ البوت يعمل...")
    app.run_polling()

if __name__ == "__main__":
    main()
