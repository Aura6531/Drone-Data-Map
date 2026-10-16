# -*- coding: utf-8 -*-
"""覆盖栅格的 HTTP 接口层（给 project_manager.py 用）

放在单独模块里，避免继续把 project_manager.py 撑大。
**依赖 numpy**：没有 numpy 时所有函数抛 CoverageUnavailable，由接口层转成友好提示。

## 落盘规则

覆盖网格存在**项目目录下**（与 project.json 同处），而不是散在原始素材目录里：

    Project/<项目名>/coverage/<视频名>.npz
    Project/<项目名>/coverage/<视频名>.json      摘要
    Project/<项目名>/coverage/<视频名>.meta.json 源 SRT 路径 + 修改时间（用于判断是否需要重建）

`.npz` 里已经带 origin / cell / 各数组，所以单独一个文件也能查。
"""

from __future__ import annotations

import io
import json
import hashlib
import math
import time
from pathlib import Path

try:
    import numpy as np
except ImportError:                     # pragma: no cover
    np = None


class CoverageUnavailable(RuntimeError):
    """缺少 numpy —— 覆盖功能需要它。"""


def _need_numpy():
    if np is None:
        raise CoverageUnavailable(
            "Coverage needs numpy. Please run the backend with a Python that has "
            "numpy installed (for example the one bundled with the packaged runtime)."
        )


# ============================================================
# 路径与清单
# ============================================================

def coverage_dir(project_name: str) -> Path:
    """项目下的覆盖目录（与 project.json 同级）。"""
    # 延迟 import，避免与 project_manager 循环依赖
    import project_manager as pm
    return pm.PROJECT_DIR / project_name / "coverage"


def find_srt_files(folders):
    """在项目登记的文件夹里找所有 .srt。返回按路径排序的列表。"""
    out = []
    for f in folders or []:
        if not f:
            continue
        root = Path(f)
        if not root.is_dir():
            continue
        # 只下探一层：DJI 的架次目录结构就是 素材根/架次/文件
        for p in sorted(root.glob("*.srt")) + sorted(root.glob("*/*.srt")):
            if p.is_file():
                out.append(p)
    # 去重（两个 glob 可能命中同一个）
    seen, uniq = set(), []
    for p in out:
        k = str(p.resolve()).lower()
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq


def _stem_key(srt_path: Path) -> str:
    """网格文件名：视频名 + 源路径哈希（不同架次同名视频也不会撞）。"""
    h = hashlib.sha1(str(srt_path.resolve()).lower().encode("utf-8")).hexdigest()[:8]
    return f"{srt_path.stem}.{h}"


def grid_path(project_name: str, srt_path: Path) -> Path:
    return coverage_dir(project_name) / f"{_stem_key(srt_path)}.npz"


def _meta_path(npz: Path) -> Path:
    return npz.with_suffix(".meta.json")


def _srt_mtime(srt_path: Path) -> float:
    try:
        return srt_path.stat().st_mtime
    except OSError:
        return 0.0


def is_old_format(npz: Path) -> bool:
    """旧版网格：origin 是**中心**、只有单一 half。

    新版 origin 是西南角、有 half_x/half_y。两者不能互换 —— 按新语义读旧网格
    会让坐标整体偏移半个网格宽（热力图和点查询都静默错位）。
    所以这种网格一律视为"需要重建"。
    """
    if np is None or not npz.is_file():
        return False
    try:
        with np.load(npz) as z:
            return "half_x" not in z.files
    except (OSError, ValueError):
        return True          # 读不出来也当它需要重建


def is_stale(npz: Path, srt_path: Path) -> bool:
    """源 SRT 比网格新、元数据丢失、或网格是旧格式 —— 都该重建。"""
    if not npz.is_file():
        return True
    if is_old_format(npz):
        return True
    mp = _meta_path(npz)
    if not mp.is_file():
        return True
    try:
        meta = json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return abs(float(meta.get("srt_mtime", -1)) - _srt_mtime(srt_path)) > 1e-6


def list_coverage(project_name: str, folders=None) -> dict:
    """列出项目里每个 SRT 对应的覆盖状态（有没有网格、是不是过期）。"""
    cdir = coverage_dir(project_name)
    items = []
    for srt in find_srt_files(folders):
        npz = grid_path(project_name, srt)
        item = {
            "srt": str(srt),
            "srt_name": srt.name,
            "video_name": srt.stem,
            "folder": str(srt.parent),
            "built": npz.is_file(),
            "stale": is_stale(npz, srt),
            "old_format": is_old_format(npz),
            "npz": str(npz) if npz.is_file() else None,
            "size_kb": round(npz.stat().st_size / 1024) if npz.is_file() else 0,
        }
        js = npz.with_suffix(".json")
        if js.is_file():
            try:
                item["summary"] = json.loads(js.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        items.append(item)
    return {
        "ok": True,
        "project": project_name,
        "coverage_dir": str(cdir),
        "has_numpy": np is not None,
        "items": items,
    }


# ============================================================
# 构建
# ============================================================

def _takeoff_elev(srt_path: Path) -> float:
    """起飞点高程 = 中位(abs_alt − rel_alt)。也是将来接 DEM 的锚点。"""
    import re
    try:
        txt = srt_path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return 0.0
    pairs = re.findall(r"\[rel_alt:\s*(-?[\d.]+)\s+abs_alt:\s*(-?[\d.]+)\]", txt)
    if not pairs:
        return 0.0
    diffs = sorted(float(b) - float(a) for a, b in pairs)
    return diffs[len(diffs) // 2]


def build_coverage(project_name: str, srt_path, cell=1.0, force=False,
                   progress=None) -> dict:
    """为一个 SRT 建覆盖网格（已有且不旧就直接复用）。"""
    _need_numpy()
    import project_manager as pm
    import coverage as cov

    srt = Path(srt_path)
    if not srt.is_file():
        raise FileNotFoundError(f"SRT not found: {srt}")

    npz = grid_path(project_name, srt)
    if npz.is_file() and not force and not is_stale(npz, srt):
        g = cov.CoverageGrid.load(npz)
        return {"reused": True, "npz": str(npz), **summarize_grid(g)}

    tele = pm.load_srt_telemetry(srt)
    recs = pm.parse_dji_srt(srt)
    step = cov.TELEMETRY_STEP
    n = tele["count"]
    lats = [recs[i]["latitude"] for i in range(0, len(recs), step)][:n]
    lngs = [recs[i]["longitude"] for i in range(0, len(recs), step)][:n]

    t0 = time.time()
    g = cov.build_from_telemetry(tele, lats, lngs, srt_name=srt.name,
                                 cell=float(cell),
                                 takeoff_elev=_takeoff_elev(srt),
                                 progress=progress)
    elapsed = time.time() - t0

    npz.parent.mkdir(parents=True, exist_ok=True)
    g.save(npz)
    # 同名 .json：与命令行工具 coverage_build.py 的产物一致
    summary = summarize_grid(g)
    npz.with_suffix(".json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _meta_path(npz).write_text(json.dumps({
        "srt": str(srt.resolve()),
        "srt_mtime": _srt_mtime(srt),
        "cell": float(cell),
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_s": round(elapsed, 1),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"reused": False, "elapsed_s": round(elapsed, 1),
            "npz": str(npz), **summary}


def _percentile(sorted_vals, q):
    if not sorted_vals:
        return None
    i = min(len(sorted_vals) - 1, max(0, int(len(sorted_vals) * q)))
    return sorted_vals[i]


def summarize_grid(g) -> dict:
    """从网格算摘要（与 coverage_build.py 的口径一致）。"""
    m = g.count > 0
    if not m.any():
        return {"covered": False}
    cnt = g.count[m]
    gsd = g.gsd_best_map[m]
    pas = g.passes()[m]
    clip = g.clipped_ratio()[m]
    area_cell = g.cell * g.cell
    cnt_s = sorted(int(v) for v in cnt)
    gsd_s = sorted(float(v) for v in gsd if v > 0)
    out = {
        "covered": True,
        "cell_m": g.cell,
        "grid": [int(g.ny), int(g.nx)],
        "origin": [g.lat0, g.lng0],
        "half_m": max(g.hx(), g.hy()),
        "half_x_m": g.hx(),
        "half_y_m": g.hy(),
        "takeoff_elev_m": round(g.takeoff_elev, 3),
        "long_px": int(g.long_px),
        "frames_total": g.frames_total,
        "frames_used": g.frames_used,
        "frames_skipped": g.frames_skipped,
        "frames_wide": g.frames_wide,
        "frames_zoom": g.frames_zoom,
        "cells_covered": int(m.sum()),
        "area_ha": round(int(m.sum()) * area_cell / 1e4, 3),
        "count": {"p25": _percentile(cnt_s, .25), "p50": _percentile(cnt_s, .5),
                  "p75": _percentile(cnt_s, .75), "p95": _percentile(cnt_s, .95),
                  "max": cnt_s[-1]},
        "gsd_best_m_per_px": {
            "p05": round(_percentile(gsd_s, .05), 4),
            "p25": round(_percentile(gsd_s, .25), 4),
            "p50": round(_percentile(gsd_s, .50), 4),
            "p95": round(_percentile(gsd_s, .95), 4),
            "max": round(gsd_s[-1], 4)},
        "passes": {"p50": _percentile(sorted(int(v) for v in pas), .5),
                   "max": int(pas.max())},
        "clipped_ratio": {
            "p50": round(_percentile(sorted(float(v) for v in clip), .5), 4),
            "max": round(float(clip.max()), 4)},
        "zoom_cells": int((g.zoom_count > 0).sum()),
    }
    for th, label in ((0.05, "5cm"), (0.10, "10cm"), (0.20, "20cm"), (0.50, "50cm")):
        out[f"resolvable_{label}_ha"] = round(
            int((gsd <= th).sum()) * area_cell / 1e4, 3)
    return out


# ============================================================
# 查询
# ============================================================

def query_point(project_name, npz_path, lat, lng, cfg=None) -> dict:
    """点查询：这个经纬度被拍到没有、看多清、多大把握。"""
    _need_numpy()
    import coverage as cov
    g = cov.CoverageGrid.load(Path(npz_path))
    # 网格范围外的点直接说清楚，别让前端去猜
    r = g.query(float(lat), float(lng), cfg=cfg)
    r["project"] = project_name
    r["grid"] = {"cell_m": g.cell, "origin": [g.lat0, g.lng0],
                 "half_m": max(g.hx(), g.hy()),
                 "half_x_m": g.hx(), "half_y_m": g.hy()}
    return r


# ============================================================
# 热力图（PNG）
# ============================================================

# 离散色带：避免连续渐变被误读成"精确值"（与置信度文档里的建议一致）
_BANDS = [
    (0.00, (242, 242, 242)),      # 无覆盖
    (0.15, (198, 226, 255)),      # 很低：淡蓝
    (0.35, (150, 232, 175)),      # 低：淡绿
    (0.55, (255, 224, 130)),      # 中：淡黄
    (0.75, (255, 160, 90)),       # 高：橙
    (1.00, (222, 60, 60)),        # 很高：红
]


def _band_color(t):
    t = max(0.0, min(1.0, t))
    for i in range(len(_BANDS) - 1):
        a, ca = _BANDS[i]
        b, cb = _BANDS[i + 1]
        if t <= b or i == len(_BANDS) - 2:
            k = 0.0 if b <= a else (t - a) / (b - a)
            k = max(0.0, min(1.0, k))
            return tuple(int(ca[j] + (cb[j] - ca[j]) * k) for j in range(3))
    return _BANDS[-1][1]


def render_heatmap_png(npz_path, metric="count", max_side=1400,
                       count_percentile=0.98, gsd_max=None) -> bytes:
    """把网格渲成 PNG。

    用**分位数上限**而不是最大值做归一化 —— 否则个别驻留上千帧的格子
    会把整张图压成一片蓝，什么都看不出来。

    metric="count"  越红 = 观测次数越多
    metric="gsd"    越红 = 解像度越好（米/像素越小）
    """
    _need_numpy()
    from PIL import Image
    import coverage as cov

    g = cov.CoverageGrid.load(Path(npz_path))
    ny, nx = g.ny, g.nx
    step = max(1, int(math.ceil(max(ny, nx) / float(max_side))))
    H = len(range(0, ny, step))
    W = len(range(0, nx, step))

    cnt = g.count[::step, ::step].astype(np.int64)
    gsd = g.gsd_best_map[::step, ::step].astype(np.float64)

    buf = np.zeros((H, W, 3), dtype=np.uint8)
    buf[:, :] = (250, 250, 250)
    m = cnt > 0

    if metric == "gsd":
        gmax = float(gsd_max) if gsd_max else 0.30
        t = np.zeros_like(gsd)
        ok = m & (gsd > 0)
        t[ok] = 1.0 - np.clip(gsd[ok] / gmax, 0.0, 1.0)
    else:
        vals = np.sort(cnt[m])
        if vals.size:
            hi = vals[min(vals.size - 1, int(vals.size * count_percentile))]
        else:
            hi = 1
        hi = max(1, float(hi))
        t = np.zeros_like(gsd)
        # 0.4 次幂：让低覆盖也能看出层次，不然全挤在蓝色端
        t[m] = np.clip(cnt[m] / hi, 0.0, 1.0) ** 0.4

    idx = np.clip((t * (len(_BANDS) - 1)).astype(np.int64), 0, len(_BANDS) - 1)
    for i, (_, c) in enumerate(_BANDS):
        sel = m & (idx == i)
        buf[sel] = c
    # 行号向下 -> north-up 要翻转
    img = Image.fromarray(buf[::-1], mode="RGB")
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def render_overlay_png(npz_path, rings, metric="count", max_side=1400,
                       count_percentile=0.98, gsd_max=None) -> bytes:
    """热力图 + 矢量轮廓叠加（把已导出的多边形画上去，核对用）。"""
    _need_numpy()
    from PIL import Image, ImageDraw
    import coverage as cov

    base = render_heatmap_png(npz_path, metric=metric, max_side=max_side,
                              count_percentile=count_percentile, gsd_max=gsd_max)
    img = Image.open(io.BytesIO(base)).convert("RGB")
    g = cov.CoverageGrid.load(Path(npz_path))
    ny, nx = g.ny, g.nx
    step = max(1, int(math.ceil(max(ny, nx) / float(max_side))))
    d = ImageDraw.Draw(img)
    mx = cov.M_PER_DEG_LNG * math.cos(math.radians(g.lat0))
    for f in (rings or {}).get("features", []):
        for ring in f.get("geometry", {}).get("coordinates", []):
            pts = []
            for lng, lat in ring:
                e = (lng - g.lng0) * mx
                n = (lat - g.lat0) * cov.M_PER_DEG_LAT
                # 网格原点是西南角，所以格坐标直接按偏移算，不用再加 half
                col = (e / g.cell) / step
                row = (n / g.cell) / step
                pts.append((col, (ny / step) - row))
            if len(pts) >= 2:
                d.line(pts, fill=(20, 20, 20), width=1)
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


# ============================================================
# 矢量导出
# ============================================================

def export_geojson(project_name, npz_path, metric="count", threshold=None,
                   gsd_max=None, tol_m=0.0, min_area_cells=4) -> dict:
    """栅格 -> GeoJSON（在服务端算好，前端直接拿去贴图）。"""
    _need_numpy()
    import coverage as cov
    import coverage_vector as cvv

    g = cov.CoverageGrid.load(Path(npz_path))
    geo, stats = cvv.to_geojson(g, metric=metric, threshold=threshold,
                                gsd_max=gsd_max, tol_m=tol_m,
                                min_area_cells=min_area_cells)
    geo["properties"]["stats"]["project"] = project_name
    return geo


def write_geojson(project_name, npz_path, out_path=None, **kw) -> Path:
    """导出并把文件落到覆盖目录（方便用户直接拿走）。"""
    geo = export_geojson(project_name, npz_path, **kw)
    npz = Path(npz_path)
    if out_path is None:
        tag = kw.get("metric", "count")
        th = kw.get("threshold")
        gm = kw.get("gsd_max")
        suffix = f"{tag}{th}" if tag == "count" else f"gsd{gm}"
        out_path = npz.with_name(f"{npz.stem}_{suffix}.geojson")
    out_path = Path(out_path)
    out_path.write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")
    return out_path


# ============================================================
# 「这个位置被哪些画面拍到过」—— 跨架次的取证检索
# ============================================================

VIDEO_EXTS = (".mp4", ".mov", ".MP4", ".MOV")

# 起播往前倒的秒数。必须与前端 PHOTO_PREROLL_SECONDS 一致 ——
# 前端要靠它算倒计时显示，两边不一致会出现"倒数到 1 但还没到画面"。
FIND_PREROLL_SECONDS = 3

# 同一架次里相邻命中帧至少隔这么久才算"另一趟"。
# 为什么要按趟分组、而不是每架次只给最清的一条：同一架次会来回飞好几趟，
# 每趟的角度/高度/清晰度都不同 —— 那正是用户想看的"不同画面"。
# 实测某个点：一个架次要经过 4 趟、另一个 9 趟，合计 13 个不同画面，
# 而"每架次只给一帧"会把其中 11 个藏起来（用户当场就发现了）。
FIND_PASS_GAP_SECONDS = 8.0
# 相邻两趟再近于这个间隔的，只留最清的一条（避免把一次连续观察切成两条）
FIND_DEDUP_SECONDS = 5.0

# ---- 「只看不同视角」模式（mode=angles）的去重阈值 ----
# 为什么需要这一档：**地面有遮挡物**。最清晰的那张可能正好被树/楼挡住，
# 而另一张没那么清晰、但从另一个位置看过去恰好没被挡 —— 那才是用户要的。
# 所以对"找不同画面"这个诉求，**视角差异比清晰度排序更重要**。
# 实测某点 7 趟里，方位角分布很散（同一段航线上来回扫），
# 这一档会把方位/俯角接近的合并成一条，只留其中最清晰的。
FIND_ANGLE_BEARING_DEG = 25.0     # 方位角差小于这个度数算"同一个视角"
FIND_ANGLE_PITCH_DEG = 12.0       # 俯角差小于这个度数算"同一个视角"

FIND_MODES = ("best", "passes", "angles")

# 目标必须落在画面**内缩这个比例**的范围内才算合格。
#
# 为什么（用户 2026-10-13）：「查找出来这种效果其实是不好的，特别是下边缘和侧面
# 边缘点，虽然理论上像素-实际物体大小的数值达到了最优，但因为目标在画面边上被
# 切割，人看不出来是什么情况。考虑增加设置一个到边界 10% 左右的隐性限制。」
#
# 也就是：解像度最优 ≠ 能看清是什么。目标贴着画面边被切掉时无法判读，
# 所以宁可退而取一张"稍微糊一点但目标完整在画面里"的帧。
#
# 用户看过 10% 的效果后定为 **25%**，并要求做成**可调选项**。
# 0.25 = 四边各内缩 25%，即 |xi| 与 |yi| 都必须 <= 0.75。
#
# 实测（10 个位置、四个档位）：0/10/25/40% 都**没有**把任何位置挡成 0 条；
# 25% 比 10% 只少 0~2 条；40% 开始明显掉（有的点从 7 条掉到 4 条）。
# 而 0% 限制下的命中里 **76%** 的边距 < 25% —— 说明这个限制相当必要。
FIND_FRAME_INSET = 0.25
# 允许范围：0 = 不限制；上限 0.45 是防呆（再往内目标就没地方站了）
FIND_FRAME_INSET_MAX = 0.45

# 「居中」程度 —— 目标离画面中心多远就终止算"居中"。
# 注意这是**终止线**，不是唯一的排序键：排序键是离中心的偏移本身（越小越靠前），
# 这个值只用来决定一条命中归入哪一类（见 find_frames 里的 category）。
#
# 取 0.40：目标落在画面中间 60%×60% 的区域里 —— 与用户画的那个红框
# （实测约 63%×60%）量级一致。
FIND_CENTRAL_MARGIN = 0.40

# 抽帧缓存：key = 视频路径 + 时间 + 宽度，值 = 磁盘上的 jpg。
# 不做内存缓存 —— ffmpeg 是子进程，进程重启就没了，落盘反而更省事也更稳。
THUMB_DIR_NAME = ".thumbs"


def _video_of_srt(srt_path: Path) -> Path | None:
    """SRT 同名的视频文件（DJI 的 SRT 与 MP4 同名同目录）。"""
    for ext in (".MP4", ".mp4", ".MOV", ".mov"):
        cand = srt_path.with_suffix(ext)
        if cand.is_file():
            return cand
    # 退一步：同目录下找同名不同大小写的
    stem = srt_path.stem.lower()
    for p in srt_path.parent.iterdir():
        if p.is_file() and p.stem.lower() == stem and p.suffix.lower() in (".mp4", ".mov"):
            return p
    return None


def _locate_in_project(project, video_path: Path):
    """把视频文件对回 (folder_index, relative_path) —— 前端开视频要这两个。"""
    for idx, item in enumerate(project.get("folders") or []):
        folder = item.get("path")
        if not folder:
            continue
        try:
            root = Path(folder).expanduser().resolve()
            rel = video_path.resolve().relative_to(root)
        except (ValueError, OSError):
            continue
        return idx, str(rel).replace("\\", "/")
    return None, None


def make_thumbnail(video_path: Path, time_seconds: float, width=480,
                   cache_dir: Path | None = None) -> Path:
    """从原片抽一帧做缩略图（带磁盘缓存）。

    缓存 key 里带上时间（保留 2 位小数），所以同一个位置反复看不会重复抽帧。
    """
    import project_manager as pm

    video_path = Path(video_path)
    cache_dir = Path(cache_dir) if cache_dir else (video_path.parent / THUMB_DIR_NAME)
    cache_dir.mkdir(parents=True, exist_ok=True)

    key = f"{video_path.stem}_{float(time_seconds):.2f}_{int(width)}".replace(".", "_")
    # 用哈希避免不同视频同名相撞
    h = hashlib.sha1(f"{video_path}|{time_seconds:.2f}|{width}".encode("utf-8")).hexdigest()[:10]
    out = cache_dir / f"t_{h}.jpg"

    if out.is_file() and out.stat().st_size > 0:
        return out

    ffmpeg = pm.find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg not found, so no frame can be extracted. "
            "Install ffmpeg and restart the service.")

    import subprocess
    import tempfile

    # 先出 PNG 再用 Pillow 转 JPEG：ffmpeg 的 JPEG 头不带 JFIF，
    # 这条链路上虽不喂 docx，但统一走同一条路省得以后踩。
    with tempfile.TemporaryDirectory(prefix="cov_thumb_") as td:
        png = Path(td) / "f.png"
        cmd = [
            ffmpeg, "-y", "-loglevel", "error",
            "-ss", f"{max(0.0, float(time_seconds)):.3f}",
            "-i", str(video_path),
            "-frames:v", "1",
            "-vf", f"scale={int(width)}:-2",
            str(png),
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=120)
        if not png.is_file() or png.stat().st_size == 0:
            err = (proc.stderr or b"").decode("utf-8", "replace")[:200]
            raise RuntimeError(f"Could not extract a frame at {time_seconds:.2f}s. {err}")

        from PIL import Image
        with Image.open(png) as im:
            im.convert("RGB").save(out, format="JPEG", quality=82, optimize=True)

    return out


def find_frames(project_name, lat, lng, limit=60, max_gsd=None,
                folder_index=None, srt_path=None, mode="passes",
                frame_inset=None) -> dict:
    """找「这个经纬度被哪些画面拍到过」。

    遍历该项目的所有覆盖网格，对**每一个架次**扫出真正把这一点看在画面里的帧，
    再按 `mode` 决定给哪些：

    | mode | 给什么 | 什么时候用 |
    |---|---|---|
    | `best`   | 全场最清晰的 **1** 张 | 只想知道"看得最清是什么样" |
    | `passes` | **每个独立趟次 1 张**（该趟最清的那帧） | 想看这块地被拍过几次（默认） |
    | `angles` | **每种视角 1 张**（方位/俯角接近的算同一视角，只留最清的） | 想找"换个角度还能不能看到" |

    `angles` 是为**遮挡**准备的：最清晰的那张可能正好被树/楼挡住，
    而另一张没那么清晰、但从另一个方向看过去恰好没被挡。
    所以这一档**不能靠清晰度代替**，必须按视角去重。

    每条都带 `start_seconds`（往前 N 秒起播）、`target_seconds`（到这一刻自动停）、
    `folder_index` / `relative_path`（前端开视频要这两个）、
    以及 `bearing_deg` / `elev_deg`（这一趟是从哪个方向看过去的）。
    """
    _need_numpy()
    import project_manager as pm
    import coverage as cov

    project = pm.load_project(project_name)
    folders = [item.get("path") for item in (project.get("folders") or [])
               if item.get("path")]

    scan_srts = [Path(srt_path)] if srt_path else find_srt_files(folders)
    if not scan_srts:
        return {"ok": True, "hits": [], "note": "This project has no SRT files."}

    # 边距内缩：默认取模块常量，调用方可按需覆盖（界面上是个选项）。
    # 注意用 `is not None` 判 —— 0 是合法值（= 不限制），别被 `or` 当成缺省。
    inset = FIND_FRAME_INSET if frame_inset is None else float(frame_inset)
    inset = min(max(inset, 0.0), FIND_FRAME_INSET_MAX)
    # 目标允许的归一化坐标上限（|xi|,|yi| 都得 <= 它）。
    # 必须在逐帧循环**之前**算好 —— 循环里要用它筛帧。
    lim = 1.0 - inset

    hits, skipped, partial = [], [], []
    for srt in scan_srts:
        npz = grid_path(project_name, srt)
        if not npz.is_file():
            skipped.append({"srt": srt.name, "why": "no coverage grid built yet"})
            continue
        if is_stale(npz, srt):
            skipped.append({"srt": srt.name, "why": "source changed — rebuild needed"})
            continue

        video = _video_of_srt(srt)
        if video is None:
            skipped.append({"srt": srt.name, "why": "no matching video file found"})
            continue
        fidx, rel = _locate_in_project(project, video)
        if fidx is None:
            skipped.append({"srt": srt.name, "why": "video is not inside this project's folders"})
            continue

        g = cov.CoverageGrid.load(npz)
        ix, iy = g.cell_of(lat, lng)
        if not g.inside(ix, iy):
            continue
        n = int(g.count[iy, ix])
        if n <= 0:
            continue

        # ------------------------------------------------------------------
        # 找出**所有**真正包含这一点的帧，而不是只信 frame_at_min 那一帧。
        #
        # 为什么要这样：
        #   ① frame_at_min 记的是「覆盖该格的所有帧里 GSD 最好的那一帧」，
        #      它不一定真的看到这一格 —— 栅格化的规则是"格子与足迹有重叠就算"，
        #      所以边界格的中心可能落在那一帧的画面之外。
        #   ② 更要紧的是**收口帧**：收口把远边沿径向缩成一条弧，四角多边形被扭歪，
        #      会给出"在足迹内、其实在画面外"的格子。实测收口帧上 26% 的命中如此。
        #
        # 所以这里用**精确的射影判定**（把点投到画面看 |xi|,|yi| <= 1），
        # 并且对每个架次扫一遍全部帧。一个架次一万多帧、每帧 O(1)，几十毫秒。
        # ------------------------------------------------------------------
        recs = pm.parse_dji_srt(srt)
        tele = pm.load_srt_telemetry(srt)
        step = cov.TELEMETRY_STEP
        # 时刻优先用**网格里存的** frame_times（建网格时从 SRT cue 时间抄下来的，
        # 与视频时间轴一致）；网格没有就退回遥测接口的 times。
        gt = getattr(g, "frame_times", None) or []
        times = gt if len(gt) >= g.frames_total else (tele.get("times") or [])
        if len(recs) < 2 or len(times) < 2:
            skipped.append({"srt": srt.name, "why": "SRT has no usable positioning"})
            continue

        tgt = (lat, lng)
        cos_lat = math.cos(math.radians(lat))
        # 收集**所有**真的把这点看在画面里的帧（不求最优，后面按趟分组再挑）
        found = []
        edge_rejected = 0
        for fi in range(g.frames_total):
            alt = g.frame_alt[fi]
            if alt <= 0:
                continue
            j = fi * step
            if j >= len(recs):
                break
            drone = (recs[j]["latitude"], recs[j]["longitude"])
            foc = g.frame_focal[fi] or 24.0
            yaw = g.frame_yaw[fi]
            pit = g.frame_pitch[fi]

            # ---- 便宜的预筛：目标必须落在这帧足迹的包围盒里 ----
            # 曾试过"用方位/俯仰与相机姿态对比"来做预筛，理论上更快，
            # 但**符号很容易搞反**（`ang` 是仰角为正，`pit` 是俯角为负，
            # 夹角应当是 |ang + pit| 而不是 |ang − pit|）——
            # 我第一版就是写成了相减，于是漏掉了正确答案（命中的帧全变了）。
            # 这里宁可慢一点，用已经验证过的包围盒。
            tgt_e = (lng - drone[1]) * cov.M_PER_DEG_LNG * cos_lat
            tgt_n = (lat - drone[0]) * cov.M_PER_DEG_LAT
            clip = max(cov.CLIP_MIN, cov.CLIP_PER_ALT * alt)
            poly, clipped = cov.frame_footprint(alt, yaw, pit, foc, clip)
            if poly is None:
                continue
            xs = (poly[0][0], poly[1][0], poly[2][0], poly[3][0])
            ys = (poly[0][1], poly[1][1], poly[2][1], poly[3][1])
            if not (min(xs) <= tgt_e <= max(xs) and min(ys) <= tgt_n <= max(ys)):
                continue

            # ---- 精确判定：把点投到画面，必须落在**内缩一圈**的范围里 ----
            # 不能只判 |xi|<=1：贴着画面边被切掉的目标没法判读（见 FIND_FRAME_INSET）。
            xi, yi, inside = cov.ground_point_in_frame(drone, alt, yaw, pit, foc, tgt)
            if xi is None or not inside:
                continue
            if abs(xi) > lim or abs(yi) > lim:
                edge_rejected += 1
                continue

            slant = math.hypot(math.hypot(tgt_e, tgt_n), alt)
            gsd = slant * cov.rad_per_px(foc, g.long_px)
            if max_gsd is not None and gsd > float(max_gsd) + 1e-9:
                continue
            found.append({"fi": fi, "gsd": gsd, "alt": alt, "foc": foc,
                          "yaw": yaw, "pit": pit, "xi": xi, "yi": yi,
                          "clipped": clipped})

        if not found:
            # 这一格在网格里"被覆盖过"，但没有任何一帧真的把这一点看在画面里
            # （边界格 / 收口帧的常见情况）。如实说明，不硬拿一帧充数。
            why = ("covered — but no frame actually has this point inside the image"
                   if not edge_rejected else
                   "covered — but in every frame that saw it the point sits within "
                   f"{int(FIND_FRAME_INSET * 100)}% of the frame edge (too close to the "
                   "border to read)")
            partial.append({"srt": srt.name, "why": why, "frames": n})
            continue

        # ------------------------------------------------------------------
        # 按**独立趟次**分组，每趟给一条（该趟里最清的那帧）。
        #
        # 为什么不是"每架次只给一条"：同一架次会来回飞好几趟，每趟的角度、
        # 高度、清晰度都不同 —— 那正是用户想看的"不同画面"。
        # 实测某个点：架次 A 经过 4 趟、架次 B 经过 9 趟，合计 13 个不同画面；
        # "每架次一条"只给 2 条，用户立刻发现"应该多次拍到却只出一条"。
        #
        # 也不是"每帧一条"：一个趟次内相邻帧几乎一样（实测一个趟次 1211 帧），
        # 全列出来只是噪声。所以趟内取最优。
        # ------------------------------------------------------------------
        found.sort(key=lambda r: r["fi"])
        passes = []
        for r in found:
            # 时刻**必须**从 times[] 取 —— 它是 SRT 的 cue 时间，与视频时间轴一致。
            # 曾经写成 `fi * TELEMETRY_STEP / 30`，那是把"采样下标"当成了"视频帧号"：
            #   采样下标 11793 的 cue 时间是 1197.0 s，而 11793/10 = 1179.3 s —— 差 17.7 s。
            # 用户报的"地图上位置差了很远"就是这个（实测差 228 m，
            # 用画面里 DJI 烧录的 OSD 经纬度核对出来的）。
            t = float(times[r["fi"]]) if r["fi"] < len(times) else 0.0
            if passes and t - passes[-1][-1][0] <= FIND_PASS_GAP_SECONDS:
                passes[-1].append((t, r))
            else:
                passes.append([(t, r)])

        for grp in passes:
            best = min((r for _, r in grp), key=lambda r: r["gsd"])
            fi = best["fi"]
            gsd = best["gsd"]
            if gsd <= 0:
                continue
            # 视频时刻 = 该采样点的 cue 时间（唯一权威来源）
            target = float(times[fi]) if fi < len(times) else 0.0
            t_from = grp[0][0]
            t_to = grp[-1][0]
            # 这一趟是从哪个方向看过去的 —— 用**无人机->目标**算，不用相机 yaw
            # （云台会独立转，frame_yaw 不一定对着目标）。
            j_best = fi * cov.TELEMETRY_STEP
            _bearing, _elev = cov.bearing_elevation(
                (recs[j_best]["latitude"], recs[j_best]["longitude"]),
                best["alt"], tgt)
            hits.append({
                "srt": str(srt),
                "srt_name": srt.name,
                "video_path": str(video),
                "video_name": video.stem,
                "folder_index": fidx,
                "relative_path": rel,
                # `frame` 是**遥测采样下标**（不要拿去当时间用！换算见 target_seconds）
                "frame": fi,
                # 视频时刻 = 该采样点的 SRT cue 时间。这是唯一权威来源。
                "target_seconds": round(target, 3),
                # 播放器要快进的秒数 = 视频内的秒数 = 采样点的 cue 时间（同一把尺子）。
                # 单独给一个字段，是为了让前端**不必**再去做"帧号 时间"的换算 ——
                # 之前正是因为前端自己算，才把采样下标当成了视频帧号（差 17.7 s）。
                "player_seek_seconds": round(target, 3),
                "start_seconds": round(max(0.0, target - FIND_PREROLL_SECONDS), 3),
                "ground_m_per_px": round(gsd, 4),
                "can_resolve_cm": round(gsd * 100, 1),
                "frames": n,
                "passes": int(1 + (n - 1) // cov.PASS_GAP_FRAMES),
                "alt_m": round(best["alt"], 1),
                # 必须 round：SRT 一位小数，存 .npz 时过了 float32，
                # 直接吐会变成 -29.299999237060547 这种尾巴（界面上真的出现过）。
                "pitch_deg": round(best["pit"], 1),
                "yaw_deg": round(best["yaw"], 1),
                "focal_mm": round(best["foc"], 1),
                "zoomed": bool(best["foc"] > cov.WIDE_MAX_FOCAL),
                "stream": ("thermal" if g.long_px == cov.LONG_PX_THERMAL else "visible"),
                # 目标在画面里的位置（归一化 -1..1），前端可用来画准星
                "image_xy": [round(best["xi"], 3), round(best["yi"], 3)],
                "clipped_frame": bool(best["clipped"]),
                # 这一帧里目标离画面边缘最近的那条边有多远（0=正中，1=贴边）。
                # 供界面提示"这张比较靠边"，也便于以后调 FIND_FRAME_INSET。
                "edge_margin": round(1.0 - max(abs(best["xi"]), abs(best["yi"])), 3),
                # 归入哪一类 —— 决定排序与界面标记。三类：
                #   "central"   目标在画面**居中**（偏移 <= FIND_CENTRAL_MARGIN）→ 最优先
                #   "zoom_cover"变焦且镜头覆盖 → 第二优先
                #   "none"      其余（画面里看得到，但既不居中、也没变焦）
                #
                # 为什么变焦要单独一类、而不是也要求居中：
                #   长焦是在**远处**看目标的，目标在画面里天生偏上/偏边
                #   （实测 175mm 那张的偏移是 0.73，永远过不了"居中"那道线）。
                #   要求它居中等于把这一类整个废掉。
                #
                # 用 FIND_CENTRAL_MARGIN 而不是 lim 判居中：lim 是硬门槛，
                # 能走到这里的帧都已经满足它了，拿它再判一次等于没判（踩过）。
                "_off": max(abs(best["xi"]), abs(best["yi"])),
                "_zoom": bool(best["foc"] > cov.WIDE_MAX_FOCAL),
                # 这一趟看着这一点的**时长**（首末命中帧之间），以及这一趟里拍到几帧。
                # 前端用来告诉用户"这是第几趟"，也便于判断是不是一次短暂掠过。
                "pass_seconds": round(max(0.0, t_to - t_from), 1),
                "pass_frames": len(grp),
                # 这一趟是从哪个方向看过去的（无人机->目标，不是相机 yaw）
                "bearing_deg": round(_bearing, 1),
                "elev_deg": round(_elev, 1),
            })

    # 相邻两趟太近的（同架次）只留最清的一条 ——
    # 否则"一次连续观察"会被切成两条几乎一样的卡。
    hits.sort(key=lambda h: (h["video_path"], h["target_seconds"]))
    dedup = []
    for h in hits:
        if dedup and dedup[-1]["video_path"] == h["video_path"] and \
                abs(dedup[-1]["target_seconds"] - h["target_seconds"]) < FIND_DEDUP_SECONDS:
            if h["ground_m_per_px"] < dedup[-1]["ground_m_per_px"]:
                dedup[-1] = h
            continue
        dedup.append(h)

    # ---------------- 三档检索 ----------------
    # 用户 2026-10-13：「应该给个检索选项，只看最清晰的 1 张，还是检索所有飞机
    # 不同角度和位置上、对那个点拍摄到的多个图」。
    # 而且他指出关键一点：**地面有遮挡物** —— 最清晰的那张可能正好被树挡住，
    # 另一张没那么清晰但从别的角度没被挡。所以"不同视角"这一档不能靠清晰度代替。
    mode = (mode or "passes").lower()
    if mode not in FIND_MODES:
        mode = "passes"

    if mode == "best":
        # 只要最清晰的那一张 —— 跨架次、跨趟次取全局最优
        chosen = sorted(dedup, key=lambda h: h["ground_m_per_px"])[:1]
    elif mode == "angles":
        # 按**视角**去重：方位/俯角接近的算同一个视角，只留其中最清晰的。
        #
        # 选法：按清晰度从好到差扫；一条只有在"与已选中的每一条都明显不同视角"
        # 时才入选。这样既保证第一张是最清晰的，又保证后面每张都带来**新的方向** ——
        # 正是为了绕开遮挡：某个方向被树挡住时，另一个方向的照片才有用。
        chosen = []
        for h in sorted(dedup, key=lambda h: h["ground_m_per_px"]):
            hb, he = h.get("bearing_deg"), h.get("elev_deg")
            if hb is None or he is None:
                chosen.append(h)
                continue
            distinct = True
            for c in chosen:
                cb, ce = c.get("bearing_deg"), c.get("elev_deg")
                if cb is None or ce is None:
                    continue
                db = abs(((hb - cb) + 180.0) % 360.0 - 180.0)      # 方位角环形差
                de = abs(he - ce)
                if db < FIND_ANGLE_BEARING_DEG and de < FIND_ANGLE_PITCH_DEG:
                    distinct = False
                    break
            if distinct:
                chosen.append(h)
    else:
        chosen = dedup

    # ---- 分类 + 排序 ----
    # 用户 2026-10-13 的第二版要求：
    #   「如果有大量帧包含目标点，那么优先跳转的应该是'目标点最贴近画面中心、
    #    或者稍微更靠近的位置'」
    # 也就是：**居中的程度本身要当排序键**，而且比"最清晰"更重要。
    #   （清晰度仍然保留为同分时的次序 —— 物理上两者本来就同向：
    #     GSD ∝ 斜距，越近越清，所以它是个合理的次级键。）
    #
    # 为什么"清晰度"不能排第一位：截图里最清晰的那张（4.2 cm/px）目标在画面
    # **上边缘**、被切掉了 —— 解像度数值最好，但判读不了。
    #
    # 顺序：类别（居中 > 变焦覆盖 > 其余）-> 离中心多近 -> 清晰度。
    _rank = {"central": 0, "zoom_cover": 1, "none": 2}
    for h in chosen:
        off, zoom = h.pop("_off", None), h.pop("_zoom", False)
        h["centre_offset"] = (round(off, 3) if off is not None else None)
        if off is not None and off <= FIND_CENTRAL_MARGIN:
            h["category"] = "central"            # 居中：最好判读
        elif zoom:
            h["category"] = "zoom_cover"         # 变焦看远处的目标，天生偏边
        else:
            h["category"] = "none"
        h["zoom_cover"] = bool(zoom)
        h["recommended"] = h["category"] in ("central", "zoom_cover")

    # 缺 centre_offset 的（理论上不该有）排到该类最后
    chosen.sort(key=lambda h: (_rank.get(h["category"], 2),
                               h["centre_offset"] if h["centre_offset"] is not None else 9.9,
                               h["ground_m_per_px"]))
    total = len(chosen)

    return {
        "ok": True,
        "lat": float(lat), "lng": float(lng),
        "mode": mode,
        # 实际生效的边距内缩（可能被夹到上限），前端回显用
        "frame_inset": round(inset, 4),
        "total": total,
        "returned": min(total, int(limit)),
        "preroll_seconds": FIND_PREROLL_SECONDS,
        "hits": chosen[:int(limit)],
        # 两类"优先推荐"的条数，前端用来解释排序（为什么这张排在前面）
        "recommended": {
            "central": sum(1 for h in chosen if h.get("category") == "central"),
            "zoom_cover": sum(1 for h in chosen if h.get("zoom_cover")),
        },
        "skipped": skipped,
        # 网格说"覆盖过"、但没有任何一帧真的把这点看在画面里的架次
        "covered_but_not_in_frame": partial,
        # 一共经过几个独立趟次（= 去重前的条数），便于前端说清"还有更多"
        "passes_total": len(hits),
        # 各档的条数，前端用来提示"换个档位能看到几张"
        "counts": {"best": 1 if dedup else 0, "passes": len(dedup),
                   "angles": len(chosen) if mode == "angles" else None},
    }

