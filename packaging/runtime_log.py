"""PyInstaller runtime hook：在入口脚本执行【之前】就把日志与异常兜底装好。

为什么需要它：
    正式版是 windowed（console=False），没有控制台。如果崩在入口脚本之前
    （导入期），我们自己的日志代码根本没机会执行 —— 现象就是「双击没反应」，
    什么线索都没有。runtime hook 由 bootloader 在最早阶段执行，所以：
      * 把 stdout/stderr 重定向到 <exe 同级>/运行日志.txt
      * 捕获未处理异常（主线程 + 子线程），写进同一个日志
    这样即使程序起不来，也能从日志里看到原因。

注意：这个文件由打包后的进程执行，**不要** import 本项目的任何模块
（那时路径还是只读的 bundle）。
"""

import os
import sys
import threading
import time
import traceback
from pathlib import Path


def _log_stream():
    try:
        base = Path(sys.executable).resolve().parent
    except Exception:
        base = Path.cwd()

    for directory in (base, Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "无人机巡查数据地图"):
        try:
            directory.mkdir(parents=True, exist_ok=True)
            return (directory / "运行日志.txt").open("a", encoding="utf-8", buffering=1)
        except OSError:
            continue

    return None


_stream = _log_stream()

if _stream is not None:
    sys.stdout = _stream
    sys.stderr = _stream

    try:
        print()
        print("=" * 64)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 启动（打包版）")
        print(f"  exe    : {sys.executable}")
        print(f"  bundle : {getattr(sys, '_MEIPASS', '(无)')}")
        print(f"  cwd    : {os.getcwd()}")
    except Exception:
        pass


def _write_exception(kind, value, tb):
    try:
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {kind} 未处理异常：")
        traceback.print_exception(value, limit=None)
        print()
    except Exception:
        pass


def _excepthook(kind, value, tb):
    _write_exception("主线程", value, tb)


def _thread_excepthook(args):
    _write_exception("子线程", args.exc_value, args.exc_traceback)


sys.excepthook = _excepthook

try:
    threading.excepthook = _thread_excepthook
except Exception:
    pass
