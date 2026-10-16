# -*- coding: utf-8 -*-
"""界面文案（英 -> 中）。

## 为什么这里用**英文原串当键**

因为界面本来就是英文的（用户 2026-10-07 起陆续要求把中文界面改成英文）。
所以英文原文已经在代码里了，再加一层抽象键名（`ui.load_tracks`）只是多一处
要对齐的东西。直接用英文串当键：

    L("Load all tracks")     # 英文环境下返回原串，中文环境下查表

好处：
  · **未翻译的串自动退回英文**，不会出现空白或键名（渐进式覆盖，不炸界面）
  · 改代码时不用同步维护键名

坏处（要接受）：改了英文原文，译文就对不上了。所以：
  · `self_check_ui()` 会报出"字典里有、但页面里已经找不到"的串
  · 改英文原文时，记得同步改这里的键

## 与 i18n.py 的分工

  i18n.py     结构化文案（带参数、有键名）：后端消息、报告模板
  i18n_ui.py  界面短文案：按钮、标题、提示（英文原串当键）
"""
from __future__ import annotations

# 英文原串 -> 中文
UI_ZH: dict[str, str] = {

    # ---------------- 左栏：项目 ----------------
    "Project": "项目",
    "Project name": "项目名称",
    "Select project": "选择项目",
    "New project": "新建项目",
    "Import data": "导入数据",
    "Markers": "标记点",
    "Tracks": "航迹",
    "Project ›": "项目 ›",
    "‹ Markers": "‹ 标记点",
    "Project data": "项目数据",
    "Back to project / tracks": "返回项目 / 航迹",
    "Back to project": "返回项目",
    "Remove the current project from the list": "把当前项目从列表中移除",
    "Create a new project": "新建一个项目",
    "Add a data folder to the current project": "把数据文件夹加入当前项目",

    # ---------------- 左栏：文件列表 ----------------
    "Date": "日期",
    "Type": "类型",
    "All dates": "全部日期",
    "All types": "全部类型",
    "Refresh": "刷新",
    "Clear": "清除",
    "Delete": "删除",
    "Load": "加载",
    "Load all tracks": "加载全部航迹",
    "Load filtered": "加载筛选结果",
    "Build tracks": "生成航迹",
    "Build tracks ✓": "生成航迹 ✓",
    "No projects": "没有项目",
    "No files match the filter. Try setting Date or Type back to “All”.":
        "没有文件符合当前筛选。把「日期」或「类型」调回「全部」试试。",
    "This project has no GeoJSON yet. Use “Make GeoJSON” above, or create a project and import data first.":
        "这个项目还没有 GeoJSON。用上面的「生成 GeoJSON」，或者先新建项目并导入数据。",

    # ---------------- 左栏：标记点 ----------------
    "Select all": "全选",
    "Name · Lat · Lng (newest first)": "名称 · 纬度 · 经度（新的在前）",
    "Export KML": "导出 KML",
    "Copy lat/lng": "复制经纬度",
    "Generate report": "生成报告",
    "No markers yet: right-click on the video frame, name the point, and it appears here.":
        "还没有标记点：在视频画面上右键，给这个点起个名字，它就会出现在这里。",
    "Click to jump: centers the map and opens the video at that frame":
        "点击跳转：把地图居中，并打开视频定位到那一帧",
    "Check markers to delete, export or copy them in bulk":
        "勾选标记点后可批量删除、导出或复制",
    "Delete this marker (asks for confirmation)": "删除这个标记点（会先确认）",
    "This marker has no matching video frame.": "这个标记点没有对应的视频帧。",
    "Select the markers to export first (use “Select all” in the header).":
        "请先勾选要导出的标记点（用表头的「全选」）。",

    # ---------------- 地图 / 搜索 ----------------
    "Track map": "轨迹地图",
    "Search a place, e.g. Zhaoqing, Nan'an Street": "搜索地点，例如 肇庆、南岸街道",
    "Search place": "搜索地点",
    "Find flights at this position": "查找经过此处的架次",
    "Frames of this spot": "此处的画面",
    "Clear selection": "清除选择",
    "Selected position (map click)": "已选位置（地图点击）",
    "Street (Tianditu)": "街道图（天地图）",
    "Satellite (Tianditu imagery)": "卫星图（天地图影像）",
    "Base map": "底图",
    "Coverage": "视场覆盖",
    "Follow": "跟随",
    "Follow · Fit": "跟随 · 适配",
    "Follow · Center": "跟随 · 居中",
    "No follow": "不跟随",
    "Show the search and action buttons": "展开搜索与操作按钮",
    "Collapse these controls to see more of the map": "收起这些控件，让地图更大",

    # ---------------- 覆盖面板 ----------------
    "Build coverage": "构建覆盖",
    "Confidence": "置信度",
    "high": "高",
    "medium": "中",
    "low": "低",
    "very_low": "很低",
    "No coverage grid yet.": "还没有覆盖网格。",
    "Not built": "未构建",
    "Built": "已构建",
    "Stale (source changed)": "已过期（源文件变了）",

    # ---------------- 视频 / 图墙 ----------------
    "Video": "视频",
    "Crosshair": "准星",
    "FOV": "视场",
    "Mini map": "小地图",
    "2× speed": "2× 速度",
    "Export ±5s": "导出 ±5s",
    "Play from here": "从这里播放",
    "Play video here": "在此播放视频",
    "Click “Play from here” in a track popup on the map, or “Play video here” in the results below; the video shows in this column.":
        "点地图上航迹弹窗里的「从这里播放」，或下面结果里的「在此播放视频」，视频会显示在这一栏。",
    "Different angles": "不同角度",
    "Centred 25%": "居中 25%",
    "Centred 10%": "居中 10%",
    "Anywhere": "不限位置",
    "Searching every flight in this project…": "正在检索这个项目的每一趟飞行…",
    "Closest to the centre first": "离画面中心最近的优先",
    "Sorted by sharpness": "按清晰度排序",
    "centred — recommended": "居中 — 推荐",
    "zoomed & covering — recommended": "变焦且覆盖 — 推荐",
    "off-centre, wide lens": "偏离中心，广角",
    "360 — nearest first": "360 — 最近的优先",
    "sphere (no gimbal)": "球面（无云台）",
    "from the drone": "距无人机",
    "bearing": "方位",
    "from centre": "偏离中心",
    "from edge": "距边缘",
    "frame(s)": "帧",
    "pass(es)": "趟",
    "this pass": "本趟",

    # ---------------- 视频状态 ----------------
    # 注意：只留一条 "Loading…"。曾经同时收了 "Loading…" 与 "loading…"，
    # 生成的 JSON 就有**重复键**，严格解析器（PowerShell 的 ConvertFrom-Json、
    # 部分严格 JSON 库）会直接报错。字典的键必须唯一。
    "Loading…": "加载中…",
    "Playback aborted": "播放已中止",
    "Network error: the video data could not be fetched": "网络错误：取不到视频数据",
    "Decode error: the video data is damaged": "解码错误：视频数据损坏",
    "This browser does not support the video's codec": "这个浏览器不支持该视频的编码格式",
    "no frame": "无画面",
    "Reload": "重新加载",

    # ---------------- 照片 ----------------
    "Photos": "照片",
    "Load all photos": "加载全部照片",
    "Photo panel below the map": "照片面板在地图下方",
    "Position: measured (laser rangefinder)": "位置：实测（激光测距）",
    "Position: approximate (flat-ground estimate)": "位置：估算（平地模型）",
    "Click to show below": "点击在下方显示",
    "Open the video at this photo's time": "打开视频定位到这张照片的时刻",
    # 计数标签用 "photo(s)"，**不要**用 "photos" ——
    # 它和上面的 "Photos"（面板标题）在 JSON 里是同一个键（键比较大小写），
    # 会产生重复键，严格解析器（PowerShell 的 ConvertFrom-Json）直接报错。
    "photo(s)": "张照片",
    "target(s)": "个目标",
    "merged": "已合并",

    # ---------------- 弹框 / 通用 ----------------
    "Language": "语言",
    "Close": "关闭",
    "Cancel": "取消",
    "Save": "保存",
    "OK": "确定",
    "Yes": "是",
    "No": "否",
    "Confirm": "确认",
    "Dismiss": "关闭",
    "Error": "错误",
    "Warning": "警告",
    "Unknown error": "未知错误",

    # ---------------- 脚本错误横幅 ----------------
    "Page script error:": "页面脚本出错：",
    "Unhandled async error:": "未处理的异步错误：",
    "(If you only see a blank area, please report this to the developer)":
        "（如果只看到一片空白，请把这个情况反馈给开发者）",

    # ---------------- 时间轴同步弹框 ----------------
    "Video and track are out of sync": "视频与航迹的时间轴不同步",
    "Some video files no longer match the timeline in their track (or SRT) file. This usually means the video was trimmed outside this program — at the head, the tail, or somewhere in the middle (a signal dropout that was cut out).":
        "有些视频已经和航迹（或 SRT）里的时间轴对不上了。"
        "这通常意味着视频在本程序之外被裁过 —— 开头、结尾，"
        "**或者中间某一段**（飞行时信号卡顿被剪掉了）。",
    "When that happens the whole time axis is wrong: frame search opens the wrong moment, thumbnails show the wrong frame, and the drone marker on the map drifts off the track. Rebuilding the SRT and track from the current video is the only reliable fix — shifting timestamps cannot repair a cut in the middle.":
        "一旦这样，整条时间轴就都错了：检索会跳到错的时刻、缩略图是错的画面、"
        "地图上的无人机标记会沿航迹飘走。**从当前视频重新生成 SRT 与航迹**"
        "是唯一可靠的办法 —— 平移时间戳修不了中间被剪掉的情况。",
    "Rebuild SRT & tracks for these": "为这些重新生成 SRT 与航迹",
    "Not now": "稍后再说",
    "No duration mismatch found.": "没有发现时长不一致。",

    # ---------------- 表格/统计 ----------------
    "Summary": "汇总",
    "Contents": "目录",
    "Name": "名称",
    "Location": "位置",
    "Video file": "视频文件",
    "Video time": "视频时刻",
    "Generated": "生成时间",
    "Video frames": "视频帧",
}


def self_check_ui():
    """返回 (重复项, 空项) —— 供自检用。"""
    dups = []
    empties = []
    for k, v in UI_ZH.items():
        if not v or not v.strip():
            empties.append(k)
    return dups, empties
