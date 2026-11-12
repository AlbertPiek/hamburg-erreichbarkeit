"""Prüft, dass web/engine.js exakt dieselben Ergebnisse liefert wie die Python-Implementierung."""
import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from hvv.network import Network
from hvv.paths import WEB_DATA_DIR, META_JSON
from hvv.reachability import scan

ROOT = Path(__file__).resolve().parent.parent

pytestmark = [
    pytest.mark.skipif(shutil.which("node") is None, reason="Node.js nicht installiert"),
    pytest.mark.skipif(not (WEB_DATA_DIR / "connections.dat").exists() or not META_JSON.exists(),
                       reason="Daten fehlen (preprocess ausführen)"),
]


def test_js_matches_python():
    net = Network.load()
    rnd = random.Random(42)
    days = sorted(net.calendar)
    queries = [
        {"station": rnd.randrange(len(net.stations)), "date": rnd.choice(days),
         "t0": rnd.randrange(0, 24 * 3600, 60), "budget": rnd.choice([10, 30, 60]) * 60}
        for _ in range(60)
    ]
    # gezielte Randfälle: nach Mitternacht, spät abends, Feedgrenzen
    queries += [
        {"station": 0, "date": days[1], "t0": 20 * 60, "budget": 1800},
        {"station": 10, "date": days[-1], "t0": 23 * 3600 + 50 * 60, "budget": 1800},
        {"station": 50, "date": days[0], "t0": 5 * 3600, "budget": 3600},
    ]

    expected = []
    for q in queries:
        w = net.connections_window(q["date"], q["t0"], q["t0"] + q["budget"])
        reached, edges = scan(w, len(net.stations), q["station"], q["t0"], q["budget"],
                              net.walk, net.meta["lines"])
        expected.append({
            "reached": sorted([r.station, r.arrival, r.via] for r in reached),
            "edges": sorted(edges),
        })

    proc = subprocess.run(["node", str(ROOT / "tests" / "js_reach.cjs")], input=json.dumps(queries),
                          capture_output=True, text=True, encoding="utf-8", check=True)
    got = json.loads(proc.stdout)

    for q, e, g in zip(queries, expected, got):
        assert sorted(g["reached"]) == e["reached"], q
        assert g["edges"] == e["edges"], q
