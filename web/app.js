"use strict";

const $ = (id) => document.getElementById(id);
const { Engine, hhmm } = window.HvvEngine;
const state = { engine: null, net: null, selected: null, reach: null, stationLayers: {}, edgeLayers: {} };
const isTouch = window.matchMedia("(pointer: coarse)").matches;
const isMobile = () => window.matchMedia("(max-width: 760px)").matches;

// ---------- Speicher (nur Komfort, darf fehlen) ----------
const store = {
  get(k) { try { return JSON.parse(localStorage.getItem("hvv:" + k)); } catch { return null; } },
  set(k, v) { try { localStorage.setItem("hvv:" + k, JSON.stringify(v)); } catch { /* egal */ } },
};

// ---------- Karte ----------
const map = L.map("map", { zoomControl: !isTouch }).setView([53.56, 10.0], 11);
map.createPane("bezirke").style.zIndex = 350;
map.createPane("edges").style.zIndex = 410;
map.createPane("stations").style.zIndex = 420;
const edgeRenderer = L.canvas({ pane: "edges" });
const stationRenderer = L.canvas({ pane: "stations", tolerance: isTouch ? 12 : 4 });

L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19, className: "basemap",
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>-Mitwirkende',
}).addTo(map);

const layers = {
  bezirke: L.layerGroup().addTo(map),
  grenze: L.layerGroup().addTo(map),
  edges: L.layerGroup().addTo(map),
  stations: L.layerGroup().addTo(map),
};

// ---------- Farben ----------
const RAMP = ["#1a9850", "#91cf60", "#fee08b", "#fc8d59", "#d73027"];
function rampColor(t) {
  t = Math.max(0, Math.min(1, t)) * (RAMP.length - 1);
  const i = Math.min(Math.floor(t), RAMP.length - 2), f = t - i;
  const a = hex(RAMP[i]), b = hex(RAMP[i + 1]);
  return `rgb(${a.map((v, k) => Math.round(v + (b[k] - v) * f)).join(",")})`;
}
function hex(h) { return [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)); }
function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

// ---------- Initialisierung ----------
function pad(n) { return String(n).padStart(2, "0"); }
function fmtDate(iso) { const [y, m, d] = iso.split("-"); return `${d}.${m}.${y}`; }

function initInputs(meta) {
  const now = new Date();
  let today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  $("date").min = meta.feed_start;
  $("date").max = meta.feed_end;
  if (today < meta.feed_start || today > meta.feed_end) {
    showWarning(`Der eingebaute Fahrplan gilt nur vom ${fmtDate(meta.feed_start)} bis ${fmtDate(meta.feed_end)}. ` +
                `Es wird ein Datum aus diesem Zeitraum verwendet.`);
    today = today < meta.feed_start ? meta.feed_start : meta.feed_end;
  }
  $("date").value = today;
  $("time").value = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  const b = store.get("budget");
  if (b) $("budget").value = b;
  const src = meta.source || {};
  $("source").innerHTML =
    `Fahrplan: ${esc(src.attribution || "Hamburger Verkehrsverbund GmbH")}, ${esc(src.license || "dl-de/by-2.0")} ` +
    `(gültig ${fmtDate(meta.feed_start)} – ${fmtDate(meta.feed_end)}). ` +
    `Grenzen: Freie und Hansestadt Hamburg, LGV. Keine offizielle hvv-App.`;
}

async function load() {
  const engine = await Engine.load("data/");
  const net = engine.network;
  state.engine = engine;
  state.net = net;
  initInputs(net.meta);
  drawBezirke(net.bezirke);
  drawGrenze(net.grenze);
  drawEdges(net.edges);
  drawStations(net.stations);
  const dl = $("stationList");
  [...net.stations].sort((a, b) => a.name.localeCompare(b.name, "de")).forEach((s) => {
    const o = document.createElement("option");
    o.value = s.name;
    dl.appendChild(o);
  });
  state.bounds = L.latLngBounds(net.stations.map((s) => [s.lat, s.lon])).pad(0.03);
  fitNetwork();

  L.control.layers(null, {
    "Bezirke": layers.bezirke, "Stadtgrenze": layers.grenze,
    "Strecken": layers.edges, "Stationen": layers.stations,
  }, { collapsed: true, position: "topright" }).addTo(map);
  if ("geolocation" in navigator) addLocateControl();

  renderList();
  const last = store.get("station");
  if (Number.isInteger(last) && last >= 0 && last < net.stations.length) selectStation(last, { pan: false });
}

// Karte erst einpassen, wenn der Container eine echte Größe hat.
let fitted = false;
function fitNetwork() {
  map.invalidateSize();
  const sz = map.getSize();
  if (state.bounds && sz.x > 50 && sz.y > 50) {
    map.fitBounds(state.bounds);
    fitted = true;
  }
}
new ResizeObserver(() => { if (!fitted) fitNetwork(); else map.invalidateSize(); }).observe($("map"));
document.addEventListener("visibilitychange", () => { if (!fitted) fitNetwork(); });

function drawBezirke(fc) {
  if (!fc) return;
  L.geoJSON(fc, {
    pane: "bezirke", interactive: false,
    style: { color: "#7b68b5", weight: 1.2, opacity: 0.7, fillColor: "#7b68b5", fillOpacity: 0.04 },
    onEachFeature: (f) => {
      const p = f.properties;
      if (p.label) {
        L.tooltip({ permanent: true, direction: "center", className: "bezirk-label", interactive: false })
          .setLatLng(p.label).setContent(esc(p.bezirk_name)).addTo(layers.bezirke);
      }
    },
  }).addTo(layers.bezirke);
}

function drawGrenze(fc) {
  if (!fc) return;
  L.geoJSON(fc, {
    pane: "bezirke", interactive: false,
    style: { color: "#3b2f6b", weight: 2.2, dashArray: "8 6", fill: false, opacity: 0.85 },
  }).addTo(layers.grenze);
}

function drawEdges(edges) {
  edges.forEach((e) => {
    const pl = L.polyline(e.coords, { renderer: edgeRenderer, interactive: false, lineCap: "round" });
    state.edgeLayers[e.id] = { layer: pl, edge: e };
    pl.addTo(layers.edges);
  });
  styleEdges();
}

function drawStations(stations) {
  stations.forEach((s) => {
    const m = L.circleMarker([s.lat, s.lon], { renderer: stationRenderer, radius: 5, weight: 1.5 });
    m.bindTooltip(() => stationTooltip(s), { direction: "top", offset: [0, -6] });
    m.on("click", () => selectStation(s.id, { pan: false }));
    state.stationLayers[s.id] = { layer: m, station: s };
    m.addTo(layers.stations);
  });
  styleStations();
}

function stationTooltip(s) {
  let html = `<strong>${esc(s.name)}</strong><br><small>${s.lines.join(" · ")}</small>`;
  const r = state.reach && state.reach.byId[s.id];
  if (r) {
    html += r.via === "start"
      ? `<br>Start ${r.arrival}`
      : `<br>Ankunft ${r.arrival} (${Math.round(r.minutes)} min${r.via === "Fußweg" ? ", zu Fuß" : ""})`;
  }
  return html;
}

// ---------- Standort ----------
function addLocateControl() {
  const Ctl = L.Control.extend({
    options: { position: "topleft" },
    onAdd() {
      const div = L.DomUtil.create("div", "leaflet-bar locate");
      const a = L.DomUtil.create("a", "", div);
      a.href = "#"; a.title = "Nächste Station zu meinem Standort"; a.setAttribute("role", "button");
      a.innerHTML = "&#x1F4CD;";
      L.DomEvent.on(a, "click", (ev) => {
        L.DomEvent.preventDefault(ev); L.DomEvent.stopPropagation(ev);
        a.classList.add("busy");
        navigator.geolocation.getCurrentPosition((pos) => {
          a.classList.remove("busy");
          const { latitude: la, longitude: lo } = pos.coords;
          let best = null, bestD = Infinity;
          for (const s of state.net.stations) {
            const d = (s.lat - la) ** 2 + ((s.lon - lo) * Math.cos(la * Math.PI / 180)) ** 2;
            if (d < bestD) { bestD = d; best = s; }
          }
          const km = Math.sqrt(bestD) * 111.2;
          if (best) {
            selectStation(best.id, { pan: true });
            toast(`Nächste Station: ${best.name} (${km < 1 ? Math.round(km * 1000) + " m" : km.toFixed(1) + " km"})`);
          }
        }, (err) => {
          a.classList.remove("busy");
          toast(err.code === 1 ? "Standortzugriff wurde nicht erlaubt." : "Standort nicht verfügbar.");
        }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 });
      });
      return div;
    },
  });
  map.addControl(new Ctl());
}

// ---------- Darstellung ----------
function styleEdges() {
  const used = state.reach ? state.reach.edges : null;
  Object.values(state.edgeLayers).forEach(({ layer, edge }) => {
    if (!used) layer.setStyle({ color: edge.color, weight: 3.5, opacity: 0.75 });
    else if (used.has(edge.id)) layer.setStyle({ color: edge.color, weight: 6, opacity: 1 });
    else layer.setStyle({ color: "#9aa3ad", weight: 2.5, opacity: 0.35 });
  });
  if (used) Object.values(state.edgeLayers).forEach(({ layer, edge }) => { if (used.has(edge.id)) layer.bringToFront(); });
}

function styleStations() {
  const budget = state.reach ? state.reach.budget : 30;
  const base = isTouch ? 1.5 : 0;
  Object.values(state.stationLayers).forEach(({ layer, station }) => {
    const r = state.reach && state.reach.byId[station.id];
    if (!state.reach) {
      layer.setStyle({ radius: 4.5 + base, color: "#1d2430", fillColor: "#ffffff", fillOpacity: 1, opacity: 0.9, weight: 1.5 });
    } else if (station.id === state.selected) {
      layer.setStyle({ radius: 10 + base, color: "#000", weight: 3, fillColor: "#ffffff", fillOpacity: 1, opacity: 1 });
    } else if (r) {
      layer.setStyle({ radius: 7 + base, color: "#1d2430", weight: 1.2, fillColor: rampColor(r.minutes / budget), fillOpacity: 1, opacity: 1 });
      layer.bringToFront();
    } else {
      layer.setStyle({ radius: 3.5 + base, color: "#8b95a1", weight: 1, fillColor: "#e9ecf0", fillOpacity: 0.9, opacity: 0.6 });
    }
  });
  if (state.selected != null) state.stationLayers[state.selected].layer.bringToFront();
}

function renderList() {
  const box = $("result");
  if (!state.reach) {
    box.innerHTML = `<p class="hint">${isTouch ? "Tippe" : "Klicke"} auf eine Station oder nutze 📍 für die nächste Station.</p>`;
    return;
  }
  const r = state.reach;
  const start = state.net.stations[state.selected];
  const others = r.reached.filter((x) => x.id !== state.selected);
  const colors = state.net.meta.colors;
  box.innerHTML = `
    <div class="summary"><strong>${esc(start.name)}</strong><br>
      ab ${r.time} Uhr: <strong>${others.length}</strong> Stationen in ${r.budget} Minuten erreichbar</div>
    <ul class="list">${others.map((x) => `
      <li data-id="${x.id}">
        <span class="dot" style="background:${rampColor(x.minutes / r.budget)}"></span>
        <span>${esc(x.name)}</span>
        <span class="via" style="color:${colors[x.via] || ""}">${x.via === "Fußweg" ? "zu Fuß" : esc(x.via)}</span>
        <span class="min">${x.arrival}</span>
      </li>`).join("")}
    </ul>`;
  box.querySelectorAll("li").forEach((li) => {
    li.addEventListener("click", () => {
      const s = state.net.stations[+li.dataset.id];
      map.panTo([s.lat, s.lon]);
      state.stationLayers[s.id].layer.openTooltip();
      if (isMobile()) $("panel").classList.add("collapsed");
    });
  });
}

function showWarning(text) {
  const w = $("warning");
  w.textContent = text || "";
  w.hidden = !text;
}

let toastTimer = null;
function toast(html, ms = 3500) {
  const t = $("toast");
  t.innerHTML = html;
  t.hidden = false;
  clearTimeout(toastTimer);
  if (ms) toastTimer = setTimeout(() => { t.hidden = true; }, ms);
}

// ---------- Abfrage (lokal im Browser) ----------
function refresh() {
  if (state.selected == null || !state.engine) return;
  const budget = Math.max(1, Math.min(180, parseInt($("budget").value || "30", 10)));
  $("budgetLabel").textContent = budget;
  $("rampMax").textContent = `${budget} min`;
  store.set("budget", budget);
  const day = $("date").value;
  const [h, m] = ($("time").value || "08:00").split(":").map(Number);
  const t0 = h * 3600 + m * 60;
  const meta = state.net.meta;

  if (!day) { showWarning("Bitte ein Datum wählen."); return; }
  showWarning(day < meta.feed_start || day > meta.feed_end
    ? `Datum liegt außerhalb des Fahrplanzeitraums (${fmtDate(meta.feed_start)} – ${fmtDate(meta.feed_end)}).`
    : "");

  const res = state.engine.reachable(state.selected, day, t0, budget * 60);
  const names = state.net.stations;
  const reached = res.reached.map((x) => ({ ...x, name: names[x.id].name, arrival: hhmm(x.arrival) }));
  state.reach = {
    time: hhmm(t0), budget, reached, edges: res.edges,
    byId: Object.fromEntries(reached.map((x) => [x.id, x])),
  };
  styleEdges();
  styleStations();
  renderList();
}

const names = (id) => state.net.stations[id];

function selectStation(id, { pan = false } = {}) {
  state.selected = id;
  store.set("station", id);
  const s = state.net.stations[id];
  $("search").value = s.name;
  refresh();
  if (pan || isMobile()) {
    // Ausschnitt auf das erreichbare Gebiet setzen (auf dem Handy immer, sonst nur bei Suche/Standort)
    const pts = (state.reach ? state.reach.reached : []).map((x) => [names(x.id).lat, names(x.id).lon]);
    if (pts.length > 1) map.fitBounds(L.latLngBounds(pts).pad(0.08), { maxZoom: 14 });
    else map.setView([s.lat, s.lon], Math.max(map.getZoom(), 13));
  }
  state.stationLayers[id].layer.openTooltip();
}

function clearSelection() {
  state.selected = null;
  state.reach = null;
  store.set("station", null);
  $("search").value = "";
  styleEdges();
  styleStations();
  renderList();
}

$("search").addEventListener("change", (ev) => {
  const q = ev.target.value.trim().toLowerCase();
  if (!q) { clearSelection(); return; }
  const s = state.net.stations.find((x) => x.name.toLowerCase() === q)
         || state.net.stations.find((x) => x.name.toLowerCase().startsWith(q))
         || state.net.stations.find((x) => x.name.toLowerCase().includes(q));
  if (s) {
    selectStation(s.id, { pan: true });
    ev.target.blur();
  } else {
    toast("Keine passende Station gefunden.");
  }
});
["date", "time", "budget"].forEach((id) => $(id).addEventListener("change", refresh));
$("handle").addEventListener("click", () => $("panel").classList.toggle("collapsed"));
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && state.selected != null) clearSelection(); });

load().catch((err) => {
  console.error(err);
  $("result").innerHTML = `<p class="hint">Fahrplandaten konnten nicht geladen werden: ${esc(err.message || err)}</p>`;
});

// ---------- Offline-Fähigkeit (Service Worker) ----------
if ("serviceWorker" in navigator && (location.protocol === "https:" || ["localhost", "127.0.0.1"].includes(location.hostname))) {
  navigator.serviceWorker.register("sw.js").then((reg) => {
    reg.addEventListener("updatefound", () => {
      const w = reg.installing;
      w && w.addEventListener("statechange", () => {
        if (w.state === "installed" && navigator.serviceWorker.controller) {
          toast('Neue Version verfügbar. <button type="button" id="reload">Neu laden</button>', 0);
          $("reload").addEventListener("click", () => location.reload());
        }
      });
    });
  }).catch((e) => console.warn("Service Worker nicht registriert:", e));
}
