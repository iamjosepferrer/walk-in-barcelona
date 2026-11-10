#!/usr/bin/env python3
"""
Build the walkable street graph from the city's street sections (TRAM codes).

Geometry: Strategic Noise Map sections (17,958 codes, EPSG:25831).
  T, R, L, N, V codes: street sections, used as edges (multi-part sections
                       are split into their parts).
  P codes:            outlines of squares and plazas. Each outline is split at
                       the points where streets meet it, and straight
                       "across the plaza" chords are added between those points
                       when they stay inside the plaza. Both carry plaza=1.
Endpoints closer than SNAP metres are merged into one intersection node.

Output: data/work/edges.parquet, data/work/nodes.parquet
"""
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely import wkt
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import linemerge, substring

RAW, WORK = Path("data/raw"), Path("data/work")
WORK.mkdir(parents=True, exist_ok=True)
SNAP = 2.0          # merge endpoints closer than this (m)
ATTACH = 6.0        # a street end this close to a plaza outline attaches to it (m)

src = pd.read_csv(RAW / "noise.csv", usecols=["TRAM", "GEOM_WKT"]).drop_duplicates("TRAM")
src["geom"] = src.GEOM_WKT.map(lambda s: linemerge(wkt.loads(s)))
src["kind"] = src.TRAM.str[0]

# ---- street sections ------------------------------------------------------
rows = []
for tram, g, kind in zip(src.TRAM, src.geom, src.kind):
    if kind == "P":
        continue
    parts = [g] if g.geom_type == "LineString" else list(g.geoms)
    for p in parts:
        if p.length > 0.5 and p.coords[0] != p.coords[-1]:
            rows.append({"TRAM": tram, "plaza": 0, "geometry": p})
streets = gpd.GeoDataFrame(rows, geometry="geometry", crs=25831)

# ---- plazas -----------------------------------------------------------------
ends = np.array([c for g in streets.geometry for c in (g.coords[0], g.coords[-1])])
tree = cKDTree(ends)
prow = []
for tram, g, kind in zip(src.TRAM, src.geom, src.kind):
    if kind != "P":
        continue
    rings = [g] if g.geom_type == "LineString" else list(g.geoms)
    for ring in rings:
        if len(ring.coords) < 4 or ring.coords[0] != ring.coords[-1]:
            continue
        poly = Polygon(ring.coords).buffer(0)
        if poly.is_empty or poly.area < 30:
            continue
        near = tree.query_ball_point(np.array(ring.centroid.coords[0]),
                                     r=ring.length / 2 + ATTACH)
        att = []
        for i in near:
            pt = Point(ends[i])
            if ring.distance(pt) <= ATTACH:
                att.append((ring.project(pt), tuple(ends[i])))
        if len(att) < 2:
            continue
        att = sorted({round(d, 1): p for d, p in att}.items())
        # outline pieces between consecutive attachment points
        ds = [d for d, _ in att]
        for a, b in zip(ds, ds[1:] + [ds[0] + ring.length]):
            if b - a < 0.5:
                continue
            if b <= ring.length:
                seg = substring(ring, a, b)
            else:
                seg = linemerge([substring(ring, a, ring.length), substring(ring, 0, b - ring.length)])
            if seg.geom_type == "LineString":
                prow.append({"TRAM": tram, "plaza": 1, "geometry": seg})
        # straight chords across the plaza (walkable open space)
        pts = [p for _, p in att]
        inner = poly.buffer(1.5)
        if len(pts) <= 14:
            for i in range(len(pts)):
                for j in range(i + 1, len(pts)):
                    ch = LineString([pts[i], pts[j]])
                    if ch.length > 3 and inner.contains(ch):
                        prow.append({"TRAM": tram, "plaza": 1, "geometry": ch})
        # the attachment points connect to the street ends through short links
        for _, p in att:
            proj = ring.interpolate(ring.project(Point(p)))
            if proj.distance(Point(p)) > 0.3:
                prow.append({"TRAM": tram, "plaza": 1, "geometry": LineString([p, proj.coords[0]])})

plazas = gpd.GeoDataFrame(prow, geometry="geometry", crs=25831)
g = pd.concat([streets, plazas], ignore_index=True)
g = gpd.GeoDataFrame(g, geometry="geometry", crs=25831)

# ---- nodes: cluster endpoints within SNAP --------------------------------
E = np.array([c for geom in g.geometry for c in (geom.coords[0], geom.coords[-1])])
par = np.arange(len(E))


def find(a):
    while par[a] != a:
        par[a] = par[par[a]]
        a = par[a]
    return a


for a, b in cKDTree(E).query_pairs(SNAP):
    ra, rb = find(a), find(b)
    if ra != rb:
        par[ra] = rb
root = np.array([find(i) for i in range(len(E))])
uniq, lab = np.unique(root, return_inverse=True)
nx_ = np.bincount(lab, weights=E[:, 0]) / np.bincount(lab)
ny_ = np.bincount(lab, weights=E[:, 1]) / np.bincount(lab)
g["u"], g["v"] = lab[0::2], lab[1::2]
g = g[g.u != g.v].copy()
g["length"] = g.length

G = nx.Graph()
G.add_edges_from(zip(g.u, g.v))
comps = sorted(nx.connected_components(G), key=len, reverse=True)
main = comps[0]
tot = G.number_of_nodes()
g = g[g.u.isin(main)].reset_index(drop=True)

used = np.array(sorted(main))
remap = -np.ones(len(uniq), dtype=int)
remap[used] = np.arange(len(used))
g["u"], g["v"] = remap[g.u], remap[g.v]
nd = pd.DataFrame({"node": np.arange(len(used)), "x": nx_[used], "y": ny_[used]})

g.to_parquet(WORK / "edges.parquet")
nd.to_parquet(WORK / "nodes.parquet")
print(f"street parts {len(streets):,}, plaza edges {len(plazas):,}")
print(f"largest component {len(main):,} of {tot:,} nodes ({len(main) / tot:.1%}), {len(comps)} pieces")
print(f"kept {len(g):,} edges, {len(nd):,} nodes, {g.length.sum() / 1000:,.0f} km, "
      f"plaza share {g[g.plaza == 1].length.sum() / g.length.sum():.1%}")
