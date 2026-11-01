#!/usr/bin/env bash
# Установка и запуск Bookmarks на Ubuntu Server.
#
# Использование:
#   bash install.sh            — установка в venv + запуск в фоне (nohup), лог в data/server.log
#   bash install.sh systemd    — установка + systemd-сервис с автозапуском
#
# Настройки через переменные окружения:
#   PORT         порт (по умолчанию 8765)
#   HOST_BIND    адрес привязки (по умолчанию 0.0.0.0)
#   BOOKMARKS_DATA каталог данных (по умолчанию <корень>/data)

set -euo pipefail

MODE="${1:-foreground}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8765}"
HOST_BIND="${HOST_BIND:-0.0.0.0}"
DATA_DIR="${BOOKMARKS_DATA:-$ROOT/data}"
VENV_DIR="$ROOT/.venv"
SERVICE_NAME="bookmarks"

cd "$ROOT"

if ! command -v python3 >/dev/null 2>&1; then
    echo "[install] python3 не найден: sudo apt install -y python3 python3-venv"
    exit 1
fi

echo "[install] Создаю виртуальное окружение в $VENV_DIR"
python3 -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --upgrade pip >/dev/null
pip install -r requirements.txt
mkdir -p "$DATA_DIR"

run_cmd=(python app.py --host "$HOST_BIND" --port "$PORT" --data "$DATA_DIR")

case "$MODE" in
  systemd)
    UNIT="/etc/systemd/system/${SERVICE_NAME}.service"
    echo "[install] Создаю systemd-сервис $UNIT"
    if [ ! -w /etc/systemd/system ] && [ "$(id -u)" -ne 0 ]; then
        echo "[install] Нужны права root для systemd-режима: sudo bash install.sh systemd"
        exit 1
    fi
    cat > "$UNIT" <<EOF
[Unit]
Description=Bookmarks - self-hosted bookmark manager
After=network.target

[Service]
Type=simple
WorkingDirectory=$ROOT
Environment=BOOKMARKS_DATA=$DATA_DIR
ExecStart=$VENV_DIR/bin/python $ROOT/app.py --host $HOST_BIND --port $PORT --data $DATA_DIR
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable --now "$SERVICE_NAME"
    echo "[install] Готово: сервис $SERVICE_NAME запущен (systemctl status $SERVICE_NAME)"
    ;;
  foreground|*)
    echo "[install] Запускаю в фоне: ${run_cmd[*]}"
    nohup "${run_cmd[@]}" >> "$DATA_DIR/server.log" 2>&1 &
    sleep 1
    if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null; then
        echo "[install] Готово: http://$(hostname -I 2>/dev/null | awk '{print $1}'):${PORT} (лог: $DATA_DIR/server.log)"
    else
        echo "[install] Сервер ещё поднимается, смотрите $DATA_DIR/server.log"
    fi
    ;;
esac
