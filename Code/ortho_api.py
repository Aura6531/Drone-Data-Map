# -*- coding: utf-8 -*-
"""正射影像的接口层：发现 / 建金字塔 / 查进度 / 出瓦片。

单独放一个文件是为了 project_manager.py 别再长 —— 那边已经 9600 行了。
所有依赖（ortho.py）都是标准库 + numpy，没有第三方 GIS 库。
"""

import json
import shutil
import threading
import time
from pathlib import Path

import ortho

# 支持的影像扩展名。`.tif/.tiff` 是正射影像的常见格式；
# `.img/.jp2` 之类目前不认（没有对应解析器），遇到会提示。
RASTER_SUFFIXES = (".tif", ".tiff")

_JOB_LOCK = threading.Lock()
_JOBS = {}           # key -> {id, state, progress, stats, error, started, finished}
_BUILDING = set()    # 正在建的 key，防重复提交
_TILE_LOCK = threading.Lock()


def _key(project, path):
    return "%s|%s" % (project, str(path))


def safe_name(path):
    """把文件名变成可以当目录名的形式（保留可读性）。"""
    stem = Path(path).stem
    out = []
    for ch in stem:
        out.append(ch if (ch.isalnum() or ch in "-_.") else "_")
    name = "".join(out).strip("._")
    return name or "ortho"


def cache_dir_for(project_dir, path):
    return Path(project_dir) / "ortho" / safe_name(path)


# ============================================================
# 发现：项目文件夹里有哪些正射影像
# ============================================================

def discover(project_dir, folders, project_name=""):
    """扫描项目的各个数据文件夹，列出正射影像及其状态。

    不建索引、不写文件 —— 纯读取，所以每次调用都反映磁盘当前状态
    （用户删了 tif，这里立刻消失，不会留下失效条目）。
    """
    found = []
    seen = set()
    for folder in folders or []:
        if not folder:
            continue
        root = Path(folder)
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in RASTER_SUFFIXES:
                continue
            try:
                resolved = str(p.resolve())
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)

            entry = {"name": p.name, "path": resolved,
                     "relative_path": _rel(folder, p)}
            cd = cache_dir_for(project_dir, resolved)
            meta = ortho.read_meta(cd)
            entry["cache_dir"] = str(cd)
            entry["ready"] = bool(meta) and ortho.cache_is_ready(cd)
            if meta:
                entry["source"] = meta.get("source")
                entry["levels"] = meta.get("levels")
                entry["build"] = meta.get("build")
                entry["tiles"] = _count_png(cd)
                entry["size_mb"] = round(_dir_size(cd) / 1e6, 1)
                entry["kind"] = "ortho"
            else:
                # 还没建：为了能在地图上立刻"看见"，这里**读一下投影**拿范围。
                # 只读 TIFF 的 IFD，不解像素，很快（实测 0.04 s）。
                try:
                    src = ortho.open_raster(resolved)
                    entry["source"] = src.info()
                    entry["levels"] = list(ortho.pyramid_levels(src))
                    entry["tiles"] = 0
                    entry["size_mb"] = 0.0
                    entry["kind"] = "ortho"
                except Exception as e:
                    # 典型情况：dsm.tif 是单波段浮点高程，不能当影像显示。
                    # 它不是"坏了"，而是**不该出现在可加载列表里** ——
                    # 标成 kind=unsupported 并带上原因，前端可以折叠掉。
                    entry["error"] = str(e)
                    entry["kind"] = "unsupported"
            found.append(entry)

    # 能用的排前面（按像素数从大到小：正射影像通常比 GSD 图大得多）
    def _rank(e):
        ok = 0 if e.get("kind") == "ortho" else 1
        src = e.get("source") or {}
        return (ok, -int(src.get("width") or 0) * int(src.get("height") or 0))

    found.sort(key=_rank)
    return found


def _rel(folder, path):
    try:
        return str(Path(path).relative_to(Path(folder)))
    except (ValueError, OSError):
        return Path(path).name


def _count_png(root):
    n = 0
    for p in Path(root).rglob("*.png"):
        n += 1
    return n


def _dir_size(root):
    total = 0
    for p in Path(root).rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def find_by_path(project_dir, folders, path):
    """按绝对路径找到一张影像（并校验它确实在项目文件夹里 —— 防止越权读盘）。"""
    target = Path(path)
    try:
        resolved = target.resolve()
    except OSError:
        return None
    if resolved.suffix.lower() not in RASTER_SUFFIXES:
        return None
    for folder in folders or []:
        if not folder:
            continue
        try:
            resolved.relative_to(Path(folder).resolve())
        except (ValueError, OSError):
            continue
        if resolved.is_file():
            return str(resolved)
    return None


# ============================================================
# 建金字塔：后台任务
# ============================================================

def job_snapshot(key):
    with _JOB_LOCK:
        job = _JOBS.get(key)
        if not job:
            return None
        return dict(job)


def start_build(project_dir, path, force=False):
    """提交建金字塔任务。已在建 / 已建好就复用。"""
    key = _key(project_dir, path)
    cd = cache_dir_for(project_dir, path)

    with _JOB_LOCK:
        existing = _JOBS.get(key)
        if existing and existing.get("state") == "running":
            return existing
        if not force and ortho.cache_is_ready(cd):
            return {"state": "ready", "cached": True, "cache_dir": str(cd),
                    "tiles": _count_png(cd), "size_mb": round(_dir_size(cd) / 1e6, 1)}
        job = {
            "id": key,
            "state": "queued",
            "phase": "queued",
            "progress": 0.0,
            "levels": {},
            "stats": None,
            "error": None,
            "started": time.time(),
            "finished": None,
            "cache_dir": str(cd),
            "path": path,
        }
        _JOBS[key] = job
        if key in _BUILDING:
            return job
        _BUILDING.add(key)

    thread = threading.Thread(target=_run_build, args=(key, project_dir, path, cd),
                              daemon=True, name="ortho-build")
    thread.start()
    return job_snapshot(key)


def _run_build(key, project_dir, path, cd):
    src = None
    lock = _source_lock(path)

    def update(**kw):
        with _JOB_LOCK:
            job = _JOBS.get(key)
            if job:
                job.update(kw)

    try:
        update(state="running", phase="opening")
        with lock:
            src = ortho.open_raster(path)
            lo, hi = ortho.pyramid_levels(src)
            update(phase="building", levels_total=hi - lo + 1)

            def progress(z, built, skipped, empty):
                done = z - lo + 1
                update(phase="building",
                       progress=round(done / float(hi - lo + 1), 3),
                       current_z=z,
                       levels={**(_JOBS.get(key, {}).get("levels") or {}),
                               str(z): {"built": built, "skipped": skipped, "empty": empty}})

            stats = ortho.build_pyramid(src, cd, progress=progress)
            ortho.write_meta(cd, src, stats)

        update(state="done", phase="done", progress=1.0, stats=stats,
               tiles=_count_png(cd), size_mb=round(_dir_size(cd) / 1e6, 1),
               finished=time.time())
    except Exception as e:
        update(state="failed", phase="failed", error=str(e), finished=time.time())
    finally:
        with _JOB_LOCK:
            _BUILDING.discard(key)


_src_locks = {}
_src_locks_lock = threading.Lock()


def _source_lock(path):
    """每张影像一把锁：并发生成瓦片时避免同一个文件句柄被打断。"""
    with _src_locks_lock:
        lock = _src_locks.get(path)
        if lock is None:
            lock = threading.Lock()
            _src_locks[path] = lock
        return lock


# ============================================================
# 瓦片：磁盘有就读文件，没有就现算（保证"还没建完也能看见"）
# ============================================================

def tile_bytes(project_dir, path, z, x, y):
    """返回 (png_bytes, source) —— source 是 'cache' 或 'live'。

    设计成"先看磁盘"很关键：金字塔建好之后，缩放/平移全是读文件（0.0~0.2 ms）；
    还没建的层级现算兜底，所以用户不用等全量建完才能看。
    """
    cd = cache_dir_for(project_dir, path)

    lvl = Path(cd) / str(z)
    if lvl.is_dir():
        p = ortho.tile_path(cd, z, x, y)
        if p.is_file():
            try:
                return p.read_bytes(), "cache"
            except OSError:
                pass

    # 现算
    src = ortho.open_raster(path)
    lo, hi = ortho.pyramid_levels(src)
    if z < lo or z > hi:
        raise ValueError("层级 %d 超出范围（这张影像支持 z%d~z%d）。" % (z, lo, hi))

    with _source_lock(path):
        rgba = src.render_tile(z, x, y)

    if src.is_empty(rgba):
        return ortho._empty_png(), "live-empty"

    data = ortho.png_bytes(rgba)
    # 顺手把算出来的落盘 —— 用户看过的区域下次就是读文件
    try:
        dest = ortho.tile_path(cd, z, x, y)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".png.tmp")
        tmp.write_bytes(data)
        tmp.replace(dest)
    except OSError:
        pass
    return data, "live"
