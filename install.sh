#!/usr/bin/env bash
#
# ─────────────────────────────────────────────────────────────────────────────
#  🔖  Bookmarks — Ubuntu Server: установка и обслуживание systemd-сервиса.
#      Интерфейс: RU/EN (автоматически по локали, UI_LANG=ru|en).
#
#   sudo bash install.sh                  # меню (интерактивно) / установка (непинтерактивно)
#   sudo bash install.sh install          # установка / повторная установка
#   sudo bash install.sh port [N]         # смена порта
#   sudo bash install.sh backup           # онлайн-бэкап базы данных
#   sudo bash install.sh uninstall        # полное удаление программы
#   sudo bash install.sh menu             # интерактивное меню
#   sudo bash install.sh help             # справка
#
#  Если папка неполная (например, с GitHub скачан только install.sh),
#  скрипт САМ клонирует репозиторий (REPO_URL) и перезапускается от
#  полной папки:
#    curl -fsSL https://raw.githubusercontent.com/evgeniy7f2/Bookmarks/main/install.sh | sudo bash
#
#  Непинтерактивный режим (переменные окружения, вопросы не задаются):
#    INSTALL_DIR=/opt/bookmarks PORT=8765 BIND=external UI_LANG=ru \
#      REPO_URL=https://github.com/evgeniy7f2/Bookmarks.git sudo bash install.sh
#    BIND:    external (0.0.0.0) или internal (127.0.0.1)
#
#  Установка: python3 и зависимости в виртуальное окружение (если нет),
#  копирование файлов, системный пользователь "bookmarks", systemd-сервис
#  "bookmarks" (автозапуск при загрузке, автоперезапуск при сбое, polkit-
#  права start/stop для самого сервиса — их использует автообновление),
#  проверка запуска (http://127.0.0.1:<порт>/health) и адрес.
#
#  Bookmarks — Ubuntu Server: install & maintain the systemd service.
#  UI: RU/EN (auto-detected from the locale, UI_LANG=ru|en).
#
#   sudo bash install.sh                  # menu (interactive) / install (non-interactive)
#   sudo bash install.sh install          # install / reinstall
#   sudo bash install.sh port [N]         # change the port
#   sudo bash install.sh backup           # online database backup
#   sudo bash install.sh uninstall        # full removal
#   sudo bash install.sh menu             # interactive menu
#   sudo bash install.sh help             # help
#
#  If the folder is incomplete (e.g. only install.sh was downloaded from
#  GitHub), the script clones the repository (REPO_URL) by itself and
#  re-runs from the complete folder:
#    curl -fsSL https://raw.githubusercontent.com/evgeniy7f2/Bookmarks/main/install.sh | sudo bash
#
#  Non-interactive (env vars, no questions):
#    INSTALL_DIR=… PORT=… BIND=… UI_LANG=… REPO_URL=… sudo bash install.sh
#    BIND: external (0.0.0.0) or internal (127.0.0.1)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE="bookmarks"
RUN_USER="bookmarks"
POLKIT_RULE="/etc/polkit-1/rules.d/90-bookmarks.rules"
UNIT_FILE="/etc/systemd/system/${SERVICE}.service"
REPO_URL="${REPO_URL:-https://github.com/evgeniy7f2/Bookmarks.git}"
DEFAULT_DIR="/opt/bookmarks"
DEFAULT_PORT="8765"

# ------------------------------------------------------------------ language --

case "${LANG:-${LC_ALL:-}}" in
  en*) UI_DEFAULT="en" ;;
  *)   UI_DEFAULT="ru" ;;
esac

UI_LANG="${UI_LANG:-}"
if [ -z "$UI_LANG" ] && [ -t 0 ]; then
  _lang_answer=""
  read -r -p "  🔖  Bookmarks — Language / Язык (ru/en) [$UI_DEFAULT]: " _lang_answer || _lang_answer=""
  UI_LANG="${_lang_answer:-$UI_DEFAULT}"
fi
UI_LANG="${UI_LANG:-$UI_DEFAULT}"
case "$(printf '%s' "$UI_LANG" | tr '[:upper:]' '[:lower:]')" in
  en*) UI_LANG="en" ;;
  *)   UI_LANG="ru" ;;
esac

set_lang() {
  case "$UI_LANG" in
    en)
      T_TAGLINE="install & maintain the Bookmarks systemd service (Ubuntu Server)"
      T_NOT_ROOT="please run as root: sudo bash install.sh"
      T_CLONING="the folder next to install.sh is incomplete — cloning the repository: %s"
      T_GIT_MISSING="git not found — installing it (apt)…"
      T_NEED_ROOT_GIT="git is missing — run with sudo so the script can install it"
      T_CLONE_FAIL="failed to clone the repository: %s"
      T_CLONE_OK="repository cloned: %s — continuing from the full folder"
      T_CLONE_NO_INSTALL="install.sh not found in the cloned repository (neither in root nor in ubuntu_sp/)"
      T_REPO_INCOMPLETE="the repository itself is incomplete (no bookmarks/, app.py) — upload the whole ubuntu_sp/ folder to GitHub"
      T_BAD_CMD="unknown command: \"%s\""
      T_STATE_NOT="Bookmarks is not installed (no systemd service \"bookmarks\")"
      T_STATE_INSTALLED="Bookmarks is installed: %s, port %s"
      T_MENU_INSTALL="install / update"
      T_MENU_PORT="change the port"
      T_MENU_BACKUP="back up the database"
      T_MENU_UNINSTALL="uninstall"
      T_MENU_EXIT="exit"
      T_MENU_Q="choose an action (0–4)"
      T_MENU_BAD="unknown choice: \"%s\""
      T_MENU_NONTTY="the menu needs an interactive terminal — use a command instead (see: install.sh help)"
      T_STEP_PORT="change the port"
      T_STEP_BACKUP="database backup"
      T_STEP_UNINSTALL="uninstall"
      T_PORT_CUR="current settings: port %s, bind %s"
      T_PORT_NEW_Q="new port"
      T_PORT_SAME="the port has not changed — nothing to do"
      T_PORT_DONE="port changed: %s -> %s"
      T_PORT_TITLE="Bookmarks restarted with the new port"
      T_UNIT_BAD="could not read the port from the service file"
      T_NOT_INSTALLED="the systemd service \"%s\" is not installed — run the install first"
      T_BACKUP="online backup — the service keeps running…"
      T_BACKUP_DONE="done — the copies are in %s (rotation: the 7 most recent)"
      T_DIR_GONE="the install directory is missing: %s"
      T_UN_STOP="stopping the service and removing the unit"
      T_UN_DIR_Q="delete the folder %s (including data/ and backups)?"
      T_UN_DIR_DONE="folder deleted: %s"
      T_UN_DIR_KEEP="folder kept, data preserved: %s"
      T_UN_USER="removing the system user %s"
      T_UN_DONE="Bookmarks has been completely removed"
      T_UN_NOT="the service is not installed — nothing to remove"
      T_PY_MISSING="python3 not found — installing (apt)…"
      T_PY_OK="python3 found: %s"
      T_DIR_Q="install directory"
      T_PORT_Q="port"
      T_ACCESS_Q="access: internal (127.0.0.1) or external (0.0.0.0)"
      T_ACCESS_ERR="access: internal or external (got \"%s\")"
      T_PORT_ERR="port — a number from 1 to 65535 (got \"%s\")"
      T_CHOSEN="directory: %s, port: %s, bind: %s"
      T_COPY="copying program files: %s -> %s"
      T_COPIED="files copied to %s"
      T_INPLACE="installing in place — the files are already in the selected directory"
      T_MISSING="\"%s\" not found next to install.sh — the folder is incomplete"
      T_VENV="creating virtual environment: %s"
      T_VENV_RETRY="failed to create venv — installing python3-venv (apt) and retrying…"
      T_PIP="installing dependencies (pip)…"
      T_DEPS_OK="dependencies installed"
      T_USER="creating system user %s"
      T_POLKIT="granting the service start/stop rights (polkit): %s"
      T_UNIT="installing systemd service: /etc/systemd/system/%s.service"
      T_WAIT="waiting for the server to start (up to 90 s)…"
      T_UFW_Q="ufw is active. Allow incoming TCP port %s? [y/N]: "
      T_UFW_INFO="ufw is active: allow the port manually — sudo ufw allow %s/tcp"
      T_HEALTH_FAIL="the server did not respond: http://127.0.0.1:%s/health"
      T_HEALTH_HINT="see the log: journalctl -u %s -n 50"
      T_DONE="Bookmarks is installed and running!"
      T_ADDR="Address:"
      T_INTERNAL_NOTE="(internal access: from the server itself, or via an SSH tunnel:"
      T_SSH_LINE="ssh -L %s:localhost:%s <user>@<server>  — then open http://127.0.0.1:%s)"
      T_SERVICE="Service:"
      T_LOGS="Logs:"
      T_DATA="Data:"
      T_UPDATES="Updates: in the app — \"About\" → \"Check for updates\""
      T_STEP1="step 1/6 — system preparation (python3)"
      T_STEP2="step 2/6 — copying files"
      T_STEP3="step 3/6 — virtual environment + dependencies"
      T_STEP4="step 4/6 — service user and permissions"
      T_STEP5="step 5/6 — systemd service"
      T_STEP6="step 6/6 — starting and verifying"
      T_IP_PLACEHOLDER="<server IP>"
      ;;
    *)
      T_TAGLINE="установка и обслуживание systemd-сервиса Bookmarks (Ubuntu Server)"
      T_NOT_ROOT="запустите с правами root: sudo bash install.sh"
      T_CLONING="папка рядом с install.sh неполная — клонирую репозиторий: %s"
      T_GIT_MISSING="git не найден — устанавливаю (apt)…"
      T_NEED_ROOT_GIT="git не установлен — запустите с sudo, чтобы скрипт мог поставить его"
      T_CLONE_FAIL="не удалось клонировать репозиторий: %s"
      T_CLONE_OK="репозиторий склонирован: %s — продолжаю от полной папки"
      T_CLONE_NO_INSTALL="в склонированном репозитории не найден install.sh (ни в корне, ни в ubuntu_sp/)"
      T_REPO_INCOMPLETE="в самом репозитории нет полной папки (bookmarks/, app.py) — загрузите на GitHub всю папку ubuntu_sp/"
      T_BAD_CMD="неизвестная команда: \"%s\""
      T_STATE_NOT="Bookmarks не установлен (нет systemd-сервиса \"bookmarks\")"
      T_STATE_INSTALLED="Bookmarks установлен: %s, порт %s"
      T_MENU_INSTALL="установить / обновить"
      T_MENU_PORT="сменить порт"
      T_MENU_BACKUP="бэкап базы данных"
      T_MENU_UNINSTALL="удалить программу"
      T_MENU_EXIT="выход"
      T_MENU_Q="выберите действие (0–4)"
      T_MENU_BAD="неизвестный выбор: \"%s\""
      T_MENU_NONTTY="меню требует интерактивный терминал — используйте команду (см.: install.sh help)"
      T_STEP_PORT="смена порта"
      T_STEP_BACKUP="бэкап базы данных"
      T_STEP_UNINSTALL="удаление"
      T_PORT_CUR="текущие настройки: порт %s, привязка %s"
      T_PORT_NEW_Q="новый порт"
      T_PORT_SAME="порт не менялся — делать нечего"
      T_PORT_DONE="порт изменён: %s -> %s"
      T_PORT_TITLE="Bookmarks перезапущен с новым портом"
      T_UNIT_BAD="не удалось прочитать порт из файла сервиса"
      T_NOT_INSTALLED="systemd-сервис \"%s\" не установлен — сначала выполните установку"
      T_BACKUP="онлайн-бэкап — сервис продолжает работать…"
      T_BACKUP_DONE="готово — копии в %s (ротация: 7 последних)"
      T_DIR_GONE="каталог установки отсутствует: %s"
      T_UN_STOP="останавливаю сервис и убираю юнит"
      T_UN_DIR_Q="удалить каталог %s (вместе с data/ и бэкапами)?"
      T_UN_DIR_DONE="каталог удалён: %s"
      T_UN_DIR_KEEP="каталог сохранён, данные не тронуты: %s"
      T_UN_USER="удаляю системного пользователя %s"
      T_UN_DONE="Bookmarks полностью удалён"
      T_UN_NOT="сервис не установлен — удалять нечего"
      T_PY_MISSING="python3 не найден — устанавливаю (apt)…"
      T_PY_OK="python3 найден: %s"
      T_DIR_Q="каталог установки"
      T_PORT_Q="порт"
      T_ACCESS_Q="доступ: internal (127.0.0.1) или external (0.0.0.0)"
      T_ACCESS_ERR="доступ: internal или external (получено \"%s\")"
      T_PORT_ERR="порт — число от 1 до 65535 (получено \"%s\")"
      T_CHOSEN="каталог: %s, порт: %s, привязка: %s"
      T_COPY="копирую файлы программы: %s -> %s"
      T_COPIED="файлы скопированы в %s"
      T_INPLACE="установка на месте — файлы уже лежат в выбранном каталоге"
      T_MISSING="рядом с install.sh не найден \"%s\" — папка неполная"
      T_VENV="создаю виртуальное окружение: %s"
      T_VENV_RETRY="не удалось создать venv — ставлю python3-venv (apt) и пробую снова…"
      T_PIP="устанавливаю зависимости (pip)…"
      T_DEPS_OK="зависимости установлены"
      T_USER="создаю системного пользователя %s"
      T_POLKIT="выдаю сервису права start/stop (polkit): %s"
      T_UNIT="устанавливаю systemd-сервис: /etc/systemd/system/%s.service"
      T_WAIT="ожидание запуска сервера (до 90 с)…"
      T_UFW_Q="ufw активен. Разрешить входящий TCP-порт %s? [y/N]: "
      T_UFW_INFO="ufw активен: разрешите порт вручную — sudo ufw allow %s/tcp"
      T_HEALTH_FAIL="сервер не ответил: http://127.0.0.1:%s/health"
      T_HEALTH_HINT="смотрите журнал: journalctl -u %s -n 50"
      T_DONE="Bookmarks установлен и запущен!"
      T_ADDR="Адрес:"
      T_INTERNAL_NOTE="(внутренний доступ: с самого сервера, либо через SSH-туннель:"
      T_SSH_LINE="ssh -L %s:localhost:%s <юзер>@<сервер>  и открыть http://127.0.0.1:%s)"
      T_SERVICE="Сервис:"
      T_LOGS="Журнал:"
      T_DATA="Данные:"
      T_UPDATES="Обновления: в приложении — «О программе» → «Проверить обновления»"
      T_STEP1="шаг 1/6 — подготовка системы (python3)"
      T_STEP2="шаг 2/6 — копирование файлов"
      T_STEP3="шаг 3/6 — виртуальное окружение + зависимости"
      T_STEP4="шаг 4/6 — сервисный пользователь и права"
      T_STEP5="шаг 5/6 — systemd-сервис"
      T_STEP6="шаг 6/6 — запуск и проверка"
      T_IP_PLACEHOLDER="<IP-адрес сервера>"
      ;;
  esac
}
set_lang

# -------------------------------------------------------------------- console --

banner() {
  echo
  echo "  ─────────────────────────────────────────────────────────────"
  echo "   🔖  Bookmarks $APP_VER"
  echo "   ${T_TAGLINE}"
  echo "  ─────────────────────────────────────────────────────────────"
  echo
}

step() {
  if [ "$#" -ge 2 ]; then
    echo
    echo "  $1 $2"
  else
    echo
    echo "  🚀 $1"
  fi
}

info() { echo "  ℹ️  $*"; }
ok()   { echo "  ✅ $*"; }
err()  { echo "  ❌ $*" >&2; }

prompt() {
  local val=""
  if [ -t 0 ]; then
    read -r -p "  ❓  $1 [$2]: " val || val=""
  fi
  echo "${val:-$2}"
}

valid_port() {
  [[ "$1" =~ ^[0-9]+$ ]] && [ "$1" -ge 1 ] && [ "$1" -le 65535 ]
}

# ------------------------------------------------------------------ bootstrap --

# Полная папка = рядом с install.sh есть и код, и зависимости, и апдейтер.
folder_complete() {
  [ -d "$SCRIPT_DIR/bookmarks" ] && [ -f "$SCRIPT_DIR/app.py" ] \
    && [ -f "$SCRIPT_DIR/requirements.txt" ] && [ -f "$SCRIPT_DIR/update.py" ]
}

# Папка неполная (скачан только install.sh) → клонируем репозиторий сами
# и перезапускаем скрипт от полной папки (оба лейаута: корень ИЛИ ubuntu_sp/).
ensure_cloned() {
  folder_complete && return 0
  if [ -n "${_BOOKMARKS_BOOTSTRAPPED:-}" ]; then
    err "$T_REPO_INCOMPLETE"
    exit 1
  fi
  export _BOOKMARKS_BOOTSTRAPPED=1
  info "$(printf "$T_CLONING" "$REPO_URL")"
  if ! command -v git >/dev/null 2>&1; then
    if [ "$(id -u)" -ne 0 ]; then
      err "$T_NEED_ROOT_GIT"
      exit 1
    fi
    info "$T_GIT_MISSING"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq git
  fi
  local clone_dir new_dir rc=0
  clone_dir="$(mktemp -d)"
  if ! git clone --depth 1 "$REPO_URL" "$clone_dir" >/dev/null 2>&1; then
    err "$(printf "$T_CLONE_FAIL" "$REPO_URL")"
    rm -rf "$clone_dir"
    exit 1
  fi
  if [ -f "$clone_dir/ubuntu_sp/install.sh" ]; then
    new_dir="$clone_dir/ubuntu_sp"
  elif [ -f "$clone_dir/install.sh" ]; then
    new_dir="$clone_dir"
  else
    err "$T_CLONE_NO_INSTALL"
    rm -rf "$clone_dir"
    exit 1
  fi
  info "$(printf "$T_CLONE_OK" "$new_dir")"
  bash "$new_dir/install.sh" "$@" || rc=$?
  rm -rf "$clone_dir"
  exit "$rc"
}

# --------------------------------------------------------------------- helpers --

# Каталог установки — из WorkingDirectory юнита (фолбэк: /opt/bookmarks).
read_install_dir() {
  local ud=""
  if [ -f "$UNIT_FILE" ]; then
    ud="$(sed -n 's/^WorkingDirectory=//p' "$UNIT_FILE" | head -n1)"
  fi
  ud="${ud%/}"
  if [ -n "$ud" ]; then
    echo "$ud"
  else
    echo "$DEFAULT_DIR"
  fi
}

unit_port() {
  sed -n 's/.*--port \([0-9][0-9]*\).*/\1/p' "$UNIT_FILE" 2>/dev/null | head -n1
}

unit_host() {
  sed -n 's/.*--host \([0-9][0-9.]*\).*/\1/p' "$UNIT_FILE" 2>/dev/null | head -n1
}

wait_health() {
  local port="$1" i
  info "$T_WAIT"
  for i in $(seq 1 45); do
    if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$port/health', timeout=3)" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

# ufw активен и доступ внешний → спросить про порт (в непинтерактиве — подсказка).
ufw_ask() {
  local port="$1"
  command -v ufw >/dev/null 2>&1 || return 0
  ufw status 2>/dev/null | head -n1 | grep -q "Status: active" || return 0
  if [ -t 0 ]; then
    local ans=""
    read -r -p "  🔥  $(printf "$T_UFW_Q" "$port")" ans || ans=""
    case "$ans" in
      y|Y|yes|да) ufw allow "${port}/tcp" ;;
    esac
  else
    info "$(printf "$T_UFW_INFO" "$port")"
  fi
  return 0
}

# Итоговый блок: адрес (+ SSH-туннель для internal), сервис, журнал, данные.
print_result() {
  local title="$1" port="$2" host="${3:-0.0.0.0}"
  local server_ip
  server_ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  [ -n "$server_ip" ] || server_ip="$T_IP_PLACEHOLDER"
  echo
  echo "  ─────────────────────────────────────────────────────────────"
  echo "   🔖  $title"
  echo "  ─────────────────────────────────────────────────────────────"
  echo
  printf "   🌐   %-12s %s\n" "$T_ADDR" "http://$server_ip:$port"
  if [ "$host" = "127.0.0.1" ]; then
    echo "        $T_INTERNAL_NOTE"
    echo "        $(printf "$T_SSH_LINE" "$port" "$port" "$port")"
  fi
  printf "   ⚙️   %-12s systemctl status %s\n" "$T_SERVICE" "$SERVICE"
  printf "   📜   %-12s journalctl -u %s -f\n" "$T_LOGS" "$SERVICE"
  printf "   📁   %-12s %s\n" "$T_DATA" "$(read_install_dir)/data"
  echo "   🔄   $T_UPDATES"
  echo
}

# ------------------------------------------------------------------ commands --

do_install() {
  # ------------------------------------------------------------------ step 1/6 --
  step "$T_STEP1"
  if ! command -v python3 >/dev/null 2>&1; then
    info "$T_PY_MISSING"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq python3 python3-venv
  else
    ok "$(printf "$T_PY_OK" "$(python3 --version 2>&1 | awk '{print $2}')")"
  fi

  local install_dir port access host_bind item
  install_dir="${INSTALL_DIR:-$(prompt "$T_DIR_Q" "$DEFAULT_DIR")}"
  port="${PORT:-$(prompt "$T_PORT_Q" "$DEFAULT_PORT")}"
  access="${BIND:-$(prompt "$T_ACCESS_Q" "external")}"

  case "$access" in
    internal|внутр*|1|127.0.0.1) host_bind="127.0.0.1" ;;
    external|внешн*|2|0.0.0.0)   host_bind="0.0.0.0" ;;
    *) err "$(printf "$T_ACCESS_ERR" "$access")"; return 1 ;;
  esac

  if ! valid_port "$port"; then
    err "$(printf "$T_PORT_ERR" "$port")"
    return 1
  fi

  # срезать хвостовой слэш, чтобы сравнение каталогов и копирование работали
  install_dir="${install_dir%/}"
  [ -n "$install_dir" ] || install_dir="/"

  info "$(printf "$T_CHOSEN" "$install_dir" "$port" "$host_bind")"

  # ------------------------------------------------------------------ step 2/6 --
  step "$T_STEP2"
  mkdir -p "$install_dir"
  if [ "$SCRIPT_DIR" != "$install_dir" ]; then
    info "$(printf "$T_COPY" "$SCRIPT_DIR" "$install_dir")"
    for item in app.py manage.py update.py requirements.txt install.sh \
                backup.sh run.sh README.md bookmarks update; do
      if [ ! -e "$SCRIPT_DIR/$item" ]; then
        err "$(printf "$T_MISSING" "$item")"
        return 1
      fi
      cp -a "$SCRIPT_DIR/$item" "$install_dir/"
    done
  else
    info "$T_INPLACE"
  fi
  mkdir -p "$install_dir/update"
  ok "$(printf "$T_COPIED" "$install_dir")"

  # ------------------------------------------------------------------ step 3/6 --
  step "$T_STEP3"
  local venv_dir="$install_dir/.venv"
  if [ ! -x "$venv_dir/bin/python" ]; then
    info "$(printf "$T_VENV" "$venv_dir")"
    if ! python3 -m venv "$venv_dir"; then
      info "$T_VENV_RETRY"
      apt-get install -y -qq python3-venv
      python3 -m venv "$venv_dir"
    fi
  fi
  info "$T_PIP"
  "$venv_dir/bin/python" -m pip install --upgrade pip >/dev/null
  "$venv_dir/bin/python" -m pip install -r "$install_dir/requirements.txt"
  ok "$T_DEPS_OK"

  # ------------------------------------------------------------------ step 4/6 --
  step "$T_STEP4"
  if ! id -u "$RUN_USER" >/dev/null 2>&1; then
    info "$(printf "$T_USER" "$RUN_USER")"
    useradd --system --home-dir "$install_dir" --shell /usr/sbin/nologin \
            --comment "Bookmarks server" "$RUN_USER"
  fi
  mkdir -p "$install_dir/data"
  chown -R "$RUN_USER:$RUN_USER" "$install_dir"

  # Пользователь сервиса должен уметь останавливать/запускать СВОЙ сервис:
  # автообновлятель приложения делает systemctl stop/start при обновлении.
  info "$(printf "$T_POLKIT" "$POLKIT_RULE")"
  cat > "$POLKIT_RULE" <<POLKIT
polkit.addAdminRule(function(action, subject) {
    if (action.id == "org.freedesktop.systemd1.manage-units" &&
        subject.user == "$RUN_USER" &&
        action.lookup("unit") == "$SERVICE" &&
        (action.lookup("verb") == "start" ||
         action.lookup("verb") == "stop" ||
         action.lookup("verb") == "restart" ||
         action.lookup("verb") == "reload")) {
        return polkit.Result.YES;
    }
});
POLKIT
  chmod 644 "$POLKIT_RULE"

  # ------------------------------------------------------------------ step 5/6 --
  step "$T_STEP5"
  info "$(printf "$T_UNIT" "$SERVICE")"
  cat > "$UNIT_FILE" <<UNIT
[Unit]
Description=Bookmarks - self-hosted bookmark manager
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_USER
WorkingDirectory="$install_dir"
Environment=BOOKMARKS_DATA="$install_dir/data"
ExecStart="$venv_dir/bin/python" "$install_dir/app.py" --host $host_bind --port $port
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT

  # install.json — порт, который автообновлятель проверяет после обновления
  printf '{"port": %s, "host": "%s"}\n' "$port" "$host_bind" > "$install_dir/install.json"
  chown "$RUN_USER:$RUN_USER" "$install_dir/install.json"

  systemctl daemon-reload
  systemctl enable "$SERVICE"

  # ------------------------------------------------------------------ step 6/6 --
  step "$T_STEP6"
  systemctl restart "$SERVICE"
  if ! wait_health "$port"; then
    err "$(printf "$T_HEALTH_FAIL" "$port")"
    err "$(printf "$T_HEALTH_HINT" "$SERVICE")"
    return 1
  fi
  if [ "$host_bind" = "0.0.0.0" ]; then
    ufw_ask "$port"
  fi
  print_result "$T_DONE" "$port" "$host_bind"
  return 0
}

do_port() {
  local requested="${1:-}"
  step "🔌" "$T_STEP_PORT"
  if [ ! -f "$UNIT_FILE" ]; then
    err "$(printf "$T_NOT_INSTALLED" "$SERVICE")"
    return 1
  fi
  local cur_port cur_host new_port dir
  cur_port="$(unit_port)"
  cur_host="$(unit_host)"
  [ -n "$cur_host" ] || cur_host="0.0.0.0"
  if [ -z "$cur_port" ]; then
    err "$T_UNIT_BAD"
    return 1
  fi
  info "$(printf "$T_PORT_CUR" "$cur_port" "$cur_host")"
  new_port="$(prompt "$T_PORT_NEW_Q" "${requested:-$cur_port}")"
  if ! valid_port "$new_port"; then
    err "$(printf "$T_PORT_ERR" "$new_port")"
    return 1
  fi
  if [ "$new_port" = "$cur_port" ]; then
    info "$T_PORT_SAME"
    return 0
  fi
  sed -i "s/--port [0-9][0-9]*/--port $new_port/" "$UNIT_FILE"
  dir="$(read_install_dir)"
  # install.json — порт, который автообновлятель проверяет после обновления
  printf '{"port": %s, "host": "%s"}\n' "$new_port" "$cur_host" > "$dir/install.json"
  systemctl daemon-reload
  systemctl restart "$SERVICE"
  if ! wait_health "$new_port"; then
    err "$(printf "$T_HEALTH_FAIL" "$new_port")"
    err "$(printf "$T_HEALTH_HINT" "$SERVICE")"
    return 1
  fi
  ok "$(printf "$T_PORT_DONE" "$cur_port" "$new_port")"
  if [ "$cur_host" = "0.0.0.0" ]; then
    ufw_ask "$new_port"
  fi
  print_result "$T_PORT_TITLE" "$new_port" "$cur_host"
  return 0
}

do_backup() {
  step "💾" "$T_STEP_BACKUP"
  if [ ! -f "$UNIT_FILE" ]; then
    err "$(printf "$T_NOT_INSTALLED" "$SERVICE")"
    return 1
  fi
  local dir cmdstr
  dir="$(read_install_dir)"
  if [ ! -d "$dir" ]; then
    err "$(printf "$T_DIR_GONE" "$dir")"
    return 1
  fi
  info "$T_BACKUP"
  cmdstr="cd $(printf '%q' "$dir") && bash backup.sh"
  if id -u "$RUN_USER" >/dev/null 2>&1; then
    # от имени сервисного пользователя — чтобы владельцем копии остался bookmarks
    su -s /bin/bash "$RUN_USER" -c "$cmdstr"
  else
    bash -c "$cmdstr"
  fi
  ok "$(printf "$T_BACKUP_DONE" "$dir/data/backups")"
  return 0
}

do_uninstall() {
  step "🗑️" "$T_STEP_UNINSTALL"
  if [ ! -f "$UNIT_FILE" ]; then
    info "$T_UN_NOT"
    return 0
  fi
  local dir ans=""
  dir="$(read_install_dir)"
  info "$(printf "$T_UN_STOP" "$SERVICE")"
  systemctl disable --now "$SERVICE" >/dev/null 2>&1 || true
  rm -f "$UNIT_FILE"
  rm -f "$POLKIT_RULE"
  systemctl daemon-reload
  # «полное удаление»: по умолчанию каталог (вместе с data/) удаляется
  if [ -t 0 ]; then
    read -r -p "  ❓  $(printf "$T_UN_DIR_Q" "$dir") [Y/n]: " ans || ans=""
  fi
  ans="$(printf '%s' "${ans:-y}" | tr '[:upper:]' '[:lower:]')"
  case "$ans" in
    y|yes|д|да)
      rm -rf "$dir"
      ok "$(printf "$T_UN_DIR_DONE" "$dir")"
      ;;
    *)
      info "$(printf "$T_UN_DIR_KEEP" "$dir")"
      ;;
  esac
  if id -u "$RUN_USER" >/dev/null 2>&1; then
    info "$(printf "$T_UN_USER" "$RUN_USER")"
    userdel "$RUN_USER" 2>/dev/null || true
  fi
  ok "$T_UN_DONE"
  return 0
}

run_menu() {
  if [ ! -t 0 ]; then
    err "$T_MENU_NONTTY"
    usage
    return 1
  fi
  local choice mdir mport
  while true; do
    echo
    echo "  ─────────────────────────────────────────────────────────────"
    echo "   🔖  Bookmarks $APP_VER"
    echo "  ─────────────────────────────────────────────────────────────"
    if [ -f "$UNIT_FILE" ]; then
      mdir="$(read_install_dir)"
      mport="$(unit_port)"
      [ -n "$mport" ] || mport="?"
      info "$(printf "$T_STATE_INSTALLED" "$mdir" "$mport")"
    else
      info "$T_STATE_NOT"
    fi
    echo
    echo "     1) $T_MENU_INSTALL"
    echo "     2) $T_MENU_PORT"
    echo "     3) $T_MENU_BACKUP"
    echo "     4) $T_MENU_UNINSTALL"
    echo "     0) $T_MENU_EXIT"
    echo
    choice=""
    read -r -p "  ❓  $T_MENU_Q: " choice || choice=""
    case "$choice" in
      1) do_install || true ;;
      2) do_port || true ;;
      3) do_backup || true ;;
      4) do_uninstall || true ;;
      0|q|Q) break ;;
      "") continue ;;
      *) err "$(printf "$T_MENU_BAD" "$choice")" ;;
    esac
  done
  return 0
}

usage() {
  cat <<'EOF'
  Usage / Использование:

    sudo bash install.sh [command]

    Commands / Команды:
      install              install / reinstall the service
                           (default for non-interactive runs without a command)
      port [N]             change the port (N = the new port, otherwise asked)
      backup               online database backup into <dir>/data/backups/
      uninstall            full removal: service, polkit, files, data, user
      menu                 interactive menu
      help                 this help

    Non-interactive env vars / Переменные окружения:
      INSTALL_DIR=…        install directory (default: /opt/bookmarks)
      PORT=…               port (default: 8765)
      BIND=…               external (0.0.0.0) or internal (127.0.0.1)
      UI_LANG=…            ru or en
      REPO_URL=…           repository for the self-clone (default: GitHub)

    Self-clone / Авто-клонирование:
      If the folder next to install.sh is incomplete, the script clones
      the repository and continues from the full folder:
        curl -fsSL https://raw.githubusercontent.com/evgeniy7f2/Bookmarks/main/install.sh | sudo bash
EOF
}

main() {
  case "${1:-}" in
    "")
      if [ -t 0 ]; then run_menu; else do_install; fi
      ;;
    install)   do_install ;;
    uninstall) do_uninstall ;;
    port)      do_port "${2:-}" ;;
    backup)    do_backup ;;
    menu)      run_menu ;;
    help|-h|--help) usage ;;
    *)
      err "$(printf "$T_BAD_CMD" "$1")"
      echo
      usage
      exit 1
      ;;
  esac
}

# ---------------------------------------------------------------------- start --

ensure_cloned "$@"

APP_VER="$(sed -n 's/^APP_VERSION = "\([^"]*\)".*/\1/p' "$SCRIPT_DIR/bookmarks/util.py" 2>/dev/null || true)"
[ -n "$APP_VER" ] || APP_VER="?"

banner

if [ "$(id -u)" -ne 0 ]; then
  err "$T_NOT_ROOT"
  exit 1
fi

main "$@"
