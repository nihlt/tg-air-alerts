"""
extract_weapons.py — вилучає всі унікальні слова/фрази зброї з JSONL-файлу.
Повертає плоский список у weapons_list.json.
"""

import json
import re
from pathlib import Path


WEAPON_PATTERNS = [
    r"(?i)\bбпла\b",
    r"(?i)\bдрон[а-яіїєa-z]*\b",
    r"(?i)\bбеспилотник[а-я]*\b",
    r"(?i)\bбезпілотник[а-я]*\b",
    r"(?i)\bшахед[а-яa-z]*\b",
    r"(?i)\bshahed[a-z]*\b",
    r"(?i)\bгеран[іьa-яa-z]*\b",
    r"(?i)\bракет[а-я]*\b",
    r"(?i)\bбалістичн[а-я]*\b",
    r"(?i)\bбаллистическ[а-я]*\b",
    r"(?i)\bіскандер[а-я-]*\b",
    r"(?i)\bискандер[а-я-]*\b",
    r"(?i)\bкрилат[а-я]*\b",
    r"(?i)\bкрылат[а-я]*\b",
    r"(?i)\bту-95[а-яa-z\s]*\b",
    r"(?i)\btu-95\b",
    r"(?i)\bfpv\b",
    r"(?i)\bfp-9\b",
    r"(?i)\bвибух[а-я]*\b",
    r"(?i)\bвзрыв[а-я]*\b",
    r"(?i)\bприл[еі]т[а-я]*\b",
    r"(?i)\bудар[а-я]*\b",
    r"(?i)\bатак[а-я]*\b",
    r"(?i)\bобстріл[а-я]*\b",
    r"(?i)\bобстрел[а-я]*\b",
    r"(?i)\bстратег[іч][а-я]*\s+ав[іа]ац[а-я]*\b",
    r"(?i)\bіскандер-м\b",
    r"(?i)\bискандер-м\b",
    r"(?i)\btu-95\s*мс\b",
    r"(?i)\bту-95\s*мс\b",
    r"(?i)\bкинджал[а-я]*\b",
    r"(?i)\bкинжал[а-я]*\b",
    r"(?i)\bx-[0-9]+[а-яa-z]*\b",
    r"(?i)\bх-[0-9]+[а-яa-z]*\b",
    r"(?i)\bкалібр[а-я]*\b",
    r"(?i)\bкалибр[а-я]*\b",
    r"(?i)\bс-300\b",
    r"(?i)\bс-400\b",
    r"(?i)\bзаліз[а-я]*\b",
]

COMPILED = [re.compile(p) for p in WEAPON_PATTERNS]


def main():
    base_dir = Path(__file__).parent
    input_file = base_dir / "tg_posts_2026-07-01_1600_to_2026-07-02_0800.jsonl"
    output_file = base_dir / "weapons_list.json"

    found: set[str] = set()

    with input_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            post = json.loads(line)
            text = post.get("text", "") or ""
            if not text:
                continue

            for pattern in COMPILED:
                for match in pattern.finditer(text):
                    word = match.group(0).strip()
                    if word:
                        found.add(word)

    result = sorted(found, key=lambda x: x.lower())

    with output_file.open("w", encoding="utf-8") as out:
        json.dump(result, out, ensure_ascii=False, indent=2)

    print(f"Знайдено унікальних варіантів: {len(result)}")
    print(f"Збережено у: {output_file}")


if __name__ == "__main__":
    main()
