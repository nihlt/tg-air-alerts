"""
extract_entities.py — аналіз і вилучення унікальних основ слів (без закінчень)
з Telegram-постів у JSONL-форматі для всіх категорій.
"""

import json
import logging
import re
from pathlib import Path

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("entity-extractor")

# Словники для пошуку
LOCATIONS_MAPPING = {
    "Київ": [r"(?i)\bкиї[вф][а-я]*\b", r"(?i)\bкиє[вф][а-я]*\b", r"(?i)\bкие[вф][а-я]*\b", r"(?i)\bkyiv\b", r"(?i)\bстолиц[а-я]*\b"],
    "Київська область": [r"(?i)\bкиївськ[a-я]*\s+област[а-я]*\b", r"(?i)\bкиевск[a-я]*\s+област[а-я]*\b"],
    "Харків": [r"(?i)\bхарк[ііо][вф][а-я]*\b"],
    "Дніпро": [r"(?i)\bдніпр[а-я]*\b", r"(?i)\bднепр[а-я]*\b"],
    "Одеса": [r"(?i)\bодес[а-я]*\b"],
    "Одеська область": [r"(?i)\bодеськ[а-я]*\s+област[а-я]*\b", r"(?i)\bодесск[а-я]*\s+област[а-я]*\b"],
    "Запоріжжя": [r"(?i)\bзапор[ііо]ж[а-я]*\b"],
    "Миколаїв": [r"(?i)\bмикол[а-я]*\b", r"(?i)\bникол[а-я]*\b"],
    "Львів": [r"(?i)\bльві[вф][а-я]*\b", r"(?i)\bльво[вф][а-я]*\b", r"(?i)\blviv\b"],
    "Херсон": [r"(?i)\bхерсон[а-я]*\b"],
    "Маріуполь": [r"(?i)\bмаріуп[а-я]*\b", r"(?i)\bмариуп[а-я]*\b"],
    "Кривий Ріг": [r"(?i)\bкрив[ио][йі]\s+р[оі]г[а-я]*\b"],
    "Полтава": [r"(?i)\bполтав[а-я]*\b"],
    "Суми": [r"(?i)\bсум[а-я]+\b"],
    "Чернігів": [r"(?i)\bчерніг[а-я]*\b", r"(?i)\bчерниг[а-я]*\b"],
    "Вінниця": [r"(?i)\bвінниц[а-я]*\b", r"(?i)\bвинниц[а-я]*\b"],
    "Житомир": [r"(?i)\bжитомир[а-я]*\b"],
    "Черкаси": [r"(?i)\bчеркас[а-я]*\b"],
    "Кропивницький": [r"(?i)\bкропив[а-я]*\b"],
    "Луцьк": [r"(?i)\bлуцьк[а-я]*\b", r"(?i)\bлуцк[а-я]*\b"],
    "Рівне": [r"(?i)\bрівн[а-я]*\b", r"(?i)\bровн[а-я]*\b"],
    "Ужгород": [r"(?i)\bужгород[а-я]*\b"],
    "Тернопіль": [r"(?i)\bтерноп[а-я]*\b"],
    "Хмельницький": [r"(?i)\bхмельниц[а-я]*\b"],
    "Костянтинівка": [r"(?i)\bкостянтин[а-я]*\b", r"(?i)\bконстантин[а-я]*\b"],
    "Слов'янськ": [r"(?i)\bслов'ян[а-я]*\b", r"(?i)\bславян[а-я]*\b"],
    "Краматорськ": [r"(?i)\bкраматор[а-я]*\b"],
    "Красний Лиман": [r"(?i)\bкрасн[ийо]\s+лиман[а-я]*\b", r"(?i)\bчервон[ийі]\s+лиман[а-я]*\b"],
    "Лиман": [r"(?i)\bлиман[а-я]*\b"],
    "Донбас": [r"(?i)\bдонбас[а-я]*\b"],
    "Крим": [r"(?i)\bкрим[а-я]*\b", r"(?i)\bкрым[а-я]*\b"],
    "Україна": [r"(?i)\bукраїн[а-я]*\b", r"(?i)\bукраин[а-я]*\b", r"(?i)\bukraine\b"],
    "Павлоград": [r"(?i)\bпавлог[а-я]*\b"],
    "Московська область": [r"(?i)\bмосковск[а-я]*\s+област[а-я]*\b", r"(?i)\bмосковськ[а-я]*\s+област[а-я]*\b"]
}

PHRASE_PATTERNS = {
    "weapons": [
        r"(?i)\bстратег[іч]еск[а-я]*\s+ав[іа]ац[а-я]*\b",
        r"(?i)\bіскандер-м\b",
        r"(?i)\bискандер-м\b",
        r"(?i)\bту-95\s*мс\b"
    ],
    "air_defense": [
        r"(?i)\bповітрян[а-я]*\s+тривог[а-я]*\b",
        r"(?i)\bвоздушн[а-я]*\s+тревог[а-я]*\b",
        r"(?i)\bсигнал[а-я]*\s+тривог[а-я]*\b",
        r"(?i)\bс-300\b",
        r"(?i)\bс-400\b",
        r"(?i)\bc-300\b",
        r"(?i)\bc-400\b"
    ]
}

WORD_PATTERNS = {
    "weapons": [
        r"(?i)\bбпла\b", r"(?i)\bдрон[а-я]*\b", r"(?i)\bбеспилотник[а-я]*\b", r"(?i)\bбезпілотник[а-я]*\b",
        r"(?i)\bшахед[а-я]*\b", r"(?i)\bshahed[а-я]*\b", r"(?i)\bгеран[іь][а-я]*\b", r"(?i)\bгеранист[а-я]*\b",
        r"(?i)\bракет[а-я]*\b", r"(?i)\bбалістичн[а-я]*\b", r"(?i)\bбаллистическ[а-я]*\b",
        r"(?i)\bіскандер[а-я]*\b", r"(?i)\bискандер[а-я]*\b", r"(?i)\bкрилат[а-я]*\b", r"(?i)\bкрылат[а-я]*\b",
        r"(?i)\bту-95\b", r"(?i)\btu-95\b", r"(?i)\bfp-9\b", r"(?i)\bfpv\b",
        r"(?i)\bвибух[а-я]*\b", r"(?i)\bвзрыв[а-я]*\b",
        r"(?i)\bприл[еі]т[а-я]*\b",
        r"(?i)\bудар[а-я]*\b", r"(?i)\bатак[а-я]*\b", r"(?i)\bобстріл[а-я]*\b", r"(?i)\bобстрел[а-я]*\b"
    ],
    "air_defense": [
        r"(?i)\bппо\b", r"(?i)\bпво\b", r"(?i)\bпротиповітрян[а-я]*\b", r"(?i)\bпротивовоздушн[а-я]*\b",
        r"(?i)\bpatriot[s]?\b", r"(?i)\bпатріот[а-я]*\b", r"(?i)\bпатриот[а-я]*\b",
        r"(?i)\bзбит[а-я]*\b", r"(?i)\bсбит[а-я]*\b", r"(?i)\bперехопл[а-я]*\b", r"(?i)\bперехвач[а-я]*\b",
        r"(?i)\bтривог[а-я]*\b", r"(?i)\btrevog[а-я]*\b",
        r"(?i)\bукритт[а-я]*\b", r"(?i)\bубежищ[а-я]*\b", r"(?i)\bметро\b"
    ]
}


def clean_word(word: str) -> str:
    """Видаляє розділові знаки на початку та в кінці слова."""
    return re.sub(r"^[^\w\d-]+|[^\w\d-]+$", "", word)


def strip_endings(word: str) -> str:
    """
    Видаляє відмінкові та множинні закінчення для українських/російських слів.
    Повертає чисту основу слова. Абревіатури та короткі слова залишає без змін.
    """
    # Якщо абревіатура або коротке слово, не чіпаємо закінчення
    if word.isupper() and len(word) <= 5:
        return word

    word_lower = word.lower()

    # Закінчення для видалення (від найдовших до найкоротших)
    endings = [
        "скими", "ськими", "ської", "ською", "ський", "ським", "ських",
        "ского", "скому", "ском", "ских", "ские", "ская", "ское", "ой", "ых", "их",
        "ської", "ській", "ською", "ського", "ському", "ським", "ських", "ські",
        "ями", "ами", "ові", "еві", "ою", "ею", "єю",
        "ах", "ях", "ів", "ов", "ев", "ей", "ем", "ом", "им", "их", "ых", "ий", "ый", "ая", "яя", "ое", "ее", "ые", "ие",
        "а", "я", "и", "і", "ы", "е", "у", "ю", "о", "ь"
    ]

    for ending in endings:
        if word_lower.endswith(ending):
            # Перевіряємо, щоб основа залишалась не менше 3 символів
            if len(word_lower) - len(ending) >= 3:
                return word_lower[:-len(ending)]
            break

    return word_lower


def main():
    base_dir = Path(__file__).parent
    input_file = base_dir / "tg_posts_2026-07-01_1600_to_2026-07-02_0800.jsonl"
    output_file = base_dir / "extracted_entities.json"

    if not input_file.exists():
        log.error("Вхідний файл не знайдено: %s", input_file)
        return

    # Збірки для унікальних значений
    extracted = {
        "locations": set(),
        "weapons": set(),
        "air_defense": set()
    }

    log.info("Аналізуємо файл: %s", input_file)

    # 1. Завантажуємо локації та перетворюємо канонічні назви на основу
    compiled_locations = {
        canonical: [re.compile(p) for p in patterns]
        for canonical, patterns in LOCATIONS_MAPPING.items()
    }

    # 2. Компільовані регулярні вирази для інших категорій
    compiled_phrases = {
        cat: [re.compile(p) for p in patterns]
        for cat, patterns in PHRASE_PATTERNS.items()
    }
    
    compiled_words = {
        cat: [re.compile(p) for p in patterns]
        for cat, patterns in WORD_PATTERNS.items()
    }

    with input_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            post = json.loads(line)
            text = post.get("text", "") or ""
            if not text:
                continue

            # Пошук локацій (беремо канонічну назву та відрізаємо закінчення)
            for canonical, regex_list in compiled_locations.items():
                for regex in regex_list:
                    if regex.search(text):
                        stemmed_loc = strip_endings(canonical)
                        extracted["locations"].add(stemmed_loc)

            # Пошук багатослівних фраз для інших категорій (відрізаємо закінчення для кожного слова у фразі)
            temp_text = text
            for cat, regex_list in compiled_phrases.items():
                for regex in regex_list:
                    for match in regex.finditer(text):
                        matched_str = match.group(0).strip()
                        matched_str = re.sub(r"\s+", " ", matched_str)
                        
                        # Робимо кожне слово у фразі без закінчень
                        phrase_words = matched_str.split()
                        stemmed_phrase = " ".join(strip_endings(clean_word(w)) for w in phrase_words)
                        
                        extracted[cat].add(stemmed_phrase)
                        temp_text = temp_text.replace(match.group(0), " ")

            # Пошук окремих слів для інших категорій
            words = temp_text.split()
            for word in words:
                cleaned = clean_word(word)
                if not cleaned:
                    continue
                
                for cat, regex_list in compiled_words.items():
                    for regex in regex_list:
                        if regex.match(cleaned):
                            stemmed_word = strip_endings(cleaned)
                            extracted[cat].add(stemmed_word)
                            break

    # Сортуємо результати
    sorted_results = {
        "locations": sorted(list(extracted["locations"])),
        "weapons": sorted(list(extracted["weapons"])),
        "air_defense": sorted(list(extracted["air_defense"]))
    }

    # Додаткове очищення пустих значень
    for cat in sorted_results:
        sorted_results[cat] = [item for item in sorted_results[cat] if item]

    with output_file.open("w", encoding="utf-8") as out:
        json.dump(sorted_results, out, ensure_ascii=False, indent=2)

    log.info("Вилучення завершено!")
    log.info("Збережено унікальних значень:")
    log.info("  Локацій (без закінчень): %d", len(sorted_results["locations"]))
    log.info("  Зброї (без закінчень): %d", len(sorted_results["weapons"]))
    log.info("  Захисту (без закінчень): %d", len(sorted_results["air_defense"]))


if __name__ == "__main__":
    main()
