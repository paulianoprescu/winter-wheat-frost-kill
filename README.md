# A Frost-Kill Trading Signal for Black Sea Winter Wheat

BSc Honours research, Wageningen University & Research (2026), supervised by Prof. Joost Pennings. [Read the paper](Frost_Kill_Trading_Signal.pdf).

A process-based crop model (WOFOST with the FROSTOL winter-kill submodule, run in PCSE) simulates daily frost kill in Rostov Oblast, Russia's largest winter-wheat region. Each frost-kill day is then tested against Euronext milling wheat (MATIF) futures with local projections.

**Result.** The response peaks at +0.72% eighteen trading days after a frost-kill day (95% CI −0.54% to +1.98%). No horizon is significant (minimum p = 0.241) and the minimum detectable effect is ±1.70%. Coarse reanalysis weather, a snow model calibrated further north and the MATIF proxy all pull the estimate toward zero, so the null bounds the effect rather than settling market efficiency.

![Season kill fraction across the Black Sea wheat belt, 2025/26. Rostov Oblast outlined.](output/figures/fig2_kill_surface_2025_26.png)

## Pipeline

| Notebook | What it does | Paper |
|---|---|---|
| `01_signal_generation.ipynb` | FROSTOL in every wheat cell of the basin, 2024/25 and 2025/26 | Table 1, Figures 1 and 2 |
| `02_oblast_daily_signal.ipynb` | Daily area-weighted kill per oblast, 2000/01 to 2025/26 | Rostov series feeds 03 |
| `03_local_projection.ipynb` | Crop-year-matched contract panel, local projections, event study, robustness checks | Figures 4 and 5 |

`functions/` holds the PCSE patch, the NASA POWER snow helper and the scripts that build the wheat grid from CROPGRIDS.

## Implementation notes

- **PCSE patch.** The winterkill crop wrapper in PCSE 6.0.x is out of step with the current WOFOST modules. `fix_winterkill.py` repairs it at runtime and works around two NASA POWER quirks.
- **Weekend frost.** Kill on a weekend or holiday is rolled onto the next trading day. A plain date merge would have dropped 48% of the kill mass.
- **Contract matching.** Each frost winter is matched to the first contract delivering the damaged harvest, so returns never cross contracts and need no roll adjustment. Every price file is checked against its expected window and hashed to catch duplicates.
- **Weighting.** Kill is computed per cell and then weighted by wheat area, never by averaging the weather first.

## Running it

Python 3.13 and PCSE 6.0.12. Install with `pip install -r requirements.txt` and run the notebooks in order from the repository root. Cached model output keeps reruns to seconds. The Barchart futures files are not included because their terms do not allow redistribution. To rerun the price side, save the 21 daily contract downloads (MLX06 to MLX14, MLU15 to MLU26) in `data/futures_prices/` with file names that start with the symbol, for example `mlu26_....csv`.

## Limitations

NASA POWER is a coarse grid-cell average, the snow model is calibrated in Tula Oblast, MATIF proxies the thin CME Black Sea Wheat contract, CROPGRIDS does not separate winter from spring wheat, and the signal has not yet been validated against realised yields.

---

© 2026 Paulian Oprescu. All rights reserved, see [LICENSE](LICENSE). Please get in touch before reusing any part of this work.
