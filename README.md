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
  <img src="https://img.shields.io/badge/version-1.4.0-2ea44f" alt="Version 1.4.0">
  <img src="https://img.shields.io/badge/storage-SQLite-003b57" alt="SQLite storage">
  <img src="https://img.shields.io/badge/interface-EN%20%2F%20RU-555555" alt="EN / RU interface">
</p>

---
<img width="800" height="477" alt="chrome_x2KvElyYkJ" src="https://github.com/user-attachments/assets/b314ff93-69b8-4f3f-b5d7-435238800916" />

## ✨ Features

- **Multi-user** — registration and login; each account has its own private space
- **Groups & “Favorites”** — custom groups, built-in “Favorites” group, drag-free reordering via a menu
- **🔐 Secret group** — a special group (right after “Favorites”) whose links are hidden from “Home”, search, tags, stats and exports until you enter a session password; by-id requests answer “not found” while it is closed; 🔐/🔓 is both an indicator and a toggle; the password (8+ chars) can only be changed while the group is open, and unlock attempts are rate-limited
- **Tags, search & sorting** — full-text search over titles, URLs, descriptions and tags; sort by date, name or visit count
- **Pagination** — feeds load 100 links at a time with a “Show more” button (`limit`/`offset` in the API)
- **Full backup & restore** — a single JSON file carries groups, links, custom icons, pinned state, settings (including quick links), avatar and the Secret-group password; importing it into a fresh account restores the whole interface, not just the list. Plus Netscape HTML export (the standard browser format)
- **Automatic metadata** — page titles, descriptions and favicons are fetched automatically (with cache and retry for failed loads)
- **Personalization** — Russian/English UI, light & dark themes, accent colors, 5 custom quick-links at the bottom of the sidebar (with own icons and reordering), mini-calendar next to the clock
- **Quotas & admin panel** — per-user limits on bookmarks/tags/groups (blank = server default 5000/100/80); exceeding one shows a clear error with the active limit. The admin panel (🛡️ sidebar item, admins only) gives summary stats (users, links, groups, tags, DB size, uptime) and a user list where you can grant/revoke the admin role, block/unblock, reset a password and set any user's limits. The first registered account becomes the admin automatically (existing databases get it via the startup migration). The profile screen shows a “My limits” block (current usage / limit)
- **Security** — scrypt password hashing, session cookies (HttpOnly, SameSite), CSP and security headers, login rate-limiting, non-root container user
- **Installer & auto-updates** — a single-file Windows installer (`bookmarks_install_v140.exe`, all app files embedded: download, run, done) and a standalone graphical installer (`python installer/installer.py`, RU/EN, tkinter): Windows (finds/installs Python, dependencies, auto-start, Start-menu shortcut), a Linux server over SSH (venv + systemd), Docker over SSH (installs Docker, builds the image, starts the container), manual install (archive with all files + a detailed guide), and updates. For Linux/Docker you only need the IP, port and SSH credentials — every dependency is downloaded automatically. Auto-update: `update.py` fetches the latest GitHub release (or the `main` branch) and upgrades in place, preserving the data dir and the venv; the admin also gets an “Updates” section in the About dialog

## 🚀 Quick start

Requirements: **Python 3.10+** (or Docker).

```sh
git clone https://github.com/<your-user>/bookmarks.git
cd bookmarks
python3 app.py
```

Open <http://127.0.0.1:8765>, register a user — and you are done.

## 📦 Installer (recommended)

**Windows — a single file:** download `bookmarks_install_v140.exe` from
the release assets and run it. The whole application is packed inside; the
bootstrapper fetches the latest files from GitHub (falling back to the
embedded copy when GitHub is unreachable) and walks you through the same
screens as the script below.

**Or from source** — a self-contained graphical installer (tkinter, RU/EN),
no manual steps:

```sh
python installer/installer.py
```

Flow: language → install method (Windows / Linux systemd / Docker /
manual install / update) → address and port → (Linux/Docker) SSH login
and password → install. It downloads everything on its own: Python
(Windows), pip packages, even Docker (Linux). For Linux/Docker you need
SSH access (root, or a user with `sudo`). The **Manual** method builds an
archive with every file plus a step-by-step guide, and **Update**
upgrades an existing install — locally or on a remote Linux/Docker box.

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
# {"app":"Bookmarks","version":"1.4.0","schema":"6","db":true,"ok":true}
```

---

## 🪟 Windows

1. Install [Python 3.10+](https://www.python.org/downloads/) — during setup
   check **“Add python.exe to PATH”**.

2. Get the project folder (clone, or copy it to the PC, e.g. `C:\bookmarks`).

**Option A — one click:** double-click **`run.bat`**.
It creates a virtual environment, installs the dependencies (Flask + waitress) and
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
# {"app":"Bookmarks","version":"1.4.0","schema":"6","db":true,"ok":true}
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
| `BOOKMARKS_TRUST_PROXY` | `1/true/yes` — trust one hop of `X-Forwarded-For/Proto` (behind nginx/Caddy) |
| `BOOKMARKS_ALLOW_PRIVATE` | `1/true/yes` — allow favicon/metadata fetches from private IPs (blocked by default) |
| `BOOKMARKS_BLOCK_PRIVATE` | legacy: `0/false/no` behaves like `BOOKMARKS_ALLOW_PRIVATE=1` |
| `BOOKMARKS_REGISTRATION` | `closed/false/0/no/off` — disable new registrations |

Private and link-local addresses are blocked for metadata/favicon fetches
(SSRF protection), including every redirect. Opt in with `BOOKMARKS_ALLOW_PRIVATE=1`
for home-lab/intranet targets.

## 📦 Data

Everything is stored in the data directory (default `./data`, created automatically):

- `bookmarks.db` — SQLite: users, sessions, groups, bookmarks, tags
- `icons/` — favicon cache and statuses of failed loads (temporary; the oldest
  entries are pruned automatically when the cache outgrows 2000)
- `secret.key` — generated cookie secret

### The secret group: access control, not encryption

The secret group hides links from other eyes in the UI: while it is locked its
links do not appear in shared feeds, search, tags, stats or export, and they do
not leak through the duplicate check. But it is **access control, not
encryption** — the database file, backups and exports store the links in
clear. If that matters, encrypt the data directory at the filesystem level.

## 🔧 Administration & backups

`manage.py` works against the data dir (`--data <dir>`, or `BOOKMARKS_DATA`,
default `./data`) and is safe while the server is running:

```sh
python manage.py list-users                        # every account + usage stats
python manage.py make-admin <user>                 # grant the admin role (CLI)
python manage.py reset-password <user> [new]       # set a password (generates one if omitted)
python manage.py lock-user <user>                  # block: instant logout + login refused
python manage.py unlock-user <user>                # unblock
python manage.py backup /backups/b.sqlite3         # consistent copy of the database
```

The copy is made with the SQLite online-backup API, so it is consistent even
while the server writes (unlike a plain file copy).

`backup.sh` (Linux/Docker) does the backup and rotates the copies:

```sh
./backup.sh                       # keeps 7 copies in <data>/backups/ (set KEEP to change)
0 3 * * * /path/to/bookmarks/backup.sh   # daily at 03:00 via cron
```

## 🌐 API (short)

All endpoints are under `/api` and require a session (except register/login).
Responses are JSON; errors look like `{"error": "code"}`.

| Method & path | Purpose |
| --- | --- |
| `POST /api/auth/register` · `POST /api/auth/login` · `POST /api/auth/logout` | auth |
| `GET /api/auth/me` | current user |
| `GET/POST /api/groups` · `PATCH/DELETE /api/groups/<id>` | groups (secret group: `PATCH` only `{password}`) |
| `POST /api/groups/<id>/unlock` · `POST /api/groups/<id>/lock` | open/close the secret group |
| `GET/POST /api/bookmarks` · `PATCH/DELETE /api/bookmarks/<id>` | bookmarks (list: `limit` ≤ 500, `offset`) |
| `POST /api/bookmarks/<id>/favorite` · `.../restore` · `DELETE .../purge` | favorite, trash |
| `POST /api/trash/empty` · `POST /api/trash/restore-all` | trash in bulk |
| `GET /api/tags` · `GET/PUT /api/settings` · `GET /api/stats` | tags, settings, stats |
| `GET /api/export?format=json\|html` · `POST /api/import` | full backup (JSON) / Netscape-HTML export · import with profile & settings restore |
| `GET /api/metadata?url=` · `GET /api/icon?url=` | metadata / favicon |
| `GET /api/admin/summary` | admin panel: summary stats (users, links, groups, tags, DB size, uptime) |
| `GET /api/admin/users` | admin panel: user list (role, limits, counters) |
| `PATCH /api/admin/users/<id>` | admin panel: role / block / limits (`max_*` = `null` resets to the server default) |
| `POST /api/admin/users/<id>/password` | admin panel: reset a user's password |
| `GET /api/update/check` | auto-update: latest version on GitHub (admin only; `403` otherwise, `502 github_unreachable` offline) |
| `POST /api/update/run` | auto-update: start `update.py` in the background (admin only; `409 already_running`, log in `data/update.log`) |

`GET /health` — liveness + database check (503 on a broken DB): `{"app": "Bookmarks", "version": "1.4.0", "schema": "6", "db": true, "ok": true}`.

`GET /api/bookmarks` returns a page: `{"bookmarks": [...], "total": N, "has_more": bool,
"limit": L, "offset": O}`. Default `limit` is 100, maximum 500.

## 🔄 Updating

Three ways — pick any:

1. **From the UI** (admin): About → Updates → *Check for updates* /
   *Update*. The server restarts itself and the page reloads.
2. **Command line** in the install directory:
   ```sh
   python update.py --check     # check only
   python update.py             # update (asks for confirmation)
   python update.py --yes       # no confirmation
   ```
3. **The installer**: `python installer/installer.py` → *Update the program*
   (locally, or on a Linux / Docker box over SSH).

The update downloads the latest release of `evgeniy7f2/Bookmarks`
(falls back to the `main` branch when the release has no archive),
replaces the program files **while keeping the data dir (`data/`) and
the virtualenv (`.venv/`)**, reinstalls dependencies, restarts the server
and waits for `health`. In Docker: copy the files into the project folder
on the host and run `docker compose up -d --build` (the installer does
this over SSH).

## 🧪 Tests

Tests are not runtime dependencies; install pytest separately:

```sh
pip install pytest
python -m pytest tests/ -v
```

Covered: register/login/logout (including closed registration), groups & bookmarks
CRUD, favorites, the secret group (password, lock/unlock, rate limit, visibility in
common feeds, by id, in tags, stats and exports), pagination, validated import,
settings, JSON & Netscape-HTML export, SSRF guard, quotas & admin panel,
RU/EN i18n parity, frontend static guards, auto-update (`/api/update/*`)
and the installer modules.

## 📁 Project structure

```
app.py                  entry point (arguments, waitress server)
update.py               auto-update from GitHub (CLI: --check/--yes/--force/--source)
installer_bootstrap.py  bootstrapper for the single-file exe (PyInstaller):
                        fetches files from GitHub, launches the GUI installer
                        (falls back to the copy embedded in the exe)
installer/              graphical installer (tkinter, RU/EN):
  installer.py            GUI: language → method → config → progress → done
  core.py                 GitHub API, IP/port validation, health check
  i18n.py                 all installer strings (RU/EN)
  win.py                  Windows: find/install Python, venv, auto-start, shortcut
  remote.py               Linux systemd / Docker over SSH (paramiko)
  actions.py              manual install, local & remote updates
  __init__.py
build_min.py            minified-JS build (esbuild)
requirements.txt        Flask + waitress (runtime dependencies)
install.sh              Ubuntu Server: background process or systemd service
run.sh / run.bat        local run with automatic venv creation
manage.py               admin CLI: list/make-admin/reset-password/lock/backup
backup.sh               backup + copy rotation (cron)
Dockerfile              image: python:3.12-slim, non-root, healthcheck
docker-compose.yml      run: port 8765, data volume, TZ
.dockerignore           what is not copied into the image (incl. ./data)
DOCKER.md               detailed guide: deploying Docker on a PC
bookmarks/
  __init__.py           app factory, CSP & security headers, /go, /health
  api.py                groups (incl. “Secret”), bookmarks, tags, settings,
                        import/export, auto-update (/api/update/*)
  admin.py              admin panel (/api/admin, admins only)
  auth.py               registration, login, sessions
  ratelimit.py          shared in-memory limiter (login + secret unlock)
  db.py                 SQLite schema & init (incl. migrations)
  settings.py           default settings, accents, normalization
  util.py               helpers (time, hashing, SSRF guard, metadata/favicon fetching)
  static/               UI: HTML, CSS, JS (sources + built min files)
tests/                  pytest: API, frontend guards, installer
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
- **🔐 Секретная группа** — особая группа (сразу после «Избранного»): ссылки в ней скрыты из «Дома», поиска, тегов, статистики и экспорта, пока не введён сессионный пароль; обращения по id отвечают «не найдено»; 🔐/🔓 — и индикатор, и переключатель; пароль (8+ символов) меняется только при открытой группе, попытки разблокировки ограничены
- **Теги, поиск и сортировка** — полнотекстовый поиск по названию, URL, описанию и тегам; сортировка по дате/названию/визитам
- **Постраничная выдача** — ленты грузятся по 100 ссылок, кнопка «Показать ещё» (`limit`/`offset` в API)
- **Импорт и экспорт** — JSON и Netscape HTML (стандартный формат экспорта браузеров)
- **Автоподтяжка метаданных** — заголовки, описания и фавиконки страниц подтягиваются автоматически (с кэшем и повтором неудачных загрузок)
- **Персонализация** — русский/английский интерфейс, светлые и тёмные темы, акцентные цвета, 5 быстрых ссылок внизу сайдбара (свои значки, перестановка местами), мини-календарь у часов
- **Квоты и админ-панель** — индивидуальные лимиты закладок/тегов/групп на пользователя (пусто = общее значение сервера 5000/100/80); при превышении — понятная ошибка с действующим лимитом. Панель администратора (пункт 🛡️ в сайдбаре, только для админов): сводная статистика (юзеры, закладки, группы, теги, размер БД, аптайм) и список пользователей — выдать/снять роль, заблокировать/разблокировать, сбросить пароль и настроить лимиты любого юзера. Первый зарегистрированный аккаунт автоматически становится администратором (для существующих баз — стартовая миграция). В профиле — блок «Мои лимиты» (текущее использование / лимит)
- **Безопасность** — scrypt-хеши паролей, сессионные cookie (HttpOnly, SameSite), CSP и security-заголовки, rate-limit на вход, не-root пользователь в контейнере
- **Установщик и автообновление** — одиночный Windows-установщик `bookmarks_install_v140.exe` (все файлы приложения внутри: скачали, запустили, готово) и самодостаточный графический установщик (`python installer/installer.py`, RU/EN, tkinter): Windows (сам найдёт/поставит Python, зависимости, автозапуск, ярлык в «Пуске»), Linux-сервер по SSH (venv + systemd), Docker по SSH (поставит Docker, соберёт образ, поднимет контейнер), ручная установка (архив со всеми файлами + подробная инструкция) и обновление. Для Linux/Docker нужны только IP, порт и SSH-учётные данные — все зависимости скачаются автоматически. Автообновление: `update.py` берёт последний релиз на GitHub (или ветку `main`), обновляет файлы на месте, сохраняя каталог данных и venv; администратору доступна секция «Обновления» в диалоге «О программе»

## 🚀 Быстрый старт

Нужно: **Python 3.10+** (или Docker).

```sh
git clone https://github.com/<ваш-пользователь>/bookmarks.git
cd bookmarks
python3 app.py
```

Откройте <http://127.0.0.1:8765>, зарегистрируйте пользователя — всё.

## 📦 Установщик (рекомендуется)

**Windows — одним файлом:** скачайте `bookmarks_install_v140.exe` из
ассетов релиза и запустите. Всё приложение упаковано внутри; бутстраппер
сам скачает последние файлы с GitHub (а при недоступности GitHub —
использует встроенную в exe копию) и проведёт установку по тем же экранам,
что и скрипт ниже.

**Или из исходников** — самодостаточный графический установщик (tkinter,
RU/EN) — без ручных шагов:

```sh
python installer/installer.py
```

Порядок: язык → способ установки (Windows / Linux systemd / Docker /
ручная установка / обновление) → адрес и порт → (для Linux/Docker)
SSH-логин и пароль → установка. Всё скачивается само: Python
(Windows), pip-пакеты, даже Docker (Linux). Для Linux/Docker нужен
SSH-доступ (root или юзер с `sudo`). Способ **«Ручная установка»**
собирает архив со всеми файлами и пошаговую инструкцию, а
**«Обновление программы»** обновляет уже установленную копию —
локально или на удалённом Linux/Docker по SSH.

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
# {"app":"Bookmarks","version":"1.4.0","schema":"6","db":true,"ok":true}
```

---

## 🪟 Windows

1. Поставьте [Python 3.10+](https://www.python.org/downloads/) — при установке
   отметьте **“Add python.exe to PATH”**.

2. Получите папку проекта (клон, либо скопируйте на ПК, например в `C:\bookmarks`).

**Вариант А — в один клик:** двойной клик по **`run.bat`**.
Скрипт создаст виртуальное окружение, установит зависимости (Flask + waitress)
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
# {"app":"Bookmarks","version":"1.4.0","schema":"6","db":true,"ok":true}
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
| `BOOKMARKS_TRUST_PROXY` | `1/true/yes` — доверять одному хопу `X-Forwarded-For/Proto` (за nginx/Caddy) |
| `BOOKMARKS_ALLOW_PRIVATE` | `1/true/yes` — разрешить загрузку фавиконок/мета с приватных IP (по умолчанию запрещено) |
| `BOOKMARKS_BLOCK_PRIVATE` | устаревшая: `0/false/no` работает как `BOOKMARKS_ALLOW_PRIVATE=1` |
| `BOOKMARKS_REGISTRATION` | `closed/false/0/no/off` — закрыть регистрацию новых пользователей |

Приватные и link-local адреса блокируются при загрузке метаданных/фавиконок
(защита от SSRF), включая каждый редирект. Для домашней сети включите
`BOOKMARKS_ALLOW_PRIVATE=1`.

## 📦 Данные

Всё хранится в каталоге данных (по умолчанию `./data`, создаётся автоматически):

- `bookmarks.db` — SQLite: пользователи, сессии, группы, закладки, теги
- `icons/` — кэш фавиконов и статусы неудачных загрузок (временные; при
  переполнении самые старые записи вычищаются автоматически)
- `secret.key` — сгенерированный секрет cookie

### Группа «Секретные»: контроль доступа, а не шифрование

Группа «Секретные» скрывает ссылки от чужих глаз в интерфейсе: закрытые
ссылки не видны в общих фидах, поиске, тегах, статистике, экспорте и не
раскрываются через проверку дублей. Но это **контроль доступа, а не
шифрование**: содержимое БД (`bookmarks.db`), файлы бэкапов и экспорт
хранят ссылки в открытом виде. Если для вас критично — шифруйте том с
каталогом данных на уровне файловой системы.

## 🔧 Администрирование и бэкапы

`manage.py` работает с каталогом данных (`--data <dir>`, или `BOOKMARKS_DATA`,
по умолчанию `./data`) и безопасен при работающем сервере:

```sh
python manage.py list-users                        # все аккаунты и статистика
python manage.py make-admin <user>                 # выдать роль администратора (CLI)
python manage.py reset-password <user> [новый]     # сброс пароля (сгенерирует случайный)
python manage.py lock-user <user>                  # блокировка: мгновенный logout + отказ во входе
python manage.py unlock-user <user>                # разблокировка
python manage.py backup /backups/b.sqlite3         # копия БД (online backup, SQLite)
```

Копия делается через `sqlite3`'s online backup API — она консистентна даже
пока сервер пишет (в отличие от простого копирования файла).

Готовый скрипт `backup.sh` (Linux/Docker) делает бэкап и ротирует копии:

```sh
./backup.sh                       # копию кладёт в <data>/backups/, держит 7 (KEEP)
0 3 * * * /path/to/bookmarks/backup.sh   # каждый день в 03:00 через cron
```

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
| `GET/POST /api/bookmarks` · `PATCH/DELETE /api/bookmarks/<id>` | закладки (список: `limit` ≤ 500, `offset`) |
| `POST /api/bookmarks/<id>/favorite` · `.../restore` · `DELETE .../purge` | избранное, корзина |
| `POST /api/trash/empty` · `POST /api/trash/restore-all` | корзина целиком |
| `GET /api/tags` · `GET/PUT /api/settings` · `GET /api/stats` | теги, настройки, статистика |
| `GET /api/export?format=json\|html` · `POST /api/import` | полный бэкап (JSON) / экспорт в Netscape-HTML · импорт с восстановлением профиля и настроек |
| `GET /api/metadata?url=` · `GET /api/icon?url=` | метаданные / фавикон |
| `GET /api/admin/summary` | админ-панель: сводная статистика (юзеры, закладки, группы, теги, размер БД, аптайм) |
| `GET /api/admin/users` | админ-панель: список пользователей (роли, лимиты, счётчики) |
| `PATCH /api/admin/users/<id>` | админ-панель: роль/блокировка/лимиты (`max_*` = `null` сбрасывает к общему) |
| `POST /api/admin/users/<id>/password` | админ-панель: сброс пароля пользователя |
| `GET /api/update/check` | автообновление: последняя версия на GitHub (только админ; иначе `403`, без интернета `502 github_unreachable`) |
| `POST /api/update/run` | автообновление: запустить `update.py` в фоне (только админ; `409 already_running`, лог в `data/update.log`) |

`GET /health` — проверка живости и доступности БД (503 при битой базе): `{"app": "Bookmarks", "version": "1.4.0", "schema": "6", "db": true, "ok": true}`.

`GET /api/bookmarks` возвращает страницу: `{"bookmarks": [...], "total": N, "has_more": bool,
"limit": L, "offset": O}`. `limit` по умолчанию 100, максимум 500.

## 🔄 Обновление

Три способа — любой:

1. **Из интерфейса** (администратор): «О программе» → «Обновления» →
   «Проверить обновления» / «Обновить». Сервер перезапустится сам,
   страница перезагрузится.
2. **Командой** в каталоге установки:
   ```sh
   python update.py --check     # только проверить
   python update.py             # обновить (спросит подтверждение)
   python update.py --yes       # без подтверждения
   ```
3. **Установщиком**: `python installer/installer.py` → «Обновление
   программы» (локально / Linux по SSH / Docker по SSH).

Обновление скачивает последний релиз `evgeniy7f2/Bookmarks` (если релиз
без архива — ветку `main`), заменяет файлы программы, **сохраняя
каталог данных (`data/`) и окружение (`.venv/`)**, ставит зависимости,
перезапускает сервер и дожидается `health`. В Docker: загрузите файлы
в каталог проекта на хосте и `docker compose up -d --build` (установщик
делает это по SSH).

## 🧪 Тесты

Тесты не входят в runtime-зависимости; поставьте pytest отдельно:

```sh
pip install pytest
python -m pytest tests/ -v
```

Покрыты: регистрация/вход/выход (включая закрытую регистрацию), CRUD групп и
закладок, избранное, секретная группа (пароль, блокировка/разблокировка,
rate-limit, видимость в общих фидах, по id, в тегах, статистике и экспорте),
пагинация, импорт с валидацией, настройки, экспорт JSON и Netscape HTML,
SSRF-гард, квоты и админ-панель, паритет переводов RU/EN, статические
гварды фронтенда, автообновление (`/api/update/*`) и модули установщика.

## 📁 Структура проекта

```
app.py                  точка входа (аргументы, запуск через waitress)
update.py               автообновление по GitHub (CLI: --check/--yes/--force/--source)
installer_bootstrap.py  бутстраппер одиночного exe (PyInstaller): загрузка
                        файлов с GitHub → запуск GUI-установщика (fallback —
                        встроенная в exe копия)
installer/              графический установщик (tkinter, RU/EN):
  installer.py            GUI: язык → способ → конфиг → прогресс → готово
  core.py                 GitHub-API, валидация IP/порта, health-чек
  i18n.py                 все строки установщика (RU/EN)
  win.py                  Windows: поиск/установка Python, venv, автозапуск, ярлык
  remote.py               Linux systemd / Docker по SSH (paramiko)
  actions.py              ручная установка, локальные/удалённые обновления
  __init__.py
build_min.py            сборка min-файлов (esbuild)
requirements.txt        Flask + waitress (runtime-зависимости)
install.sh              Ubuntu Server: фоновый процесс или systemd-сервис
run.sh / run.bat        локальный запуск с авто-созданием venv
manage.py               администрирование: list/make-admin/reset-password/lock/backup
backup.sh               бэкап + ротация копий (cron)
Dockerfile              образ python:3.12-slim, не-root, healthcheck
docker-compose.yml      запуск: порт 8765, том с данными, TZ
.dockerignore           что не попадать в образ (включая ./data)
DOCKER.md               подробная инструкция: развёртывание в Docker на ПК
bookmarks/
  __init__.py           фабрика приложения, CSP и security-заголовки, /go, /health
  api.py                группы (вкл. «Секретные»), закладки, теги, настройки,
                        импорт/экспорт, автообновление (/api/update/*)
  admin.py              админ-панель (/api/admin, только админ)
  auth.py               регистрация, вход, сессии
  ratelimit.py          общий in-memory лимитер (вход и разблокировка «Секретных»)
  db.py                 схема SQLite и init (вкл. миграции)
  settings.py           настройки по умолчанию, акценты, нормализация
  util.py               хелперы (время, хеши, SSRF-гард, метаданные/фавиконки)
  static/               UI: HTML, CSS, JS (исходники + собранные min-файлы)
tests/                  pytest: API, гварды фронтенда, установщик
data/                   данные (создаются при работе; не коммитятся — см. .gitignore)
```


## 💖 Поддержать разработку

Если вам нравится проект и вы хотите поддержать его развитие:

💳 **Карты РФ / СБП / Tinkoff Pay:**  
👉 [Поддержать через CloudTips](https://pay.cloudtips.ru/p/c57e8211)

<img width="1439" height="859" alt="chrome_R6ErHtuHdl" src="https://github.com/user-attachments/assets/22f5cadc-8b5c-470b-9ab8-d771a48207c1" />

## 📄 Лицензия

Свободна к использованию: запускайте у себя, форкайте, улучшайте и делитесь.
