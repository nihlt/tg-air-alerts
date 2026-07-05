import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
INPUT_PATH = BASE_DIR / "exports" / "tg_posts_2026-07-01_1600_to_2026-07-02_0800.jsonl"
SEED_PATH = BASE_DIR / "tg-news-markers.json"
OUTPUT_PATH = BASE_DIR / "tg-news-markers.json"
REPORT_PATH = BASE_DIR / "exports" / "markers_report.txt"

VALID_CATEGORIES = ("location", "weapon", "equipment", "other")
CATEGORY_ORDER = {category: index for index, category in enumerate(VALID_CATEGORIES)}

MIN_MARKER_LENGTH = 3
SHORT_MARKER_WHITELIST = {
    "бпла",
    "fpv",
    "пво",
    "ппо",
    "зрк",
    "каб",
    "рлс",
    "реб",
    "рэб",
    "бмп",
    "бтр",
    "сша",
    "нато",
    "крим",
    "азов",
    "ес",
    "єс",
}

EXCLUDED_NORMALIZED = {
    "район",
    "если",
    "это",
    "без",
    "над",
    "также",
    "центр",
    "група",
    "группа",
    "нові",
    "нови",
    "аналитика",
    "аналітика",
    "подписаться",
    "подписатся",
    "подпишись",
    "підписатися",
    "надіслати",
    "реактивний",
    "реактивный",
    "ударный",
    "удары",
    "ес",
    "єс",
    "рух",
    "они",
    "тор",
    "бал",
    "сум",
    "дон",
    "укр",
    "бор",
    "мир",
    "над",
    "при",
    "для",
    "или",
    "ещё",
    "еще",
    "все",
    "всё",
    "тут",
    "там",
    "они",
    "она",
    "его",
    "них",
    "наш",
    "ваш",
    "так",
    "уже",
    "еще",
    "ещё",
    "труха",
    "соловь",
    "vvoenkor",
}

MAX_POST_COVERAGE_RATIO = 0.35
TARGET_MARKERS = 350
# Drop longer marker when a shorter one in the same category already covers it
# (e.g. "Бровар" covers "Бровары", but "Дніпр" does not replace "Дніпропетров").
MAX_COVERED_SUFFIX_LEN = 6

CURATED_MARKERS: list[tuple[str, str]] = [
    # Locations
    ("Київ", "location"),
    ("Киев", "location"),
    ("Києв", "location"),
    ("Київщин", "location"),
    ("Киевщин", "location"),
    ("столиц", "location"),
    ("Харків", "location"),
    ("Харьков", "location"),
    ("Харківщин", "location"),
    ("Харьковск", "location"),
    ("Одес", "location"),
    ("Дніпр", "location"),
    ("Днепр", "location"),
    ("Дніпропетров", "location"),
    ("Днепропетров", "location"),
    ("Запорож", "location"),
    ("Запоріж", "location"),
    ("Полтав", "location"),
    ("Сумщин", "location"),
    ("Сумск", "location"),
    ("Суми", "location"),
    ("Сумы", "location"),
    ("Черкас", "location"),
    ("Черніг", "location"),
    ("Житомир", "location"),
    ("Вінниц", "location"),
    ("Винниц", "location"),
    ("Микола", "location"),
    ("Николаев", "location"),
    ("Херсон", "location"),
    ("Крим", "location"),
    ("Крым", "location"),
    ("Кривой", "location"),
    ("Кривий", "location"),
    ("Павлоград", "location"),
    ("Бровар", "location"),
    ("Ірпін", "location"),
    ("Ирпен", "location"),
    ("Буч", "location"),
    ("Вишгород", "location"),
    ("Вишнев", "location"),
    ("Славутич", "location"),
    ("Жулян", "location"),
    ("Голосіїв", "location"),
    ("Голосеев", "location"),
    ("Дарниц", "location"),
    ("Печерськ", "location"),
    ("Печерск", "location"),
    ("Оболон", "location"),
    ("Поділ", "location"),
    ("Подол", "location"),
    ("Святошин", "location"),
    ("Соломян", "location"),
    ("Деснян", "location"),
    ("Шевченк", "location"),
    ("Дніпров", "location"),
    ("Львів", "location"),
    ("Львов", "location"),
    ("Луцьк", "location"),
    ("Луцк", "location"),
    ("Рівн", "location"),
    ("Ровн", "location"),
    ("Терноп", "location"),
    ("Ужгород", "location"),
    ("Хмельниц", "location"),
    ("Кропивниц", "location"),
    ("Кировоград", "location"),
    ("Чернівц", "location"),
    ("Черновц", "location"),
    ("Івано-Франк", "location"),
    ("Ивано-Франк", "location"),
    ("Конотоп", "location"),
    ("Шостк", "location"),
    ("Борисп", "location"),
    ("Фастів", "location"),
    ("Фастов", "location"),
    ("Васильк", "location"),
    ("Біла Церк", "location"),
    ("Белая Церк", "location"),
    ("Україн", "location"),
    ("Украин", "location"),
    ("Росі", "location"),
    ("Росси", "location"),
    ("Ростов", "location"),
    ("Бєлгород", "location"),
    ("Белгород", "location"),
    ("Курськ", "location"),
    ("Курск", "location"),
    ("Севастоп", "location"),
    ("Мелітоп", "location"),
    ("Мелитоп", "location"),
    ("Бердян", "location"),
    ("Маріуп", "location"),
    ("Мариуп", "location"),
    ("Донец", "location"),
    ("Луган", "location"),
    ("Бахмут", "location"),
    ("Авдіїв", "location"),
    ("Авдеев", "location"),
    ("Куп'ян", "location"),
    ("Купян", "location"),
    ("Ізюм", "location"),
    ("Изюм", "location"),
    ("Чугуїв", "location"),
    ("Чугуев", "location"),
    ("Краматор", "location"),
    ("Слов'ян", "location"),
    ("Славян", "location"),
    ("Кременч", "location"),
    ("Ніжин", "location"),
    ("Нежин", "location"),
    ("Прилу", "location"),
    ("Миргород", "location"),
    ("Лубн", "location"),
    ("Канів", "location"),
    ("Канев", "location"),
    ("Уман", "location"),
    ("Обухів", "location"),
    ("Обухов", "location"),
    ("Переяслав", "location"),
    ("Миронів", "location"),
    ("Миронов", "location"),
    ("Чорнобил", "location"),
    ("Чернобыл", "location"),
    ("Прип'ят", "location"),
    ("Припят", "location"),
    ("Чернігівщин", "location"),
    ("Черниговщин", "location"),
    ("Полтавщин", "location"),
    ("Одещин", "location"),
    ("Херсонщин", "location"),
    ("Миколаївщин", "location"),
    ("Запоріжж", "location"),
    ("Запорожь", "location"),
    ("Волин", "location"),
    ("Волын", "location"),
    ("Закарп", "location"),
    ("Закарпат", "location"),
    ("Черкащин", "location"),
    ("Чорномор", "location"),
    ("Черномор", "location"),
    ("Азов", "location"),
    ("Європ", "location"),
    ("Европ", "location"),
    ("Білорус", "location"),
    ("Беларус", "location"),
  # Weapons
    ("ракет", "weapon"),
    ("БПЛА", "weapon"),
    ("бпла", "weapon"),
    ("дрон", "weapon"),
    ("шахед", "weapon"),
    ("Шахед", "weapon"),
    ("Геран", "weapon"),
    ("мопед", "weapon"),
    ("крилат", "weapon"),
    ("Крилат", "weapon"),
    ("Искандер", "weapon"),
    ("Іскандер", "weapon"),
    ("Калибр", "weapon"),
    ("Калібр", "weapon"),
    ("Циркон", "weapon"),
    ("Кинжал", "weapon"),
    ("Кінжал", "weapon"),
    ("Орешник", "weapon"),
    ("Орешнік", "weapon"),
    ("Х-101", "weapon"),
    ("Х-22", "weapon"),
    ("Х-59", "weapon"),
    ("Х-69", "weapon"),
    ("Х-31", "weapon"),
    ("Х-35", "weapon"),
    ("Х-55", "weapon"),
    ("С-300", "weapon"),
    ("С-400", "weapon"),
    ("FPV", "weapon"),
    ("fpv", "weapon"),
    ("бомб", "weapon"),
    ("артил", "weapon"),
    ("снаряд", "weapon"),
    ("мін", "weapon"),
    ("мин", "weapon"),
    ("КАБ", "weapon"),
    ("кассет", "weapon"),
    ("фосфор", "weapon"),
    ("баліст", "weapon"),
    ("баллист", "weapon"),
    ("гиперзвук", "weapon"),
    ("гіперзвук", "weapon"),
    ("ЗРК", "weapon"),
    ("ПВО", "weapon"),
    ("зеніт", "weapon"),
    ("зенит", "weapon"),
    ("безпілот", "weapon"),
    ("беспилот", "weapon"),
    ("Shahed", "weapon"),
    ("Ланцет", "weapon"),
    ("Орлан", "weapon"),
    ("Гербер", "weapon"),
    ("Гераны", "weapon"),
    ("Герані", "weapon"),
    ("Онікс", "weapon"),
    ("Оникс", "weapon"),
    ("Точка", "weapon"),
    ("Точка-У", "weapon"),
    ("Смерч", "weapon"),
    ("Ураган", "weapon"),
    ("Град", "weapon"),
    ("HIMARS", "weapon"),
    ("ATACMS", "weapon"),
    ("Storm Shadow", "weapon"),
    ("Patriot", "weapon"),
    ("NASAMS", "weapon"),
    ("IRIS-T", "weapon"),
    ("Бук", "weapon"),
    ("Панцир", "weapon"),
    ("Панцирь", "weapon"),
    ("Оса", "weapon"),
    ("Стріла", "weapon"),
    ("Стрела", "weapon"),
    # Equipment
    ("Ту-95", "equipment"),
    ("ТУ-95", "equipment"),
    ("Ту-160", "equipment"),
    ("ТУ-160", "equipment"),
    ("Ту-22", "equipment"),
    ("Ту-22М3", "equipment"),
    ("МіГ-31", "equipment"),
    ("МиГ-31", "equipment"),
    ("МіГ-29", "equipment"),
    ("МиГ-29", "equipment"),
    ("Су-24", "equipment"),
    ("Су-25", "equipment"),
    ("Су-27", "equipment"),
    ("Су-30", "equipment"),
    ("Су-34", "equipment"),
    ("Су-35", "equipment"),
    ("Су-57", "equipment"),
    ("Іл-76", "equipment"),
    ("Ил-76", "equipment"),
    ("стратегічн", "equipment"),
    ("стратегическ", "equipment"),
    ("бомбардувальник", "equipment"),
    ("бомбардировщик", "equipment"),
    ("пусков", "equipment"),
    ("радар", "equipment"),
    ("РЛС", "equipment"),
    ("РЭБ", "equipment"),
    ("РЕБ", "equipment"),
    ("F-16", "equipment"),
    ("Байрактар", "equipment"),
    ("Bayraktar", "equipment"),
    ("TB2", "equipment"),
    ("винищувач", "equipment"),
    ("истребитель", "equipment"),
    ("штурмовик", "equipment"),
    ("штурмов", "equipment"),
    ("авіанос", "equipment"),
    ("авианос", "equipment"),
    ("підводн", "equipment"),
    ("подводн", "equipment"),
    ("РСЗО", "equipment"),
    ("РСЗВ", "equipment"),
    # Other
    ("тривог", "other"),
    ("вибух", "other"),
    ("взрыв", "other"),
    ("пуск", "other"),
    ("загроз", "other"),
    ("угроз", "other"),
    ("активн", "other"),
    ("моніторинг", "other"),
    ("мониторинг", "other"),
    ("повітрян", "other"),
    ("воздушн", "other"),
    ("зліт", "other"),
    ("взлет", "other"),
    ("посадк", "other"),
    ("прилёт", "other"),
    ("прилет", "other"),
    ("удар", "other"),
    ("обстрел", "other"),
    ("обстріл", "other"),
    ("атак", "other"),
    ("відбій", "other"),
    ("отбой", "other"),
    ("сирен", "other"),
    ("ППО", "other"),
    ("перехоп", "other"),
    ("перехват", "other"),
    ("збит", "other"),
    ("сбит", "other"),
    ("уражен", "other"),
    ("поражен", "other"),
    ("знищен", "other"),
    ("уничтож", "other"),
    ("влучан", "other"),
    ("попадан", "other"),
    ("падін", "other"),
    ("паден", "other"),
    ("дим", "other"),
    ("дым", "other"),
    ("пожар", "other"),
    ("Пожар", "other"),
    ("пожеж", "other"),
    ("летят", "other"),
    ("летит", "other"),
    ("маневр", "other"),
    ("напрям", "other"),
    ("направлен", "other"),
    ("траєктор", "other"),
    ("траектор", "other"),
    ("швидкіст", "other"),
    ("скорост", "other"),
    ("висот", "other"),
    ("высот", "other"),
    ("радіолок", "other"),
    ("радиолок", "other"),
    ("виявлен", "other"),
    ("обнаруж", "other"),
    ("фіксован", "other"),
    ("фиксирован", "other"),
    ("спостер", "other"),
    ("наблюд", "other"),
    ("реактивн", "other"),
    ("балістич", "other"),
    ("баллистич", "other"),
    ("масован", "other"),
    ("массирован", "other"),
    ("комбінован", "other"),
    ("комбинирован", "other"),
    ("нічн", "other"),
    ("ночн", "other"),
    ("ранков", "other"),
    ("утрен", "other"),
    ("вечірн", "other"),
    ("вечерн", "other"),
    ("очіку", "other"),
    ("ожида", "other"),
    ("ймовір", "other"),
    ("вероят", "other"),
    ("можлив", "other"),
    ("возмож", "other"),
    ("підтвердж", "other"),
    ("подтвержд", "other"),
]

TECH_PATTERNS = [
    (re.compile(r"Т[уУ]-95(?:МС|мс)?", re.IGNORECASE), "equipment"),
    (re.compile(r"Т[уУ]-160", re.IGNORECASE), "equipment"),
    (re.compile(r"Т[уУ]-22(?:М3|м3)?", re.IGNORECASE), "equipment"),
    (re.compile(r"[Мм]і?[Гг]-31", re.IGNORECASE), "equipment"),
    (re.compile(r"[Мм]і?[Гг]-29", re.IGNORECASE), "equipment"),
    (re.compile(r"[Сс]у-\d{2}", re.IGNORECASE), "equipment"),
    (re.compile(r"[ХхXx]-\d{2,3}", re.IGNORECASE), "weapon"),
    (re.compile(r"[Сс]-[34]00", re.IGNORECASE), "weapon"),
    (re.compile(r"[ІИ]л-\d{2,3}", re.IGNORECASE), "equipment"),
    (re.compile(r"F-\d{2}", re.IGNORECASE), "equipment"),
]

SEED_MARKERS: list[tuple[str, str]] = [
    ("прилёт", "other"),
    ("Пожар", "other"),
    ("дым", "other"),
    ("ракет", "weapon"),
    ("БПЛА", "weapon"),
    ("крилат", "weapon"),
    ("Циркон", "weapon"),
    ("Ту-160", "equipment"),
    ("Ту-95", "equipment"),
    ("бомбардировщик", "equipment"),
    ("летят", "other"),
    ("мопед", "weapon"),
    ("столиц", "location"),
    ("Бровар", "location"),
    ("Киев", "location"),
    ("Славутич", "location"),
    ("Київ", "location"),
    ("Жулян", "location"),
    ("Голосіїв", "location"),
    ("Дарниц", "location"),
    ("Запорож", "location"),
]


def normalize_for_search(value: str) -> str:
    return value.casefold().replace("ё", "е").replace("Ё", "е")


def normalize_marker_text(value: str) -> str:
    return " ".join(value.split()).strip()


def valid_category(value: str) -> str:
    return value if value in VALID_CATEGORIES else "other"


def is_allowed_marker(text: str) -> bool:
    normalized = normalize_for_search(text)
    if not normalized or normalized in EXCLUDED_NORMALIZED:
        return False
    if len(normalized) < MIN_MARKER_LENGTH:
        return False
    if len(normalized) < 4 and normalized not in SHORT_MARKER_WHITELIST:
        return False
    return True


def load_posts() -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
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


def load_seed_markers() -> list[tuple[str, str]]:
    return list(SEED_MARKERS)


def merge_markers(*sources: list[tuple[str, str]]) -> dict[str, tuple[str, str]]:
    merged: dict[str, tuple[str, str]] = {}
    for source in sources:
        for text, category in source:
            normalized_text = normalize_marker_text(text)
            if not is_allowed_marker(normalized_text):
                continue
            merged[normalize_for_search(normalized_text)] = (
                normalized_text,
                valid_category(category),
            )
    return merged


def discover_tech_markers(corpus: str) -> list[tuple[str, str]]:
    discovered: list[tuple[str, str]] = []
    for pattern, category in TECH_PATTERNS:
        for match in pattern.finditer(corpus):
            text = normalize_marker_text(match.group(0))
            if is_allowed_marker(text):
                discovered.append((text, category))
    return discovered


def count_matches(marker_text: str, corpus_normalized: str, post_texts_normalized: list[str]) -> tuple[int, int]:
    normalized_marker = normalize_for_search(marker_text)
    if not normalized_marker:
        return 0, 0

    substring_hits = corpus_normalized.count(normalized_marker)
    post_hits = sum(1 for post_text in post_texts_normalized if normalized_marker in post_text)
    return substring_hits, post_hits


def sort_markers(markers: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        markers,
        key=lambda marker: (
            CATEGORY_ORDER.get(marker["category"], 99),
            normalize_for_search(marker["text"]),
        ),
    )


def is_covered_by_marker(shorter: str, longer: str) -> bool:
    shorter_normalized = normalize_for_search(shorter)
    longer_normalized = normalize_for_search(longer)
    if not shorter_normalized or shorter_normalized == longer_normalized:
        return False
    if not longer_normalized.startswith(shorter_normalized):
        return False
    return len(longer_normalized) - len(shorter_normalized) <= MAX_COVERED_SUFFIX_LEN


def dedupe_covered_markers(
    markers: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[tuple[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {category: [] for category in VALID_CATEGORIES}
    for marker in markers:
        grouped[marker["category"]].append(marker)

    kept: list[dict[str, str]] = []
    dropped: list[tuple[str, str]] = []

    for group in grouped.values():
        remaining = list(group)
        changed = True
        while changed:
            changed = False
            remaining.sort(key=lambda marker: len(normalize_for_search(marker["text"])))
            to_remove: list[dict[str, str]] = []
            for index, short_marker in enumerate(remaining):
                for long_marker in remaining[index + 1 :]:
                    if is_covered_by_marker(short_marker["text"], long_marker["text"]):
                        to_remove.append(long_marker)
                        dropped.append((long_marker["text"], short_marker["text"]))
                        changed = True
            if to_remove:
                remove_ids = {id(marker) for marker in to_remove}
                remaining = [marker for marker in remaining if id(marker) not in remove_ids]
        kept.extend(remaining)

    return sort_markers(kept), dropped


def build_markers(posts: list[dict[str, Any]]) -> tuple[list[dict[str, str]], str]:
    post_texts = [str(post.get("text") or "") for post in posts]
    post_texts_normalized = [normalize_for_search(text) for text in post_texts]
    corpus = "\n".join(post_texts)
    corpus_normalized = normalize_for_search(corpus)

    merged = merge_markers(
        load_seed_markers(),
        CURATED_MARKERS,
        discover_tech_markers(corpus),
    )

    validated_with_stats: list[tuple[dict[str, str], int, int]] = []
    dropped_zero: list[str] = []
    dropped_broad: list[tuple[str, int, int]] = []
    stats: list[tuple[str, str, int, int]] = []

    max_post_hits = max(1, int(len(posts) * MAX_POST_COVERAGE_RATIO))

    for text, category in merged.values():
        substring_hits, post_hits = count_matches(text, corpus_normalized, post_texts_normalized)
        stats.append((text, category, substring_hits, post_hits))

        if substring_hits == 0:
            dropped_zero.append(text)
            continue

        if post_hits > max_post_hits:
            dropped_broad.append((text, post_hits, substring_hits))
            continue

        validated_with_stats.append(({"text": text, "category": category}, post_hits, substring_hits))

    validated_with_stats.sort(key=lambda item: (item[2], item[1]), reverse=True)
    if len(validated_with_stats) > TARGET_MARKERS:
        validated_with_stats = validated_with_stats[:TARGET_MARKERS]

    validated_before_dedupe = [marker for marker, _, _ in validated_with_stats]
    validated, dropped_covered = dedupe_covered_markers(validated_before_dedupe)

    report_lines = [
        "Markers validation report",
        f"Input posts: {len(posts)}",
        f"Posts with text: {sum(1 for text in post_texts if text.strip())}",
        f"Candidate markers: {len(merged)}",
        f"Final markers: {len(validated)}",
        f"Dropped (zero hits): {len(dropped_zero)}",
        f"Dropped (too broad, >{MAX_POST_COVERAGE_RATIO:.0%} posts): {len(dropped_broad)}",
        f"Dropped (covered by shorter root, suffix <= {MAX_COVERED_SUFFIX_LEN}): {len(dropped_covered)}",
        "",
        "Top 20 markers by substring hits:",
    ]

    for text, category, substring_hits, post_hits in sorted(stats, key=lambda item: item[2], reverse=True)[:20]:
        report_lines.append(f"  {substring_hits:4d} hits / {post_hits:4d} posts  [{category}]  {text}")

    if dropped_zero:
        report_lines.extend(["", "Dropped zero-hit markers:"])
        for text in sorted(dropped_zero, key=normalize_for_search):
            report_lines.append(f"  - {text}")

    if dropped_broad:
        report_lines.extend(["", "Dropped overly-broad markers:"])
        for text, post_hits, substring_hits in sorted(dropped_broad, key=lambda item: item[1], reverse=True):
            report_lines.append(f"  - {text} ({post_hits} posts, {substring_hits} hits)")

    if dropped_covered:
        report_lines.extend(["", "Dropped markers covered by shorter root:"])
        for removed, covered_by in sorted(dropped_covered, key=lambda item: normalize_for_search(item[0])):
            report_lines.append(f"  - {removed}  (covered by {covered_by})")

    report_lines.extend(["", "By category:"])
    category_counts = Counter(marker["category"] for marker in validated)
    for category in VALID_CATEGORIES:
        report_lines.append(f"  {category}: {category_counts.get(category, 0)}")

    return validated, "\n".join(report_lines) + "\n"


def main() -> None:
    posts = load_posts()
    markers, report = build_markers(posts)

    OUTPUT_PATH.write_text(
        json.dumps(markers, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    REPORT_PATH.write_text(report, encoding="utf-8")

    print(report)
    print(f"Wrote {len(markers)} markers to {OUTPUT_PATH}")
    print(f"Wrote report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
