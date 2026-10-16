# -*- coding: utf-8 -*-
"""应用级设置（很小的一份，只有一个语言选项）。

## 为什么放服务端持久化，而不是只用 localStorage

语言这个偏好**后端也要用**，而且有些调用**没有请求上下文** ——
最典型的是 Windows 文件选择对话框（`pick.folder_multi` 那类文案），
它是在一个独立线程里弹的，拿不到"这次请求带的语言"。

所以：语言存成一份服务端设置，前端切换时通知一次。
请求级覆盖（`?lang=` / `Accept-Language`）仍然有效，优先级更高。

文件放在 `Project/_settings.json` —— 与项目状态同处，且已在 .gitignore 覆盖范围内
（`Project/` 不进仓库）。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "Project" / "_settings.json"
_lock = threading.Lock()
_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    data = {}
    try:
        if SETTINGS_PATH.is_file():
            loaded = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
    except (OSError, ValueError):
        data = {}
    _cache = data
    return _cache


def get(key: str, default=None):
    return _load().get(key, default)


def set_value(key: str, value) -> dict:
    global _cache
    with _lock:
        data = dict(_load())
        data[key] = value
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                           encoding="utf-8")
            tmp.replace(SETTINGS_PATH)
        except OSError:
            pass
        _cache = data
    return _cache


def reload():
    global _cache
    _cache = None
