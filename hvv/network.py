"""Lädt den vorverarbeiteten Cache in den Speicher."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache

import numpy as np

from .paths import (
    STATIONS_JSON, EDGES_JSON, CONNECTIONS_NPZ, CALENDAR_JSON, META_JSON,
    GRENZE_GEOJSON, BEZIRKE_GEOJSON,
)

DAY = 86_400


@dataclass
class Network:
    stations: list[dict]
    edges: list[dict]
    meta: dict
    calendar: dict[str, list[int]]           # Datum → aktive Service-Indizes
    conn: dict[str, np.ndarray]              # Spalten der Verbindungen (sortiert nach dep)
    n_services: int
    grenze: dict | None = None
    bezirke: dict | None = None
    walk: list[list[tuple[int, int]]] = field(default_factory=list)

    @classmethod
    def load(cls) -> "Network":
        missing = [p for p in (STATIONS_JSON, EDGES_JSON, CONNECTIONS_NPZ, CALENDAR_JSON, META_JSON)
                   if not p.exists()]
        if missing:
            raise FileNotFoundError(
                "Cache fehlt (" + ", ".join(p.name for p in missing) + "). "
                "Bitte zuerst  python -m hvv.download  und  python -m hvv.preprocess  ausführen.")
        rd = lambda p: json.loads(p.read_text(encoding="utf-8"))
        npz = np.load(CONNECTIONS_NPZ)
        conn = {k: npz[k] for k in npz.files}
        stations = rd(STATIONS_JSON)
        net = cls(
            stations=stations,
            edges=rd(EDGES_JSON),
            meta=rd(META_JSON),
            calendar=rd(CALENDAR_JSON),
            conn=conn,
            n_services=int(conn["service"].max()) + 1 if len(conn["service"]) else 0,
            grenze=rd(GRENZE_GEOJSON) if GRENZE_GEOJSON.exists() else None,
            bezirke=rd(BEZIRKE_GEOJSON) if BEZIRKE_GEOJSON.exists() else None,
            walk=[[(b, t) for b, t in s["walk"]] for s in stations],
        )
        return net

    def service_mask(self, day: str) -> np.ndarray:
        return _mask(tuple(self.calendar.get(day, ())), self.n_services)

    def connections_window(self, day: str, t0: int, t1: int) -> dict[str, np.ndarray]:
        """Alle Verbindungen mit Abfahrt in [t0, t1] (Sekunden ab Mitternacht des Tages `day`).

        Berücksichtigt Fahrten des Vortags mit GTFS-Zeiten ≥ 24:00 und Fahrten des
        Folgetags, falls das Fenster über Mitternacht hinausgeht.
        """
        d = date.fromisoformat(day)
        dep = self.conn["dep"]
        chunks = []
        for offset_days in (-1, 0, 1):
            shift = offset_days * DAY               # Zeit im Feed des Servicetags = t - shift
            lo, hi = t0 - shift, t1 - shift
            if hi < 0:
                continue
            i0, i1 = np.searchsorted(dep, lo, "left"), np.searchsorted(dep, hi, "right")
            if i0 >= i1:
                continue
            sday = (d + timedelta(days=offset_days)).isoformat()
            sl = slice(i0, i1)
            keep = self.service_mask(sday)[self.conn["service"][sl]]
            if not keep.any():
                continue
            part = {k: v[sl][keep] for k, v in self.conn.items()}
            part["dep"] = part["dep"] + shift
            part["arr"] = part["arr"] + shift
            # Fahrt-IDs je Servicetag eindeutig machen
            part["trip"] = part["trip"].astype(np.int64) * 3 + (offset_days + 1)
            chunks.append(part)
        if not chunks:
            return {k: v[:0] for k, v in self.conn.items()}
        out = {k: np.concatenate([c[k] for c in chunks]) for k in chunks[0]}
        order = np.lexsort((out["arr"], out["dep"]))
        return {k: v[order] for k, v in out.items()}


@lru_cache(maxsize=32)
def _mask(active: tuple[int, ...], n: int) -> np.ndarray:
    m = np.zeros(max(n, 1), dtype=bool)
    if active:
        m[list(active)] = True
    return m
