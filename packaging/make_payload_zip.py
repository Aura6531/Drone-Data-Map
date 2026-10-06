"""把目录版程序（packaging/dist/UAVMap）压成 payload.zip，给安装程序当载荷。

用 LZMA：150MB 的目录版能压到 ~60-80MB，安装程序 exe 也就这个量级。
条目按「相对安装目录」存，所以解压到安装目录后 UAVMap.exe 就在根上。

用法：python packaging/make_payload_zip.py
"""

import os
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 默认打包正式版（dist/UAVMap）；可以把 UAVMAP_PAYLOAD_SOURCE 指到别的目录
# （例如 dist/UAVMapDebug），用来做「安装 -> 运行 -> 全流程」的自动化验证。
SOURCE = Path(os.environ.get("UAVMAP_PAYLOAD_SOURCE") or (HERE / "dist" / "UAVMap"))
TARGET = HERE / "payload.zip"


def main():
    if not SOURCE.is_dir() or not any(SOURCE.glob("*.exe")):
        raise SystemExit(f"没找到目录版程序：{SOURCE}（先跑 build_installer.ps1 的前半段）")

    print(f"  载荷来源：{SOURCE}")

    if TARGET.exists():
        TARGET.unlink()

    files = sorted(path for path in SOURCE.rglob("*") if path.is_file())
    started = time.time()

    with zipfile.ZipFile(TARGET, "w", zipfile.ZIP_LZMA, compresslevel=6) as package:

        for path in files:
            package.write(path, path.relative_to(SOURCE).as_posix())

    size = TARGET.stat().st_size / 1024**2
    raw = sum(path.stat().st_size for path in files) / 1024**2

    print(f"  载荷 {len(files)} 个文件：{raw:.1f} MB -> {size:.1f} MB（LZMA，耗时 {time.time() - started:.0f}s）")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
