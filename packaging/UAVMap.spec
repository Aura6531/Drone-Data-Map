# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：无人机巡查数据地图（目录版）。

构建（在仓库根目录执行）：
    $env:PYTHONPATH = "packaging\\build_libs"
    python -m PyInstaller packaging\\UAVMap.spec --noconfirm --clean

产物：packaging/dist/UAVMap/UAVMap.exe + _internal/（同目录整份拷走即可运行）
安装包由 packaging/UAVMap.iss（Inno Setup）在这个产物外面再套一层。

几个刻意的选择：
- console=False：不做黑窗口（关闭走托盘图标）。出错信息写进数据目录的「运行日志.txt」。
- upx=False：UPX 压缩是杀软误报的重灾区，宁可比它大几 MB。
- 把页面/图标/vendor/ffmpeg 都塞进 bundle：EXE 侧按 CODE_DIR（= _MEIPASS）找它们。
- 显式钉上 docx 的模板文件：python-docx 生成文档时要用它，漏了就是一生成就报错。
"""

import os
import sys
from pathlib import Path

SPEC_DIR = Path(SPECPATH)
ROOT = SPEC_DIR.parent
PAYLOAD = SPEC_DIR / "payload"

# 调试构建：UAVMAP_CONSOLE=1 时带控制台（能看见 traceback），产物名也区分开
CONSOLE = os.environ.get("UAVMAP_CONSOLE") == "1"
APP_NAME = "UAVMapDebug" if CONSOLE else "UAVMap"

import docx  # noqa: E402  用它的真实位置定位模板文件

DOCX_TEMPLATE = Path(docx.__file__).parent / "templates" / "default.docx"

# 页面（6 个）：页面里都是相对路径请求，放 bundle 根目录即可
PAGES = [
    "project_manager.html",
    "project_import.html",
    "project_media.html",
    "project_video_inspector.html",
    "project_geojson_preview.html",
    "project_geo3d_preview.html",
]

datas = [(str(ROOT / "Code" / page), ".") for page in PAGES]

datas += [
    (str(SPEC_DIR / "UAVMap.ico"), "."),
    (str(ROOT / "docs" / "使用说明.md"), "."),
    # 「申请指南」PDF：网页上补填天地图 key 的弹窗里点它打开（路由 /key-guide.pdf）
    (str(ROOT / "docs" / "天地图key申请教程.pdf"), "docs"),
    (str(DOCX_TEMPLATE), "docx/templates"),
]

# 前端地图库（Leaflet）：整份 payload/vendor 进 bundle/vendor
if (PAYLOAD / "vendor").is_dir():
    datas.append((str(PAYLOAD / "vendor"), "vendor"))

# ffmpeg：只带 ffmpeg.exe 与它的许可/说明（ffprobe 代码里没用到）
for name in ("ffmpeg.exe", "LICENSE", "README.txt"):
    candidate = PAYLOAD / "ffmpeg" / name

    if candidate.is_file():
        datas.append((str(candidate), "ffmpeg"))

a = Analysis(
    [str(ROOT / "Code" / "project_manager.py")],
    pathex=[str(ROOT / "Code")],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "pystray._win32",          # pystray 的后端是运行时挑的，必须显式钉
        "PIL._tkinter_finder",     # Pillow + tkinter 的老坑
        "lxml.etree",
        "lxml._elementpath",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(SPEC_DIR / "runtime_log.py")],   # 入口脚本之前就装好日志/异常兜底
    excludes=[
        "numpy", "requests", "matplotlib", "pytest", "scipy", "pandas",
        "PyQt5", "PySide2", "IPython", "notebook",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=CONSOLE,               # 正式版不做黑窗口；关程序走托盘图标
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(SPEC_DIR / "UAVMap.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
