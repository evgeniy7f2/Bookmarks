# Bookmarks
Bookmarks
<p align="center">
  <img src="bookmarks/static/favicon.svg" width="72" alt="Bookmarks icon">
</p>

<h1 align="center">🔖 Bookmarks</h1>

<p align="center">
  A self-hosted bookmark manager: one Python process, one SQLite file, zero external services.<br>
  A beautiful place for the links that matter to you.
</p>

<p align="center">
  <b>English</b> · <a href="#-русский">Русский</a>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.10%2B-3776ab?logo=python&logoColor=white" alt="Python 3.10+"></a>
  <img src="https://img.shields.io/badge/Flask-3.x-black?logo=flask&logoColor=white" alt="Flask 3.x">
  <img src="https://img.shields.io/badge/version-1.0.9-2ea44f" alt="Version 1.0.9">
  <img src="https://img.shields.io/badge/storage-SQLite-003b57" alt="SQLite storage">
  <img src="https://img.shields.io/badge/interface-EN%20%2F%20RU-555555" alt="EN / RU interface">
</p>

---

## ✨ Features

- **Multi-user** — registration and login; each account has its own private space
- **Groups & “Favorites”** — custom groups, built-in “Favorites” group, drag-free reordering via a menu
- **🔐 Secret group** — a special group (right after “Favorites”) whose links are hidden from “Home”, search and tags until you enter a session password; 🔐/🔓 is both an indicator and a toggle
- **Tags, search & sorting** — full-text search over titles, URLs, descriptions and tags; sort by date, name or visit count
- **Import & export** — JSON and Netscape HTML (the standard browser export format)
- **Automatic metadata** — page titles, descriptions and favicons are fetched automatically (with cache and retry for failed loads)
- **Personalization** — Russian/English UI, light & dark themes, accent colors, 5 custom quick-links at the bottom of the sidebar (with own icons and reordering), mini-calendar next to the clock
- **Security** — scrypt password hashing, session cookies (HttpOnly, SameSite), CSP and security headers, login rate-limiting, non-root container user

## 🚀 Quick start

Requirements: **Python 3.10+** (or Docker).

```sh
git clone https://github.com/evgeniy7f2/bookmarks.git
cd bookmarks
python3 app.py
```

Open <http://127.0.0.1:8765>, register a user — and you are done.

---

## 🐧 Linux (Ubuntu / Debian)

1. Install Python if you don't have it:

   ```sh
   sudo apt update && sudo apt install -y python3 python3-venv
   ```

2. Get the project (clone, or copy the folder to the machine).

**Option A — quick run** (venv is created automatically):

```sh
cd bookmarks
./run.sh
```

**Option B — `install.sh`** (background process or systemd service with auto-start):

```sh
bash install.sh            # venv + start in background (nohup), log in data/server.log
bash install.sh systemd    # venv + systemd service (survives reboot)
```

Useful environment variables for `install.sh`: `PORT` (default `8765`),
`HOST_BIND` (default `0.0.0.0`), `BOOKMARKS_DATA` (default `<root>/data`).

**Check it works:**

```sh
curl http://127.0.0.1:8765/health
# {"app":"Bookmarks","version":"1.0.9","ok":true}
```

---

## 🪟 Windows

1. Install [Python 3.10+](https://www.python.org/downloads/) — during setup
   check **“Add python.exe to PATH”**.

2. Get the project folder (clone, or copy it to the PC, e.g. `C:\bookmarks`).

**Option A — one click:** double-click **`run.bat`**.
It creates a virtual environment, installs the only dependency (Flask) and
starts the server with the browser open.

**Option B — manually:**

```powershell
cd C:\bookmarks
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python app.py --open
```

**Check it works:** open <http://127.0.0.1:8765> in the browser, or in PowerShell:

```powershell
(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/health).Content
# {"app":"Bookmarks","version":"1.0.9","ok":true}
```

> If the port is busy, find the owner: `netstat -ano | findstr 8765`,
> or run with a different port: `python app.py --port 8080`.

---

## 🐳 Docker

```sh
cd bookmarks
docker compose up -d --build
```

Or without compose (equivalent):

```sh
docker build -t bookmarks .
docker run -d --name bookmarks -p 8765:8765 -v bookmarks_data:/data bookmarks
```

- Image base: `python:3.12-slim`; the app runs as a **non-root** user (uid 10001)
- Data lives in a named volume at `/data` — it survives rebuilds and container removal
- Healthcheck (`GET /health`) is built into the image
- Server log timezone: `TZ` in `docker-compose.yml` (default `Etc/MSK`);
  the UI always shows your browser's local time

**Updating** after code changes: `docker compose up -d --build` (data stays).
**Stopping:** `docker compose down` (data stays) · `down -v` (removes the data volume — careful!).

📖 A full step-by-step guide — installing Docker Desktop on Windows (WSL2),
migrating existing data, troubleshooting — is in **[DOCKER.md](DOCKER.md)**.

---

## ⚙️ Configuration

### `app.py` flags

| Flag | Default | Description |
| --- | --- | --- |
| `--host` | `0.0.0.0` | bind address |
| `--port` | `8765` | port |
| `--data` | `./data` | data directory (same as `BOOKMARKS_DATA`) |
| `--debug` | off | Flask debug mode |
| `--open` | off | open the browser on start |
| `--version` | | show version |

### Environment variables

| Variable | Description |
| --- | --- |
| `BOOKMARKS_DATA` | data directory (DB, favicon cache, `secret.key`) |
| `BOOKMARKS_SECRET` | cookie-signing secret (otherwise `secret.key` is auto-generated in the data dir) |
| `BOOKMARKS_COOKIE_SECURE` | `1/true/yes` — session cookie only over HTTPS (behind a reverse proxy) |
| `BOOKMARKS_BLOCK_PRIVATE` | `1/true/yes` — don't fetch favicons/metadata from private IP ranges |

## 📦 Data

Everything is stored in the data directory (default `./data`, created automatically):

- `bookmarks.db` — SQLite: users, sessions, groups, bookmarks, tags
- `icons/` — favicon cache and statuses of failed loads
- `secret.key` — generated cookie secret

To move your data to another machine: export JSON from the UI (Settings → Export)
and import it in the new copy — or copy `bookmarks.db` + `secret.key` into the
data dir (for Docker: `docker cp`).

## 🌐 API (short)

All endpoints are under `/api` and require a session (except register/login).
Responses are JSON; errors look like `{"error": "code"}`.

| Method & path | Purpose |
| --- | --- |
| `POST /api/auth/register` · `POST /api/auth/login` · `POST /api/auth/logout` | auth |
| `GET /api/auth/me` | current user |
| `GET/POST /api/groups` · `PATCH/DELETE /api/groups/<id>` | groups (secret group: `PATCH` only `{password}`) |
| `POST /api/groups/<id>/unlock` · `POST /api/groups/<id>/lock` | open/close the secret group |
| `GET/POST /api/bookmarks` · `PATCH/DELETE /api/bookmarks/<id>` | bookmarks |
| `POST /api/bookmarks/<id>/favorite` · `.../restore` · `DELETE .../purge` | favorite, trash |
| `POST /api/trash/empty` · `POST /api/trash/restore-all` | trash in bulk |
| `GET /api/tags` · `GET/PUT /api/settings` · `GET /api/stats` | tags, settings, stats |
| `GET /api/export?format=json\|html` · `POST /api/import` | import/export |
| `GET /api/metadata?url=` · `GET /api/icon?url=` | metadata / favicon |

`GET /health` — liveness check.

## 🧪 Tests

Tests are not runtime dependencies; install pytest separately:

```sh
pip install pytest
python -m pytest tests/ -v
```

Covered: register/login/logout, groups & bookmarks CRUD, favorites, the secret
group (password, lock/unlock, link visibility in common feeds), settings,
JSON & Netscape-HTML export.

## 📁 Project structure

```
app.py                  entry point (arguments, run)
build_min.py            minified-JS build (esbuild)
sync_parts.py           regenerates core*.part.js / dialogs.part.js from app.js
requirements.txt        Flask (the only runtime dependency)
install.sh              Ubuntu Server: background process or systemd service
run.sh / run.bat        local run with automatic venv creation
Dockerfile              image: python:3.12-slim, non-root, healthcheck
docker-compose.yml      run: port 8765, data volume, TZ
.dockerignore           what is not copied into the image (incl. ./data)
DOCKER.md               detailed guide: deploying Docker on a PC
bookmarks/
  __init__.py           app factory, CSP & security headers
  api.py                groups (incl. “Secret”), bookmarks, tags, settings, import/export
  auth.py               registration, login, sessions, rate-limit
  db.py                 SQLite schema & init (incl. secret-group migration)
  settings.py           default settings, accents, normalization
  util.py               helpers (time, hashing, metadata/favicon fetching)
  static/               UI: HTML, CSS, JS (sources + built min files)
tests/                  pytest: auth, CRUD, secret group, import/export
data/                   data (created at runtime; not committed — see .gitignore)
```

## 📄 License

Free to use: run it on your machine, fork it, improve it and share it back.

---
---

<h1 id="-русский" align="center">🔖 Bookmarks <small>(русский)</small></h1>

<p align="center">
  Self-hosted менеджер закладок: один Python-процесс, один файл SQLite,
  ноль внешних сервисов.<br>
  Красивое место для ссылок, которые вам дороги.
</p>

## ✨ Возможности

- **Мультипользовательский** — регистрация и вход; у каждого аккаунта своё приватное пространство
- **Группы и «Избранное»** — свои группы, встроенное «Избранное», перестановка групп
- **🔐 Секретная группа** — особая группа (сразу после «Избранного»): ссылки в ней скрыты из «Дома», поиска и тегов, пока не введён сессионный пароль; 🔐/🔓 — и индикатор, и переключатель
- **Теги, поиск и сортировка** — полнотекстовый поиск по названию, URL, описанию и тегам; сортировка по дате/названию/визитам
- **Импорт и экспорт** — JSON и Netscape HTML (стандартный формат экспорта браузеров)
- **Автоподтяжка метаданных** — заголовки, описания и фавиконки страниц подтягиваются автоматически (с кэшем и повтором неудачных загрузок)
- **Персонализация** — русский/английский интерфейс, светлые и тёмные темы, акцентные цвета, 5 быстрых ссылок внизу сайдбара (свои значки, перестановка местами), мини-календарь у часов
- **Безопасность** — scrypt-хеши паролей, сессионные cookie (HttpOnly, SameSite), CSP и security-заголовки, rate-limit на вход, не-root пользователь в контейнере

## 🚀 Быстрый старт

Нужно: **Python 3.10+** (или Docker).

```sh
git clone https://github.com/evgeniy7f2/bookmarks.git
cd bookmarks
python3 app.py
```

Откройте <http://127.0.0.1:8765>, зарегистрируйте пользователя — всё.

---

## 🐧 Linux (Ubuntu / Debian)

1. Поставьте Python, если его нет:

   ```sh
   sudo apt update && sudo apt install -y python3 python3-venv
   ```

2. Получите проект (клон, либо скопируйте папку на машину).

**Вариант А — быстрый запуск** (venv создастся сам):

```sh
cd bookmarks
./run.sh
```

**Вариант Б — `install.sh`** (фоновый процесс или systemd-сервис с автозапуском):

```sh
bash install.sh            # venv + запуск в фоне (nohup), лог в data/server.log
bash install.sh systemd    # venv + systemd-сервис (переживает перезагрузку)
```

Полезные переменные окружения для `install.sh`: `PORT` (по умолчанию `8765`),
`HOST_BIND` (по умолчанию `0.0.0.0`), `BOOKMARKS_DATA` (по умолчанию `<корень>/data`).

**Проверка:**

```sh
curl http://127.0.0.1:8765/health
# {"app":"Bookmarks","version":"1.0.9","ok":true}
```

---

## 🪟 Windows

1. Поставьте [Python 3.10+](https://www.python.org/downloads/) — при установке
   отметьте **“Add python.exe to PATH”**.

2. Получите папку проекта (клон, либо скопируйте на ПК, например в `C:\bookmarks`).

**Вариант А — в один клик:** двойной клик по **`run.bat`**.
Скрипт создаст виртуальное окружение, установит единственную зависимость (Flask)
и запустит сервер с открытым браузером.

**Вариант Б — вручную:**

```powershell
cd C:\bookmarks
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python app.py --open
```

**Проверка:** откройте <http://127.0.0.1:8765> в браузере, или в PowerShell:

```powershell
(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/health).Content
# {"app":"Bookmarks","version":"1.0.9","ok":true}
```

> Если порт занят: `netstat -ano | findstr 8765` — найти PID и остановить процесс,
> либо запустить на другом порту: `python app.py --port 8080`.

---

## 🐳 Docker

```sh
cd bookmarks
docker compose up -d --build
```

Или без compose (равносильно):

```sh
docker build -t bookmarks .
docker run -d --name bookmarks -p 8765:8765 -v bookmarks_data:/data bookmarks
```

- Базовый образ: `python:3.12-slim`; приложение работает от **не-root** пользователя (uid 10001)
- Данные — в именованном томе `/data`: переживают пересборку и удаление контейнера
- Healthcheck (`GET /health`) встроен в образ
- Часовой пояс логов: `TZ` в `docker-compose.yml` (по умолчанию `Etc/MSK`);
  интерфейс всегда показывает время вашего браузера

**Обновление** после изменений кода: `docker compose up -d --build` (данные остаются).
**Остановка:** `docker compose down` (данные остаются) · `down -v` (удаляет том с данными — осторожно!).

📖 Подробная пошаговая инструкция — установка Docker Desktop на Windows (WSL2),
перенос существующих данных, типовые проблемы — в файле **[DOCKER.md](DOCKER.md)**.

---

## ⚙️ Настройки

### Флаги `app.py`

| Флаг | По умолчанию | Описание |
| --- | --- | --- |
| `--host` | `0.0.0.0` | адрес привязки |
| `--port` | `8765` | порт |
| `--data` | `./data` | каталог данных (то же, что `BOOKMARKS_DATA`) |
| `--debug` | выкл. | debug-режим Flask |
| `--open` | выкл. | открыть браузер при старте |
| `--version` | | показать версию |

### Переменные окружения

| Переменная | Описание |
| --- | --- |
| `BOOKMARKS_DATA` | каталог данных (БД, кэш фавиконов, `secret.key`) |
| `BOOKMARKS_SECRET` | секрет подписи cookie (иначе создаётся `secret.key` в каталоге данных) |
| `BOOKMARKS_COOKIE_SECURE` | `1/true/yes` — сессионная cookie только по HTTPS (за reverse-proxy) |
| `BOOKMARKS_BLOCK_PRIVATE` | `1/true/yes` — не ходить за фавиконками/мета по приватным IP |

## 📦 Данные

Всё хранится в каталоге данных (по умолчанию `./data`, создаётся автоматически):

- `bookmarks.db` — SQLite: пользователи, сессии, группы, закладки, теги
- `icons/` — кэш фавиконов и статусы неудачных загрузок
- `secret.key` — сгенерированный секрет cookie

Перенос данных на другую машину: экспорт JSON из UI («Настройки» → «Экспорт»)
и импорт в новой копии — либо копирование `bookmarks.db` + `secret.key` в
каталог данных (для Docker — `docker cp`).

## 🌐 API (кратко)

Все эндпоинты под `/api`, требуют сессию (кроме register/login).
Ответы — JSON, ошибки вида `{"error": "код"}`.

| Метод и путь | Назначение |
| --- | --- |
| `POST /api/auth/register` · `POST /api/auth/login` · `POST /api/auth/logout` | аутентификация |
| `GET /api/auth/me` | текущий пользователь |
| `GET/POST /api/groups` · `PATCH/DELETE /api/groups/<id>` | группы (у секретной `PATCH` — только `{password}`) |
| `POST /api/groups/<id>/unlock` · `POST /api/groups/<id>/lock` | открыть/закрыть «Секретные» |
| `GET/POST /api/bookmarks` · `PATCH/DELETE /api/bookmarks/<id>` | закладки |
| `POST /api/bookmarks/<id>/favorite` · `.../restore` · `DELETE .../purge` | избранное, корзина |
| `POST /api/trash/empty` · `POST /api/trash/restore-all` | корзина целиком |
| `GET /api/tags` · `GET/PUT /api/settings` · `GET /api/stats` | теги, настройки, статистика |
| `GET /api/export?format=json\|html` · `POST /api/import` | экспорт/импорт |
| `GET /api/metadata?url=` · `GET /api/icon?url=` | метаданные / фавикон |

`GET /health` — проверка живости.

## 🧪 Тесты

Тесты не входят в runtime-зависимости; поставьте pytest отдельно:

```sh
pip install pytest
python -m pytest tests/ -v
```

Покрыты: регистрация/вход/выход, CRUD групп и закладок, избранное,
секретная группа (пароль, блокировка/разблокировка, видимость ссылок),
настройки, экспорт JSON и Netscape HTML.

## 📁 Структура проекта

```
app.py                  точка входа (аргументы, запуск)
build_min.py            сборка min-файлов (esbuild)
sync_parts.py           регенерация core*.part.js / dialogs.part.js из app.js
requirements.txt        Flask (единственная runtime-зависимость)
install.sh              Ubuntu Server: фоновый процесс или systemd-сервис
run.sh / run.bat        локальный запуск с авто-созданием venv
Dockerfile              образ python:3.12-slim, не-root, healthcheck
docker-compose.yml      запуск: порт 8765, том с данными, TZ
.dockerignore           что не попадать в образ (включая ./data)
DOCKER.md               подробная инструкция: развёртывание в Docker на ПК
bookmarks/
  __init__.py           фаблик приложения, CSP и security-заголовки
  api.py                группы (вкл. «Секретные»), закладки, теги, настройки, импорт/экспорт
  auth.py               регистрация, вход, сессии, rate-limit
  db.py                 схема SQLite и init (вкл. миграцию секретной группы)
  settings.py           настройки по умолчанию, акценты, нормализация
  util.py               хелперы (время, хеши, fetch метаданных/фавик)
  static/               UI: HTML, CSS, JS (исходники + собранные min-файлы)
tests/                  pytest: аутентификация, CRUD, секретная группа, импорт/экспорт
data/                   данные (создаются при работе; не коммитятся — см. .gitignore)
```

## 📄 Лицензия

Свободна к использованию: запускайте у себя, форкайте, улучшайте и делитесь.
