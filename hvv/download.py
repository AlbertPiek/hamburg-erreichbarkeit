"""Einmaliger Download der Rohdaten.

- hvv-Fahrplandaten (GTFS) aus dem Transparenzportal Hamburg (CKAN-API)
- Landesgrenze und Bezirksgrenzen aus der OGC-API "Verwaltungsgrenzen" (api.hamburg.de)

Aufruf:  python -m hvv.download [--url <GTFS-ZIP-URL>] [--force]
"""
from __future__ import annotations

import argparse
import json
import sys

import requests

from .paths import RAW_DIR, GTFS_ZIP, BEZIRKE_GEOJSON, GRENZE_GEOJSON, SOURCE_JSON

CKAN_SEARCH = "https://suche.transparenz.hamburg.de/api/3/action/package_search"
OGC_BASE = "https://api.hamburg.de/datasets/v1/verwaltungsgrenzen/collections/{c}/items"
CRS84 = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
HEADERS = {"User-Agent": "hvv-erreichbarkeit/1.0 (lokales Analysewerkzeug)"}

EXPECTED_BEZIRKE = {
    "Altona", "Bergedorf", "Eimsbüttel", "Hamburg-Mitte",
    "Hamburg-Nord", "Harburg", "Wandsbek",
}


def find_latest_gtfs() -> dict:
    """Sucht den neuesten hvv-GTFS-Datensatz und gibt Metadaten + ZIP-URL zurück."""
    params = {
        "q": "hvv Fahrplandaten GTFS",
        "sort": "metadata_created desc",
        "rows": 20,
    }
    r = requests.get(CKAN_SEARCH, params=params, headers=HEADERS, timeout=60)
    r.raise_for_status()
    for pkg in r.json()["result"]["results"]:
        if not pkg["name"].startswith("hvv-fahrplandaten-gtfs"):
            continue
        for res in pkg.get("resources", []):
            if (res.get("format") or "").upper() == "ZIP" and res.get("url"):
                return {
                    "dataset": pkg["name"],
                    "title": pkg.get("title"),
                    "created": pkg.get("metadata_created"),
                    "license": pkg.get("license_title"),
                    "attribution": "Hamburger Verkehrsverbund GmbH",
                    "url": res["url"],
                }
    raise RuntimeError("Kein hvv-GTFS-Datensatz im Transparenzportal gefunden. Bitte --url angeben.")


def download_file(url: str, target) -> None:
    tmp = target.with_suffix(target.suffix + ".part")
    with requests.get(url, headers=HEADERS, stream=True, timeout=300) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {done / 1e6:6.1f} / {total / 1e6:.1f} MB", end="", flush=True)
    print()
    tmp.replace(target)


def download_boundaries(force: bool) -> None:
    for coll, target in (("landesgrenze", GRENZE_GEOJSON), ("bezirke", BEZIRKE_GEOJSON)):
        if target.exists() and not force:
            print(f"✓ {target.name} vorhanden")
            continue
        print(f"→ Lade {coll} …")
        r = requests.get(
            OGC_BASE.format(c=coll),
            params={"f": "json", "limit": 100, "crs": CRS84},
            headers=HEADERS,
            timeout=120,
        )
        r.raise_for_status()
        r.encoding = "utf-8"
        fc = r.json()
        fc = {"type": "FeatureCollection", "features": fc["features"]}
        if coll == "bezirke":
            names = {f["properties"].get("bezirk_name") for f in fc["features"]}
            if names != EXPECTED_BEZIRKE:
                print(f"  ⚠ Unerwartete Bezirksnamen: {sorted(n or '?' for n in names)}")
        target.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
        print(f"✓ {target.name} ({len(fc['features'])} Features)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="GTFS-ZIP-URL manuell vorgeben")
    ap.add_argument("--force", action="store_true", help="Vorhandene Dateien neu laden")
    args = ap.parse_args(argv)

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if GTFS_ZIP.exists() and not args.force and not args.url:
        print(f"✓ {GTFS_ZIP.name} vorhanden (mit --force neu laden)")
    else:
        if args.url:
            meta = {"dataset": None, "url": args.url,
                    "license": "Datenlizenz Deutschland – Namensnennung – 2.0",
                    "attribution": "Hamburger Verkehrsverbund GmbH"}
        else:
            print("→ Suche neuesten GTFS-Datensatz im Transparenzportal …")
            meta = find_latest_gtfs()
            print(f"  {meta['title']} ({meta['created'][:10]})")
        print(f"→ Lade GTFS: {meta['url']}")
        download_file(meta["url"], GTFS_ZIP)
        SOURCE_JSON.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ {GTFS_ZIP.name}")

    download_boundaries(args.force)
    print("Fertig. Weiter mit:  python -m hvv.preprocess")
    return 0


if __name__ == "__main__":
    sys.exit(main())
