# -*- coding: utf-8 -*-
"""为某个视频/架次构建覆盖栅格，并（可选）出热力图。

用法：
    python -B coverage_build.py <srt 路径> [--out 输出目录] [--cell 1.0] [--png]

产物（默认写到 SRT 同目录下 coverage/ 子目录）：
    <视频名>.coverage.npz        覆盖网格（count/gsd_best/zoom_hit/clipped_hit/pass_count）
    <视频名>.coverage.json       摘要（范围、覆盖面积、分位、置信度分档统计）
    <视频名>.coverage.png        热力图（左：覆盖帧数 / 右：最优解像度）—— 加 --png
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import coverage as cov  # noqa: E402


def percentile(sorted_vals, q):
    if not sorted_vals:
        return None
    i = min(len(sorted_vals) - 1, max(0, int(len(sorted_vals) * q)))
    return sorted_vals[i]


def summarize(g: cov.CoverageGrid):
    import numpy as np
    m = g.count > 0
    if not m.any():
        return {"covered": False}
    cnt = g.count[m]
    gsd_map = g.gsd_best_map
    gsd = gsd_map[m]
    pas = g.passes()[m]
    clip = g.clipped_ratio()[m]
    zoom = g.zoom_count[m]
    area_cell = g.cell * g.cell

    cnt_s = sorted(int(v) for v in cnt)
    gsd_s = sorted(float(v) for v in gsd if v > 0)

    out = {
        "covered": True,
        "cell_m": g.cell,
        "grid": [g.ny, g.nx],
        "half_m": max(g.hx(), g.hy()),
        "half_x_m": g.hx(),
        "half_y_m": g.hy(),
        "origin": [g.lat0, g.lng0],
        "takeoff_elev_m": round(g.takeoff_elev, 3),
        "long_px": g.long_px,
        "frames_total": g.frames_total,
        "frames_used": g.frames_used,
        "frames_skipped": g.frames_skipped,
        "frames_wide": g.frames_wide,
        "frames_zoom": g.frames_zoom,
        "cells_covered": int(m.sum()),
        "area_ha": round(int(m.sum()) * area_cell / 1e4, 2),
        "count": {"p25": percentile(cnt_s, .25), "p50": percentile(cnt_s, .5),
                  "p75": percentile(cnt_s, .75), "p95": percentile(cnt_s, .95),
                  "max": cnt_s[-1]},
        "gsd_best_m_per_px": {
            "p05": round(percentile(gsd_s, .05), 3), "p25": round(percentile(gsd_s, .25), 3),
            "p50": round(percentile(gsd_s, .50), 3), "p95": round(percentile(gsd_s, .95), 3),
            "max": round(gsd_s[-1], 3)},
        "passes": {"p50": percentile(sorted(int(v) for v in pas), .5),
                   "max": int(pas.max())},
        "clipped_ratio": {
            "p50": round(percentile(sorted(float(v) for v in clip), .5), 4),
            "max": round(float(clip.max()), 4)},
        "zoom_cells": int((zoom > 0).sum()),
        "zoom_ratio": round(float((zoom > 0).mean()), 4),
    }
    for th, label in ((0.05, "5cm"), (0.10, "10cm"), (0.20, "20cm"), (0.50, "50cm")):
        n = int((gsd <= th).sum())
        out[f"resolvable_{label}_ha"] = round(n * area_cell / 1e4, 2)
    return out


def render(g: cov.CoverageGrid, path: Path, metric="count"):
    """出热力图。

    实现在 coverage_api.render_heatmap_png() —— 接口层与命令行必须**同一套配色**，
    所以只保留那一份实现；这里把内存里的网格临时落成 npz 再调它。

    metric="count" 越红 = 观测次数越多；metric="gsd" 越红 = 解像度越好。
    """
    import tempfile

    import coverage_api

    with tempfile.TemporaryDirectory(prefix="cov_render_") as td:
        tmp = Path(td) / "g.npz"
        g.save(tmp)
        kw = {"metric": metric}
        if metric == "gsd":
            kw["gsd_max"] = 0.30
        path.write_bytes(coverage_api.render_heatmap_png(tmp, **kw))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("srt")
    ap.add_argument("--out", default=None, help="输出目录（默认 <srt目录>/coverage）")
    ap.add_argument("--cell", type=float, default=1.0)
    ap.add_argument("--png", action="store_true", help="同时出热力图")
    args = ap.parse_args()

    srt = Path(args.srt).resolve()
    if not srt.is_file():
        print(f"找不到 {srt}")
        return 1
    outdir = Path(args.out) if args.out else srt.parent / "coverage"
    stem = srt.stem

    import project_manager as pm
    tele = pm.load_srt_telemetry(srt)
    recs = pm.parse_dji_srt(srt)
    step = cov.TELEMETRY_STEP
    n = tele["count"]
    lats = [recs[i]["latitude"] for i in range(0, len(recs), step)][:n]
    lngs = [recs[i]["longitude"] for i in range(0, len(recs), step)][:n]

    # 起飞点高程 = abs_alt - rel_alt（DEM 扩展的锚点）
    takeoff = 0.0
    try:
        import re as _re
        txt = srt.read_text(encoding="utf-8-sig", errors="replace")
        pairs = _re.findall(r"\[rel_alt:\s*(-?[\d.]+)\s+abs_alt:\s*(-?[\d.]+)\]", txt)
        if pairs:
            diffs = sorted(float(b) - float(a) for a, b in pairs)
            takeoff = diffs[len(diffs) // 2]
    except OSError:
        pass

    print(f"素材：{srt.name}")
    print(f"  遥测点 {n}   定位点 {len(lats)}   起飞点高程 {takeoff:.2f} m")
    t0 = time.time()
    g = cov.build_from_telemetry(tele, lats, lngs, srt_name=srt.name,
                                 cell=args.cell, takeoff_elev=takeoff)
    dt = time.time() - t0
    print(f"  网格 {g.ny}x{g.nx} @ {g.cell} m   用时 {dt:.1f} s"
          f"（{g.frames_used / max(dt, 1e-9):.0f} 帧/秒）")
    print(f"  用上 {g.frames_used} 帧（广角 {g.frames_wide} / 变焦 {g.frames_zoom}）"
          f"   跳过 {g.frames_skipped}")

    summary = summarize(g)
    outdir.mkdir(parents=True, exist_ok=True)
    npz = outdir / f"{stem}.coverage.npz"
    g.save(npz)
    js = outdir / f"{stem}.coverage.json"
    js.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  已保存 {npz.name}（{npz.stat().st_size/1024:.0f} KB）")
    print(f"  已保存 {js.name}")

    if summary.get("covered"):
        c = summary["count"]
        gs = summary["gsd_best_m_per_px"]
        print(f"  覆盖 {summary['area_ha']} 公顷   帧数 p50 {c['p50']} max {c['max']}")
        print(f"  解像 p50 {gs['p50']} m/px   可判读 20cm 内 {summary.get('resolvable_20cm_ha')} 公顷")
        cl = summary["clipped_ratio"]
        print(f"  收口帧占比 p50 {cl['p50']} max {cl['max']}"
              f"   变焦覆盖 {summary['zoom_cells']} 格（{summary['zoom_ratio']*100:.2f}%）")

    if args.png:
        png = outdir / f"{stem}.coverage.png"
        render(g, png)
        print(f"  已保存 {png.name}（{png.stat().st_size/1024:.0f} KB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
