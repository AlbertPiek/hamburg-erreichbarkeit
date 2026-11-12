"""Lokaler Server für die Web-App (web/) – Grundlage für Browser- und Desktop-Variante.

Die Berechnung läuft im Browser (web/engine.js). Zusätzlich gibt es /api/reachable
(Python-Implementierung) für Skripte und Tests.

Aufruf:  python -m hvv.app [--port 5000] [--host 0.0.0.0]
"""
from __future__ import annotations

import argparse
import re
from datetime import date

from flask import Flask, abort, jsonify, request, send_from_directory

from .paths import WEB_DIR, WEB_DATA_DIR

app = Flask(__name__, static_folder=None)
_NET = None


def web_data_ok() -> bool:
    return all((WEB_DATA_DIR / f).exists() for f in ("network.json", "calendar.json", "connections.dat"))


@app.after_request
def no_cache_for_shell(resp):
    # Entwicklung/Desktop: App-Dateien nie veralten lassen; versionierte Daten dürfen gecacht werden.
    if request.path.startswith("/data/") and request.args.get("v"):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/data/<path:name>")
def data(name):
    return send_from_directory(WEB_DATA_DIR, name)


@app.get("/<path:name>")
def web_file(name):
    if name.startswith("data/"):
        abort(404)
    return send_from_directory(WEB_DIR, name)


TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


@app.get("/api/reachable")
def api_reachable():
    global _NET
    from .network import Network          # numpy nur bei Bedarf laden
    from .reachability import scan
    if _NET is None:
        _NET = Network.load()
    n = _NET
    try:
        if not request.args.get("station", "").isdigit():
            raise ValueError("Parameter 'station' fehlt oder ist ungültig")
        station = int(request.args["station"])
        day = date.fromisoformat(request.args.get("date", date.today().isoformat())).isoformat()
        m = TIME_RE.match(request.args.get("time", ""))
        if not m:
            raise ValueError("Uhrzeit im Format HH:MM angeben")
        t0 = int(m.group(1)) * 3600 + int(m.group(2)) * 60
        budget = int(request.args.get("budget", 30))
        if not 0 <= station < len(n.stations):
            raise ValueError("Unbekannte Station")
        if not 1 <= budget <= 180:
            raise ValueError("Zeitbudget muss zwischen 1 und 180 Minuten liegen")
    except (KeyError, ValueError) as e:
        return jsonify({"error": str(e)}), 400

    budget_s = budget * 60
    window = n.connections_window(day, t0, t0 + budget_s)
    reached, edges = scan(window, len(n.stations), station, t0, budget_s, n.walk, n.meta["lines"])

    def hhmm(sec: int) -> str:
        sec %= 86_400
        return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}"

    return jsonify({
        "station": station, "date": day, "time": hhmm(t0), "budget": budget,
        "reached": [{"id": r.station, "name": n.stations[r.station]["name"],
                     "arrival": hhmm(r.arrival), "minutes": r.minutes, "via": r.via}
                    for r in reached],
        "edges": sorted(edges),
    })


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1",
                    help="0.0.0.0, um vom Handy im selben WLAN zuzugreifen")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args(argv)
    if not web_data_ok():
        raise SystemExit("web/data fehlt. Bitte zuerst  python -m hvv.download  und  python -m hvv.preprocess")
    print(f"HVV-Erreichbarkeit läuft auf http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
