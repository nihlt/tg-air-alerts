import asyncio
import shutil
import sys
from pathlib import Path
from telethon import TelegramClient
from telethon.tl.functions.channels import LeaveChannelRequest
from telethon.tl.types import Channel

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tg_telethon_io import (
    EXPORTS_DIR,
    PHOTOS_DIR,
    create_telegram_client,
    load_channels,
)

async def main():
    print("=== PROJECT CLEANUP & SYNC ===\n")
    
    # 1. Load new/current channels
    try:
        current_urls = load_channels()
    except Exception as exc:
        print(f"Error loading channels: {exc}")
        return
        
    current_usernames = set()
    for url in current_urls:
        u = url.strip().rstrip('/').split('/')[-1].lower()
        if u:
            current_usernames.add(u)
            
    print(f"Current channels in config: {len(current_usernames)}")
    
    # 2. Find old directories in exports/photos
    old_dirs = []
    if PHOTOS_DIR.exists():
        for path in PHOTOS_DIR.iterdir():
            if path.is_dir():
                name = path.name.lower()
                if name not in current_usernames:
                    old_dirs.append(path)
                    
    print(f"Found {len(old_dirs)} old channel photo folders to delete:")
    for d in old_dirs:
        print(f"  - {d.name}")
        
    # 3. Connect to Telegram to unsubscribe from these old channels
    if old_dirs:
        print("\nConnecting to Telegram to unsubscribe from old channels...")
        try:
            client = await create_telegram_client()
            for path in old_dirs:
                channel_name = path.name
                print(f"Leaving channel: {channel_name}...")
                try:
                    entity = await client.get_entity(channel_name)
                    if isinstance(entity, Channel):
                        await client(LeaveChannelRequest(entity))
                        print(f"  [left] {channel_name}")
                    else:
                        print(f"  [skip] {channel_name} (not a channel)")
                except Exception as exc:
                    print(f"  [error] could not leave {channel_name}: {exc}")
            await client.disconnect()
        except Exception as exc:
            print(f"Telegram client error: {exc}")
            
    # 4. Delete old channel folders
    print("\nDeleting old channel folders...")
    for d in old_dirs:
        try:
            shutil.rmtree(d)
            print(f"  Deleted folder: {d.name}")
        except Exception as exc:
            print(f"  Failed to delete folder {d.name}: {exc}")
            
    # 5. Delete old generated files
    files_to_delete = [
        "events.json",
        "events_report.txt",
        "markers_report.txt",
        "news.html",
        "tg_posts_live.jsonl",
    ]
    
    if EXPORTS_DIR.exists():
        for path in EXPORTS_DIR.iterdir():
            if path.is_file() and path.name.startswith("tg_posts_") and path.name.endswith(".jsonl"):
                files_to_delete.append(path.name)
            
    print("\nDeleting generated files...")
    for file_name in sorted(set(files_to_delete)):
        file_path = EXPORTS_DIR / file_name
        if file_path.exists():
            try:
                file_path.unlink()
                print(f"  Deleted file: {file_name}")
            except Exception as exc:
                print(f"  Failed to delete file {file_name}: {exc}")
                
    print("\nCleanup completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
