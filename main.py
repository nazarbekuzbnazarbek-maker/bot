import asyncio
import random
import string
from typing import Dict, List, Set
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from pydantic import BaseModel

BOT_TOKEN = "9098001352:AAGsUGdQxNKAYE_XfbvGCvBKs_gjbYEWBc8"  # @BotFather'dan olingan token
ADMIN_IDS: List[int] = [8052376816]  # O'zingizning Telegram ID'ingizni kiriting

app = FastAPI()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# CORS sozlamalari
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ma'lumotlar ombori (Xotirada — Real loyihada PostgreSQL yoki SQLite ishlatish tavsiya etiladi)
pending_sessions: Dict[str, dict] = {}
# Har bir sessiya strukturasi: {session_id: {"code": "1234", "verified": False, "telegram_id": None}}

# Statik va Majburiy Obunalar
bot_users: Set[int] = set()  # Barcha kirganlar
blocked_users: Set[int] = set()  # Botni bloklaganlar
mandatory_channels: List[dict] = []  # [{"channel_id": "-100123456789", "link": "https://t.me/+DmwB_aMw8X40YzYy"}]


def generate_code(length=4) -> str:
    return ''.join(random.choices(string.digits, k=length))


# ----------------- FASTAPI ENDPOINTS -----------------

class RequestCodeModel(BaseModel):
    session_id: str


class VerifyCodeModel(BaseModel):
    session_id: str
    code: str


@app.post("/api/request-code")
async def request_code(data: RequestCodeModel):
    code = generate_code()
    pending_sessions[data.session_id] = {
        "code": code,
        "verified": False,
        "telegram_id": None
    }
    bot_info = await bot.get_me()
    bot_link = f"https://t.me/{bot_info.username}?start={data.session_id}"
    return {"bot_link": bot_link, "session_id": data.session_id}


@app.post("/api/verify-code")
async def verify_code(data: VerifyCodeModel):
    session = pending_sessions.get(data.session_id)
    if not session:
        raise HTTPException(status_code=400, detail="Sessiya topilmadi yoki muddati o'tdi")

    if session["code"] == data.code:
        session["verified"] = True
        return {"status": "success", "message": "Kod muvaffaqiyatli tasdiqlandi!"}
    else:
        raise HTTPException(status_code=400, detail="Kod xato kiritildi!")


# ----------------- BOT LOGIKASI & MAJBURIY OBUNA -----------------

async def check_subscriptions(user_id: int) -> tuple[bool, InlineKeyboardMarkup]:
    """Foydalanuvchi majburiy kanallarga a'zoligini tekshiradi"""
    unsubscribed_channels = []
    keyboard_buttons = []

    for ch in mandatory_channels:
        try:
            member = await bot.get_chat_member(chat_id=ch["channel_id"], user_id=user_id)
            if member.status in ["left", "kicked"]:
                unsubscribed_channels.append(ch)
                keyboard_buttons.append([InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=ch["link"])])
        except Exception:
            # Agar bot kanalda admin bo'lmasa yoki kanal topilmasa
            continue

    if unsubscribed_channels:
        # Tekshirish tugmasi
        keyboard_buttons.append([InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub")])
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        return False, markup

    return True, None


@dp.message(CommandStart())
async def start_handler(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    bot_users.add(user_id)
    if user_id in blocked_users:
        blocked_users.remove(user_id)

    session_id = command.args

    if session_id and session_id in pending_sessions:
        pending_sessions[session_id]["telegram_id"] = user_id

        # Majburiy obunani tekshirish
        is_subscribed, markup = await check_subscriptions(user_id)
        if not is_subscribed:
            await message.answer(
                "⚠️ **Botdan foydalanish va kodni olish uchun quyidagi kanallarga obuna bo'ling:**",
                reply_markup=markup,
                parse_mode="Markdown"
            )
            return

        # Obuna bo'lgan bo'lsa kod yuboriladi
        code = pending_sessions[session_id]["code"]
        await message.answer(
            f"🔑 **KunlikIsh.uz** platformasi uchun tasdiqlash kodingiz:\n\n"
            f"👉 `{code}` 👈\n\n"
            f"Ushbu kodni saytga kiriting.",
            parse_mode="Markdown"
        )
    else:
        await message.answer("👋 Xush kelibsiz! Kod olish uchun platformamiz orqali o'ting.")


@dp.callback_query(F.data == "check_sub")
async def check_subscription_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_subscribed, markup = await check_subscriptions(user_id)

    if not is_subscribed:
        await callback.answer("❌ Hali barcha kanallarga obuna bo'lmadingiz!", show_alert=True)
    else:
        await callback.message.delete()

        # Foydalanuvchining aktiv sessiyasini topish
        user_session = None
        for s_id, data in pending_sessions.items():
            if data["telegram_id"] == user_id and not data["verified"]:
                user_session = data
                break

        if user_session:
            code = user_session["code"]
            await callback.message.answer(
                f"✅ Obuna tasdiqlandi!\n\n🔑 Tasdiqlash kodingiz: `{code}`",
                parse_mode="Markdown"
            )
        else:
            await callback.message.answer("✅ Obuna tasdiqlandi! Endi saytdan qayta kod so'rashingiz mumkin.")


# ----------------- ADMIN PANEL -----------------

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton(text="➕ Majburiy kanal qo'shish", callback_data="admin_add_channel")],
        [InlineKeyboardButton(text="🗑 Kanallar ro'yxati / O'chirish", callback_data="admin_list_channels")]
    ])

    await message.answer("👨‍💻 **Admin Panel paneli:**", reply_markup=admin_keyboard, parse_mode="Markdown")


@dp.callback_query(F.data == "admin_stats")
async def admin_stats_callback(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return

    # Faollar va bloklaganlarni aniqlash
    total = len(bot_users)
    active = 0
    blocked = 0

    for u_id in list(bot_users):
        try:
            await bot.send_chat_action(chat_id=u_id, action="typing")
            active += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            blocked += 1
            blocked_users.add(u_id)

    stats_text = (
        f"📊 **BOT STATISTIKASI:**\n\n"
        f"👤 Jami tashrif buyurganlar: **{total}**\n"
        f"🟢 Faol foydalanuvchilar: **{active}**\n"
        f"🔴 Botni tark etganlar/bloklaganlar: **{blocked}**"
    )
    await callback.message.edit_text(stats_text, parse_mode="Markdown", reply_markup=callback.message.reply_markup)


@dp.callback_query(F.data == "admin_add_channel")
async def admin_add_channel_prompt(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return

    await callback.message.answer(
        "📝 **Yangi majburiy kanal qo'shish uchun ma'lumotni quyidagi formatda yuboring:**\n\n"
        "`/addchannel -100123456789 https://t.me/kanal_linki`\n\n"
        "⚠️ *Bot ushbu kanalda ADMIN huquqiga ega bo'lishi shart!*",
        parse_mode="Markdown"
    )
    await callback.answer()


@dp.message(Command("addchannel"))
async def add_channel_command(message: types.Message, command: CommandObject):
    if message.from_user.id not in ADMIN_IDS:
        return

    args = command.args.split() if command.args else []
    if len(args) < 2:
        await message.answer("❌ Noto'g'ri format! Misol: `/addchannel -100123456789 https://t.me/kanal_linki`",
                             parse_mode="Markdown")
        return

    channel_id, link = args[0], args[1]
    mandatory_channels.append({"channel_id": channel_id, "link": link})
    await message.answer(f"✅ Kanal muvaffaqiyatli qo'shildi!\nID: `{channel_id}`", parse_mode="Markdown")


@dp.callback_query(F.data == "admin_list_channels")
async def admin_list_channels(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return

    if not mandatory_channels:
        await callback.answer("Hozircha majburiy kanallar yo'q.", show_alert=True)
        return

    msg = "📢 **Majburiy kanallar ro'yxati:**\n\n"
    for idx, ch in enumerate(mandatory_channels, 1):
        msg += f"{idx}. ID: `{ch['channel_id']}` | [Link]({ch['link']})\n"

    await callback.message.edit_text(msg, parse_mode="Markdown", disable_web_page_preview=True)


# Startup process
@app.on_event("startup")
async def on_startup():
    asyncio.create_task(dp.start_polling(bot))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)