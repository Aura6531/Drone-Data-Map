# -*- coding: utf-8 -*-
"""把覆盖网格导成矢量 GeoJSON。

用法：
    python -B coverage_export.py <网格.npz> [选项]

选项：
    --metric count|gsd     按"覆盖帧数"或"解像度"取面（默认 count）
    --threshold N          count 指标下的最小帧数（默认 1）
    --gsd-max M            gsd 指标下的最大米/像素（默认 0.10，即 10 cm）
    --tol M                Douglas-Peucker 简化容差（米，默认 0，不简化）
    --min-area N           丢掉小于 N 格的碎片（默认 4）
    --out 路径             输出 GeoJSON（默认与 npz 同目录同名）

例：
    # "被拍到过"的整片覆盖
    python -B coverage_export.py "..\\Data\\X\\coverage\\V.coverage.npz" --metric count --threshold 1

    # "至少看过 30 帧"的可靠覆盖
    python -B coverage_export.py "..\\...\\V.coverage.npz" --threshold 30

    # "看得清 20 cm 以内"的高价值区
    python -B coverage_export.py "..\\...\\V.coverage.npz" --metric gsd --gsd-max 0.20
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import coverage as cov            # noqa: E402
import coverage_vector as cvv     # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("npz")
    ap.add_argument("--metric", default="count", choices=["count", "gsd"])
    ap.add_argument("--threshold", type=int, default=None)
    ap.add_argument("--gsd-max", type=float, default=None)
    ap.add_argument("--tol", type=float, default=0.0)
    ap.add_argument("--min-area", type=int, default=4)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    src = Path(args.npz).resolve()
    if not src.is_file():
        print(f"找不到 {src}")
        return 1
    t0 = time.time()
    g = cov.CoverageGrid.load(src)
    print(f"网格：{g.ny}x{g.nx} @ {g.cell} m   （加载 {time.time()-t0:.1f}s）")

    t1 = time.time()
    geo, stats = cvv.to_geojson(
        g, metric=args.metric, threshold=args.threshold, gsd_max=args.gsd_max,
        tol_m=args.tol, min_area_cells=args.min_area)
    dt = time.time() - t1

    out = Path(args.out) if args.out else src.with_suffix("").with_suffix(".geojson")
    if out.name.endswith(".coverage.geojson") is False:
        out = out.parent / (out.stem + ".geojson")
    out.write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")

    print(f"矢量化用时 {dt:.1f}s")
    print(f"  指标 {stats['metric']}  阈值 {stats['threshold']}  简化容差 {stats['tol_m']} m")
    print(f"  掩膜格数 {stats['mask_cells']:,}")
    print(f"  多边形 {stats['rings']} 个（含洞 {stats['holes']} 个，"
          f"丢掉小块 {stats['dropped_small_rings']} 个）")
    print(f"  顶点合计 {stats['vertices']:,}")
    print(f"  面积 {stats['area_ha']} 公顷")
    print(f"  已写出 {out.name}（{out.stat().st_size/1024:.0f} KB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
