import json
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from news_events import group_events

BASE_DIR = Path(__file__).resolve().parent
EXPORTS_DIR = BASE_DIR / "exports"
INPUT_PATH = EXPORTS_DIR / "tg_posts_2026-07-01_1600_to_2026-07-02_0800.jsonl"
OUTPUT_PATH = EXPORTS_DIR / "news.html"
MARKERS_PATH = BASE_DIR / "tg-news-markers.json"

EVENT_STYLES = """
    .events-panel {
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
    .events-panel-title {
      display: flex;
      flex-wrap: wrap;
      gap: 8px 12px;
      align-items: baseline;
      justify-content: space-between;
      margin-bottom: 10px;
    }
    .events-panel-title h2 {
      margin: 0;
      font-size: 18px;
    }
    .events-help {
      color: #6b7280;
      font-size: 13px;
    }
    .events-list {
      display: flex;
      flex-direction: column;
      gap: 10px;
      max-height: calc(100vh - 120px);
      overflow-y: auto;
      padding-right: 4px;
      scrollbar-gutter: stable;
    }
    .event-card {
      display: grid;
      grid-template-columns: 6px minmax(0, 1fr);
      gap: 10px;
      align-items: start;
      padding: 10px 10px 10px 0;
      border: 1px solid #e5e7eb;
      border-radius: 10px;
      background: #ffffff;
      cursor: pointer;
      text-align: left;
      font: inherit;
      color: inherit;
      width: 100%;
    }
    .event-card:hover,
    .event-card:focus-visible {
      border-color: #9ca3af;
      box-shadow: 0 2px 8px rgb(0 0 0 / 8%);
    }
    .event-card-swatch {
      width: 6px;
      align-self: stretch;
      border-radius: 999px;
      margin-left: 10px;
    }
    .event-card-body {
      min-width: 0;
      padding-right: 8px;
    }
    .event-card-message {
      margin: 0 0 6px;
      font-size: 14px;
      font-weight: 700;
      line-height: 1.35;
      overflow-wrap: anywhere;
    }
    .event-card-meta {
      margin: 0;
      color: #6b7280;
      font-size: 12px;
      line-height: 1.4;
    }
    .event-card-send {
      margin: 4px 0 0;
      color: #2563eb;
      font-size: 12px;
      font-weight: 600;
    }
    .message--grouped {
      border-left-width: 4px;
      border-left-style: solid;
    }
    .message--summary {
      border-left: 4px solid #f8fafc;
      background: rgb(248 250 252 / 88%);
    }
"""

EVENT_SCRIPT = """
  <script>
    (() => {
      document.querySelectorAll("[data-event-card]").forEach((card) => {
        card.addEventListener("click", () => {
          const eventId = card.dataset.eventCard;
          const target = document.querySelector(`[data-event-id="${eventId}"]`);
          if (target) {
            target.scrollIntoView({ behavior: "smooth", block: "center" });
            target.classList.add("message--highlight");
            window.setTimeout(() => target.classList.remove("message--highlight"), 1200);
          }
        });
      });
    })();
  </script>
"""

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
    .stance-filters {
      margin-top: 4px;
      margin-bottom: 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid #e5e7eb;
    }
    .stance-filters h3 {
      margin: 0 0 8px;
      font-size: 13px;
      text-transform: uppercase;
      color: #4b5563;
      letter-spacing: 0.05em;
    }
    .stance-filters-group {
      display: flex;
      gap: 16px;
    }
    .stance-filter-label {
      display: flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 500;
    }
    .stance-filter-label input {
      cursor: pointer;
      width: 16px;
      height: 16px;
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
    .message--highlight {
      outline: 2px solid #2563eb;
      outline-offset: 2px;
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

      function readSeedMarkers() {
        const seedElement = document.getElementById("tg-news-markers-seed");
        if (!seedElement) {
          return [];
        }

        try {
          const parsed = JSON.parse(seedElement.textContent || "[]");
          if (!Array.isArray(parsed)) {
            return [];
          }

          return uniqueMarkers(parsed.map(normalizeMarker));
        } catch {
          return [];
        }
      }

      const seedMarkers = readSeedMarkers();

      function loadMarkers() {
        try {
          const storedMarkers = JSON.parse(localStorage.getItem(storageKey) || "[]");
          const stored = Array.isArray(storedMarkers)
            ? uniqueMarkers(storedMarkers.map(normalizeMarker))
            : [];
          const byText = new Map();

          seedMarkers.forEach((marker) => byText.set(markerIdentity(marker.text), marker));
          stored.forEach((marker) => byText.set(markerIdentity(marker.text), marker));
          return Array.from(byText.values());
        } catch {
          return [...seedMarkers];
        }
      }

      let markers = loadMarkers();

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
        const messageContainers = document.querySelectorAll(messageTextSelector);
        markers.forEach((marker) => {
          messageContainers.forEach((container) => {
            textNodesIn(container).forEach((textNode) => {
              const key = markerIdentity(marker.text);
              const created = highlightTextNode(textNode, marker);
              counts.set(key, (counts.get(key) || 0) + created);
            });
          });
        });

        return counts;
      }

      function countExistingHighlights() {
        const counts = new Map(markers.map((marker) => [markerIdentity(marker.text), 0]));
        document.querySelectorAll("mark.marker-highlight").forEach((highlight) => {
          const key = markerIdentity(highlight.dataset.marker || highlight.textContent || "");
          counts.set(key, (counts.get(key) || 0) + 1);
        });
        return counts;
      }

      function renderMarkers(useExistingHighlights = false) {
        const counts = useExistingHighlights ? countExistingHighlights() : applyHighlights();
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
      renderMarkers(true);
    })();
  </script>
"""


def load_seed_markers() -> list[dict[str, str]]:
    if not MARKERS_PATH.exists():
        return []

    try:
        with MARKERS_PATH.open("r", encoding="utf-8") as markers_file:
            markers = json.load(markers_file)
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(markers, list):
        return []

    return markers


def render_seed_markers_script(markers: list[dict[str, str]]) -> str:
    seed_json = json.dumps(markers, ensure_ascii=False).replace("</", "<\\/")
    return f'  <script type="application/json" id="tg-news-markers-seed">{seed_json}</script>'


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


def normalize_for_search(value: str) -> str:
    return value.casefold().replace("ё", "е")


def normalize_marker_text(value: str) -> str:
    return " ".join(value.split())


def valid_marker_category(value: object) -> str:
    if value in {"location", "weapon", "equipment", "other"}:
        return str(value)
    return "other"


def normalize_markers(markers: list[object]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()

    for marker in markers:
        if isinstance(marker, str):
            text = normalize_marker_text(marker)
            category = "other"
        elif isinstance(marker, dict):
            text = normalize_marker_text(str(marker.get("text") or ""))
            category = valid_marker_category(marker.get("category"))
        else:
            continue

        if not text:
            continue

        identity = normalize_for_search(text)
        if identity in seen:
            continue

        seen.add(identity)
        normalized.append({"text": text, "category": category})

    return normalized


def highlight_text_with_markers(text: str, markers: list[dict[str, str]]) -> str:
    if not text:
        return ""

    if not markers:
        return escape(text).replace("\n", "<br>")

    categories: list[str | None] = [None] * len(text)
    marker_labels: list[str | None] = [None] * len(text)
    lower_text = normalize_for_search(text)

    for marker in markers:
        marker_text = marker["text"]
        lower_marker = normalize_for_search(marker_text)
        category = marker["category"]
        cursor = 0

        while cursor < len(text):
            match_index = lower_text.find(lower_marker, cursor)
            if match_index == -1:
                break

            end_index = match_index + len(marker_text)
            if all(categories[index] is None for index in range(match_index, end_index)):
                for index in range(match_index, end_index):
                    categories[index] = category
                    marker_labels[index] = marker_text

            cursor = match_index + len(marker_text)

    parts: list[str] = []
    index = 0
    while index < len(text):
        category = categories[index]
        if category is None:
            next_index = index + 1
            while next_index < len(text) and categories[next_index] is None:
                next_index += 1
            chunk = text[index:next_index]
            parts.append(escape(chunk).replace("\n", "<br>"))
            index = next_index
            continue

        next_index = index + 1
        while next_index < len(text) and categories[next_index] == category:
            next_index += 1

        chunk = text[index:next_index]
        marker_text = marker_labels[index] or chunk
        escaped_chunk = escape(chunk).replace("\n", "<br>")
        escaped_marker = escape(marker_text, quote=True)
        parts.append(
            f'<mark class="marker-highlight marker-highlight-{category}" '
            f'data-marker="{escaped_marker}" data-category="{category}">'
            f"{escaped_chunk}</mark>"
        )
        index = next_index

    return "".join(parts)


def render_text(post: dict[str, Any], markers: list[dict[str, str]] | None = None) -> str:
    text = str(post.get("text") or "").strip()
    if not text and post.get("has_media"):
        text = "Без тексту"

    if not text:
        return ""

    if markers:
        return highlight_text_with_markers(text, markers)

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


def post_key(post: dict[str, Any]) -> str:
    return f"{post.get('channel')}:{post.get('message_id')}"


def render_post(
    post: dict[str, Any],
    event: dict[str, Any] | None = None,
    *,
    is_summary: bool = False,
    markers: list[dict[str, str]] | None = None,
    stances: dict[str, str] | None = None,
) -> str:
    channel = escape(str(post.get("channel") or "unknown"))
    channel_url = escape(str(post.get("channel_url") or "#"), quote=True)
    date_kyiv = escape(format_date(post.get("date_kyiv")))
    text_html = render_text(post, markers)
    photo_html = render_photo(post)
    views = escape(str(post.get("views") if post.get("views") is not None else "-"))
    forwards = escape(str(post.get("forwards") if post.get("forwards") is not None else "-"))
    replies = escape(str(post.get("replies") if post.get("replies") is not None else "-"))
    message_id = escape(str(post.get("message_id") or "-"))

    text_block = f'<div class="message-text">{text_html}</div>' if text_html else ""

    stance = ""
    if stances:
        clean_url = post.get("channel_url", "").rstrip("/")
        for curl, cstance in stances.items():
            if curl.rstrip("/") == clean_url:
                stance = cstance
                break

    event_attrs = ""
    event_classes = "message"
    if is_summary:
        event_attrs = ' data-post-kind="summary"'
        event_classes = "message message--summary"
    elif event:
        event_color = escape(str(event.get("color") or "#94a3b8"))
        event_id = escape(str(event.get("id") or ""))
        event_attrs = (
            f' data-event-id="{event_id}"'
            f' id="post-{event_id}-{message_id}"'
            f' style="--event-color: {event_color}; border-left-color: {event_color};"'
        )
        event_classes = "message message--grouped"

    if stance:
        event_attrs += f' data-stance="{stance}"'
        channel_display = f"{channel} {stance}"
    else:
        channel_display = channel

    return f"""<article class="{event_classes}"{event_attrs}>
  <header class="message-header">
    <time>{date_kyiv}</time>
    <a href="{channel_url}" target="_blank" rel="noopener noreferrer">{channel_display}</a>
  </header>
  {text_block}
  {photo_html}
  <footer class="message-meta">views: {views} | forwards: {forwards} | replies: {replies} | id: {message_id}</footer>
</article>"""


def render_event_card(event: dict[str, Any]) -> str:
    event_id = escape(str(event.get("id") or ""))
    color = escape(str(event.get("color") or "#94a3b8"))
    user_message = escape(str(event.get("user_message") or "Подія"))
    started_at = escape(format_date(event.get("started_at")))
    last_post_at = escape(format_date(event.get("last_post_at")))
    send_at = escape(format_date(event.get("send_at")))
    source_count = int(event.get("source_count") or 0)
    channels = ", ".join(escape(channel) for channel in event.get("channels") or [])

    return f"""<button class="event-card" type="button" data-event-card="{event_id}">
  <span class="event-card-swatch" style="background: {color};"></span>
  <span class="event-card-body">
    <p class="event-card-message">{user_message}</p>
    <p class="event-card-meta">{started_at} – {last_post_at}<br>{source_count} джерел: {channels}</p>
    <p class="event-card-send">Відправити о {send_at}</p>
  </span>
</button>"""


def render_events_panel(events: list[dict[str, Any]]) -> str:
    if not events:
        return """<section class="events-panel" aria-label="Згруповані події">
      <div class="events-panel-title">
        <h2>Події</h2>
        <span class="events-help">0 подій</span>
      </div>
      <p class="events-help">Поки немає згрупованих подій.</p>
    </section>"""

    rendered_events = "\n".join(render_event_card(event) for event in events)
    multi_source = sum(1 for event in events if int(event.get("source_count") or 0) > 1)

    return f"""<section class="events-panel" aria-label="Згруповані події">
      <div class="events-panel-title">
        <h2>Події</h2>
        <span class="events-help">{len(events)} подій · {multi_source} з 2+ джерел</span>
      </div>
      <div class="events-list">
        {rendered_events}
      </div>
    </section>"""


def load_channel_stances() -> dict[str, str]:
    csv_path = BASE_DIR / "tg-chanel-links.csv"
    if not csv_path.exists():
        return {}
    import csv
    stances = {}
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header:
                if not (header[0].startswith("http://") or header[0].startswith("https://")):
                    pass
                else:
                    url = header[0].strip()
                    stances[url] = header[1].strip() if len(header) > 1 else ""
            for row in reader:
                if not row:
                    continue
                url = row[0].strip()
                if not url or url.startswith("#"):
                    continue
                stances[url] = row[1].strip() if len(row) > 1 else ""
    except Exception:
        pass
    return stances


def render_html(
    posts: list[dict[str, Any]],
    events: list[dict[str, Any]],
    assignment: dict[str, str],
    summary_posts: set[str],
) -> str:
    stances = load_channel_stances()
    events_by_id = {str(event["id"]): event for event in events}
    seed_markers = normalize_markers(load_seed_markers())
    rendered_posts = "\n".join(
        render_post(
            post,
            events_by_id.get(assignment.get(post_key(post), "")),
            is_summary=post_key(post) in summary_posts,
            markers=seed_markers,
            stances=stances,
        )
        for post in posts
    )
    rendered_events = render_events_panel(events)
    grouped_count = len(assignment)
    summary_count = len(summary_posts)
    seed_markers_script = render_seed_markers_script(seed_markers)

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
      grid-template-columns: minmax(220px, 280px) minmax(0, 1fr) minmax(260px, 320px);
      gap: 24px;
      align-items: start;
      max-width: 1600px;
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
    .message--grouped {{
      background: color-mix(in srgb, var(--event-color) 12%, #ffffff);
    }}
    .message--summary {{
      border-left-color: #f8fafc;
      background: rgb(248 250 252 / 92%);
    }}
{MARKER_STYLES}
{EVENT_STYLES}
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
      .message--grouped {{
        background: color-mix(in srgb, var(--event-color) 18%, #1f2937);
      }}
      .message--summary {{
        border-left-color: #e5e7eb;
        background: rgb(229 231 235 / 18%);
      }}
      .events-panel {{
        border-color: #4b5563;
        background: rgb(31 41 55 / 94%);
      }}
      .events-help,
      .event-card-meta {{
        color: #9ca3af;
      }}
      .event-card {{
        border-color: #374151;
        background: #1f2937;
      }}
      .event-card-send {{
        color: #93c5fd;
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
      .stance-filters {{
        border-bottom-color: #374151;
      }}
      .stance-filters h3 {{
        color: #9ca3af;
      }}
    }}
    @media (max-width: 1200px) {{
      main {{
        display: block;
        max-width: 860px;
      }}
      .marker-panel,
      .events-panel {{
        top: 0;
        margin: 0 0 20px;
        max-height: none;
        overflow: visible;
      }}
      .marker-list {{
        flex-flow: row wrap;
        max-height: 220px;
      }}
      .events-list {{
        max-height: 320px;
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
      <p class="summary">Повідомлень: {len(posts)}. Подій: {len(events)}. У групах: {grouped_count}. Зведення: {summary_count}. Сортування: від ранніх до пізніх за київським часом.</p>
    </div>
    <section class="marker-panel" aria-label="Маркери для аналізу">
      <div class="marker-panel-title">
        <h2>Маркери</h2>
        <span class="marker-help">Виділіть текст: Q - локації, W - зброя, E - військова техніка, R - інше</span>
      </div>
      <div class="stance-filters">
        <h3>Позиція каналу</h3>
        <div class="stance-filters-group">
          <label class="stance-filter-label">
            <input type="checkbox" id="filter-ua" checked>
            🇺🇦 Проукраїнські
          </label>
          <label class="stance-filter-label">
            <input type="checkbox" id="filter-ru" checked>
            🐖 Проросійські
          </label>
        </div>
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
    {rendered_events}
  </main>
  <script>
    (() => {{
      const filterUa = document.getElementById("filter-ua");
      const filterRu = document.getElementById("filter-ru");
      const messages = document.querySelectorAll(".message");

      function updateFilters() {{
        const showUa = filterUa.checked;
        const showRu = filterRu.checked;

        messages.forEach((msg) => {{
          const stance = msg.getAttribute("data-stance");
          let shouldShow = true;
          if (stance === "🇺🇦") {{
            shouldShow = showUa;
          }} else if (stance === "🐖") {{
            shouldShow = showRu;
          }}
          msg.style.display = shouldShow ? "" : "none";
        }});
      }}

      if (filterUa && filterRu) {{
        filterUa.addEventListener("change", updateFilters);
        filterRu.addEventListener("change", updateFilters);
        updateFilters();
      }}
    }})();
  </script>
{seed_markers_script}
{MARKER_SCRIPT}
{EVENT_SCRIPT}
</body>
</html>
"""


def main() -> None:
    posts = sorted(load_posts(), key=sort_key)
    events, assignment, summary_posts = group_events(posts)
    OUTPUT_PATH.write_text(
        render_html(posts, events, assignment, summary_posts),
        encoding="utf-8",
        newline="\n",
    )
    print(f"Read {len(posts)} posts from {INPUT_PATH}")
    print(f"Grouped {len(assignment)} posts into {len(events)} events")
    print(f"Summary posts: {len(summary_posts)}")
    print(f"Wrote HTML to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
