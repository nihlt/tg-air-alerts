import json
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
EXPORTS_DIR = BASE_DIR / "exports"
INPUT_PATH = EXPORTS_DIR / "tg_posts_2026-07-01_1600_to_2026-07-02_0800.jsonl"
OUTPUT_PATH = EXPORTS_DIR / "news.html"

MARKER_STYLES = """
    .marker-panel {
      position: sticky;
      top: 16px;
      z-index: 10;
      align-self: start;
      max-height: calc(100vh - 32px);
      overflow: hidden;
      padding: 14px 16px;
      border: 1px solid #d1d5db;
      border-radius: 12px;
      background: rgb(255 255 255 / 94%);
      box-shadow: 0 8px 24px rgb(0 0 0 / 10%);
      backdrop-filter: blur(10px);
    }
    .marker-panel-title {
      display: flex;
      flex-wrap: wrap;
      gap: 8px 12px;
      align-items: baseline;
      justify-content: space-between;
      margin-bottom: 10px;
    }
    .marker-panel-title h2 {
      margin: 0;
      font-size: 18px;
    }
    .marker-help {
      color: #6b7280;
      font-size: 13px;
    }
    .marker-actions {
      display: grid;
      gap: 8px;
      margin-top: 10px;
    }
    .marker-export,
    .marker-import {
      width: 100%;
      border: 1px solid #2563eb;
      border-radius: 8px;
      background: #2563eb;
      color: #ffffff;
      cursor: pointer;
      font: inherit;
      padding: 8px 10px;
    }
    .marker-import {
      border-color: #4b5563;
      background: #ffffff;
      color: #111827;
    }
    .marker-export:hover,
    .marker-export:focus-visible {
      background: #1d4ed8;
    }
    .marker-import:hover,
    .marker-import:focus-visible {
      background: #f3f4f6;
    }
    .marker-file-input {
      display: none;
    }
    .marker-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
      max-height: calc(100vh - 170px);
      margin-top: 10px;
      overflow-y: auto;
      padding-right: 4px;
      scrollbar-gutter: stable;
    }
    .marker-empty {
      margin: 0;
      color: #6b7280;
      font-size: 14px;
    }
    .marker-pill {
      display: inline-flex;
      gap: 8px;
      align-items: center;
      justify-content: space-between;
      max-width: 100%;
      padding: 6px 8px 6px 10px;
      border: 1px solid #f59e0b;
      border-radius: 999px;
      font-size: 14px;
    }
    .marker-pill[data-category="location"] {
      border-color: #2563eb;
      background: #dbeafe;
      color: #1e3a8a;
    }
    .marker-pill[data-category="weapon"] {
      border-color: #dc2626;
      background: #fee2e2;
      color: #7f1d1d;
    }
    .marker-pill[data-category="equipment"] {
      border-color: #7c3aed;
      background: #ede9fe;
      color: #4c1d95;
    }
    .marker-pill[data-category="other"] {
      border-color: #f59e0b;
      background: #fef3c7;
      color: #78350f;
    }
    .marker-pill-text {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .marker-pill button {
      border: 0;
      border-radius: 999px;
      background: #92400e;
      color: #ffffff;
      cursor: pointer;
      font: inherit;
      padding: 2px 8px;
    }
    .marker-pill button:hover,
    .marker-pill button:focus-visible {
      background: #78350f;
    }
    .marker-highlight {
      border-radius: 3px;
      color: #111827;
      padding: 0 2px;
    }
    .marker-highlight-location {
      background: #93c5fd;
    }
    .marker-highlight-weapon {
      background: #fca5a5;
    }
    .marker-highlight-equipment {
      background: #c4b5fd;
    }
    .marker-highlight-other {
      background: #fde047;
    }
"""

MARKER_SCRIPT = """
  <script>
    (() => {
      const storageKey = `tg-news-markers:${location.pathname}`;
      const markerList = document.querySelector("[data-marker-list]");
      const markerEmpty = document.querySelector("[data-marker-empty]");
      const markerExportButton = document.querySelector("[data-marker-export]");
      const markerImportButton = document.querySelector("[data-marker-import]");
      const markerImportInput = document.querySelector("[data-marker-import-input]");
      const messageTextSelector = ".message-text";
      const markerCategories = {
        location: { label: "Локації", shortcut: "Q" },
        weapon: { label: "Зброя", shortcut: "W" },
        equipment: { label: "Військова техніка", shortcut: "E" },
        other: { label: "Інше", shortcut: "R" },
      };
      const shortcutCategories = new Map([
        ["KeyQ", "location"],
        ["KeyW", "weapon"],
        ["KeyE", "equipment"],
        ["KeyR", "other"],
      ]);
      let markers = loadMarkers();

      function normalizeMarkerText(value) {
        return value.replace(/\\s+/g, " ").trim();
      }

      function normalizeForSearch(value) {
        return value.toLocaleLowerCase("uk-UA").replaceAll("ё", "е");
      }

      function markerIdentity(value) {
        return normalizeForSearch(value);
      }

      function validCategory(value) {
        return Object.prototype.hasOwnProperty.call(markerCategories, value) ? value : "other";
      }

      function normalizeMarker(marker) {
        if (typeof marker === "string") {
          return { text: normalizeMarkerText(marker), category: "other" };
        }

        if (!marker || typeof marker !== "object") {
          return null;
        }

        return {
          text: normalizeMarkerText(String(marker.text || "")),
          category: validCategory(marker.category),
        };
      }

      function uniqueMarkers(nextMarkers) {
        const byText = new Map();
        nextMarkers.forEach((marker) => {
          if (marker && marker.text) {
            byText.set(markerIdentity(marker.text), marker);
          }
        });
        return Array.from(byText.values());
      }

      function loadMarkers() {
        try {
          const storedMarkers = JSON.parse(localStorage.getItem(storageKey) || "[]");
          if (!Array.isArray(storedMarkers)) {
            return [];
          }

          return uniqueMarkers(storedMarkers.map(normalizeMarker));
        } catch {
          return [];
        }
      }

      function saveMarkers() {
        try {
          localStorage.setItem(storageKey, JSON.stringify(markers));
        } catch {
          // The page should remain usable even if localStorage is unavailable.
        }
      }

      function addSelectedMarker(category) {
        const selection = window.getSelection();
        const selectedText = normalizeMarkerText(selection ? selection.toString() : "");
        if (!selectedText) {
          return;
        }

        const existingMarker = markers.find(
          (marker) => markerIdentity(marker.text) === markerIdentity(selectedText),
        );
        if (existingMarker) {
          existingMarker.category = category;
        } else {
          markers.push({ text: selectedText, category });
        }
        saveMarkers();

        if (selection) {
          selection.removeAllRanges();
        }
        renderMarkers();
      }

      function removeMarker(markerToRemove) {
        markers = markers.filter(
          (marker) => markerIdentity(marker.text) !== markerIdentity(markerToRemove.text),
        );
        saveMarkers();
        renderMarkers();
      }

      function clearHighlights() {
        document.querySelectorAll("mark.marker-highlight").forEach((highlight) => {
          highlight.replaceWith(document.createTextNode(highlight.textContent || ""));
        });

        document.querySelectorAll(messageTextSelector).forEach((container) => {
          container.normalize();
        });
      }

      function textNodesIn(container) {
        const walker = document.createTreeWalker(
          container,
          NodeFilter.SHOW_TEXT,
          {
            acceptNode(node) {
              if (!node.nodeValue || !node.nodeValue.trim()) {
                return NodeFilter.FILTER_REJECT;
              }

              if (node.parentElement && node.parentElement.closest(".marker-highlight")) {
                return NodeFilter.FILTER_REJECT;
              }

              return NodeFilter.FILTER_ACCEPT;
            },
          },
        );
        const nodes = [];
        let node = walker.nextNode();
        while (node) {
          nodes.push(node);
          node = walker.nextNode();
        }
        return nodes;
      }

      function highlightTextNode(textNode, marker) {
        const sourceText = textNode.nodeValue || "";
        const lowerSource = normalizeForSearch(sourceText);
        const lowerMarker = normalizeForSearch(marker.text);
        const fragment = document.createDocumentFragment();
        let cursor = 0;
        let count = 0;
        let matchIndex = lowerSource.indexOf(lowerMarker, cursor);

        while (matchIndex !== -1) {
          if (matchIndex > cursor) {
            fragment.appendChild(document.createTextNode(sourceText.slice(cursor, matchIndex)));
          }

          const highlight = document.createElement("mark");
          highlight.className = `marker-highlight marker-highlight-${marker.category}`;
          highlight.dataset.marker = marker.text;
          highlight.dataset.category = marker.category;
          highlight.textContent = sourceText.slice(matchIndex, matchIndex + marker.text.length);
          fragment.appendChild(highlight);

          count += 1;
          cursor = matchIndex + marker.text.length;
          matchIndex = lowerSource.indexOf(lowerMarker, cursor);
        }

        if (!count) {
          return 0;
        }

        if (cursor < sourceText.length) {
          fragment.appendChild(document.createTextNode(sourceText.slice(cursor)));
        }

        textNode.replaceWith(fragment);
        return count;
      }

      function applyHighlights() {
        const counts = new Map(markers.map((marker) => [markerIdentity(marker.text), 0]));

        clearHighlights();
        markers.forEach((marker) => {
          document.querySelectorAll(messageTextSelector).forEach((container) => {
            textNodesIn(container).forEach((textNode) => {
              const key = markerIdentity(marker.text);
              counts.set(key, (counts.get(key) || 0) + highlightTextNode(textNode, marker));
            });
          });
        });

        return counts;
      }

      function renderMarkers() {
        const counts = applyHighlights();
        markerList.textContent = "";
        markerEmpty.hidden = markers.length > 0;
        markerExportButton.disabled = markers.length === 0;

        markers.forEach((marker) => {
          const category = markerCategories[marker.category];
          const item = document.createElement("span");
          item.className = "marker-pill";
          item.dataset.category = marker.category;

          const text = document.createElement("span");
          text.className = "marker-pill-text";
          text.title = `${category.label}: ${marker.text}`;
          text.textContent = `${category.shortcut} · ${marker.text} (${counts.get(markerIdentity(marker.text)) || 0})`;

          const removeButton = document.createElement("button");
          removeButton.type = "button";
          removeButton.textContent = "Видалити";
          removeButton.addEventListener("click", () => removeMarker(marker));

          item.append(text, removeButton);
          markerList.appendChild(item);
        });
      }

      function exportMarkers() {
        const exportedMarkers = markers.map((marker) => ({
          text: marker.text,
          category: marker.category,
        }));
        const blob = new Blob([JSON.stringify(exportedMarkers, null, 2)], {
          type: "application/json;charset=utf-8",
        });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "tg-news-markers.json";
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
      }

      function importMarkersFromFile(file) {
        const reader = new FileReader();
        reader.addEventListener("load", () => {
          try {
            const importedMarkers = JSON.parse(String(reader.result || "[]"));
            if (!Array.isArray(importedMarkers)) {
              throw new Error("Expected a JSON array");
            }

            markers = uniqueMarkers(importedMarkers.map(normalizeMarker));
            saveMarkers();
            renderMarkers();
          } catch (error) {
            window.alert("Не вдалося імпортувати теги. Перевірте формат JSON.");
          }
        });
        reader.readAsText(file, "utf-8");
      }

      function isEditableTarget(target) {
        return target instanceof HTMLElement && (
          target.isContentEditable ||
          ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)
        );
      }

      document.addEventListener("keydown", (event) => {
        const category = shortcutCategories.get(event.code);
        const isSimpleMarkerShortcut = (
          category &&
          !event.ctrlKey &&
          !event.altKey &&
          !event.metaKey &&
          !isEditableTarget(event.target)
        );
        const isLegacyMarkerShortcut = event.ctrlKey && event.shiftKey && event.code === "KeyH";

        if (isSimpleMarkerShortcut || isLegacyMarkerShortcut) {
          event.preventDefault();
          addSelectedMarker(category || "other");
        }
      });

      markerExportButton.addEventListener("click", exportMarkers);
      markerImportButton.addEventListener("click", () => markerImportInput.click());
      markerImportInput.addEventListener("change", () => {
        const [file] = markerImportInput.files || [];
        if (file) {
          importMarkersFromFile(file);
        }
        markerImportInput.value = "";
      });
      renderMarkers();
    })();
  </script>
"""


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
      display: grid;
      grid-template-columns: minmax(220px, 280px) minmax(0, 860px);
      gap: 24px;
      align-items: start;
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px 16px 48px;
    }}
    .page-header {{
      grid-column: 1 / -1;
    }}
    .message-feed {{
      min-width: 0;
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
{MARKER_STYLES}
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
      .marker-panel {{
        border-color: #4b5563;
        background: rgb(31 41 55 / 94%);
      }}
      .marker-help,
      .marker-empty {{
        color: #9ca3af;
      }}
      .marker-import {{
        border-color: #6b7280;
        background: #1f2937;
        color: #f9fafb;
      }}
      .marker-import:hover,
      .marker-import:focus-visible {{
        background: #374151;
      }}
      .message-header a {{
        color: #93c5fd;
      }}
    }}
    @media (max-width: 960px) {{
      main {{
        display: block;
        max-width: 860px;
      }}
      .marker-panel {{
        top: 0;
        margin: 0 0 20px;
        max-height: none;
        overflow: visible;
      }}
      .marker-list {{
        flex-flow: row wrap;
        max-height: 220px;
      }}
      .marker-pill {{
        justify-content: flex-start;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="page-header">
      <h1>Telegram News Timeline</h1>
      <p class="summary">Повідомлень: {len(posts)}. Сортування: від ранніх до пізніх за київським часом.</p>
    </div>
    <section class="marker-panel" aria-label="Маркери для аналізу">
      <div class="marker-panel-title">
        <h2>Маркери</h2>
        <span class="marker-help">Виділіть текст: Q - локації, W - зброя, E - військова техніка, R - інше</span>
      </div>
      <div class="marker-actions">
        <button class="marker-export" type="button" data-marker-export>Експорт тегів</button>
        <button class="marker-import" type="button" data-marker-import>Імпорт тегів</button>
        <input class="marker-file-input" type="file" accept="application/json,.json" data-marker-import-input>
      </div>
      <p class="marker-empty" data-marker-empty>Активних маркерів ще немає.</p>
      <div class="marker-list" data-marker-list></div>
    </section>
    <section class="message-feed" aria-label="Повідомлення Telegram">
      {rendered_posts}
    </section>
  </main>
{MARKER_SCRIPT}
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
