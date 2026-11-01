#!/usr/bin/env python3
"""Bookmarks 🔖 - a tiny self-hosted bookmark manager.

Run:  python app.py --port 8765
Open: http://<this-machine-ip>:8765
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import webbrowser

from bookmarks import create_app
from bookmarks.util import APP_VERSION


def _local_addresses() -> list[str]:
    addresses: set[str] = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            addresses.add(info[4][0])
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            addresses.add(probe.getsockname()[0])
    except OSError:
        pass
    return sorted(address for address in addresses if not address.startswith("127."))


def _serve(app, host: str, port: int, debug: bool) -> None:
    """Run the app on a real WSGI server unless debug mode is requested."""
    if debug:
        app.run(host=host, port=port, debug=True, threaded=True, use_reloader=True)
        return
    try:
        from waitress import serve
    except ImportError:
        print(
            "  waitress не установлен — используется встроенный сервер Flask\n"
            "  (это медленно и не предназначено для работы вне разработки).\n"
            "  Установите зависимости: pip install -r requirements.txt",
            file=sys.stderr,
        )
        app.run(host=host, port=port, threaded=True)
        return
    serve(app, host=host, port=port, threads=8, channel_timeout=30)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bookmarks - self-hosted bookmark manager with a web UI."
    )
    parser.add_argument("--host", default="0.0.0.0", help="bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765, help="port (default: 8765)")
    parser.add_argument("--data", help="data directory (default: ./data)")
    parser.add_argument("--debug", action="store_true", help="enable Flask debug mode")
    parser.add_argument("--open", action="store_true", help="open the browser on start")
    parser.add_argument("--version", action="version", version=f"Bookmarks {APP_VERSION}")
    args = parser.parse_args()

    if args.data:
        os.environ["BOOKMARKS_DATA"] = os.path.abspath(args.data)

    app = create_app()
    scheme = "http"
    local_url = f"{scheme}://127.0.0.1:{args.port}"
    print()
    print(f"  🔖  Bookmarks v{APP_VERSION}")
    print(f"  ─────────────────────────────────────────────")
    print(f"  Локально:   {local_url}")
    for address in _local_addresses():
        print(f"  В сети:     {scheme}://{address}:{args.port}")
    print(f"  Данные:     {app.config['DATA_DIR']}")
    print(f"  Остановка:  Ctrl+C")
    print()

    if args.open:
        webbrowser.open(local_url)

    try:
        _serve(app, args.host, args.port, args.debug)
    except OSError as exc:
        print(f"\n  Не удалось запустить сервер: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
