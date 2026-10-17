"""
power_snow.py -- NASA POWER prescribed snow for the winterkill runs (ISNOWSRC=0).

POWER (MERRA-2) exposes SNODP (snow depth *within the snow-covered fraction*) and FRSNO
(land snowcover fraction). The grid-cell-average snow depth is SNODP * FRSNO, because SNODP
alone is held near-constant inside the covered fraction (MERRA-2 WEMIN threshold). This
module fetches both, forms the grid-cell depth in cm, and injects it as SNOWDEPTH into a
pcse WeatherDataProvider so the winterkill Engine can run with ISNOWSRC=0.

    fetch_power_snow(lat, lon, ...) -> pd.Series   (SNOWDEPTH cm, indexed by date; disk-cached)
    attach_snow(wdp, depth)         -> int         (adds SNOWDEPTH to every container)

UNIT NOTE: POWER's parameter listing gives SNODP in cm, so SNODP_TO_CM defaults to 1.0. If
the printed depths look like metres (winter max < ~2), set SNODP_TO_CM = 100 and re-run.
CACHE: each point's snow series is cached to power_snow_cache/ for CACHE_TTL_DAYS, so re-runs
are fast; delete the folder (or wait out the TTL) to pick up newly-settled recent POWER days.
"""
import datetime as dt
import os
import time
import numpy as np
import pandas as pd
import requests

POWER_URL      = "https://power.larc.nasa.gov/api/temporal/daily/point"
SNODP_TO_CM    = 1.0          # cm per POWER's parameter listing; set 100.0 if POWER reports metres
CACHE_DIR      = "power_snow_cache"
CACHE_TTL_DAYS = 7            # re-fetch a point if its cached snow file is older than this
_FILL          = -999.0
_MAX_CM        = 300.0

def _parse_snow(power_json):
    """POWER daily-point JSON -> grid-cell snow depth Series (cm), NaN where missing."""
    par = power_json["properties"]["parameter"]
    snodp = pd.Series(par["SNODP"], dtype="float64")
    frsno = pd.Series(par["FRSNO"], dtype="float64")
    snodp.index = pd.to_datetime(snodp.index, format="%Y%m%d")
    frsno.index = pd.to_datetime(frsno.index, format="%Y%m%d")
    snodp = snodp.mask(snodp <= _FILL)
    frsno = frsno.mask(frsno <= _FILL)
    depth = (snodp * frsno * SNODP_TO_CM).clip(lower=0.0, upper=_MAX_CM)
    return depth.sort_index()

def fetch_power_snow(lat, lon, start="19830701", end=None, user="wurblacksea",
                     end_buffer_days=30, timeout=120, verbose=False, cache=True):
    depth, path = None, None
    if cache:
        os.makedirs(CACHE_DIR, exist_ok=True)
        path = os.path.join(CACHE_DIR, f"{round(lat, 4)}_{round(lon, 4)}.pkl")
        if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < CACHE_TTL_DAYS * 86400:
            depth = pd.read_pickle(path)
    if depth is None:
        if end is None:
            end = (dt.date.today() - dt.timedelta(days=end_buffer_days)).strftime("%Y%m%d")
        params = {"request": "execute", "parameters": "SNODP,FRSNO",
                  "latitude": lat, "longitude": lon, "start": start, "end": end,
                  "community": "AG", "format": "JSON", "user": user}
        r = requests.get(POWER_URL, params=params, timeout=timeout)
        if r.status_code != 200:
            raise RuntimeError(f"POWER snow fetch HTTP {r.status_code}: {r.text[:160]}")
        depth = _parse_snow(r.json())
        if cache:
            depth.to_pickle(path)
    if verbose:
        v = depth.dropna()
        if len(v):
            print(f"  POWER snow SNODP*FRSNO: {len(v)} days, cm min {v.min():.2f} "
                  f"mean {v.mean():.2f} max {v.max():.2f}")
            if v.max() < 2.0:
                print("  NOTE: max < 2 cm -> SNODP is probably in metres; "
                      "set SNODP_TO_CM = 100 in power_snow.py and re-run.")
    return depth

def attach_snow(wdp, depth, default=0.0):
    """Add SNOWDEPTH (cm) to every WeatherDataContainer in wdp, aligned by date.
       Missing snow days are forward-filled; leading gaps set to `default`."""
    s = pd.Series(np.asarray(depth, dtype="float64"),
                  index=[pd.Timestamp(i).date() for i in depth.index]).sort_index()
    prov_dates = sorted({k[0] for k in wdp.store})
    aligned = s.reindex(prov_dates).ffill().fillna(default)
    for d in prov_dates:
        wdc = wdp(d)
        try:
            wdc.add_variable("SNOWDEPTH", float(aligned[d]), "cm")
        except Exception:
            wdc.SNOWDEPTH = float(aligned[d])
    return len(prov_dates)
