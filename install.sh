#!/usr/bin/env bash
#
# Bookmarks — установка на Ubuntu Server в виде системного сервиса (systemd).
#
#   sudo bash install.sh
#
# Скрипт интерактивно задаёт вопросы (Enter — принять значение по умолчанию):
#   1. каталог установки                    (по умолчанию: /opt/bookmarks)
#   2. порт                                 (по умолчанию: 8765)
#   3. доступ: internal (127.0.0.1)
#              или external (0.0.0.0)       (по умолчанию: external)
#
# Непрерактивный режим (переменные окружения, вопросы не задаются):
#   INSTALL_DIR=/opt/bookmarks PORT=8765 BIND=external sudo bash install.sh
#   BIND: external (0.0.0.0) или internal (127.0.0.1)
#
# Что делает скрипт:
#   * ставит python3 и зависимости в виртуальное окружение (если нет),
#   * копирует файлы программы в выбранный каталог,
#   * создаёт системного пользователя "bookmarks",
#   * устанавливает systemd-сервис "bookmarks" (автозапуск при загрузке,
#     автоперезапуск при сбое, права start/stop для самого сервиса —
#     их использует автообновление приложения),
#   * проверяет запуск сервера (http://127.0.0.1:<порт>/health)
#     и печатает адрес.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE="bookmarks"
RUN_USER="bookmarks"
POLKIT_RULE="/etc/polkit-1/rules.d/90-bookmarks.rules"

info() { echo "[install] $*"; }
err()  { echo "[install] ОШИБКА: $*" >&2; }

# prompt <вопрос> <по умолчанию> — печатает выбранный ответ
# (в непинтерактивном режиме stdin не tty — сразу возвращается дефолт)
prompt() {
  local val=""
  if [ -t 0 ]; then
    read -r -p "[install] $1 [$2]: " val || val=""
  fi
  echo "${val:-$2}"
}

valid_port() {
  [[ "$1" =~ ^[0-9]+$ ]] && [ "$1" -ge 1 ] && [ "$1" -le 65535 ]
}

# ------------------------------------------------------------- предварительное --

if [ "$(id -u)" -ne 0 ]; then
  err "запустите с правами root: sudo bash install.sh"
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  info "python3 не найден — устанавливаю (apt) …"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq python3 python3-venv
fi

# ------------------------------------------------------------------ вопросы --

INSTALL_DIR="${INSTALL_DIR:-$(prompt "каталог установки" "/opt/bookmarks")}"
PORT="${PORT:-$(prompt "порт" "8765")}"
ACCESS="${BIND:-$(prompt "доступ: internal (127.0.0.1) или external (0.0.0.0)" "external")}"

case "$ACCESS" in
  internal|внутр*|1)  HOST_BIND="127.0.0.1" ;;
  external|внешн*|2|0.0.0.0) HOST_BIND="0.0.0.0" ;;
  *) err "доступ: internal или external (получено \"$ACCESS\")"; exit 1 ;;
esac

if ! valid_port "$PORT"; then
  err "порт — число от 1 до 65535 (получено \"$PORT\")"
  exit 1
fi

# срезать хвостовой слэш, чтобы сравнение каталогов и копирование работали
INSTALL_DIR="${INSTALL_DIR%/}"
[ -n "$INSTALL_DIR" ] || INSTALL_DIR="/"

info "каталог: $INSTALL_DIR, порт: $PORT, привязка: $HOST_BIND"

# ----------------------------------------------------------------- копирование --

mkdir -p "$INSTALL_DIR"
if [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
  info "копирую файлы программы: $SCRIPT_DIR -> $INSTALL_DIR"
  for item in app.py manage.py update.py requirements.txt install.sh \
              backup.sh run.sh README.md README_EN.md bookmarks update; do
    if [ ! -e "$SCRIPT_DIR/$item" ]; then
      err "рядом с install.sh не найден \"$item\" — папка неполная"
      exit 1
    fi
    cp -a "$SCRIPT_DIR/$item" "$INSTALL_DIR/"
  done
fi
mkdir -p "$INSTALL_DIR/update"

# ------------------------------------------------------------ виртуальное окружение --

if [ ! -x "$INSTALL_DIR/.venv/bin/python" ]; then
  info "создаю виртуальное окружение: $INSTALL_DIR/.venv"
  if ! python3 -m venv "$INSTALL_DIR/.venv"; then
    info "не удалось создать venv — ставлю python3-venv (apt) и пробую снова …"
    apt-get install -y -qq python3-venv
    python3 -m venv "$INSTALL_DIR/.venv"
  fi
fi
info "устанавливаю зависимости (pip) …"
"$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip >/dev/null
"$INSTALL_DIR/.venv/bin/python" -m pip install -r "$INSTALL_DIR/requirements.txt"

# ---------------------------------------------------------------- сервисный юзер --

if ! id -u "$RUN_USER" >/dev/null 2>&1; then
  info "создаю системного пользователя $RUN_USER"
  useradd --system --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin \
          --comment "Bookmarks server" "$RUN_USER"
fi

mkdir -p "$INSTALL_DIR/data"
chown -R "$RUN_USER:$RUN_USER" "$INSTALL_DIR"

# Пользователь сервиса должен уметь останавливать/запускать СВОЙ сервис:
# автообновлятель приложения делает systemctl stop/start при обновлении.
info "выдаю сервису права start/stop (polkit): $POLKIT_RULE"
cat > "$POLKIT_RULE" <<EOF
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
EOF
chmod 644 "$POLKIT_RULE"

# ---------------------------------------------------------------- systemd --

info "устанавливаю systemd-сервис: /etc/systemd/system/$SERVICE.service"
cat > "/etc/systemd/system/$SERVICE.service" <<EOF
[Unit]
Description=Bookmarks - self-hosted bookmark manager
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_USER
WorkingDirectory="$INSTALL_DIR"
Environment=BOOKMARKS_DATA="$INSTALL_DIR/data"
ExecStart="$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/app.py" --host $HOST_BIND --port $PORT
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# install.json — порт, который автообновлятель проверяет после обновления
printf '{"port": %s, "host": "%s"}\n' "$PORT" "$HOST_BIND" > "$INSTALL_DIR/install.json"
chown "$RUN_USER:$RUN_USER" "$INSTALL_DIR/install.json"

systemctl daemon-reload
systemctl enable "$SERVICE"
systemctl restart "$SERVICE"

# ----------------------------------------------------------------- проверка --

info "ожидание запуска сервера (до 90 с) …"
ok=""
for _ in $(seq 1 45); do
  if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$PORT/health', timeout=3)" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 2
done

# Если включён файрвол ufw — спросить про порт (только для внешнего доступа)
if [ "$HOST_BIND" = "0.0.0.0" ] && command -v ufw >/dev/null 2>&1; then
  if ufw status 2>/dev/null | head -n1 | grep -q "Status: active"; then
    if [ -t 0 ]; then
      answer=""
      read -r -p "[install] ufw активен. Разрешить входящий TCP-порт $PORT? [y/N]: " answer || answer=""
      case "$answer" in
        y|Y|yes|да) ufw allow "$PORT/tcp" ;;
      esac
    else
      info "ufw активен: разрешите порт вручную — sudo ufw allow $PORT/tcp"
    fi
  fi
fi

SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
[ -n "$SERVER_IP" ] || SERVER_IP="<IP-адрес сервера>"

if [ -z "$ok" ]; then
  err "сервер не ответил: http://127.0.0.1:$PORT/health"
  err "смотрите журнал: journalctl -u $SERVICE -n 50"
  exit 1
fi

echo
echo "  🔖  Bookmarks установлен и запущен!"
echo
if [ "$HOST_BIND" = "0.0.0.0" ]; then
  echo "  Адрес:      http://$SERVER_IP:$PORT"
else
  echo "  Адрес:      http://127.0.0.1:$PORT"
  echo "  (внутренний доступ: с самого сервера, либо через SSH-туннель:"
  echo "   ssh -L $PORT:localhost:$PORT <юзер>@<сервер>  и открыть http://127.0.0.1:$PORT)"
fi
echo "  Сервис:     systemctl status $SERVICE"
echo "  Журнал:     journalctl -u $SERVICE -f"
echo "  Данные:     $INSTALL_DIR/data"
echo "  Обновления: в приложении — «О программе» → «Проверить обновления»"
echo
