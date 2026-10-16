# -*- coding: utf-8 -*-
"""把 360（.OSV 双鱼眼）的一帧/一段时间导出成等距柱状图，供预览器与后续步骤用。

用法示例：
    python -B pano360_export.py --srt <path.srt> --t 20 --out frame.png
    python -B pano360_export.py --srt <path.srt> --at-latlon 30.0021 101.5545 --out f.png
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pano360


def _ffmpeg() -> str:
    import project_manager as pm
    return pm.find_ffmpeg()


def video_of_srt(srt: Path) -> Path:
    for ext in (".OSV", ".MP4", ".mp4", ".MOV", ".mov"):
        c = srt.with_suffix(ext)
        if c.is_file():
            return c
    raise FileNotFoundError("找不到对应的视频（.OSV/.MP4）: %s" % srt)


def grab_lens_frames(video: Path, t_sec: float, size: int = 1440) -> tuple:
    """抽同一时刻的两路鱼眼帧。返回 (up, down)，各 size x size x 3 uint8。

    为什么按"时刻"抽而不是按帧号：ffmpeg 的 `-ss` 是精确到秒的 seek，
    两路用同一个时刻抽，天然对齐（两路帧号相同）。
    """
    ff = _ffmpeg()
    out = []
    for idx in (0, 1):
        p = subprocess.run(
            [ff, "-y", "-loglevel", "error", "-ss", "%.3f" % t_sec, "-i", str(video),
             "-map", "0:v:%d" % idx, "-frames:v", "1",
             "-vf", "scale=%d:%d" % (size, size), "-f", "image2pipe",
             "-vcodec", "png", "-"],
            capture_output=True, timeout=1800)
        if p.returncode != 0 or not p.stdout:
            raise RuntimeError("抽第 %d 路失败: %s" % (idx, (p.stderr or b"")[:300]))
        import io
        out.append(np.asarray(Image.open(io.BytesIO(p.stdout)).convert("RGB")))
    return out[0], out[1]


def equirect_at(srt: Path, t_sec: float, size: int = 1440,
                ew: int | None = None, fov_deg: float = pano360.DEFAULT_FOV):
    """抽某时刻并拼成等距柱状。返回 uint8 数组。"""
    video = video_of_srt(srt)
    up, dn = grab_lens_frames(video, t_sec, size=size)
    g = pano360.Fisheye360(fov_deg=fov_deg)
    return g.stitch(up, dn, ew=ew)


def main():
    ap = argparse.ArgumentParser(description="360 -> equirectangular 导出")
    ap.add_argument("--srt", required=True)
    ap.add_argument("--t", type=float, default=0.0, help="视频内秒数")
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=1440, help="单路鱼眼抽帧尺寸")
    ap.add_argument("--ew", type=int, default=None, help="输出等距柱状宽度（高度减半）")
    ap.add_argument("--fov", type=float, default=pano360.DEFAULT_FOV)
    a = ap.parse_args()

    equi = equirect_at(Path(a.srt), a.t, size=a.size, ew=a.ew, fov_deg=a.fov)
    Image.fromarray(equi).save(a.out)
    print("已写出 %s  %s   FOV=%.0f°" % (a.out, equi.shape, a.fov))


if __name__ == "__main__":
    main()
