"""Search index for the From and To boxes: web/places.js.

Three kinds of place, all snapped to a street node of the graph in web/data.js:
  - landmarks from config/landmarks.json (checked against their neighbourhood),
  - neighbourhoods (the node nearest the middle of the barri's own nodes),
  - street corners, wherever two differently named streets meet.

Street names come from the city's street sections and are messy: half the
sections have no name, the same street appears as "C Arago" and "Aragó", and
some use the catalogue form "Estadi, Av., de L'". They are normalised to one
display name per street ("Aragó", "Pg. Gràcia", "Av. Estadi").

Run after 05_export.py. Needs: pyproj, numpy.
"""
import base64
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
raw = (ROOT / "web/data.js").read_text(encoding="utf-8")
D = json.loads(raw[raw.index("=") + 1: raw.rstrip().rindex(";")])


def dec(s, dt):
    return np.frombuffer(base64.b64decode(s), dtype=dt)


NX, NY = dec(D["nx"], "<i4"), dec(D["ny"], "<i4")
EU, EV = dec(D["eu"], "<i4"), dec(D["ev"], "<i4")
NB = dec(D["nbarri"], "u1")
FLAG = dec(D["eflag"], "u1")
BARRIS = D["barris"]
x0, y0 = D["origin"]

# Only nodes on the main connected component, so every place can be routed to.
N = len(NX)
parent = np.arange(N)


def find(a):
    while parent[a] != a:
        parent[a] = parent[parent[a]]
        a = parent[a]
    return a


for a, b in zip(EU, EV):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[ra] = rb
roots = np.array([find(i) for i in range(N)])
main = roots == Counter(roots.tolist()).most_common(1)[0][0]
print(f"main component: {main.sum()} of {N} nodes")


def fold(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


# ---------- street names ----------
TYPES = {  # abbreviation in the data -> display prefix ("" for a plain carrer)
    "c": "", "pl": "Pl.", "ptge": "Ptge.", "pg": "Pg.", "av": "Av.", "rbla": "Rbla.", "ctra": "Ctra.",
    "rda": "Rda.", "jr": "Jardins", "plta": "Pta.", "bda": "Bda.", "trav": "Trav.", "cami": "Camí",
    "via": "Via", "gran via": "Gran Via", "pas": "Pas", "riera": "Riera", "torrent": "Torrent", "parc": "Parc",
}
# Types that are part of the proper name rather than a prefix ("Via Augusta", "Riera Blanca").
KEEP = {"via", "riera", "torrent", "parc", "cami", "pas"}


def parse(name):
    """Return (type_key, core) or None."""
    name = name.strip()
    if not name:
        return None
    if "," in name:  # catalogue form: "Estadi, Av., de L'" or "Corts Catalanes, Gran Via, de Les"
        parts = [p.strip() for p in name.split(",")]
        core, t = parts[0], fold(parts[1].rstrip(".")) if len(parts) > 1 else "c"
        t = t if t in TYPES else "c"
        if name.startswith("De ") and t == "c":
            core = core[3:]
        return t, core
    words = name.split(" ")
    w0 = fold(words[0])
    if fold(" ".join(words[:2])) == "gran via" and len(words) > 2:
        return "gran via", " ".join(words[2:])
    if w0 in TYPES and len(words) > 1 and w0 not in KEEP:
        return w0, " ".join(words[1:])
    return "c", name


def key(t, core):
    c = re.sub(r"[^a-z0-9 ]", " ", fold(core))
    c = re.sub(r"\b(de|del|dels|la|les|el|els|l|d|i|en|na)\b", " ", c)
    return t + "|" + " ".join(c.split())


def nicer(a, b):
    """Prefer the variant with accents, then proper capitalisation."""
    score = lambda s: (sum(ord(ch) > 127 for ch in s), sum(ch.isupper() for ch in s[1:]) == 0, -len(s))
    return a if score(a) >= score(b) else b


ROMAN = re.compile(r"\b(Ii|Iii|Iv|Vi|Vii|Viii|Ix|Xi|Xii|Xiii|Xiv|Xv)\b")
PARTICLE = re.compile(r"(?<=\s)(De|Del|Dels|La|Les|El|Els|I|En|Na)(?=\s)|(?<=\s)(L'|D')|(?<=·)(L)")


def tidy(core):
    """Undo the title-casing of the source: 'Marquès De L'Argentera' -> 'Marquès de l'Argentera'."""
    core = ROMAN.sub(lambda m: m.group(0).upper(), core)
    return PARTICLE.sub(lambda m: m.group(0).lower(), core)


names = D["names"]
edge_key = [None] * len(names)
display = {}
for i, nm in enumerate(names):
    p = parse(nm)
    if not p or nm.strip().startswith("("):  # "(Sin Asignar)" = unassigned
        continue
    t, core = p
    core = tidy(core)
    k = key(t, core)
    edge_key[i] = k
    pref = TYPES[t]
    label = f"{pref} {core}".strip() if t not in KEEP else core if fold(core).startswith(t) else f"{TYPES[t]} {core}"
    display[k] = nicer(display[k], label) if k in display else label
print(f"streets: {len(set(names)) - 1} raw names -> {len(display)} streets")

# ---------- corners ----------
node_streets = defaultdict(set)
for i, k in enumerate(edge_key):
    if k:
        node_streets[EU[i]].add(k)
        node_streets[EV[i]].add(k)
corners = {}
for n, ks in node_streets.items():
    if not main[n] or len(ks) < 2:
        continue
    ks = sorted(ks)
    for a in range(len(ks)):
        for b in range(a + 1, len(ks)):
            pair = (ks[a], ks[b])
            corners.setdefault(pair, []).append(n)
# A pair of streets can meet more than once (a curved street, a plaza ring): keep the first node only.
corner_list = []
for (a, b), ns in corners.items():
    da, db = display[a], display[b]
    if fold(da) == fold(db):
        continue
    first, second = sorted([da, db], key=lambda s: (s.startswith(("Pl.", "Ptge.", "Pta.", "Jardins")), fold(s)))
    corner_list.append({"label": f"{first} / {second}", "node": int(ns[0]), "kind": "corner"})
print(f"corners: {len(corner_list)}")

# ---------- neighbourhoods ----------
barri_list = []
for bi, bname in enumerate(BARRIS):
    idx = np.where((NB == bi) & main)[0]
    if len(idx) == 0:
        continue
    cx, cy = np.median(NX[idx]), np.median(NY[idx])
    n = idx[np.argmin((NX[idx] - cx) ** 2 + (NY[idx] - cy) ** 2)]
    label = bname[0].upper() + bname[1:]
    barri_list.append({"label": label, "node": int(n), "kind": "barri"})

# ---------- landmarks ----------
tf = Transformer.from_crs("EPSG:4326", D["crs"], always_xy=True)
lm = json.loads((ROOT / "config/landmarks.json").read_text(encoding="utf-8"))["landmarks"]
mx, my = NX.astype(float), NY.astype(float)
land_list, bad = [], []
for p in lm:
    X, Y = tf.transform(p["lon"], p["lat"])
    X, Y = X - x0, Y - y0
    d2 = (mx - X) ** 2 + (my - Y) ** 2
    d2[~main] = np.inf
    n = int(np.argmin(d2))
    got = BARRIS[NB[n]]
    ok = fold(got) in {fold(b) for b in p["barri"]}
    print(f"  {p['name']:<28} {np.sqrt(d2[n]):5.0f} m  {got}{'' if ok else '   <-- check'}")
    if not ok or np.sqrt(d2[n]) > 250:
        bad.append(p["name"])
    land_list.append({"label": p["name"], "node": n, "kind": "place"})
if bad:
    sys.exit(f"landmarks off target: {bad}")

# ---------- write ----------
places = land_list + barri_list + sorted(corner_list, key=lambda c: fold(c["label"]))
# compact form: [label, node, kind code]
code = {"place": 0, "barri": 1, "corner": 2}
out = {"places": [[p["label"], p["node"], code[p["kind"]]] for p in places]}
# clean street name per section, for the page's tooltips and notes (-1 = unnamed)
skeys = sorted(display, key=lambda k: fold(display[k]))
sid = {k: i for i, k in enumerate(skeys)}
out["streets"] = [display[k] for k in skeys]
out["edge_street"] = base64.b64encode(np.array([sid[k] if k else -1 for k in edge_key], dtype="<i2").tobytes()).decode()
js = "window.PAS_PLACES=" + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n"
(ROOT / "web/places.js").write_text(js, encoding="utf-8")
print(f"web/places.js: {len(land_list)} landmarks, {len(barri_list)} neighbourhoods, {len(corner_list)} corners, {len(js) / 1024:.0f} KB")
