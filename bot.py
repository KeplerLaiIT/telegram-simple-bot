import logging
import os
import sqlite3
import asyncio
import json
from datetime import datetime
from urllib.parse import quote, urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

DATABASE_PATH = "bot.db"
WEB_APP_URL = ""
MENU = ReplyKeyboardMarkup(
    [["👤 Личный кабинет", "🌤 Погода"], ["💱 Курсы валют", "❓ Помощь"]],
    resize_keyboard=True,
)
WEATHER_MENU = ReplyKeyboardMarkup(
    [["🏙 Город"], ["⬅️ Главное меню"]], resize_keyboard=True
)
PROFILE_MENU = ReplyKeyboardMarkup(
    [["✏️ Изменить имя"], ["⬅️ Главное меню"]],
    resize_keyboard=True,
)


def web_app_url_for_user(telegram_id: int) -> str:
    user = get_user(telegram_id)
    if not user or not WEB_APP_URL:
        return WEB_APP_URL
    first_name, username, _, _, timezone, profile_name, _ = user
    params = urlencode(
        {
            "profile_name": profile_name or first_name,
            "telegram_username": username or "",
            "timezone": timezone,
        }
    )
    separator = "&" if "?" in WEB_APP_URL else "?"
    return f"{WEB_APP_URL}{separator}{params}"


def menu_for_user(telegram_id: int) -> ReplyKeyboardMarkup:
    app_url = web_app_url_for_user(telegram_id)
    rows = []
    if app_url:
        rows.append([KeyboardButton("📱 Открыть приложение", web_app=WebAppInfo(app_url))])
    rows.extend([["👤 Личный кабинет", "🌤 Погода"], ["💱 Курсы валют", "❓ Помощь"]])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def profile_menu_for_user(telegram_id: int) -> ReplyKeyboardMarkup:
    app_url = web_app_url_for_user(telegram_id)
    rows = []
    if app_url:
        rows.append([KeyboardButton("📱 Открыть приложение", web_app=WebAppInfo(app_url))])
    rows.extend([["✏️ Изменить имя"], ["⬅️ Главное меню"]])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def init_database() -> None:
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT NOT NULL,
                city TEXT,
                timezone TEXT NOT NULL DEFAULT 'Europe/Moscow',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(users)")
        }
        if "city" not in columns:
            connection.execute("ALTER TABLE users ADD COLUMN city TEXT")
        if "timezone" not in columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN timezone TEXT NOT NULL DEFAULT 'Europe/Moscow'"
            )
        if "profile_name" not in columns:
            connection.execute("ALTER TABLE users ADD COLUMN profile_name TEXT")
        if "profile_username" not in columns:
            connection.execute("ALTER TABLE users ADD COLUMN profile_username TEXT")


def register_user(update: Update) -> None:
    user = update.effective_user
    if user is None:
        return

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            INSERT INTO users (telegram_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
            """,
            (user.id, user.username, user.first_name),
        )


def get_user(
    telegram_id: int,
) -> tuple[str, str, str, str | None, str, str | None, str | None] | None:
    with sqlite3.connect(DATABASE_PATH) as connection:
        return connection.execute(
            "SELECT first_name, username, created_at, city, timezone, "
            "profile_name, profile_username "
            "FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()


def save_profile_field(telegram_id: int, field: str, value: str) -> None:
    if field not in {"profile_name", "profile_username"}:
        raise ValueError("Недопустимое поле профиля")
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            f"UPDATE users SET {field} = ? WHERE telegram_id = ?",
            (value, telegram_id),
        )


def save_timezone(telegram_id: int, timezone: str) -> None:
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            "UPDATE users SET timezone = ? WHERE telegram_id = ?",
            (timezone, telegram_id),
        )


def format_local_datetime(created_at: str, timezone: str) -> str:
    try:
        local_zone = ZoneInfo(timezone)
    except KeyError:
        local_zone = ZoneInfo("Europe/Moscow")
    utc_time = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=ZoneInfo("UTC")
    )
    return utc_time.astimezone(local_zone).strftime("%d.%m.%Y %H:%M")


def save_city(telegram_id: int, city: str) -> None:
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            "UPDATE users SET city = ? WHERE telegram_id = ?",
            (city, telegram_id),
        )


def get_saved_city(telegram_id: int) -> str | None:
    with sqlite3.connect(DATABASE_PATH) as connection:
        result = connection.execute(
            "SELECT city FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
    return result[0] if result else None


async def fetch_json(url: str) -> dict:
    def request() -> dict:
        with urlopen(url, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    return await asyncio.to_thread(request)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    register_user(update)
    context.user_data.pop("editing_profile", None)
    await update.message.reply_text(
        "Привет! Ты зарегистрирован. Выбери действие в меню ниже.",
        reply_markup=menu_for_user(update.effective_user.id),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Доступные команды:\n"
        "/start - открыть меню и зарегистрироваться\n"
        "/help - показать помощь\n"
        "/city - изменить сохранённый город\n"
        "Кнопка «Погода» - получить прогноз по городу\n"
        "Кнопка «Курсы валют» - узнать курс валют к USD.",
        reply_markup=MENU,
    )


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    register_user(update)
    user = get_user(update.effective_user.id)
    if user is None:
        await update.message.reply_text("Не удалось найти профиль.", reply_markup=MENU)
        return

    first_name, username, created_at, city, timezone, profile_name, _ = user
    name_text = profile_name or first_name
    username_text = f"@{username}" if username else "не указан"
    city_text = city or "не указан"
    registration_time = format_local_datetime(created_at, timezone)
    await update.message.reply_text(
        f"👤 Личный кабинет\n\nИмя: {name_text}\n"
        f"Username: {username_text}\nГород: {city_text}\n"
        f"Дата регистрации: {registration_time}\n"
        f"Часовой пояс: {timezone}",
        reply_markup=profile_menu_for_user(update.effective_user.id),
    )


async def edit_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.text == "✏️ Изменить имя":
        context.user_data["editing_profile"] = "profile_name"
        prompt = "Напиши имя, которое нужно показывать в профиле."
    await update.message.reply_text(
        prompt, reply_markup=profile_menu_for_user(update.effective_user.id)
    )


async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    register_user(update)
    saved_city = get_saved_city(update.effective_user.id)
    if saved_city:
        await get_weather(update, saved_city)
        return

    await request_city(update, context)


async def request_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["waiting_for_city"] = True
    await update.message.reply_text(
        "Напиши название города, например: Москва. Его можно будет изменить командой /city.",
        reply_markup=WEATHER_MENU,
    )


async def city_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    register_user(update)
    await request_city(update, context)


async def get_weather(update: Update, city: str) -> None:
    try:
        location = await fetch_json(
            "https://geocoding-api.open-meteo.com/v1/search?"
            f"name={quote(city)}&count=1&language=ru&format=json"
        )
        results = location.get("results", [])
        if not results:
            await update.message.reply_text(
                f"Город «{city}» не найден. Проверь написание и попробуй ещё раз.",
                reply_markup=MENU,
            )
            return

        place = results[0]
        forecast = await fetch_json(
            "https://api.open-meteo.com/v1/forecast?"
            f"latitude={place['latitude']}&longitude={place['longitude']}"
            "&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code"
            "&timezone=auto"
        )
        current = forecast["current"]
        weather_codes = {
            0: "Ясно",
            1: "Преимущественно ясно",
            2: "Переменная облачность",
            3: "Пасмурно",
            45: "Туман",
            48: "Изморозь",
            51: "Лёгкая морось",
            61: "Небольшой дождь",
            63: "Дождь",
            65: "Сильный дождь",
            71: "Небольшой снег",
            73: "Снег",
            75: "Сильный снег",
            80: "Ливень",
            81: "Сильный ливень",
            82: "Очень сильный ливень",
            95: "Гроза",
            96: "Гроза с градом",
            99: "Сильная гроза с градом",
        }
        description = weather_codes.get(current["weather_code"], "Неизвестные условия")
        place_name = f"{place['name']}, {place.get('country', 'Россия')}"
        if update.effective_user:
            save_city(update.effective_user.id, place["name"])
        await update.message.reply_text(
            f"🌤 Погода в городе {place_name}:\n"
            f"{description}\n"
            f"Температура: {current['temperature_2m']} °C\n"
            f"Ощущается как: {current['apparent_temperature']} °C\n"
            f"Влажность: {current['relative_humidity_2m']}%",
            reply_markup=WEATHER_MENU,
        )
    except (KeyError, IndexError, OSError, TypeError, json.JSONDecodeError):
        await update.message.reply_text(
            "Не получилось получить погоду. Проверь название города и попробуй ещё раз.",
            reply_markup=WEATHER_MENU,
        )


async def rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        data = await fetch_json("https://open.er-api.com/v6/latest/USD")
        rates_data = data["rates"]
        usd_rub = rates_data["RUB"]
        eur_rub = usd_rub / rates_data["EUR"]
        kzt_rub = usd_rub / rates_data["KZT"]
        rub_kzt = rates_data["KZT"] / usd_rub
        await update.message.reply_text(
            "💱 Курсы валют к рублю:\n"
            f"1 USD = {usd_rub:.2f} RUB\n"
            f"1 EUR = {eur_rub:.2f} RUB\n\n"
            f"1 KZT = {kzt_rub:.2f} RUB\n"
            f"1 RUB = {rub_kzt:.4f} KZT\n\n"
            "Источник: open.er-api.com",
            reply_markup=MENU,
        )
    except (KeyError, OSError, json.JSONDecodeError):
        await update.message.reply_text(
            "Не получилось получить курсы валют. Попробуй позже.", reply_markup=MENU
        )


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    register_user(update)
    text = update.message.text

    if text == "⬅️ Главное меню":
        context.user_data.pop("waiting_for_city", None)
        context.user_data.pop("editing_profile", None)
        await start(update, context)
    elif text == "✏️ Изменить имя":
        await edit_profile(update, context)
    elif (field := context.user_data.pop("editing_profile", None)):
        if not text.strip():
            await update.message.reply_text(
                "Значение не может быть пустым.", reply_markup=PROFILE_MENU
            )
            return
        save_profile_field(update.effective_user.id, field, text.strip())
        await update.message.reply_text("Профиль обновлён.", reply_markup=PROFILE_MENU)
        await profile(update, context)
    elif text == "🏙 Город":
        await request_city(update, context)
    elif context.user_data.pop("waiting_for_city", False):
        await get_weather(update, text)
    elif text == "👤 Личный кабинет":
        await profile(update, context)
    elif text == "🌤 Погода":
        await weather(update, context)
    elif text == "💱 Курсы валют":
        await rates(update, context)
    elif text == "❓ Помощь":
        await help_command(update, context)
    else:
        await update.message.reply_text(
            "Выбери действие кнопкой меню или отправь /help.", reply_markup=MENU
        )


async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.effective_message.web_app_data:
        return
    try:
        data = json.loads(update.effective_message.web_app_data.data)
        timezone = data.get("timezone", "Europe/Moscow")
        ZoneInfo(timezone)
        profile_name = data.get("profile_name", "").strip()
    except (KeyError, TypeError, json.JSONDecodeError, ZoneInfoNotFoundError):
        await update.effective_message.reply_text(
            "Не удалось определить часовой пояс.", reply_markup=MENU
        )
        return

    register_user(update)
    save_timezone(update.effective_user.id, timezone)
    if profile_name:
        save_profile_field(update.effective_user.id, "profile_name", profile_name)
    await update.effective_message.reply_text(
        "Данные профиля и часовой пояс синхронизированы.",
        reply_markup=menu_for_user(update.effective_user.id),
    )


def main() -> None:
    load_dotenv()
    init_database()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Не найден TELEGRAM_BOT_TOKEN. Создайте файл .env и добавьте токен."
        )

    application = Application.builder().token(token).build()
    web_app_url = os.getenv("WEB_APP_URL")
    if web_app_url:
        global MENU, WEB_APP_URL
        WEB_APP_URL = web_app_url
        MENU = ReplyKeyboardMarkup(
            [
                [KeyboardButton("📱 Открыть приложение", web_app=WebAppInfo(web_app_url))],
                ["👤 Личный кабинет", "🌤 Погода"],
                ["💱 Курсы валют", "❓ Помощь"],
            ],
            resize_keyboard=True,
        )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("city", city_command))
    application.add_handler(
        MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data)
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler)
    )

    print("Бот запущен. Для остановки нажмите Ctrl+C.")
    application.run_polling()


if __name__ == "__main__":
    main()