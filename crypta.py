import random
import json
import os
from datetime import datetime, timezone
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent, LabeledPrice

BOT_TOKEN = os.environ.get("BOT_TOKEN")

LIMITS_FILE = "user_limits.json"
HISTORY_FILE = "user_history.json"
PREDICTIONS_FILE = "predictions.txt"
DAILY_LIMIT = 5
EXTRA_GEN = 5
PRICE_STARS = 5  # 1 Telegram Star

from aiohttp import web

async def handle(request):
    return web.Response(text="I'm alive!")

app = web.Application()
app.router.add_get("/", handle)


def load_predictions():
    with open(PREDICTIONS_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def load_limits():
    if not os.path.exists(LIMITS_FILE):
        return {}
    with open(LIMITS_FILE, "r") as f:
        return json.load(f)


def save_limits(limits):
    with open(LIMITS_FILE, "w") as f:
        json.dump(limits, f)


def get_today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_user_limit(user_id):
    limits = load_limits()
    today = get_today()
    user = str(user_id)
    if user not in limits or limits[user]["date"] != today:
        limits[user] = {"date": today, "left": DAILY_LIMIT}
        save_limits(limits)
    return limits[user]["left"]


def dec_user_limit(user_id):
    limits = load_limits()
    today = get_today()
    user = str(user_id)
    if user not in limits or limits[user]["date"] != today:
        limits[user] = {"date": today, "left": DAILY_LIMIT}
    if limits[user]["left"] > 0:
        limits[user]["left"] -= 1
    save_limits(limits)
    return limits[user]["left"]


def add_user_limit(user_id, count):
    limits = load_limits()
    today = get_today()
    user = str(user_id)
    if user not in limits or limits[user]["date"] != today:
        limits[user] = {"date": today, "left": DAILY_LIMIT}
    limits[user]["left"] += count
    save_limits(limits)
    return limits[user]["left"]


def load_user_history():
    if not os.path.exists(HISTORY_FILE):
        return {}
    with open(HISTORY_FILE, "r") as f:
        return json.load(f)


def save_user_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f)


def get_random_prediction(user_id):
    predictions = load_predictions()
    history = load_user_history()
    user = str(user_id)
    used = set(history.get(user, []))
    available = [i for i in range(len(predictions)) if i not in used]
    if not available:
        # Все предсказания показаны, сбрасываем историю
        history[user] = []
        save_user_history(history)
        available = list(range(len(predictions)))
    idx = random.choice(available)
    history.setdefault(user, []).append(idx)
    save_user_history(history)
    return predictions[idx]


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def main_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🎲 Случайное", callback_data="random")
    kb.button(text="👤 Личный кабинет", callback_data="profile")
    kb.button(text="ℹ️ О боте", callback_data="about")
    return kb.as_markup()


def profile_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="💫 Купить 5 генераций (1 Star)", callback_data="buy")
    kb.button(text="⬅️ Назад", callback_data="back")
    return kb.as_markup()


@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "Привет. Я бот для предсказаний про крипту.\n"
        "Жми кнопку или используй инлайн: @predcryptobot <жми на предсказание>",
        reply_markup=main_keyboard()
    )


@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "Жми кнопку или используй инлайн-режим: @predcryptobot <жми на предсказание>.\n"
        "Я генерирую крипто-предсказания для TON-комьюнити."
    )


@dp.callback_query(F.data == "random")
async def cb_random(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    left = get_user_limit(user_id)
    if left <= 0:
        await callback.message.edit_text(
            "У тебя закончились генерации на сегодня.\n"
            "Зайди в личный кабинет и купи ещё генераций или жди до завтра.",
            reply_markup=main_keyboard()
        )
        return
    await callback.message.edit_text("Генерирую...")
    result = get_random_prediction(user_id)
    dec_user_limit(user_id)
    await callback.message.edit_text(
        f"🔮 Предсказание:\n\n{result}\n\n"
        f"<span class=\"tg-spoiler\">Осталось генераций: {get_user_limit(user_id)}</span>",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )


@dp.callback_query(F.data == "profile")
async def cb_profile(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    left = get_user_limit(user_id)
    await callback.message.edit_text(
        f"👤 <b>Личный кабинет</b>\n\n"
        f"Осталось генераций: <b>{left}</b>\n"
        f"Лимит сбрасывается каждый день по UTC.\n\n"
        f"Если хочешь больше — купи генерации за Telegram Stars.",
        reply_markup=profile_keyboard(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "buy")
async def cb_buy(callback: types.CallbackQuery):
    prices = [LabeledPrice(label="5 генераций", amount=1)]  # 1 Star = 1 XTR
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Покупка генераций",
        description="Покупка 5 генераций для бота",
        payload="buy_generations",
        currency="XTR",
        prices=prices,
        start_parameter="buy_generations"
    )
    await callback.answer()


@dp.pre_checkout_query()
async def pre_checkout_query_handler(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@dp.message(F.successful_payment)
async def successful_payment_handler(message: types.Message):
    user_id = message.from_user.id
    add_user_limit(user_id, EXTRA_GEN)
    await message.answer(
        f"Спасибо за покупку! Тебе добавлено {EXTRA_GEN} генераций.\n"
        f"Осталось генераций: {get_user_limit(user_id)}",
        reply_markup=main_keyboard()
    )


@dp.callback_query(F.data == "back")
async def cb_back(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Привет. Я бот для предсказаний про TON.\n"
        "Жми кнопку или используй инлайн: @predcryptobot <жми на предсказание>",
        reply_markup=main_keyboard()
    )


@dp.callback_query(F.data == "about")
async def cb_about(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Генерирую предсказания для TON-комьюнити.\n"
        "Инлайн: @predcryptobot <жми на предсказание>.",
        reply_markup=main_keyboard()
    )


@dp.inline_query()
async def inline_query_handler(inline_query: types.InlineQuery):
    user_id = inline_query.from_user.id
    left = get_user_limit(user_id)
    if left <= 0:
        result = "У тебя закончились генерации на сегодня. Зайди в личный кабинет и купи ещё генераций или жди до завтра."
    else:
        result = get_random_prediction(user_id)
        dec_user_limit(user_id)
    results = [
        InlineQueryResultArticle(
            id="prediction",
            title="🔮 Предсказание",
            input_message_content=InputTextMessageContent(
                message_text=f"🔮 Предсказание:\n\n{result}\n\n"
                             f"<span class=\"tg-spoiler\">Осталось генераций: {get_user_limit(user_id)}</span>",
                parse_mode="HTML"
            ),
            description="Предсказание для тебя",
        ),
    ]
    await bot.answer_inline_query(inline_query.id, results, cache_time=1)


@dp.message()
async def on_user_message(message: types.Message):
    if message.text and message.text.startswith("🔮 Предсказание:"):
        user_id = message.from_user.id
        left = get_user_limit(user_id)
        if left > 0:
            dec_user_limit(user_id)
            await message.reply(
                f"<span class=\"tg-spoiler\">Осталось генераций: {get_user_limit(user_id)}</span>",
                parse_mode="HTML"
            )
        else:
            await message.reply(
                "У тебя закончились генерации на сегодня. Зайди в личный кабинет и купи ещё генераций или жди до завтра.",
                reply_markup=main_keyboard()
            )

from aiohttp import web

async def handle(request):
    return web.Response(text="I'm alive!")

async def start_web_app():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 3000)
    await site.start()

if __name__ == "__main__":
    import asyncio

    print("[main] Бот запускается...")

    async def main():
        await start_web_app()
        await dp.start_polling(bot)

    asyncio.run(main())
