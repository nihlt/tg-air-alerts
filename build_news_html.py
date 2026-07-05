import json
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
EXPORTS_DIR = BASE_DIR / "exports"
INPUT_PATH = EXPORTS_DIR / "tg_posts_2026-07-01_1600_to_2026-07-02_0800.jsonl"
OUTPUT_PATH = EXPORTS_DIR / "news.html"


def load_posts() -> list[dict[str, Any]]:
    posts = []

    with INPUT_PATH.open("r", encoding="utf-8") as input_file:
        for line_number, line in enumerate(input_file, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                posts.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSON on line {line_number}: {exc}") from exc

    return posts


def sort_key(post: dict[str, Any]) -> tuple[datetime, str, int]:
    date_value = post.get("date_kyiv") or post.get("date_utc") or ""

    try:
        parsed_date = datetime.fromisoformat(date_value)
    except ValueError:
        parsed_date = datetime.min

    return (
        parsed_date,
        str(post.get("channel") or ""),
        int(post.get("message_id") or 0),
    )


def format_date(value: object) -> str:
    if not value:
        return "Unknown time"

    try:
        parsed_date = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)

    return parsed_date.strftime("%Y-%m-%d %H:%M:%S")


def render_text(post: dict[str, Any]) -> str:
    text = str(post.get("text") or "").strip()
    if not text and post.get("has_media"):
        text = "Без тексту"

    if not text:
        return ""

    return escape(text).replace("\n", "<br>")


def render_photo(post: dict[str, Any]) -> str:
    photo_path = post.get("photo_path")
    if not photo_path:
        return ""

    absolute_photo_path = BASE_DIR / str(photo_path)
    if not absolute_photo_path.exists():
        return ""

    relative_photo_path = absolute_photo_path.relative_to(OUTPUT_PATH.parent).as_posix()
    escaped_path = escape(relative_photo_path, quote=True)
    return f'<img class="message-photo" src="{escaped_path}" alt="Telegram post photo">'


def render_post(post: dict[str, Any]) -> str:
    channel = escape(str(post.get("channel") or "unknown"))
    channel_url = escape(str(post.get("channel_url") or "#"), quote=True)
    date_kyiv = escape(format_date(post.get("date_kyiv")))
    text_html = render_text(post)
    photo_html = render_photo(post)
    views = escape(str(post.get("views") if post.get("views") is not None else "-"))
    forwards = escape(str(post.get("forwards") if post.get("forwards") is not None else "-"))
    replies = escape(str(post.get("replies") if post.get("replies") is not None else "-"))
    message_id = escape(str(post.get("message_id") or "-"))

    text_block = f'<div class="message-text">{text_html}</div>' if text_html else ""

    return f"""<article class="message">
  <header class="message-header">
    <time>{date_kyiv}</time>
    <a href="{channel_url}" target="_blank" rel="noopener noreferrer">{channel}</a>
  </header>
  {text_block}
  {photo_html}
  <footer class="message-meta">views: {views} | forwards: {forwards} | replies: {replies} | id: {message_id}</footer>
</article>"""


def render_html(posts: list[dict[str, Any]]) -> str:
    rendered_posts = "\n".join(render_post(post) for post in posts)

    return f"""<!doctype html>
<html lang="uk">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Telegram News Timeline</title>
  <style>
    :root {{
      color-scheme: light dark;
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.5;
    }}
    body {{
      margin: 0;
      background: #f3f4f6;
      color: #111827;
    }}
    main {{
      max-width: 860px;
      margin: 0 auto;
      padding: 24px 16px 48px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
    }}
    .summary {{
      margin: 0 0 20px;
      color: #4b5563;
    }}
    .message {{
      margin: 0 0 14px;
      padding: 16px;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      background: #ffffff;
      box-shadow: 0 1px 2px rgb(0 0 0 / 6%);
    }}
    .message-header {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px 12px;
      justify-content: space-between;
      margin-bottom: 10px;
      color: #4b5563;
      font-size: 14px;
    }}
    .message-header a {{
      color: #2563eb;
      text-decoration: none;
      font-weight: 700;
    }}
    .message-text {{
      white-space: normal;
      overflow-wrap: anywhere;
      margin-bottom: 12px;
    }}
    .message-photo {{
      display: block;
      max-width: 100%;
      height: auto;
      margin: 12px 0;
      border-radius: 10px;
    }}
    .message-meta {{
      margin-top: 10px;
      color: #6b7280;
      font-size: 13px;
    }}
    @media (prefers-color-scheme: dark) {{
      body {{
        background: #111827;
        color: #f9fafb;
      }}
      .summary,
      .message-header,
      .message-meta {{
        color: #9ca3af;
      }}
      .message {{
        border-color: #374151;
        background: #1f2937;
      }}
      .message-header a {{
        color: #93c5fd;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>Telegram News Timeline</h1>
    <p class="summary">Повідомлень: {len(posts)}. Сортування: від ранніх до пізніх за київським часом.</p>
    {rendered_posts}
  </main>
</body>
</html>
"""


def main() -> None:
    posts = sorted(load_posts(), key=sort_key)
    OUTPUT_PATH.write_text(render_html(posts), encoding="utf-8", newline="\n")
    print(f"Read {len(posts)} posts from {INPUT_PATH}")
    print(f"Wrote HTML to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
