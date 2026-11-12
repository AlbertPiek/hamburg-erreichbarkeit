// Hilfsskript für test_js_parity.py: liest Abfragen (JSON) von stdin,
// rechnet sie mit web/engine.js und gibt die Ergebnisse als JSON aus.
const fs = require("fs");
const path = require("path");
const zlib = require("zlib");
const { Engine, decodeConnections } = require("../web/engine.js");

const dataDir = path.join(__dirname, "..", "web", "data");
const network = Engine.prepare(JSON.parse(fs.readFileSync(path.join(dataDir, "network.json"), "utf8")));
const calendar = JSON.parse(fs.readFileSync(path.join(dataDir, "calendar.json"), "utf8"));
const raw = zlib.gunzipSync(fs.readFileSync(path.join(dataDir, "connections.dat")));
const buf = raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength);
const engine = new Engine(network, calendar, decodeConnections(buf, network.edges));

const queries = JSON.parse(fs.readFileSync(0, "utf8"));
const out = queries.map((q) => {
  const r = engine.reachable(q.station, q.date, q.t0, q.budget);
  return {
    reached: r.reached.map((x) => [x.id, x.arrival, x.via]),
    edges: [...r.edges].sort((a, b) => a - b),
  };
});
process.stdout.write(JSON.stringify(out));
