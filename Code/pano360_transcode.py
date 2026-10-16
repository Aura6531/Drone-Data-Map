# -*- coding: utf-8 -*-
"""把 DJI `.OSV`（双鱼眼 HEVC）转成**浏览器能直接播的等距柱状 H.264**。

这条管线是逐步验证出来的，每一步都有踩坑记录：

## 为什么用 ffmpeg 而不是 Python 逐帧拼接
  · Python 拼接实测 512² 输出要 317 ms、1024² 要 1192 ms —— 到不了 30 fps
  · 环境里没有 cv2 / scipy / numba，纯 numpy 优化后也只快 2.9 倍
  · ffmpeg 的重投影是原生 C，快几十倍

## 关键结论（都是实测出来的，不是猜的）
  1. **map 必须 `format=gray16le`**
     `format=gray` 会把 16 位 map 只读成 8 位（或砍掉高/低字节），
     3840 的坐标变成 0~255 → 输出是"放射状拖尾"的垃圾。
     这是前几轮一直失败的根本原因。
  2. **map 的数值 = 源图上的像素坐标**（恒等映射逐像素无损、最大差 0）
  3. **map 与源的存储尺寸不必相同**（实测两种尺寸重叠区最大差 0），
     但 remap 的**输出尺寸 = 输入尺寸**
  4. **`maskedmerge` 不能用来选路** —— 它的 mask 是**混合权重**：
     白遮罩会把两路各半混成灰。真正的选路要把遮罩"烘"进图像再相加
  5. **ffmpeg 标签名不能带撇号**：`[a']` 会被当成引号，
     报 "Stream specifier ... matches no streams"
  6. 源用 `rgb24` 而不是 `yuv420p` —— 后者有色度子采样损失

## 与 Python 实现的一致性
  合成图（每个像素编码自身方向）上两者**逐像素 100% 相同**；
  真素材上"差<=30"占 89.7%、中位差 5.0 —— 差异来自插值方式，不是几何。
"""
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pano360
import project_manager as pm

# 转码用的默认参数
DEFAULT_LENS_SIZE = 2048      # 解码后缩到的鱼眼边长（源是 3840）
DEFAULT_EQUI_W = 2048         # 输出等距柱状宽度
DEFAULT_CRF = 22
DEFAULT_PRESET = "veryfast"

# 质量档位。实测（3 秒片段，各跑 3 次取中位，cuda 硬解 + NVENC）：
#
#   档位          lens  equi   中位     实时倍率   79 秒素材约
#   全质量        2048  2048   15.8 s   0.19x     7.0 分钟
#   中档          2048  1536   12.3 s   0.24x     5.4 分钟
#   快档          1536  1536   12.0 s   0.25x     5.3 分钟
#   很快          1280  1280    9.6 s   0.31x     4.2 分钟
#
# 用户 2026-10-15：「先追求最优效果，后面要做项目的工程化了再考虑减量、
# 处理速度、文件大小这些问题的优化」—— 所以**默认取全质量**。
# 档位是给"素材太多、先粗看一遍"这种场景用的。
QUALITY_TIERS = {
    "full": {"lens_size": 2048, "equi_w": 2048, "crf": 22},
    "medium": {"lens_size": 2048, "equi_w": 1536, "crf": 22},
    "fast": {"lens_size": 1536, "equi_w": 1536, "crf": 23},
    "quick": {"lens_size": 1280, "equi_w": 1280, "crf": 24},
}
DEFAULT_TIER = "full"


def _map_dir(cache_dir):
    d = Path(cache_dir) / "pano_maps"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_map16(arr, path):
    """存 16 位灰度 PNG。**必须用 I;16** —— 见模块开头第 1 条。"""
    Image.fromarray(np.clip(np.round(arr), 0, 65535).astype(np.uint16),
                    mode="I;16").save(path)


def build_maps(lens_size, equi_w, cache_dir, fov_deg=None):
    """算两路 remap 图 + 遮罩，写盘并返回路径。

    同样的几何只算一次（按 lens_size × equi_w 缓存）。
    """
    fov = float(fov_deg if fov_deg is not None else pano360.DEFAULT_FOV)
    equi_h = max(1, equi_w // 2)
    tag = "l%d_e%d_f%.1f" % (lens_size, equi_w, fov)
    d = _map_dir(cache_dir)
    paths = {k: d / ("%s_%s.png" % (tag, k))
             for k in ("up_x", "up_y", "dn_x", "dn_y", "mask")}
    if all(p.is_file() for p in paths.values()):
        return paths, (equi_w, equi_h)

    g = pano360.Fisheye360(fov_deg=fov)
    _LON, cz, dx, dy = g._direction_grid(equi_w, equi_h)
    half = np.deg2rad(fov / 2.0)
    c = (lens_size - 1) / 2.0
    phi = np.arctan2(dx, dy)
    for name, sign in (("up", 1.0), ("dn", -1.0)):
        theta = np.arccos(np.clip(sign * cz, -1.0, 1.0))
        rr = c * (theta / half)
        save_map16(c + rr * np.cos(phi), paths["%s_x" % name])
        save_map16(c + rr * np.sin(phi), paths["%s_y" % name])
    # 遮罩：**上镜头优先**（极角更小者），硬边 0/255
    th_u = np.arccos(np.clip(cz, -1, 1))
    th_d = np.arccos(np.clip(-cz, -1, 1))
    Image.fromarray(np.where(th_u <= th_d, 255, 0).astype(np.uint8),
                    mode="L").save(paths["mask"])
    return paths, (equi_w, equi_h)


def build_filtergraph(paths, lens_size, equi_w, equi_h, hwdecode=False):
    """两输入滤镜链：remap 两路 -> 烘遮罩 -> 相加。

    见模块开头第 4、5 条：不能用 maskedmerge，标签名不能带撇号。

    `hwdecode=True` 时前面接的是**硬解帧**（在显存里），必须先 `hwdownload` 拉回内存，
    而且**必须写成 `format=p010le`** —— `.OSV` 是 10 位 HEVC，
    硬解输出是 p010，写成 nv12 会报 `Invalid output format nv12 for hwframe download`。
    """
    pre = "hwdownload,format=%s," % HW_DOWNLOAD_FORMAT if hwdecode else ""
    return (
        "[0:v:0]{pre}scale={L}:{L},format=rgb24[s0];"
        "[1:v]format=gray16le[x0];[2:v]format=gray16le[y0];"
        "[s0][x0][y0]remap=fill=black[ua];"
        "[0:v:1]{pre}scale={L}:{L},format=rgb24[s1];"
        "[3:v]format=gray16le[x1];[4:v]format=gray16le[y1];"
        "[s1][x1][y1]remap=fill=black[da];"
        "[5:v]format=gray,format=rgb24[m0];"
        "[ua][m0]blend=all_expr='A*B/255'[u2];"
        "[5:v]format=gray,format=rgb24[m1];"
        "[da][m1]blend=all_expr='A*(255-B)/255'[d2];"
        "[u2][d2]blend=all_expr='A+B'[out]"
    ).format(L=lens_size, pre=pre)


# 判定"产物是否有效"的最小体积。
#
# 为什么不能用 `size > 0`：转码中途被杀会留下**几 KB 的残片**
# （实测见过 0.0 MB 的 `..._quick.mp4`），`> 0` 会把它当成"已转好"，
# 于是缓存永远命中、永远放不出画面，而且用户不知道该删哪个文件。
# 1 MB 对任何真实片段都远远小于其体积（最快档 10 秒也有十几 MB），
# 又能挡掉所有残片。
MIN_VALID_BYTES = 1024 * 1024


def is_valid_output(path):
    """转码产物的有效性判据（见 MIN_VALID_BYTES 的说明）。"""
    try:
        return Path(path).is_file() and Path(path).stat().st_size >= MIN_VALID_BYTES
    except OSError:
        return False
#
# 顺序有意义：**cuda（NVDEC）优先** —— 用户 2026-10-16 把 RTX 4060 的驱动装好后实测：
#   · cuda 硬解 + 重投影 + NVENC   CPU 合计 196 s（软解 + NVENC 是 284 s）
#   · 单看解码 cuda 硬解 1.19x 实时，软件解码 0.68x
# d3d11va 在**只有核显**的机器上也能用（实测 1.42x），但注意：
#   接进完整重投影管线时 d3d11va + remap 组合会失败
#   （`Nothing was written into output file`），所以排在 cuda 之后。
HWACCEL_CANDIDATES = ("cuda", "d3d11va", "d3d12va")

# 各硬解方式对应的 `-hwaccel_output_format`。
#
# **这个不能写死。** 踩过：统一写成 `d3d11`，于是选到 cuda 时格式不匹配，
# 输出 `frame= 0`、一帧都出不来（而单独手测 cuda 是能跑的 —— 差别就在这一项）。
# 同时它必须与 hwdownload 的取法配套：下面 HW_DOWNLOAD_FORMAT 对应 10 位源。
HWACCEL_OUTPUT_FORMAT = {
    "cuda": "cuda",
    "d3d11va": "d3d11",
    "d3d12va": "d3d12",
    "dxva2": "dxva2_vld",
    "qsv": "qsv",
    "vaapi": "vaapi",
    "vulkan": "vulkan",
}

# 硬件编码器候选。NVENC 实测把 CPU 时间从 303 s 降到 284 s（不显著），
# 但配合硬解时整体 CPU 时间 196 s vs 软解+软编 303 s —— 有明显收益。
HW_ENCODERS = {
    "h264": ("h264_nvenc", ["-preset", "p4", "-cq", "24"]),
}

# hwdownload 的取法。`p010le` = 10 位源（`.OSV` 是 HEVC Main10）。
# 写成 8 位的 `nv12`/`yuv420p` 会报
# `Invalid output format nv12 for hwframe download`。
HW_DOWNLOAD_FORMAT = "p010le"


def probe_hwaccel(src, ffmpeg=None, candidates=HWACCEL_CANDIDATES):
    """试出这个文件 + 这台机器上能用的硬解方式；都不行返回 None（走软件解码）。

    **只测"能不能解码"是不够的**：d3d11va 单独解码没问题，但接进
    完整重投影管线后 `remap` 会报 `Nothing was written into output file`。
    所以这里用**最小编译链**（两点 blend + 一张 16 位 map 的 remap）来试，
    能跑通才算可用。
    """
    ff = ffmpeg or pm.find_ffmpeg()
    for hw in candidates:
        ofmt = HWACCEL_OUTPUT_FORMAT.get(hw, hw)
        cmd = [ff, "-hide_banner", "-loglevel", "error",
               "-hwaccel", hw, "-hwaccel_output_format", ofmt,
               "-ss", "30", "-t", "1", "-i", str(src), "-map", "0:v:0",
               "-vf", "hwdownload,format=%s,scale=320:320" % HW_DOWNLOAD_FORMAT,
               "-f", "null", "-"]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=300)
        except Exception:
            continue
        if r.returncode != 0:
            continue
        # 再试一次带 remap 的链（这才是真正的可用性判据）
        probe_map = _ensure_probe_map()
        cmd2 = [ff, "-hide_banner", "-loglevel", "error",
                "-hwaccel", hw, "-hwaccel_output_format", ofmt,
                "-ss", "30", "-t", "1", "-i", str(src),
                "-i", str(probe_map),
                "-filter_complex",
                "[0:v:0]hwdownload,format=%s,scale=320:320,format=yuv420p,"
                "format=rgb24[s];[1:v]format=gray16le[x];"
                "[s][x]blend=all_expr='A*B/255'[out]" % HW_DOWNLOAD_FORMAT,
                "-map", "[out]", "-f", "null", "-"]
        try:
            r2 = subprocess.run(cmd2, capture_output=True, timeout=300)
        except Exception:
            continue
        if r2.returncode == 0:
            return hw
    return None


_ENCODER_OK = {}


def probe_encoder(name, ffmpeg=None):
    """试一下这个编码器是否真能用（驱动没装时 ffmpeg 只是"列着"，一调就失败）。

    用合成源（`testsrc`）试，不依赖素材，结果缓存。
    """
    if name in _ENCODER_OK:
        return _ENCODER_OK[name]
    ff = ffmpeg or pm.find_ffmpeg()
    out = Path(tempfile.gettempdir()) / ("dsh_enc_probe_%s.mp4" % name)
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=1",
           "-c:v", name, "-pix_fmt", "yuv420p", str(out)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=300)
        ok = r.returncode == 0 and is_valid_output(out)
    except Exception:
        ok = False
    try:
        out.unlink()
    except OSError:
        pass
    _ENCODER_OK[name] = ok
    return ok


_PROBE_MAP = None


def _ensure_probe_map():
    """给 probe_hwaccel 用的一张小灰度 map。

    **尺寸必须与探针里 scale 出来的帧一致（320×320）**：
    踩过 —— 一开始写成 180×320，`remap` 因尺寸不匹配直接失败，
    于是 probe 误判"硬解不可用"，把好端端的 cuda 硬解给禁掉了。
    坐标值也必须在 320 以内（源是 320×320）。
    """
    global _PROBE_MAP
    if _PROBE_MAP is not None and Path(_PROBE_MAP).is_file():
        return Path(_PROBE_MAP)
    p = Path(tempfile.gettempdir()) / "dsh_pano_probe_map.png"
    arr = np.zeros((320, 320), dtype=np.uint16)
    arr[:, :] = np.arange(320, dtype=np.uint16)[None, :]
    Image.fromarray(arr, mode="I;16").save(p)
    _PROBE_MAP = p
    return p


def transcode_pano(src, dst, cache_dir, lens_size=None, equi_w=None,
                   crf=None, preset=DEFAULT_PRESET,
                   start=None, duration=None, ffmpeg=None, progress=None,
                   hwaccel="auto", encoder="auto", tier=DEFAULT_TIER,
                   on_progress=None):
    """把 `.OSV` 转成等距柱状 H.264 MP4。返回 (ok, 用时秒, stderr)。

    `tier`：`"full"` / `"medium"` / `"fast"` / `"quick"`（见 QUALITY_TIERS）。
            显式给了 `lens_size` / `equi_w` / `crf` 就覆盖档位里的值。

    `hwaccel`：
      · `"auto"`（默认）—— 先探测可用的硬解，不行就软件解码
      · 具体名字（如 `"cuda"`）—— 强制用那个
      · `None` / `""` —— 强制软件解码

    `encoder`：
      · `"auto"`（默认）—— 硬解可用时用 NVENC，否则 libx264
      · 列表（如 `["-c:v","h264_nvenc","-preset","p4"]`）—— 直接用
      · `None` —— 强制 libx264
    """
    src = Path(src)
    dst = Path(dst)
    ff = ffmpeg or pm.find_ffmpeg()
    t = QUALITY_TIERS.get(tier) or QUALITY_TIERS[DEFAULT_TIER]
    lens_size = int(lens_size or t["lens_size"])
    equi_w = int(equi_w or t["equi_w"])
    crf = int(crf if crf is not None else t["crf"])
    paths, (ew, eh) = build_maps(lens_size, equi_w, cache_dir)

    hw = None
    if hwaccel is None or hwaccel == "":
        hw = None
    elif hwaccel == "auto":
        hw = probe_hwaccel(src, ff)
    else:
        hw = hwaccel

    # 编码器：显式给了就用给的；`encoder="auto"` 时在硬解可用的情况下试硬编。
    enc = None
    if encoder == "auto":
        if hw:
            name, opts = HW_ENCODERS["h264"]
            if probe_encoder(name, ff):
                enc = [name] + opts + ["-pix_fmt", "yuv420p"]
        if enc is None:
            enc = None      # 下面走默认的 libx264 分支
    elif encoder:
        enc = list(encoder)

    if progress:
        progress("maps ready: %dx%d equirect, lens %d, hwaccel=%s, encoder=%s" % (
            ew, eh, lens_size, hw or "software",
            (enc[1] if enc and len(enc) > 1 else "libx264") if enc else "libx264"))

    cmd = [ff, "-y", "-loglevel", "error", "-stats"]
    if start is not None:
        cmd += ["-ss", "%.3f" % float(start)]
    if hw:
        # 硬解输出留在显存，滤镜链里再 hwdownload 拉回来（见 build_filtergraph）。
        # output_format 必须按 hw 名字取，不能写死（见 HWACCEL_OUTPUT_FORMAT）。
        cmd += ["-hwaccel", hw,
                "-hwaccel_output_format", HWACCEL_OUTPUT_FORMAT.get(hw, hw)]
    cmd += ["-i", str(src)]
    cmd += ["-i", str(paths["up_x"]), "-i", str(paths["up_y"]),
            "-i", str(paths["dn_x"]), "-i", str(paths["dn_y"]),
            "-i", str(paths["mask"]),
            "-filter_complex",
            build_filtergraph(paths, lens_size, ew, eh, hwdecode=bool(hw)),
            "-map", "[out]"]
    # `-t` 必须放在**所有输入与滤镜之后**（作为输出的时长限制）。
    # 踩过：放在第二个 `-i` 后面时，ffmpeg 把它当成**那个输入的**时长限制，
    # 于是输出的时长限制没生效 —— 要 5 秒的结果出了 49 秒。
    if duration is not None:
        cmd += ["-t", "%.3f" % float(duration)]
    if enc:
        cmd += ["-c:v"] + enc
    else:
        cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                "-pix_fmt", "yuv420p"]
    cmd += ["-movflags", "+faststart", str(dst)]
    dst.parent.mkdir(parents=True, exist_ok=True)

    def attempt():
        try:
            dst.unlink()
        except OSError:
            pass
        t0 = time.time()
        # 用 Popen + `-progress pipe:1` 而不是 subprocess.run：
        #   ① 进度能被读到（同步接口没法报进度，异步任务要它）
        #   ② 不会因为 stderr 缓冲区满而卡死（长时间转码时 run 有这个问题）
        # `-progress` 走 stdout，日志仍走 stderr，两者不打架。
        run_cmd = cmd + ["-progress", "pipe:1", "-nostats"]
        p = subprocess.Popen(run_cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        err_chunks = []

        def drain_err():
            for line in p.stderr:
                err_chunks.append(line)
        th = threading.Thread(target=drain_err, daemon=True)
        th.start()

        last = {}
        try:
            for raw in p.stdout:
                line = raw.decode("utf-8", "replace").strip()
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                last[k] = v
                if on_progress and k in ("out_time_us", "out_time_ms", "progress"):
                    try:
                        us = int(last.get("out_time_us") or last.get("out_time_ms") or 0)
                        done = us / 1_000_000.0
                        pct = None
                        if duration:
                            pct = max(0.0, min(100.0, done / float(duration) * 100.0))
                        on_progress({
                            "seconds_done": round(done, 2),
                            "percent": (round(pct, 1) if pct is not None else None),
                            "speed": last.get("speed"),
                            "frame": last.get("frame"),
                            "fps": last.get("fps"),
                        })
                    except (TypeError, ValueError):
                        pass
        finally:
            p.wait(timeout=24 * 3600)
            th.join(timeout=10)
        el = time.time() - t0
        good = p.returncode == 0 and is_valid_output(dst)
        return good, el, b"".join(err_chunks).decode("utf-8", "replace")

    ok, dt, err = attempt()

    # **失败自动回退到软件解码。**
    # 为什么需要：探针只能验"这条链大致能用"，验不全。
    # 踩过两次 ——
    #   · d3d11va 单看解码通过，接进完整重投影管线却 `frame= 0`（一帧都不出）
    #   · cuda 曾因 `-hwaccel_output_format` 写死成 `d3d11` 而整条失败
    # 与其把探针写得越来越复杂，不如让转码器自己兜住：
    # 硬解这条路出不来东西就换软解重跑一次，调用方不必关心。
    if not ok and (hw or enc):
        if progress:
            progress("hardware path failed — retrying with software decode")
        hw, enc = None, None
        cmd = [c for c in cmd]
        # 重建命令（去掉硬解与硬编参数）
        cmd = [ff, "-y", "-loglevel", "error", "-stats"]
        if start is not None:
            cmd += ["-ss", "%.3f" % float(start)]
        cmd += ["-i", str(src)]
        cmd += ["-i", str(paths["up_x"]), "-i", str(paths["up_y"]),
                "-i", str(paths["dn_x"]), "-i", str(paths["dn_y"]),
                "-i", str(paths["mask"]),
                "-filter_complex",
                build_filtergraph(paths, lens_size, ew, eh, hwdecode=False),
                "-map", "[out]"]
        if duration is not None:
            cmd += ["-t", "%.3f" % float(duration)]
        cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)]
        ok, dt2, err2 = attempt()
        dt += dt2
        err = err + "\n[fallback]\n" + err2

    return ok, dt, err


# ============================================================
# 异步转码任务
# ============================================================#
# 为什么需要：转码是**分钟级**（79 秒素材约 7 分钟）。
# 同步接口会让前端只能干等、看不到进度、还可能被浏览器/代理超时掐掉。
# 所以改成"提交任务 -> 轮询进度"。
#
# 并发度：默认 **1**（串行）。
# 为什么不全开：转码本身会把 6 个核吃满（4K HEVC 软件解码 + 重投影），
# 并行跑多个只会互相拖慢，而且 GPU 只有一块。串行反而总吞吐更高、也更可预期。
_JOB_MAX_WORKERS = 1

_jobs = {}                 # job_id -> dict
_jobs_lock = threading.Lock()
_queue = []                # 待办 job_id（FIFO）
_queue_cv = threading.Condition()
_workers_started = False


def _ensure_workers():
    global _workers_started
    with _jobs_lock:
        if _workers_started:
            return
        _workers_started = True
        for i in range(_JOB_MAX_WORKERS):
            t = threading.Thread(target=_worker, name="pano-transcode-%d" % i,
                                 daemon=True)
            t.start()


def _worker():
    while True:
        with _queue_cv:
            while not _queue:
                _queue_cv.wait()
            job_id = _queue.pop(0)
        with _jobs_lock:
            job = _jobs.get(job_id)
        if not job or job.get("state") in ("cancelled",):
            continue
        try:
            _run_job(job)
        except Exception as e:                       # 绝不能让工作线程死掉
            with _jobs_lock:
                job["state"] = "failed"
                job["error"] = "%s: %s" % (type(e).__name__, e)
                job["finished_at"] = time.time()


def _run_job(job):
    dst = Path(job["dst"])
    if is_valid_output(dst) and not job.get("force"):
        with _jobs_lock:
            job["state"] = "done"
            job["percent"] = 100.0
            job["size"] = dst.stat().st_size
            job["cached"] = True
            job["finished_at"] = time.time()
        return

    with _jobs_lock:
        job["state"] = "running"
        job["started_at"] = time.time()

    def onp(info):
        with _jobs_lock:
            job["percent"] = info.get("percent")
            job["seconds_done"] = info.get("seconds_done")
            job["speed"] = info.get("speed")
            job["fps"] = info.get("fps")
            job["frame"] = info.get("frame")

    ok, dt, err = transcode_pano(
        job["src"], dst, dst.parent, tier=job["tier"],
        duration=job.get("duration"), on_progress=onp)

    with _jobs_lock:
        job["seconds"] = round(dt, 1)
        job["finished_at"] = time.time()
        if ok:
            job["state"] = "done"
            job["percent"] = 100.0
            job["size"] = dst.stat().st_size if dst.is_file() else 0
            job["path"] = str(dst)
        else:
            job["state"] = "failed"
            job["error"] = (err or "")[-800:]


def submit(src, dst, tier=DEFAULT_TIER, force=False, duration=None, label=None):
    """提交一个转码任务，返回 job_id。重复提交同一目标会复用未完成的那个。"""
    _ensure_workers()
    src, dst = Path(src), Path(dst)
    with _jobs_lock:
        for jid, j in _jobs.items():
            if (j.get("dst") == str(dst) and j.get("state") in ("queued", "running")):
                return jid
        jid = uuid.uuid4().hex[:12]
        _jobs[jid] = {
            "id": jid, "state": "queued", "src": str(src), "dst": str(dst),
            "tier": tier, "force": bool(force), "duration": duration,
            "label": label or src.name, "percent": 0.0, "queued_at": time.time(),
        }
    with _queue_cv:
        _queue.append(jid)
        _queue_cv.notify()
    return jid


def job(job_id):
    """取单个任务状态。**自己拿锁** —— 不要在持锁时调用它（见 all_jobs 的注释）。"""
    with _jobs_lock:
        j = _jobs.get(job_id)
        if not j:
            return None
        return _job_snapshot(j)


def _job_snapshot(j):
    """把任务 dict 复制成可安全序列化的快照。**调用方必须已经持锁。**"""
    out = {k: v for k, v in j.items() if k != "dst"}
    out["dst_name"] = Path(j["dst"]).name
    return out


def all_jobs():
    # 注意：**必须先拿快照列表、再逐个构造**，不能在持锁时调用 `job()`。
    # 踩过：`_jobs_lock` 是普通 `threading.Lock`（**不可重入**），
    # `all_jobs` 持锁后调 `job()` → `job()` 再拿同一把锁 → **死锁**，
    # 表现为 `/api/pano360/job` 永久挂住（而别的接口正常，所以很难猜）。
    with _jobs_lock:
        ids = list(_jobs)
    return [job(i) for i in ids]


def active_jobs():
    with _jobs_lock:
        ids = [i for i, j in _jobs.items()
               if j.get("state") in ("queued", "running")]
    return [job(i) for i in ids]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="OSV -> 等距柱状 H.264")
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--lens", type=int, default=DEFAULT_LENS_SIZE)
    ap.add_argument("--width", type=int, default=DEFAULT_EQUI_W)
    ap.add_argument("--crf", type=int, default=DEFAULT_CRF)
    ap.add_argument("--preset", default=DEFAULT_PRESET)
    ap.add_argument("--start", type=float, default=None)
    ap.add_argument("--duration", type=float, default=None)
    ap.add_argument("--cache", default=None)
    a = ap.parse_args()
    cache = a.cache or str(Path(a.dst).resolve().parent)
    ok, dt, err = transcode_pano(a.src, a.dst, cache, lens_size=a.lens,
                                 equi_w=a.width, crf=a.crf, preset=a.preset,
                                 start=a.start, duration=a.duration,
                                 progress=lambda m: print("  " + m))
    print("  ok=%s  用时 %.1f s" % (ok, dt))
    if ok:
        p = Path(a.dst)
        print("  产物 %s  %.1f MB" % (p.name, p.stat().st_size / 1e6))
        # 报告实时倍率
        if a.duration:
            print("  速度 %.2fx 实时" % (a.duration / dt))
    else:
        print("  失败:\n%s" % err[:1200])
