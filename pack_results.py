#!/usr/bin/env python3
"""Zip runs/ and results_r1/ into SAGM_GWO_R1_results_<date>.zip for sending back."""
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
out = ROOT / f"SAGM_GWO_R1_results_{time.strftime('%Y%m%d_%H%M')}.zip"
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for folder in ("runs", "results_r1", "runs_r2", "results_r2", "config"):
        for p in (ROOT / folder).rglob("*"):
            if p.is_file() and (ROOT / folder).exists():
                z.write(p, p.relative_to(ROOT))
print(f"wrote {out}  ({out.stat().st_size / 1e6:.1f} MB) -- send this file back")
