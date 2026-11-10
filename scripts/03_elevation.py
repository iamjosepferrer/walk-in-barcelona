#!/usr/bin/env python3
"""
Sample terrain elevation from the ICGC 2 m terrain model (MET2m, CC BY 4.0)
through its public WMS GetFeatureInfo, at every graph node and every ~40 m
along every section (resumable). Output: data/work/elev_points.parquet (x, y, z).
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

WORK = Path("data/work")
URL = "https://geoserveis.icgc.cat/servei/catalunya/elevacions/wms"
STEP = 40.0
OUT = WORK / "elev_points.parquet"

e = gpd.read_parquet(WORK / "edges.parquet")
n = pd.read_parquet(WORK / "nodes.parquet")

pts = [(round(x, 1), round(y, 1)) for x, y in zip(n.x, n.y)]
def sample_points(geom, step=STEP):
    """Interior sample positions along a section: shared with 04_indicators."""
    k = int(geom.length // step)
    return [geom.interpolate(i * geom.length / (k + 1)) for i in range(1, k + 1)]


for geom in e.geometry:
    for p in sample_points(geom):
        pts.append((round(p.x, 1), round(p.y, 1)))
pts = list(dict.fromkeys(pts))

done = {}
if OUT.exists():
    old = pd.read_parquet(OUT)
    done = {(x, y): z for x, y, z in zip(old.x, old.y, old.z) if np.isfinite(z)}
todo = [p for p in pts if p not in done]
print(f"{len(pts):,} points, {len(todo):,} to query")

s = requests.Session()
rx = re.compile(r"Pixel Value;\s*(-?[\d.]+)")


def q(p):
    x, y = p
    params = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetFeatureInfo",
              "LAYERS": "MET2m", "QUERY_LAYERS": "MET2m", "CRS": "EPSG:25831",
              "BBOX": f"{x - 2},{y - 2},{x + 2},{y + 2}", "WIDTH": 3, "HEIGHT": 3,
              "I": 1, "J": 1, "INFO_FORMAT": "text/plain", "STYLES": "", "FORMAT": "image/png"}
    for a in range(4):
        try:
            m = rx.search(s.get(URL, params=params, timeout=20).text)
            return p, float(m.group(1)) if m else np.nan
        except Exception:
            time.sleep(1 + a * 2)
    return p, np.nan


t0 = time.time()
with ThreadPoolExecutor(8) as ex:
    for i, (p, z) in enumerate(ex.map(q, todo), 1):
        done[p] = z
        if i % 2000 == 0:
            print(f"  {i:,} ({time.time() - t0:.0f}s)")
            pd.DataFrame([(a, b, c) for (a, b), c in done.items()], columns=["x", "y", "z"]).to_parquet(OUT)

df = pd.DataFrame([(a, b, c) for (a, b), c in done.items()], columns=["x", "y", "z"])
df.to_parquet(OUT)
print(f"done: {df.z.notna().mean():.1%} valid, z {df.z.min():.0f} to {df.z.max():.0f} m, {time.time() - t0:.0f}s")
