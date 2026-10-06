"""安装向导「点击流程」冒烟测试（不需要人看界面）。

做法：构造向导窗口但不进入 mainloop，然后程序化点击
「下一步 -> 下一步 -> 开始安装 -> 完成」，检查完成页是否真的就位。
专门防这类只在点击路径上出现的错：装完了却还停在「正在安装……」、
按钮没变成「完成」、还得多点一次确认。

**不进 run_tests.js**（它要装一遍 150MB，约 40 秒），需要时手动跑：

    python smoke_installer_wizard.py [安装目录]

跑完会自己清理：安装目录、桌面与开始菜单的快捷方式、注册表卸载项。
"""

import importlib.util
import os
import pathlib
import shutil
import sys
import tkinter
import winreg

sys.stdout.reconfigure(encoding="utf-8")

TARGET = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else r"packaging\_wizardtest")
REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\无人机巡查数据地图"

spec = importlib.util.spec_from_file_location("inst", "packaging/uavmap_installer.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

tkinter.Tk.mainloop = lambda self: None          # 不进事件循环

created = {}
original_tk = tkinter.Tk


def capturing_tk(*args, **kwargs):
    root = original_tk(*args, **kwargs)
    created["root"] = root
    return root


tkinter.Tk = capturing_tk
installer.run_wizard()
tkinter.Tk = original_tk

root = created.get("root")

if root is None:
    raise SystemExit("没能抓到向导窗口")

print("  向导构造成功")


def walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from walk(child)


def button(label):
    for widget in walk(root):
        if isinstance(widget, tkinter.Button) and widget.cget("text") == label:
            return widget

    return None


entries = [w for w in walk(root) if isinstance(w, tkinter.Entry)]
checks = [w for w in walk(root) if isinstance(w, tkinter.Checkbutton)]
print(f"  输入框 {len(entries)} 个、复选框 {len(checks)} 个")

shutil.rmtree(TARGET, ignore_errors=True)
entries[0].delete(0, "end")
entries[0].insert(0, str(TARGET))

button("下一步").invoke()                          # -> 天地图 key 页
button("下一步").invoke()                          # -> 附加任务页

for check in checks:
    if "启动" in check.cget("text") and root.getvar(check.cget("variable")):
        check.invoke()                             # 取消「立即启动」，测试时别弹浏览器
        print("  已取消勾选：", check.cget("text"))

button("开始安装").invoke()                        # 同步跑完安装

labels = [w.cget("text") for w in walk(root) if isinstance(w, tkinter.Label)]
finish = button("完成")
result = next((t for t in labels if t and "已安装到" in t), "")

checks_done = [
    ("标题变为『安装完成』", "安装完成" in labels),
    ("结果说明写在页面上", bool(result)),
    ("按钮变为『完成』且可用", bool(finish) and str(finish.cget("state")) == "normal"),
    ("不再有『正在安装……』", "正在安装……" not in labels),
    ("卸载说明（保留 Data/Project）写在页面上", "卸载.bat" in result),
    ("程序文件确实装上了", (TARGET / "UAVMap.exe").is_file()),
]

print()
for label, ok in checks_done:
    print(f"  [{'OK' if ok else 'FAIL'}] {label}")

finish.invoke()                                    # 关掉向导
print("  点『完成』后窗口已销毁（TclError 即证明）")

# ---- 自清理：安装目录、快捷方式、注册表 ----
shutil.rmtree(TARGET, ignore_errors=True)

for link in (
    pathlib.Path.home() / "Desktop" / f"{installer.APP_NAME}.lnk",
    pathlib.Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs"
    / f"{installer.APP_NAME}.lnk",
):
    try:
        link.unlink()
        print("  已清理快捷方式：", link.name)

    except OSError:
        pass

try:
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_PATH)
    print("  已清理注册表卸载项")

except OSError:
    pass

failed = [label for label, ok in checks_done if not ok]
print(f"\n结果: {'全部通过' if not failed else '有失败项：' + '、'.join(failed)}")
sys.exit(1 if failed else 0)
