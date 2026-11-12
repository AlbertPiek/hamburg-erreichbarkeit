"""Desktop-Version: startet den Server im Hintergrund und öffnet die Karte in einem eigenen Fenster.

Aufruf:  python -m hvv.desktop      (oder die gebaute HVV-Erreichbarkeit.exe)
"""
from __future__ import annotations

import socket
import sys
import threading
import traceback

import webview
from werkzeug.serving import make_server

from .app import app, web_data_ok
from .paths import WEB_DATA_DIR


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def show_error(msg: str) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "HVV-Erreichbarkeit", 0x10)
    except Exception:
        print(msg, file=sys.stderr)


def main() -> int:
    if not web_data_ok():
        show_error(f"Fahrplandaten fehlen in:\n{WEB_DATA_DIR}")
        return 1

    port = free_port()
    server = make_server("127.0.0.1", port, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    webview.create_window(
        "HVV-Erreichbarkeit – S- & U-Bahn Hamburg",
        f"http://127.0.0.1:{port}/",
        width=1400, height=900, min_size=(800, 560),
    )
    try:
        webview.start()
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        show_error("Unerwarteter Fehler:\n\n" + traceback.format_exc())
        sys.exit(1)
