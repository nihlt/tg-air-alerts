import json
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
EXPORTS_DIR = BASE_DIR / "exports"
OUTPUT_PATH = EXPORTS_DIR / "news.html"
CHANNELS_PATH = BASE_DIR / "tg-chanel-links.txt"


def load_allowed_channels() -> set[str]:
    if not CHANNELS_PATH.exists():
        return set()
    
    allowed = set()
    for line in CHANNELS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            url = line.lower().rstrip("/")
            allowed.add(url)
            if "t.me/" in url:
                username = url.split("t.me/")[-1]
                allowed.add(username)
    return allowed


def load_posts() -> list[dict[str, Any]]:
    posts = []
    jsonl_files = list(EXPORTS_DIR.glob("tg_posts_*.jsonl"))

    if not jsonl_files:
        raise RuntimeError(f"No tg_posts_*.jsonl files found in {EXPORTS_DIR}")

    for jsonl_file in jsonl_files:
        with jsonl_file.open("r", encoding="utf-8") as input_file:
            for line_number, line in enumerate(input_file, start=1):
                line = line.strip()
                if not line:
                    continue

                try:
                    posts.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"Invalid JSON in {jsonl_file.name} on line {line_number}: {exc}") from exc

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


UKRAINIAN_MONTHS = {
    1: "січня",
    2: "лютого",
    3: "березня",
    4: "квітня",
    5: "травня",
    6: "червня",
    7: "липня",
    8: "серпня",
    9: "вересня",
    10: "жовтня",
    11: "листопада",
    12: "грудня",
}


def format_date_ua(parsed_date: datetime) -> str:
    day = parsed_date.day
    month = UKRAINIAN_MONTHS.get(parsed_date.month, "")
    year = parsed_date.year
    return f"{day} {month} {year}"


def format_number(val: int) -> str:
    return f"{val:,}".replace(",", " ")


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


def get_categories_and_badges(text: str) -> tuple[list[str], str]:
    categories = []
    badges = []
    text_lower = text.lower()
    
    if "тривог" in text_lower:
        categories.append("alert")
        badges.append('<span class="badge badge-alert">🚨 Тривога</span>')
    if "відбій" in text_lower:
        categories.append("clear")
        badges.append('<span class="badge badge-clear">✅ Відбій</span>')
    if "вибух" in text_lower:
        categories.append("explosion")
        badges.append('<span class="badge badge-explosion">💥 Вибух</span>')
    if any(k in text_lower for k in ["пуск", "виліт", "ракет", "шахед", "шахід", "бпла", "камикадзе", "калібр", "іскандер", "кинджал", "ту-95"]):
        categories.append("launch")
        badges.append('<span class="badge badge-launch">🚀 Загроза / Пуск</span>')
        
    return categories, " ".join(badges)


def render_post(post: dict[str, Any]) -> str:
    channel = escape(str(post.get("channel") or "unknown"))
    channel_url = escape(str(post.get("channel_url") or "#"), quote=True)
    date_kyiv = escape(format_date(post.get("date_kyiv")))
    text_html = render_text(post)
    photo_html = render_photo(post)
    
    categories, badges_markup = get_categories_and_badges(str(post.get("text") or ""))
    badges_html = f'<div class="message-badges">{badges_markup}</div>' if badges_markup else ""
    
    views_count = post.get("views")
    views = escape(str(views_count)) if views_count is not None else "0"
    
    forwards_count = post.get("forwards")
    forwards = escape(str(forwards_count)) if forwards_count is not None else "0"
    
    replies_count = post.get("replies")
    replies = escape(str(replies_count)) if replies_count is not None else "0"
    
    message_id = escape(str(post.get("message_id") or "-"))

    text_block = f'<div class="message-text">{text_html}</div>' if text_html else ""

    # ISO date for data attributes
    date_val = post.get("date_kyiv") or post.get("date_utc") or ""
    date_iso = ""
    try:
        date_iso = datetime.fromisoformat(date_val).date().isoformat()
    except ValueError:
        pass

    # SVG Icons
    eye_svg = '<svg class="meta-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>'
    share_svg = '<svg class="meta-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" x2="12" y1="2" y2="15"/></svg>'
    reply_svg = '<svg class="meta-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>'
    hash_svg = '<svg class="meta-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" x2="20" y1="9" y2="9"/><line x1="4" x2="20" y1="15" y2="15"/><line x1="10" x2="8" y1="3" y2="21"/><line x1="16" x2="14" y1="3" y2="21"/></svg>'
    external_link_svg = '<svg class="link-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" x2="21" y1="14" y2="3"/></svg>'

    return f"""<article class="message" data-date="{date_iso}" data-channel="{channel}" data-categories="{','.join(categories)}">
  <header class="message-header">
    <div class="channel-info">
      <a href="{channel_url}" target="_blank" rel="noopener noreferrer" class="channel-link">
        <span class="channel-name">{channel}</span>
        {external_link_svg}
      </a>
    </div>
    <time class="message-time">{date_kyiv}</time>
  </header>
  {badges_html}
  {text_block}
  {photo_html}
  <footer class="message-meta">
    <div class="meta-item" title="Views">
      {eye_svg}
      <span>{views}</span>
    </div>
    <div class="meta-item" title="Forwards">
      {share_svg}
      <span>{forwards}</span>
    </div>
    <div class="meta-item" title="Replies">
      {reply_svg}
      <span>{replies}</span>
    </div>
    <div class="meta-item id-badge" title="Message ID">
      {hash_svg}
      <span>{message_id}</span>
    </div>
  </footer>
</article>"""


def render_html(posts: list[dict[str, Any]]) -> str:
    # Gather statistics for dynamic sidebars
    channel_stats = {}
    date_stats = {}
    
    posts_by_date = {}
    for post in posts:
        chan = post.get("channel") or "unknown"
        channel_stats[chan] = channel_stats.get(chan, 0) + 1
        
        date_value = post.get("date_kyiv") or post.get("date_utc") or ""
        try:
            parsed_date = datetime.fromisoformat(date_value)
            date_key = parsed_date.date()
        except ValueError:
            date_key = datetime.min.date()
            
        posts_by_date.setdefault(date_key, []).append(post)
        
        if date_key != datetime.min.date():
            date_iso = date_key.isoformat()
            date_stats[date_iso] = date_stats.get(date_iso, 0) + 1

    # Sorted channels
    sorted_channels = sorted(channel_stats.items(), key=lambda x: x[0].lower())
    # Sorted dates for filters
    sorted_dates_filter = sorted(date_stats.keys())

    # Build Sidebar Filters HTML
    # Reset filters button
    reset_btn_html = '<button class="reset-btn" id="reset-filters-btn">🔄 Скинути фільтри</button>'

    # Date filter list
    date_options_html = [f'<button class="filter-btn active" data-date="all"><span>📅 Всі дати</span><span class="count">{len(posts)}</span></button>']
    for date_iso in sorted_dates_filter:
        dt = datetime.fromisoformat(date_iso)
        ua_date = format_date_ua(dt)
        count = date_stats[date_iso]
        date_options_html.append(
            f'<button class="filter-btn" data-date="{date_iso}"><span>📅 {ua_date}</span><span class="count">{count}</span></button>'
        )

    # Channel filter checkboxes
    channel_options_html = []
    for chan, count in sorted_channels:
        channel_options_html.append(
            f"""<label class="checkbox-label">
              <input type="checkbox" data-channel="{escape(chan)}">
              <span class="channel-lbl-name">{escape(chan)}</span>
              <span class="count">{count}</span>
            </label>"""
        )

    # Sort dates for chronological rendering
    sorted_dates = sorted(posts_by_date.keys())

    rendered_sections = []
    for date_key in sorted_dates:
        if date_key == datetime.min.date():
            header_text = "Невідома дата"
            date_iso_val = ""
        else:
            header_text = format_date_ua(date_key)
            date_iso_val = date_key.isoformat()

        group_posts = posts_by_date[date_key]
        rendered_posts = "\n".join(render_post(post) for post in group_posts)

        section_html = f"""<section class="date-group" data-group-date="{date_iso_val}">
      <h2 class="date-header">{header_text}</h2>
      <div class="posts-list">
        {rendered_posts}
      </div>
    </section>"""
        rendered_sections.append(section_html)

    all_sections_html = "\n".join(rendered_sections)

    # Template HTML with double curly brace variables for replacement
    template = r"""<!doctype html>
<html lang="uk">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Telegram News Timeline</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
    
    :root {
      color-scheme: light dark;
      --font-sans: 'Outfit', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      
      /* Light Mode Colors */
      --bg-app: #f1f5f9;
      --bg-card: #ffffff;
      --bg-sidebar: #ffffff;
      --border-card: #e2e8f0;
      --text-main: #0f172a;
      --text-muted: #64748b;
      --text-link: #2563eb;
      --text-link-hover: #1d4ed8;
      --bg-badge: #f8fafc;
      
      --accent: #2563eb;
      --accent-hover: #1d4ed8;
      
      --alert-color: #ef4444;
      --clear-color: #22c55e;
      --explosion-color: #f97316;
      --launch-color: #eab308;
      
      --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
      --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.05);
      --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.05), 0 4px 6px -4px rgb(0 0 0 / 0.05);
    }
    
    @media (prefers-color-scheme: dark) {
      :root {
        /* Dark Mode Colors */
        --bg-app: #080c14;
        --bg-card: #111a2e;
        --bg-sidebar: #152238;
        --border-card: #1e2d4a;
        --text-main: #f8fafc;
        --text-muted: #94a3b8;
        --text-link: #60a5fa;
        --text-link-hover: #93c5fd;
        --bg-badge: #0e1626;
        
        --accent: #3b82f6;
        --accent-hover: #60a5fa;
      }
    }
    
    body {
      margin: 0;
      font-family: var(--font-sans);
      background-color: var(--bg-app);
      color: var(--text-main);
      -webkit-font-smoothing: antialiased;
      line-height: 1.6;
    }}
    
    .layout {
      display: grid;
      grid-template-columns: 300px 1fr;
      gap: 32px;
      max-width: 1280px;
      margin: 0 auto;
      padding: 32px 24px;
      box-sizing: border-box;
    }
    
    /* Sidebar Filter Panel */
    .sidebar {
      position: sticky;
      top: 32px;
      height: calc(100vh - 64px);
      overflow-y: auto;
      background-color: var(--bg-sidebar);
      border: 1px solid var(--border-card);
      border-radius: 20px;
      padding: 24px;
      box-shadow: var(--shadow-md);
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
      gap: 24px;
    }
    
    .sidebar-section {
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--border-card);
    }
    
    .sidebar-section:last-child {
      border-bottom: none;
      padding-bottom: 0;
    }
    
    .section-title {
      font-size: 13px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
    }
    
    .form-input {
      width: 100%;
      padding: 10px 14px;
      border: 1px solid var(--border-card);
      background-color: var(--bg-app);
      color: var(--text-main);
      border-radius: 10px;
      font-family: var(--font-sans);
      font-size: 14px;
      box-sizing: border-box;
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    
    .form-input:focus {
      outline: none;
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
    }
    
    .filter-group {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    
    .filter-btn {
      display: flex;
      align-items: center;
      justify-content: space-between;
      width: 100%;
      padding: 8px 12px;
      border: 1px solid transparent;
      background-color: transparent;
      color: var(--text-main);
      border-radius: 8px;
      cursor: pointer;
      font-family: var(--font-sans);
      font-size: 14px;
      font-weight: 500;
      text-align: left;
      transition: background-color 0.15s, color 0.15s;
    }
    
    .filter-btn:hover {
      background-color: var(--bg-app);
    }
    
    .filter-btn.active {
      background-color: var(--accent);
      color: #ffffff;
    }
    
    .filter-btn.active .count {
      background-color: rgba(255, 255, 255, 0.2);
      color: #ffffff;
    }
    
    .checkbox-label {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 14px;
      color: var(--text-main);
      cursor: pointer;
      padding: 6px 8px;
      border-radius: 8px;
      transition: background-color 0.15s;
      user-select: none;
    }
    
    .checkbox-label:hover {
      background-color: var(--bg-app);
    }
    
    .checkbox-label input {
      cursor: pointer;
      accent-color: var(--accent);
      width: 15px;
      height: 15px;
    }
    
    .count {
      margin-left: auto;
      font-size: 11px;
      background-color: var(--bg-badge);
      color: var(--text-muted);
      padding: 2px 8px;
      border-radius: 10px;
      font-weight: 600;
    }
    
    .reset-btn {
      width: 100%;
      padding: 10px;
      background-color: var(--bg-badge);
      border: 1px solid var(--border-card);
      color: var(--text-main);
      border-radius: 10px;
      cursor: pointer;
      font-family: var(--font-sans);
      font-size: 13px;
      font-weight: 600;
      text-align: center;
      transition: background-color 0.2s, border-color 0.2s;
    }
    
    .reset-btn:hover {
      background-color: var(--border-card);
    }
    
    /* Main Content Area */
    .content-area {
      display: flex;
      flex-direction: column;
    }
    
    .header-section {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: 8px;
      margin-bottom: 32px;
      padding-bottom: 24px;
      border-bottom: 1px solid var(--border-card);
    }
    
    h1 {
      margin: 0;
      font-size: 32px;
      font-weight: 700;
      letter-spacing: -0.025em;
      background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    
    .summary-badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 16px;
      background: var(--bg-badge);
      border: 1px solid var(--border-card);
      border-radius: 9999px;
      font-size: 14px;
      font-weight: 500;
      color: var(--text-muted);
    }
    
    .date-group {
      margin-bottom: 32px;
    }
    
    .date-header {
      font-size: 20px;
      font-weight: 700;
      color: var(--text-main);
      margin: 24px 0 16px;
      padding-bottom: 8px;
      border-bottom: 2px solid var(--border-card);
      display: flex;
      align-items: center;
      gap: 12px;
    }
    
    .date-header::after {
      content: '';
      flex: 1;
      height: 1px;
      background-color: var(--border-card);
      opacity: 0.5;
    }
    
    /* Message Card styling */
    .message {
      margin-bottom: 20px;
      padding: 24px;
      border: 1px solid var(--border-card);
      border-radius: 16px;
      background-color: var(--bg-card);
      box-shadow: var(--shadow-sm);
      transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
    }
    
    .message:hover {
      transform: translateY(-2px);
      box-shadow: var(--shadow-md);
      border-color: rgba(59, 130, 246, 0.4);
    }
    
    .message-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
      border-bottom: 1px dashed var(--border-card);
      padding-bottom: 10px;
    }
    
    .channel-link {
      display: flex;
      align-items: center;
      gap: 4px;
      color: var(--text-link);
      text-decoration: none;
      font-weight: 600;
      font-size: 15px;
      transition: color 0.15s ease;
    }
    
    .channel-link:hover {
      color: var(--text-link-hover);
    }
    
    .channel-link:hover .link-icon {
      transform: translate(1px, -1px);
    }
    
    .link-icon {
      width: 14px;
      height: 14px;
      transition: transform 0.15s ease;
    }
    
    .message-time {
      font-size: 13px;
      color: var(--text-muted);
      font-weight: 400;
    }
    
    /* Badges */
    .message-badges {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 12px;
    }
    
    .badge {
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 600;
      line-height: 1;
    }
    
    .badge-alert {
      background-color: rgba(239, 68, 68, 0.12);
      color: var(--alert-color);
      border: 1px solid rgba(239, 68, 68, 0.2);
    }
    
    .badge-clear {
      background-color: rgba(34, 197, 94, 0.12);
      color: var(--clear-color);
      border: 1px solid rgba(34, 197, 94, 0.2);
    }
    
    .badge-explosion {
      background-color: rgba(249, 115, 22, 0.12);
      color: var(--explosion-color);
      border: 1px solid rgba(249, 115, 22, 0.2);
    }
    
    .badge-launch {
      background-color: rgba(234, 179, 8, 0.12);
      color: var(--launch-color);
      border: 1px solid rgba(234, 179, 8, 0.2);
    }
    
    .message-text {
      font-size: 15px;
      line-height: 1.6;
      white-space: normal;
      overflow-wrap: anywhere;
      margin-bottom: 12px;
      color: var(--text-main);
    }
    
    .message-photo {
      display: block;
      max-width: 100%;
      max-height: 380px;
      height: auto;
      margin: 16px auto;
      border-radius: 12px;
      box-shadow: var(--shadow-sm);
      object-fit: contain;
    }
    
    .message-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      margin-top: 14px;
      padding-top: 10px;
      border-top: 1px solid var(--border-card);
    }
    
    .meta-item {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      color: var(--text-muted);
      font-weight: 500;
    }
    
    .meta-icon {
      width: 16px;
      height: 16px;
      opacity: 0.7;
    }
    
    .id-badge {
      margin-left: auto;
      opacity: 0.6;
    }
    
    /* Highlight style */
    mark.highlight {
      background-color: rgba(234, 179, 8, 0.35);
      color: inherit;
      border-radius: 3px;
      padding: 0 2px;
    }
    
    /* No results styling */
    .no-results {
      text-align: center;
      padding: 48px;
      color: var(--text-muted);
      font-size: 16px;
      font-weight: 500;
      background-color: var(--bg-card);
      border: 1px dashed var(--border-card);
      border-radius: 16px;
      display: none;
    }
    
    @media (max-width: 900px) {
      .layout {
        grid-template-columns: 1fr;
        padding: 16px;
        gap: 20px;
      }
      .sidebar {
        position: relative;
        top: 0;
        height: auto;
      }
      .message {
        padding: 16px;
      }
      .id-badge {
        margin-left: 0;
      }
    }
  </style>
</head>
<body>
  <div class="layout">
    <!-- Sidebar Filter Panel -->
    <aside class="sidebar">
      {RESET_BTN}
      
      <div class="sidebar-section">
        <span class="section-title">🔍 Пошук</span>
        <input type="text" id="search-input" placeholder="Шукати в тексті..." class="form-input">
      </div>
      
      <div class="sidebar-section">
        <span class="section-title">📅 Фільтр по датах</span>
        <div class="filter-group" id="date-filters">
          {DATE_OPTIONS}
        </div>
      </div>
      
      <div class="sidebar-section">
        <span class="section-title">🔥 Категорії подій</span>
        <div class="filter-group" id="category-filters">
          <button class="filter-btn active" data-category="all"><span>🔥 Всі події</span></button>
          <button class="filter-btn" data-category="alert"><span>🚨 Тривоги</span></button>
          <button class="filter-btn" data-category="clear"><span>✅ Відбої</span></button>
          <button class="filter-btn" data-category="explosion"><span>💥 Вибухи</span></button>
          <button class="filter-btn" data-category="launch"><span>🚀 Загрози / Пуски</span></button>
        </div>
      </div>
      
      <div class="sidebar-section">
        <span class="section-title">📢 Фільтр по каналах</span>
        <div class="filter-group" id="channel-filters">
          {CHANNEL_OPTIONS}
        </div>
      </div>
    </aside>
    
    <!-- Main Content Area -->
    <main class="content-area">
      <header class="header-section">
        <h1>Telegram News Timeline</h1>
        <div class="summary-badge">
          <span>Показано повідомлень: <strong id="visible-count">{TOTAL_POSTS}</strong> з <strong>{TOTAL_POSTS}</strong></span>
        </div>
      </header>
      
      <div class="no-results" id="no-results-msg">
        Нічого не знайдено за вибраними фільтрами.
      </div>
      
      {ALL_SECTIONS}
    </main>
  </div>

  <script>
    document.addEventListener('DOMContentLoaded', () => {
      const searchInput = document.getElementById('search-input');
      const dateButtons = document.querySelectorAll('#date-filters .filter-btn');
      const channelCheckboxes = document.querySelectorAll('#channel-filters input[type="checkbox"]');
      const categoryButtons = document.querySelectorAll('#category-filters .filter-btn');
      const posts = document.querySelectorAll('.message');
      const dateGroups = document.querySelectorAll('.date-group');
      const totalCountEl = document.getElementById('visible-count');
      const resetBtn = document.getElementById('reset-filters-btn');
      const noResultsMsg = document.getElementById('no-results-msg');
      
      let activeDate = 'all';
      let activeCategory = 'all';
      
      function applyFilters() {
        const searchText = searchInput.value.toLowerCase().trim();
        
        // Get checked channels
        const checkedChannels = [];
        channelCheckboxes.forEach(cb => {
          if (cb.checked) {
            checkedChannels.push(cb.getAttribute('data-channel'));
          }
        });
        
        let visibleCount = 0;
        
        posts.forEach(post => {
          const postText = post.querySelector('.message-text')?.textContent.toLowerCase() || '';
          const postChannel = post.getAttribute('data-channel') || '';
          const postDate = post.getAttribute('data-date') || '';
          const postCategories = post.getAttribute('data-categories')?.split(',') || [];
          
          const matchesSearch = !searchText || postText.includes(searchText);
          const matchesDate = activeDate === 'all' || postDate === activeDate;
          const matchesChannel = checkedChannels.length === 0 || checkedChannels.includes(postChannel);
          const matchesCategory = activeCategory === 'all' || postCategories.includes(activeCategory);
          
          if (matchesSearch && matchesDate && matchesChannel && matchesCategory) {
            post.style.display = '';
            visibleCount++;
            
            // Highlight text matches
            const textEl = post.querySelector('.message-text');
            if (textEl && searchText) {
              const originalText = textEl.getAttribute('data-original-text') || textEl.innerHTML;
              if (!textEl.hasAttribute('data-original-text')) {
                textEl.setAttribute('data-original-text', originalText);
              }
              
              const parts = originalText.split('<br>');
              const highlightedParts = parts.map(part => {
                // Escape regex helper
                const escapedSearch = searchText
                  .replace(/&/g, "&amp;")
                  .replace(/</g, "&lt;")
                  .replace(/>/g, "&gt;");
                if (!escapedSearch) return part;
                const regex = new RegExp(`(${escapedSearch.replace(/[-\/\\\\^$*+?.()|[\]{}]/g, '\\\\$&')})`, 'gi');
                return part.replace(regex, '<mark class="highlight">$1</mark>');
              });
              textEl.innerHTML = highlightedParts.join('<br>');
            } else if (textEl && textEl.hasAttribute('data-original-text')) {
              textEl.innerHTML = textEl.getAttribute('data-original-text');
            }
          } else {
            post.style.display = 'none';
          }
        });
        
        // Hide date groups that have no visible posts
        dateGroups.forEach(group => {
          const visiblePostsInGroup = group.querySelectorAll('.message:not([style*="display: none"])');
          if (visiblePostsInGroup.length === 0) {
            group.style.display = 'none';
          } else {
            group.style.display = '';
          }
        });
        
        // Total visible counter
        if (totalCountEl) {
          totalCountEl.textContent = visibleCount;
        }
        
        // Show/hide no results msg
        if (visibleCount === 0) {
          noResultsMsg.style.display = 'block';
        } else {
          noResultsMsg.style.display = 'none';
        }
      }
      
      // Events
      searchInput.addEventListener('input', applyFilters);
      
      dateButtons.forEach(btn => {
        btn.addEventListener('click', () => {
          dateButtons.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          activeDate = btn.getAttribute('data-date');
          applyFilters();
        });
      });
      
      channelCheckboxes.forEach(cb => {
        cb.addEventListener('change', applyFilters);
      });
      
      categoryButtons.forEach(btn => {
        btn.addEventListener('click', () => {
          categoryButtons.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          activeCategory = btn.getAttribute('data-category');
          applyFilters();
        });
      });
      
      // Reset
      resetBtn.addEventListener('click', () => {
        searchInput.value = '';
        
        dateButtons.forEach(b => b.classList.remove('active'));
        dateButtons[0].classList.add('active');
        activeDate = 'all';
        
        categoryButtons.forEach(b => b.classList.remove('active'));
        categoryButtons[0].classList.add('active');
        activeCategory = 'all';
        
        channelCheckboxes.forEach(cb => cb.checked = false);
        
        applyFilters();
      });
    });
  </script>
</body>
</html>
"""

    # Direct string replacements to prevent python f-string formatting syntax errors
    res = template.replace("{RESET_BTN}", reset_btn_html)
    res = res.replace("{DATE_OPTIONS}", "\n".join(date_options_html))
    res = res.replace("{CHANNEL_OPTIONS}", "\n".join(channel_options_html))
    res = res.replace("{TOTAL_POSTS}", str(len(posts)))
    res = res.replace("{ALL_SECTIONS}", all_sections_html)

    return res


def main() -> None:
    posts = load_posts()
    allowed_channels = load_allowed_channels()
    
    if allowed_channels:
        filtered_posts = []
        for post in posts:
            channel_url = str(post.get("channel_url") or "").lower().rstrip("/")
            channel_name = str(post.get("channel") or "").lower()
            if channel_url in allowed_channels or channel_name in allowed_channels:
                filtered_posts.append(post)
        posts = filtered_posts
        
    posts = sorted(posts, key=sort_key)
    OUTPUT_PATH.write_text(render_html(posts), encoding="utf-8", newline="\n")
    print(f"Read {len(posts)} posts matching channel constraints from exports directory.")
    print(f"Wrote HTML to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
