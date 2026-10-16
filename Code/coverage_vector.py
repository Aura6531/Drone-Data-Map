# -*- coding: utf-8 -*-
"""覆盖栅格 -> 矢量多边形（P3）

## 算法：块追踪（block tracing）

栅格是二值掩膜（哪些格算"覆盖够"），边界一定由**格边**组成，
所以直接把边界格边收集起来、首尾相接成环即可 —— 不需要等值线/行进方块，
而且得到的多边形**不会自相交**、顶点数也少（台阶形）。

### 方向约定（决定环是外环还是洞）

每条边界边按「**已填充区域在行进方向左侧**」定向：

    格 (i,j) 的四个角：
        左上 (i,j)      右上 (i,j+1)
        左下 (i+1,j)    右下 (i+1,j+1)
    某条边是边界（另一侧没填充）时，按下列方向发出：
        上边：左上 -> 右上   （填充在下方 = 行进右侧）→ 所以取反：右上 -> 左上
    ……

每条边界边按「**填充格在行进方向左侧**」定向，于是：

  - **外环** 在像素坐标（行向下、列向右）里是 **顺时针**，有向面积为 **正**
  - **洞**   是 **逆时针**，有向面积为 **负**

### 为什么填充区要按 8 邻接

若把填充区当 4 邻接，两个对角相接的格子会在同一个顶点汇聚**四条**边
（"蝴蝶结"），顶点到后继的关系不唯一、环会串错。
按 8 邻接处理，边界是 8 连通闭合环，每个顶点恰好一条出边。
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from coverage import M_PER_DEG_LAT, M_PER_DEG_LNG


# ============================================================
# 0) 对角缝闭合（8 邻接的闭包）
# ============================================================

def close_diagonal_gaps(mask: np.ndarray) -> np.ndarray:
    """把"只在角上相接"的缝填上，让填充区成为 8 连通的正规区域。

    为什么必须做：两格**对角相接**时，在共享顶点处会有**两条边都指向该顶点**
    （上边一个方向、下边另一个方向），顶点→后继的关系不唯一，环会串错。
    填掉缝之后边界才是简单闭曲线，每个顶点恰好一条出边。

    规则：若某空格的对角两格都已填充，则填它自己（把斜接变成 L 形）。
    迭代到不再变化；实测通常 1~2 轮就收敛。

    副作用：面积会略微变大（每处斜接多 1 格 ≈ 1 m²）。对 1 m 网格、
    数百公顷的覆盖区来说可忽略；而且 8 邻接本来就意味着"斜着也算连通"。
    """
    out = mask.copy()
    if out.size == 0:
        return out
    while True:
        a = out[:-1, :-1]
        b = out[1:, 1:]
        c = out[:-1, 1:]
        d = out[1:, :-1]
        # 两种斜接方向
        g1 = c & d & ~a & ~b                  # 右上+左下 填充，左上+右下 为空 -> 填左上或右下
        g2 = a & b & ~c & ~d                  # 左上+右下 填充 -> 填右上或左下
        if not (g1.any() or g2.any()):
            return out
        # 每处缝只填一格（各填一个即可打破斜接）
        sub = out[:-1, :-1]
        sub[g1] = True                        # 填左上
        sub2 = out[:-1, 1:]
        sub2[g2] = True                       # 填右上


# ============================================================
# 1) 边界边提取
# ============================================================

def boundary_edges(mask: np.ndarray):
    """从二值掩膜提取定向边界边。

    返回 dict：顶点 (i,j) -> 后继顶点，每条边占一项。

    **方向约定（关键）**：让**填充格在行进方向左侧**。
    填充区按 **8 邻接**处理，于是它的边界是 8 连通闭合环，
    每个顶点恰好一条出边（不会出现"蝴蝶结"双出边）。

    在"行号向下增长"的像素坐标里，上述约定表现为
    **外环顺时针（有向面积为正）**、**洞逆时针（为负）**。
    """
    ny, nx = mask.shape
    p = np.zeros((ny + 2, nx + 2), dtype=bool)      # 边界外一律未填充
    p[1:-1, 1:-1] = mask

    nxt = {}

    def add(vi, vj, wi, wj):
        if (vi, vj) in nxt:
            raise RuntimeError(
                f"顶点 ({vi},{vj}) 有两条出边 —— 掩膜不满足 8 邻接边界假设")
        nxt[(vi, vj)] = (wi, wj)

    # 遍历每个格子的四条边；某条边外侧为空则是边界，按"填充格在左"定向。
    # 行向下、列向右时，四个方向分别是：
    #   上边 (i,j)   -> (i,j+1)    填充在南侧 = 左
    #   右边 (i,j+1) -> (i+1,j+1)  填充在西侧 = 左
    #   下边 (i+1,j+1)->(i+1,j)    填充在北侧 = 左
    #   左边 (i+1,j) -> (i,j)      填充在东侧 = 左
    up = mask & ~p[0:ny, 1:nx + 1]                  # 上邻为空
    for i, j in zip(*np.nonzero(up)):
        add(i, j, i, j + 1)
    rt = mask & ~p[1:ny + 1, 2:nx + 2]              # 右邻为空
    for i, j in zip(*np.nonzero(rt)):
        add(i, j + 1, i + 1, j + 1)
    dn = mask & ~p[2:ny + 2, 1:nx + 1]              # 下邻为空
    for i, j in zip(*np.nonzero(dn)):
        add(i + 1, j + 1, i + 1, j)
    lf = mask & ~p[1:ny + 1, 0:nx]                  # 左邻为空
    for i, j in zip(*np.nonzero(lf)):
        add(i + 1, j, i, j)

    return nxt


# ============================================================
# 2) 组装成环
# ============================================================

def assemble_rings(nxt):
    """把边集接成环。返回环的列表，每个环是顶点列表（闭合，首尾不重复）。"""
    rings = []
    remaining = dict(nxt)
    while remaining:
        start = next(iter(remaining))
        ring = [start]
        cur = remaining.pop(start)
        while cur != start:
            ring.append(cur)
            nxt_v = remaining.pop(cur, None)
            if nxt_v is None:
                # 断链：说明掩膜里有违反假设的结构，退回该环但不静默丢数据
                raise RuntimeError(f"环在顶点 {cur} 断开")
            cur = nxt_v
        rings.append(ring)
    return rings


def signed_area_px(ring):
    """像素坐标下的有向面积（鞋带公式）。外环为正、洞为负（见模块 docstring）。"""
    a = 0.0
    n = len(ring)
    for k in range(n):
        i1, j1 = ring[k]
        i2, j2 = ring[(k + 1) % n]
        a += j1 * i2 - j2 * i1          # x=j（列）, y=i（行）
    return a / 2.0


# ============================================================
# 3) 洞归属
# ============================================================

def _point_in_ring(px, py, ring):
    """射线法。ring 是像素坐标 (i,j) 列表。"""
    inside = False
    n = len(ring)
    for k in range(n):
        i1, j1 = ring[k]
        i2, j2 = ring[(k + 1) % n]
        # 用 (x=j, y=i)
        if (j1 > px) != (j2 > px):
            t = (px - j1) / (j2 - j1)
            if py < i1 + t * (i2 - i1):
                inside = not inside
    return inside


def assign_holes(exteriors, holes, max_holes=20000):
    """把洞分配给包含它的最小外环。返回 exteriors 的索引 -> 洞列表。"""
    out = [list() for _ in exteriors]
    if not holes:
        return out
    # 外环按面积绝对值从小到大试，第一个包含它的就是最内层的父环
    order = sorted(range(len(exteriors)),
                   key=lambda k: abs(signed_area_px(exteriors[k])))
    for h in holes[:max_holes]:
        hi = h[0]
        px, py = hi[1] + 0.5, hi[0] + 0.5      # 环上顶点在格角，取格内一点更稳
        for k in order:
            if _point_in_ring(px, py, exteriors[k]):
                out[k].append(h)
                break
    return out


# ============================================================
# 4) 简化（可选）
# ============================================================

def simplify_ring(ring, cell_m, tol_m):
    """Douglas-Peucker 简化台阶。tol_m <= 0 则不简化。"""
    if tol_m <= 0 or len(ring) <= 4:
        return ring
    pts = [(float(j) * cell_m, float(i) * cell_m) for i, j in ring]

    def dp(seq):
        if len(seq) < 3:
            return seq
        (x1, y1), (x2, y2) = seq[0], seq[-1]
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy)
        best, bi = -1.0, -1
        for k in range(1, len(seq) - 1):
            x, y = seq[k]
            d = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / L if L > 1e-12 else math.hypot(x - x1, y - y1)
            if d > best:
                best, bi = d, k
        if best <= tol_m or bi <= 0:
            return [seq[0], seq[-1]]
        left = dp(seq[:bi + 1])
        right = dp(seq[bi:])
        return left[:-1] + right

    # 环要当闭合折线处理：切成两半各自简化更稳
    half = len(pts) // 2
    a = dp(pts[:half + 1])
    b = dp(pts[half:] + [pts[0]])
    out = a[:-1] + b[:-1]
    return [(int(round(y / cell_m)), int(round(x / cell_m))) for x, y in out]


# ============================================================
# 5) 主入口
# ============================================================

def mask_to_rings(mask, cell_m=1.0, tol_m=0.0, close_gaps=True):
    """二值掩膜 -> (外环列表, 每个外环的洞列表)，坐标为像素顶点 (i,j)。"""
    m = close_diagonal_gaps(mask) if close_gaps else mask
    nxt = boundary_edges(m)
    rings = assemble_rings(nxt)
    exteriors, holes = [], []
    for r in rings:
        if len(r) < 4:                       # 少于 4 点不构成面
            continue
        if signed_area_px(r) > 0:              # 外环：顺时针，有向面积为正
            exteriors.append(r)
        else:
            holes.append(r)
    if tol_m > 0:
        exteriors = [simplify_ring(r, cell_m, tol_m) for r in exteriors]
        holes = [simplify_ring(r, cell_m, tol_m) for r in holes]
    hole_of = assign_holes(exteriors, holes)
    return exteriors, hole_of


def ring_to_latlng(ring, grid, cell_m=1.0):
    """像素顶点 (i,j) -> [ [lng,lat], ... ]。

    (lat0, lng0) 是网格的**西南角**，格 (i,j) 占 e∈[j·cell, (j+1)·cell)。
    行号 i 向下增长，所以纬度要按 (ny − i) 反着数（北向上）。
    """
    mx = M_PER_DEG_LNG * math.cos(math.radians(grid.lat0))
    out = []
    for i, j in ring:
        e = j * cell_m
        n = (grid.ny - i) * cell_m
        out.append([round(grid.lng0 + e / mx, 7),
                    round(grid.lat0 + n / M_PER_DEG_LAT, 7)])
    return out


# ============================================================
# 6) 从覆盖网格导出 GeoJSON
# ============================================================

def build_mask(grid, metric="count", threshold=None, gsd_max=None):
    """按指标生成二值掩膜。

    metric="count"  -> mask = count >= threshold          （"被拍到过"）
    metric="gsd"    -> mask = (0 < gsd_best <= gsd_max)   （"看得清"）
    """
    cnt = grid.count
    if metric == "count":
        th = 1 if threshold is None else int(threshold)
        return cnt >= th, th
    if metric == "gsd":
        g = grid.gsd_best_map
        gmax = 0.10 if gsd_max is None else float(gsd_max)
        return (g > 0) & (g <= gmax), gmax
    raise ValueError(f"未知指标 {metric}")


def vectorize_grid(grid, metric="count", threshold=None, gsd_max=None,
                   tol_m=0.0, min_area_cells=4, progress=None):
    """把一个 CoverageGrid 矢量化。

    返回 (features, stats)：
      features  GeoJSON Feature 列表（每个外环一个 Polygon，洞塞在里环）
      stats     统计信息（环数、洞数、面积、顶点数）

    min_area_cells 用来丢掉孤立噪点（1~3 格的碎片）。
    """
    mask, used = build_mask(grid, metric=metric, threshold=threshold, gsd_max=gsd_max)
    ny, nx = mask.shape
    before = int(mask.sum())
    exteriors, hole_of = mask_to_rings(mask, cell_m=grid.cell, tol_m=tol_m)

    # 丢小块：按像素面积（格数）过滤
    keep = [k for k, r in enumerate(exteriors)
            if abs(signed_area_px(r)) >= min_area_cells]
    dropped = len(exteriors) - len(keep)

    mx = M_PER_DEG_LNG * math.cos(math.radians(grid.lat0))
    features = []
    total_rings = total_holes = total_pts = 0

    for k in keep:
        ext = exteriors[k]
        holes = hole_of[k]
        ext_pts = ring_to_latlng(ext, grid, grid.cell)
        # GeoJSON 要求外环逆时针；这里外环在像素坐标是顺时针，
        # 转到经纬度后方向会翻（行号取反），下面显式校正。
        if _signed_area_lnglat(ext_pts) < 0:
            ext_pts = ext_pts[::-1]
        rings = [ext_pts]
        for h in holes:
            if abs(signed_area_px(h)) < min_area_cells:
                continue
            h_pts = ring_to_latlng(h, grid, grid.cell)
            if _signed_area_lnglat(h_pts) > 0:
                h_pts = h_pts[::-1]
            rings.append(h_pts)
        # RFC 7946：线性环必须闭合（首尾坐标相同）
        rings = [_close_ring(r) for r in rings]
        cells = abs(signed_area_px(ext)) - sum(abs(signed_area_px(h)) for h in holes)
        props = {
            "metric": metric,
            "threshold": used,
            "cell_m": grid.cell,
            "cells": int(round(cells)),
            "area_m2": round(cells * grid.cell * grid.cell, 1),
            "area_ha": round(cells * grid.cell * grid.cell / 1e4, 4),
            "holes": len(rings) - 1,
            "vertices": len(ext_pts) + sum(len(r) for r in rings[1:]),
            "source_srt": grid.srt_name,
            "type": "hard_boundary_or_clipped",
        }
        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Polygon", "coordinates": rings},
        })
        total_rings += 1
        total_holes += len(rings) - 1
        total_pts += props["vertices"]

    stats = {
        "metric": metric, "threshold": used, "cell_m": grid.cell,
        "grid": [ny, nx],
        "mask_cells": before,
        "rings": total_rings,
        "holes": total_holes,
        "vertices": total_pts,
        "dropped_small_rings": dropped,
        "area_ha": round(sum(f["properties"]["area_ha"] for f in features), 3),
        "tol_m": tol_m,
    }
    return features, stats


def _close_ring(pts):
    """RFC 7946：线性环首尾坐标必须相同、且至少 4 个坐标。"""
    if not pts:
        return pts
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    while len(pts) < 4:                    # 退化环至少凑到 4 点
        pts = pts[:-1] + [pts[0]] + [pts[-1]] if len(pts) < 4 else pts
        break
    return pts


def _signed_area_lnglat(pts):
    """经纬度环的有向面积（只用符号，不换算米）。"""
    a = 0.0
    n = len(pts)
    for k in range(n):
        x1, y1 = pts[k]
        x2, y2 = pts[(k + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def to_geojson(grid, **kw):
    """直接产出完整 GeoJSON FeatureCollection（含元数据）。"""
    from datetime import datetime
    feats, stats = vectorize_grid(grid, **kw)
    meta = {
        "generator": "coverage_vector.py (block tracing)",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_srt": grid.srt_name,
        "origin": [grid.lat0, grid.lng0],
        "takeoff_elev_m": round(grid.takeoff_elev, 3),
        "accuracy_note": (
            "Flat-ground model; footprint boundary uncertainty is described by "
            "coverage.sigma_footprint(). The whole map also carries a GNSS positioning "
            "offset. Attitude accuracy is estimated from the SRT quantisation step plus "
            "a safety margin, and has not been verified against a surveyed target. "
            "Boundary types: an edge derived entirely from real geometry is a "
            "hard_boundary; any part that relies on the 12x-height far-edge cap is "
            "clipped (this file does not distinguish them per vertex — use the "
            "query() 'type' field for that)."
        ),
    }
    return {"type": "FeatureCollection", "features": feats,
            "properties": {"stats": stats, "meta": meta}}, stats
