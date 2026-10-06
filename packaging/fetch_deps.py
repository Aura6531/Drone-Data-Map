"""准备打包要用到的第三方资源（可重复执行，已存在就跳过）。

下载两个东西，都落在 packaging/payload/ 下：
  1. ffmpeg（gyan.dev release essentials，静态构建，含 libx264 -> GPLv3）
     只保留 ffmpeg.exe 和它的 LICENSE/README（ffprobe.exe 代码里没用到，不带）
  2. Leaflet 1.9.4 的 js/css/图片 -> payload/vendor/
     （页面优先用本地 /vendor/，没有才回退 unpkg CDN；内网/断网机器必须带）

注意：沙箱里 PowerShell 的 HTTPS 会被掐（Invoke-WebRequest 报 "connection closed"），
但 Python 的 urllib 正常 —— 所以这里统一用 Python 下。
"""

import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

PAYLOAD = Path(__file__).resolve().parent / "payload"
VENDOR = PAYLOAD / "vendor"
FFMPEG_DIR = PAYLOAD / "ffmpeg"

FFMPEG_ZIP = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
LEAFLET_BASE = "https://unpkg.com/leaflet@1.9.4/dist/"

LEAFLET_FILES = (
    "leaflet.js",
    "leaflet.css",
    "images/marker-icon.png",
    "images/marker-icon-2x.png",
    "images/marker-shadow.png",
    "images/layers.png",
    "images/layers-2x.png",
)

HEADERS = {"User-Agent": "Mozilla/5.0 (packaging-fetch)"}


def log(*parts):
    print(*parts, flush=True)


def fetch(url, timeout=180):
    request = urllib.request.Request(url, headers=HEADERS)

    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_leaflet():
    VENDOR.mkdir(parents=True, exist_ok=True)

    for name in LEAFLET_FILES:
        target = VENDOR / name

        if target.exists() and target.stat().st_size > 0:
            log(f"  跳过（已存在）vendor/{name}")
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        data = fetch(LEAFLET_BASE + name)
        target.write_bytes(data)
        log(f"  vendor/{name}  {len(data) / 1024:.1f} KB")


def fetch_ffmpeg():
    ffmpeg_exe = FFMPEG_DIR / "ffmpeg.exe"

    if ffmpeg_exe.exists() and ffmpeg_exe.stat().st_size > 10 * 1024 * 1024:
        log(f"  跳过（已存在）ffmpeg/ffmpeg.exe  {ffmpeg_exe.stat().st_size / 1024**2:.1f} MB")
        return

    log(f"  下载 {FFMPEG_ZIP}")
    blob = fetch(FFMPEG_ZIP)
    log(f"  下载完成 {len(blob) / 1024**2:.1f} MB，解包中……")

    FFMPEG_DIR.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        wanted = []

        for info in archive.infolist():
            name = info.filename

            if name.endswith("/"):
                continue

            base = name.rsplit("/", 1)[-1].lower()

            if base in ("ffmpeg.exe", "license", "readme.txt"):
                wanted.append(info)

        if not any(i.filename.lower().endswith("ffmpeg.exe") for i in wanted):
            raise SystemExit("压缩包里没找到 ffmpeg.exe，下载内容可能不对")

        for info in wanted:
            base = info.filename.rsplit("/", 1)[-1]
            target = FFMPEG_DIR / base

            with archive.open(info) as source, target.open("wb") as out:
                shutil.copyfileobj(source, out)

            log(f"  ffmpeg/{base}  {target.stat().st_size / 1024**2:.1f} MB")


def main():
    log("准备打包资源 ->", PAYLOAD)

    log("[1/2] Leaflet（前端地图库，离线可用）")
    fetch_leaflet()

    log("[2/2] ffmpeg（抽帧 + 4K HEVC 转码）")
    fetch_ffmpeg()

    total = sum(p.stat().st_size for p in PAYLOAD.rglob("*") if p.is_file())
    log(f"完成，payload 合计 {total / 1024**2:.1f} MB")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
