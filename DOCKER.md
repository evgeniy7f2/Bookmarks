# Развёртывание Bookmarks в Docker (на ПК)

Пошаговая инструкция, как поставить менеджер закладок Bookmarks в Docker-контейнер.
Основной сценарий — **Windows (Docker Desktop)**; в конце — вариант для **Linux/Ubuntu-сервера**.

Готовый результат: приложение доступно по адресу `http://localhost:8765`,
данные хранятся в томе Docker и переживают пересборку и удаление контейнера.

> **Быстрый способ — установщик.** `python installer/installer.py` →
> «Docker по SSH» — сам поставит Docker, соберёт образ и поднимет
> контейнер на удалённом Linux-сервере по SSH (нужны только IP, порт и
> SSH-логин/пароль). На локальной машине способ «Ручная установка»
> соберёт архив со всеми файлами и инструкцию. Подробности — в
> [README.md](README.md), раздел «Установщик».

---

## 0. Что нужно заранее

| Что | Зачем |
|---|---|
| Docker Desktop (Windows) или Docker Engine + compose-плагин (Linux) | Запускать контейнер |
| Папка с проектом Bookmarks (эта) | От неё строится образ |
| Порт **8765** свободен на машине | Порт приложения |

Состав проекта, который нужен для сборки (остальное в образ не попадает — `.dockerignore`):
`Dockerfile`, `docker-compose.yml`, `requirements.txt`, `app.py`, `manage.py`,
`backup.sh`, каталог `bookmarks/`.

---

## 1. Установка Docker — Windows (Docker Desktop)

1. **Проверьте систему.** Нужен Windows 10 (64-bit, 21H2 и новее) или Windows 11.
   Включите **Virtualization (VT-x/AMD-V)** в BIOS/UEFI и установите платформу WSL2:

   ```powershell
   wsl --install
   ```
   (перезагрузитесь после установки). Если WSL уже есть — этот шаг не нужен.

2. **Скачайте Docker Desktop:**
   <https://www.docker.com/products/docker-desktop/>
   → кнопка *Download for Windows*. Запустите установник, согласитесь с условиями.

3. **Перезагрузите ПК**, если установщик попросил. Docker Desktop стартует в трее
   (кит 🐳). Дождитесь статуса *Docker Desktop is running*.

4. **Проверьте** в PowerShell:

   ```powershell
   docker --version          # Docker version 2x.x.x ...
   docker compose version    # Docker Compose version v2.x.x ...
   ```

   Обе команды должны ответить версиями — Docker готов.

> Если видите ошибку про WSL/virtualization: убедитесь, что WSL2 установлен
> (`wsl --list --verbose`), виртуализация включена в BIOS, и перезапустите
> Docker Desktop (ПКМ по киту → Settings → General → *Restart*).

---

## 2. Установка Docker — Linux (Ubuntu/Debian)

```sh
# 1) Официальный репозиторий Docker
curl -fsSL https://get.docker.com | sh

# 2) Compose-плагин (обычно ставится вместе, иначе вручную):
sudo apt-get install -y docker-compose-plugin

# 3) Разрешить текущему пользователю работать с docker без sudo (опционально)
sudo usermod -aG docker $USER   # после — выйти и зайти снова

# 4) Проверка
docker --version
docker compose version
```

---

## 3. Подготовьте папку проекта

Скопируйте папку `bookmarks` (корень проекта, где лежит `Dockerfile`) на ПК,
например в `C:\bookmarks`. Варианты:

- скопировать папку с другой машины (USB, сетевая папка, `robocopy`/`scp`);
- скачать с сервера: `scp -r root@192.168.100.20:/root/bookmarks C:\bookmarks`
  (если проект уже лежит на сервере);
- клонировать из git, если проект в репозитории.

Убедитесь, что в папке есть `Dockerfile` и `docker-compose.yml`:

```powershell
dir C:\bookmarks
```

---

## 4. Сборка и запуск

### Вариант А — через compose (рекомендуется)

```powershell
cd C:\bookmarks
docker compose up -d --build
```

`--build` соберёт образ из `Dockerfile` (при первом запуске и после изменений кода).
Флаг `-d` — в фоне.

### Вариант Б — вручную (docker build + run)

```powershell
docker build -t bookmarks .
docker run -d --name bookmarks -p 8765:8765 -v bookmarks_data:/data bookmarks
```

---

## 5. Проверка, что всё работает

```powershell
docker compose ps        # статус: Up ... (healthy)
docker compose logs -f   # логи; Ctrl+C — выйти
```

Откройте в браузере **`http://localhost:8765`** и зарегистрируйте первого пользователя.

Быстрая проверка «здоровья» из командной строки:

```powershell
curl http://localhost:8765/health
# {"app":"Bookmarks","version":"1.4.0","schema":"6","db":true,"ok":true}
```

---

## 6. Перенос уже существующих данных (опционально)

Если у вас уже есть работающая копия с данными (например, на другой машине),
их можно перенести. Два способа:

1. **Через интерфейс (проще всего):** в старой копии «Настройки» (⚙) → «Экспорт» →
   «Скачать полный бэкап (JSON)»; в новой копии зарегистрируйте пользователя и
   импортируйте файл (раздел «Импорт») — восстановятся группы, ссылки, иконки,
   настройки, быстрые ссылки, аватар и пароль «Секретных».

2. **Скопировать файл БД в том** (имена/пароли переносятся как есть):

   ```powershell
   docker cp bookmarks.db bookmarks:/data/bookmarks.db
   docker exec -u root bookmarks chown bookmarks:bookmarks /data/bookmarks.db
   docker compose restart
   ```

   > На Windows файл `bookmarks.db` лежит в каталоге `data/` старой установки
   > (`C:\...\bookmarks\data\bookmarks.db`).
   > Перед копированием остановите старую копию приложения: SQLite работает в
   > режиме WAL, и свежие данные могут лежать в `bookmarks.db-wal` — без
   > остановки копия будет неполной. Если остановить нельзя — используйте «Экспорт».

После переноса: `curl http://localhost:8765/health` → `ok:true`, в интерфейсе видны
старые пользователи/закладки.

---

## 7. Обновление после изменений кода

Положите обновлённые файлы в папку проекта и пересоберите:

```powershell
cd C:\bookmarks
docker compose up -d --build
```

Данные в томе **остаются на месте** — теряются только при явном удалении тома.

---

## 8. Остановка и удаление

```powershell
docker compose stop          # остановить (данные и образ остаются)
docker compose down          # остановить и удалить контейнер (данные в томе ОСТАЮТСЯ)
docker compose down -v       # + удалить ТОМ с данными (БД пропадёт — осторожно!)
docker rmi bookmarks         # удалить сам образ (опционально)
```

Чтобы удалить вообще всё, включая данные: `docker compose down -v`, затем
`docker volume rm bookmarks_bookmarks-data` (имя тома зависит от имени папки проекта).

---

## 9. Справочник: что где и как

| Параметр | Значение |
|---|---|
| Порт | **8765** (`-p 8765:8765`) |
| Адрес | `http://localhost:8765` (с ПК) / `http://<ip-машины>:8765` (из сети) |
| Данные (в контейнере) | `/data` (том) |
| Том (compose) | `bookmarks_bookmarks-data` |
| Имя контейнера | `bookmarks` |
| Пользователь в контейнере | `bookmarks` (uid **10001**, не root) |
| Часовой пояс логов | `TZ` в `docker-compose.yml` (по умолчанию `Etc/MSK`; на интерфейс не влияет) |
| Healthcheck | `GET /health` (встроен в образ) |
| Переменная окружения | `BOOKMARKS_DATA=/data` (уже прописана в образе) |
| Приватные адреса | по умолчанию блокируются (SSRF); разрешить: `BOOKMARKS_ALLOW_PRIVATE: "1"` в `environment` |
| Закрытая регистрация | `BOOKMARKS_REGISTRATION: "closed"` в `environment` |

### Ключевые команды

| Действие | Команда |
|---|---|
| Поднять | `docker compose up -d --build` |
| Статус | `docker compose ps` |
| Логи | `docker compose logs -f` |
| Остановить | `docker compose down` |
| Пересобрать после правок | `docker compose up -d --build` |
| Открыть shell внутри | `docker compose exec bookmarks sh` |
| Посмотреть данные | `docker volume inspect bookmarks_bookmarks-data` |

---

## 10. Частые проблемы

| Симптом | Причина / решение |
|---|---|
| `docker: command not found` / «не является внутренней командой» | Docker не установлен или PowerShell/терминал открыт до установки. Перезапустите терминал; на Windows — убедитесь, что Docker Desktop запущен. |
| Порт 8765 занят | `netstat -ano \| findstr 8765` → найдите PID и остановите процесс, либо смените порт: в `docker-compose.yml` `ports: - "8080:8765"` и откройте `http://localhost:8080`. |
| Контейнер сразу падает | `docker compose logs -f` — читать последнюю строку. Часто это конфликт порта или битая БД в томе. |
| Статус `unhealthy` | Приложение не ответило на `/health`. `docker compose logs -f`; обычно стартует через несколько секунд — подождите и повторите `docker compose ps`. |
| `permission denied` при записи в БД (только Linux, bind mount) | Файлы должны принадлежать uid 10001: `sudo chown -R 10001:10001 data`. Проще использовать именованный том (как в compose) — он инициализируется с правильными правами сам. |
| Данные пропали после `down` | Скорее всего использован `down -v`. Данные живут в томе; `down` без `-v` их сохраняет. |
| Медленный первый запуск | Первый `docker build` качает базовый образ `python:3.12-slim` (~50 МБ) — это нормально, дальше используется кэш. |
| `docker compose: command not found` (Linux) | Установите плагин: `sudo apt-get install -y docker-compose-plugin`. Старый `docker-compose` (с дефисом) тоже подойдёт, но compose-плагин предпочтительнее. |

---

## 11. Бэкапы на сервере (Linux)

Данные лежат в томе (`/data` в контейнере). Копировать файл БД «на лету»
нельзя (WAL), поэтому для бэкапа есть `manage.py backup` — онлайн-копия через
`sqlite3`'s backup API, безопасная при работающем контейнере:

```sh
# одноразовый бэкап прямо из контейнера (manage.py уже в образе):
docker compose exec bookmarks python manage.py backup /data/backups/bookmarks.sql3
# или с хоста, если данные смонтированы в папку:
./backup.sh        # кладёт копию в data/backups/ и держит 7 последних (KEEP)
```

На сервере удобно повесить `backup.sh` в cron (раздел «Администрирование» в README).
Перед удалением тома (`docker compose down -v`) убедитесь, что свежий бэкап есть.

## 12. Короткий чек-лист

1. Docker установлен: `docker --version` + `docker compose version` отвечают.
2. Папка проекта скопирована, в ней есть `Dockerfile` и `docker-compose.yml`.
3. `docker compose up -d --build` → без ошибок.
4. `docker compose ps` → `Up ... (healthy)`.
5. `http://localhost:8765` открыт, создан пользователь.
6. (Опционально) старые данные перенесены.

Готово — Bookmarks работает в Docker на вашем ПК.
