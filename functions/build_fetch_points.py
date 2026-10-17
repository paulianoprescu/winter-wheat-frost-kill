"""
build_fetch_points.py: turn the CROPGRIDS wheat grid into the weather fetch points
and wheat-area weights used by the FROSTOL runs.

    CROPGRIDS harvested area (0.05 deg) -> summed to `stride` cells
    -> cells above `min_ha` hectares -> fetch points (pid, lon, lat, wheat_ha, weight)

The stride sets the sampling density. NASA POWER is about 0.5 deg, so 0.5 is the
default. Each point keeps the wheat area it represents. Kill is aggregated by weighting
the per-cell model outputs with the helpers below, never by averaging the weather.

The bounding box also catches neighbouring countries. join_oblasts.py then labels each
point by country and oblast, which gives data/fetch_points_0.5deg_labeled.csv.

Usage, from the repository root:
    python functions/build_fetch_points.py --stride 0.5
"""
import argparse
import xarray as xr

# basin bounding box: lonmin, lonmax, latmin, latmax
DEFAULT_BBOX = (25.0, 50.0, 41.0, 54.0)


def build_fetch_points(nc="data/CROPGRIDSv1.08_wheat.nc", stride=0.5,
                       bbox=DEFAULT_BBOX, min_ha=100.0, out=None):
    ds = xr.open_dataset(nc)
    lonmin, lonmax, latmin, latmax = bbox
    sub = ds.harvarea.sel(lat=slice(latmin, latmax), lon=slice(lonmin, lonmax))
    harv = sub.where(sub > 0, 0.0)                       # drop ocean(-1)/neg

    f = int(round(stride / 0.05))                        # 0.05 deg native cells per stride cell
    c = harv.coarsen(lat=f, lon=f, boundary="trim").sum()

    df = c.to_dataframe(name="wheat_ha").reset_index()
    df = df[df["wheat_ha"] > min_ha].copy()
    df = df.sort_values("wheat_ha", ascending=False).reset_index(drop=True)
    df["weight"] = df["wheat_ha"] / df["wheat_ha"].sum()
    df["pid"] = ["g%05d" % i for i in range(len(df))]
    df = df[["pid", "lon", "lat", "wheat_ha", "weight"]].round(
        {"lon": 3, "lat": 3, "wheat_ha": 1, "weight": 6})

    if out is None:
        out = f"data/fetch_points_{stride:g}deg.csv"
    df.to_csv(out, index=False)
    covered = df["wheat_ha"].sum() / 1e6
    print(f"{out}: {len(df):,} points, {covered:.1f} Mha covered "
          f"(stride {stride} deg, min_ha {min_ha})")
    return df


# --- aggregation: weight the per-cell OUTPUTS, never the weather inputs -----
def weighted_index(panel_df, value="RF_FROST_T", weight="wheat_ha"):
    """Single area-weighted scalar over all cells (e.g. the basin signal)."""
    w = panel_df[weight]
    return float((panel_df[value] * w).sum() / w.sum())


def weighted_by_group(panel_df, group="oblast", value="RF_FROST_T", weight="wheat_ha"):
    """Area-weighted value per group (needs the oblast or country label added by
    join_oblasts.py)."""
    g = panel_df.groupby(group)
    num = g.apply(lambda d: (d[value] * d[weight]).sum())
    den = g[weight].sum()
    return (num / den).rename(value)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--nc", default="data/CROPGRIDSv1.08_wheat.nc")
    ap.add_argument("--stride", type=float, default=0.5)
    ap.add_argument("--min_ha", type=float, default=100.0)
    args = ap.parse_args()
    build_fetch_points(nc=args.nc, stride=args.stride, min_ha=args.min_ha)
