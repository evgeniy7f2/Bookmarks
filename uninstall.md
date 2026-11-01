# Удаление Bookmarks

Полное удаление приложения по типам установки: **Windows**, **Linux (systemd)**,
**Docker**. Общий порядок везде один: **бэкап данных → остановить процесс/сервис
→ убрать автозапуск → удалить артефакты (каталог, юнит, том, образ, ярлык) →
проверить порт**.

## 0. Данные (сделать ДО удаления)

Лучший бэкап — из веб-интерфейса: **Экспорт → «Скачать полный бэкап (JSON)»**
(v1.2.0+): группы со значками, ссылки (иконки/pinned/visits/dates), настройки
(включая быстрые ссылки), профиль и пароль секретной группы. Импорт в новый
аккаунт восстанавливает весь интерфейс.

Где лежит база (если нужен именно файл БД):

| Тип установки | Путь к `bookmarks.db` |
|---|---|
| Windows | `C:\Bookmarks\data\bookmarks.db` (или `<каталог-установки>\data\`) |
| Linux (systemd) | `<каталог>/data/bookmarks.db` (`/opt/bookmarks` у root, `~/bookmarks` у обычного юзера) |
| Docker | в именованном томе `<имя-каталога>_bookmarks-data` (например `bookmarks_bookmarks-data`) |

---

## 1. Windows

Установка создаёт: каталог `C:\Bookmarks` (файлы приложения, `.venv`, `data`,
`install.json`), **автозапуск в реестре** (`HKCU\...\Run`, значение `Bookmarks`),
**ярлык в «Пуске»** (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Bookmarks.lnk`),
фоновый процесс `python.exe` (отделённый, без окна).

```powershell
# 1. Остановить сервер (процесс слушает порт; по умолчанию 8765)
Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }

# 2. Убрать автозапуск (реестр)
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v Bookmarks /f

# 3. Убрать ярлык «Пуска»
Remove-Item "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Bookmarks.lnk" -ErrorAction SilentlyContinue

# 4. Удалить каталог установки (всё: файлы, .venv, data, install.json)
Remove-Item C:\Bookmarks -Recurse -Force

# 5. (опционально) кэш EXE-установщика (payload + paramiko)
Remove-Item "$env:LOCALAPPDATA\bookmarks-installer" -Recurse -Force -ErrorAction SilentlyContinue
```

Нюансы:

- Если установщик **сам ставил Python** (галка «установить Python автоматически»
  при его отсутствии на машине) — он установлен отдельно:
  «Параметры → Приложения → Python → Удалить». Удаляйте только если Python не
  нужен другим программам.
- Если порт был не 8765 — подставьте свой в п. 1.
- Кэш `%LOCALAPPDATA%\bookmarks-installer` создаёт EXE-установщик при скачивании
  payload; на работу приложения не влияет, можно удалить.

**Проверка:** `Get-NetTCPConnection -LocalPort 8765` → пусто;
`reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v Bookmarks` →
«не найдено»; `Test-Path C:\Bookmarks` → `False`.

---

## 2. Linux (systemd)

Установка создаёт: каталог (root → `/opt/bookmarks`, обычный юзер → `~/bookmarks`)
с файлами приложения, `.venv/` и `data/`, **systemd-юнит**
`/etc/systemd/system/bookmarks.service` (включён в автозапуск, `Restart=always`).

```bash
# 1. Остановить сервис и убрать автозапуск
sudo systemctl disable --now bookmarks

# 2. Удалить файл юнита и перезагрузить systemd
sudo rm /etc/systemd/system/bookmarks.service
sudo systemctl daemon-reload

# 3. Удалить каталог установки (всё: файлы, .venv, data)
#    у root:
sudo rm -rf /opt/bookmarks
#    у обычного юзера:
rm -rf ~/bookmarks

# 4. (опционально) если установщик сам ставил python3-venv и он не нужен
sudo apt-get remove -y python3-venv
```

**Проверка:** `systemctl status bookmarks` →
`Unit bookmarks.service could not be found`; `ss -tlnp | grep 8765` → пусто.

---

## 3. Docker

Установка создаёт: каталог с исходниками (например `/root/bookmarks` —
`Dockerfile`, `docker-compose.yml`, `app.py`, `bookmarks/`), **контейнер** и
**образ** `bookmarks`, **именованный том** `<имя-каталога>_bookmarks-data`
(например `bookmarks_bookmarks-data` — данные). При отсутствии Docker установка
ставила и сам Docker Engine (`get.docker.com`).

```bash
# 1. Остановить и удалить контейнер (из каталога установки)
cd /root/bookmarks && docker compose down

# 2. Удалить том С ДАННЫМИ (если бэкап сделан и он не нужен)
docker volume rm bookmarks_bookmarks-data
#    либо сразу в п.1: docker compose down -v — удалит все томы, объявленные
#    в docker-compose.yml

# 3. Удалить образ
docker rmi bookmarks

# 4. Удалить каталог с исходниками
rm -rf /root/bookmarks

# 5. (опционально) если Docker был установлен установщиком и больше не нужен
sudo systemctl disable --now docker
sudo apt-get remove -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Нюансы:

- `docker compose down -v` безопасно только если в `docker-compose.yml` объявлены
  тома **только** Bookmarks — иначе проверьте `docker compose config` перед `down -v`.
- Если порт в compose менялся установщиком (`sed` на `8765:8765`), в `docker ps`
  смотрите фактический внешний порт.

**Проверка:** `docker ps -a | grep bookmarks` → пусто;
`docker volume ls | grep bookmarks` → пусто; порт закрыт.

---

## Быстрая справка «что удалять»

| Артефакт | Windows | Linux (systemd) | Docker |
|---|---|---|---|
| Каталог приложения | `C:\Bookmarks` | `/opt/bookmarks` или `~/bookmarks` | `/root/bookmarks` (исходники) |
| Виртуальное окружение | `<dir>\.venv` | `<dir>/.venv` | внутри образа |
| Данные (БД, иконки, secret.key) | `<dir>\data` | `<dir>/data` | том `<каталог>_bookmarks-data` |
| Автозапуск | реестр `Run\Bookmarks` | `systemctl enable` + `.service` | `restart: unless-stopped` (с контейнером) |
| Ярлык/контейнер/образ | `Bookmarks.lnk` в «Пуске» | — | контейнер + образ `bookmarks` |
| Сервер-процесс | detached `python.exe` | systemd-юнит `bookmarks` | контейнер `bookmarks` |
| Кэш установщика | `%LOCALAPPDATA%\bookmarks-installer` | `~/.cache/bookmarks-installer` | — |
