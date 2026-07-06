from __future__ import annotations

import json
import logging
import mimetypes
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from tg_data import BASE_DIR, enrich_event_posts, enrich_post
from tg_format import format_event_text, format_summary_text
from tg_data import TimelineItem

ENV_PATH = BASE_DIR / ".env"
SEND_PAUSE_SECONDS = 0.4
logger = logging.getLogger(__name__)


def load_bot_token(env_path: Path = ENV_PATH) -> str:
    config = dotenv_values(env_path)
    token = (config.get("TG_BOT_TOKEN") or config.get("bot_token") or "").strip().strip('"')
    if not token:
        raise RuntimeError(f"Missing TG_BOT_TOKEN in {env_path}")
    return token


def load_bot_config(env_path: Path = ENV_PATH) -> tuple[str, str]:
    config = dotenv_values(env_path)
    token = load_bot_token(env_path)
    chat_id = (config.get("TELEGRAM_AUTHOR") or config.get("telegram_user_id") or "").strip()
    if not chat_id:
        raise RuntimeError(f"Missing TELEGRAM_AUTHOR in {env_path}")
    return token, chat_id


@dataclass(frozen=True)
class PhotoItem:
    path: Path
    channel: str
    message_id: int | str


class TelegramBot:
    def __init__(self, token: str, chat_id: str = "") -> None:
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"

    def for_chat(self, chat_id: str) -> TelegramBot:
        return TelegramBot(self.token, str(chat_id))

    def _api(
        self,
        method: str,
        data: dict[str, Any] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        *,
        include_chat_id: bool = True,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{method}"
        payload = dict(data or {})
        if include_chat_id:
            payload["chat_id"] = self.chat_id

        if files:
            boundary = f"----tgairalerts{uuid.uuid4().hex}"
            body = self._encode_multipart(payload, files, boundary)
            request = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
        else:
            encoded = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                url,
                data=encoded,
                headers={"Content-Type": "application/json"},
            )

        import ssl
        context = ssl._create_unverified_context()
        try:
            with urllib.request.urlopen(request, timeout=60, context=context) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Telegram API error {exc.code} for {method}: {error_body}") from exc

        if not body.get("ok"):
            raise RuntimeError(f"Telegram API returned error for {method}: {body}")
        return body

    @staticmethod
    def _encode_multipart(
        fields: dict[str, Any],
        files: dict[str, tuple[str, bytes, str]],
        boundary: str,
    ) -> bytes:
        lines: list[bytes] = []

        def add_line(line: bytes) -> None:
            lines.append(line)

        for name, value in fields.items():
            if value is None:
                continue
            add_line(f"--{boundary}\r\n".encode())
            add_line(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
            add_line(f"{value}\r\n".encode())

        for name, (filename, content, content_type) in files.items():
            add_line(f"--{boundary}\r\n".encode())
            add_line(
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{filename}"\r\n'
                ).encode()
            )
            add_line(f"Content-Type: {content_type}\r\n\r\n".encode())
            add_line(content)
            add_line(b"\r\n")

        add_line(f"--{boundary}--\r\n".encode())
        return b"".join(lines)

    def send_message(
        self,
        text: str,
        *,
        parse_mode: str = "HTML",
        reply_markup: dict[str, Any] | str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = (
                reply_markup if isinstance(reply_markup, str) else json.dumps(reply_markup)
            )
        return self._api("sendMessage", payload)

    def edit_message_reply_markup(
        self,
        message_id: int,
        *,
        reply_markup: dict[str, Any] | str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"message_id": message_id}
        if reply_markup is not None:
            payload["reply_markup"] = (
                reply_markup if isinstance(reply_markup, str) else json.dumps(reply_markup)
            )
        return self._api("editMessageReplyMarkup", payload)

    def answer_callback_query(
        self,
        callback_query_id: str,
        *,
        text: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        return self._api("answerCallbackQuery", payload, include_chat_id=False)

    def send_photo(
        self,
        path: Path,
        *,
        caption: str | None = None,
        parse_mode: str = "HTML",
        reply_markup: dict[str, Any] | str | None = None,
    ) -> dict[str, Any]:
        content = path.read_bytes()
        mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        files = {"photo": (path.name, content, mime_type)}
        data: dict[str, Any] = {}
        if caption:
            data["caption"] = caption
            data["parse_mode"] = parse_mode
        if reply_markup is not None:
            data["reply_markup"] = (
                reply_markup if isinstance(reply_markup, str) else json.dumps(reply_markup)
            )
        return self._api("sendPhoto", data, files=files)

    def send_media_group(
        self,
        items: list[PhotoItem],
        *,
        caption: str | None = None,
        parse_mode: str = "HTML",
    ) -> dict[str, Any]:
        if not items:
            raise ValueError("send_media_group requires at least one photo")
        if len(items) > 10:
            raise ValueError("send_media_group supports at most 10 photos")

        media: list[dict[str, Any]] = []
        files: dict[str, tuple[str, bytes, str]] = {}
        for index, item in enumerate(items):
            attach_name = f"photo{index}"
            content = item.path.read_bytes()
            mime_type = mimetypes.guess_type(item.path.name)[0] or "image/jpeg"
            files[attach_name] = (item.path.name, content, mime_type)
            entry: dict[str, Any] = {
                "type": "photo",
                "media": f"attach://{attach_name}",
            }
            if index == 0 and caption:
                entry["caption"] = caption
                entry["parse_mode"] = parse_mode
            media.append(entry)

        return self._api(
            "sendMediaGroup",
            {"media": json.dumps(media)},
            files=files,
        )

    def get_updates(self, *, offset: int | None = None, timeout: int = 30) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        body = self._api("getUpdates", payload, include_chat_id=False)
        return list(body.get("result") or [])


def collect_photos(
    enriched_posts: list[dict[str, Any]],
    base_dir: Path = BASE_DIR,
) -> list[dict[str, Any]]:
    photos: list[dict[str, Any]] = []
    for post in enriched_posts:
        photo_path = post.get("photo_path")
        if not photo_path:
            continue
        absolute_path = base_dir / str(photo_path)
        if not absolute_path.exists():
            logger.warning("Missing photo file: %s", absolute_path)
            continue
        photos.append(
            {
                "path": absolute_path,
                "channel": str(post.get("channel") or ""),
                "message_id": post.get("message_id"),
                "post": post,
            }
        )
    return photos


def chunk_photos(photos: list[dict[str, Any]], size: int = 10) -> list[list[dict[str, Any]]]:
    return [photos[index : index + size] for index in range(0, len(photos), size)]


def _pause() -> None:
    time.sleep(SEND_PAUSE_SECONDS)


def _extract_message_id(response: dict[str, Any]) -> int | None:
    result = response.get("result")
    if isinstance(result, list):
        if not result:
            return None
        return int(result[-1]["message_id"])
    if isinstance(result, dict) and "message_id" in result:
        return int(result["message_id"])
    return None


def send_photos_for_posts(
    bot: TelegramBot,
    enriched_posts: list[dict[str, Any]],
    *,
    base_dir: Path = BASE_DIR,
) -> None:
    photos = collect_photos(enriched_posts, base_dir=base_dir)
    if not photos:
        return

    batches = chunk_photos(photos)
    for batch in batches:
        photo_items = [
            PhotoItem(
                path=item["path"],
                channel=item["channel"],
                message_id=item["message_id"],
            )
            for item in batch
        ]
        if len(photo_items) == 1:
            bot.send_photo(photo_items[0].path)
        else:
            bot.send_media_group(photo_items)
        _pause()


def send_event_alert(
    bot: TelegramBot,
    event: dict[str, Any],
    posts_index: dict[str, dict[str, Any]],
    *,
    debug: bool = False,
    debug_meta: tuple[TimelineItem, int, int] | None = None,
    base_dir: Path = BASE_DIR,
    reply_markup: dict[str, Any] | None = None,
) -> int | None:
    text = format_event_text(
        event,
        posts_index,
        debug=debug,
        debug_meta=debug_meta,
    )
    enriched_posts = enrich_event_posts(event, posts_index)
    send_photos_for_posts(bot, enriched_posts, base_dir=base_dir)
    response = bot.send_message(text, reply_markup=reply_markup)
    _pause()
    return _extract_message_id(response)


def send_summary_alert(
    bot: TelegramBot,
    post: dict[str, Any],
    posts_index: dict[str, dict[str, Any]],
    *,
    debug: bool = False,
    debug_meta: tuple[TimelineItem, int, int] | None = None,
    base_dir: Path = BASE_DIR,
    reply_markup: dict[str, Any] | None = None,
) -> int | None:
    enriched = enrich_post(post, posts_index)
    text = format_summary_text(enriched)
    if debug and debug_meta is not None:
        from tg_format import escape_html, format_debug_footer

        text = f"{text}\n\n{escape_html(format_debug_footer(*debug_meta))}"
    send_photos_for_posts(bot, [enriched], base_dir=base_dir)
    response = bot.send_message(text, reply_markup=reply_markup)
    _pause()
    return _extract_message_id(response)
