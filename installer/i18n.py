# -*- coding: utf-8 -*-
"""Installer UI strings (RU / EN).

Every user-visible string of the installer lives here, so the interface is
fully localised without touching the logic.
"""
from __future__ import annotations

STRINGS = {
    "ru": {
        # --- common / window ---
        "app.title": "Установщик Bookmarks",
        "app.name": "Bookmarks 🔖",
        "app.subtitle": "Установщик · самодостаточный менеджер закладок",
        "btn.back": "← Назад",
        "btn.next": "Далее →",
        "btn.start": "Установить",
        "btn.cancel": "Отмена",
        "btn.close": "Закрыть",
        "btn.copy": "📋 Копировать в буфер",
        "btn.open_browser": "🌐 Открыть в браузере",
        "btn.save_instructions": "💾 Сохранить инструкцию (.txt)",
        "btn.update": "🔄 Обновить",
        "error.fix_and_retry": "Исправьте ошибки в форме и нажмите «Установить» ещё раз.",
        "error.title": "Что-то пошло не так",

        # --- language screen ---
        "lang.title": "Выберите язык",
        "lang.hint": "Язык можно переключить позже вверху окна.",
        "lang.ru": "Русский",
        "lang.en": "English",

        # --- method screen ---
        "method.title": "Как установить Bookmarks?",
        "method.hint": "Выберите способ. Все зависимости скачаются и установятся автоматически.",
        "method.win.title": "Windows — на этом компьютере",
        "method.win.desc": "Установка прямо на этот ПК: скачивание файлов, Python, зависимости, автозапуск. Самый простой вариант.",
        "method.linux.title": "Linux — системный процесс",
        "method.linux.desc": "Удалённая установка на Linux-сервер по SSH: программа станет системным сервисом (systemd) и будет запускаться при каждом включении.",
        "method.docker.title": "Docker",
        "method.docker.desc": "Удалённая установка в Docker-контейнер по SSH: изолированное окружение, данные хранятся в томе, легко переносить.",
        "method.manual.title": "Ручная установка",
        "method.manual.desc": "Скачать архив со всеми файлами программы и получить подробную инструкцию по установке своими руками.",
        "method.update.title": "Обновление программы",
        "method.update.desc": "Скачать последнюю версию с GitHub и обновить уже установленную программу (данные при этом сохраняются).",

        # --- config: common ---
        "cfg.win.title": "Установка на этот компьютер (Windows)",
        "cfg.win.dir.label": "Каталог установки",
        "cfg.win.dir.hint": "Сюда будут скопированы файлы программы.",
        "cfg.port.label": "Порт веб-интерфейса",
        "cfg.port.hint": "Страница будет доступна как http://IP-адрес:ПОРТ. Обычно оставляют 8765.",
        "cfg.network.label": "Доступ к странице",
        "cfg.network.this": "Только этот компьютер",
        "cfg.network.lan": "И другие устройства в сети",
        "cfg.win.python.label": "Python на этом компьютере",
        "cfg.win.python.auto": "Если Python не найден — скачать автоматически (рекомендуется)",
        "cfg.win.autostart": "Запускать Bookmarks при входе в Windows",
        "cfg.win.openbrowser": "Открыть страницу в браузере после установки",
        "cfg.win.shortcut": "Создать ярлык в меню «Пуск»",

        "cfg.remote.title": "Параметры удалённого сервера",
        "cfg.remote.server": "IP-адрес сервера",
        "cfg.remote.server.hint": "Адрес компьютера, на котором будет работать Bookmarks (например, 192.168.1.10).",
        "cfg.remote.port": "Порт веб-интерфейса",
        "cfg.remote.port.hint": "Страница будет доступна как http://АДРЕС:ПОРТ (например, http://192.168.1.10:8765).",
        "cfg.remote.sshport": "SSH-порт",
        "cfg.remote.sshport.hint": "Порт SSH-соединения. Обычно 22, менять не нужно.",
        "cfg.remote.user": "Имя пользователя SSH",
        "cfg.remote.user.hint": "Логин для подключения (например, root или имя вашего пользователя).",
        "cfg.remote.pass": "Пароль пользователя",
        "cfg.remote.pass.hint": "Пароль к указанному пользователю. Он нужен, чтобы копировать файлы и запускать команды.",
        "cfg.remote.show": "👁 Показать пароль",
        "cfg.remote.hide": "🙈 Скрыть пароль",
        "cfg.remote.linux.note": "Если программа ещё не установлена — установщик сам поставит Python и systemd-сервис. Если уже установлена (в том же каталоге) — файлы обновятся, данные останутся.",
        "cfg.remote.docker.note": "Если Docker ещё не установлен — установщик поставит его автоматически (нужны права root или sudo).",
        "cfg.remote.path": "Каталог на сервере",
        "cfg.remote.path.hint": "Куда положить файлы. Оставите пустым — выберем сам (/opt/bookmarks или домашняя папка).",

        # --- manual ---
        "manual.title": "Ручная установка",
        "manual.hint": "Скачаем архив со всеми файлами программы. После скачивания ниже появится подробная инструкция.",
        "manual.dest.label": "Куда скачать архив",
        "manual.dest.hint": "Каталог, в который положим bookmarks-latest.zip.",
        "manual.downloading": "Скачиваем архив с GitHub…",
        "manual.done": "Архив сохранён:",
        "manual.copy_hint": "Распакуйте архив и следуйте инструкции ниже. Все шаги описаны подробно.",

        # --- update screen ---
        "update.title": "Обновление программы",
        "update.hint": "Выберите, где установлена программа, которую нужно обновить.",
        "update.win": "На этом компьютере (Windows)",
        "update.win.desc": "Установщик найдёт каталог установки и обновит файлы через update.py.",
        "update.linux": "На Linux-сервере (SSH, systemd)",
        "update.linux.desc": "Подключимся по SSH и запустим обновление на сервере.",
        "update.docker": "В Docker (SSH)",
        "update.docker.desc": "Подключимся по SSH, пересоберём образ и поднимем контейнер.",
        "update.dir.label": "Каталог установки на этом компьютере",
        "update.dir.hint": "Папка, куда была установлена программа (там лежат app.py и каталог bookmarks).",
        "update.checking": "Проверяем версию на GitHub…",

        # --- progress screen ---
        "progress.title": "Установка…",
        "progress.wait": "Пожалуйста, не закрывайте окно. Все шаги видны ниже.",
        "progress.cancel": "Отменить",
        "progress.cancelled": "Отменено пользователем.",

        # --- done screen ---
        "done.title": "Установка завершена!",
        "done.url.label": "Откройте в браузере:",
        "done.hint.first": "При первом входе зарегистрируйте аккаунт — первый аккаунт автоматически становится администратором.",
        "done.hint.firewall": "Если страница не открывается с других устройств, разрешите порт в файрволе: sudo ufw allow {port} (Linux) или правила Windows Defender.",
        "done.hint.logs.linux": "Логи: journalctl -u bookmarks -f",
        "done.hint.logs.docker": "Логи: docker logs -f bookmarks",
        "done.hint.logs.win": "Лог: {path}",
        "done.hint.update": "Обновления: запустите установщик снова и выберите «Обновление программы» — либо кнопка «Обновить» в диалоге «О программе» (для администратора).",
        "done.manual.title": "Архив скачан!",

        # --- steps (progress log) ---
        "step.python": "Ищем Python на этом компьютере…",
        "step.python.ok": "Найден: {ver} ({path})",
        "step.python.missing": "Python не найден",
        "step.python.downloading": "Скачиваем Python (это займёт 1-3 минуты)…",
        "step.python.embedded": "Python установлен в каталог программы",
        "step.copy": "Копируем файлы программы…",
        "step.copy.ok": "Файлы скопированы ({n} шт.)",
        "step.copy.local": "Используем файлы из архива установщика (скачивание не нужно)",
        "step.copy.download": "Скачиваем последнюю версию с GitHub…",
        "step.venv": "Создаём виртуальное окружение и ставим зависимости (Flask, waitress)…",
        "step.venv.ok": "Зависимости установлены",
        "step.config": "Сохраняем настройки установки…",
        "step.start": "Запускаем сервер…",
        "step.health": "Проверяем, что сервер отвечает…",
        "step.health.ok": "Сервер работает: {ver} / schema {schema}",
        "step.autostart": "Включаем автозапуск при входе в Windows…",
        "step.autostart.ok": "Автозапуск включён",
        "step.shortcut": "Создаём ярлык в меню «Пуск»…",
        "step.shortcut.ok": "Ярлык создан",
        "step.open": "Открываем страницу в браузере…",

        "step.connect": "Подключаемся к серверу {ip} по SSH…",
        "step.connect.ok": "Соединение установлено (привет, {user}!)",
        "step.root": "Проверяем права (root/sudo)…",
        "step.root.ok": "Права готовы",
        "step.python.linux": "Проверяем Python на сервере…",
        "step.python.linux.install": "Ставим Python на сервере (это может занять пару минут)…",
        "step.python.linux.ok": "Python готов: {ver}",
        "step.copy.remote": "Копируем файлы программы на сервер ({dir})…",
        "step.copy.remote.ok": "Файлы на месте",
        "step.venv.remote": "Ставим зависимости на сервере…",
        "step.venv.remote.ok": "Зависимости установлены",
        "step.systemd": "Создаём системный сервис systemd (программа будет стартовать сама при включении)…",
        "step.systemd.ok": "Сервис bookmarks запущен",
        "step.nohup": "Запускаем сервер в фоне…",
        "step.docker.check": "Проверяем Docker на сервере…",
        "step.docker.install": "Устанавливаем Docker (это может занять несколько минут)…",
        "step.docker.install.ok": "Docker установлен и запущен",
        "step.docker.compose": "Проверяем docker compose…",
        "step.docker.build": "Собираем образ и запускаем контейнер (2-5 минут)…",
        "step.docker.up.ok": "Контейнер запущен",
        "step.health.remote": "Проверяем сервер по адресу http://{ip}:{port}/health…",
        "step.health.remote.ok": "Сервер отвечает: {ver}",

        "step.update.check": "Сверяем версию с GitHub…",
        "step.update.uptodate": "Уже установлена последняя версия {ver}. Обновление не требуется.",
        "step.update.run": "Запускаем обновление…",
        "step.update.done": "Обновление завершено!",
        "step.update.line": "  {line}",
        "step.paramiko": "Устанавливаем SSH-библиотеку paramiko (первый запуск, это быстро)…",

        # --- errors ---
        "err.ip": "Введите корректный IP-адрес или имя (например, 192.168.1.10).",
        "err.port": "Введите порт от 1 до 65535 (например, 8765).",
        "err.sshport": "Введите SSH-порт от 1 до 65535 (обычно 22).",
        "err.user": "Введите имя пользователя SSH.",
        "err.pass": "Введите пароль (или оставьте пустым, если вход по ключу).",
        "err.pass.required": "Введите пароль SSH.",
        "err.dir": "Укажите существующий каталог (или пустой, чтобы выбрать по умолчанию).",
        "err.download": "Не удалось скачать файлы с GitHub: {detail}. Проверьте интернет и повторите.",
        "err.no_python": "Python не найден, и автоматическое скачивание выключено.\n\nУстановите Python 3.10+ с python.org (в мастере установки поставьте галочку «Add Python to PATH»), затем повторите установку.",
        "err.ssh_failed": "Не удалось подключиться по SSH: {detail}\n\nПроверьте: адрес, порт, логин и пароль; включён ли SSH-сервер (sudo systemctl status ssh).",
        "err.ssh_auth": "SSH: неверный логин или пароль. Проверьте данные.",
        "err.health": "Сервер запустился, но не ответил на проверку за 90 секунд.\n\nПроверьте лог: {log}",
        "err.cancelled": "Операция отменена.",
        "err.update_dir": "Каталог установки не найден: нет app.py. Укажите папку, куда была установлена программа.",
        "err.generic": "Ошибка: {detail}",
        "err.paramiko": "Не удалось установить paramiko: {detail}\n\nПроверьте доступ в интернет и повторите.",
        "err.remote_cmd": "Команда завершилась с ошибкой: {cmd}\n\n{detail}",

        # --- manual instructions (detailed) ---
        "manual.instructions.win": """\
РУЧНАЯ УСТАНОВКА НА WINDOWS
===========================

1. Установите Python 3.10 или новее, если его ещё нет:
   https://python.org/downloads → скачайте установщик → при запуске
   ОБЯЗАТЕЛЬНО поставьте галочку «Add Python to PATH» → Install Now.

2. Распакуйте архив bookmarks-latest.zip в любой каталог,
   например C:\\Bookmarks. Внутри должны лежать app.py, каталог bookmarks\\
   и requirements.txt.

3. Откройте командную строку (Win+R → cmd) и выполните:
     cd /d C:\\Bookmarks
     python -m venv .venv
     .venv\\Scripts\\pip install -r requirements.txt

4. Запустите программу:
     .venv\\Scripts\\python app.py --host 0.0.0.0 --port 8765

5. Откройте в браузере:  http://127.0.0.1:8765
   С других устройств в сети: http://<IP-адрес-ПК>:8765

Полезное:
  • Остановка — Ctrl+C в окне запуска.
  • Автозапуск: добавьте команду из п.4 в «Диспетчер задач» →
    «Планировщик задач» → «Создать базовое задание», триггер — «При входе в систему».
  • Обновление: python update.py --yes (из каталога программы).
""",
        "manual.instructions.linux": """\
РУЧНАЯ УСТАНОВКА НА LINUX
=========================

1. Подключитесь к серверу по SSH:
     ssh <пользователь>@<адрес>
   (если это ваш первый SSH-вход — подтвердите отпечаток ключа, введите yes)

2. Убедитесь, что установлен Python 3.10+:
     python3 --version
   Если нет:
     sudo apt update && sudo apt install -y python3 python3-venv     (Ubuntu/Debian)
     sudo dnf install -y python3                                    (Fedora/RHEL)

3. Скачайте архив и распакуйте:
     cd /opt
     sudo mkdir -p bookmarks && sudo chown $USER bookmarks
   скопируйте содержимое bookmarks-latest.zip в /opt/bookmarks
   (должны оказаться /opt/bookmarks/app.py и /opt/bookmarks/bookmarks/)

4. Создайте виртуальное окружение и зависимости:
     cd /opt/bookmarks
     python3 -m venv .venv
     .venv/bin/pip install -r requirements.txt

5. Самый простой запуск (в фоне, лог в data/server.log):
     bash install.sh
   Или системный сервис (автозапуск при включении, рекомендуется):
     sudo bash install.sh systemd
   Проверка:  systemctl status bookmarks

6. Откройте в браузере:  http://<адрес-сервера>:8765
   Если со смартфона/другого ПК не открывается — разрешите порт в файрволе:
     sudo ufw allow 8765/comment 'bookmarks'

Полезное:
  • Логи: journalctl -u bookmarks -f
  • Остановка: sudo systemctl stop bookmarks
  • Управление пользователями: .venv/bin/python manage.py list-users
  • Обновление: .venv/bin/python update.py --yes
""",
        "manual.instructions.docker": """\
РУЧНАЯ УСТАНОВКА В DOCKER
=========================

1. Подключитесь к серверу по SSH:
     ssh <пользователь>@<адрес>

2. Установите Docker, если его ещё нет (официальный скрипт сам определит
   дистрибутив):
     curl -fsSL https://get.docker.com | sh
     sudo systemctl enable --now docker
   Если хотите запускать docker без sudo:
     sudo usermod -aG docker $USER   (затем выйдите и зайдите снова)

3. Разместите файлы проекта (из bookmarks-latest.zip) в каталог,
   например:
     sudo mkdir -p /opt/bookmarks && sudo cp -r <содержимое архива> /opt/bookmarks

4. Подготовьте compose-файл с нужным портом (заменив 8765 на свой):
     cd /opt/bookmarks
     # в docker-compose.yml строка ports: - "8765:8765"
     # измените левую часть на свой порт, например "9000:8765"

5. Соберите образ и запустите контейнер (данные сохранятся в томе
   bookmarks-data и переживут пересборку/удаление контейнера):
     docker compose up -d --build

6. Проверка:
     docker compose ps            # статус healthy
     curl http://127.0.0.1:8765/health
   Откройте в браузере:  http://<адрес-сервера>:8765

Полезное:
  • Логи: docker logs -f bookmarks
  • Остановка: docker compose stop
  • Обновление: docker compose up -d --build (после замены файлов)
""",
        "manual.instructions.all": "ВЫБЕРИТЕ ВАШ ВАРИАНТ В ИНСТРУКЦИИ НИЖЕ\n"
        "=======================================================\n\n",
    },
    "en": {
        # --- common / window ---
        "app.title": "Bookmarks Installer",
        "app.name": "Bookmarks 🔖",
        "app.subtitle": "Installer · self-hosted bookmark manager",
        "btn.back": "← Back",
        "btn.next": "Next →",
        "btn.start": "Install",
        "btn.cancel": "Cancel",
        "btn.close": "Close",
        "btn.copy": "📋 Copy to clipboard",
        "btn.open_browser": "🌐 Open in browser",
        "btn.save_instructions": "💾 Save instructions (.txt)",
        "btn.update": "🔄 Update",
        "error.fix_and_retry": "Fix the errors in the form and press “Install” again.",
        "error.title": "Something went wrong",

        # --- language screen ---
        "lang.title": "Choose a language",
        "lang.hint": "You can switch languages later at the top of the window.",
        "lang.ru": "Русский",
        "lang.en": "English",

        # --- method screen ---
        "method.title": "How would you like to install Bookmarks?",
        "method.hint": "Pick a method. All dependencies are downloaded and installed automatically.",
        "method.win.title": "Windows — on this computer",
        "method.win.desc": "Install right on this PC: downloads the files, Python and dependencies, sets up auto-start. The easiest option.",
        "method.linux.title": "Linux — system service",
        "method.linux.desc": "Remote install on a Linux server over SSH: the app becomes a systemd service and starts on every boot.",
        "method.docker.title": "Docker",
        "method.docker.desc": "Remote install into a Docker container over SSH: isolated environment, data stored in a volume, easy to move.",
        "method.manual.title": "Manual installation",
        "method.manual.desc": "Download the archive with all program files and get a detailed how-to guide.",
        "method.update.title": "Update the program",
        "method.update.desc": "Download the latest version from GitHub and update an existing installation (your data is kept).",

        # --- config: common ---
        "cfg.win.title": "Install on this computer (Windows)",
        "cfg.win.dir.label": "Install directory",
        "cfg.win.dir.hint": "Program files will be copied here.",
        "cfg.port.label": "Web interface port",
        "cfg.port.hint": "The page will be available at http://IP:PORT. Keep 8765 unless you need another.",
        "cfg.network.label": "Page access",
        "cfg.network.this": "This computer only",
        "cfg.network.lan": "Other devices on the network too",
        "cfg.win.python.label": "Python on this computer",
        "cfg.win.python.auto": "Download Python automatically if not found (recommended)",
        "cfg.win.autostart": "Start Bookmarks when I sign in to Windows",
        "cfg.win.openbrowser": "Open the page in a browser after install",
        "cfg.win.shortcut": "Create a Start menu shortcut",

        "cfg.remote.title": "Remote server settings",
        "cfg.remote.server": "Server IP address",
        "cfg.remote.server.hint": "Address of the machine that will run Bookmarks (e.g. 192.168.1.10).",
        "cfg.remote.port": "Web interface port",
        "cfg.remote.port.hint": "The page will be available at http://ADDRESS:PORT (e.g. http://192.168.1.10:8765).",
        "cfg.remote.sshport": "SSH port",
        "cfg.remote.sshport.hint": "SSH connection port. Usually 22 — leave it as is.",
        "cfg.remote.user": "SSH username",
        "cfg.remote.user.hint": "Login used to connect (e.g. root or your user name).",
        "cfg.remote.pass": "User password",
        "cfg.remote.pass.hint": "Password for that user. Needed to copy files and run commands.",
        "cfg.remote.show": "👁 Show password",
        "cfg.remote.hide": "🙈 Hide password",
        "cfg.remote.linux.note": "If the app is not installed yet, the installer sets up Python and the systemd service by itself. If it is already installed (same directory) — files are updated, data stays.",
        "cfg.remote.docker.note": "If Docker is not installed yet, the installer installs it automatically (root or sudo required).",
        "cfg.remote.path": "Directory on the server",
        "cfg.remote.path.hint": "Where to place the files. Leave empty to choose automatically (/opt/bookmarks or home folder).",

        # --- manual ---
        "manual.title": "Manual installation",
        "manual.hint": "We will download the archive with all program files. A detailed guide will appear below once it is ready.",
        "manual.dest.label": "Where to save the archive",
        "manual.dest.hint": "Folder for bookmarks-latest.zip.",
        "manual.downloading": "Downloading the archive from GitHub…",
        "manual.done": "Archive saved to:",
        "manual.copy_hint": "Unpack the archive and follow the guide below. Every step is explained in detail.",

        # --- update screen ---
        "update.title": "Update the program",
        "update.hint": "Choose where the program you want to update is installed.",
        "update.win": "On this computer (Windows)",
        "update.win.desc": "The installer will locate the install directory and update via update.py.",
        "update.linux": "On a Linux server (SSH, systemd)",
        "update.linux.desc": "We will connect over SSH and run the update on the server.",
        "update.docker": "In Docker (SSH)",
        "update.docker.desc": "We will connect over SSH, rebuild the image and start the container.",
        "update.dir.label": "Install directory on this computer",
        "update.dir.hint": "The folder the program was installed to (it contains app.py and the bookmarks folder).",
        "update.checking": "Checking the version on GitHub…",

        # --- progress screen ---
        "progress.title": "Installing…",
        "progress.wait": "Please do not close the window. All steps are shown below.",
        "progress.cancel": "Cancel",
        "progress.cancelled": "Cancelled by the user.",

        # --- done screen ---
        "done.title": "Installation complete!",
        "done.url.label": "Open in your browser:",
        "done.hint.first": "On first login, register an account — the first account automatically becomes the administrator.",
        "done.hint.firewall": "If the page does not open from other devices, allow the port in the firewall: sudo ufw allow {port} (Linux) or a Windows Defender rule.",
        "done.hint.logs.linux": "Logs: journalctl -u bookmarks -f",
        "done.hint.logs.docker": "Logs: docker logs -f bookmarks",
        "done.hint.logs.win": "Log: {path}",
        "done.hint.update": "Updates: run the installer again and pick “Update the program” — or use the “Update” button in the About dialog (admin only).",
        "done.manual.title": "Archive downloaded!",

        # --- steps (progress log) ---
        "step.python": "Looking for Python on this computer…",
        "step.python.ok": "Found: {ver} ({path})",
        "step.python.missing": "Python not found",
        "step.python.downloading": "Downloading Python (this takes 1–3 minutes)…",
        "step.python.embedded": "Python installed into the program folder",
        "step.copy": "Copying the program files…",
        "step.copy.ok": "Files copied ({n})",
        "step.copy.local": "Using files from the installer archive (no download needed)",
        "step.copy.download": "Downloading the latest version from GitHub…",
        "step.venv": "Creating a virtual environment and installing dependencies (Flask, waitress)…",
        "step.venv.ok": "Dependencies installed",
        "step.config": "Saving the install configuration…",
        "step.start": "Starting the server…",
        "step.health": "Checking that the server responds…",
        "step.health.ok": "Server is up: {ver} / schema {schema}",
        "step.autostart": "Enabling auto-start when signing in to Windows…",
        "step.autostart.ok": "Auto-start enabled",
        "step.shortcut": "Creating a Start menu shortcut…",
        "step.shortcut.ok": "Shortcut created",
        "step.open": "Opening the page in a browser…",

        "step.connect": "Connecting to {ip} over SSH…",
        "step.connect.ok": "Connected (hello, {user}!)",
        "step.root": "Checking privileges (root/sudo)…",
        "step.root.ok": "Privileges ready",
        "step.python.linux": "Checking Python on the server…",
        "step.python.linux.install": "Installing Python on the server (may take a couple of minutes)…",
        "step.python.linux.ok": "Python ready: {ver}",
        "step.copy.remote": "Copying the program files to the server ({dir})…",
        "step.copy.remote.ok": "Files in place",
        "step.venv.remote": "Installing dependencies on the server…",
        "step.venv.remote.ok": "Dependencies installed",
        "step.systemd": "Creating the systemd service (the app will start on every boot)…",
        "step.systemd.ok": "Service bookmarks is running",
        "step.nohup": "Starting the server in the background…",
        "step.docker.check": "Checking Docker on the server…",
        "step.docker.install": "Installing Docker (may take a few minutes)…",
        "step.docker.install.ok": "Docker installed and running",
        "step.docker.compose": "Checking docker compose…",
        "step.docker.build": "Building the image and starting the container (2–5 minutes)…",
        "step.docker.up.ok": "Container is up",
        "step.health.remote": "Checking the server at http://{ip}:{port}/health…",
        "step.health.remote.ok": "Server responds: {ver}",

        "step.update.check": "Comparing the version with GitHub…",
        "step.update.uptodate": "You already have the latest version {ver}. Nothing to do.",
        "step.update.run": "Running the update…",
        "step.update.done": "Update finished!",
        "step.update.line": "  {line}",
        "step.paramiko": "Installing the SSH library paramiko (first run, this is quick)…",

        # --- errors ---
        "err.ip": "Enter a valid IP address or name (e.g. 192.168.1.10).",
        "err.port": "Enter a port between 1 and 65535 (e.g. 8765).",
        "err.sshport": "Enter an SSH port between 1 and 65535 (usually 22).",
        "err.user": "Enter the SSH username.",
        "err.pass": "Enter the password (or leave empty for key-based login).",
        "err.pass.required": "Enter the SSH password.",
        "err.dir": "Point to an existing folder (or leave empty for the default).",
        "err.download": "Could not download the files from GitHub: {detail}. Check the internet connection and retry.",
        "err.no_python": "Python was not found and auto-download is off.\n\nInstall Python 3.10+ from python.org (tick “Add Python to PATH” in the installer), then retry.",
        "err.ssh_failed": "Could not connect over SSH: {detail}\n\nCheck: address, port, login and password; is the SSH server running (sudo systemctl status ssh).",
        "err.ssh_auth": "SSH: wrong login or password. Check your credentials.",
        "err.health": "The server started but did not answer the health check within 90 seconds.\n\nCheck the log: {log}",
        "err.cancelled": "Operation cancelled.",
        "err.update_dir": "Install directory not found: no app.py there. Point to the folder the program was installed to.",
        "err.generic": "Error: {detail}",
        "err.paramiko": "Could not install paramiko: {detail}\n\nCheck the internet connection and retry.",
        "err.remote_cmd": "A command failed: {cmd}\n\n{detail}",

        # --- manual instructions (detailed) ---
        "manual.instructions.win": """\
MANUAL INSTALL ON WINDOWS
=========================

1. Install Python 3.10 or newer if you do not have it yet:
   https://python.org/downloads → download the installer → tick
   “Add Python to PATH” in the setup wizard → Install Now.

2. Unpack bookmarks-latest.zip into any folder, e.g. C:\\Bookmarks.
   It must contain app.py, the bookmarks\\ folder and requirements.txt.

3. Open a command prompt (Win+R → cmd) and run:
     cd /d C:\\Bookmarks
     python -m venv .venv
     .venv\\Scripts\\pip install -r requirements.txt

4. Start the program:
     .venv\\Scripts\\python app.py --host 0.0.0.0 --port 8765

5. Open in your browser:  http://127.0.0.1:8765
   From other devices on the network: http://<PC-IP>:8765

Useful:
  • Stop — Ctrl+C in the launch window.
  • Auto-start: add the command from step 4 to Task Scheduler
    (trigger — “At log on”).
  • Update: python update.py --yes (from the program folder).
""",
        "manual.instructions.linux": """\
MANUAL INSTALL ON LINUX
=======================

1. Connect to the server over SSH:
     ssh <user>@<address>
   (on the first connection confirm the fingerprint with yes)

2. Make sure Python 3.10+ is installed:
     python3 --version
   If not:
     sudo apt update && sudo apt install -y python3 python3-venv     (Ubuntu/Debian)
     sudo dnf install -y python3                                    (Fedora/RHEL)

3. Download the archive and unpack it:
     cd /opt
     sudo mkdir -p bookmarks && sudo chown $USER bookmarks
   copy the contents of bookmarks-latest.zip into /opt/bookmarks
   (/opt/bookmarks/app.py and /opt/bookmarks/bookmarks/ must appear)

4. Create a virtual environment and install dependencies:
     cd /opt/bookmarks
     python3 -m venv .venv
     .venv/bin/pip install -r requirements.txt

5. Simplest start (background, log in data/server.log):
     bash install.sh
   Or a system service (starts on every boot, recommended):
     sudo bash install.sh systemd
   Check:  systemctl status bookmarks

6. Open in your browser:  http://<server-address>:8765
   If it does not open from a phone/another PC — allow the port:
     sudo ufw allow 8765/comment 'bookmarks'

Useful:
  • Logs: journalctl -u bookmarks -f
  • Stop: sudo systemctl stop bookmarks
  • Manage users: .venv/bin/python manage.py list-users
  • Update: .venv/bin/python update.py --yes
""",
        "manual.instructions.docker": """\
MANUAL INSTALL WITH DOCKER
==========================

1. Connect to the server over SSH:
     ssh <user>@<address>

2. Install Docker if you do not have it (the official script detects
   your distribution automatically):
     curl -fsSL https://get.docker.com | sh
     sudo systemctl enable --now docker
   To run docker without sudo:
     sudo usermod -aG docker $USER   (then log out and back in)

3. Place the project files (from bookmarks-latest.zip) into a folder,
   e.g.:
     sudo mkdir -p /opt/bookmarks && sudo cp -r <archive contents> /opt/bookmarks

4. Prepare a compose file with your port (replace 8765 if needed):
     cd /opt/bookmarks
     # in docker-compose.yml the line ports: - "8765:8765"
     # change the left side to your port, e.g. "9000:8765"

5. Build the image and start the container (data lives in the
   bookmarks-data volume and survives rebuilds/container removal):
     docker compose up -d --build

6. Check:
     docker compose ps            # status healthy
     curl http://127.0.0.1:8765/health
   Open in your browser:  http://<server-address>:8765

Useful:
  • Logs: docker logs -f bookmarks
  • Stop: docker compose stop
  • Update: docker compose up -d --build (after replacing the files)
""",
        "manual.instructions.all": "PICK YOUR OPTION IN THE GUIDE BELOW\n"
        "=======================================================\n\n",
    },
}


def strings(lang: str) -> dict:
    return STRINGS.get(lang, STRINGS["ru"])


def t(lang: str, key: str, **kwargs) -> str:
    table = STRINGS.get(lang, STRINGS["ru"])
    text = table.get(key)
    if text is None:
        text = STRINGS["ru"].get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text
