# TG Air Alerts

Невеликий Python-проєкт для експорту постів із Telegram-каналів за заданий проміжок часу та побудови локальної HTML-стрічки новин.

## Можливості

- читає список Telegram-каналів із `tg-chanel-links.txt`;
- експортує пости через Telethon у `exports/*.jsonl`;
- завантажує фото постів у `exports/photos/`;
- генерує локальну сторінку `exports/news.html` для перегляду результатів.

## Вимоги

- Python 3.11+;
- Telegram API credentials: `api_id` і `api_hash` з [my.telegram.org](https://my.telegram.org/).

## Швидкий старт

Створіть і активуйте віртуальне середовище:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Встановіть залежності:

```powershell
pip install -r requirements.txt
```

Скопіюйте приклад конфігурації:

```powershell
Copy-Item .env.example .env
```

Заповніть у `.env` значення `api_id`, `api_hash` і, за потреби, `phone` або `bot_token`.

## Використання

Оновіть список каналів у `tg-chanel-links.txt`, після чого запустіть експорт:

```powershell
python download_tg_posts.py
```

Після завершення експорту згенеруйте HTML-сторінку:

```powershell
python build_news_html.py
```

Результати з'являться в каталозі `exports/`.

## Налаштування періоду

Проміжок часу задається в `download_tg_posts.py` константами:

- `START_KYIV`;
- `END_KYIV`;
- `OUTPUT_PATH`.

Якщо змінюєте назву JSONL-файлу експорту, оновіть також `INPUT_PATH` у `build_news_html.py`.

## Безпека

Файли `.env`, Telegram-сесії та каталог `exports/` додані в `.gitignore`, тому їх не потрібно публікувати в GitHub. Перед першим комітом перевірте `git status`, щоб переконатися, що приватні ключі, сесії та згенеровані дані не потрапляють у staging.
