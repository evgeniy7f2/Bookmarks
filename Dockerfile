FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Etc/UTC

WORKDIR /app

# tzdata — чтобы переменная TZ применялась (системные логи).
# В самом приложении время хранится в UTC, интерфейс показывает время браузера.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# Только файлы рантайма (build_min.py — инструмент сборки).
# update.py — автообновлятор: «Проверить обновления» в «О Программе»
# импортирует его из корня установки, поэтому файл должен быть в образе.
COPY app.py ./
COPY manage.py ./
COPY backup.sh ./
COPY update.py ./
COPY update/ ./update/
COPY bookmarks/ ./bookmarks/

# Данные (SQLite, кэш фавиконок, secret.key) живут в томе.
# Каталог создаётся в образе и принадлежит не-root пользователю:
# именованный том Docker инициализирует этими правами при первом запуске.
RUN useradd -m -u 10001 bookmarks \
    && mkdir -p /data \
    && chown bookmarks:bookmarks /data
VOLUME ["/data"]
ENV BOOKMARKS_DATA=/data

USER bookmarks

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=3).status==200 else 1)"

CMD ["python", "app.py", "--host", "0.0.0.0", "--port", "8765"]
