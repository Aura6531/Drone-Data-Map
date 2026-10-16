# -*- coding: utf-8 -*-
"""核对热力图叠加位置：把「网格真实范围」与「前端会算出的范围」都打出来，
并给出几个**边界上的实测覆盖点** —— 在界面上点它们，看是否正好落在热力图边缘。

用法：
    python -B coverage_bounds_check.py --project test
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np          # noqa: E402
import coverage as cov      # noqa: E402

# 与页面里的 COV_M_PER_DEG_LAT / COV_M_PER_DEG_LNG 保持一致的"前端算式"
COV_M_PER_DEG_LAT = 110540.0
COV_M_PER_DEG_LNG = 111320.0


def frontend_bounds(summary):
    """复现页面 coverageBoundsFromSummary 的算法。"""
    lat0, lng0 = summary["origin"]
    ny, nx = summary["grid"]
    cell = summary.get("cell_m") or 1.0
    mLat = COV_M_PER_DEG_LAT
    mLng = COV_M_PER_DEG_LNG * math.cos(math.radians(lat0))
    return (lat0, lng0, lat0 + ny * cell / mLat, lng0 + nx * cell / mLng)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="test")
    ap.add_argument("--npz", default=None)
    args = ap.parse_args()

    import project_manager as pm

    if args.npz:
        files = [Path(args.npz)]
    else:
        cdir = pm.PROJECT_DIR / args.project / "coverage"
        files = sorted(cdir.glob("*.npz"))

    for npz in files:
        g = cov.CoverageGrid.load(npz)
        js = npz.with_suffix(".json")
        if not js.is_file():
            print(f"{npz.name}: 没有摘要 json，跳过")
            continue
        s = json.loads(js.read_text(encoding="utf-8"))
        lat0, lng0 = s["origin"]
        ny, nx = s["grid"]
        cell = s["cell_m"]

        print("=" * 78)
        print(f"{npz.name}")
        print(f"  摘要: grid=[ny={ny}, nx={nx}]  origin=[{lat0:.7f}, {lng0:.7f}]  cell={cell}")
        print(f"  载入: g.ny={g.ny} g.nx={g.nx}（应当与摘要一致）")

        mx = cov.M_PER_DEG_LNG * math.cos(math.radians(lat0))
        trueN = lat0 + ny * cell / cov.M_PER_DEG_LAT
        trueE = lng0 + nx * cell / mx
        fS, fW, fN, fE = frontend_bounds(s)

        print(f"  网格真实范围 : lat {lat0:.7f}..{trueN:.7f}   lng {lng0:.7f}..{trueE:.7f}")
        print(f"  前端算的范围 : lat {fS:.7f}..{fN:.7f}   lng {fW:.7f}..{fE:.7f}")
        dN = (fN - trueN) * cov.M_PER_DEG_LAT
        dE = (fE - trueE) * mx
        print(f"  差（米）     : 纬度 {dN:+.3f}   经度 {dE:+.3f}"
              + ("   <- 一致" if abs(dN) < 0.01 and abs(dE) < 0.01 else "   <- **不一致，图会歪**"))

        # 边界上的实测覆盖点：在界面上点这些经纬度，应正好落在热力图**有颜色**的边缘。
        # 注意 iy 是**向北**增长的（ENU 约定），iy 小 = 南、iy 大 = 北。
        m = g.count > 0
        ys, xs = np.nonzero(m)
        print(f"  覆盖格 {int(m.sum())} 行 {ys.min()}..{ys.max()} 列 {xs.min()}..{xs.max()}"
              f"  （顶边界: 南{ys.min()==0} 北{ys.max()==g.ny-1}"
              f" 西{xs.min()==0} 东{xs.max()==g.nx-1}）")
        picks = []
        # 最南 / 最北：取该行里"帧数最多"的列，避免选到孤立的噪点格
        for name, iy in (("最南的覆盖点", int(ys.min())), ("最北的覆盖点", int(ys.max()))):
            row = np.nonzero(m[iy])[0]
            ix = int(row[np.argmax(g.count[iy, row])])
            picks.append((name, ix, iy))
        # 最西 / 最东
        for name, ix in (("最西的覆盖点", int(xs.min())), ("最东的覆盖点", int(xs.max()))):
            col = np.nonzero(m[:, ix])[0]
            iy = int(col[np.argmax(g.count[col, ix])])
            picks.append((name, ix, iy))
        for name, ix, iy in picks:
            lat, lng = g.cell_latlng(ix, iy)
            print(f"    {name}: {lat:.6f}, {lng:.6f}   （格 {ix},{iy}，{int(g.count[iy,ix])} 帧）")
        print()


if __name__ == "__main__":
    main()
