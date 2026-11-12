import numpy as np

from hvv.network import Network, DAY
from hvv.reachability import scan

H = 3600
M = 60
LINES = ["S1", "U1"]


def make_conn(rows):
    """rows: (dep, arr, frm, to, trip, edge, line)"""
    rows = sorted(rows, key=lambda r: (r[0], r[1]))
    cols = ["dep", "arr", "frm", "to", "trip", "edge", "line"]
    return {c: np.array([r[i] for r in rows], dtype=np.int64) for i, c in enumerate(cols)}


NO_WALK = [[] for _ in range(6)]


def by_station(reached):
    return {r.station: r for r in reached}


def test_same_trip_and_budget_limit():
    # Fahrt 0: 0 → 1 → 2 → 3, je 10 Minuten
    conn = make_conn([
        (8 * H + 2 * M, 8 * H + 12 * M, 0, 1, 0, 0, 0),
        (8 * H + 12 * M, 8 * H + 22 * M, 1, 2, 0, 1, 0),
        (8 * H + 22 * M, 8 * H + 32 * M, 2, 3, 0, 2, 0),
    ])
    reached, edges = scan(conn, 6, 0, 8 * H, 30 * M, NO_WALK, LINES)
    r = by_station(reached)
    assert set(r) == {0, 1, 2}           # Station 3 erst nach 32 min
    assert r[2].minutes == 22
    assert edges == {0, 1}


def test_transfer_time_respected():
    # Ankunft an 1 um 8:10; Anschluss A fährt 8:11 (zu knapp), Anschluss B 8:12 (ok)
    conn = make_conn([
        (8 * H, 8 * H + 10 * M, 0, 1, 0, 0, 0),
        (8 * H + 11 * M, 8 * H + 15 * M, 1, 2, 1, 1, 1),
        (8 * H + 12 * M, 8 * H + 20 * M, 1, 3, 2, 2, 1),
    ])
    r = by_station(scan(conn, 6, 0, 8 * H, 30 * M, NO_WALK, LINES)[0])
    assert 2 not in r
    assert r[3].minutes == 20 and r[3].via == "U1"


def test_missed_departure_before_start():
    conn = make_conn([(7 * H + 59 * M, 8 * H + 5 * M, 0, 1, 0, 0, 0)])
    reached, _ = scan(conn, 6, 0, 8 * H, 30 * M, NO_WALK, LINES)
    assert [x.station for x in reached] == [0]


def test_walk_transfer():
    walk = [[] for _ in range(6)]
    walk[1] = [(4, 3 * M)]
    walk[4] = [(1, 3 * M)]
    conn = make_conn([
        (8 * H, 8 * H + 10 * M, 0, 1, 0, 0, 0),
        (8 * H + 14 * M, 8 * H + 20 * M, 4, 5, 1, 1, 1),
    ])
    r = by_station(scan(conn, 6, 0, 8 * H, 30 * M, walk, LINES)[0])
    assert r[4].via == "Fußweg" and r[4].minutes == 13
    assert r[5].minutes == 20


def _fake_network(conn, calendar):
    return Network(stations=[{}] * 6, edges=[], meta={}, calendar=calendar, conn=conn,
                   n_services=2, walk=NO_WALK)


def test_after_midnight_uses_previous_service_day():
    # Fahrt des Servicetags 01.11. mit GTFS-Zeit 24:20 → am 02.11. um 00:20
    conn = make_conn([(24 * H + 20 * M, 24 * H + 30 * M, 0, 1, 0, 0, 0)])
    conn["service"] = np.array([0])
    net = _fake_network(conn, {"2026-11-01": [0]})
    window = net.connections_window("2026-11-02", 10 * M, 40 * M)
    assert list(window["dep"]) == [20 * M]
    r = by_station(scan(window, 6, 0, 10 * M, 30 * M, NO_WALK, LINES)[0])
    assert r[1].minutes == 20


def test_inactive_service_filtered():
    conn = make_conn([(8 * H, 8 * H + 5 * M, 0, 1, 0, 0, 0)])
    conn["service"] = np.array([1])
    net = _fake_network(conn, {"2026-11-02": [0]})
    assert len(net.connections_window("2026-11-02", 8 * H, 9 * H)["dep"]) == 0
