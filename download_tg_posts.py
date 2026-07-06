import asyncio
import json
import sys
from datetime import datetime, timezone

from telethon import TelegramClient

from tg_telethon_io import (
    EXPORTS_DIR,
    KYIV_TZ,
    PHOTOS_DIR,
    channel_folder_name,
    create_telegram_client,
    download_photo,
    ensure_export_dirs,
    load_channels,
    message_to_record,
)

OUTPUT_PATH = EXPORTS_DIR / "tg_posts_2026-07-01_1600_to_2026-07-02_0800.jsonl"

START_KYIV = datetime(2026, 7, 1, 16, 0, tzinfo=KYIV_TZ)
END_KYIV = datetime(2026, 7, 2, 8, 0, tzinfo=KYIV_TZ)
START_UTC = START_KYIV.astimezone(timezone.utc)
END_UTC = END_KYIV.astimezone(timezone.utc)


async def export_channel(client: TelegramClient, channel_url: str, output_file) -> int:
    entity = await client.get_entity(channel_url)
    channel_dir = PHOTOS_DIR / channel_folder_name(entity)
    exported_count = 0

    async for message in client.iter_messages(entity):
        message_date_utc = message.date.astimezone(timezone.utc)

        if message_date_utc >= END_UTC:
            continue

        if message_date_utc < START_UTC:
            break

        photo_path = await download_photo(message, channel_dir, channel_url)
        record = message_to_record(channel_url, message, photo_path)
        output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        exported_count += 1

    return exported_count


async def main() -> None:
    channels = load_channels()
    ensure_export_dirs()

    client = await create_telegram_client()

    try:
        total_exported = 0

        with OUTPUT_PATH.open("w", encoding="utf-8", newline="\n") as output_file:
            for channel_url in channels:
                try:
                    count = await export_channel(client, channel_url, output_file)
                except Exception as exc:
                    print(f"[warn] {channel_url}: {exc}", file=sys.stderr)
                    continue

                total_exported += count
                print(f"[ok] {channel_url}: exported {count} posts")
    finally:
        await client.disconnect()

    print(f"Done. Exported {total_exported} posts to {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
