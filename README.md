<div align="center">

# 🔖 Bookmarks

**Многопользовательский менеджер закладок с поддержкой приватных пространств, тегов, метаданных и продвинутого администрирования.**  
*A multi-user bookmark manager featuring private spaces, tags, automatic metadata fetching, and advanced administration.*

[![Ubuntu Server](https://img.shields.io/badge/Ubuntu%20Server-22.04%20%2F%2024.04-E95420?style=flat-square&logo=ubuntu&logoColor=white)](https://ubuntu.com/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)

---

[🇷🇺 Русский](#-русский) | [🇬🇧 English](#-english)

</div>

---

## ✨ Возможности / Features

- **👥 Мультипользовательский / Multi-user** — регистрация и вход; у каждого аккаунта своё приватное пространство.
- **📁 Группы и «Избранное» / Groups & Favorites** — кастомные группы, встроенное «Избранное», перестановка групп местами.
- **🔐 Секретная группа / Secret Group** — особая группа сразу после «Избранного»:
  - Ссылки скрыты из «Дома», поиска, тегов, статистики и экспорта до ввода сессионного пароля.
  - Обращения по ID возвращают «не найдено».
  - 🔐/🔓 служит одновременно индикатором и переключателем.
  - Пароль (от 8 символов) меняется только при открытой группе, попытки разблокировки ограничены.
- **🔍 Поиск, теги и сортировка / Search, Tags & Sorting** — полнотекстовый поиск по названию, URL, описанию и тегам; сортировка по дате, названию или количеству визитов.
- **📄 Постраничная выдача / Pagination** — ленты загружаются по 100 ссылок с удобной кнопкой «Показать ещё» (`limit`/`offset` в API).
- **📥 Импорт и экспорт / Import & Export** — поддержка форматов JSON и Netscape HTML (стандартный экспорт браузеров).
- **⚡ Автоподтяжка метаданных / Auto Metadata** — заголовки, описания и фавиконки подтягиваются автоматически (с кэшированием и механизмом повтора неудачных загрузок).
- **🎨 Персонализация / Personalization** — выбор интерфейса (русский/английский), светлые и тёмные темы, акцентные цвета, 5 быстрых ссылок внизу сайдбара (свои значки и порядок) и мини-календарь у часов.
- **🛡️ Квоты и админ-панель / Quotas & Admin Panel** — индивидуальные лимиты закладок, тегов и групп на пользователя. Удобная панель администратора: сводная статистика, управление пользователями (роли, блокировка, сброс пароля, лимиты). Первый зарегистрированный аккаунт автоматически получает права администратора.

---

## 🛠️ `install.sh`

> **Один скрипт — установка, обслуживание и удаление сервиса Bookmarks** на Ubuntu Server (systemd). Если рядом с `install.sh` нет файлов программы, он **самостоятельно клонирует репозиторий** и продолжает работу из полной папки.
> 
> *One script — install, maintain, and remove the Bookmarks service on Ubuntu Server (systemd).*

---

## 🇷🇺 Русский

### 🚀 Быстрый старт

Установка одной командой:

```bash
curl -fsSL https://raw.githubusercontent.com/evgeniy7f2/Bookmarks/main/install.sh | sudo bash
```

Скрипт автоматически установит зависимости, скопирует файлы, создаст systemd-сервис `bookmarks` (с автозагрузкой при старте и перезапуском при сбое), проверит работоспособность и выведет адрес в терминале. **Первый зарегистрированный пользователь станет администратором системы.**

<img width="721" height="228" alt="image" src="https://github.com/user-attachments/assets/1ccefe59-0738-410f-8636-03e99808dca1" />


```bash
git clone https://github.com/evgeniy7f2/Bookmarks.git
cd Bookmarks
sudo bash install.sh
```

---

### 💻 Управление и команды

| Команда | Описание |
| :--- | :--- |
| `sudo bash install.sh` | Интерактивное меню / установка |
| `sudo bash install.sh install` | Установка / повторная установка (обновление файлов) |
| `sudo bash install.sh port [N]` | Смена порта (`N` — новый порт; без аргумента — запросит интерактивно) |
| `sudo bash install.sh backup` | Создание онлайн-бэкапа базы в `data/backups/` без остановки сервиса |
| `sudo bash install.sh uninstall` | Полное удаление: сервис, правила polkit, файлы, данные и системный пользователь |
| `sudo bash install.sh menu` | Вызов интерактивного меню |
| `sudo bash install.sh help` | Справка |

---

### ⚙️ Неинтерактивный режим

Для автоматизированного развёртывания используйте переменные окружения:

```bash
INSTALL_DIR=/opt/bookmarks PORT=8765 BIND=external UI_LANG=ru sudo bash install.sh
```

| Переменная | Описание |
| :--- | :--- |
| `INSTALL_DIR` | Каталог установки (по умолчанию: `/opt/bookmarks`) |
| `PORT` | Порт приложения (по умолчанию: `8765`) |
| `BIND` | `external` (0.0.0.0) или `internal` (127.0.0.1) |
| `UI_LANG` | Язык интерфейса: `ru` или `en` (иначе — из локали системы) |
| `REPO_URL` | Репозиторий для автоклонирования (по умолчанию: `evgeniy7f2/Bookmarks`) |

---

### 🔧 Обслуживание

- **Смена порта:**  
  `sudo bash install.sh port 9000` обновит конфигурацию в `/etc/systemd/system/bookmarks.service` и `install.json`, перезапустит сервис и выполнит `health`-чек. При внешнем доступе скрипт напомнит открыть порт в фаерволе (`sudo ufw allow 9000/tcp`).
- **Бэкап базы данных:**  
  `sudo bash install.sh backup` создаёт консистентную копию базы данных в `<каталог>/data/backups/` (`bookmarks-YYYYmmdd-HHMMSS.sqlite3`). Хранится 7 последних копий (`KEEP=14 /opt/bookmarks/backup.sh` — для изменения количества).  
  *Восстановление:* остановить сервис (`sudo systemctl stop bookmarks`), заменить `data/bookmarks.db` файлом бэкапа и запустить обратно (`sudo systemctl start bookmarks`).
- **Полное удаление (`uninstall`):**  
  Останавливает и убирает systemd-юнит `bookmarks`, удаляет правила polkit (`/etc/polkit-1/rules.d/90-bookmarks.rules`), удаляет файлы программы и данные (включая бэкапы) и удаляет системного пользователя `bookmarks`.

---

### 📋 Требования
- Ubuntu Server 22.04 / 24.04
- `git` и `Python 3.10+` (устанавливаются автоматически при отсутствии)

---

## 🇬🇧 English

### 🚀 Quick Start

Install with a single command:

```bash
curl -fsSL https://raw.githubusercontent.com/evgeniy7f2/Bookmarks/main/install.sh | sudo bash
```

The script will install dependencies, copy files, create a systemd service `bookmarks` (with auto-start on boot and failure recovery), verify startup, and print the web address. **The first registered user automatically becomes the administrator.**

<img width="721" height="228" alt="image" src="https://github.com/user-attachments/assets/5b3f7ca1-9c57-4ffa-9449-526e9c2a8e28" />


Or manually:

```bash
git clone https://github.com/evgeniy7f2/Bookmarks.git
cd Bookmarks
sudo bash install.sh
```

---

### 💻 Commands & Management

| Command | Description |
| :--- | :--- |
| `sudo bash install.sh` | Interactive menu / installation |
| `sudo bash install.sh install` | Install / reinstall (file update) |
| `sudo bash install.sh port [N]` | Change port (`N` = new port; prompts if omitted) |
| `sudo bash install.sh backup` | Create online database backup in `data/backups/` without stopping the service |
| `sudo bash install.sh uninstall` | Complete removal: service, polkit rules, files, data, and system user |
| `sudo bash install.sh menu` | Open interactive menu |
| `sudo bash install.sh help` | Show help information |

---

### ⚙️ Non-Interactive Mode

For automated deployments, pass environment variables:

```bash
INSTALL_DIR=/opt/bookmarks PORT=8765 BIND=external UI_LANG=ru sudo bash install.sh
```

| Variable | Description |
| :--- | :--- |
| `INSTALL_DIR` | Installation directory (default: `/opt/bookmarks`) |
| `PORT` | Application port (default: `8765`) |
| `BIND` | `external` (0.0.0.0) or `internal` (127.0.0.1) |
| `UI_LANG` | Interface language: `ru` or `en` (otherwise taken from system locale) |
| `REPO_URL` | Repository for auto-cloning (default: `evgeniy7f2/Bookmarks`) |

---

### 🔧 Maintenance

- **Changing the Port:**  
  `sudo bash install.sh port 9000` updates `--port` in `/etc/systemd/system/bookmarks.service` and `install.json`, restarts the service, and runs a health check. Reminds you about the firewall if needed (`sudo ufw allow 9000/tcp`).
- **Database Backup:**  
  `sudo bash install.sh backup` creates a consistent online backup in `<dir>/data/backups/` named `bookmarks-YYYYmmdd-HHMMSS.sqlite3` (keeps the 7 most recent copies, customizable via `KEEP=14`).  
  *Restore:* stop the service (`sudo systemctl stop bookmarks`), replace `data/bookmarks.db` with the backup file, and start the service (`sudo systemctl start bookmarks`).
- **Full Uninstall:**  
  Stops the service, removes the systemd unit, polkit rules (`/etc/polkit-1/rules.d/90-bookmarks.rules`), program files, data (including backups), and the `bookmarks` system user.

---

### 📋 Requirements
- Ubuntu Server 22.04 / 24.04
- `git` and `Python 3.10+` (installed automatically if missing)
