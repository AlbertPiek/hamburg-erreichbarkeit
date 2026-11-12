# HVV-Erreichbarkeit (S- und U-Bahn Hamburg)

Interaktive Karte. Station antippen, Uhrzeit wählen, und die App zeigt alle S- und U-Bahn-Stationen und Streckenabschnitte, die ab dieser Zeit innerhalb von 30 Minuten erreichbar sind (Zeitbudget einstellbar). Stadtgrenze und die sieben Bezirke sind eingezeichnet.

Es gibt **eine Oberfläche** (`web/`) in drei Varianten:

| Variante | Für | Rechnet |
|---|---|---|
| **Web-App (PWA)** | Android, iPhone, jeder Browser; installierbar, offline-fähig | im Browser (`web/engine.js`) |
| **Windows-Programm** `dist\HVV-Erreichbarkeit.exe` | Windows ohne Python | im Fenster (WebView2) |
| **Lokaler Server** `python -m hvv.app` | Entwicklung | im Browser |

## Installation (Entwicklung)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
```

## Daten laden und aufbereiten

```bash
python -m hvv.download      # GTFS (~40 MB) + Stadt- und Bezirksgrenzen nach data/raw/
python -m hvv.preprocess    # Filter auf S/U-Bahn → data/cache/ und Web-Daten → web/data/
```

- `download` sucht über die CKAN-API des Transparenzportals automatisch den **neuesten** hvv-GTFS-Datensatz. Neu laden mit `--force`, eigene URL mit `--url <zip>`.
- Der hvv veröffentlicht die Daten etwa monatlich, jeder Datensatz gilt rund zehn Wochen. Für spätere Daten `download --force` und `preprocess` erneut ausführen.
- `preprocess` ruft am Ende `python -m hvv.export_web` auf. Das erzeugt `web/data/` (rund 870 KB): `network.json`, `calendar.json`, `connections.dat` (gzip, binär) und `version.json`.

## Web-App (PWA) aufs Handy bringen

`web/` ist eine fertige statische Website. Es gibt **keinen Server-Code**, sie lässt sich bei jedem Static-Hoster ablegen. Für die Installation als App und den Offline-Betrieb braucht es **HTTPS**.

**Variante A: GitHub Pages (kostenlos)**
1. Ein GitHub-Repository anlegen und den **Inhalt** von `web/` (inklusive `web/data/`) hochladen.
2. Unter *Settings → Pages* als Quelle den Branch `main` mit Ordner `/` (root) wählen.
3. Nach etwa einer Minute ist die App unter `https://<benutzer>.github.io/<repo>/` erreichbar.

**Variante B: Netlify Drop:** Den Ordner `web/` auf app.netlify.com/drop ziehen. Das geht ohne Git.

**Auf Android installieren:** Die URL in Chrome öffnen, dann *⋮ → „Zum Startbildschirm hinzufügen“* bzw. *„App installieren“*. Danach startet sie ohne Browserleiste und funktioniert auch offline. Nur die Hintergrundkarte braucht Netz, bereits angesehene Kacheln (bis 800) bleiben im Cache.

**Fahrplan aktualisieren:** `download --force` und `preprocess` ausführen, dann `web/data/` neu hochladen. Die App lädt beim nächsten Start mit Netz automatisch den neuen Datensatz. `version.json` stellt sicher, dass immer ein zusammenpassender Satz verwendet wird.

**Schnelltest im WLAN ohne Hosting:** `python -m hvv.app --host 0.0.0.0` starten und auf dem Handy `http://<PC-IP>:5000` öffnen. Die App funktioniert so, ist aber ohne HTTPS weder installierbar noch offline nutzbar.

## Windows-Programm (.exe)

`dist\HVV-Erreichbarkeit.exe` (rund 16 MB) ist eine einzelne Datei. Python muss auf dem Zielrechner nicht installiert sein. Die App öffnet sich in einem eigenen Fenster (Edge WebView2, bei Windows 10/11 vorinstalliert). Nur die Hintergrundkarte braucht Internet.

```bash
pip install -r requirements-desktop.txt
build_exe.bat
```

**Neuerer Fahrplan ohne Neubau:** Den Inhalt von `web/data/` in einen Ordner `web-data` neben die .exe kopieren. Er hat Vorrang vor den eingebauten Daten.

Eine unsignierte .exe kann beim ersten Start eine SmartScreen-Warnung auslösen („Weitere Informationen“ → „Trotzdem ausführen“).

## Bedienung

- **Station wählen:** Kreis auf der Karte antippen oder anklicken, Namen ins Feld „Startstation“ tippen oder 📍 für die nächste Station zum eigenen Standort.
- **Datum, Uhrzeit, Minuten:** Jede Änderung rechnet sofort neu. Die zuletzt gewählte Station und das Zeitbudget werden gemerkt.
- Erreichbare Abschnitte werden kräftig in Linienfarbe gezeichnet, erreichbare Stationen nach Fahrzeit eingefärbt (grün → rot). Der Rest wird grau.
- Die Liste zeigt die erreichbaren Stationen mit Ankunftszeit und Linie. Ein Klick zentriert die Karte.
- **Smartphone:** Karte oben, Panel unten. Den Griff antippen, um die Liste aus- oder einzuklappen.
- Am PC hebt `Esc` die Auswahl auf. Die Kartenebenen lassen sich oben rechts ein- und ausblenden. Ein dunkles Design folgt der Systemeinstellung.

## Modell und Annahmen

- Nur **S- und U-Bahn** (Linien `S…`/`U…` laut GTFS; RE/RB, AKN, Busse und Fähren sind nicht enthalten).
- Nur der **Soll-Fahrplan**, keine Echtzeit oder Verspätungen.
- Die 30 Minuten zählen ab der gewählten Uhrzeit, inklusive Wartezeit an der Startstation. Der Weg zur Startstation zählt nicht mit.
- Umstieg innerhalb einer Station: **2 Minuten**. Sitzenbleiben im selben Zug kostet nichts.
- Fußweg-Umstiege zwischen Stationen bis 400 m Luftlinie (z. B. Hbf Nord ↔ Hamburg Hbf, Rathaus ↔ Jungfernstieg): Luftlinie × 1,3 bei 80 m/min + 1 Minute.
- Fahrten nach Mitternacht (GTFS-Zeiten ≥ 24:00) werden korrekt dem Vortag zugeordnet.
- Algorithmus: Connection Scan (früheste Ankunft). Eine Abfrage dauert wenige Millisekunden, auch auf dem Handy.

Parameter: `TRANSFER_S` in `web/engine.js` **und** `hvv/reachability.py`, `WALK_*` in `hvv/preprocess.py`. Nach einer Änderung an `WALK_*` muss `preprocess` erneut laufen.

## Tests

```bash
python -m pytest -q
```

`tests/test_js_parity.py` rechnet 63 Abfragen (zufällig gewählt plus Randfälle) mit Python **und** `web/engine.js` (über Node.js) und verlangt identische Ergebnisse. Ohne Node.js wird der Test übersprungen.

## Aufbau

| Datei | Zweck |
|---|---|
| `hvv/download.py` | Download GTFS + Grenzen |
| `hvv/preprocess.py` | S/U-Filter, Stationen (IFOPT), Kanten mit Linienverlauf aus `shapes.txt`, Kalender |
| `hvv/export_web.py` | kompakte Web-Daten nach `web/data/` |
| `hvv/network.py`, `hvv/reachability.py` | Python-Referenzimplementierung (Tests, `/api/reachable`) |
| `hvv/app.py` | lokaler Server für `web/` |
| `hvv/desktop.py`, `run_desktop.py` | Desktop-Fenster (pywebview), Einstieg für die .exe |
| `hvv_erreichbarkeit.spec`, `build_exe.bat` | PyInstaller-Build |
| `web/engine.js` | Erreichbarkeitsberechnung im Browser |
| `web/app.js`, `index.html`, `style.css` | Oberfläche |
| `web/sw.js`, `manifest.webmanifest`, `icons/` | PWA: Offline-Cache, Installation |
| `web/vendor/leaflet/` | Leaflet 1.9.4 (BSD-2-Lizenz) |
| `tools/make_icons.py` | erzeugt die App-Icons (braucht Pillow) |

## Datenquellen und Lizenzen

- **Fahrplan:** Hamburger Verkehrsverbund GmbH, „hvv Fahrplandaten (GTFS)“, Transparenzportal Hamburg, Datenlizenz Deutschland – Namensnennung – 2.0.
- **Stadt- und Bezirksgrenzen:** Freie und Hansestadt Hamburg, Landesbetrieb Geoinformation und Vermessung (LGV), OGC-API „Verwaltungsgrenzen“ (api.hamburg.de), Datenlizenz Deutschland – Namensnennung – 2.0.
- **Hintergrundkarte:** © OpenStreetMap-Mitwirkende (tile.openstreetmap.org; Nutzungsrichtlinie beachten, für den privaten Gebrauch gedacht).
- Dies ist **keine offizielle hvv-App**.
