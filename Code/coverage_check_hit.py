# -*- coding: utf-8 -*-
"""核对「检索出来的帧到底有没有包含被点的位置」—— 把点投影回原帧，画十字。

为什么需要这个工具：
    「Frames of this spot」给出的只是**候选帧**（那一点落在足迹内）。
    但"落在足迹内"和"画面里看得见那一点"是两件事，尤其浅俯角时
    点可能落在画面顶端甚至之外。肉眼核对是最快的判断方式。

做法：
    对每一帧，按 SRT 的姿态与高度，把目标经纬度反投影成图像像素，
    抽那一帧的原图并在该像素画十字。图上还会带上归一化坐标 ——
    |xi|<=1 且 |yi|<=1 才算真的在画面里。

用法：
    python -B coverage_check_hit.py --lat 23.047131 --lng 114.104236
    python -B coverage_check_hit.py --lat .. --lng .. --project test --limit 5
"""

from __future__ import annotations

import argparse
import math
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import coverage as cov          # noqa: E402
import coverage_api as api      # noqa: E402
import project_manager as pm    # noqa: E402


def image_point_of_ground(origin, height, yaw, pitch, lat, lng, focal):
    """地面点 -> 归一化图像坐标 (xi, yi) 与是否在画面内。

    这是 coverage.imagePointOfGround() 的 Python 版（同一个针孔模型），
    但**独立实现**了一遍 —— 复用它就失去"交叉验证"的意义了。
    """
    lat0, lng0 = origin
    mx = cov.M_PER_DEG_LNG * math.cos(math.radians(lat0))
    d = ((lng - lng0) * mx, (lat - lat0) * cov.M_PER_DEG_LAT, -height)
    L = math.sqrt(sum(c * c for c in d))
    if L <= 0:
        return None, None, False
    d = tuple(c / L for c in d)

    yr, pr = math.radians(yaw), math.radians(pitch)
    sy, cy = math.sin(yr), math.cos(yr)
    sp, cp = math.sin(pr), math.cos(pr)
    f = (cp * sy, cp * cy, sp)
    u = (-sp * sy, -sp * cy, cp)
    r = (f[1] * u[2] - f[2] * u[1],
         f[2] * u[0] - f[0] * u[2],
         f[0] * u[1] - f[1] * u[0])

    z = sum(d[k] * f[k] for k in range(3))
    if z <= 1e-9:
        return None, None, False            # 在相机背后
    x = sum(d[k] * r[k] for k in range(3)) / z
    y = sum(d[k] * u[k] for k in range(3)) / z
    hf, vf = cov.fov_of(focal)
    xi = x / math.tan(math.radians(hf / 2))
    yi = y / math.tan(math.radians(vf / 2))
    return xi, yi, (abs(xi) <= 1.0 and abs(yi) <= 1.0)


def extract_frame(ffmpeg, video: Path, t: float, dst: Path, width=1280) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-ss", f"{max(0.0, t):.3f}",
         "-i", str(video), "-frames:v", "1", "-vf", f"scale={width}:-2", str(dst)],
        capture_output=True, timeout=180)
    return dst.is_file() and dst.stat().st_size > 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lng", type=float, required=True)
    ap.add_argument("--project", default=None, help="项目名（默认取第一个有网格的）")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--out", default=None, help="输出目录（默认 <工作区>/_hitcheck）")
    args = ap.parse_args()

    import numpy as np
    from PIL import Image, ImageDraw

    # 找项目
    proj_name = args.project
    if not proj_name:
        for d in sorted(pm.PROJECT_DIR.iterdir()):
            if d.is_dir() and (d / "coverage").is_dir() and any((d / "coverage").glob("*.npz")):
                proj_name = d.name
                break
    if not proj_name:
        print("找不到有覆盖网格的项目。先在界面上 Build 一个。")
        return 1

    outdir = Path(args.out) if args.out else (pm.BASE_DIR / "_hitcheck")
    ffmpeg = pm.find_ffmpeg()
    if not ffmpeg:
        print("找不到 ffmpeg，抽不了帧。")
        return 1

    res = api.find_frames(proj_name, args.lat, args.lng, limit=args.limit)
    print(f"项目 {proj_name}   目标 {args.lat}, {args.lng}")
    print(f"命中 {res['total']} 条（显示前 {len(res['hits'])}）\n")
    for s in (res.get("skipped") or []):
        print(f"  跳过 {s['srt']}: {s['why']}")
    if res.get("skipped"):
        print()

    proj = pm.load_project(proj_name)
    for h in res["hits"]:
        srt = Path(h["srt"])
        video = srt.with_suffix(".MP4")
        if not video.is_file():
            print(f"  {srt.stem}: 找不到视频")
            continue
        tele = pm.load_srt_telemetry(srt)
        recs = pm.parse_dji_srt(srt)
        step = cov.TELEMETRY_STEP
        i = h["frame"]
        lat_i = recs[i * step]["latitude"]
        lng_i = recs[i * step]["longitude"]
        alt, yaw, pit = tele["alt"][i], tele["yaw"][i], tele["pitch"][i]
        foc = tele["focal"][i] or 24.0

        dst = outdir / f"{srt.stem}_f{i}.png"
        if not extract_frame(ffmpeg, video, h["target_seconds"], dst, args.width):
            print(f"  {srt.stem} 帧 {i}: 抽帧失败")
            continue
        with Image.open(dst) as im0:
            im = im0.convert("RGB")
        W, H = im.size
        xi, yi, vis = image_point_of_ground(
            (lat_i, lng_i), alt, yaw, pit, args.lat, args.lng, foc)

        print(f"  {srt.stem}  帧 {i}  {h['target_seconds']:.2f}s  "
              f"{h['can_resolve_cm']} cm/px")
        print(f"      无人机 {lat_i:.6f},{lng_i:.6f}  高度 {alt:.1f} m  "
              f"焦距 {foc:.1f} mm  偏航 {yaw:.1f}°  俯角 {pit:.1f}°")
        if xi is None:
            print("      ✗ 目标在相机背后（不该被算作覆盖）")
        else:
            px, py = (xi + 1) / 2 * W, (1 - yi) / 2 * H
            print(f"      归一化 xi={xi:+.3f} yi={yi:+.3f} -> 像素 ({px:.0f},{py:.0f})"
                  f"   在画面内: {vis}")
            d = ImageDraw.Draw(im)
            color = (255, 0, 0) if vis else (255, 140, 0)
            if 0 <= px < W and 0 <= py < H:
                d.line([(px - 40, py), (px + 40, py)], fill=color, width=4)
                d.line([(px, py - 40), (px, py + 40)], fill=color, width=4)
            d.text((8, 6), f"frame {i}  xi={xi:+.2f} yi={yi:+.2f}  in-frame={vis}",
                   fill=color)
        im.save(dst)
        print(f"      -> {dst}")
        print()

    print("核对方式：打开这些图，看十字有没有落在你点的那个东西上。")
    print("|xi| 或 |yi| > 1 表示那一点在画面之外 —— 那种命中应该被排除。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
