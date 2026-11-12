/* Service Worker: macht die App offline-fähig.
 * - App-Dateien und data/version.json: zuerst Netz (max. 4 s), sonst Cache
 * - versionierte Fahrplandaten (data/*?v=…): Cache zuerst, ändern sich nie
 * - Kartenkacheln: Cache zuerst, begrenzt auf MAX_TILES
 */
const SHELL_CACHE = "hvv-shell-v1";
const DATA_CACHE = "hvv-data-v1";
const TILE_CACHE = "hvv-tiles-v1";
const MAX_TILES = 800;
const SHELL = [
  "./", "index.html", "style.css", "app.js", "engine.js", "manifest.webmanifest",
  "vendor/leaflet/leaflet.js", "vendor/leaflet/leaflet.css", "vendor/leaflet/images/layers.png",
  "vendor/leaflet/images/layers-2x.png", "icons/icon-192.png", "icons/icon-512.png",
];

self.addEventListener("install", (ev) => {
  ev.waitUntil(caches.open(SHELL_CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (ev) => {
  const keep = [SHELL_CACHE, DATA_CACHE, TILE_CACHE];
  ev.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => !keep.includes(k)).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (ev) => {
  const req = ev.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  if (url.hostname === "tile.openstreetmap.org") {
    ev.respondWith(tileFirst(req));
  } else if (url.origin === location.origin && url.pathname.includes("/data/") && url.searchParams.has("v")) {
    ev.respondWith(cacheFirst(req, DATA_CACHE, true));
  } else if (url.origin === location.origin) {
    ev.respondWith(networkFirst(req, SHELL_CACHE));
  }
});

async function networkFirst(req, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const res = await withTimeout(fetch(req), 4000);
    if (res.ok) cache.put(req, res.clone());
    return res;
  } catch (e) {
    const hit = await cache.match(req, { ignoreSearch: false });
    if (hit) return hit;
    throw e;
  }
}

async function cacheFirst(req, cacheName, pruneOldVersions) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok) {
    await cache.put(req, res.clone());
    if (pruneOldVersions) {
      // ältere Versionen derselben Datei entfernen
      const path = new URL(req.url).pathname, v = new URL(req.url).searchParams.get("v");
      for (const k of await cache.keys()) {
        const u = new URL(k.url);
        if (u.pathname === path && u.searchParams.get("v") !== v) await cache.delete(k);
      }
    }
  }
  return res;
}

async function tileFirst(req) {
  const cache = await caches.open(TILE_CACHE);
  const hit = await cache.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok || res.type === "opaque") {
    await cache.put(req, res.clone());
    const keys = await cache.keys();
    for (let i = 0; i < keys.length - MAX_TILES; i++) await cache.delete(keys[i]);
  }
  return res;
}

function withTimeout(p, ms) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("timeout")), ms);
    p.then((v) => { clearTimeout(t); resolve(v); }, (e) => { clearTimeout(t); reject(e); });
  });
}
