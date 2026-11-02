# 🔖 Bookmarks 
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


## install.sh

**Один скрипт — установка, обслуживание и удаление сервиса Bookmarks**
на Ubuntu Server (systemd). Если рядом с `install.sh` нет файлов программы
(например, с GitHub скачан только сам скрипт), он **сам клонирует
репозиторий** и продолжает от полной папки.

**One script — install, maintain and remove the Bookmarks service** on
Ubuntu Server (systemd). If the program files are missing next to
`install.sh` (e.g. only the script itself was downloaded from GitHub), it
**clones the repository by itself** and continues from the full folder.

---

## 🇷🇺 Русский

### Быстрый старт

```bash
curl -fsSL https://raw.githubusercontent.com/evgeniy7f2/Bookmarks/main/install.sh | sudo bash
```

Откроется меню — выберите «1) установить / обновить» и ответьте на три
вопроса (Enter — значение по умолчанию):

| Вопрос | По умолчанию | Что означает |
|---|---|---|
| Каталог установки | `/opt/bookmarks` | где будут файлы программы и данные |
| Порт | `8765` | TCP-порт для HTTP |
| Доступ | `external` | `internal` — только с самого сервера (127.0.0.1); `external` — из сети (0.0.0.0) |

Скрипт поставит зависимости, скопирует файлы, создаст systemd-сервис
`bookmarks` (автозапуск при загрузке, автоперезапуск при сбое), проверит
запуск и напечатает адрес. **Первый зарегистрированный пользователь
автоматически становится администратором.**

Либо вручную:

```bash
git clone https://github.com/evgeniy7f2/Bookmarks.git
cd Bookmarks                 # или Bookmarks/ubuntu_sp
sudo bash install.sh
```

### Команды

| Команда | Что делает |
|---|---|
| `sudo bash install.sh` | меню (интерактивно) / установка (непинтерактивно) |
| `sudo bash install.sh install` | установка / повторная установка (обновление файлов) |
| `sudo bash install.sh port [N]` | смена порта (N — новый порт; без N — вопрос) |
| `sudo bash install.sh backup` | онлайн-бэкап базы в `data/backups/` (сервис не останавливается) |
| `sudo bash install.sh uninstall` | полное удаление: сервис, polkit, файлы, данные, пользователь |
| `sudo bash install.sh menu` | интерактивное меню |
| `sudo bash install.sh help` | справка |

### Непинтерактивный режим

```bash
INSTALL_DIR=/opt/bookmarks PORT=8765 BIND=external UI_LANG=ru sudo bash install.sh
```

| Переменная | Значение |
|---|---|
| `INSTALL_DIR` | каталог установки (по умолчанию `/opt/bookmarks`) |
| `PORT` | порт (по умолчанию `8765`) |
| `BIND` | `external` (0.0.0.0) или `internal` (127.0.0.1) |
| `UI_LANG` | `ru` или `en` (иначе — из локали системы) |
| `REPO_URL` | репозиторий для авто-клона (по умолчанию `evgeniy7f2/Bookmarks`) |

### Смена порта

`sudo bash install.sh port 9000` — скрипт обновляет `--port` в
`/etc/systemd/system/bookmarks.service` и `install.json` (именно на этом
порту автообновлятель проверяет сервер после обновления), перезапускает
сервис и проверяет `health`. При внешнем доступе напомнит про файрвол:
`sudo ufw allow 9000/tcp`.

### Бэкап базы данных

`sudo bash install.sh backup` — согласованная онлайн-копия базы
(сервис не останавливается) появляется в `<каталог>/data/backups/`
с именем `bookmarks-YYYYmmdd-HHMMSS.sqlite3`. Ротация: хранится
7 последних копий (`KEEP=14 /opt/bookmarks/backup.sh` — изменить число).
Восстановление: `sudo systemctl stop bookmarks` → заменить
`data/bookmarks.db` файлом из бэкапа → `sudo systemctl start bookmarks`.

### Полное удаление

`sudo bash install.sh uninstall`:

1. останавливает и убирает systemd-юнит `bookmarks`;
2. удаляет polkit-правило `/etc/polkit-1/rules.d/90-bookmarks.rules`;
3. спрашивает про каталог установки (по умолчанию — удаляет **вместе с
   `data/` и бэкапами**; в непинтерактивном режиме тоже удаляет);
4. удаляет системного пользователя `bookmarks`;
5. `systemctl daemon-reload`.

### Требования

Ubuntu Server 22.04/24.04; `git` и Python 3.10+ — установятся сами,
если отсутствуют.

---

## 🇬🇧 English

### Quick start

```bash
curl -fsSL https://raw.githubusercontent.com/evgeniy7f2/Bookmarks/main/install.sh | sudo bash
```

A menu opens — pick "1) install / update" and answer three questions
(Enter — accept the default):

| Question | Default | Meaning |
|---|---|---|
| Install directory | `/opt/bookmarks` | where the program files and data live |
| Port | `8765` | TCP port for HTTP |
| Access | `external` | `internal` — from the server itself only (127.0.0.1); `external` — from the network (0.0.0.0) |

The script installs the dependencies, copies the files, creates the
systemd service `bookmarks` (auto-start on boot, auto-restart on
failure), verifies the start and prints the address. **The first
registered user automatically becomes the administrator.**

Or by hand:

```bash
git clone https://github.com/evgeniy7f2/Bookmarks.git
cd Bookmarks                 # or Bookmarks/ubuntu_sp
sudo bash install.sh
```

### Commands

| Command | What it does |
|---|---|
| `sudo bash install.sh` | menu (interactive) / install (non-interactive) |
| `sudo bash install.sh install` | install / reinstall (file update) |
| `sudo bash install.sh port [N]` | change the port (N = the new port; without N — asks) |
| `sudo bash install.sh backup` | online database backup into `data/backups/` (the service keeps running) |
| `sudo bash install.sh uninstall` | full removal: service, polkit, files, data, user |
| `sudo bash install.sh menu` | interactive menu |
| `sudo bash install.sh help` | help |

### Non-interactive mode

```bash
INSTALL_DIR=/opt/bookmarks PORT=8765 BIND=external UI_LANG=ru sudo bash install.sh
```

| Variable | Value |
|---|---|
| `INSTALL_DIR` | install directory (default `/opt/bookmarks`) |
| `PORT` | port (default `8765`) |
| `BIND` | `external` (0.0.0.0) or `internal` (127.0.0.1) |
| `UI_LANG` | `ru` or `en` (otherwise taken from the system locale) |
| `REPO_URL` | repository for the self-clone (default `evgeniy7f2/Bookmarks`) |

### Changing the port

`sudo bash install.sh port 9000` — the script rewrites `--port` in
`/etc/systemd/system/bookmarks.service` and `install.json` (the auto-
updater checks the server on exactly this port after an update), restarts
the service and runs the `health` check. For external access it reminds
about the firewall: `sudo ufw allow 9000/tcp`.

### Database backup

`sudo bash install.sh backup` — a consistent online copy of the database
(the service keeps running) appears in `<dir>/data/backups/` named
`bookmarks-YYYYmmdd-HHMMSS.sqlite3`. Rotation: the 7 most recent copies
are kept (`KEEP=14 /opt/bookmarks/backup.sh` — change the count).
Restore: `sudo systemctl stop bookmarks` → replace `data/bookmarks.db`
with the backup file → `sudo systemctl start bookmarks`.

### Full uninstall

`sudo bash install.sh uninstall`:

1. stops and removes the systemd unit `bookmarks`;
2. removes the polkit rule `/etc/polkit-1/rules.d/90-bookmarks.rules`;
3. asks about the install directory (default — removes it **including
   `data/` and the backups**; non-interactive mode removes it as well);
4. removes the system user `bookmarks`;
5. `systemctl daemon-reload`.

### Requirements

Ubuntu Server 22.04/24.04; `git` and Python 3.10+ are installed
automatically if missing.
