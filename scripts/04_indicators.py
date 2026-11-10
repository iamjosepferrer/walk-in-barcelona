#!/usr/bin/env python3
"""
Nine walkability indicators from the UX Mobility method (Table 2 of the paper),
computed per street section from Barcelona open data, then percentile-scaled
to [-1, 1] with the median at 0 and +1 always the better condition.

 #  condition              Barcelona source                               raw value on a section
 1  Slope                  ICGC terrain model 2 m                         mean absolute grade, %
 2  Crossing distance      Crossings inventory (active)                   distance from section ends to nearest crossing, m
 3  Park                   park outlines rebuilt from park trees          share of section within 25 m of a park, %
 4  Trees                  Biodiversity Atlas, all 244k trees             trees per 100 m within 40 m
 5  Air quality            NO2 immission map 2024, per section            band midpoint, ug/m3
 6  Shade and water        proxy: canopy + climate shelters + fountains   index
 7  Shops and terraces     ground-floor premises 2024 + terraces          active premises per 100 m within 60 m
 8  Low traffic            road-traffic noise Lden 2017 per section       dB(A)
 9  Pedestrian             proxy: plazas + sections with no traffic noise 0/1

The paper's other three (sidewalk width, pavement, lighting) have no city-wide open data, so they are left out.

Output: data/work/edges_ind.parquet with raw_<k>, x_<k>, plus grade, zs, name.
"""
import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely import concave_hull
from shapely.geometry import MultiPoint, Point

RAW, WORK = Path("data/raw"), Path("data/work")
IND = ["slope", "crossings", "park", "trees", "air", "thermal", "attractiveness", "low_traffic", "pedestrian"]
STEP = 40.0

e = gpd.read_parquet(WORK / "edges.parquet")
nodes = pd.read_parquet(WORK / "nodes.parquet")
L = np.maximum(e.length.values, 20.0)
per100 = 100.0 / L
mid = gpd.GeoSeries([g.interpolate(0.5, normalized=True) for g in e.geometry], crs=25831)


def pts(df, x, y):
    d = df[[x, y]].apply(pd.to_numeric, errors="coerce").dropna()
    return gpd.GeoDataFrame(geometry=gpd.points_from_xy(d[x], d[y]), crs=25831, index=d.index)


EDGES = gpd.GeoDataFrame(geometry=e.geometry, crs=25831)


def count_near(points, r, weights=None):
    """Points within r metres of a section, each point assigned to its nearest
    section only (so wide avenues get the shops and trees on their facades)."""
    j = gpd.sjoin_nearest(points, EDGES, max_distance=r, how="inner")
    j = j[~j.index.duplicated()]
    if weights is None:
        c = j.groupby("index_right").size()
    else:
        c = j.assign(w=weights.reindex(j.index).values).groupby("index_right").w.sum()
    return c.reindex(e.index, fill_value=0).values.astype(float)


def band_mid(s, unit=""):
    s = str(s).replace(unit, "").strip()
    a = re.findall(r"\d+", s)
    if not a:
        return np.nan
    if s.startswith("<"):
        return float(a[0]) - 2.5
    if s.startswith(">"):
        return float(a[0]) + 2.5
    return (float(a[0]) + float(a[1])) / 2 if len(a) >= 2 else float(a[0])


def pscale(v, good_high=True):
    """Percentile scaling to [-1, 1] with the median at 0; NaN stays NaN."""
    v = pd.Series(v, dtype=float)
    x = 2 * v.rank(pct=True, method="average") - 1
    x = (x - np.nanmedian(x)).clip(-1, 1)
    return (x if good_high else -x).values


def fill_nearest(series):
    s = pd.Series(series, dtype=float).copy()
    have = s.notna().values
    if have.all() or not have.any():
        return s
    c = np.array([(p.x, p.y) for p in mid])
    _, i = cKDTree(c[have]).query(c[~have])
    s[~have] = s[have].values[i]
    return s


raw, note = {}, {}

# ---- 3. slope ---------------------------------------------------------------
ep = pd.read_parquet(WORK / "elev_points.parquet")
tree = cKDTree(ep[["x", "y"]].values)
zs_all, grade = [], []
for geom in e.geometry:
    k = int(geom.length // STEP)
    ds = [0.0] + [i * geom.length / (k + 1) for i in range(1, k + 1)] + [geom.length]
    xy = np.array([geom.interpolate(d).coords[0] for d in ds])
    dist, idx = tree.query(xy)
    z = ep.z.values[idx]
    dd = np.diff(ds)
    g = np.abs(np.diff(z)) / np.maximum(dd, 1)
    grade.append(float(np.sum(g * dd) / max(sum(dd), 1) * 100))
    zs_all.append(np.round(z, 1).tolist())
e["zs"] = zs_all
e["grade"] = grade
raw["slope"] = np.array(grade)
esc = pd.read_csv(RAW / "escalators.csv", low_memory=False)
e["escalator"] = (count_near(pts(esc, "geo_epgs_25831_x", "geo_epgs_25831_y"), 20) > 0).astype(int)
e["stairs"] = (e.grade > 25).astype(int)          # stair-like sections (121 in the city, 6.9 km)

# ---- 4. crossing distance --------------------------------------------------
cr = pd.read_csv(RAW / "crossings.csv")
cr = cr[cr.Data_Baixa.isna() & (cr.Codi_Pas != "000000255_Ciclista")]
ct = cKDTree(cr[["X_ETRS89", "Y_ETRS89"]].values)
dn, _ = ct.query(nodes[["x", "y"]].values)
raw["crossings"] = (dn[e.u.values] + dn[e.v.values]) / 2

# ---- 6. park and 7. trees --------------------------------------------------
ta = pd.read_csv(RAW / "trees_all.csv", usecols=["geom_wgs84"])
xy = ta.geom_wgs84.str.extract(r"POINT \(([-\d.]+) ([-\d.]+)\)").astype(float)
trees = gpd.GeoDataFrame(geometry=gpd.points_from_xy(xy[0], xy[1]), crs=4326).to_crs(25831)
raw["trees"] = count_near(trees, 40) * per100

tp = pd.read_csv(RAW / "trees_parks.csv", usecols=["x_etrs89", "y_etrs89", "espai_verd"]).dropna()
polys = []
for name, g in tp.groupby("espai_verd"):
    if len(g) < 8:
        continue
    h = concave_hull(MultiPoint(list(zip(g.x_etrs89, g.y_etrs89))), ratio=0.35).buffer(8)
    if h.area >= 1500:
        polys.append({"park": name, "trees": len(g), "geometry": h})
parks = gpd.GeoDataFrame(polys, geometry="geometry", crs=25831)
parks.to_parquet(WORK / "parks.parquet")
pu = parks.union_all().buffer(25)
share = np.array([g.intersection(pu).length / g.length if g.length else 0 for g in e.geometry])
raw["park"] = np.where(e.plaza.values == 1, 1.0, share) * 100

# ---- 8. NO2 ----------------------------------------------------------------
no2 = pd.read_csv(RAW / "air_no2.csv", usecols=["TRAM", "Rang"])
no2["v"] = no2.Rang.map(lambda s: band_mid(s, "µg/m³"))
e["no2"] = e.TRAM.map(no2.set_index("TRAM").v)
raw["air"] = fill_nearest(e.no2).values

# ---- 11. low traffic (noise as volume proxy) and 12. pedestrian ------------
nz = pd.read_csv(RAW / "noise.csv", usecols=["TRAM", "TRANSIT_DEN", "VIANANTS_D"]).set_index("TRAM")
traffic = fill_nearest(e.TRAM.map(nz.TRANSIT_DEN.map(band_mid)))
people = fill_nearest(e.TRAM.map(nz.VIANANTS_D.map(band_mid)))
e["traffic_db"], e["people_db"] = traffic.values, people.values
raw["low_traffic"] = traffic.values
raw["pedestrian"] = ((e.plaza.values == 1) | (traffic.values <= 45) | (people.values >= traffic.values)).astype(float)

# ---- 9. thermal comfort (proxy) ---------------------------------------------
sh = pts(pd.read_csv(RAW / "climate_shelters.csv", low_memory=False), "geo_epgs_25831_x", "geo_epgs_25831_y")
fo = pts(pd.read_csv(RAW / "fountains.csv"), "X_ETRS89", "Y_ETRS89")
canopy = count_near(trees, 40) * per100
raw["thermal"] = 0.6 * pscale(canopy) + 0.2 * pscale(count_near(sh, 150)) + 0.2 * pscale(count_near(fo, 100))

# ---- 10. attractiveness -----------------------------------------------------
shp = pd.read_csv(RAW / "shops.csv", low_memory=False)
shp = shp[~shp.Nom_Sector_Activitat.str.startswith("Locals buits", na=False)]
te = pd.read_csv(RAW / "terraces.csv")
tpts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(te.LONGITUD, te.LATITUD), crs=4326).to_crs(25831)
raw["attractiveness"] = (count_near(pts(shp, "X_UTM_ETRS89", "Y_UTM_ETRS89"), 60)
                         + 0.25 * count_near(tpts, 60, te.TAULES.astype(float))) * per100

# ---- scale -----------------------------------------------------------------
GOOD_HIGH = {"slope": False, "crossings": False, "park": True, "trees": True, "air": False, "thermal": True,
             "attractiveness": True, "low_traffic": False, "pedestrian": True}
for k in IND:
    e[f"raw_{k}"] = raw[k]
    e[f"x_{k}"] = pscale(raw[k], GOOD_HIGH[k]) if np.isfinite(raw[k]).any() else np.nan

# ---- street names (nearest addressed premises and benches) ------------------
def norm_name(n):
    n = str(n).strip().upper()
    m = re.match(r"^(.*?), ([A-ZÀ-Ü.]+?)\.?,? ?(D'|DE LA|DE LES|DELS|DEL|DE)?$", n)
    if m:
        n = f"{m.group(2).rstrip('.')} {m.group(1)}"
    return n.title().replace("D'", "d'").replace(" De ", " de ").replace(" Del ", " del ").replace(" Dels ", " dels ").replace(" La ", " la ").replace(" Les ", " les ")


names = pd.concat([
    pd.DataFrame({"x": pd.to_numeric(shp.X_UTM_ETRS89, errors="coerce"), "y": pd.to_numeric(shp.Y_UTM_ETRS89, errors="coerce"), "n": shp.Nom_Via}),
    pd.read_csv(RAW / "benches.csv", usecols=["x_etrs89", "y_etrs89", "nom_carrer"]).rename(columns={"x_etrs89": "x", "y_etrs89": "y", "nom_carrer": "n"}),
]).dropna()
npts = gpd.GeoDataFrame(names, geometry=gpd.points_from_xy(names.x, names.y), crs=25831)
npts["n"] = npts.n.map(norm_name)
j = gpd.sjoin_nearest(npts, EDGES, max_distance=40, how="inner")
j = j[~j.index.duplicated()]
best = j.groupby("index_right").n.agg(lambda s: s.mode().iloc[0])
e["name"] = best.reindex(e.index).fillna("")

e.to_parquet(WORK / "edges_ind.parquet")
print("coverage:", {k: f"{np.isfinite(raw[k]).mean():.0%}" for k in IND})
print(f"parks: {len(parks)} polygons, {parks.area.sum() / 1e4:.0f} ha; stairs-like sections: {int(e.stairs.sum())}; named edges: {(e.name != '').mean():.0%}")
print(pd.DataFrame({k: pd.Series(raw[k]).describe() for k in IND}).T[["min", "25%", "50%", "75%", "max"]].round(1).to_string())
