# План: Telegram-алерти та рейтинг



Статус: **реалізовано** (debug + live).



## Контекст



1. **Простий текст події** — 3 блоки.

2. **Відправка** — фото (альбом) → текст з кнопками.

3. **Рейтинг** — `bullshit` | `valuable`, лог у JSONL.



**Live:** `listen_tg_channels.py` + `tg_live_events.py` — групування в реальному часі.



**Debug:** `tg_bot_debug.py` — перегляд експорту, той самий формат.



---



## TODO — реалізація



- [x] `format_event_text`, `tg_send.py`, `tg_rating.py`

- [x] `tg_bot_debug.py` — рейтинг, help

- [x] **Live:** `tg_live_events.py`, `listen_tg_channels.py`, `tg_bot_handlers.py`

- [x] `/toggle` для шумних постів (per-user у `tg_subscribers.json`)

- [x] `exports/live_listener_state.json` (лише `update_offset`)

- [x] Розсилка підписникам (`tg_subscribers.py`, `/start`)

- [x] Одне фото на канал у альбомі

- [x] Посилання на пост (не канал) + subscribe footer



---



## TODO — майбутнє



- [ ] Аналіз `exports/ratings.jsonl`



---



## Перевірка



```bash

python preview_tg_alert.py --event evt_0001

python tg_bot_debug.py

run_listener.bat

```



Live: події після ~2–3 хв, summary одразу, `/start` для підписки, `/toggle` для шуму (per-user), кнопки рейтингу.



---



## Приклад UX



```

[альбом фото]



3 Ракети → Київ, Харків



14:32–14:45 · 5 джерел

eRadarrua · monitor_ukraine



[bullshit]  [valuable]

```


