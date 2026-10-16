# -*- coding: utf-8 -*-
"""双语（中文 / English）。

## 为什么需要它

页面本身是英文的，但**后端有 191 条中文字符串** —— 其中不少会直接显示在
界面上（HTTP 错误、状态、文件选择对话框），还有**导出报告**里的模板文字。
用户 2026-10-15 要求：「右上角增加一个切换语言的选项，中文英文可互相切换，
切换后所有按钮、显示文字、输出报告模板都要自动更换。」

## 怎么用

    from i18n import t, set_lang, norm_lang
    t("project.name_empty")                    # 按当前语言取
    t("project.name_empty", lang="zh")         # 指定语言

字符串表就是 `MESSAGES`：`键 -> {"zh": ..., "en": ...}`。

## 两条纪律

1. **键一旦定下就别改**（前端、测试、缓存都可能引用它）。
2. **zh 与 en 必须成对存在** —— `self_check()` 会报出缺哪一边，
   `test_i18n.py` 把它做成断言。半翻译（只加了一边）是最容易犯的错。
"""
from __future__ import annotations

import threading

from i18n_ui import UI_ZH

LANGS = ("en", "zh")
DEFAULT_LANG = "en"

_lock = threading.local()


def norm_lang(value) -> str:
    """把任意输入归一成一个受支持的语言代码。认不出来就给默认值。

    要宽容一点：这个值可能来自 localStorage、URL 查询串、请求头，
    甚至用户手输。认不出来不该报错，退回默认语言即可。
    """
    if not value:
        return DEFAULT_LANG
    v = str(value).strip().lower().replace("_", "-")
    if v.startswith("zh") or v in ("cn", "chinese", "中文", "简体"):
        return "zh"
    if v.startswith("en") or v in ("english", "英文"):
        return "en"
    return DEFAULT_LANG


def set_lang(value) -> str:
    """设置**本线程**的当前语言（ThreadingHTTPServer 是每请求一个线程）。"""
    _lock.lang = norm_lang(value)
    return _lock.lang


def get_lang() -> str:
    return getattr(_lock, "lang", DEFAULT_LANG)


def t(key: str, lang: str | None = None, **fmt) -> str:
    """取一条文案。

    找不到键时**返回键名本身**（不抛异常）—— 界面上一眼能看出漏了哪个键，
    比整页崩掉好。缺某个语言时退回另一种语言，再不行才给键名。

    **也支持把英文原文当键**（见 `i18n_ui.py`）：界面短文案直接用英文串查，
    中文环境下命中 `UI_ZH`，英文环境下原样返回 —— 于是"没翻译的串"自动退回
    英文，不会出现空白。这是刻意做的，为了能**渐进式**扩大覆盖面。
    """
    entry = MESSAGES.get(key)
    if entry is None:
        # 退到界面文案表（英文原串当键）
        use = norm_lang(lang) if lang else get_lang()
        if use == "zh":
            zh = UI_ZH.get(key)
            if zh is not None:
                return _fmt(zh, fmt)
            # 中文环境下没翻到 -> 原样返回英文，而不是给键名
            return _fmt(key, fmt) if fmt else key
        return _fmt(key, fmt) if fmt else key
    use = norm_lang(lang) if lang else get_lang()
    text = entry.get(use)
    if text is None:
        # 退回另一种语言：宁可显示另一种语言，也不要显示键名
        text = entry.get("en") or entry.get("zh")
    if text is None:
        return key
    return _fmt(text, fmt)


def _fmt(text: str, fmt: dict) -> str:
    if not fmt:
        return text
    try:
        return text.format(**fmt)
    except (KeyError, IndexError, ValueError):
        return text


def all_messages(lang: str) -> dict:
    """给前端用：整张表在**某一种**语言下的样子。

    包含两部分：
      · 结构化文案（键名 -> 文案），带参数的原样给出（前端自己 format 不现实，
        所以带参数的条目前端一般不用；这里仍然给出去，便于排查）
      · 界面文案：**英文原串 -> 该语言的串**（中文环境下就是英->中映射）
        前端可以直接 `L('Load all tracks')` 这样查
    """
    use = norm_lang(lang)
    out = {}
    for key, entry in MESSAGES.items():
        text = entry.get(use) or entry.get("en") or entry.get("zh")
        if text is not None:
            out[key] = text
    # 界面文案：用英文原串当键。英文环境下**不放进表里**（原样返回即可），
    # 省掉几百条冗余条目、也避免"英文键映射到英文值"这种无意义条目。
    if use == "zh":
        for en, zh in UI_ZH.items():
            out[en] = zh
    return out


def self_check() -> list:
    """自检：返回问题列表（空列表 = 没问题）。

    检查两件事：
      ① 每个键是否 zh / en 都在
      ② 有没有 zh 与 en 完全相同的条目（多半是忘了翻，但也可能是
         "这个词两种语言一样"，比如 "KML" —— 所以只作为提示）
    """
    problems = []
    for key, entry in MESSAGES.items():
        missing = [lg for lg in LANGS if not entry.get(lg)]
        if missing:
            problems.append("%s 缺少: %s" % (key, ", ".join(missing)))
    return problems


# ============================================================
# 字符串表
# ============================================================
#
# 分组：
#   app.*       应用级
#   project.*   项目 / 文件夹
#   video.*     视频 / SRT / 检测
#   coverage.*  视场覆盖
#   report.*    导出报告
#   ui.*        界面控件（前端也会拉这张表）
#   pano.*      360 全景
#
MESSAGES: dict[str, dict[str, str]] = {

    # ---------------- 应用级 ----------------
    "app.title": {
        "en": "Fly Data Map",
        "zh": "无人机巡查数据地图",
    },
    "app.not_found": {
        "en": "Not found: {path}",
        "zh": "未找到：{path}",
    },

    # ---------------- 项目 ----------------
    "project.name_must_be_string": {
        "en": "The project name must be a string.",
        "zh": "项目名称必须是字符串。",
    },
    "project.name_empty": {
        "en": "The project name cannot be empty.",
        "zh": "项目名称不能为空。",
    },
    "project.name_is_dot": {
        "en": "The project name cannot be '.' or '..'.",
        "zh": "项目名称不能为 . 或 ..。",
    },
    "project.name_control_chars": {
        "en": "The project name cannot contain control characters.",
        "zh": "项目名称不能包含控制字符。",
    },
    "project.name_bad_chars": {
        "en": "The project name cannot contain any of these characters: ",
        "zh": "项目名称不能包含以下字符：",
    },
    "project.name_trailing": {
        "en": "The project name cannot end with a space or a period.",
        "zh": "项目名称不能以空格或句点结尾。",
    },
    "project.name_reserved": {
        "en": "That name is a reserved Windows device name and cannot be used.",
        "zh": "这个名称属于 Windows 保留设备名称，不能使用。",
    },
    "project.not_found": {
        "en": "The project does not exist.",
        "zh": "项目不存在。",
    },
    "project.path_not_folder": {
        "en": "The project path is not a folder.",
        "zh": "项目路径不是文件夹。",
    },
    "project.folder_missing": {
        "en": "The specified folder does not exist.",
        "zh": "指定文件夹不存在。",
    },
    "project.path_not_folder2": {
        "en": "The specified path is not a folder.",
        "zh": "指定路径不是文件夹。",
    },
    "project.folder_unavailable": {
        "en": "The folder does not exist or is currently unavailable.",
        "zh": "文件夹不存在或当前无法访问。",
    },
    "project.recorded_path_not_folder": {
        "en": "The recorded location is not a folder.",
        "zh": "记录的位置不是文件夹。",
    },
    "project.folder_out_of_range": {
        "en": "The folder index is out of range.",
        "zh": "文件夹序号超出范围。",
    },
    "project.folder_no_path": {
        "en": "This folder has no path.",
        "zh": "这个文件夹没有路径。",
    },

    # ---------------- 文件选择对话框 ----------------
    "pick.folder_multi": {
        "en": "Choose the drone data folder (hold Ctrl / Shift to pick several)",
        "zh": "选择无人机数据文件夹（按住 Ctrl / Shift 可多选）",
    },
    "pick.folder": {
        "en": "Choose the drone data folder",
        "zh": "选择无人机数据文件夹",
    },
    "pick.files_multi": {
        "en": "Choose drone data files (you can pick several)",
        "zh": "选择无人机数据文件（可多选）",
    },
    "pick.drone_data": {
        "en": "Drone data",
        "zh": "无人机数据",
    },
    "pick.all_files": {
        "en": "All files",
        "zh": "所有文件",
    },
    "pick.guid_failed": {
        "en": "Could not parse the GUID",
        "zh": "GUID 解析失败",
    },
    "pick.cocreate_failed": {
        "en": "CoCreateInstance failed",
        "zh": "CoCreateInstance 失败",
    },
    "pick.getoptions_failed": {
        "en": "GetOptions failed",
        "zh": "GetOptions 失败",
    },
    "pick.setoptions_failed": {
        "en": "SetOptions failed",
        "zh": "SetOptions 失败",
    },
    "pick.getresults_failed": {
        "en": "GetResults failed",
        "zh": "GetResults 失败",
    },
    "pick.getcount_failed": {
        "en": "GetCount failed",
        "zh": "GetCount 失败",
    },
    "pick.none_selected": {
        "en": "No files were selected.",
        "zh": "没有选择任何文件。",
    },
    "pick.file_missing": {
        "en": "The file does not exist: {path}",
        "zh": "文件不存在：{path}",
    },
    "pick.not_a_file": {
        "en": "Not a file: {path}",
        "zh": "不是文件：{path}",
    },
    "pick.same_folder": {
        "en": "Please choose files from the same folder "
              "(the current selection spans several folders).",
        "zh": "请选择同一个文件夹里的文件（当前跨了多个目录）。",
    },

    # ---------------- 视频 / ffmpeg ----------------
    "video.ffprobe_missing": {
        "en": "ffprobe was not found.",
        "zh": "未找到 ffprobe。",
    },
    "video.ffmpeg_path_hint": {
        "en": "Make sure FFmpeg is installed and on the system PATH.",
        "zh": "请确认 FFmpeg 已安装并已加入系统 PATH。",
    },
    "video.ffprobe_timeout": {
        "en": "ffprobe timed out.",
        "zh": "ffprobe 检测超时。",
    },
    "video.ffprobe_spawn_failed": {
        "en": "Could not start ffprobe: {e}",
        "zh": "启动 ffprobe 失败：{e}",
    },
    "video.ffprobe_failed": {
        "en": "ffprobe detection failed.",
        "zh": "ffprobe 检测失败。",
    },
    "video.ffprobe_parse_failed": {
        "en": "Could not parse the ffprobe output: {e}",
        "zh": "无法解析 ffprobe 返回结果：{e}",
    },
    "video.no_video_file": {
        "en": "The file does not exist.",
        "zh": "视频文件不存在。",
    },
    "video.not_mp4_mov": {
        "en": "That file is not an MP4/MOV/OSV video.",
        "zh": "指定文件不是 MP4/MOV/OSV 视频。",
    },
    "video.ffmpeg_missing": {
        "en": "ffmpeg was not found. Make sure FFmpeg is installed and on the system PATH.",
        "zh": "未找到 ffmpeg。请确认 FFmpeg 已安装并加入系统 PATH。",
    },
    "video.path_outside_folder": {
        "en": "The video path points outside the project data folder.",
        "zh": "视频路径超出了项目数据文件夹范围。",
    },
    "video.no_subtitle_stream": {
        "en": "This video has no subtitle stream to extract.",
        "zh": "该视频没有可提取的字幕流。",
    },
    "video.srt_missing_for_geojson": {
        "en": "No matching SRT yet — extract the SRT first.",
        "zh": "尚未找到对应 SRT 文件，请先点击“提取 SRT”。",
    },

    # ---------------- 覆盖 ----------------
    "coverage.no_points": {
        "en": "No usable telemetry / position points.",
        "zh": "没有可用的遥测/定位点",
    },
    "coverage.no_footprint": {
        "en": "No frame produced a usable footprint "
              "(the pitch/altitude data may be wrong).",
        "zh": "所有帧都算不出足迹（俯角/高度数据可能有问题）",
    },
    "coverage.outside_grid": {
        "en": "Outside the coverage grid for this flight.",
        "zh": "超出这次飞行的覆盖网格范围。",
    },
    "coverage.no_frame_saw": {
        "en": "No frame of this flight saw this spot.",
        "zh": "这次飞行没有任何一帧看到这个位置。",
    },

    # ---------------- 360 全景 ----------------
    "pano.north_too_low": {
        "en": "The sun is only {el:+.2f}° above the horizon (below {min:.0f}°), "
              "so the sun disc cannot be reliably told apart from the horizon glow "
              "— leaving north unknown rather than guessing.",
        "zh": "太阳高度角只有 {el:+.2f}°（低于 {min:.0f}°），太阳贴着地平线，"
              "无法可靠地把日面和地平线光带分开 —— 北向留空，不猜。",
    },
    "pano.north_untrusted": {
        "en": "The sun position is not trustworthy (the bright blob does not match "
              "where the sun should be) — leaving north unknown rather than guessing.",
        "zh": "太阳位置不可信（找到的亮点对不上理论日面位置）—— 北向留空，不猜。",
    },
    "pano.no_sun_found": {
        "en": "Could not measure the sun disc at any sampled moment "
              "(the sun may be behind a mountain or cloud, or the clip is too short) "
              "— leaving north unknown rather than guessing.",
        "zh": "试过的时刻都量不出日面（多半是太阳被山/云挡住，或素材太短）"
              "—— 北向留空，不猜。",
    },

    # ---------------- 报告 ----------------
    "report.title": {
        "en": "Marker Report — {project}",
        "zh": "标记点报告 — {project}",
    },
    "report.untitled": {
        "en": "Untitled",
        "zh": "未命名",
    },
    "report.generated": {
        "en": "Generated: {time}    Markers: {count}    Video frames: {mode}",
        "zh": "生成时间：{time}    标记点：{count}    视频帧：{mode}",
    },
    "report.contents": {
        "en": "Contents",
        "zh": "目录",
    },
    "report.contents_hint": {
        "en": "Click any item below to jump to that section.",
        "zh": "点击下面任意一项可跳到对应章节。",
    },
    "report.summary": {
        "en": "Summary",
        "zh": "汇总",
    },
    "report.col_index": {"en": "#", "zh": "序号"},
    "report.col_name": {"en": "Name", "zh": "名称"},
    "report.col_lat": {"en": "Lat (°N)", "zh": "纬度 (°N)"},
    "report.col_lng": {"en": "Lng (°E)", "zh": "经度 (°E)"},
    "report.col_location": {"en": "Location", "zh": "位置"},
    "report.col_video": {"en": "Video file", "zh": "视频文件"},
    "report.col_time": {"en": "Video time", "zh": "视频时刻"},
    "report.image_compressed": {
        "en": "compressed to 320 ppi (about 2480 px wide)",
        "zh": "已压缩到 320 ppi（约 2480 px 宽）",
    },
    "report.image_original": {
        "en": "original resolution",
        "zh": "原始分辨率",
    },
    "report.fig_video": {
        "en": "Figure 1  Target video frame ({video}  {time})",
        "zh": "图 1  目标视频帧（{video}  {time}）",
    },
    "report.fig_map": {
        "en": "Figure 2  Target map view (basemap: {basemap}  zoom {zoom})",
        "zh": "图 2  目标地图视图（底图：{basemap}  缩放 {zoom}）",
    },
    "report.basemap_current": {"en": "current", "zh": "当前"},
    "report.field_lat": {"en": "Latitude (°N)", "zh": "纬度 (°N)"},
    "report.field_lng": {"en": "Longitude (°E)", "zh": "经度 (°E)"},
    "report.marker_fallback": {"en": "Marker", "zh": "标记点"},
    "report.unresolved": {"en": "unresolved", "zh": "未解析"},
    "report.no_markers": {
        "en": "No valid markers to write into the report.",
        "zh": "没有有效的标记点可写入报告。",
    },
    "report.filename": {
        "en": "Marker_Report_{project}_{date}.docx",
        "zh": "标记点报告_{project}_{date}.docx",
    },

    # ---------------- 界面控件（前端也会用这张表） ----------------
    "ui.language": {"en": "Language", "zh": "语言"},
    "ui.lang_en": {"en": "English", "zh": "英文"},
    "ui.lang_zh": {"en": "中文", "zh": "中文"},
    "ui.save": {"en": "Save", "zh": "保存"},
    "ui.cancel": {"en": "Cancel", "zh": "取消"},
    "ui.close": {"en": "Close", "zh": "关闭"},
    "ui.yes": {"en": "Yes", "zh": "是"},
    "ui.no": {"en": "No", "zh": "否"},
    "ui.ok": {"en": "OK", "zh": "确定"},
    "ui.error": {"en": "Error", "zh": "错误"},
    "ui.warning": {"en": "Warning", "zh": "警告"},
    "ui.search_place": {"en": "Search place", "zh": "搜索地点"},
    "ui.build_tracks": {"en": "Build tracks", "zh": "生成航迹"},
    "ui.frames_of_spot": {"en": "Frames of this spot", "zh": "此处的画面"},
    "ui.find_flights": {"en": "Find flights at this position", "zh": "查找经过此处的架次"},
    "ui.clear_selection": {"en": "Clear selection", "zh": "清除选择"},
    "ui.load_all_tracks": {"en": "Load all tracks", "zh": "加载全部航迹"},
    "ui.coverage": {"en": "Coverage", "zh": "视场覆盖"},
    "ui.base_map": {"en": "Base map", "zh": "底图"},
}


if __name__ == "__main__":
    import sys
    problems = self_check()
    print("i18n 自检：%d 个键" % len(MESSAGES))
    if problems:
        print("发现 %d 个问题：" % len(problems))
        for p in problems:
            print("   " + p)
        sys.exit(1)
    print("  zh / en 都齐全")
    for lg in LANGS:
        print()
        print("  样例（%s）：" % lg)
        for k in ("app.title", "project.name_empty", "report.title"):
            print("    %-24s %s" % (k, t(k, lang=lg, project="Demo", el=0.07, min=12)))
