#!/usr/bin/env python3
"""
Pull the layers that Open Data BCN serves through its datastore API
(no bot check on this route). Writes data/raw/<key>.csv.

    python scripts/01_fetch.py
"""
import csv
import sys
import time
from pathlib import Path

import requests

API = "https://opendata-ajuntament.barcelona.cat/data/api/3/action/datastore_search"

# key: resource id (newest datastore-backed file of each dataset, checked 2026-09-30)
RESOURCES = {
    "crossings":         "5cd64615-8f97-464c-a43a-7b98b464e0b1",  # pedestrian crossings inventory
    "air_no2":           None,                                    # NO2 immission map, resolved below (newest)
    "noise":             "3ef70228-789c-47f7-8712-d3789b01a82e",  # 2017 strategic noise map, per section (also the street graph)
    "trees_parks":       None,   # park trees, used to rebuild park outlines
    "trees_all":         None,   # Biodiversity Atlas: every tree (street, zone, park)
    "climate_shelters":  None,
    "fountains":         None,
    "benches":           "cdec2de4-9098-4b88-94bb-d1ec12959b3a",  # street names
    "escalators":        "f7134b6f-95ce-4b83-bacd-6f411bd9c1f0",
    "shops":             None,   # ground-floor premises census
    "terraces":          None,
}
# datasets where we take the newest datastore-backed resource matching a pattern
RESOLVE = {
    "air_no2": ("mapes-immissio-qualitat-aire", "NO2_Mapa_Qualitat_Aire_BCN.csv"),
    "trees_parks": ("arbrat-parcs", ".csv"),
    "trees_all": ("atles-biodiversitat-arbrat-geometries", ".csv"),
    "climate_shelters": ("xarxa-refugis-climatics", ".csv"),
    "fountains": ("fonts", "Fonts_beure.csv"),
    "shops": ("cens-locals-planta-baixa-act-economica", "CensComercial_BCN.csv"),
    "terraces": ("terrasses-comercos-vigents", "Terrasses.csv"),
}


def resolve(slug, needle, s):
    r = s.get("https://opendata-ajuntament.barcelona.cat/data/api/3/action/package_show",
              params={"id": slug}, timeout=60).json()["result"]["resources"]
    r = [x for x in r if x.get("datastore_active") and needle.lower() in x["name"].lower()]
    r.sort(key=lambda x: (x["name"][:4], x.get("created", "")), reverse=True)
    return r[0]["id"], r[0]["name"]


def pull(rid, dest, s, page=10000):
    offset, fields, n = 0, None, 0
    with open(dest, "w", newline="", encoding="utf-8") as f:
        w = None
        while True:
            for attempt in range(4):
                try:
                    j = s.get(API, params={"resource_id": rid, "limit": page, "offset": offset},
                              timeout=120).json()["result"]
                    break
                except Exception:
                    time.sleep(3 * (attempt + 1))
            else:
                raise RuntimeError(f"failed at offset {offset}")
            if fields is None:
                fields = [x["id"] for x in j["fields"] if x["id"] != "_id"]
                w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                w.writeheader()
                total = j["total"]
            recs = j["records"]
            w.writerows(recs)
            n += len(recs)
            offset += page
            if not recs or n >= total:
                break
    return n


def main():
    out = Path("data/raw")
    out.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    only = set(sys.argv[1:])
    for k, rid in RESOURCES.items():
        if only and k not in only:
            continue
        dest = out / f"{k}.csv"
        if dest.exists() and dest.stat().st_size > 0:
            print(f"{k:16s} cached")
            continue
        name = ""
        if rid is None:
            rid, name = resolve(*RESOLVE[k], s)
        n = pull(rid, dest, s)
        print(f"{k:16s} {n:>7,} rows  {name}")


if __name__ == "__main__":
    main()
