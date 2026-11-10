#!/usr/bin/env python3
"""
Export the graph for the browser as web/data.js (window.PAS_DATA), so the page
works from file:// with no server. Arrays are base64-encoded typed arrays.
"""
import base64
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

WORK, RAW, WEB = Path("data/work"), Path("data/raw"), Path("web")
WEB.mkdir(exist_ok=True)
IND = ["slope", "crossings", "park", "trees", "air", "thermal", "attractiveness", "low_traffic", "pedestrian"]  # as in 04_indicators.py

e = gpd.read_parquet(WORK / "edges_ind.parquet")
n = pd.read_parquet(WORK / "nodes.parquet")
x0, y0 = float(n.x.min()), float(n.y.min())


def b64(a):
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()


# geometry: simplified, 1 m integer coords relative to (x0, y0)
coords, offs = [], [0]
zs_flat, zoffs = [], [0]
for g, zs in zip(e.geometry, e.zs):
    c = np.round(np.array(g.simplify(1.0).coords) - [x0, y0]).astype(np.int32)
    coords.append(c.ravel())
    offs.append(offs[-1] + len(c))
    zs_flat.extend(zs)
    zoffs.append(zoffs[-1] + len(zs))
coords = np.concatenate(coords)

X = e[[f"x_{k}" for k in IND]].values
Xq = np.where(np.isfinite(X), np.round(X * 127), -128).astype(np.int8)
R = e[[f"raw_{k}" for k in IND]].values.astype(np.float32)   # raw values for the hover
GOOD_HIGH = {"slope": False, "crossings": False, "park": True, "trees": True, "air": False, "thermal": True,
             "attractiveness": True, "low_traffic": False, "pedestrian": True}
raw_range = {k: [float(np.nanpercentile(R[:, i], 2)), float(np.nanpercentile(R[:, i], 98)), GOOD_HIGH[k]] for i, k in enumerate(IND)}
flags = (e.plaza.values.astype(np.uint8) | (e.stairs.values.astype(np.uint8) << 1)
         | (e.escalator.values.astype(np.uint8) << 2))

# parks (simplified polygons) for the base map
parks = gpd.read_parquet(WORK / "parks.parquet")
park_rings = []
for g in parks.geometry:
    for poly in (g.geoms if g.geom_type == "MultiPolygon" else [g]):
        ring = np.round(np.array(poly.exterior.simplify(4).coords) - [x0, y0]).astype(int)
        if len(ring) >= 4:
            park_rings.append(ring.ravel().tolist())

# district labels placed at the median of their crossings
cr = pd.read_csv(RAW / "crossings.csv").dropna(subset=["Nom_Districte"])
lab = cr.groupby("Nom_Districte")[["X_ETRS89", "Y_ETRS89"]].median()
labels = [{"name": k, "x": round(r.X_ETRS89 - x0), "y": round(r.Y_ETRS89 - y0)} for k, r in lab.iterrows()]

# neighbourhood per node (nearest named crossing)
cb = cr.dropna(subset=["Nom_Barri"])
barris = sorted(cb.Nom_Barri.unique())
bidx = cb.Nom_Barri.map({b: i for i, b in enumerate(barris)}).values
_, near = cKDTree(cb[["X_ETRS89", "Y_ETRS89"]].values).query(n[["x", "y"]].values)
nbarri = bidx[near].astype(np.uint8)

data = {
    "origin": [x0, y0], "crs": "EPSG:25831", "indicators": IND,
    "n_nodes": len(n), "n_edges": len(e),
    "nx": b64(np.round(n.x.values - x0).astype(np.int32)), "ny": b64(np.round(n.y.values - y0).astype(np.int32)),
    "eu": b64(e.u.values.astype(np.int32)), "ev": b64(e.v.values.astype(np.int32)),
    "elen": b64(np.round(e.length.values * 10).astype(np.int32)),
    "ex": b64(Xq), "eraw": b64(R), "raw_range": raw_range, "eflag": b64(flags),
    "gxy": b64(coords), "goff": b64(np.array(offs, dtype=np.int32)),
    "zs": b64(np.round(np.array(zs_flat) * 10).astype(np.int16)), "zoff": b64(np.array(zoffs, dtype=np.int32)),
    "names": e.name.tolist(),
    "parks": park_rings, "labels": labels, "barris": barris, "nbarri": b64(nbarri),
}
js = "window.PAS_DATA=" + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n"
(WEB / "data.js").write_text(js, encoding="utf-8")
print(f"web/data.js {len(js) / 1e6:.2f} MB, {len(e):,} edges, {len(park_rings)} park rings, stairs {int(e.stairs.sum())}")
