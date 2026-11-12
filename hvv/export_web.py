"""Exportiert den Cache als statische Dateien für die Web-App (PWA) nach web/data/.

Aufruf:  python -m hvv.export_web     (läuft auch automatisch am Ende von preprocess)

Dateien:
  network.json     Stationen, Kanten, Grenzen, Metadaten
  calendar.json    Datum → aktive Service-Indizes
  connections.dat  gzip-komprimiert, spaltenweise Binärdaten (siehe unten)

Layout von connections.dat (entpackt, Little Endian):
  uint32  N
  uint16[N]  dep_delta   Abfahrt in s, Differenz zur vorherigen Zeile (sortiert)
  uint16[N]  duration    Fahrzeit in s
  uint16[N]  trip
  uint16[N]  edge        Anzeige-Kante (enthält die Linie)
  uint8[N]   from        Station
  uint8[N]   to          Station
  uint8[N]   service
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sys

import numpy as np

from .paths import (
    STATIONS_JSON, EDGES_JSON, CONNECTIONS_NPZ, CALENDAR_JSON, META_JSON,
    GRENZE_GEOJSON, BEZIRKE_GEOJSON, WEB_DATA_DIR,
)

FORMAT_VERSION = 1


def _ring_simplify(ring, min_deg=0.0002):
    out = [ring[0]]
    for p in ring[1:-1]:
        if abs(p[0] - out[-1][0]) >= min_deg or abs(p[1] - out[-1][1]) >= min_deg:
            out.append(p)
    out.append(ring[-1])
    if len(out) < 4:
        return None
    return [[round(x, 5), round(y, 5)] for x, y in out]


def _simplify_geom(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    new = []
    for poly in polys:
        rings = [r for r in (_ring_simplify(r) for r in poly) if r]
        if rings:
            new.append(rings)
    return {"type": "MultiPolygon", "coordinates": new}


def _label_point(geom):
    """Schwerpunkt des flächengrößten Außenrings → [lat, lon] (Neuwerk zählt nicht)."""
    best, best_area = None, 0.0
    for poly in geom["coordinates"]:
        ring = poly[0]
        a = cx = cy = 0.0
        for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
            f = x0 * y1 - x1 * y0
            a += f
            cx += (x0 + x1) * f
            cy += (y0 + y1) * f
        if a and abs(a) > best_area:
            best_area = abs(a)
            best = [round(cy / (3 * a), 5), round(cx / (3 * a), 5)]
    return best


def _boundaries(path, keep_props):
    if not path.exists():
        return None
    fc = json.loads(path.read_text(encoding="utf-8"))
    feats = []
    for f in fc["features"]:
        g = _simplify_geom(f["geometry"])
        props = {k: f["properties"].get(k) for k in keep_props}
        props["label"] = _label_point(g)
        feats.append({"type": "Feature", "properties": props, "geometry": g})
    return {"type": "FeatureCollection", "features": feats}


def main() -> int:
    rd = lambda p: json.loads(p.read_text(encoding="utf-8"))
    stations = rd(STATIONS_JSON)
    edges = rd(EDGES_JSON)
    meta = rd(META_JSON)
    c = np.load(CONNECTIONS_NPZ)

    n = len(c["dep"])
    dep = c["dep"].astype(np.int64)
    dep_delta = np.diff(dep, prepend=0)
    dur = c["arr"].astype(np.int64) - dep
    checks = {
        "dep sortiert": (dep_delta >= 0).all(),
        "dep_delta < 65536": dep_delta.max() < 65536,
        "Fahrzeit < 65536": (dur >= 0).all() and dur.max() < 65536,
        "trip < 65536": c["trip"].max() < 65536,
        "edge < 65536": c["edge"].max() < 65536,
        "Stationen < 256": len(stations) < 256,
        "Services < 256": c["service"].max() < 256,
    }
    bad = [k for k, ok in checks.items() if not ok]
    if bad:
        print("Export nicht möglich, Wertebereich überschritten: " + ", ".join(bad))
        return 1

    blob = b"".join([
        np.array([n], dtype="<u4").tobytes(),
        dep_delta.astype("<u2").tobytes(),
        dur.astype("<u2").tobytes(),
        c["trip"].astype("<u2").tobytes(),
        c["edge"].astype("<u2").tobytes(),
        c["frm"].astype("u1").tobytes(),
        c["to"].astype("u1").tobytes(),
        c["service"].astype("u1").tobytes(),
    ])

    network = {
        "format": FORMAT_VERSION,
        "stations": [{k: s[k] for k in ("id", "name", "lat", "lon", "lines", "walk")} for s in stations],
        "edges": edges,
        "grenze": _boundaries(GRENZE_GEOJSON, []),
        "bezirke": _boundaries(BEZIRKE_GEOJSON, ["bezirk_name"]),
        "meta": {k: meta.get(k) for k in ("lines", "colors", "feed_start", "feed_end", "feed_version", "source", "built")},
    }

    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    (WEB_DATA_DIR / "network.json").write_text(
        json.dumps(network, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (WEB_DATA_DIR / "calendar.json").write_text(
        CALENDAR_JSON.read_text(encoding="utf-8"), encoding="utf-8")
    conn_gz = gzip.compress(blob, compresslevel=9, mtime=0)
    (WEB_DATA_DIR / "connections.dat").write_bytes(conn_gz)

    # Version = Hash über alle Datendateien → Browser lädt nur zusammenpassende Sätze.
    h = hashlib.sha256()
    for name in ("network.json", "calendar.json", "connections.dat"):
        h.update((WEB_DATA_DIR / name).read_bytes())
    version = h.hexdigest()[:12]
    (WEB_DATA_DIR / "version.json").write_text(
        json.dumps({"version": version, "feed_start": meta.get("feed_start"),
                    "feed_end": meta.get("feed_end")}), encoding="utf-8")

    for f in sorted(WEB_DATA_DIR.iterdir()):
        print(f"  {f.name:18s} {f.stat().st_size / 1024:8.0f} KB")
    print(f"✓ Web-Daten exportiert nach {WEB_DATA_DIR}  ({n:,} Verbindungen)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
