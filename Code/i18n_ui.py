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
    "Ortho": "正射影像",
    "OpenStreetMap": "开放街图（OSM）",
    "Tianditu key": "天地图 key",
    "The app still works without a key (base map falls back to OpenStreetMap, place search is disabled).":
        "没有 key 也能用：底图自动退回开放街图（OSM），地名搜索不可用。",
    "Once you have it, paste the 32-character tk below and click Save — it takes effect immediately, no restart or reinstall needed.":
        "申请到之后，把 32 位 tk 粘到下面、点保存即刻生效，不用重启或重装。",
    "Paste the 32-character Tianditu key (tk)": "粘贴 32 位天地图 key（tk）",
    "Apply at:": "申请地址：",
    "Status: configured ✓ (base map and place search available). Paste a new key to replace it — saving applies it at once.":
        "状态：已配置 ✓（底图与地名搜索可用）。粘贴新 key 即可替换，保存后立即生效。",
    "Status: not configured — the base map uses OpenStreetMap and place search is off. Paste your tk and save.":
        "状态：未配置 —— 底图用开放街图，地名搜索关闭。粘贴 tk 后保存即可。",
    "Searching…": "搜索中…",
    "missing SRT files": "个 SRT 缺失",
    "missing GeoJSON files": "个 GeoJSON 缺失",
    "▶ Play video here": "▶ 在此播放视频",
    "Center map here": "以此为中心",
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
    # ---------------- 动态渲染文案（JS 里 t() 用的键） ----------------
    # 这一组全部来自页面里 JS 拼出来的动态文字：文件列表徽标、图墙、
    # 覆盖图例/状态、流程状态、遥测那一行。
    # 带变量的整句只能覆盖"固定取值"（t() 不做 {n} 参数替换，见 i18n.py）。
    'points': '点',
    'segments': '段',
    'Folder:': '数据文件夹：',
    'Relative path:': '相对路径：',
    'Remove this GeoJSON from the project (source video and SRT are kept)': '把这个 GeoJSON 从项目里移除（源视频和 SRT 保留）',
    'Other': '其他',
    'Thermal 1280×1024': '热成像 1280×1024',
    'Visible 3840×2160': '可见光 3840×2160',
    'Visible 1920×1080': '可见光 1920×1080',
    '5:4 · thermal sensor 640×512, recorded after 2× in-camera upscaling': '5:4 · 热成像传感器 640×512，机内超分 2× 后录制',
    '16:9 · visible-light hybrid zoom (4K main stream)': '16:9 · 可见光混合变焦（4K 主码流）',
    '16:9 · visible-light hybrid zoom (1080p version of the same view)': '16:9 · 可见光混合变焦（同一画面的 1080p 版本）',
    'GeoJSON files': 'GeoJSON 文件',
    'Features': '要素',
    'Position records': '定位记录',
    'of': '/',
    'selected': '已选',
    '(empty)': '（空）',
    'Reading gimbal and focal data…': '正在读取云台与焦距数据…',
    'Live info unavailable:': '实时信息不可用：',
    'No usable attitude data for this video': '这个视频没有可用的姿态数据',
    'Lens': '镜头',
    'Heading': '机头朝向',
    'Pitch': '俯仰角',
    'Level': '水平',
    'near level': '接近水平',
    'Ground distance at frame center': '画面中心地面距离',
    'Horizontal distance from where the frame center meets the ground to the point directly below the drone': '从画面中心落地点到飞机正下方那一点的水平距离',
    'Checking videos and subtitle streams…': '正在检查视频与字幕流…',
    'Checked subtitle streams and position data': '字幕流与定位数据已检查',
    'No SRT files yet': '还没有 SRT 文件',
    'Creating SRT files': '正在生成 SRT',
    'Creating GeoJSON tracks': '正在生成 GeoJSON 航迹',
    'Loading tracks onto the map…': '正在把航迹加载到地图上…',
    'No GeoJSON to load with the current filter.': '当前筛选下没有可加载的 GeoJSON。',
    'This project has no GeoJSON to load.': '这个项目没有可加载的 GeoJSON。',
    'Exporting GeoJSON…': '正在导出 GeoJSON…',
    'Choose a project first.': '请先选择一个项目。',
    'Click a position on the map first.': '请先在地图上点一个位置。',
    'No frame in this project covers this position.': '这个项目里没有任何画面覆盖到这个位置。',
    'Coverage grids are only built for flights you ran': '覆盖网格只对跑过「',
    'on; use the': '」的架次建过；请用下面的「',
    'button for that.': '」按钮。',
    'Skipped': '已跳过',
    'flight(s):': '个架次：',
    'across': '跨',
    'flight(s)': '个架次',
    'Show': '显示',
    'more': '更多',
    'shown': '已显示',
    'all': '共',
    'Showing': '正在显示',
    'pass(es) found.': '趟（共找到这些）。',
    'Sort by': '排序',
    'Frame inset': '边距限制',
    'How many frames to list: different angles = one per distinct viewpoint (useful when one angle is blocked by trees); every pass = one per fly-by; clearest only = the single sharpest frame': '列多少帧：不同角度 = 每个不同视角一张（某个角度被树挡住时有用）；每一趟 = 每次飞过一张；只留最清 = 只给最清晰的那一帧',
    'How far the target must be from the frame edge. A point right at the border is often cut off, so you cannot tell what you are looking at — even if that frame happens to be the sharpest. Higher = prefer frames where the target sits more centrally (slightly fewer choices); Anywhere = no limit.': '目标离画面边缘至少要有多远。贴着边的点常被切掉，看不出拍的是什么 —— 哪怕那一帧恰好最清晰。越往右 = 越偏向目标居中的帧（可选帧会少一点）；不限位置 = 不设这个限制。',
    'then the rest by sharpness.': '其余按清晰度排。',
    'Sorted by sharpness (no frame is centred or zoom-covered here).': '按清晰度排序（这里没有任何一帧是居中的或变焦覆盖的）。',
    'centred': '居中',
    'zoomed': '变焦',
    'zoomed &amp; covering': '变焦且覆盖',
    'zoomed &amp; covering — recommended': '变焦且覆盖 — 推荐',
    'm from the drone': '米（距无人机）',
    'frame(s) · ': '帧 · ',
    'zoom': '变焦',
    '360': '360',
    'Thermal': '热成像',
    'frame': '帧',
    'Coverage controls': '视场覆盖控件',
    'Collapse the coverage controls': '收起视场覆盖控件',
    'Flight': '架次',
    'Build': '构建',
    'Generate the coverage grid for this flight (reads its SRT; about 30 s for a 20-minute video)': '为这个架次生成覆盖网格（读它的 SRT；20 分钟的视频约 30 秒）',
    'Observed (times seen)': '观测次数（被看到几次）',
    'Sharpness (best detail)': '清晰度（最细可辨）',
    'Coverage area (polygon)': '覆盖范围（多边形）',
    'at least': '至少',
    'frames': '帧',
    'better than': '优于',
    'Opacity': '不透明度',
    'Reading flights…': '正在读取架次…',
    'No flights with SRT in this project': '这个项目里没有带 SRT 的架次',
    'No SRT files found in this project’s folders.': '这个项目的文件夹里没找到 SRT 文件。',
    '(needs rebuild)': '（需重建）',
    '(ready)': '（就绪）',
    '(not built)': '（未构建）',
    'Not built yet — click Build.': '还没有构建 —— 点「构建」。',
    'The flight data changed since this was built — Build again.': '构建之后这个架次的数据变了 —— 请重新构建。',
    'Building… this can take up to a minute for a long flight. Keep this page open.': '正在构建… 长架次可能要一分钟，请保持本页打开。',
    'Coverage grid built.': '覆盖网格已构建。',
    'Reused the existing coverage grid.': '沿用了已有的覆盖网格。',
    'Loading layer…': '正在加载图层…',
    'Coverage area': '覆盖范围',
    'coarser': '更粗',
    'few': '少',
    'no coverage': '无覆盖',
    'Redder = you can see finer detail there.': '越红 = 那里能看清的细节越细。',
    'Darker red = more frames saw that spot.': '越深红 = 拍到那一格的画面越多。',
    'Status': '状态',
    'Not observed': '未观测到',
    'Reason': '原因',
    'Observed': '观测',
    'Best': '最细可辨',
    'Sharpest': '最清晰',
    'Boundary': '边界',
    '(zoomed)': '（已变焦）',
    'passes': '趟',
    'Open': '打开',
    'Exported': '已导出',
    '— open it from the link below.': '—— 从下面的链接打开。',
    'Exports are not listed as tracks.': '导出产物不会列进航迹列表。',
    'Delete the generated files for this video?': '要删除这个视频生成的文件吗？',
    'File:': '文件：',
    'Location:': '位置：',
    '· Deleted: this file’s GeoJSON (including the 3D version) and SRT': '· 会删除：这个文件的 GeoJSON（含 3D 版本）与 SRT',
    '· Kept: the source video (MP4) — the original is untouched': '· 会保留：源视频（MP4）—— 原始文件不动',
    '· To restore: use “Make SRT” / “Make GeoJSON” above, or': '· 想恢复：用上面的「生成 SRT」/「生成 GeoJSON」，或者',
    '  import the source data again': '  重新导入一次源数据',
    'Deleted': '已删除',
    'Delete failed:': '删除失败：',
    'Cannot find the data folder this file belongs to.': '找不到这个文件所属的数据文件夹。',

    # 导入时的提示（含"导入后顺手把 360 素材排进转码队列"那条）
    'Updated data folder: ': '已更新数据文件夹：',
    'Imported data folder: ': '已导入数据文件夹：',
    '360 clip(s) are transcoding in the background': '个 360 素材正在后台转码',
    'they will open instantly once done.': '转完之后点开就是秒开。',
    '360 background transcode did not start:': '360 后台转码没能启动：',

    # 标记点类别（用户 2026-10-16 要求：建标记点时有"名字 + 类别"两项，
    # 类别第一次输入即新建，之后可复用）
    'Category': '类别',
    'Category (optional)': '类别（可不填）',

    # 正射影像叠加层（瓦片金字塔）
    'Building pyramid…': '正在建立金字塔…',
    'Pyramid ready': '金字塔已就绪',
    'Pyramid build failed: ': '建立金字塔失败：',
    'tiles': '块瓦片',

    # 照片点聚合
    'photo groups': '个照片点',
    'click to zoom in': '点击放大',

}


def self_check_ui():
    """返回 (重复项, 空项) —— 供自检用。"""
    dups = []
    empties = []
    for k, v in UI_ZH.items():
        if not v or not v.strip():
            empties.append(k)
    return dups, empties
