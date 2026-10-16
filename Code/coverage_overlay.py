# -*- coding: utf-8 -*-
"""把矢量边界叠在栅格热力图上，用来肉眼核对矢量化是否忠实于栅格。

左：覆盖帧数热力图 + 轮廓；右：最优解像度热力图 + 轮廓。
轮廓线来自导出的 GeoJSON，所以这张图验证的是"矢量化有没有跑偏"。
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import coverage as cov  # noqa: E402


def ramp(t):
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        k = t / 0.5
        return (int(40 + 60 * k), int(90 + 120 * k), int(230 - 60 * k))
    k = (t - 0.5) / 0.5
    return (int(100 + 155 * k), int(210 - 140 * k), int(170 - 150 * k))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("npz")
    ap.add_argument("geojson")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    g = cov.CoverageGrid.load(Path(args.npz))
    geo = json.loads(Path(args.geojson).read_text(encoding="utf-8"))
    stat = geo["properties"]["stats"]
    print(f"网格 {g.ny}x{g.nx} @ {g.cell} m；GeoJSON {stat['rings']} 个多边形、"
          f"{stat['vertices']:,} 顶点、{stat['area_ha']} 公顷")

    ny, nx = g.ny, g.nx
    cnt = g.count
    gsd = g.gsd_best_map
    mx_cnt = int(cnt.max()) or 1
    mx_gsd = float(gsd.max()) or 1.0

    left = Image.new("RGB", (nx, ny), (250, 250, 250))
    right = Image.new("RGB", (nx, ny), (250, 250, 250))
    pl, pr = left.load(), right.load()
    for iy in range(ny):
        row = cnt[iy]
        rowg = gsd[iy]
        yy = ny - 1 - iy
        for ix in range(nx):
            v = int(row[ix])
            if v:
                pl[ix, yy] = ramp((v / mx_cnt) ** 0.35)
                gv = float(rowg[ix])
                if gv > 0:
                    pr[ix, yy] = ramp((1.0 - min(1.0, gv / mx_gsd)) ** 0.5)

    # 画矢量轮廓：经纬度 -> 像素
    mx = cov.M_PER_DEG_LNG * math.cos(math.radians(g.lat0))
    n_pt = 0
    for side in (left, right):
        d = ImageDraw.Draw(side)
        for f in geo["features"]:
            for ring in f["geometry"]["coordinates"]:
                pix = []
                for lng, lat in ring:
                    e = (lng - g.lng0) * mx
                    n = (lat - g.lat0) * cov.M_PER_DEG_LAT
                    # 网格原点是西南角，格坐标直接按偏移算
                    ix = int(e / g.cell)
                    iy = int(n / g.cell)
                    pix.append((ix, ny - 1 - iy))
                n_pt += len(pix)
                d.line(pix, fill=(20, 20, 20), width=1)

    side = Image.new("RGB", (nx * 2 + 16, ny), (255, 255, 255))
    side.paste(left, (0, 0))
    side.paste(right, (nx + 16, 0))
    d = ImageDraw.Draw(side)
    d.text((8, 8), "LEFT: frame count + vector outline", fill=(0, 0, 0))
    d.text((nx + 24, 8), "RIGHT: best resolution + same outline", fill=(0, 0, 0))
    out = Path(args.out) if args.out else Path(args.geojson).with_name(
        Path(args.geojson).stem + "_overlay.png")
    side.save(out)
    print(f"轮廓点数 {n_pt:,}；已写出 {out.name}（{out.stat().st_size/1024:.0f} KB）")


if __name__ == "__main__":
    main()
