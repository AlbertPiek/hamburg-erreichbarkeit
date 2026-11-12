"""Vorverarbeitung: GTFS → kompakter Cache nur für S- und U-Bahn.

Aufruf:  python -m hvv.preprocess
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from .paths import (
    CACHE_DIR, GTFS_ZIP, SOURCE_JSON,
    STATIONS_JSON, EDGES_JSON, CONNECTIONS_NPZ, CALENDAR_JSON, META_JSON,
)

LINE_RE = re.compile(r"^(S|U)\d+$")

# Offizielle Linienfarben als Rückfall, falls route_color im Feed fehlt.
FALLBACK_COLORS = {
    "S1": "#1a962b", "S2": "#b51143", "S3": "#622181", "S5": "#0089bb",
    "S7": "#cc7720", "U1": "#006ab3", "U2": "#e2001a", "U3": "#ffdd00",
    "U4": "#0098a1",
}

# Fußweg-Umstiege zwischen getrennten Stationen (z. B. Hbf Nord ↔ Hbf Süd)
WALK_MAX_M = 400          # max. Luftlinie
WALK_SPEED_M_PER_MIN = 80  # ca. 4,8 km/h
WALK_DETOUR = 1.3          # Umweg-Faktor gegenüber Luftlinie
WALK_EXTRA_S = 60          # Treppen, Orientierung


def read(z: zipfile.ZipFile, name: str, **kw) -> pd.DataFrame:
    return pd.read_csv(z.open(name), dtype=str, encoding="utf-8", **kw)


def to_seconds(s: pd.Series) -> np.ndarray:
    parts = s.str.split(":", expand=True).astype(int)
    return (parts[0] * 3600 + parts[1] * 60 + parts[2]).to_numpy(np.int32)


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6_371_000 * 2 * np.arcsin(np.sqrt(a))


def place_of(stop_id: pd.Series) -> pd.Series:
    """IFOPT-Haltestelle (de:02000:10950) aus der Bahnsteig-ID (de:02000:10950:2:...)."""
    return stop_id.str.split(":").str[:3].str.join(":")


def main() -> int:
    if not GTFS_ZIP.exists():
        print("GTFS-ZIP fehlt. Zuerst:  python -m hvv.download")
        return 1
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    z = zipfile.ZipFile(GTFS_ZIP)

    # ---------- Linien ----------
    routes = read(z, "routes.txt")
    routes = routes[routes.route_short_name.str.match(LINE_RE, na=False)].copy()
    routes["line"] = routes.route_short_name
    colors = {}
    for line, grp in routes.groupby("line"):
        c = grp.route_color.dropna()
        colors[line] = ("#" + c.iloc[0].lower()) if len(c) else FALLBACK_COLORS.get(line, "#666666")
    print(f"Linien: {', '.join(sorted(colors))}")
    route_line = dict(zip(routes.route_id, routes.line))

    # ---------- Fahrten ----------
    trips = read(z, "trips.txt", usecols=["route_id", "service_id", "trip_id", "shape_id"])
    trips = trips[trips.route_id.isin(route_line)].copy()
    trips["line"] = trips.route_id.map(route_line)
    print(f"Fahrten: {len(trips):,}")

    # ---------- Haltezeiten (groß → in Chunks) ----------
    trip_ids = set(trips.trip_id)
    parts = []
    for ch in pd.read_csv(z.open("stop_times.txt"), dtype=str, chunksize=2_000_000,
                          usecols=["trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time"]):
        parts.append(ch[ch.trip_id.isin(trip_ids)])
    st = pd.concat(parts, ignore_index=True)
    st["stop_sequence"] = st.stop_sequence.astype(int)
    st = st.sort_values(["trip_id", "stop_sequence"], kind="stable").reset_index(drop=True)
    st["arr"] = to_seconds(st.arrival_time)
    st["dep"] = to_seconds(st.departure_time)
    st["place"] = place_of(st.stop_id)
    print(f"Haltezeiten: {len(st):,}")

    # ---------- Stationen ----------
    stops = read(z, "stops.txt", usecols=["stop_id", "stop_name", "stop_lat", "stop_lon"])
    stops = stops[stops.stop_id.isin(set(st.stop_id))].copy()
    stops["lat"] = stops.stop_lat.astype(float)
    stops["lon"] = stops.stop_lon.astype(float)
    stops["place"] = place_of(stops.stop_id)
    plat_coord = dict(zip(stops.stop_id, zip(stops.lat, stops.lon)))

    line_by_place = (st.merge(trips[["trip_id", "line"]], on="trip_id")
                       .groupby("place").line.agg(lambda x: sorted(set(x))))
    stations = []
    for i, (pl, grp) in enumerate(stops.groupby("place", sort=True)):
        name = re.sub(r"\s*\(\d+\)$", "", grp.stop_name.mode().iloc[0])
        stations.append({
            "id": i, "key": pl, "name": name,
            "lat": round(grp.lat.mean(), 6), "lon": round(grp.lon.mean(), 6),
            "lines": line_by_place.get(pl, []),
        })
    st_idx = {s["key"]: s["id"] for s in stations}
    print(f"Stationen: {len(stations)}")

    # Fußweg-Umstiege
    lat = np.array([s["lat"] for s in stations])
    lon = np.array([s["lon"] for s in stations])
    d = haversine_m(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    walks = []
    for a, b in zip(*np.where((d > 0) & (d <= WALK_MAX_M))):
        secs = int(d[a, b] * WALK_DETOUR / WALK_SPEED_M_PER_MIN * 60 + WALK_EXTRA_S)
        walks.append((int(a), int(b), secs))
    for s in stations:
        s["walk"] = [[b, t] for a, b, t in walks if a == s["id"]]
    print(f"Fußweg-Umstiege: {len(walks)}  (z. B. "
          + ", ".join(f"{stations[a]['name']}→{stations[b]['name']} {t // 60}:{t % 60:02d}"
                      for a, b, t in walks[:3]) + ")")

    # ---------- Verbindungen (Kante zwischen zwei aufeinanderfolgenden Halten) ----------
    nxt = st.shift(-1)
    same = (st.trip_id == nxt.trip_id) & (st.place != nxt.place)
    con = pd.DataFrame({
        "trip_id": st.trip_id[same],
        "from_stop": st.stop_id[same], "to_stop": nxt.stop_id[same],
        "from": st.place[same].map(st_idx), "to": nxt.place[same].map(st_idx),
        "dep": st.dep[same], "arr": nxt.arr[same].astype(np.int32),
        "seq": st.stop_sequence[same],
    })
    con = con.merge(trips[["trip_id", "line", "service_id", "shape_id"]], on="trip_id")

    # Anzeige-Kanten: ungerichtet je Linie
    con["a"] = con[["from", "to"]].min(axis=1)
    con["b"] = con[["from", "to"]].max(axis=1)
    edge_keys = con[["line", "a", "b"]].drop_duplicates().sort_values(["line", "a", "b"]).reset_index(drop=True)
    edge_keys["edge"] = np.arange(len(edge_keys))
    con = con.merge(edge_keys, on=["line", "a", "b"])
    print(f"Verbindungen: {len(con):,}   Anzeige-Kanten: {len(edge_keys)}")

    # ---------- Geometrie aus shapes.txt ----------
    geoms = build_geometries(z, con, plat_coord, stations)

    lines_sorted = sorted(colors)
    edges = []
    for row in edge_keys.itertuples():
        g = geoms.get(row.edge)
        if g is None:
            sa, sb = stations[row.a], stations[row.b]
            g = [[sa["lat"], sa["lon"]], [sb["lat"], sb["lon"]]]
        edges.append({"id": int(row.edge), "line": row.line, "color": colors[row.line],
                      "a": int(row.a), "b": int(row.b), "coords": g})

    # ---------- Kalender ----------
    services = sorted(con.service_id.unique())
    svc_idx = {s: i for i, s in enumerate(services)}
    active = service_dates(z, set(services))
    cal = {d: sorted(svc_idx[s] for s in svcs) for d, svcs in sorted(active.items())}

    # ---------- Speichern ----------
    trip_codes, trip_uni = pd.factorize(con.trip_id)
    order = np.lexsort((con.seq.to_numpy(), con.arr.to_numpy(), con.dep.to_numpy()))
    np.savez_compressed(
        CONNECTIONS_NPZ,
        dep=con.dep.to_numpy(np.int32)[order],
        arr=con.arr.to_numpy(np.int32)[order],
        frm=con["from"].to_numpy(np.int16)[order],
        to=con["to"].to_numpy(np.int16)[order],
        trip=trip_codes.astype(np.int32)[order],
        service=con.service_id.map(svc_idx).to_numpy(np.int32)[order],
        edge=con.edge.to_numpy(np.int32)[order],
        line=pd.Categorical(con.line, categories=lines_sorted).codes.astype(np.int8)[order],
    )
    STATIONS_JSON.write_text(json.dumps(stations, ensure_ascii=False), encoding="utf-8")
    EDGES_JSON.write_text(json.dumps(edges, ensure_ascii=False), encoding="utf-8")
    CALENDAR_JSON.write_text(json.dumps(cal), encoding="utf-8")

    feed = read(z, "feed_info.txt").iloc[0]
    source = json.loads(SOURCE_JSON.read_text(encoding="utf-8")) if SOURCE_JSON.exists() else {}
    meta = {
        "lines": lines_sorted, "colors": colors,
        "feed_start": iso(feed.feed_start_date), "feed_end": iso(feed.feed_end_date),
        "feed_version": feed.feed_version, "source": source,
        "built": datetime.now().isoformat(timespec="seconds"),
    }
    META_JSON.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Feed gültig {meta['feed_start']} – {meta['feed_end']}")
    print(f"✓ Cache geschrieben nach {CACHE_DIR}")

    from . import export_web
    if export_web.main() != 0:
        return 1
    print("Weiter mit:  python -m hvv.app   (oder web/ hochladen, siehe README)")
    return 0


def iso(yyyymmdd: str) -> str:
    s = str(yyyymmdd)
    return f"{s[:4]}-{s[4:6]}-{s[6:]}"


def service_dates(z, wanted: set[str]) -> dict[str, set[str]]:
    """Datum (YYYY-MM-DD) → aktive service_ids (nur die gewünschten)."""
    active: dict[str, set[str]] = {}
    cal = read(z, "calendar.txt")
    cal = cal[cal.service_id.isin(wanted)]
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for r in cal.itertuples():
        d0 = datetime.strptime(r.start_date, "%Y%m%d").date()
        d1 = datetime.strptime(r.end_date, "%Y%m%d").date()
        flags = [getattr(r, x) == "1" for x in days]
        d = d0
        while d <= d1:
            if flags[d.weekday()]:
                active.setdefault(d.isoformat(), set()).add(r.service_id)
            d += timedelta(days=1)
    cd = read(z, "calendar_dates.txt")
    cd = cd[cd.service_id.isin(wanted)]
    for r in cd.itertuples():
        d = iso(r.date)
        if r.exception_type == "1":
            active.setdefault(d, set()).add(r.service_id)
        else:
            active.get(d, set()).discard(r.service_id)
    return active


def build_geometries(z, con: pd.DataFrame, plat_coord, stations) -> dict[int, list]:
    """Schneidet für jede Anzeige-Kante ein Stück aus einer passenden Shape."""
    con = con[con.shape_id.notna()]
    # je Kante eine repräsentative Fahrt
    rep = con.drop_duplicates("edge")[["edge", "trip_id", "shape_id", "from_stop", "to_stop"]]
    shape_ids = set(rep.shape_id)
    parts = []
    for ch in pd.read_csv(z.open("shapes.txt"), chunksize=3_000_000,
                          dtype={"shape_id": str}):
        parts.append(ch[ch.shape_id.isin(shape_ids)])
    sh = pd.concat(parts).sort_values(["shape_id", "shape_pt_sequence"])
    shapes = {sid: g[["shape_pt_lat", "shape_pt_lon"]].to_numpy()
              for sid, g in sh.groupby("shape_id")}

    geoms = {}
    for r in rep.itertuples():
        pts = shapes.get(r.shape_id)
        if pts is None or r.from_stop not in plat_coord or r.to_stop not in plat_coord:
            continue
        ia = nearest(pts, plat_coord[r.from_stop])
        ib = nearest(pts, plat_coord[r.to_stop], start=ia)
        if ib - ia < 1:
            continue
        seg = pts[ia:ib + 1]
        seg = simplify(seg)
        geoms[int(r.edge)] = [[round(float(a), 5), round(float(b), 5)] for a, b in seg]
    return geoms


def nearest(pts: np.ndarray, latlon, start: int = 0) -> int:
    lat, lon = latlon
    sub = pts[start:]
    d = (sub[:, 0] - lat) ** 2 + ((sub[:, 1] - lon) * 0.6) ** 2
    return start + int(np.argmin(d))


def simplify(seg: np.ndarray, min_deg: float = 0.00015) -> np.ndarray:
    """Entfernt sehr dicht liegende Punkte (≈ 10 m), Endpunkte bleiben."""
    if len(seg) <= 2:
        return seg
    keep = [0]
    for i in range(1, len(seg) - 1):
        if np.abs(seg[i] - seg[keep[-1]]).max() >= min_deg:
            keep.append(i)
    keep.append(len(seg) - 1)
    return seg[keep]


if __name__ == "__main__":
    sys.exit(main())
