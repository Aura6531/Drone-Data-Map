"""下载打包工具（PyInstaller / pystray 及其依赖）到 packaging/build_libs。

为什么不直接用 pip：
    这台机器上 pip 写 `<wheel>.whl.metadata` 会稳定报
    `PermissionError: [Errno 13]`（实时扫描把刚下下来的文件锁住），
    换 --target / 换 TEMP 目录都一样。所以这里自己查 PyPI、
    自己下 wheel、自己按 zip 解开 —— wheel 本来就是 zip，内容与安装后的目录一一对应。

用法：python fetch_build_libs.py
之后用 PYTHONPATH=packaging/build_libs 跑 `python -m PyInstaller ...` 即可。
"""

import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIBS_DIR = HERE / "build_libs"
WHEELS_DIR = HERE / "_wheels"

ROOTS = ("pyinstaller", "pystray")

# 这些如果当前 Python 里已经有，就不重复下载
ALREADY = ("setuptools", "packaging", "six", "PIL")

HEADERS = {"User-Agent": "Mozilla/5.0 (packaging-fetch)"}
PYPI_JSON = "https://pypi.org/pypi/{name}/json"


def log(*parts):
    print(*parts, flush=True)


def get_json(name):
    request = urllib.request.Request(PYPI_JSON.format(name=name), headers=HEADERS)

    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def pick_wheel(info):
    """挑一个能在 Windows + 当前 Python 上直接解开的 wheel。"""

    for item in info.get("urls", []):
        filename = item.get("filename", "")

        if not filename.endswith(".whl"):
            continue

        # 只要纯 Python 轮子（py3-none-any）或 win_amd64 的通用 py3 轮子
        if "py3-none-any" in filename or "py3-none-win_amd64" in filename:
            return item

    return None


def wheel_name(filename):
    return filename.split("-")[0]


def requirements_of(wheel_bytes):
    """从 wheel 的 METADATA 里读依赖名（跳过 extras）。"""

    names = []

    with zipfile.ZipFile(io.BytesIO(wheel_bytes)) as archive:

        for entry in archive.namelist():

            if not entry.endswith(".dist-info/METADATA"):
                continue

            text = archive.read(entry).decode("utf-8", "replace")

            for line in text.splitlines():

                if not line.startswith("Requires-Dist:"):
                    continue

                spec = line.split(":", 1)[1].strip()

                if "extra ==" in spec:      # 可选依赖，跳过
                    continue

                name = spec.split(";")[0].strip()
                name = name.split("[")[0].strip()
                name = name.split(" ")[0].strip()
                name = name.split("<")[0].split(">")[0].split("=")[0].strip()
                name = name.split("!")[0].strip()

                if name:
                    names.append(name.lower())

    return names


def is_importable(name):
    import importlib.util

    return importlib.util.find_spec(name) is not None


def main():
    LIBS_DIR.mkdir(parents=True, exist_ok=True)
    WHEELS_DIR.mkdir(parents=True, exist_ok=True)

    seen = set()
    queue = list(ROOTS)

    while queue:
        name = queue.pop(0).lower()

        if name in seen:
            continue

        seen.add(name)

        if name in ALREADY and is_importable(name):
            log(f"  跳过（当前 Python 已有）{name}")
            continue

        try:
            info = get_json(name)

        except Exception as e:
            log(f"  跳过 {name}（查不到：{e}）")
            continue

        wheel = pick_wheel(info)

        if wheel is None:
            log(f"  跳过 {name}（没有合适的纯 Python wheel）")
            continue

        target = WHEELS_DIR / wheel["filename"]

        if target.exists():
            blob = target.read_bytes()
            log(f"  已下载 {wheel['filename']}")

        else:
            request = urllib.request.Request(wheel["url"], headers=HEADERS)

            with urllib.request.urlopen(request, timeout=180) as response:
                blob = response.read()

            target.write_bytes(blob)
            log(f"  下载 {wheel['filename']}  {len(blob) / 1024:.0f} KB")

        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            archive.extractall(LIBS_DIR)

        queue.extend(requirements_of(blob))

    total = sum(p.stat().st_size for p in LIBS_DIR.rglob("*") if p.is_file())
    log(f"完成：{LIBS_DIR} 合计 {total / 1024**2:.1f} MB")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
