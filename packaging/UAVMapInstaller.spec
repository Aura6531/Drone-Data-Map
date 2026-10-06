# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 配置：安装程序（单文件 exe，内含 LZMA 载荷）。

构建：
    $env:PYTHONPATH = "packaging\\build_libs"
    python packaging\\make_payload_zip.py          # 先做载荷
    python -m PyInstaller packaging\\UAVMapInstaller.spec --noconfirm --clean --distpath packaging\\dist-installer --workpath packaging\\build-installer

    # 调试版（带控制台，便于自动化验证）：
    $env:UAVMAP_CONSOLE = "1" ... 同上

产物：packaging/dist-installer/无人机巡查数据地图_安装程序.exe（约 80MB，单文件）
"""

import os
from pathlib import Path

SPEC_DIR = Path(SPECPATH)

CONSOLE = os.environ.get("UAVMAP_CONSOLE") == "1"
ONEFOLDER = os.environ.get("UAVMAP_INSTALLER_ONEFOLDER") == "1"
NAME = "UAVMapInstallerDebug" if CONSOLE else "无人机巡查数据地图_安装程序"

PAYLOAD = SPEC_DIR / "payload.zip"

if not PAYLOAD.is_file():
    raise SystemExit("缺 packaging/payload.zip —— 先跑 python packaging/make_payload_zip.py")

a = Analysis(
    [str(SPEC_DIR / "uavmap_installer.py")],
    pathex=[str(SPEC_DIR)],
    binaries=[],
    datas=[(str(PAYLOAD), ".")],
    hiddenimports=["tkinter", "tkinter.filedialog", "tkinter.messagebox", "tkinter.ttk"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "numpy", "requests", "matplotlib", "pytest", "scipy", "pandas",
        "PIL", "docx", "lxml", "pystray", "PyQt5", "PySide2",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

if ONEFOLDER:
    # 目录版安装程序：exe + payload.zip 两个文件（打包成 zip 分发，启动快、无临时解包）
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=CONSOLE,
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
        name=NAME,
    )

else:
    # 单文件版：一个 exe（首次启动会把内容解到 %TEMP%，真机可用；
    # 受限环境里可能因为临时目录不可写而失败）
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=CONSOLE,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(SPEC_DIR / "UAVMap.ico"),
    )
