"""无人机巡查数据地图 —— 安装程序（自带向导，不依赖 Inno Setup）。

为什么要自己做一个：Inno Setup 的编译器（ISCC）需要先跑一次图形安装程序才能拿到，
而本项目的开发/构建环境拿不到（见 docs/交接说明.md）。这个安装程序用 Python + PyInstaller
打成单个 exe，功能与 Inno 方案对齐：

  * 默认装到 %LOCALAPPDATA%\\无人机巡查数据地图（数据放程序目录内，所以安装目录必须可写）
  * 向导最后一页让使用者填天地图 key（附申请链接与三步说明），写进 <安装目录>\\tianditu_key.txt
  * 开始菜单快捷方式 + 可选桌面快捷方式；**不开机自启**
  * 注册表卸载项（HKCU，按用户，不需要管理员）
  * 卸载时**保留 Data\\ 与 Project\\**（用户数据）

用法：
    uavmap_installer.exe                                    # 图形向导
    uavmap_installer.exe --silent --dir <安装目录> [--key <tk>] [--no-desktop-icon]
    uavmap_installer.exe --uninstall --dir <安装目录> [--silent]

载荷：与本程序同目录（或 PyInstaller 解包目录）里的 payload.zip（LZMA 压缩的目录版程序）。
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
import winreg
import zipfile
from pathlib import Path

APP_NAME = "无人机巡查数据地图"
APP_EXE = "UAVMap.exe"
APP_VERSION = "1.0.0"
REG_PATH = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_NAME}"
KEY_URL = "https://lbs.tianditu.gov.cn/authorization/authorization.html"
UNINSTALL_BAT = "卸载.bat"
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def base_dir():
    """本程序所在目录（打包后在 _MEIPASS 里）。"""

    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def payload_zip():
    candidate = base_dir() / "payload.zip"

    if not candidate.is_file():
        raise SystemExit(f"找不到载荷 payload.zip（应在 {candidate}）")

    return candidate


def default_dir():
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / APP_NAME


def log(message):
    print(message, flush=True)


# ------------------------------------------------------------
# 安装
# ------------------------------------------------------------

def extract_payload(target, progress=None):
    archive = payload_zip()
    target.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive) as package:
        members = package.infolist()
        total = len(members)

        for index, member in enumerate(members, start=1):
            package.extract(member, target)

            if progress and (index % 20 == 0 or index == total):
                progress(index / total)

    return total


def write_key(target, key):
    key = (key or "").strip()

    if not key:
        return False

    (target / "tianditu_key.txt").write_text(key + "\n", encoding="utf-8")
    return True


def make_shortcut(link, target, workdir, icon):
    """用 PowerShell 的 WScript.Shell 建 .lnk（不引入 pywin32）。"""

    if not link:
        return False

    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{link}');"
        "$s.TargetPath='{target}';"
        "$s.WorkingDirectory='{work}';"
        "$s.IconLocation='{icon}';"
        "$s.Description='{name}';"
        "$s.Save()"
    ).format(link=link, target=target, work=workdir, icon=icon, name=APP_NAME)

    try:
        done = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            check=False,
            creationflags=CREATE_NO_WINDOW,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    except OSError as e:
        log(f"  快捷方式没建成（{link}）：{e}")
        return False

    if Path(link).exists():
        return True

    detail = (done.stderr or done.stdout or "").strip().splitlines()
    log(f"  快捷方式没建成（{link}）：{detail[-1] if detail else 'PowerShell 没有报错但文件不存在'}")

    return False


def shortcuts_for(target, desktop_icon=True):
    program_links = Path(os.environ.get("APPDATA") or "") / "Microsoft/Windows/Start Menu/Programs"
    desktop = Path(os.environ.get("USERPROFILE") or "") / "Desktop"

    exe = target / APP_EXE
    icon = target / "UAVMap.ico"
    created = []

    if make_shortcut(program_links / f"{APP_NAME}.lnk", exe, target, icon):
        created.append("开始菜单")

    if desktop_icon and make_shortcut(desktop / f"{APP_NAME}.lnk", exe, target, icon):
        created.append("桌面")

    return created


def remove_shortcuts():
    program_links = Path(os.environ.get("APPDATA") or "") / "Microsoft/Windows/Start Menu/Programs"
    desktop = Path(os.environ.get("USERPROFILE") or "") / "Desktop"

    for link in (program_links / f"{APP_NAME}.lnk", desktop / f"{APP_NAME}.lnk"):

        try:
            link.unlink()

        except OSError:
            pass


def write_uninstall_bat(target):
    """在安装目录放一个卸载脚本，并把它写进注册表。

    卸载只删程序文件与缓存，**Data\\ 与 Project\\ 一定保留**。
    """

    lines = [
        "@echo off",
        "chcp 65001 >nul",
        f"title 卸载 {APP_NAME}",
        "echo.",
        f"echo 即将卸载「{APP_NAME}」。",
        "echo 你的数据（Data\\ 与 Project\\）会被保留，不会删除。",
        "echo.",
        "pause",
        "cd /d %TEMP%",
        f'reg delete "{REG_PATH}" /f >nul 2>nul',
        f'del "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\{APP_NAME}.lnk" >nul 2>nul',
        f'del "%USERPROFILE%\\Desktop\\{APP_NAME}.lnk" >nul 2>nul',
        'rmdir /s /q "%~dp0_internal" >nul 2>nul',
        'rmdir /s /q "%~dp0tile_cache" "%~dp0video_proxy" "%~dp0report_cache" "%~dp0geocode_cache" >nul 2>nul',
        'rmdir /s /q "%~dp0说明" >nul 2>nul',
        f'del "%~dp0{APP_EXE}" "%~dp0UAVMap.ico" "%~dp0使用说明.md" "%~dp0运行日志.txt" "%~dp0tianditu_key.txt" >nul 2>nul',
        f'del "%~dp0{UNINSTALL_BAT}" >nul 2>nul',
        "echo.",
        "echo 已卸载。Data\\ 与 Project\\ 仍在原目录，可自行备份或删除。",
        "timeout /t 5 >nul",
        'rmdir "%~dp0" >nul 2>nul',
    ]

    path = target / UNINSTALL_BAT
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("gbk", "replace"))

    return path


def write_registry(target, size_kb=0):
    """写卸载项。**失败不能让安装崩掉** —— 文件已经装好了，注册表只是方便卸载。

    （受限环境里 HKCU 也可能写不进去；那时提示一句，用户仍可从目录里的
      「卸载.bat」手动卸载。）
    """

    exe = target / APP_EXE
    bat = target / UNINSTALL_BAT

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(target))
            winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, str(exe))
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{bat}"')
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)

            if size_kb:
                winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, int(size_kb))

        return True

    except OSError as e:
        log(f"  注册表卸载项没写成（不影响使用，可用目录里的「{UNINSTALL_BAT}」卸载）：{e}")
        return False


def delete_registry():
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_PATH)

    except OSError:
        pass


def install(target, key=None, desktop_icon=True, progress=None):
    target = Path(target).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)

    # 装到 Program Files 这类只读目录时，早点说清楚（程序要求数据写在程序目录内）
    probe = target / ".write_probe"

    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()

    except OSError:
        raise SystemExit(
            f"这个目录不可写：{target}\n"
            f"请换一个当前用户有写权限的目录（默认 {default_dir()}）。"
        )

    count = extract_payload(target, progress)
    write_key(target, key)
    bat = write_uninstall_bat(target)

    created = shortcuts_for(target, desktop_icon)
    size_kb = sum(p.stat().st_size for p in target.rglob("*") if p.is_file()) // 1024
    write_registry(target, size_kb)

    log(f"已安装到 {target}")
    log(f"  释放文件：{count} 个，约 {size_kb / 1024:.1f} MB")
    log(f"  快捷方式：{'、'.join(created) if created else '（没建成）'}")
    log(f"  卸载脚本：{bat.name}")
    log(f"  天地图 key：{'已写入' if (target / 'tianditu_key.txt').is_file() else '未填（之后可放进该目录）'}")

    return target


def uninstall(target):
    target = Path(target).expanduser().resolve()

    remove_shortcuts()
    delete_registry()

    if not target.is_dir():
        log("安装目录不存在，只清理了快捷方式与注册表。")
        return

    # 保留用户数据
    keep = {"Data", "Project"}
    removed = 0

    for item in target.iterdir():

        if item.name in keep:
            continue

        try:
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)

            else:
                item.unlink()

            removed += 1

        except OSError:
            pass

    log(f"已卸载：清掉 {removed} 项；Data\\ 与 Project\\ 保留在 {target}")


# ------------------------------------------------------------
# 图形向导
# ------------------------------------------------------------

def run_wizard():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    state = {"dir": str(default_dir()), "key": "", "desktop": True, "launch": True}

    root = tk.Tk()
    root.title(f"{APP_NAME} 安装程序")

    # DPI：先让 tk 按屏幕比例换算字号，再把窗口与固定像素值一起放大
    scale = apply_dpi_scaling(root)
    px = lambda value: int(round(value * scale))          # noqa: E731

    root.geometry(f"{px(560)}x{px(430)}")
    root.resizable(False, False)

    header = tk.Label(root, text=APP_NAME, font=("Microsoft YaHei UI", 16, "bold"))
    header.pack(pady=(px(18), px(2)))

    sub = tk.Label(root, text=f"把无人机巡查数据地图装到这台电脑上（约 150MB）", fg="#555")
    sub.pack()

    body = tk.Frame(root, padx=px(24), pady=px(16))
    body.pack(fill="both", expand=True)

    # ---- 第 1 步：安装位置 ----
    step1 = tk.Frame(body)

    tk.Label(step1, text="安装位置（程序与数据都放这里，请选一个可写目录）", anchor="w").pack(fill="x")
    row = tk.Frame(step1)
    row.pack(fill="x", pady=6)
    dir_var = tk.StringVar(value=state["dir"])
    tk.Entry(row, textvariable=dir_var).pack(side="left", fill="x", expand=True)

    def browse():
        chosen = filedialog.askdirectory(title="选择安装目录", mustexist=False)

        if chosen:
            dir_var.set(chosen)

    tk.Button(row, text="浏览…", command=browse).pack(side="left", padx=(6, 0))
    tk.Label(
        step1,
        text="提示：不要装到 Program Files —— 程序会把导入的视频与标记点存在安装目录里。",
        fg="#a15c00", justify="left", wraplength=px(480)
    ).pack(fill="x", pady=(px(8), 0))

    # ---- 第 2 步：天地图 key ----
    step2 = tk.Frame(body)

    tk.Label(step2, text="天地图 key（可跳过）", anchor="w",
             font=("Microsoft YaHei UI", 11, "bold")).pack(fill="x")
    tk.Label(
        step2,
        text=("底图与地名搜索由天地图提供，需要一串属于你自己的 key（免费，约 2 分钟申请）：\n"
              "① 打开下面的「申请说明」页，注册/登录并申请成为开发者\n"
              "② 进「控制台 → 应用管理」创建应用，类型选「浏览器端」\n"
              "③ 把生成的 32 位 tk 粘到下面\n"
              "没填也能用：底图会退回 OpenStreetMap，只是地名搜索不可用。"),
        justify="left", wraplength=px(490), fg="#444"
    ).pack(fill="x", pady=(px(6), px(8)))

    key_var = tk.StringVar()
    tk.Label(step2, text="天地图 key（tk，32 位）：", anchor="w").pack(fill="x")
    tk.Entry(step2, textvariable=key_var).pack(fill="x", pady=6)

    link = tk.Label(step2, text=KEY_URL, fg="#1155cc", cursor="hand2")
    link.pack(anchor="w")

    def open_link(_event=None):
        try:
            os.startfile(KEY_URL)

        except Exception:
            messagebox.showinfo("申请地址", KEY_URL)

    link.bind("<Button-1>", open_link)

    # ---- 第 3 步：附加任务 ----
    step3 = tk.Frame(body)
    tk.Label(step3, text="附加任务", anchor="w",
             font=("Microsoft YaHei UI", 11, "bold")).pack(fill="x", pady=(0, 8))

    desktop_var = tk.BooleanVar(value=True)
    launch_var = tk.BooleanVar(value=True)
    tk.Checkbutton(step3, text="创建桌面快捷方式", variable=desktop_var).pack(anchor="w")
    tk.Checkbutton(step3, text="安装完成后立即启动", variable=launch_var).pack(anchor="w", pady=(4, 0))
    tk.Label(step3, text="（不会开机自启；程序常驻右下角托盘，右键图标可退出）",
             fg="#666").pack(anchor="w", pady=(10, 0))

    # ---- 安装 / 完成（同一页：装完就地变完成页，不再多弹一个框）----
    step4 = tk.Frame(body)

    status_label = tk.Label(step4, text="正在安装……", anchor="w",
                            font=("Microsoft YaHei UI", 11, "bold"))
    status_label.pack(fill="x")

    bar = ttk.Progressbar(step4, length=px(480), maximum=100)
    bar.pack(fill="x", pady=px(10))

    result_label = tk.Label(step4, text="", anchor="w", justify="left",
                            wraplength=px(480), fg="#333")
    result_label.pack(fill="x", pady=px(6))

    steps = [step1, step2, step3, step4]
    position = {"index": 0}

    def show(index):
        for frame in steps:
            frame.pack_forget()

        steps[index].pack(fill="both", expand=True)
        position["index"] = index
        back_btn.config(state="normal" if index in (1, 2) else "disabled")
        next_btn.config(text="开始安装" if index == 2 else ("完成" if index == 3 else "下一步"))
        next_btn.config(state="normal")
        cancel_btn.config(state="normal" if index < 3 else "disabled")

    def go_next():
        index = position["index"]

        if index == 0:
            target = dir_var.get().strip()

            if not target:
                messagebox.showwarning("提示", "请先选择安装目录。")
                return

            state["dir"] = target
            show(1)
            return

        if index == 1:
            state["key"] = key_var.get().strip()
            show(2)
            return

        if index == 2:
            state["desktop"] = desktop_var.get()
            state["launch"] = launch_var.get()
            show(3)
            root.update_idletasks()
            next_btn.config(state="disabled")
            back_btn.config(state="disabled")

            def progress(ratio):
                bar["value"] = ratio * 100
                root.update_idletasks()

            try:
                install(state["dir"], state["key"], state["desktop"], progress)

                # 就地变完成页：标题 + 进度条收起 + 结果说明，按钮变「完成」
                bar["value"] = 100
                bar.pack_forget()
                status_label.config(text="安装完成", fg="#137333")
                result_label.config(text=(
                    f"已安装到：{state['dir']}\n\n"
                    + ("下次启动会自动带上你填的天地图 key。\n" if state["key"]
                       else "还没填天地图 key：之后把 tk 放进该目录的 tianditu_key.txt 即可（存盘即生效）。\n")
                    + "\n卸载：控制面板「程序和功能」，或目录里的「卸载.bat」\n（会保留 Data\\ 与 Project\\）"
                    + ("\n\n点「完成」会自动启动程序。" if state["launch"] else "")
                ))
                next_btn.config(state="normal")

            except SystemExit as e:
                status_label.config(text="安装失败", fg="#b00020")
                result_label.config(text=str(e))
                messagebox.showerror("安装失败", str(e))
                next_btn.config(state="normal")
                back_btn.config(state="normal")

            except Exception as e:
                status_label.config(text="安装失败", fg="#b00020")
                result_label.config(text=f"{type(e).__name__}: {e}")
                messagebox.showerror("安装失败", f"{type(e).__name__}: {e}")
                next_btn.config(state="normal")
                back_btn.config(state="normal")

            return

        # 完成：需要的话把程序拉起来，然后关掉向导
        if state["launch"]:
            exe = Path(state["dir"]) / APP_EXE

            if exe.is_file():
                try:
                    subprocess.Popen([str(exe)], cwd=str(state["dir"]))

                except OSError:
                    pass

        root.destroy()

    footer = tk.Frame(root, padx=px(24), pady=px(14))
    footer.pack(fill="x", side="bottom")
    back_btn = tk.Button(footer, text="上一步", width=10, command=lambda: show(position["index"] - 1))
    back_btn.pack(side="left")
    next_btn = tk.Button(footer, text="下一步", width=12, command=go_next)
    next_btn.pack(side="right")
    cancel_btn = tk.Button(footer, text="取消", width=8, command=root.destroy)
    cancel_btn.pack(side="right", padx=8)

    show(0)
    root.mainloop()


def main():
    awareness = enable_dpi_awareness()

    parser = argparse.ArgumentParser(description=f"{APP_NAME} 安装程序")
    parser.add_argument("--silent", action="store_true", help="不显示界面（配合 --dir 使用）")
    parser.add_argument("--dir", help="安装目录")
    parser.add_argument("--key", help="天地图 key（tk）")
    parser.add_argument("--no-desktop-icon", action="store_true", help="不建桌面快捷方式")
    parser.add_argument("--uninstall", action="store_true", help="卸载")
    args = parser.parse_args()

    if args.uninstall:
        uninstall(args.dir or default_dir())
        return 0

    if args.silent or args.dir:
        log(f"DPI 感知：{awareness or '（未能声明，界面可能发虚）'}")
        install(args.dir or default_dir(), args.key, not args.no_desktop_icon)
        return 0

    run_wizard()

    return 0


def enable_dpi_awareness():
    """声明本进程 DPI 感知 —— 否则高分屏上 Windows 会把窗口整体位图拉伸，字发虚。

    必须在**创建任何窗口之前**调用。三种 API 依次尝试（新系统到老系统），
    全都失败也不影响功能（只是界面可能糊）。
    """

    import ctypes

    # 1) Per-Monitor v2（Win10 1703+）
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return "PerMonitorV2"

    except Exception:
        pass

    # 2) Per-Monitor（Win8.1+）
    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
            return "PerMonitor"

    except Exception:
        pass

    # 3) 系统级（Vista+）
    try:
        if ctypes.windll.user32.SetProcessDPIAware():
            return "System"

    except Exception:
        pass

    return ""


def dpi_scale():
    """当前系统 DPI 相对 96 的比例（100% -> 1.0、150% -> 1.5）。"""

    import ctypes

    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()

    except Exception:
        try:
            hdc = ctypes.windll.user32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)      # LOGPIXELSX
            ctypes.windll.user32.ReleaseDC(0, hdc)

        except Exception:
            return 1.0

    return max(1.0, round((dpi or 96) / 96.0, 4))


def apply_dpi_scaling(root):
    """把 tk 的字号换算基准和窗口尺寸按 DPI 放大，返回比例。"""

    scale = dpi_scale()

    try:
        # tk 的 scaling = 每「点」多少像素：96dpi 时 96/72=1.333
        root.tk.call("tk", "scaling", scale * 96.0 / 72.0)

    except Exception:
        pass

    return scale


def prepare_streams():
    """无控制台的 exe（console=False）里 sys.stdout/stderr 是 None —— 不能直接 reconfigure。

    （这正是本项目打包版踩过的坑：windowed 下任何对 sys.stdout 的操作都要先判空。
      顺便把异常也写到日志，出事时能查。）
    """

    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)

        if stream is None:
            continue

        try:
            stream.reconfigure(encoding="utf-8", errors="replace")

        except Exception:
            pass


def log_path():
    import tempfile

    return Path(tempfile.gettempdir()) / "无人机巡查安装日志.txt"


def report_crash(error):
    """把未处理异常写进日志 + 弹一个能看懂的提示框（无控制台时这是唯一线索）。"""

    import traceback

    detail = "".join(traceback.format_exception(type(error), error, error.__traceback__))

    try:
        log_path().write_text(detail, encoding="utf-8")

    except OSError:
        pass

    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(
            f"{APP_NAME} 安装程序出错",
            f"{type(error).__name__}: {error}\n\n详细信息：{log_path()}",
        )
        root.destroy()

    except Exception:
        pass

    print(detail, flush=True)


if __name__ == "__main__":
    prepare_streams()

    try:
        sys.exit(main())

    except SystemExit:
        raise

    except BaseException as crash:      # noqa: BLE001 - 最后一道兜底
        report_crash(crash)
        sys.exit(1)
