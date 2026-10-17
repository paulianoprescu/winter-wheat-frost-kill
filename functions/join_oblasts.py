import json, re, sys
import pandas as pd
from shapely.geometry import shape, Point
from shapely import STRtree

NE  = "ne_admin1.geojson"
PTS = sys.argv[1] if len(sys.argv) > 1 else "fetch_points_0.5deg.csv"
OUT = PTS.replace(".csv", "_labeled.csv")

TARGET   = {"Russia": "RU", "Ukraine": "UA", "Romania": "RO", "Bulgaria": "BG"}
OCC_KEYS = ["donets", "luhans", "zaporizh", "kherson", "crimea", "sevastopol"]
norm = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())

d = json.load(open(NE))
geoms, meta = [], []
for f in d["features"]:
    adm = f["properties"].get("admin")
    if adm in TARGET:
        geoms.append(shape(f["geometry"]))
        meta.append((TARGET[adm], f["properties"].get("name")))
tree = STRtree(geoms)

def locate(lon, lat):
    p = Point(float(lon), float(lat))
    for i in tree.query(p):
        if geoms[i].contains(p):
            return meta[i]
    return (None, None)

# sanity: known city coords -> expected oblast
for nm, la, lo in [("Rostov", 47.2, 40.8), ("Odessa", 46.5, 30.7), ("Braila", 45.0, 27.5)]:
    print(f"  sanity {nm}: {locate(lo, la)}")

df = pd.read_csv(PTS)
res = [locate(lo, la) for lo, la in zip(df["lon"], df["lat"])]
df["country"] = [c for c, _ in res]
df["oblast"]  = [o for _, o in res]
df["note"]    = ["occupied" if (c == "UA" and o and any(k in norm(o) for k in OCC_KEYS)) else ""
                 for c, o in res]

before = len(df)
df = df[df["country"].notna()].copy().drop(columns=["weight"], errors="ignore")
df.to_csv(OUT, index=False)

print(f"\n{OUT}: kept {len(df)} of {before} points (dropped non-target neighbours/sea)")
print(df.groupby("country").agg(points=("pid", "size"),
      wheat_Mha=("wheat_ha", lambda s: round(s.sum()/1e6, 2))).to_string())
occ = df[df["note"] == "occupied"]
print(f"flagged occupied/contested UA: {len(occ)} points -> {sorted(occ['oblast'].dropna().unique())}")
