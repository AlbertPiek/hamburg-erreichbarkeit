/* Erreichbarkeits-Engine (Connection Scan Algorithm) – läuft komplett im Browser.
 * Entspricht hvv/network.py + hvv/reachability.py.
 * Funktioniert im Browser (window.HvvEngine) und in Node (module.exports) für Tests.
 */
(function (root) {
  "use strict";

  const DAY = 86400;
  const TRANSFER_S = 120;   // Umstieg innerhalb einer Station

  // ---------- Laden ----------
  async function gunzipIfNeeded(buf) {
    const u8 = new Uint8Array(buf);
    if (u8[0] !== 0x1f || u8[1] !== 0x8b) return buf;     // Server hat schon entpackt
    const ds = new DecompressionStream("gzip");
    const stream = new Blob([u8]).stream().pipeThrough(ds);
    return await new Response(stream).arrayBuffer();
  }

  function decodeConnections(buf, edges) {
    const n = new DataView(buf).getUint32(0, true);
    let off = 4;
    const u16 = () => { const a = new Uint16Array(buf, off, n); off += 2 * n; return a; };
    const u8 = () => { const a = new Uint8Array(buf, off, n); off += n; return a; };
    const depDelta = u16(), dur = u16(), trip = u16(), edge = u16();
    const frm = u8(), to = u8(), service = u8();
    const dep = new Int32Array(n), arr = new Int32Array(n), line = new Uint8Array(n);
    const lineIdx = edges.map((e) => e.lineIdx);
    let t = 0;
    for (let i = 0; i < n; i++) {
      t += depDelta[i];
      dep[i] = t;
      arr[i] = t + dur[i];
      line[i] = lineIdx[edge[i]];
    }
    return { n, dep, arr, frm, to, trip, edge, service, line };
  }

  class Engine {
    constructor(network, calendar, conn) {
      this.network = network;
      this.stations = network.stations;
      this.edges = network.edges;
      this.lines = network.meta.lines;
      this.calendar = calendar;
      this.conn = conn;
      this.walk = this.stations.map((s) => s.walk || []);
      let maxSvc = 0;
      for (let i = 0; i < conn.n; i++) if (conn.service[i] > maxSvc) maxSvc = conn.service[i];
      this.nServices = maxSvc + 1;
      this._masks = new Map();
    }

    static prepare(network) {
      const li = Object.fromEntries(network.meta.lines.map((l, i) => [l, i]));
      network.edges.forEach((e) => { e.lineIdx = li[e.line]; });
      return network;
    }

    static async load(base = "data/") {
      // version.json bestimmt, welcher zusammengehörige Datensatz geladen wird (Cache-Busting).
      let v = "";
      try {
        const r = await fetch(base + "version.json", { cache: "no-store" });
        if (r.ok) v = "?v=" + encodeURIComponent((await r.json()).version);
      } catch (e) { /* offline ohne Cache: ohne Version weiter */ }
      const get = async (f, kind) => {
        const r = await fetch(base + f + v);
        if (!r.ok) throw new Error(`${f}: HTTP ${r.status}`);
        return kind === "json" ? r.json() : r.arrayBuffer();
      };
      const [network, calendar, raw] = await Promise.all([
        get("network.json", "json"), get("calendar.json", "json"), get("connections.dat", "bin"),
      ]);
      Engine.prepare(network);
      const conn = decodeConnections(await gunzipIfNeeded(raw), network.edges);
      return new Engine(network, calendar, conn);
    }

    serviceMask(day) {
      let m = this._masks.get(day);
      if (!m) {
        m = new Uint8Array(this.nServices);
        for (const s of this.calendar[day] || []) m[s] = 1;
        this._masks.set(day, m);
      }
      return m;
    }

    /** Verbindungen mit Abfahrt in [t0, t1] (s ab Mitternacht von `day`), inkl. Vortag ≥ 24:00 und Folgetag. */
    window(day, t0, t1) {
      const c = this.conn, out = [];
      for (const offset of [-1, 0, 1]) {
        const shift = offset * DAY, lo = t0 - shift, hi = t1 - shift;
        if (hi < 0) continue;
        const i0 = lowerBound(c.dep, lo), i1 = upperBound(c.dep, hi);
        if (i0 >= i1) continue;
        const mask = this.serviceMask(addDays(day, offset));
        for (let i = i0; i < i1; i++) {
          if (!mask[c.service[i]]) continue;
          out.push({
            dep: c.dep[i] + shift, arr: c.arr[i] + shift, frm: c.frm[i], to: c.to[i],
            trip: c.trip[i] * 3 + (offset + 1), edge: c.edge[i], line: c.line[i],
          });
        }
      }
      out.sort((a, b) => a.dep - b.dep || a.arr - b.arr);
      return out;
    }

    /** Erreichbarkeit ab Station `start`, Datum `day` (YYYY-MM-DD), Zeit `t0` (s), Budget in s. */
    reachable(start, day, t0, budgetS, transferS = TRANSFER_S) {
      return scan(this.window(day, t0, t0 + budgetS), this.stations.length, start, t0, budgetS,
                  this.walk, this.lines, transferS);
    }
  }

  // ---------- CSA ----------
  function scan(conns, nStations, start, t0, budgetS, walk, lines, transferS = TRANSFER_S) {
    const INF = 1 << 30, limit = t0 + budgetS;
    const arr = new Array(nStations).fill(INF);
    const ready = new Array(nStations).fill(INF);
    const via = new Array(nStations).fill("");
    arr[start] = ready[start] = t0;
    via[start] = "start";

    const relaxWalk = (s, tAt) => {
      for (const [b, w] of walk[s]) {
        const ta = tAt + w;
        if (ta < arr[b] && ta <= limit) {
          arr[b] = ta;
          via[b] = "Fußweg";
          if (ta < ready[b]) ready[b] = ta;
        }
      }
    };
    relaxWalk(start, t0);

    const onTrip = new Set(), usedEdges = new Set();
    for (const c of conns) {
      if (c.dep > limit) break;
      if (c.arr > limit) continue;
      if (!onTrip.has(c.trip)) {
        if (ready[c.frm] > c.dep) continue;
        onTrip.add(c.trip);
      }
      usedEdges.add(c.edge);
      if (c.arr < arr[c.to]) {
        arr[c.to] = c.arr;
        via[c.to] = lines[c.line];
        const nr = c.arr + transferS;
        if (nr < ready[c.to]) ready[c.to] = nr;
        relaxWalk(c.to, c.arr);
      }
    }

    const reached = [];
    for (let s = 0; s < nStations; s++) {
      if (arr[s] <= limit) {
        reached.push({ id: s, arrival: arr[s], minutes: Math.round((arr[s] - t0) / 6) / 10, via: via[s] });
      }
    }
    reached.sort((a, b) => a.arrival - b.arrival || a.id - b.id);
    return { reached, edges: usedEdges };
  }

  // ---------- Hilfsfunktionen ----------
  function lowerBound(a, x) { let lo = 0, hi = a.length; while (lo < hi) { const m = (lo + hi) >> 1; if (a[m] < x) lo = m + 1; else hi = m; } return lo; }
  function upperBound(a, x) { let lo = 0, hi = a.length; while (lo < hi) { const m = (lo + hi) >> 1; if (a[m] <= x) lo = m + 1; else hi = m; } return lo; }
  function addDays(iso, n) {
    const d = new Date(iso + "T12:00:00Z");
    d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  }
  function hhmm(sec) {
    sec = ((sec % DAY) + DAY) % DAY;
    return `${String(Math.floor(sec / 3600)).padStart(2, "0")}:${String(Math.floor((sec % 3600) / 60)).padStart(2, "0")}`;
  }

  const api = { Engine, scan, decodeConnections, gunzipIfNeeded, addDays, hhmm, DAY, TRANSFER_S };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.HvvEngine = api;
})(typeof self !== "undefined" ? self : this);
