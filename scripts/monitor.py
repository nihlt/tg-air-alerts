"""
monitor.py — моніторинг Telegram-каналів через Telethon.

Читає список каналів з tg-list-channels.csv, підключається як звичайний
користувач і виводить нові повідомлення в реальному часі.

Нові повідомлення пересилаються власнику у чат з ботом.
Хук process_message() готовий для підключення OpenAI / Gemini.
"""

import asyncio
import csv
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)

# ──────────────────────────────────────────────────────────────────────────────
# Налаштування логування
# ──────────────────────────────────────────────────────────────────────────────

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FMT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FMT,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("monitor.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("tg-monitor")

# ──────────────────────────────────────────────────────────────────────────────
# Константи
# ──────────────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
CHANNELS_CSV = BASE_DIR / "tg-list-channels.csv"
SESSION_FILE = BASE_DIR / "monitor_session"

load_dotenv(BASE_DIR / ".env")

API_ID: int = int(os.environ["api_id"])
API_HASH: str = os.environ["api_hash"]
PHONE: str | None = os.getenv("phone")
BOT_TOKEN: str = os.environ["TG_BOT_TOKEN"]
OWNER_ID: int = int(os.environ["TELEGRAM_AUTHOR"])


# ──────────────────────────────────────────────────────────────────────────────
# Допоміжні функції
# ──────────────────────────────────────────────────────────────────────────────

def load_channels(csv_path: Path) -> list[str]:
    """
    Зчитує список каналів з CSV-файлу.

    Формат рядка: https://t.me/<username>\\t<emoji>
    Повертає список username'ів (без https://t.me/).
    """
    channels: list[str] = []
    try:
        with csv_path.open(encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t")
            for row in reader:
                if not row:
                    continue
                url = row[0].strip()
                # витягуємо username з URL або приймаємо як є
                match = re.search(r"t\.me/([A-Za-z0-9_+]+)", url)
                if match:
                    channels.append(match.group(1))
                elif url and not url.startswith("http"):
                    channels.append(url)
    except FileNotFoundError:
        log.error("Файл каналів не знайдено: %s", csv_path)
    except Exception as exc:
        log.exception("Помилка читання CSV: %s", exc)
    return channels


def build_message_link(chat_username: str | None, chat_id: int, msg_id: int) -> str | None:
    """Повертає посилання на конкретне повідомлення."""
    if chat_username:
        return f"https://t.me/{chat_username}/{msg_id}"
    # для приватних каналів — посилання c/
    pure_id = str(abs(chat_id)).removeprefix("100")
    return f"https://t.me/c/{pure_id}/{msg_id}"


# ──────────────────────────────────────────────────────────────────────────────
# Хук для AI-аналізу (OpenAI / Gemini тощо)
# ──────────────────────────────────────────────────────────────────────────────

async def process_message(channel_name: str, message_text: str) -> None:
    """
    Викликається для кожного нового повідомлення.

    Тут можна підключити аналіз загроз через OpenAI або Gemini:

        response = await openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ти аналітик загроз..."},
                {"role": "user", "content": message_text},
            ],
        )
        threat_level = response.choices[0].message.content
        log.info("[AI] %s → %s", channel_name, threat_level)
    """
    pass  # TODO: додати AI-аналіз


# ──────────────────────────────────────────────────────────────────────────────
# Основна логіка
# ──────────────────────────────────────────────────────────────────────────────

async def resolve_channels(
    client: TelegramClient, usernames: list[str]
) -> dict[int, str]:
    """
    Резолвить username'и в entity та повертає {chat_id: channel_name}.
    Пропускає недоступні або невалідні канали.
    """
    resolved: dict[int, str] = {}
    for username in usernames:
        try:
            entity = await client.get_entity(username)
            chat_id = entity.id
            name = getattr(entity, "title", username)
            resolved[chat_id] = name
            log.info("✅  Підключено: %s (%s)", name, username)
        except (UsernameInvalidError, UsernameNotOccupiedError):
            log.warning("⚠️  Невалідний або неіснуючий канал: %s", username)
        except ChannelPrivateError:
            log.warning("🔒  Канал приватний або ви не підписані: %s", username)
        except FloodWaitError as e:
            log.warning("⏳  Flood wait %d с — пропускаємо %s", e.seconds, username)
            await asyncio.sleep(e.seconds)
        except Exception as exc:
            log.exception("❌  Не вдалось підключитись до %s: %s", username, exc)
    return resolved


async def main() -> None:
    channels_usernames = load_channels(CHANNELS_CSV)
    if not channels_usernames:
        log.error("Список каналів порожній. Перевірте %s", CHANNELS_CSV)
        return

    log.info("Завантажено %d каналів з CSV", len(channels_usernames))

    # Клієнт-користувач — слухає канали
    user_client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    await user_client.start(phone=PHONE)
    me = await user_client.get_me()
    log.info("Авторизовано як: %s (id=%s)", me.username or me.first_name, me.id)

    # Бот-клієнт — надсилає повідомлення власнику
    bot_client = TelegramClient(str(BASE_DIR / "bot_session"), API_ID, API_HASH)
    await bot_client.start(bot_token=BOT_TOKEN)
    log.info("Бот-клієнт запущено")

    # Резолвимо канали
    channel_map: dict[int, str] = await resolve_channels(user_client, channels_usernames)
    if not channel_map:
        log.error("Жоден канал не вдалось підключити. Завершення.")
        await user_client.disconnect()
        await bot_client.disconnect()
        return

    log.info(
        "Моніторинг активний для %d каналів. Очікую повідомлення…",
        len(channel_map),
    )

    # Підтвердження старту у чат з ботом
    channel_list = "\n".join(f"  • {name}" for name in channel_map.values())
    await bot_client.send_message(
        OWNER_ID,
        f"✅ *Монітор запущено*\n"
        f"📡 Відстежую {len(channel_map)} каналів:\n{channel_list}",
        parse_mode="md",
    )

    # ──────────────────────────────────────────────────────────────────────────
    # Обробник нових повідомлень
    # ──────────────────────────────────────────────────────────────────────────

    @user_client.on(events.NewMessage(chats=list(channel_map.keys())))
    async def new_message_handler(event: events.NewMessage.Event) -> None:
        try:
            msg = event.message
            chat = await event.get_chat()

            channel_name: str = channel_map.get(
                chat.id, getattr(chat, "title", str(chat.id))
            )
            message_text: str = msg.text or ""
            msg_date: datetime = msg.date.astimezone(timezone.utc)

            chat_username: str | None = getattr(chat, "username", None)
            link = build_message_link(chat_username, chat.id, msg.id)

            # ── Виводимо в консоль ──────────────────────────────────────────
            separator = "─" * 60
            log.info(
                "\n%s\n📢  Канал     : %s\n🕐  Час       : %s\n📝  Текст     : %s\n🔗  Посилання : %s\n%s",
                separator,
                channel_name,
                msg_date.strftime("%Y-%m-%d %H:%M:%S UTC"),
                message_text[:500] + ("…" if len(message_text) > 500 else ""),
                link or "недоступне",
                separator,
            )

            # ── Надсилаємо у чат з ботом ────────────────────────────────────
            text_preview = message_text[:1000] + ("…" if len(message_text) > 1000 else "")
            link_line = f"\n🔗 {link}" if link else ""
            notification = (
                f"📢 *{channel_name}*\n"
                f"🕐 {msg_date.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
                f"{text_preview}"
                f"{link_line}"
            )
            try:
                await bot_client.send_message(OWNER_ID, notification, parse_mode="md")
            except Exception as send_exc:
                log.warning("Не вдалось надіслати повідомлення боту: %s", send_exc)

            # ── AI-аналіз (хук) ────────────────────────────────────────────
            if message_text:
                await process_message(channel_name, message_text)

        except FloodWaitError as e:
            log.warning("FloodWait — чекаємо %d секунд", e.seconds)
            await asyncio.sleep(e.seconds)
        except Exception as exc:
            log.exception("Помилка обробки повідомлення: %s", exc)

    # Тримаємо обидва клієнти живими до Ctrl+C
    try:
        await asyncio.gather(
            user_client.run_until_disconnected(),
            bot_client.run_until_disconnected(),
        )
    except KeyboardInterrupt:
        log.info("Зупинено користувачем (Ctrl+C)")
    finally:
        await user_client.disconnect()
        await bot_client.disconnect()
        log.info("З'єднання закрито.")


# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    asyncio.run(main())
