import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # Als .exe (PyInstaller): Programmdateien liegen im entpackten Bundle.
    ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    EXE_DIR = Path(sys.executable).resolve().parent
    # Ein "data"-Ordner neben der .exe (z. B. mit neuerem Fahrplan) hat Vorrang vor den eingebauten Daten.
    DATA_DIR = EXE_DIR / "data" if (EXE_DIR / "data" / "cache" / "meta.json").exists() else ROOT / "data"
else:
    ROOT = Path(__file__).resolve().parent.parent
    DATA_DIR = ROOT / "data"

# Web-App (PWA): statische Dateien; web/data/ wird von hvv.export_web erzeugt.
WEB_DIR = ROOT / "web"
WEB_DATA_DIR = WEB_DIR / "data"
if getattr(sys, "frozen", False) and (EXE_DIR / "web-data" / "network.json").exists():
    # Neuere Web-Daten neben der .exe (Ordner "web-data") haben Vorrang.
    WEB_DATA_DIR = EXE_DIR / "web-data"

RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR / "cache"

GTFS_ZIP = RAW_DIR / "hvv_gtfs.zip"
SOURCE_JSON = RAW_DIR / "quelle.json"
GRENZE_GEOJSON = RAW_DIR / "hamburg_grenze.geojson"
BEZIRKE_GEOJSON = RAW_DIR / "hamburg_bezirke.geojson"

STATIONS_JSON = CACHE_DIR / "stations.json"
EDGES_JSON = CACHE_DIR / "edges.json"
CONNECTIONS_NPZ = CACHE_DIR / "connections.npz"
CALENDAR_JSON = CACHE_DIR / "calendar.json"
META_JSON = CACHE_DIR / "meta.json"
