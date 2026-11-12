"""Erreichbarkeit per Connection Scan Algorithm (CSA)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

INF = 1 << 30
TRANSFER_S = 120   # Umstieg innerhalb einer Station (anderer Zug)


@dataclass
class Reached:
    station: int
    arrival: int          # Sekunden ab Mitternacht des Abfragetags
    minutes: float
    via: str              # "start" | Linie | "Fußweg"


def scan(conn: dict[str, np.ndarray], n_stations: int, start: int, t0: int, budget_s: int,
         walk: list[list[tuple[int, int]]], lines: list[str],
         transfer_s: int = TRANSFER_S):
    """Früheste Ankunft je Station ab `start` zur Zeit `t0` innerhalb von `budget_s`.

    `conn` muss nach Abfahrt sortiert sein (Spalten dep, arr, frm, to, trip, edge, line).
    Rückgabe: (Liste Reached, Menge genutzter Kanten-IDs)
    """
    limit = t0 + budget_s
    arr = [INF] * n_stations      # tatsächliche Ankunft
    ready = [INF] * n_stations    # frühester Zeitpunkt, um in einen *anderen* Zug zu steigen
    via = [""] * n_stations
    arr[start] = ready[start] = t0
    via[start] = "start"

    def relax_walk(s: int, t_at: int):
        for b, w in walk[s]:
            ta = t_at + w
            if ta < arr[b] and ta <= limit:
                arr[b] = ta
                via[b] = "Fußweg"
                if ta < ready[b]:
                    ready[b] = ta
    relax_walk(start, t0)

    on_trip: set[int] = set()
    used_edges: set[int] = set()

    dep_a, arr_a = conn["dep"], conn["arr"]
    frm_a, to_a = conn["frm"], conn["to"]
    trip_a, edge_a, line_a = conn["trip"], conn["edge"], conn["line"]

    for i in range(len(dep_a)):
        d = int(dep_a[i])
        if d > limit:
            break
        a = int(arr_a[i])
        if a > limit:
            continue
        tr = int(trip_a[i])
        f = int(frm_a[i])
        if tr not in on_trip:
            if ready[f] > d:
                continue
            on_trip.add(tr)
        used_edges.add(int(edge_a[i]))
        t = int(to_a[i])
        if a < arr[t]:
            arr[t] = a
            via[t] = lines[int(line_a[i])]
            nr = a + transfer_s
            if nr < ready[t]:
                ready[t] = nr
            relax_walk(t, a)

    reached = [Reached(s, arr[s], round((arr[s] - t0) / 60, 1), via[s])
               for s in range(n_stations) if arr[s] <= limit]
    reached.sort(key=lambda r: r.arrival)
    return reached, used_edges
