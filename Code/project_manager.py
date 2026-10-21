import json
import hashlib
import io
import math
import os
import sys
import threading
import ctypes
import tkinter as tk
import subprocess
import shutil
import re
import time
import urllib.request
import urllib.error

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tkinter import filedialog
from urllib.parse import urlparse, parse_qs, urlencode, quote as url_quote

import i18n
import settings_store


# ============================================================
# Windows 高 DPI 适配
# ============================================================

def enable_windows_dpi_awareness():

    try:
        awareness_context = ctypes.c_void_p(-4)
        user32 = ctypes.windll.user32

        user32.SetProcessDpiAwarenessContext.argtypes = [
            ctypes.c_void_p
        ]
        user32.SetProcessDpiAwarenessContext.restype = ctypes.c_bool

        user32.SetProcessDpiAwarenessContext(
            awareness_context
        )
        return

    except Exception:
        pass

    try:
        shcore = ctypes.windll.shcore
        shcore.SetProcessDpiAwareness(2)
        return

    except Exception:
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()

    except Exception:
        pass


enable_windows_dpi_awareness()


# ============================================================
# 基础目录（打包成 exe 后不能再用 __file__ 推）
# ============================================================
#
# 两种运行方式：
#   1) 源码直接跑：代码在 Code\ 下，数据放在它的上一级（仓库根目录）
#   2) 打包成 exe 后：__file__ 指向包内部（PyInstaller 单文件模式更是每次启动都变的
#      【临时目录】）—— 数据必须改用 **exe 所在目录**，否则用户导入的数据、标记点
#      会写进临时目录，一关程序就全没了。这是打包最容易翻车的一处。
FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN:
    BASE_DIR = Path(sys.executable).resolve().parent
    CODE_DIR = Path(getattr(sys, "_MEIPASS", str(BASE_DIR)))   # 只读资源（页面 / ffmpeg）
else:
    CODE_DIR = Path(__file__).resolve().parent
    BASE_DIR = CODE_DIR.parent


def _is_writable(path):
    """能不能在这里建文件？装到 Program Files 这类只读目录时要兜底。"""

    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True

    except OSError:
        return False


if _is_writable(BASE_DIR):
    DATA_DIR = BASE_DIR

else:
    # 兜底：数据落到用户目录（启动横幅里会打印实际位置）
    DATA_DIR = Path(
        os.environ.get("LOCALAPPDATA") or Path.home()
    ) / "无人机巡查数据地图"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

TEST_DIR = DATA_DIR        # 旧名字：代码里到处在用，语义就是"数据根目录"

PROJECT_DIR = TEST_DIR / "Project"

PROJECT_MANAGER_HTML = CODE_DIR / "project_manager.html"
PROJECT_IMPORT_HTML = CODE_DIR / "project_import.html"
PROJECT_MEDIA_HTML = CODE_DIR / "project_media.html"
PROJECT_VIDEO_INSPECTOR_HTML = CODE_DIR / "project_video_inspector.html"
PROJECT_GEOJSON_PREVIEW_HTML = CODE_DIR / "project_geojson_preview.html"
PROJECT_GEO3D_PREVIEW_HTML = CODE_DIR / "project_geo3d_preview.html"
# 360 全景预览器（Avata 360 的 .OSV 双鱼眼 -> 等距柱状 -> 可拖拽透视）
PANO360_VIEWER_HTML = CODE_DIR / "pano360_viewer.html"
PANO360_PLAYER_HTML = CODE_DIR / "pano360_player.html"
# 瓦片缓存放在工作区根目录（与视频转码缓存一致），不放在代码目录
MAP_TILE_CACHE_DIR = TEST_DIR / "tile_cache"
MAP_TILE_CACHE_SECONDS = 7 * 24 * 60 * 60
MAP_TILE_CACHE_MAX_MB = 2048

# 天地图瓦片图层：键 -> (WMTS 图层名, 服务名)
# 注意：影像层返回的是 JPEG，矢量/注记是 PNG，所以 Content-Type 要按真实内容判断
TIANDITU_TILE_LAYERS = {
    "tdt_vec": ("vec", "vec_w"),
    "tdt_img": ("img", "img_w"),
    "tdt_cva": ("cva", "cva_w"),
    "tdt_cia": ("cia", "cia_w"),
}
TIANDITU_TILE_SUBDOMAINS = 8

# ------------------------------------------------------------
# 天地图地名搜索（地图搜索框用）
# key 只从**环境变量 TIANDITU_KEY** 或数据目录下的 tianditu_key.txt 读取；
# 不要把 key 写进源码 —— 源码是要公开的，写进来就等于泄了。
# 申请地址：https://lbs.tianditu.gov.cn/authorization/authorization.html
# （旧的 console.tianditu.gov.cn 主机目前返回 502，别再指向它）
# ------------------------------------------------------------

TIANDITU_KEY = (os.environ.get("TIANDITU_KEY") or "").strip()
# key 文件放在数据目录（打包后就是 exe 同级，安装向导的结束页写这里）。
# 刻意**不做**"包内自带一份"的回退：那样安装目录里残留的旧文件会盖过用户填的，
# 测试也没法构造"没有 key"的场景。
TIANDITU_KEY_FILE = DATA_DIR / "tianditu_key.txt"
TIANDITU_SEARCH_URL = "https://api.tianditu.gov.cn/v2/search"
# 地名搜索的范围框（minLon,minLat,maxLon,maxLat）。用全国范围，
# 这样搜索不受当前地图视野限制。
TIANDITU_MAP_BOUND = "73,3,135,54"
GEOCODE_CACHE_DIR = DATA_DIR / "geocode_cache"      # 可写目录（打包后包内是只读的）
GEOCODE_CACHE_SECONDS = 30 * 24 * 60 * 60
GEOCODE_MEMORY = {}
GEOCODE_MEMORY_LOCK = threading.Lock()

# ------------------------------------------------------------
# 标记点报告（Word）
#
# 抽帧 / 地图截图 / docx 都落在 report_cache/（不进仓库），
# 前端通过 /report/<文件名> 取回。
# ------------------------------------------------------------

REPORT_DIR = TEST_DIR / "report_cache"

TIANDITU_GEOCODER_URL = "https://api.tianditu.gov.cn/geocoder"
REVERSE_GEOCODE_MEMORY = {}
REVERSE_GEOCODE_LOCK = threading.Lock()

# 报告里地图截图的底图：必须跟随用户当前选的那一种
MAP_SNAPSHOT_LAYERS = {
    "street": [("tdt_vec", False), ("tdt_cva", True)],
    "satellite": [("tdt_img", False), ("tdt_cia", True)],
    "osm": [("osm", False)],
}
MAP_SNAPSHOT_MAX_TILES = 80        # 一张截图最多拼多少块瓦片（防手滑传个巨大尺寸）
MAP_TILE_PIXELS = 256

# 「压缩」档：A4 正文宽约 19.7cm，按 320 ppi 折算 ≈ 2480 px 宽
REPORT_IMAGE_WIDTH_A4 = 2480

# 报告里插图的尺寸：两张图都**横向占满正文宽**（REPORT_IMAGE_MAX_WIDTH_CM = 15.9cm），
# 只有「太高」的图才按高度上限回缩（热成像 5:4 那种方图，铺满宽会有 12.7cm 高，一页塞不下）。
#
# 于是实际尺寸就是：
#   视频截图（16:9）→ 15.9cm 宽 × 8.94cm 高（撞宽度上限，铺满）
#   地图截图（2.5:1）→ 15.9cm 宽 × 6.36cm 高（铺满，且上下裁得更扁）
# 一节的预算：标题 1.0 + 字段表 3.7 + 照片 8.94 + 图注 0.7 + 地图 6.36 + 图注 0.7 ≈ 22cm，
# A4 正文高 24.7cm —— 留 2.7cm 余量。
REPORT_VIDEO_IMAGE_MAX_HEIGHT_CM = 9.5
REPORT_MAP_IMAGE_MAX_HEIGHT_CM = 6.6
REPORT_IMAGE_MAX_HEIGHT_CM = REPORT_VIDEO_IMAGE_MAX_HEIGHT_CM   # 兼容旧断言/调用

# 正文宽 = 21 - 2.5 - 2.5 = 16.0cm。表格与插图都**用同一个 15.9cm**：
#   - 都用 16.0（=正文宽）时，Word 有时会把贴死的行内图略微缩一点再居中，
#     左边缘就跟表格差出 1~2mm（用户实测过）；
#   - 15.9 留 1mm 余量，不会被缩；表格也同步用 15.9，于是两者左边缘、右边缘都严格重合。
# 关键还有一条：插图段落要**左对齐**（不是居中），居中的话 15.9 会两边各让 0.5mm。
REPORT_IMAGE_MAX_WIDTH_CM = 15.9

# 地图截图上画的飞机箭头 / 注视虚线，颜色与页面上的保持一致
DRONE_ARROW_FILL = (30, 136, 229)      # #1e88e5
LOOK_LINE_COLOR = (156, 163, 175)      # #9ca3af
#
# 尺寸：报告里的地图是 1600×640，印到 15.9cm 宽 —— 沿宽度方向约 100px/cm。
# 若照网页图标的 34px 画，缩到纸上只有 3.4mm、在 Word 里看约 9px，比网页版小得多
# （用户反馈「跟网页版不一样」）。所以按观感放大到 size=24：外接框约 39×44px
# （纸上约 3.9×4.4mm），和红十字（半径 16）尺度相当，不喧宾夺主。
DRONE_ARROW_SIZE = 24
DRONE_NOSE_PX = 24                     # 虚线起点＝机头；与箭头 size 一致
# 注：前端网页地图上的 DRONE_NOSE_PX=14 是配 34px 图标的，**不要**跟着改。

# ------------------------------------------------------------
# 本地第三方资源目录
#
# 页面原来从 unpkg CDN 取 Leaflet，断网或内网环境下整页会失效。
# 把 leaflet.js / leaflet.css 放进这个目录，页面就完全不需要外网
# （底图瓦片另有服务端代理和本地缓存）。
# 放在工作区根目录是因为它不属于代码，属于随项目部署的资源。
# ------------------------------------------------------------

VENDOR_DIR = TEST_DIR / "vendor"
VENDOR_DIR_BUNDLED = CODE_DIR / "vendor"     # 打包时随包带一份，断网也能用

VENDOR_CONTENT_TYPES = {
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
}

# ------------------------------------------------------------
# 网页播放代理
#
# 无人机原片是 4K HEVC/H.265（约 40 Mbps）：Chrome 在 Windows 上不支持
# 软件解 HEVC，Firefox 完全不支持，且原片 moov 在文件尾部不适合边下边播。
# 这里按需把“点击位置”附近一小段转成 1080p H.264 + faststart，转一次即缓存。
# 实测：90 秒片段约 19 秒转完，输出约 41 MB / 3.7 Mbps。
# ------------------------------------------------------------

PROXY_DIR = TEST_DIR / "video_proxy"
PROXY_SECONDS = 90           # 每次生成的片段长度（秒）
PROXY_BUCKET_SECONDS = 30    # 起播点对齐粒度，便于缓存命中（前端必须一致）
PROXY_HEIGHT = 1080          # 片段高度
PROXY_CRF = 25               # H.264 质量，越小越清晰、文件越大

# 「导出前后 10 秒」：以当前播放位置为中心，前 5 秒 + 后 5 秒，压成 1080p。
# 这种片段是拿来转发给别人的，但**不能为了小把画面压糊**：
# 用户 2026-10-07 先反馈「码率压得有点高，看着比较糊」，随后定档：
# 「用 18，每次导出文件控制在 10MB 左右我觉得是没问题的」。
# 实测同一段真实素材（4K 原片第 600 秒起 10 秒，缩到 1080p，
# 与 crf12/slow 的对照算 SSIM/PSNR）：
#     crf28 + 2200k：2.3 MB，SSIM 0.894，PSNR 30.5 dB  ← 最初那档，确实糊
#     crf24 + 4000k：4.3 MB，SSIM 0.939，PSNR 33.4 dB
#     crf22 + 5000k：5.8 MB，SSIM 0.953，PSNR 34.7 dB
#     crf20 + 6000k：7.3 MB，SSIM 0.960，PSNR 35.6 dB
#     crf18 + 8000k：9.8 MB，SSIM 0.970，PSNR 37.1 dB  ← 现在这档（约 10 MB）
# 注意 CRF 与限码率要配套：CRF 18 想要更高码率，若还卡在 6000k 就等于白设，
# 所以限码率同步提到 8000k。
# 想再小就把 CLIP_CRF 调到 20（约 7.3 MB）或 22（约 5.8 MB）。
CLIP_BEFORE_SECONDS = 5
CLIP_AFTER_SECONDS = 5
CLIP_HEIGHT = 1080
CLIP_CRF = 18
CLIP_MAXRATE = "8000k"
CLIP_BUFSIZE = "16000k"
CLIP_AUDIO_BITRATE = "96k"
CLIP_DIR_NAME = "video_clip"
CLIP_CACHE_MAX_MB = 2048     # 导出片段目录上限，超出后按最旧的删
PROXY_CACHE_MAX_MB = 4096    # 片段缓存上限，超出后按最旧的删除
PROXY_LOCK = threading.Lock()

# 导出片段放这里（和网页缓存的转码片段分开，免得被 prune 按缓存清掉）
CLIP_DIR = TEST_DIR / CLIP_DIR_NAME
CLIP_LOCK = threading.Lock()

# ------------------------------------------------------------
# 视频实时信息（云台朝向/俯仰、焦距、变焦、高度）
# 数据源是 SRT —— GeoJSON 里只有坐标和时间，没有姿态与焦距。
# ------------------------------------------------------------

TELEMETRY_STEP = 3           # 每 3 帧取一条（30fps -> 10Hz），显示够用且体积小
TELEMETRY_CACHE = {}
TELEMETRY_CACHE_LOCK = threading.Lock()
TELEMETRY_CACHE_MAX = 24

SRT_CUE_TIME_RE = re.compile(
    r"^(\d\d):(\d\d):(\d\d)[,.](\d\d\d)\s*-->"
)

SRT_FIELD_RES = {
    "yaw": re.compile(r"gb_yaw:\s*(-?\d+(?:\.\d+)?)"),
    "pitch": re.compile(r"gb_pitch:\s*(-?\d+(?:\.\d+)?)"),
    "focal": re.compile(r"\[focal_len:\s*(-?\d+(?:\.\d+)?)\]"),
    "dzoom": re.compile(r"\[dzoom_ratio:\s*(-?\d+(?:\.\d+)?)\]"),
    "alt": re.compile(r"\[rel_alt:\s*(-?\d+(?:\.\d+)?)"),
    # 海拔。与 alt 只差一个常数（起飞点海拔）—— 用户 2026-10-15 指出
    # 「因为是山顶起飞，起飞点高度 0m（非海拔），有些片段飞到山顶侧下方，
    # 高度为负值。这个是正常情况，换算成海拔就没问题了」。
    "alt_abs": re.compile(r"abs_alt:\s*(-?\d+(?:\.\d+)?)"),
    # `FrameCnt` = **这一路视频里该帧的帧号**（SRT 每行都带）。
    #
    # 为什么要它（用户 2026-10-15 的要求）：一次拍摄有三路视频（V 可见光 4K /
    # S 1080p / T 热成像），定位数据几乎相同（实测差 0~6 m），所以地图上只该画一条。
    # 但**帧号三路各不相同**，而且**推不出来**：
    #   · 三路帧率不同（29.78 / 29.75 / 30.00），跑 1228 秒就累积出几百帧偏差
    #   · 实测"同一时刻 T−V" 前 1/4 中位 +50、后 1/4 中位 +231（漂移 181 帧）
    #   · 三路都有丢帧（FrameCnt 不连续：V 49 处、S 10 处、T 11 处）
    # 所以必须**逐点各自记录**，否则跳到另两路视频时会定位到错的画面。
    "frame_cnt": re.compile(r"FrameCnt:\s*(\d+)"),
}


# ============================================================
# Windows 保留设备名称
# ============================================================

RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5",
    "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5",
    "LPT6", "LPT7", "LPT8", "LPT9",
    "COM¹", "COM²", "COM³",
    "LPT¹", "LPT²", "LPT³",
}


# ============================================================
# 项目名称验证
# ============================================================

def validate_project_name(name: str):

    if not isinstance(name, str):
        return "项目名称必须是字符串。"

    if not name:
        return "项目名称不能为空。"

    if name in (".", ".."):
        return "项目名称不能为 . 或 ..。"

    for char in name:
        if ord(char) <= 31:
            return "项目名称不能包含控制字符。"

    invalid_chars = '<>:"/\\|?*'

    for char in invalid_chars:
        if char in name:
            return "项目名称不能包含以下字符： " + invalid_chars

    if name[-1] in (" ", "."):
        return "项目名称不能以空格或句点结尾。"

    base_name = name.split(".")[0].upper()

    if base_name in RESERVED_NAMES:
        return "这个名称属于 Windows 保留设备名称，不能使用。"

    return None


# ============================================================
# JSON 返回
# ============================================================

def json_response(handler, data, status=200):

    body = json.dumps(
        data,
        ensure_ascii=False
    ).encode("utf-8")

    handler.send_response(status)

    handler.send_header(
        "Content-Type",
        "application/json; charset=utf-8"
    )

    handler.send_header(
        "Content-Length",
        str(len(body))
    )

    handler.end_headers()

    # 走统一出口：HEAD 请求时这里会被丢弃（只发头，不发正文）
    if hasattr(handler, "_write_body"):
        handler._write_body(body)
    else:
        handler.wfile.write(body)


# ============================================================
# 获取项目列表
# ============================================================

def get_project_directories():

    PROJECT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    projects = []

    for folder in PROJECT_DIR.iterdir():

        if not folder.is_dir():
            continue

        projects.append({
            "name": folder.name
        })

    projects.sort(
        key=lambda item: item["name"].casefold()
    )

    return projects


# ============================================================
# 读取项目
# ============================================================

def queue_pano_precache(project_name, tier="full", force=False, scan_root=None):
    """把一个项目里所有 `.OSV` 排进转码队列。返回 (queued_list, already_done_count)。

    为什么要抽成函数：**导入数据时和手动调用时都要用**。
    用户说「不怕预加载和导入的过程中生成文件」—— 导入后自动转一次，
    之后点开任何 360 素材都是秒开（否则第一次点要等几分钟）。

    `scan_root` 只扫这个目录（导入时只关心**刚加进来的那个文件夹**，
    不必把项目里其它文件夹重扫一遍）。
    """
    import pano360_transcode
    if tier not in pano360_transcode.QUALITY_TIERS:
        raise ValueError("Unknown tier: %s" % tier)

    if scan_root is not None:
        folders = [Path(scan_root).expanduser()]
    else:
        project = load_project(project_name)
        folders = [Path(item.get("path")).expanduser()
                   for item in (project.get("folders") or []) if item.get("path")]

    queued, already, seen = [], 0, set()
    for f in folders:
        if not f.is_dir():
            continue
        for src in sorted(list(f.rglob("*.OSV")) + list(f.rglob("*.osv"))):
            key = str(src.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            out = src.parent / "pano_cache" / ("%s_%s.mp4" % (src.stem, tier))
            if pano360_transcode.is_valid_output(out) and not force:
                already += 1
                continue
            queued.append({
                "job": pano360_transcode.submit(
                    src, out, tier=tier, force=force, label=src.name),
                "video": src.name,
            })
    return queued, already


def _resolve_project_media(project_name, relative_path, want_suffix=None):
    """把项目内的相对路径解析成真实文件，并**确保它确实在项目文件夹里**。

    为什么单独抽出来：360 相关的几个接口（转码 / 流式播放 / 预转）
    都要做同一件事 —— 解析 + 越界检查。重复写三遍迟早有一处漏掉检查
    （那就会变成"能用 `..` 读任意文件"的问题）。

    `want_suffix`：想要的后缀（如 `.osv`），大小写不敏感；给了就校验。
    """
    project = load_project(project_name)
    folders = [Path(item.get("path")).expanduser()
               for item in (project.get("folders") or []) if item.get("path")]
    for f in folders:
        try:
            cand = (f / relative_path).resolve()
        except (OSError, ValueError):
            continue
        if cand.is_file() and f.resolve() in cand.parents:
            if want_suffix and cand.suffix.lower() != want_suffix.lower():
                raise ValueError("Expected %s but got: %s" % (want_suffix, cand.name))
            return cand
    raise ValueError("Not found inside this project's folders: %s" % relative_path)


def load_project(project_name):

    error = validate_project_name(project_name)

    if error:
        raise ValueError(error)

    project_path = PROJECT_DIR / project_name

    if not project_path.exists():
        raise FileNotFoundError("项目不存在。")

    if not project_path.is_dir():
        raise NotADirectoryError("项目路径不是文件夹。")

    config_path = project_path / "project.json"

    if not config_path.exists():

        project = {
            "name": project_name,
            "version": 1,
            "folders": [],
            "videos": [],
            "photos": [],
            "tracks": []
        }

        save_project(project_name, project)

        return project

    with open(
        config_path,
        "r",
        encoding="utf-8"
    ) as f:

        project = json.load(f)

    project.setdefault("name", project_name)
    project.setdefault("version", 1)
    project.setdefault("folders", [])
    project.setdefault("videos", [])
    project.setdefault("photos", [])
    project.setdefault("tracks", [])

    return project


# ============================================================
# 保存项目
# ============================================================

def save_project(project_name, project):

    project_path = PROJECT_DIR / project_name

    project_path.mkdir(
        parents=True,
        exist_ok=True
    )

    config_path = project_path / "project.json"

    with open(
        config_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            project,
            f,
            ensure_ascii=False,
            indent=4
        )


# ============================================================
# 扫描文件夹
# ============================================================

def scan_folder(folder_path):

    folder = Path(
        folder_path
    ).expanduser().resolve()

    if not folder.exists():
        raise FileNotFoundError("指定文件夹不存在。")

    if not folder.is_dir():
        raise NotADirectoryError("指定路径不是文件夹。")

    files = []

    mp4_count = 0
    srt_count = 0
    jpg_count = 0
    other_count = 0

    total_size = 0

    for file_path in folder.rglob("*"):

        if not file_path.is_file():
            continue

        try:
            size = file_path.stat().st_size
        except OSError:
            size = 0

        extension = file_path.suffix.lower()

        relative_path = str(
            file_path.relative_to(folder)
        )

        file_info = {
            "name": file_path.name,
            "extension": extension,
            "size": size,
            "relative_path": relative_path
        }

        files.append(file_info)

        total_size += size

        if extension in (".mp4", ".mov"):
            mp4_count += 1

        elif extension == ".srt":
            srt_count += 1

        elif extension in (".jpg", ".jpeg"):
            jpg_count += 1

        else:
            other_count += 1

    files.sort(
        key=lambda item:
        item["relative_path"].casefold()
    )

    return {
        "name": folder.name,
        "path": str(folder),
        "file_count": len(files),
        "mp4_count": mp4_count,
        "srt_count": srt_count,
        "jpg_count": jpg_count,
        "other_count": other_count,
        "total_size": total_size,
        "files": files
    }


# ============================================================
# Windows 原生选择文件夹
# ============================================================

def clean_selected_folders(paths):
    """把用户选中的文件夹路径收拾干净：去掉空值、去重、只留真实存在的目录。"""

    result = []

    for raw in paths or []:

        try:
            path = os.path.abspath(str(raw).strip().strip('"'))

        except (TypeError, ValueError):
            continue

        if not path or not os.path.isdir(path):
            continue

        key = os.path.normcase(path)

        if key in {os.path.normcase(item) for item in result}:
            continue

        result.append(path)

    return result


def select_folders_windows():
    """选文件夹（**可多选**）。

    tkinter 的 askdirectory 只能选一个 —— 一次要导十几个架次时很难受。
    Windows 自带的现代文件对话框 IFileOpenDialog 支持
    FOS_PICKFOLDERS | FOS_ALLOWMULTISELECT，所以直接用 ctypes 调 COM；
    任何一步失败（老系统、COM 不可用……）都退回原来的单选对话框，行为不变。
    """

    try:
        chosen = _com_multi_folder_dialog()

    except Exception:
        chosen = None

    if chosen:
        return chosen

    single = select_folder_windows()

    return [single] if single else []


def _foreground_window():
    """当前前台窗口句柄（拿不到就返回 0）。"""

    try:
        return int(ctypes.windll.user32.GetForegroundWindow() or 0)

    except Exception:
        return 0


def _raise_window_when_ready(title, seconds=8.0):
    """后台线程：等这个标题的对话框出现后，把它强制提到最前。

    为什么需要：选择框是由**服务进程**弹出的，而前台是浏览器窗口。Windows 有前台锁定，
    后台进程新建的窗口会被压在别人后面（用户得点任务栏才能看到）。
    配合「把前台窗口当 owner」一起用，双保险。
    """

    def worker():
        import time

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        deadline = time.time() + seconds

        while time.time() < deadline:
            hwnd = int(user32.FindWindowW(None, title) or 0)

            if hwnd:
                try:
                    # 附加到前台线程的输入队列后再抢前台，是绕开前台锁定的标准做法
                    foreground = int(user32.GetForegroundWindow() or 0)
                    target_thread = user32.GetWindowThreadProcessId(foreground, None)
                    this_thread = kernel32.GetCurrentThreadId()

                    user32.AttachThreadInput(target_thread, this_thread, True)
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)
                    user32.AttachThreadInput(target_thread, this_thread, False)

                except Exception:
                    pass

                try:
                    user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)   # HWND_TOPMOST
                    user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002)   # HWND_NOTOPMOST

                except Exception:
                    pass

                return

            time.sleep(0.1)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    return thread


def _com_multi_folder_dialog(title="选择无人机数据文件夹（按住 Ctrl / Shift 可多选）"):
    """ctypes 调 IFileOpenDialog 多选文件夹；失败抛异常（由调用方兜底）。

    vtable 索引（IFileDialog 继承 IUnknown）：
        3 = Show、9 = SetOptions、10 = GetOptions、17 = SetTitle
        IFileOpenDialog 追加：27 = GetResults
        IShellItemArray：7 = GetCount、8 = GetItemAt
        IShellItem：5 = GetDisplayName
    """

    import ctypes
    from ctypes import wintypes

    ole32 = ctypes.WinDLL("ole32")

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    def make_guid(text):
        value = GUID()

        if ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(value)) != 0:
            raise OSError("GUID 解析失败")

        return value

    def call(pointer, index, restype, *argtypes):
        """按 vtable 下标取方法并调用（返回已绑定 pointer 的可调用对象）。"""

        vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p))[0]
        address = ctypes.cast(vtable, ctypes.POINTER(ctypes.c_void_p))[index]
        prototype = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
        method = prototype(address)

        return lambda *args: method(pointer, *args)

    ole32.CoInitialize(None)

    dialog = ctypes.c_void_p()
    ole32.CoCreateInstance(
        ctypes.byref(make_guid("{DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7}")),   # CLSID_FileOpenDialog
        None,
        1,                                                                  # CLSCTX_INPROC_SERVER
        ctypes.byref(make_guid("{d57c7288-d4ad-4768-be02-9d969532d960}")),   # IID_IFileOpenDialog
        ctypes.byref(dialog),
    )

    if not dialog:
        raise OSError("CoCreateInstance 失败")

    try:
        get_options = call(dialog, 10, ctypes.c_long, ctypes.POINTER(wintypes.DWORD))
        set_options = call(dialog, 9, ctypes.c_long, wintypes.DWORD)
        set_title = call(dialog, 17, ctypes.c_long, ctypes.c_wchar_p)
        show = call(dialog, 3, ctypes.c_long, wintypes.HWND)
        get_results = call(dialog, 27, ctypes.c_long, ctypes.POINTER(ctypes.c_void_p))

        options = wintypes.DWORD()

        if get_options(ctypes.byref(options)) != 0:
            raise OSError("GetOptions 失败")

        # FOS_PICKFOLDERS(0x20) | FOS_ALLOWMULTISELECT(0x200) | FOS_FORCEFILESYSTEM(0x40)
        if set_options(options.value | 0x20 | 0x200 | 0x40) != 0:
            raise OSError("SetOptions 失败")

        set_title(title)

        # 关键：用当前前台窗口（一般就是浏览器）当属主 —— 有属主的对话框必然浮在属主之上，
        # 否则它是个无主窗口，会被浏览器盖住（用户得去点任务栏）。
        owner = _foreground_window()
        _raise_window_when_ready(title)

        # Show 返回 0x800704C7（用户取消）时不是错误
        if show(owner) != 0:
            return []

        items = ctypes.c_void_p()

        if get_results(ctypes.byref(items)) != 0 or not items:
            raise OSError("GetResults 失败")

        try:
            get_count = call(items, 7, ctypes.c_long, ctypes.POINTER(wintypes.DWORD))
            get_item_at = call(
                items, 8, ctypes.c_long, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)
            )

            count = wintypes.DWORD()

            if get_count(ctypes.byref(count)) != 0:
                raise OSError("GetCount 失败")

            paths = []

            for index in range(count.value):
                item = ctypes.c_void_p()

                if get_item_at(index, ctypes.byref(item)) != 0 or not item:
                    continue

                try:
                    # SIGDN_FILESYSPATH = 0x80058000 -> 拿到文件系统路径
                    name = ctypes.c_wchar_p()
                    get_display_name = call(
                        item, 5, ctypes.c_long, ctypes.c_uint,
                        ctypes.POINTER(ctypes.c_wchar_p)
                    )

                    if get_display_name(0x80058000, ctypes.byref(name)) == 0 and name.value:
                        # 刻意不 CoTaskMemFree：释放的是 COM 分配的字符串指针，
                        # 万一类型对不上就是崩溃；这里每次导入只漏几十字节，不值得冒险。
                        paths.append(name.value)

                finally:
                    call(item, 2, ctypes.c_ulong)()

            return clean_selected_folders(paths)

        finally:
            call(items, 2, ctypes.c_ulong)()

    finally:
        call(dialog, 2, ctypes.c_ulong)()


def select_folder_windows():

    result = {
        "path": None
    }

    def open_dialog():

        root = tk.Tk()
        root.withdraw()

        root.attributes(
            "-topmost",
            True
        )

        try:

            selected = filedialog.askdirectory(
                title="选择无人机数据文件夹",
                mustexist=True
            )

            if selected:
                result["path"] = selected

        finally:
            root.destroy()

    thread = threading.Thread(
        target=open_dialog
    )

    thread.start()
    thread.join()

    return result["path"]


def select_files_windows():
    """多选文件（用于只导入某几个视频，而不是整个文件夹）。

    说明：Windows/tkinter 没有「文件和文件夹都能选」的对话框 ——
    askdirectory 只能选文件夹、askopenfilenames 只能选文件。
    所以界面上分成「选文件夹」「选文件」两个入口，各自调用一个函数。
    """

    result = {
        "paths": []
    }

    def open_dialog():

        root = tk.Tk()
        root.withdraw()

        root.attributes(
            "-topmost",
            True
        )

        try:

            selected = filedialog.askopenfilenames(
                title="选择无人机数据文件（可多选）",
                filetypes=[
                    (
                        "无人机数据",
                        "*.MP4 *.mp4 *.MOV *.mov *.SRT *.srt *.JPG *.jpg *.JPEG *.jpeg"
                    ),
                    (
                        "所有文件",
                        "*.*"
                    )
                ]
            )

            if selected:
                result["paths"] = list(selected)

        finally:
            root.destroy()

    thread = threading.Thread(
        target=open_dialog
    )

    thread.start()
    thread.join()

    return result["paths"]


# ============================================================
# 媒体识别
# ============================================================

def folder_from_files(file_paths):
    """把「选中的若干文件」整理成和 scan_folder 同构的 folder 对象。

    path 取这些文件的共同父目录，files 只保留选中的这些，
    计数与体积按筛选后的结果重算 —— 这样它可以直接交给 add-folder，
    和「导入整个文件夹」走完全同一套后续流程（检测 / 生成 / 加载）。

    Windows 和 tkinter 都没有「文件和文件夹都能选」的对话框，
    所以只能分成两个入口；这里负责把「文件入口」的结果补齐成同一种形状。
    """

    if not file_paths:
        raise ValueError("没有选择任何文件。")

    paths = []

    for raw in file_paths:

        path = Path(raw).expanduser().resolve()

        if not path.exists():
            raise FileNotFoundError(f"文件不存在：{path}")

        if not path.is_file():
            raise IsADirectoryError(f"不是文件：{path}")

        paths.append(path)

    parents = {str(path.parent) for path in paths}

    if len(parents) != 1:
        raise ValueError("请选择同一个文件夹里的文件（当前跨了多个目录）。")

    folder = Path(next(iter(parents)))

    scanned = scan_folder(str(folder))

    wanted = {path.name for path in paths}

    files = [
        item for item in scanned.get("files", [])
        if item.get("name") in wanted
    ]

    mp4_count = 0
    srt_count = 0
    jpg_count = 0
    other_count = 0
    total_size = 0

    for item in files:

        extension = item.get("extension", "")

        total_size += item.get("size", 0)

        if extension in (".mp4", ".mov"):
            mp4_count += 1

        elif extension == ".srt":
            srt_count += 1

        elif extension in (".jpg", ".jpeg"):
            jpg_count += 1

        else:
            other_count += 1

    return {
        "name": folder.name,
        "path": str(folder),
        "file_count": len(files),
        "mp4_count": mp4_count,
        "srt_count": srt_count,
        "jpg_count": jpg_count,
        "other_count": other_count,
        "total_size": total_size,
        "files": files,
        # 标明这不是「整个文件夹」，而是用户挑出来的几个文件
        "selected_only": True
    }


def analyze_project_media(project_name):

    project = load_project(project_name)

    folders = project.get("folders", [])

    result_folders = []

    total_video_count = 0
    total_srt_count = 0
    total_matched_count = 0

    for folder_info in folders:

        folder_path = folder_info.get("path")

        if not folder_path:
            continue

        folder = Path(folder_path)

        if not folder.exists():

            result_folders.append({
                "name": folder_info.get(
                    "name",
                    folder.name
                ),
                "path": folder_path,
                "error": "文件夹不存在或当前无法访问。",
                "videos": []
            })

            continue

        if not folder.is_dir():

            result_folders.append({
                "name": folder_info.get(
                    "name",
                    folder.name
                ),
                "path": folder_path,
                "error": "记录的位置不是文件夹。",
                "videos": []
            })

            continue

        all_files = []

        for file_path in folder.rglob("*"):

            if not file_path.is_file():
                continue

            try:
                size = file_path.stat().st_size
            except OSError:
                size = 0

            try:
                relative_path = str(
                    file_path.relative_to(folder)
                )
            except ValueError:
                relative_path = file_path.name

            all_files.append({
                "path": file_path,
                "name": file_path.name,
                "extension": file_path.suffix.lower(),
                "relative_path": relative_path,
                "size": size
            })

        srt_index = {}

        for file_info in all_files:

            if file_info["extension"] != ".srt":
                continue

            relative_parent = str(
                Path(
                    file_info["relative_path"]
                ).parent
            )

            if relative_parent == ".":
                relative_parent = ""

            stem = Path(
                file_info["name"]
            ).stem.casefold()

            key = (
                relative_parent.casefold(),
                stem
            )

            srt_index[key] = file_info
            total_srt_count += 1

        videos = []

        for file_info in all_files:

            if file_info["extension"] not in (
                ".mp4",
                ".mov"
            ):
                continue

            total_video_count += 1

            relative_parent = str(
                Path(
                    file_info["relative_path"]
                ).parent
            )

            if relative_parent == ".":
                relative_parent = ""

            stem = Path(
                file_info["name"]
            ).stem.casefold()

            key = (
                relative_parent.casefold(),
                stem
            )

            matched_srt = srt_index.get(key)

            video_result = {
                "name": file_info["name"],
                "relative_path": file_info["relative_path"],
                "size": file_info["size"],
                "extension": file_info["extension"],
                "srt": None
            }

            if matched_srt:

                total_matched_count += 1

                video_result["srt"] = {
                    "name": matched_srt["name"],
                    "relative_path":
                        matched_srt["relative_path"],
                    "size": matched_srt["size"]
                }

            videos.append(video_result)

        videos.sort(
            key=lambda item:
            item["relative_path"].casefold()
        )

        result_folders.append({
            "name": folder_info.get(
                "name",
                folder.name
            ),
            "path": str(folder),
            "error": None,
            "videos": videos
        })

    return {
        "project": project_name,
        "folder_count": len(folders),
        "video_count": total_video_count,
        "srt_count": total_srt_count,
        "matched_count": total_matched_count,
        "pending_count": max(
            0,
            total_video_count -
            total_matched_count
        ),
        "folders": result_folders
    }


# ============================================================
# FFprobe 路径
# ============================================================

def find_ffprobe():

    # 随包目录优先：打包后 ffmpeg 就在程序目录/包内，装了 exe 的机器不一定另装 ffmpeg
    for bundled in (
        DATA_DIR / "ffmpeg" / "ffprobe.exe",
        CODE_DIR / "ffmpeg" / "ffprobe.exe",
    ):

        if bundled.exists():
            return str(bundled)

    configured = shutil.which("ffprobe")

    if configured:
        return configured

    common_paths = [
        Path(
            r"C:\Program Files\ffmpeg\bin\ffprobe.exe"
        ),
        Path(
            r"C:\Program Files\FFmpeg\bin\ffprobe.exe"
        ),
        Path(
            r"C:\ffmpeg\bin\ffprobe.exe"
        ),
    ]

    for path in common_paths:

        if path.exists():
            return str(path)

    return None


def find_ffmpeg():
    """找 ffmpeg：**随包目录优先**，其次 PATH，再 ffprobe 同目录，最后常见安装路径。"""

    for bundled in (
        DATA_DIR / "ffmpeg" / "ffmpeg.exe",
        CODE_DIR / "ffmpeg" / "ffmpeg.exe",
    ):

        if bundled.exists():
            return str(bundled)

    configured = shutil.which("ffmpeg")

    if configured:
        return configured

    ffprobe = find_ffprobe()

    if ffprobe:

        candidate = Path(ffprobe).with_name(
            "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
        )

        if candidate.exists():
            return str(candidate)

    common_paths = [
        Path(
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"
        ),
        Path(
            r"C:\Program Files\FFmpeg\bin\ffmpeg.exe"
        ),
        Path(
            r"C:\ffmpeg\bin\ffmpeg.exe"
        ),
    ]

    for path in common_paths:

        if path.exists():
            return str(path)

    return None


# ============================================================
# 安全读取字符串
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    return str(value)


# ============================================================
# 单个视频结构检测
# ============================================================

def inspect_video_file(
    file_path,
    relative_path=""
):

    path = Path(file_path)

    result = {
        "name": path.name,
        "relative_path": relative_path or path.name,
        "size": 0,
        "success": False,
        "error": None,
        "format": {},
        "streams": [],
        "video_streams": [],
        "audio_streams": [],
        "subtitle_streams": [],
        "data_streams": [],
        "attachment_streams": [],
        "evidence": [],
        "dji_telemetry": False,
        "dji_telemetry_reason": [],
        "has_subtitle": False,
        "has_data_stream": False,
        "duration": None
    }

    try:
        result["size"] = path.stat().st_size
    except OSError:
        pass

    ffprobe = find_ffprobe()

    if not ffprobe:

        result["error"] = (
            "未找到 ffprobe。"
            "请确认 FFmpeg 已安装并已加入系统 PATH。"
        )

        return result

    command = [
        ffprobe,
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path)
    ]

    try:

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120
        )

    except subprocess.TimeoutExpired:

        result["error"] = (
            "ffprobe 检测超时。"
        )

        return result

    except Exception as e:

        result["error"] = (
            f"启动 ffprobe 失败：{e}"
        )

        return result

    if completed.returncode != 0:

        stderr = clean_text(
            completed.stderr
        ).strip()

        result["error"] = (
            stderr[:1000]
            if stderr
            else "ffprobe 检测失败。"
        )

        return result

    try:

        probe = json.loads(
            completed.stdout
        )

    except Exception as e:

        result["error"] = (
            f"无法解析 ffprobe 返回结果：{e}"
        )

        return result

    # --------------------------------------------------------
    # Format
    # --------------------------------------------------------

    format_info = probe.get(
        "format",
        {}
    )

    format_name = clean_text(
        format_info.get(
            "format_name"
        )
    )

    format_long_name = clean_text(
        format_info.get(
            "format_long_name"
        )
    )

    duration = format_info.get(
        "duration"
    )

    result["format"] = {
        "format_name": format_name,
        "format_long_name": format_long_name,
        "duration": duration,
        "size": format_info.get(
            "size"
        ),
        "bit_rate": format_info.get(
            "bit_rate"
        ),
        "tags": format_info.get(
            "tags",
            {}
        )
    }

    result["duration"] = duration

    # --------------------------------------------------------
    # Streams
    # --------------------------------------------------------

    streams = probe.get(
        "streams",
        []
    )

    for stream in streams:

        codec_type = clean_text(
            stream.get(
                "codec_type"
            )
        )

        codec_name = clean_text(
            stream.get(
                "codec_name"
            )
        )

        codec_long_name = clean_text(
            stream.get(
                "codec_long_name"
            )
        )

        codec_tag_string = clean_text(
            stream.get(
                "codec_tag_string"
            )
        )

        codec_tag = clean_text(
            stream.get(
                "codec_tag"
            )
        )

        tags = stream.get(
            "tags",
            {}
        ) or {}

        compact_stream = {
            "index":
                stream.get("index"),

            "codec_type":
                codec_type,

            "codec_name":
                codec_name,

            "codec_long_name":
                codec_long_name,

            "codec_tag_string":
                codec_tag_string,

            "codec_tag":
                codec_tag,

            "width":
                stream.get("width"),

            "height":
                stream.get("height"),

            "pix_fmt":
                stream.get("pix_fmt"),

            "r_frame_rate":
                stream.get(
                    "r_frame_rate"
                ),

            "sample_rate":
                stream.get(
                    "sample_rate"
                ),

            "channels":
                stream.get(
                    "channels"
                ),

            "channel_layout":
                stream.get(
                    "channel_layout"
                ),

            "tags":
                tags,

            "side_data_list":
                stream.get(
                    "side_data_list",
                    []
                )
        }

        result["streams"].append(
            compact_stream
        )

        if codec_type == "video":

            result["video_streams"].append(
                compact_stream
            )

        elif codec_type == "audio":

            result["audio_streams"].append(
                compact_stream
            )

        elif codec_type == "subtitle":

            result["subtitle_streams"].append(
                compact_stream
            )

        elif codec_type == "data":

            result["data_streams"].append(
                compact_stream
            )

        elif codec_type == "attachment":

            result["attachment_streams"].append(
                compact_stream
            )

        # ----------------------------------------------------
        # DJI 线索
        # ----------------------------------------------------

        searchable = " ".join([
            codec_type,
            codec_name,
            codec_long_name,
            codec_tag_string,
            codec_tag,
            json.dumps(
                tags,
                ensure_ascii=False
            )
        ]).lower()

        if "djmd" in searchable:

            result["evidence"].append(
                "检测到 djmd 字样"
            )

            result["dji_telemetry"] = True

            result["dji_telemetry_reason"].append(
                "djmd"
            )

        if "dbgi" in searchable:

            result["evidence"].append(
                "检测到 dbgi 字样"
            )

            result["dji_telemetry"] = True

            result["dji_telemetry_reason"].append(
                "dbgi"
            )

        if (
            codec_type == "data"
        ):

            result["has_data_stream"] = True

            result["evidence"].append(
                "存在 data 数据流"
            )

            result["dji_telemetry"] = True

            result["dji_telemetry_reason"].append(
                "data stream"
            )

        if (
            codec_type == "subtitle"
        ):

            result["has_subtitle"] = True

            result["evidence"].append(
                "存在字幕流"
            )

            # mov_text 是我们之前验证过的
            # DJI 视频常见的内嵌遥测承载方式之一。
            if codec_name == "mov_text":

                result["evidence"].append(
                    "字幕编码为 mov_text"
                )

                result["dji_telemetry"] = True

                result[
                    "dji_telemetry_reason"
                ].append(
                    "mov_text subtitle"
                )

    # --------------------------------------------------------
    # 去重
    # --------------------------------------------------------

    result["evidence"] = list(
        dict.fromkeys(
            result["evidence"]
        )
    )

    result["dji_telemetry_reason"] = list(
        dict.fromkeys(
            result["dji_telemetry_reason"]
        )
    )

    result["success"] = True

    return result


# ============================================================
# 项目视频结构检测
# ============================================================

def inspect_project_videos(
    project_name
):

    media = analyze_project_media(
        project_name
    )

    inspected_folders = []

    total_videos = 0
    inspected_videos = 0
    telemetry_videos = 0
    subtitle_videos = 0
    data_stream_videos = 0
    failed_videos = 0

    for folder in media["folders"]:

        inspected_videos_in_folder = []

        for video in folder.get(
            "videos",
            []
        ):

            total_videos += 1

            folder_path = Path(
                folder["path"]
            )

            file_path = (
                folder_path
                /
                video["relative_path"]
            )

            inspection = inspect_video_file(
                file_path,
                video["relative_path"]
            )

            inspection["folder_path"] = str(
                folder_path
            )

            if inspection["success"]:

                inspected_videos += 1

            else:

                failed_videos += 1

            if inspection[
                "dji_telemetry"
            ]:

                telemetry_videos += 1

            if inspection[
                "has_subtitle"
            ]:

                subtitle_videos += 1

            if inspection[
                "has_data_stream"
            ]:

                data_stream_videos += 1

            inspected_videos_in_folder.append(
                inspection
            )

        inspected_folders.append({

            "name":
                folder["name"],

            "path":
                folder["path"],

            "error":
                folder.get(
                    "error"
                ),

            "videos":
                inspected_videos_in_folder
        })

    return {

        "project":
            project_name,

        "folder_count":
            media["folder_count"],

        "video_count":
            total_videos,

        "inspected_count":
            inspected_videos,

        "telemetry_count":
            telemetry_videos,

        "subtitle_video_count":
            subtitle_videos,

        "data_stream_video_count":
            data_stream_videos,

        "failed_count":
            failed_videos,

        "ffprobe":
            bool(find_ffprobe()),

        "folders":
            inspected_folders
    }



# ============================================================
# 路径安全：确认目标文件夹属于当前项目
# ============================================================

def resolve_project_folder(project_name, folder_path):
    project = load_project(project_name)

    target = Path(folder_path).expanduser().resolve()

    for folder_info in project.get("folders", []):
        saved = folder_info.get("path")
        if not saved:
            continue

        try:
            candidate = Path(saved).expanduser().resolve()
        except Exception:
            continue

        if candidate == target:
            return candidate

    raise ValueError("指定的数据文件夹不属于当前项目。")


# ============================================================
# 获取视频文件的字幕流
# ============================================================

def get_subtitle_stream_index(file_path):
    inspection = inspect_video_file(file_path, file_path.name)

    if not inspection.get("success"):
        raise RuntimeError(
            inspection.get("error") or "无法读取视频结构。"
        )

    subtitle_streams = inspection.get(
        "subtitle_streams",
        []
    )

    if not subtitle_streams:
        raise ValueError("该视频没有可提取的字幕流。")

    return subtitle_streams[0].get("index")


# ============================================================
# 提取内嵌字幕为外部 SRT
# ============================================================

def extract_srt_for_video(
    project_name,
    folder_path,
    relative_path
):
    folder = resolve_project_folder(
        project_name,
        folder_path
    )

    video_path = (
        folder /
        Path(relative_path)
    ).resolve()

    try:
        video_path.relative_to(folder)
    except ValueError:
        raise ValueError("视频路径超出了项目数据文件夹范围。")

    if not video_path.exists():
        raise FileNotFoundError("视频文件不存在。")

    if video_path.suffix.lower() not in (".mp4", ".mov", ".osv"):
        raise ValueError("指定文件不是 MP4/MOV/OSV 视频。")

    ffmpeg = shutil.which("ffmpeg")

    if not ffmpeg:
        raise RuntimeError(
            "未找到 ffmpeg。请确认 FFmpeg 已安装并加入系统 PATH。"
        )

    subtitle_index = get_subtitle_stream_index(
        video_path
    )

    if subtitle_index is None:
        raise ValueError("没有找到可用的字幕流。")

    output_path = video_path.with_suffix(".srt")

    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", str(video_path),
        "-map", f"0:{subtitle_index}",
        "-c:s", "srt",
        str(output_path)
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("SRT 提取超时。")
    except Exception as e:
        raise RuntimeError(f"启动 ffmpeg 失败：{e}")

    if completed.returncode != 0:
        error_text = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or "ffmpeg 提取 SRT 失败。"
        )
        raise RuntimeError(error_text[:2000])

    if not output_path.exists():
        raise RuntimeError("ffmpeg 执行完成，但没有生成 SRT 文件。")

    size = output_path.stat().st_size

    if size == 0:
        raise RuntimeError("生成的 SRT 文件为空。")

    return {
        "video": video_path.name,
        "srt_name": output_path.name,
        "srt_relative_path": str(
            output_path.relative_to(folder)
        ),
        "size": size
    }


# ============================================================
# SRT 时间解析
# ============================================================

def parse_srt_timestamp(value):
    match = re.match(
        r"^\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})\s*$",
        value
    )

    if not match:
        return None

    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    milliseconds = int(match.group(4))

    return (
        hours * 3600
        + minutes * 60
        + seconds
        + milliseconds / 1000.0
    )


# ============================================================
# 从 SRT 文本提取经纬度
# ============================================================

def extract_lat_lon(text):
    normalized = (
        text
        .replace("：", ":")
        .replace("，", ",")
    )

    lat_patterns = [
        r"\[\s*latitude\s*:\s*([-+]?\d+(?:\.\d+)?)\s*\]",
        r"\[\s*lat\s*:\s*([-+]?\d+(?:\.\d+)?)\s*\]",
        r"\blatitude\s*[:=]\s*([-+]?\d+(?:\.\d+)?)",
        r"\blat\s*[:=]\s*([-+]?\d+(?:\.\d+)?)",
    ]

    lon_patterns = [
        r"\[\s*longitude\s*:\s*([-+]?\d+(?:\.\d+)?)\s*\]",
        r"\[\s*lon\s*:\s*([-+]?\d+(?:\.\d+)?)\s*\]",
        r"\blongitude\s*[:=]\s*([-+]?\d+(?:\.\d+)?)",
        r"\blon\s*[:=]\s*([-+]?\d+(?:\.\d+)?)",
    ]

    lat = None
    lon = None

    for pattern in lat_patterns:
        match = re.search(
            pattern,
            normalized,
            flags=re.IGNORECASE
        )
        if match:
            lat = float(match.group(1))
            break

    for pattern in lon_patterns:
        match = re.search(
            pattern,
            normalized,
            flags=re.IGNORECASE
        )
        if match:
            lon = float(match.group(1))
            break

    if lat is None or lon is None:
        return None, None

    if not (-90 <= lat <= 90):
        return None, None

    if not (-180 <= lon <= 180):
        return None, None

    return lat, lon


# ============================================================
# 从 SRT 文本提取 DJI 高度
# ============================================================

def extract_altitudes(text):

    normalized = (
        text
        .replace("：", ":")
        .replace("，", ",")
    )

    def find_value(patterns):
        for pattern in patterns:
            match = re.search(
                pattern,
                normalized,
                flags=re.IGNORECASE
            )
            if match:
                try:
                    return float(match.group(1))
                except Exception:
                    return None
        return None

    rel_patterns = [
        r"\[\s*rel_alt\s*:\s*([-+]?\d+(?:\.\d+)?)\s*\]",
        r"\[\s*relative_altitude\s*:\s*([-+]?\d+(?:\.\d+)?)\s*\]",
        r"\brel_alt\s*[:=]\s*([-+]?\d+(?:\.\d+)?)",
        r"\brelative_altitude\s*[:=]\s*([-+]?\d+(?:\.\d+)?)",
    ]

    abs_patterns = [
        r"\[\s*abs_alt\s*:\s*([-+]?\d+(?:\.\d+)?)\s*\]",
        r"\[\s*absolute_altitude\s*:\s*([-+]?\d+(?:\.\d+)?)\s*\]",
        r"\babs_alt\s*[:=]\s*([-+]?\d+(?:\.\d+)?)",
        r"\babsolute_altitude\s*[:=]\s*([-+]?\d+(?:\.\d+)?)",
    ]

    return (
        find_value(rel_patterns),
        find_value(abs_patterns)
    )


# ============================================================
# 解析 DJI SRT（含高度）
# ============================================================

def parse_dji_srt_3d(srt_path):

    text = srt_path.read_text(
        encoding="utf-8-sig",
        errors="replace"
    )

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    blocks = re.split(
        r"\n\s*\n",
        text.strip()
    )

    records = []

    for block in blocks:

        lines = [
            line.strip()
            for line in block.split("\n")
            if line.strip()
        ]

        if not lines:
            continue

        time_index = None

        for index, line in enumerate(lines):
            if "-->" in line:
                time_index = index
                break

        if time_index is None:
            continue

        time_parts = re.split(
            r"\s*-->\s*",
            lines[time_index],
            maxsplit=1
        )

        if len(time_parts) != 2:
            continue

        start_time = parse_srt_timestamp(
            time_parts[0]
        )

        end_time = parse_srt_timestamp(
            time_parts[1].split()[0]
        )

        if start_time is None:
            continue

        if end_time is None:
            end_time = start_time

        subtitle_text = "\n".join(
            lines[time_index + 1:]
        )

        lat, lon = extract_lat_lon(
            subtitle_text
        )

        if lat is None or lon is None:
            continue

        rel_alt, abs_alt = extract_altitudes(
            subtitle_text
        )

        # 三维轨迹必须有高度。
        # 优先使用相对高度；如果没有，则使用绝对高度。
        height = (
            rel_alt
            if rel_alt is not None
            else abs_alt
        )

        if height is None:
            continue

        # FrameCnt = 这一路视频里该帧的帧号。
        # 要它是因为**三路画面的帧号各不相同、而且推不出来**（帧率不同会累积漂移，
        # 还各有丢帧）—— 所以逐点原样记下来，跳视频时才定位得准。
        frame_match = re.search(r"FrameCnt:\s*(\d+)", subtitle_text)
        frame_cnt = int(frame_match.group(1)) if frame_match else None

        records.append({
            "subtitle_id":
                lines[0]
                if time_index > 0
                else str(len(records) + 1),

            "video_start":
                start_time,

            "video_end":
                end_time,

            "latitude":
                lat,

            "longitude":
                lon,

            "rel_alt":
                rel_alt,

            "abs_alt":
                abs_alt,

            "height":
                height,

            "frame_cnt":
                frame_cnt
        })

    return records


# ============================================================
# 生成独立的 3D GeoJSON
# ============================================================

def delete_geojson_for_video(
    project_name,
    folder_path,
    relative_path
):
    """删掉某一个 GeoJSON 文件（从当前项目里移除它）。

    只删这一个 .geojson：源视频、SRT 都不动。
    删掉之后文件列表里不会再出现它；想恢复的话点「生成 GeoJSON」
    重新生成一次，或者重新导入一次源数据。
    """

    folder = resolve_project_folder(
        project_name,
        folder_path
    )

    target = (
        folder /
        Path(relative_path)
    ).resolve()

    try:
        target.relative_to(folder)
    except ValueError:
        raise ValueError("路径超出了项目数据文件夹范围。")

    if target.suffix.lower() != ".geojson":
        raise ValueError("只能删除 GeoJSON 文件。")

    if not target.exists():
        raise FileNotFoundError("文件不存在，可能已经被删掉了。")

    # 只删「这一个视频对应的派生物」：GeoJSON（含 3D 版）和 SRT。
    # 视频源文件（MP4/MOV）绝不碰 —— 它是唯一的原始数据，删了就真没了。
    # 判据是「扩展名白名单」而不是「把同名的都删掉」，避免误伤。
    allowed = (".geojson", ".srt")

    stem = target.name[: -len(".geojson")]

    candidates = [
        target,                                # DJI_..._S.geojson
        folder / (stem + ".3d.geojson"),       # DJI_..._S.3d.geojson
        folder / (stem + ".srt")               # DJI_..._S.srt
    ]

    deleted = []

    for path in candidates:

        resolved = path.resolve()

        try:
            resolved.relative_to(folder)
        except ValueError:
            raise ValueError("路径超出了项目数据文件夹范围。")

        # 双保险：不在白名单里的（尤其是 .mp4/.mov）直接拒绝，绝不删除
        if resolved.suffix.lower() not in allowed:
            raise ValueError(
                "只允许删除 GeoJSON 与 SRT，视频源文件不会被删除。"
            )

        if resolved.exists():
            resolved.unlink()
            deleted.append(resolved.name)

    return {
        "deleted": deleted,
        "deleted_count": len(deleted)
    }


def flight_stem_of(name):
    """从文件名里取出"一次拍摄"的公共名（去掉 V/S/T 与扩展名）。

    `DJI_20260924095258_0001_V.MP4` -> `DJI_20260924095258_0001`

    **保留原始大小写**。踩过：一开始在这里做了 `.lower()`，结果生成的航迹叫
    `dji_...geojson`，而磁盘上是 `DJI_...` —— 在 Windows 上大小写不敏感，
    于是**又多出一个副本**而不是替换掉旧的。

    要比较两个名字是不是同一次拍摄，用 `flight_key()`（它才小写化）。
    """
    s = str(name or "").strip()
    if not s:
        return None
    s = re.sub(r"\.(mp4|mov|srt|geojson|osv)$", "", s, flags=re.I)
    s = re.sub(r"\.3d$", "", s, flags=re.I)
    m = re.match(r"^(.*)_([VST])$", s, flags=re.I)
    if not m:
        return None
    return m.group(1)


def flight_key(name):
    """用于**比较**的键：`flight_stem_of` 的小写形式（大小写不敏感）。"""
    stem = flight_stem_of(name)
    return stem.lower() if stem else None


def merge_flight_streams(srt_paths, ref_suffix="V", tol=0.2):
    """把同一拍摄的多路 SRT 合并成**一份**航迹数据。

    ## 为什么这么做（用户 2026-10-15 的要求）

    一次拍摄有三路视频（V 可见光 4K / S 1080p / T 热成像），定位数据几乎相同
    （实测按时刻对齐差 0~6 m），所以**地图上只该画一条**。但**帧号三路各不相同**、
    而且推不出来（帧率不同会累积漂移、还各有丢帧），所以把三路帧号
    **逐点存成数组**，这样跳到任一路视频时都能精确定位。

    参考路（默认 V，分辨率最高）提供坐标与时刻，其他路按**时刻就近配对**取帧号。

    返回 dict：
      ok / stream_names / reference / point_times / coords / frames /
      dropped / why
    """
    streams = {}
    for p in srt_paths:
        suf = None
        m = re.search(r"_([VST])$", Path(p).stem, flags=re.I)
        if m:
            suf = m.group(1).upper()
        elif re.search(r"_([VST])\.", str(p), flags=re.I):
            suf = re.search(r"_([VST])\.", str(p), flags=re.I).group(1).upper()
        if suf:
            streams[suf] = Path(p)

    if not streams:
        return {"ok": False, "why": "没有识别出任何一路（V/S/T）"}

    ref = ref_suffix if ref_suffix in streams else sorted(streams)[0]
    parsed = {}
    for suf, p in streams.items():
        rows = parse_dji_srt_3d(p)
        if rows:
            parsed[suf] = rows
    if ref not in parsed:
        return {"ok": False, "why": "参考路 %s 解析不出记录" % ref, "stream_names": sorted(streams)}

    ref_rows = parsed[ref]
    point_times = [float(r["video_start"]) for r in ref_rows]
    coords = [[round(float(r["longitude"]), 9), round(float(r["latitude"]), 9),
               round(float(r["height"]), 3)] for r in ref_rows]

    frames = {}
    dropped = {}
    for suf, rows in parsed.items():
        ts = [float(r["video_start"]) for r in rows]
        fs = [int(r.get("frame_cnt")) if r.get("frame_cnt") is not None else None
              for r in rows]
        f_list = []
        j = 0
        miss = 0
        for t in point_times:
            # 两指针：ts 与 point_times 都是升序
            while j + 1 < len(ts) and abs(ts[j + 1] - t) <= abs(ts[j] - t):
                j += 1
            if ts and abs(ts[j] - t) <= tol:
                f_list.append(fs[j])
            else:
                f_list.append(None)
                miss += 1
        frames[suf] = f_list
        if miss:
            dropped[suf] = miss

    return {
        "ok": True,
        "stream_names": sorted(parsed),
        "reference": ref,
        "point_times": [round(t, 3) for t in point_times],
        "coords": coords,
        "frames": frames,
        "dropped": dropped,
    }


def write_merged_track(folder, stem, merged, height_type="relative"):
    """把 `merge_flight_streams` 的结果写成**一份** geojson。

    文件名用公共名（`DJI_..._0001.geojson`），不带 _V/_S/_T —— 因为它代表
    **整次拍摄**，不是某一路。

    结构：
      properties.video       参考路（V）的视频文件名 —— 保持旧字段，兼容现有点图跳视频
      properties.videos      {路 -> 视频文件名}，三路都在
      properties.point_frames{路 -> [逐点帧号]}，三路都在
      properties.streams     路列表（用于界面显示"这一趟有几个镜头"）
    """
    import json as _json
    out_path = Path(folder) / ("%s.geojson" % stem)
    props = {
        "video": None,          # 下面按参考路填
        "videos": {},
        "srt": None,
        "record_count": len(merged["point_times"]),
        "segment_count": 1,
        "height_type": height_type,
        "video_start": merged["point_times"][0] if merged["point_times"] else 0,
        "video_end": merged["point_times"][-1] if merged["point_times"] else 0,
        "duration": (merged["point_times"][-1] - merged["point_times"][0]
                     if merged["point_times"] else 0),
        "point_times": merged["point_times"],
        "point_frames": merged["frames"],
        "streams": merged["stream_names"],
        "reference_stream": merged["reference"],
        "merged_from_streams": True,
    }
    base = Path(folder)
    for suf in merged["stream_names"]:
        for ext, key in ((".MP4", "videos"), (".mp4", "videos")):
            cand = base / ("%s_%s%s" % (stem, suf, ext))
            if cand.is_file():
                props[key][suf] = cand.name
                break
        for ext in (".srt", ".SRT"):
            cand = base / ("%s_%s%s" % (stem, suf, ext))
            if cand.is_file():
                if suf == merged["reference"]:
                    props["srt"] = cand.name
                break
    props["video"] = props["videos"].get(merged["reference"]) or next(
        iter(props["videos"].values()), None)

    feature = {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "LineString", "coordinates": merged["coords"]},
    }
    doc = {
        "type": "FeatureCollection",
        "name": stem,
        "properties": {
            "source_video": props["video"],
            "source_srt": props["srt"],
            "record_count": props["record_count"],
            "segment_count": 1,
            "height_type": height_type,
            "streams": merged["stream_names"],
            "merged_from_streams": True,
        },
        "features": [feature],
    }
    tmp = out_path.with_suffix(".geojson.tmp")
    tmp.write_text(_json.dumps(doc, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    tmp.replace(out_path)
    return out_path


def generate_merged_track(project_name, folder_path, relative_path):
    """建航迹的**主入口**：把一次拍摄的多路（V/S/T）合成一份 geojson。

    单路素材（没有兄弟 SRT）也走这里 —— 它就退化成"一路的合并"。
    """
    folder = resolve_project_folder(project_name, folder_path)
    video_path = (folder / Path(relative_path)).resolve()
    try:
        video_path.relative_to(folder)
    except ValueError:
        raise ValueError(i18n.t("video.path_outside_folder"))
    if not video_path.exists():
        raise FileNotFoundError(i18n.t("video.no_video_file"))

    stem = flight_stem_of(video_path.name)
    if stem is None:
        # 认不出 V/S/T（比如 360 的 _D），退回原来的单路生成
        return generate_geojson_for_video(project_name, folder_path, relative_path)

    # 找出同一个拍摄的所有 SRT（比较用小写键，生成文件名用原始大小写）
    want = flight_key(video_path.name)
    srt_paths = []
    for p in folder.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() == ".srt" and flight_key(p.name) == want:
            srt_paths.append(p)
    if not srt_paths:
        raise FileNotFoundError(i18n.t("video.srt_missing_for_geojson"))

    merged = merge_flight_streams(srt_paths)
    if not merged.get("ok"):
        return generate_geojson_for_video(project_name, folder_path, relative_path)

    # 清掉旧的分路 geojson（V/S/T 各一份的那些），避免列表里又冒出三条重复线
    removed = []
    for suf in ("V", "S", "T"):
        for ext in (".geojson", ".3d.geojson"):
            old = folder / ("%s_%s%s" % (stem, suf, ext))
            if old.is_file():
                try:
                    old.unlink()
                    removed.append(old.name)
                except OSError:
                    pass

    out = write_merged_track(folder, stem, merged)
    return {
        "geojson_name": out.name,
        "geojson_relative_path": out.name,
        "record_count": len(merged["point_times"]),
        "segment_count": 1,
        "size": out.stat().st_size,
        "streams": merged["stream_names"],
        "reference_stream": merged["reference"],
        "merged": True,
        "removed_old": removed,
    }


def generate_geo3d_for_video(
    project_name,
    folder_path,
    relative_path
):

    folder = resolve_project_folder(
        project_name,
        folder_path
    )

    video_path = (
        folder /
        Path(relative_path)
    ).resolve()

    try:
        video_path.relative_to(folder)
    except ValueError:
        raise ValueError("视频路径超出了项目数据文件夹范围。")

    if not video_path.exists():
        raise FileNotFoundError("视频文件不存在。")

    srt_path = video_path.with_suffix(".srt")

    if not srt_path.exists():
        raise FileNotFoundError(
            "尚未找到对应 SRT 文件，请先点击“提取 SRT”。"
        )

    records = parse_dji_srt_3d(
        srt_path
    )

    if not records:
        raise ValueError(
            "SRT 中没有解析出同时包含经纬度和高度的有效记录。"
        )

    segments = []
    current = []

    for record in records:

        if not current:
            current = [record]
            continue

        previous = current[-1]

        time_gap = (
            record["video_start"]
            -
            previous["video_end"]
        )

        if time_gap > 5:

            if len(current) >= 2:
                segments.append(current)

            current = [record]

        else:
            current.append(record)

    if len(current) >= 2:
        segments.append(current)

    if not segments and records:
        segments = [[record] for record in records]

    features = []

    for segment_index, segment in enumerate(
        segments,
        start=1
    ):

        coordinates = [
            [
                record["longitude"],
                record["latitude"],
                record["height"]
            ]
            for record in segment
        ]

        geometry = {
            "type": "LineString",
            "coordinates": coordinates
        }

        features.append({
            "type": "Feature",
            "properties": {
                "video": video_path.name,
                "srt": srt_path.name,
                "segment_index": segment_index,
                "point_count": len(segment),
                "video_start": segment[0]["video_start"],
                "video_end": segment[-1]["video_end"],
                "duration": max(
                    0,
                    segment[-1]["video_end"]
                    -
                    segment[0]["video_start"]
                ),
                "height_type": (
                    "relative"
                    if segment[0]["rel_alt"] is not None
                    else "absolute"
                ),
                "min_height": min(
                    r["height"] for r in segment
                ),
                "max_height": max(
                    r["height"] for r in segment
                ),
                "point_times": [
                    r["video_start"]
                    for r in segment
                ]
                # 注意：这里曾经还有一个 "point_heights" 数组，取值同样是
                # r["height"]，和上面 coordinates 的第三个分量完全重复。
                # 实测每个文件里这段占 652 KB（13.5%），已删除。
                # 需要逐点高度时直接读坐标第三维即可。
            },
            "geometry": geometry
        })

    geojson = {
        "type": "FeatureCollection",
        "name": video_path.stem + "_3D",
        "properties": {
            "source_video": video_path.name,
            "source_srt": srt_path.name,
            "record_count": len(records),
            "segment_count": len(features),
            "height_type": (
                "relative"
                if records[0]["rel_alt"] is not None
                else "absolute"
            )
        },
        "features": features
    }

    output_path = (
        video_path.parent
        /
        f"{video_path.stem}.3d.geojson"
    )

    output_path.write_text(
        json.dumps(
            geojson,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    return {
        "video": video_path.name,
        "geo3d_name": output_path.name,
        "geo3d_relative_path": str(
            output_path.relative_to(folder)
        ),
        "record_count": len(records),
        "segment_count": len(features),
        "size": output_path.stat().st_size,
        "height_type": geojson["properties"]["height_type"]
    }


# ============================================================
# 解析 DJI SRT
# ============================================================

def parse_dji_srt(srt_path):
    text = srt_path.read_text(
        encoding="utf-8-sig",
        errors="replace"
    )

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    blocks = re.split(
        r"\n\s*\n",
        text.strip()
    )

    records = []

    for block in blocks:
        lines = [
            line.strip()
            for line in block.split("\n")
            if line.strip()
        ]

        if not lines:
            continue

        time_index = None

        for index, line in enumerate(lines):
            if "-->" in line:
                time_index = index
                break

        if time_index is None:
            continue

        time_line = lines[time_index]

        time_parts = re.split(
            r"\s*-->\s*",
            time_line,
            maxsplit=1
        )

        if len(time_parts) != 2:
            continue

        start_time = parse_srt_timestamp(
            time_parts[0]
        )

        end_time = parse_srt_timestamp(
            time_parts[1].split()[0]
        )

        if start_time is None:
            continue

        if end_time is None:
            end_time = start_time

        subtitle_text = "\n".join(
            lines[time_index + 1:]
        )

        lat, lon = extract_lat_lon(
            subtitle_text
        )

        if lat is None or lon is None:
            continue

        records.append({
            "subtitle_id":
                lines[0]
                if time_index > 0
                else str(len(records) + 1),

            "video_start":
                start_time,

            "video_end":
                end_time,

            "latitude":
                lat,

            "longitude":
                lon,

            "text":
                subtitle_text
        })

    return records


# ============================================================
# 生成 GeoJSON
# ============================================================

def generate_geojson_for_video(
    project_name,
    folder_path,
    relative_path
):
    """兼容入口：按"一路视频"生成航迹（旧接口，保留给单路素材与外部调用）。

    多路（V/S/T）的合并走 `generate_merged_track`，它在建航迹那一步被调用。
    """
    folder = resolve_project_folder(
        project_name,
        folder_path
    )

    video_path = (
        folder /
        Path(relative_path)
    ).resolve()

    try:
        video_path.relative_to(folder)
    except ValueError:
        raise ValueError("视频路径超出了项目数据文件夹范围。")

    if not video_path.exists():
        raise FileNotFoundError("视频文件不存在。")

    srt_path = video_path.with_suffix(".srt")

    if not srt_path.exists():
        raise FileNotFoundError(
            "尚未找到对应 SRT 文件，请先点击“提取 SRT”。"
        )

    records = parse_dji_srt(
        srt_path
    )

    if not records:
        raise ValueError(
            "SRT 中没有解析出有效的经纬度记录。"
        )

    # --------------------------------------------------------
    # 连续轨迹分段
    # --------------------------------------------------------

    segments = []

    current = []

    for record in records:

        if not current:
            current = [record]
            continue

        previous = current[-1]

        time_gap = (
            record["video_start"]
            -
            previous["video_end"]
        )

        # 正常连续记录允许较小时间间隔。
        # 如果出现明显时间跳跃，则开始新轨迹段。
        if time_gap > 5:
            if len(current) >= 2:
                segments.append(current)

            current = [record]

        else:
            current.append(record)

    if len(current) >= 2:
        segments.append(current)

    # 如果只有一个有效点，则保留为 Point，
    # 避免因为数据量太少导致结果完全为空。
    if not segments and records:
        segments = [[record] for record in records]

    features = []

    for segment_index, segment in enumerate(
        segments,
        start=1
    ):

        coordinates = [
            [
                record["longitude"],
                record["latitude"]
            ]
            for record in segment
        ]

        if len(coordinates) >= 2:

            geometry = {
                "type": "LineString",
                "coordinates": coordinates
            }

        else:

            geometry = {
                "type": "Point",
                "coordinates": coordinates[0]
            }

        features.append({

            "type": "Feature",

            "properties": {

                "video":
                    video_path.name,

                "srt":
                    srt_path.name,

                "segment_index":
                    segment_index,

                "point_count":
                    len(segment),

                "video_start":
                    segment[0]["video_start"],

                "video_end":
                    segment[-1]["video_end"],

                # 每个点对应的视频时间（秒）。2D 页面靠它做「按此位置搜索飞行视频」，
                # 也靠它把播放位置映射到航迹点；漏写这个字段的轨迹搜不到、箭头也发不出来。
                # 3D 生成器一直有这一段，这里是补回 2D 路径漏掉的部分。
                "point_times": [
                    record["video_start"]
                    for record in segment
                ],

                "duration":
                    max(
                        0,
                        segment[-1]["video_end"]
                        -
                        segment[0]["video_start"]
                    )
            },

            "geometry":
                geometry
        })

    geojson = {

        "type":
            "FeatureCollection",

        "name":
            video_path.stem,

        "properties": {

            "source_video":
                video_path.name,

            "source_srt":
                srt_path.name,

            "record_count":
                len(records),

            "segment_count":
                len(features)
        },

        "features":
            features
    }

    output_path = (
        video_path.parent
        /
        f"{video_path.stem}.geojson"
    )

    output_path.write_text(
        json.dumps(
            geojson,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    return {

        "video":
            video_path.name,

        "srt_name":
            srt_path.name,

        "geojson_name":
            output_path.name,

        "geojson_relative_path":
            str(
                output_path.relative_to(
                    folder
                )
            ),

        "record_count":
            len(records),

        "segment_count":
            len(features),

        "size":
            output_path.stat().st_size
    }

# ============================================================
# GeoJSON 预览：扫描当前项目中的 GeoJSON
# ============================================================

def is_coverage_export(data):
    """这份 GeoJSON 是不是「覆盖图层导出的产物」？

    为什么要认得它（用户 2026-10-13）：
        「这几个 coverage 的矢量图层没有存在的必要了，至少图上不要加载出来，
        也不要在搜索结果里面显示出来。我查看信息直接看热力图了，看它干嘛」
        —— 这些文件是 `Coverage -> Export` 写出来的，落在数据文件夹里，
        于是被当成"航迹"出现在左栏列表、还能被加载到地图上、被检索扫到。
        它们是**导出产物**，不是飞行数据，不该混进航迹列表。

    判据（实测两份真实文件确认）：
        覆盖导出：顶层 properties 有 `stats`（+ `meta`），每个 feature 有 `metric`
        真航迹  ：顶层 properties 有 `record_count`/`segment_count`，
                  每个 feature 有 `point_times`，几何是 LineString

    用属性判而不是用文件名：文件名是 `{npz.stem}_{metric}{threshold}.geojson`，
    而 npz stem 里带一段 sha1，形态不稳定（见过的就有
    `DJI_coverage_count1` / `DJI_resolvable_20cm`）。属性是稳定的。
    """
    if not isinstance(data, dict):
        return False
    props = data.get("properties") or {}
    if isinstance(props, dict) and "stats" in props:
        return True
    features = data.get("features") or []
    for f in features[:3]:
        fp = (f or {}).get("properties") or {}
        if isinstance(fp, dict) and "metric" in fp and "point_times" not in fp:
            return True
    return False


def list_project_geojson(project_name):

    project = load_project(project_name)

    result = []

    folders = project.get("folders", [])

    for folder_index, folder_info in enumerate(folders):

        folder_path = folder_info.get("path")

        if not folder_path:
            continue

        folder = Path(folder_path).expanduser().resolve()

        if not folder.exists() or not folder.is_dir():
            continue

        for file_path in folder.rglob("*.geojson"):

            if not file_path.is_file():
                continue

            try:
                relative_path = str(file_path.relative_to(folder))
                size = file_path.stat().st_size
            except OSError:
                continue

            record_count = None
            segment_count = None

            try:
                data = json.loads(
                    file_path.read_text(
                        encoding="utf-8"
                    )
                )

                # 覆盖导出产物不算航迹：不进列表，也就不会被加载到地图、
                # 不会被检索扫到（用户 2026-10-13 的要求）。
                if is_coverage_export(data):
                    print(
                        f"[geojson-list] skip coverage export: {relative_path}",
                        file=sys.stderr,
                    )
                    continue

                properties = data.get("properties", {})

                record_count = properties.get("record_count")
                segment_count = properties.get("segment_count")

            except Exception:
                pass

            result.append({
                "folder_index": folder_index,
                "folder_name": folder.name,
                "file_name": file_path.name,
                "relative_path": relative_path,
                "size": size,
                "record_count": record_count,
                "segment_count": segment_count
            })

    result.sort(
        key=lambda item: (
            item["folder_name"].casefold(),
            item["relative_path"].casefold()
        )
    )

    return {
        "project": project_name,
        "count": len(result),
        "files": result
    }


# ============================================================
# 视频 / 航迹 同步自检
# ============================================================

# 时长对不上的容忍度（秒）。
#
# 为什么不能是 0：SRT 的最后一个 cue 与视频最后一帧本来就不完全重合，
# 实测 360 素材两者差 0.03 s / 0.31 s。而"裁掉一段"至少也是零点几秒起步，
# 所以 2 s 既能滤掉正常抖动，又能抓住任何有实际影响的不同步。
SYNC_TOLERANCE_SECONDS = 2.0

# 能重新抽取内嵌 SRT 的容器。DJI 把遥测放在字幕流里，所以裁过之后
# 从**新视频**重新抽一次 SRT，就能得到与它自洽的时间轴。
SYNC_VIDEO_SUFFIXES = (".mp4", ".mov", ".osv")


def _track_duration_of_geojson(path):
    """从一个航迹 geojson 里读出它覆盖的视频时长与它声称对应的视频名。

    航迹有两种写法（都在这份数据里见过）：
      · 单 feature + properties.point_times 数组（预览页用的那种）
      · 多 feature，每个 properties 里带自己的时长
    两种都要认，否则会漏判。
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None, None
    if not isinstance(data, dict):
        return None, None, None

    props = data.get("properties") or {}
    video_name = props.get("video") or None
    feats = data.get("features") or []

    # ① 单 feature 带 point_times / duration
    raw = props.get("point_times")
    dur = props.get("duration")
    if not isinstance(raw, (int, float)) or not raw:
        # point_times 是权威的：它的跨度就是这条航迹覆盖的视频时间范围
        pt = None
        for f in feats:
            fp = (f or {}).get("properties") or {}
            cand = fp.get("point_times")
            if isinstance(cand, list) and cand:
                pt = cand
                video_name = video_name or fp.get("video")
                break
        if pt:
            try:
                lo, hi = float(min(pt)), float(max(pt))
                dur = hi - lo
                # video_end 更准（cue 的结束时刻），有就用它
                for f in feats:
                    fp = (f or {}).get("properties") or {}
                    if fp.get("point_times") is pt:
                        if isinstance(fp.get("video_end"), (int, float)):
                            dur = float(fp["video_end"]) - lo
                        if isinstance(fp.get("video_start"), (int, float)):
                            dur = float(fp["video_end"] or hi) - float(fp["video_start"])
                        break
            except (TypeError, ValueError):
                dur = None
        elif isinstance(dur, (int, float)):
            dur = float(dur)

    # ② 多 feature：取所有 feature 时长的和（分段航迹）
    if not isinstance(dur, (int, float)) or not dur:
        total = 0.0
        seen = False
        for f in feats:
            fp = (f or {}).get("properties") or {}
            d = fp.get("duration")
            if isinstance(d, (int, float)) and d:
                total += float(d)
                seen = True
                video_name = video_name or fp.get("video")
        dur = total if seen else None

    if not isinstance(dur, (int, float)) or dur <= 0:
        return None, None, video_name

    return float(dur), path, video_name


def _srt_duration(srt_path):
    """SRT 覆盖的时间跨度（秒）。读不出来返回 None。"""
    try:
        recs = parse_dji_srt(srt_path)
    except Exception:
        return None
    if not recs:
        return None
    lo = min(r["video_start"] for r in recs if r.get("video_start") is not None)
    hi = max((r.get("video_end") or r.get("video_start"))
             for r in recs if r.get("video_start") is not None)
    if hi is None or lo is None or hi <= lo:
        return None
    return float(hi - lo)


def check_project_sync(project_name,
                       tolerance=SYNC_TOLERANCE_SECONDS):
    """检查项目里每个视频的**实际时长**与航迹/SRT 记录的时长是否对得上。

    ## 为什么需要它

    用户可能在程序之外裁过视频（去头去尾，或者**中间信号卡顿的一段**）。
    这个程序整条链路都假设 **SRT 时刻 == 视频时刻，1:1** ——
    `point_times` 直接就是 SRT 的 cue 时刻（见 `parse_dji_srt`）。
    一旦视频被裁，覆盖检索会**抽错帧**、点图跳转会**跳到错的时刻**、
    地图上的无人机标记会**沿航迹偏几十秒**（实测偏 116~1336 m）。

    ## 为什么不做"平移时间戳"

    因为破坏**不一定是均匀的**：中间丢一段的话，前面偏 N 秒、后面偏 M 秒，
    任何单一偏移量都修不好。所以这里只**报告**，让用户重新生成 ——
    重新从**新视频**里抽 SRT 才能得到自洽的时间轴。
    （用户 2026-10-14 明确要求：不要平移。）

    返回 {"checked", "problems": [...], "ok": bool}
    """
    project = load_project(project_name)
    folders = project.get("folders") or []
    problems = []
    checked = 0

    # 先把每个文件夹里的视频、航迹、SRT 都列出来
    for folder_index, folder_info in enumerate(folders):
        folder_path = folder_info.get("path")
        if not folder_path:
            continue
        folder = Path(folder_path).expanduser()
        if not folder.exists() or not folder.is_dir():
            continue

        videos = {}
        for vp in folder.rglob("*"):
            if not vp.is_file():
                continue
            if vp.suffix.lower() not in SYNC_VIDEO_SUFFIXES:
                continue
            videos[vp.stem.lower()] = vp

        tracks = {}
        # 航迹可能有两种命名：**合并后**的公共名（`DJI_..._0001.geojson`，
        # 一次拍摄一份）与旧的**分路**名（`DJI_..._0001_V.geojson`）。
        # 两个键都登记，否则按视频名（带 _V）去找会找不到合并文件，
        # 静默退回用 SRT 当参照 —— 那就查不出航迹本身的问题了。
        for gp in folder.rglob("*.geojson"):
            if not gp.is_file():
                continue
            try:
                data = json.loads(gp.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if is_coverage_export(data):
                continue        # 覆盖导出产物不是航迹
            tracks[gp.stem.lower()] = gp
            fk = flight_key(gp.name)
            if fk:
                tracks.setdefault(fk, gp)

        srts = {}
        for sp in folder.rglob("*.srt"):
            if sp.is_file():
                srts[sp.stem.lower()] = sp
        # 360 素材的 SRT 是大写 .SRT
        for sp in folder.rglob("*.SRT"):
            if sp.is_file():
                srts.setdefault(sp.stem.lower(), sp)

        for stem, video in sorted(videos.items()):
            info = probe_video_stream(video)
            vdur = (info or {}).get("duration") or 0.0
            if not vdur:
                continue        # 探不出时长就不下结论
            checked += 1

            # 参照物：优先航迹，没有航迹就用 SRT
            ref_kind = None
            ref_dur = None
            ref_path = None
            gp = tracks.get(stem)
            if gp is None:
                # 视频名带 _V/_S/_T，而合并航迹去掉了后缀 —— 用"拍摄键"再找一遍
                gp = tracks.get(flight_key(video.name) or "")
            if gp is not None:
                d, p, _vn = _track_duration_of_geojson(gp)
                if d:
                    ref_kind, ref_dur, ref_path = "track", d, gp
            if ref_dur is None:
                sp = srts.get(stem)
                if sp is not None:
                    d = _srt_duration(sp)
                    if d:
                        ref_kind, ref_dur, ref_path = "srt", d, sp
            if ref_dur is None:
                problems.append({
                    "folder_index": folder_index,
                    "folder_name": folder.name,
                    "video": video.name,
                    "relative_path": str(video.relative_to(folder)),
                    "kind": "no_reference",
                    "video_duration": round(vdur, 2),
                    "reference_duration": None,
                    "delta": None,
                    "severity": "info",
                    "message": (
                        "这条视频既没有航迹也没有可用的 SRT，"
                        "无法核对时间轴。请先生成 SRT 与航迹。"),
                })
                continue

            delta = ref_dur - vdur
            if abs(delta) > float(tolerance):
                problems.append({
                    "folder_index": folder_index,
                    "folder_name": folder.name,
                    "video": video.name,
                    "relative_path": str(video.relative_to(folder)),
                    "kind": ("track_shorter" if delta < 0 else "track_longer"),
                    "reference": ref_kind,
                    "reference_name": (ref_path.name if ref_path else None),
                    "video_duration": round(vdur, 2),
                    "reference_duration": round(ref_dur, 2),
                    "delta": round(delta, 2),
                    "severity": "error",
                    "message": (
                        "视频时长 %.1f s，但 %s 记录的时长是 %.1f s（差 %+.1f s）。"
                        % (vdur,
                           "航迹" if ref_kind == "track" else "SRT",
                           ref_dur, delta)),
                })

    return {
        "project": project_name,
        "tolerance": float(tolerance),
        "checked": checked,
        "ok": not any(p.get("severity") == "error" for p in problems),
        "problems": problems,
    }


def resync_existing_files(project_name, folder_index, relative_path):
    """对一条视频**就地重新生成** SRT 与航迹（覆盖旧的）。

    这是"校验发现不同步"之后的修复动作。为什么必须重生成而不是平移：
    裁切可能发生在**中间**（信号卡顿），那样时间轴被非均匀破坏，
    任何单一偏移都修不好。从**新视频**里重新抽 SRT 才能自洽。
    """
    project = load_project(project_name)
    folders = project.get("folders") or []
    if not (0 <= folder_index < len(folders)):
        raise ValueError("文件夹序号超出范围。")
    folder_path = folders[folder_index].get("path")
    if not folder_path:
        raise ValueError("这个文件夹没有路径。")

    result = {}
    # ① 重新抽 SRT（DJI 把遥测放在视频的**字幕流**里）。
    #
    # **抽不出来就不要往下走。** 踩过：第一版在抽取失败时仍然用**旧 SRT**
    # 重建了航迹 —— 结果 `record_count` 一个都没变、时长还是 1228.66 s、
    # 自检依然报错。用户看到"track rebuilt"却什么都没修好，比不修更糟。
    try:
        srt_info = extract_srt_for_video(project_name, folder_path, relative_path)
        result["srt"] = srt_info
    except Exception as e:
        result["srt_error"] = str(e)
        result["ok"] = False
        # 这一步失败时给一句**能照着做**的话。实测最常见的原因是：
        # 视频被重新编码过，内嵌字幕流丢了（ffmpeg -c copy 裁剪就是这样）。
        # 这种情况下程序**无法**自动恢复同步 —— 因为"正确的时刻"只存在于
        # 那个被裁掉的原始视频里，而这个程序看不到它。
        result["advice"] = (
            "无法从这条视频里重新提取遥测（DJI 把它放在字幕流里，"
            "视频被重新编码/裁剪后这一步会失败）。程序没法自动算出正确的时刻 ——"
            "正确的时刻只存在于被裁之前的原始视频里。请用**导出该视频的原始 App**"
            "（或重新导出一次，勾选保留字幕）拿到与裁剪后视频匹配的 SRT，"
            "放进同一个文件夹，再点一次「Build tracks」。")
        return result

    # ② 用新 SRT 重建航迹
    try:
        geo_info = generate_geojson_for_video(project_name, folder_path, relative_path)
        result["geojson"] = geo_info
    except Exception as e:
        result["geojson_error"] = str(e)
        result["ok"] = False
        return result

    # ③ 复查：新 SRT 的跨度必须和视频对得上，否则这一步白做了
    try:
        folder = Path(folder_path).expanduser()
        video = (folder / relative_path).resolve()
        vdur = (probe_video_stream(video) or {}).get("duration") or 0.0
        sdur = _srt_duration(video.with_suffix(".SRT")) or _srt_duration(video.with_suffix(".srt"))
        result["new_video_duration"] = round(vdur, 2) if vdur else None
        result["new_srt_duration"] = round(sdur, 2) if sdur else None
        if vdur and sdur and abs(sdur - vdur) > SYNC_TOLERANCE_SECONDS:
            result["ok"] = False
            result["advice"] = (
                "重新提取出来的 SRT 与视频**仍然**对不上"
                "（视频 %.1f s，SRT %.1f s）。说明这条视频里的字幕流本身"
                "就不是与它匹配的那一份。请从原始素材重新导出。" % (vdur, sdur))
    except Exception as e:
        result["verify_error"] = str(e)

    # ④ 清掉按旧时间轴生成的缓存，避免"错的图一直命中"。
    #    覆盖网格靠 SRT 的 mtime 判过期，SRT 刚重写过所以会自动重建；
    #    但缩略图的缓存 key 里**没有**文件指纹，必须显式清。
    cleaned = {"thumbs": 0, "coverage": 0}
    try:
        folder = Path(folder_path).expanduser()
        video = (folder / relative_path).resolve()
        tdir = video.parent / ".thumbs"
        if tdir.is_dir():
            for f in tdir.glob("t_*.jpg"):
                try:
                    f.unlink()
                    cleaned["thumbs"] += 1
                except OSError:
                    pass
        stem = video.stem
        cdir = Path(__file__).resolve().parent.parent / "Project" / project_name / "coverage"
        if cdir.is_dir():
            for f in cdir.glob(stem + ".*"):
                try:
                    f.unlink()
                    cleaned["coverage"] += 1
                except OSError:
                    pass
    except Exception as e:
        result["cleanup_error"] = str(e)
    result["cleaned"] = cleaned
    result.setdefault("ok", True)

    return result


# ============================================================
# GeoJSON 预览：读取指定 GeoJSON
# ============================================================

def load_project_geojson(
    project_name,
    folder_index,
    relative_path
):

    project = load_project(project_name)

    folders = project.get("folders", [])

    try:
        folder_index = int(folder_index)
    except Exception:
        raise ValueError("无效的数据文件夹编号。")

    if folder_index < 0 or folder_index >= len(folders):
        raise ValueError("数据文件夹不存在。")

    folder_info = folders[folder_index]

    folder_path = folder_info.get("path")

    if not folder_path:
        raise ValueError("数据文件夹路径为空。")

    folder = Path(folder_path).expanduser().resolve()

    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError("数据文件夹不存在或无法访问。")

    geojson_path = (
        folder / Path(relative_path)
    ).resolve()

    try:
        geojson_path.relative_to(folder)
    except ValueError:
        raise ValueError("GeoJSON 路径超出了数据文件夹范围。")

    if geojson_path.suffix.lower() != ".geojson":
        raise ValueError("指定文件不是 GeoJSON。")

    if not geojson_path.exists() or not geojson_path.is_file():
        raise FileNotFoundError("GeoJSON 文件不存在。")

    try:
        data = json.loads(
            geojson_path.read_text(
                encoding="utf-8"
            )
        )
    except Exception as e:
        raise ValueError(
            f"GeoJSON 读取失败：{e}"
        )

    return data


# ============================================================
# 视频流输出（支持 HTTP Range，供浏览器视频播放器拖动/定位）
# ============================================================

def resolve_project_file(project_name, folder_index, relative_path):
    """把 项目 + 数据文件夹索引 + 相对路径 解析成真实存在的文件（不限类型）。"""

    project = load_project(project_name)

    try:
        index = int(folder_index)
    except Exception:
        raise ValueError("数据文件夹索引无效。")

    folders = project.get("folders", [])

    if index < 0 or index >= len(folders):
        raise ValueError("数据文件夹不存在。")

    folder_info = folders[index]
    saved_folder = folder_info.get("path")

    if not saved_folder:
        raise ValueError("项目数据文件夹路径为空。")

    folder = Path(saved_folder).expanduser().resolve()
    file_path = (folder / Path(relative_path)).resolve()

    try:
        file_path.relative_to(folder)
    except ValueError:
        raise ValueError("路径超出了项目数据文件夹范围。")

    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError("文件不存在。")

    return file_path


def sibling_thermal_video(video_path):
    """找同目录同名的红外录像。

    DJI 四摄会同时录可见光和红外：DJI_xxx_0001_V.MP4 对应 DJI_xxx_0001_T.MP4。
    只对 _V/_S 这类可见光文件找；红外文件自己不找。
    """

    match = re.match(
        r"^(?P<base>.+)_(?P<lens>V|S|W|Z)(?P<ext>\.[^.]+)$",
        video_path.name,
        re.IGNORECASE
    )

    if not match:
        return None

    base = match.group("base")

    try:
        candidates = sorted(video_path.parent.glob(f"{base}_T.*"))
    except OSError:
        return None

    for candidate in candidates:

        if (
            candidate.is_file()
            and candidate.suffix.lower() in (".mp4", ".mov")
        ):
            return candidate

    return None


def sibling_relative_path(relative_path, suffix):
    """把可见光视频的相对路径换成红外那份（只改文件名部分）。"""

    return re.sub(
        r"_(V|S|W|Z)(\.[^.\\/]+)$",
        "_T" + suffix,
        relative_path,
        flags=re.IGNORECASE
    )


def resolve_project_video(project_name, folder_index, relative_path):
    """解析成真实存在的 MP4/MOV 视频文件。"""

    video_path = resolve_project_file(
        project_name,
        folder_index,
        relative_path
    )

    if video_path.suffix.lower() not in (".mp4", ".mov", ".osv"):
        raise ValueError("指定文件不是 MP4/MOV/OSV 视频。")

    return video_path


def send_file_range(
    handler,
    file_path,
    content_type="video/mp4",
    cache_control="no-cache"
):
    """按 HTTP Range 发送文件，支持开放式与后缀 Range。"""

    file_size = file_path.stat().st_size

    range_header = handler.headers.get("Range")

    if not range_header:
        start = 0
        end = file_size - 1
        status = 200
    else:
        try:
            units, ranges = range_header.strip().split("=", 1)
            if units.lower() != "bytes":
                raise ValueError

            range_part = ranges.split(",", 1)[0].strip()

            if range_part.startswith("-"):
                length = int(range_part[1:])
                if length <= 0:
                    raise ValueError
                start = max(0, file_size - length)
                end = file_size - 1
            else:
                parts = range_part.split("-", 1)
                start = int(parts[0])
                end = int(parts[1]) if parts[1] else file_size - 1

            if start < 0 or start >= file_size or end < start:
                raise ValueError

            end = min(end, file_size - 1)
            status = 206

        except Exception:
            handler.send_response(416)
            handler.send_header("Content-Range", f"bytes */{file_size}")
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return

    length = end - start + 1

    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Length", str(length))
    handler.send_header("Cache-Control", cache_control)

    if status == 206:
        handler.send_header(
            "Content-Range",
            f"bytes {start}-{end}/{file_size}"
        )

    handler.end_headers()

    with open(file_path, "rb") as video_file:
        video_file.seek(start)
        remaining = length

        while remaining > 0:
            chunk = video_file.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            handler._write_body(chunk) if hasattr(handler, "_write_body") else handler.wfile.write(chunk)
            remaining -= len(chunk)


def stream_project_video(handler, project_name, folder_index, relative_path):
    """原片直出。仅用于浏览器本来就能播的文件。"""

    video_path = resolve_project_video(
        project_name,
        folder_index,
        relative_path
    )

    content_type = (
        "video/quicktime"
        if video_path.suffix.lower() == ".mov"
        else "video/mp4"
    )

    send_file_range(handler, video_path, content_type)


# ============================================================
# 网页播放代理：按需把 4K HEVC 片段转成 H.264
# ============================================================

VIDEO_PROBE_CACHE = {}


def probe_video_stream(video_path):
    """探测视频编码与时长，按 文件+大小+修改时间 缓存。失败返回 None。"""

    try:
        stat = video_path.stat()
        key = (str(video_path), stat.st_size, int(stat.st_mtime))

    except OSError:
        return None

    if key in VIDEO_PROBE_CACHE:
        return VIDEO_PROBE_CACHE[key]

    ffprobe = find_ffprobe()

    if not ffprobe:
        VIDEO_PROBE_CACHE[key] = None
        return None

    command = [
        ffprobe,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height",
        "-show_entries", "format=duration",
        "-of", "json",
        str(video_path),
    ]

    info = None

    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )

        data = json.loads(
            completed.stdout.decode("utf-8", errors="replace") or "{}"
        )

        streams = data.get("streams") or []
        stream = streams[0] if streams else {}

        try:
            duration = float(
                (data.get("format") or {}).get("duration") or 0
            )
        except (TypeError, ValueError):
            duration = 0.0

        info = {
            "codec": str(stream.get("codec_name") or "").lower(),
            "width": stream.get("width"),
            "height": stream.get("height"),
            "duration": duration,
        }

    except Exception:
        info = None

    VIDEO_PROBE_CACHE[key] = info

    return info


def load_srt_telemetry(srt_path):
    """从 SRT 字幕抽逐帧的云台朝向/俯仰、焦距、变焦倍率、相对高度。

    按 TELEMETRY_STEP 抽稀（30fps -> 10Hz）：实时显示够用，
    返回体积也从 ~1.5MB 压到几百 KB。
    """

    try:
        stat = srt_path.stat()
        key = (str(srt_path), stat.st_size, int(stat.st_mtime))

    except OSError:
        raise FileNotFoundError("无法读取 SRT 文件。")

    with TELEMETRY_CACHE_LOCK:
        cached = TELEMETRY_CACHE.get(key)

    if cached is not None:
        return cached

    data = {
        "step": TELEMETRY_STEP,
        "count": 0,
        "times": [],
        "yaw": [],
        "pitch": [],
        "focal": [],
        "dzoom": [],
        # `alt` = **相对起飞点**的高度（SRT 的 `[rel_alt:]`）。
        # 覆盖几何用它当"离地高度"—— 这在平坦地形上没问题，但在**山顶起飞、
        # 飞到侧下方**时会偏：rel_alt 为负只说明飞机在起飞点之下，不代表离地高度为负。
        # 要正确处理得有 DEM（地形高程），见 docs/视场覆盖*.md 的遗留一节。
        "alt": [],
        # `alt_abs` = **海拔**（SRT 的 `abs_alt`）。
        # 与 alt 只差一个常数（起飞点海拔，实测偏移标准差 0.000）。
        # 它的用处：把高度讲清楚（"换算成海拔就没问题了"），
        # 以及将来接 DEM 时作为基准。
        "alt_abs": [],
        # 这一路视频里该帧的帧号。
        # **必须在这里占位**：`SRT_FIELD_RES` 增加了 "frame_cnt"，
        # 而解析循环是 `for name, pattern in SRT_FIELD_RES.items():
        # data[name].append(...)` —— 少一个键就 KeyError。
        # （踩过：加了正则忘了加字典项，11 套测试连锁失败。）
        "frame_cnt": [],
    }

    cue_time = None
    index = 0

    try:

        with srt_path.open(
            "r",
            encoding="utf-8",
            errors="replace"
        ) as handle:

            for line in handle:

                match = SRT_CUE_TIME_RE.match(line)

                if match:

                    cue_time = (
                        int(match.group(1)) * 3600
                        + int(match.group(2)) * 60
                        + int(match.group(3))
                        + int(match.group(4)) / 1000.0
                    )
                    continue

                if "latitude" not in line:
                    continue

                if index % TELEMETRY_STEP == 0 and cue_time is not None:

                    data["times"].append(round(cue_time, 3))

                    for name, pattern in SRT_FIELD_RES.items():

                        found = pattern.search(line)

                        data[name].append(
                            float(found.group(1)) if found else None
                        )

                index += 1

    except OSError:
        raise FileNotFoundError("读取 SRT 文件失败。")

    if not data["times"]:
        raise ValueError("SRT 里没有解析出可用记录。")

    data["count"] = len(data["times"])

    # 起飞点海拔 = abs_alt − rel_alt（常数）。实测 12 段素材的偏移标准差都是
    # **0.000**，所以取中位数即可，完全稳。
    #
    # 有了它，界面上就能把"高度"讲清楚：rel 为负只是**基准**在起飞点，
    # 换成海拔是正常的（用户 2026-10-15 明确指出的一点）。
    try:
        offs = [a - r for a, r in zip(data["alt_abs"], data["alt"])
                if a is not None and r is not None]
        if offs:
            offs.sort()
            data["takeoff_elev"] = round(offs[len(offs) // 2], 1)
    except Exception:
        pass

    with TELEMETRY_CACHE_LOCK:

        if len(TELEMETRY_CACHE) >= TELEMETRY_CACHE_MAX:
            TELEMETRY_CACHE.clear()

        TELEMETRY_CACHE[key] = data

    return data


def prune_proxy_cache():
    """片段缓存超过上限时，按最旧的先删，避免无限占盘。"""

    try:
        files = [
            item for item in PROXY_DIR.glob("*.mp4")
            if item.is_file()
        ]

    except OSError:
        return

    total = sum(item.stat().st_size for item in files)
    limit = PROXY_CACHE_MAX_MB * 1024 * 1024

    if total <= limit:
        return

    files.sort(key=lambda item: item.stat().st_mtime)

    for item in files:

        if total <= limit:
            break

        try:
            size = item.stat().st_size
            item.unlink()
            total -= size

        except OSError:
            continue


def build_proxy_segment(video_path, start_seconds, seconds):
    """把 [start, start+seconds] 转成浏览器能直接播的 H.264 片段。

    返回 (片段路径, 片段真实起始时间)。
    起播点按 PROXY_BUCKET_SECONDS 对齐以便缓存命中，
    前端用同样的对齐算法换算 currentTime。
    """

    ffmpeg = find_ffmpeg()

    if not ffmpeg:
        raise ValueError(
            "未找到 ffmpeg，无法生成网页播放片段。"
            " 请安装 ffmpeg 并确保 ffmpeg 在 PATH 中，然后重启服务。"
        )

    try:
        stat = video_path.stat()
        stamp = f"{video_path}|{stat.st_size}|{int(stat.st_mtime)}"

    except OSError:
        raise ValueError("无法读取视频文件信息。")

    bucket = (
        int(max(0.0, start_seconds) // PROXY_BUCKET_SECONDS)
        * PROXY_BUCKET_SECONDS
    )

    digest = hashlib.sha1(
        f"{stamp}|{bucket}|{seconds}|{PROXY_HEIGHT}|{PROXY_CRF}".encode("utf-8")
    ).hexdigest()[:20]

    output_path = PROXY_DIR / f"{digest}.mp4"

    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path, bucket

    with PROXY_LOCK:

        # 等锁期间可能已经被另一个请求转好了
        if output_path.exists() and output_path.stat().st_size > 0:
            return output_path, bucket

        PROXY_DIR.mkdir(parents=True, exist_ok=True)

        temp_path = output_path.with_name(
            output_path.stem + ".part.mp4"
        )

        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-ss", str(bucket),
            "-i", str(video_path),
            "-t", str(seconds),
            "-map", "0:v:0",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", str(PROXY_CRF),
            "-vf", f"scale=-2:{PROXY_HEIGHT}",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "96k",
            "-movflags", "+faststart",
            "-y", str(temp_path),
        ]

        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=1800,
            )

        except subprocess.TimeoutExpired:
            raise ValueError("转码超时。可减小 PROXY_SECONDS 或 PROXY_HEIGHT。")

        except OSError as e:
            raise ValueError(f"无法启动 ffmpeg：{e}")

        if (
            completed.returncode != 0
            or not temp_path.exists()
            or temp_path.stat().st_size == 0
        ):
            try:
                temp_path.unlink()
            except OSError:
                pass

            detail = (completed.stderr or b"").decode(
                "utf-8",
                errors="replace"
            ).strip()[:300]

            raise ValueError(f"Transcode failed: {detail or 'unknown error'}")

        temp_path.replace(output_path)

    prune_proxy_cache()

    return output_path, bucket


# ============================================================
# 导出「前后 10 秒」片段（给用户转发用）
# ============================================================

def build_clip(video_path, center_seconds):
    """以 center_seconds 为中心，切「前 5 秒 + 后 5 秒」并压成 1080p。

    返回 (片段路径, 实际起点秒, 实际时长秒)。

    和 build_proxy_segment 的区别：
      · 起点**不对齐**到 PROXY_BUCKET_SECONDS —— 用户要的就是「当前这一下」前后各 5 秒；
      · 码率压得更狠（CRF 28 + maxrate 2200k），因为这种片段是转发给别人的，
        文件越小越好；10 秒大约 2~3 MB；
      · 结果也缓存（同一视频同一秒重复点不会重转），但放在单独的 CLIP_DIR，
        不会被网页播放缓存的 prune_proxy_cache 清掉。
    """

    ffmpeg = find_ffmpeg()

    if not ffmpeg:
        raise ValueError(
            "未找到 ffmpeg，无法导出片段。"
            " 请安装 ffmpeg 并确保 ffmpeg 在 PATH 中，然后重启服务。"
        )

    try:
        stat = video_path.stat()
        stamp = f"{video_path}|{stat.st_size}|{int(stat.st_mtime)}"

    except OSError:
        raise ValueError("无法读取视频文件信息。")

    info = probe_video_stream(video_path)
    duration = float((info or {}).get("duration") or 0.0)

    # 起点：想往前 5 秒，但不能小于 0；同时保证「后 5 秒」还在文件里
    start = max(0.0, float(center_seconds) - CLIP_BEFORE_SECONDS)

    if duration:
        start = min(start, max(0.0, duration - 0.5))

    seconds = float(CLIP_BEFORE_SECONDS + CLIP_AFTER_SECONDS)

    if duration:
        seconds = max(1.0, min(seconds, max(1.0, duration - start)))

    digest = hashlib.sha1(
        f"{stamp}|{round(start, 2)}|{round(seconds, 2)}|{CLIP_HEIGHT}|{CLIP_CRF}"
        f"|{CLIP_MAXRATE}|{CLIP_BUFSIZE}".encode("utf-8")
    ).hexdigest()[:20]

    output_path = CLIP_DIR / f"{digest}.mp4"

    with CLIP_LOCK:

        if output_path.exists() and output_path.stat().st_size > 0:
            return output_path, start, seconds

        CLIP_DIR.mkdir(parents=True, exist_ok=True)

        temp_path = output_path.with_name(output_path.stem + ".part.mp4")

        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            # -ss 放在 -i 前面：关键帧定位、快（不需要解码前面那一大段）。
            # 导出片段差个零点几秒无所谓，换来的是几秒钟就能出结果。
            "-ss", f"{start:.3f}",
            "-i", str(video_path),
            "-t", f"{seconds:.3f}",
            "-map", "0:v:0",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", str(CLIP_CRF),
            "-maxrate", CLIP_MAXRATE,
            "-bufsize", CLIP_BUFSIZE,
            "-vf", f"scale=-2:{CLIP_HEIGHT}",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", CLIP_AUDIO_BITRATE,
            "-movflags", "+faststart",
            "-y", str(temp_path),
        ]

        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=600,
            )

        except subprocess.TimeoutExpired:
            raise ValueError("导出超时（ffmpeg 超过 10 分钟没完成）。")

        except OSError as e:
            raise ValueError(f"无法启动 ffmpeg：{e}")

        if (
            completed.returncode != 0
            or not temp_path.exists()
            or temp_path.stat().st_size == 0
        ):
            try:
                temp_path.unlink()
            except OSError:
                pass

            detail = (completed.stderr or b"").decode(
                "utf-8",
                errors="replace"
            ).strip()[:300]

            raise ValueError(f"Export failed: {detail or 'unknown error'}")

        temp_path.replace(output_path)

    prune_clip_cache()

    return output_path, start, seconds


def prune_clip_cache():
    """导出片段目录别无限长：超过 CLIP_CACHE_MAX_MB 就按最旧的删。

    导出的片段是给用户下载的，删了也不影响他用（他自己那份已经存下来了），
    所以要清就清，不会像网页缓存那样有「删了就得重转」的代价。
    """

    try:
        files = [
            p for p in CLIP_DIR.glob("*.mp4")
            if p.is_file()
        ]

    except OSError:
        return

    total = 0
    entries = []

    for path in files:
        try:
            stat = path.stat()

        except OSError:
            continue

        total += stat.st_size
        entries.append((stat.st_mtime, stat.st_size, path))

    limit = CLIP_CACHE_MAX_MB * 1024 * 1024

    if total <= limit:
        return

    entries.sort()  # 最旧的在前

    for _mtime, size, path in entries:
        if total <= limit:
            break

        try:
            path.unlink()
            total -= size

        except OSError:
            continue


def send_clip_download(handler, file_path, download_name):
    """把导出的片段当**下载**发出去（浏览器直接存文件，不在页面里播）。"""

    file_size = file_path.stat().st_size

    # 文件名里可能有中文/空格，按 RFC 5987 同时给 filename 与 filename*
    quoted = url_quote(download_name)

    handler.send_response(200)
    handler.send_header("Content-Type", "video/mp4")
    handler.send_header("Content-Length", str(file_size))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header(
        "Content-Disposition",
        f"attachment; filename=\"{quoted}\"; filename*=UTF-8''{quoted}"
    )
    handler.end_headers()

    with open(file_path, "rb") as clip_file:
        remaining = file_size

        while remaining > 0:
            chunk = clip_file.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            handler._write_body(chunk) if hasattr(handler, "_write_body") else handler.wfile.write(chunk)
            remaining -= len(chunk)


# ============================================================
# 地图瓦片代理
# ============================================================

# ============================================================
# 天地图地名搜索
# ============================================================

def get_tianditu_key():
    """按优先级取天地图 tk：环境变量 > 同目录 tianditu_key.txt > 源码常量。

    读文件的方式改完 key 只需刷新网页，不用重启服务。
    文件里以 # 开头的行会被忽略。
    """

    env_key = (os.environ.get("TIANDITU_KEY") or "").strip()

    if env_key:
        return env_key

    try:

        # utf-8-sig：记事本「UTF-8」另存会加 BOM，strip() 去不掉 \ufeff，
        # 带进 tk 就会被天地图判为无效（SRT 读取也是这么处理的）
        with TIANDITU_KEY_FILE.open("r", encoding="utf-8-sig") as f:

            for line in f:

                line = line.strip()

                if not line or line.startswith("#"):
                    continue

                return line

    except OSError:
        pass

    return TIANDITU_KEY


def save_tianditu_key(raw_key, clear=False):
    """把网页上补填的天地图 key 写进数据目录的 tianditu_key.txt。

    返回给前端的只有状态与掩码，**不回显完整 key**。
    key 是每次请求现读文件的，所以写完立刻生效（不用重启服务，也不用重装程序）。
    """

    key = str(raw_key or "").strip()

    if clear or not key:
        try:
            if TIANDITU_KEY_FILE.is_file():
                TIANDITU_KEY_FILE.unlink()

        except OSError as e:
            raise ValueError(f"删不掉 {TIANDITU_KEY_FILE.name}：{e}")

        return {
            "success": True,
            "cleared": True,
            "active": bool(get_tianditu_key()),
            "note": "（环境变量 TIANDITU_KEY 仍在生效）" if (os.environ.get("TIANDITU_KEY") or "").strip() else "",
        }

    if not re.fullmatch(r"[0-9A-Za-z]{32}", key):
        raise ValueError("天地图 key 是 32 位数字/字母，请检查是否复制完整、前后有没有多空格。")

    TIANDITU_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)

    TIANDITU_KEY_FILE.write_text(
        "# 天地图 key（tk）—— 由网页上的「天地图key」按钮写入，可以随时覆盖\n"
        "# 以 # 开头的行会被忽略；第一行非注释内容就是生效的 key\n"
        f"{key}\n",
        encoding="utf-8",
    )

    return {
        "success": True,
        "cleared": False,
        "active": bool(get_tianditu_key()),
        "masked": key[:4] + "…" + key[-4:],
        "source": str(TIANDITU_KEY_FILE),
        "envOverride": bool((os.environ.get("TIANDITU_KEY") or "").strip()),
    }


def enable_dpi_awareness():
    """声明本进程 DPI 感知。

    否则 125%/150% 缩放的高分屏上，Windows 会把 tkinter 对话框（选文件夹、选文件）
    整体位图拉伸，字发虚。必须在创建任何窗口之前调用；失败也不影响功能。
    """

    import ctypes

    for label, call in (
        ("PerMonitorV2", lambda: ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))),
        ("PerMonitor", lambda: ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0),
        ("System", lambda: ctypes.windll.user32.SetProcessDPIAware()),
    ):
        try:
            if call():
                return label

        except Exception:
            continue

    return ""


def migrate_legacy_key_file():
    """把老位置的天地图 key 搬到数据目录（只搬一次）。

    历史：早期版本把 key 放在**代码目录**（`Code/tianditu_key.txt`）；为了打包，
    key 改由数据目录（安装目录/exe 同级）承载。如果只改读取位置而不搬文件，
    升级后就会出现「刷新一下 key 像是丢了」——本函数就是补这一步。
    """

    legacy = CODE_DIR / "tianditu_key.txt"

    if FROZEN or not legacy.is_file() or TIANDITU_KEY_FILE.exists():
        return False

    try:
        # 目标父目录可能还不存在（copyfile 不会建目录）
        TIANDITU_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(legacy, TIANDITU_KEY_FILE)
        return True

    except OSError:
        return False


def parse_lonlat(value):
    """天地图不同版本用逗号或空格分隔经纬度，这里统一解析。"""

    if not value:
        return None, None

    parts = re.split(r"[,\s]+", str(value).strip())

    if len(parts) < 2:
        return None, None

    try:
        return float(parts[0]), float(parts[1])

    except ValueError:
        return None, None


def shorter_keyword(keyword):
    """完整地址常常查不到，退一步只查最具体的那一段。

    例：“肇庆市端州区南岸街道” -> “南岸街道”
    """

    candidates = []

    for separator in ("市", "区", "县", "镇", "乡", "街道"):

        index = keyword.rfind(separator)

        if index < 0:
            continue

        tail = keyword[index + len(separator):].strip()

        if tail and tail != keyword:
            candidates.append(tail)

    if not candidates:
        return None

    return min(candidates, key=len)


def request_tianditu_search(keyword, tianditu_key):
    """调一次天地图地名搜索，返回原始 payload。"""

    post_str = json.dumps(
        {
            "keyWord": keyword,
            "level": 12,
            "mapBound": TIANDITU_MAP_BOUND,
            "queryType": 1,
            "start": 0,
            "count": 10,
        },
        ensure_ascii=False
    )

    url = (
        TIANDITU_SEARCH_URL
        + "?"
        + urlencode(
            {
                "postStr": post_str,
                "type": "query",
                "tk": tianditu_key,
            }
        )
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent":
                "LianheZhihui-UAV-Inspection-Map/1.0",
        }
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=15
        ) as response:

            raw = response.read().decode(
                "utf-8",
                errors="replace"
            )

    except urllib.error.HTTPError as e:

        detail = ""

        try:
            body = json.loads(
                e.read().decode("utf-8", errors="replace")
            )
            detail = body.get("msg") or body.get("resolve") or ""

        except Exception:
            detail = ""

        if e.code == 429:
            raise ValueError(
                f"天地图返回限流，请稍后再试。{detail}".strip()
            )

        raise ValueError(
            f"天地图服务返回错误：HTTP {e.code}。{detail}".strip()
        )

    except urllib.error.URLError as e:

        raise ValueError(f"无法连接天地图服务：{e.reason}。")

    try:
        return json.loads(raw)

    except ValueError:

        raise ValueError("天地图返回的内容无法解析为 JSON。")


def parse_tianditu_payload(payload, keyword):
    """从天地图返回里取候选点。

    两种结果形态都要处理：
      - POI 检索     -> pois[]（名称/地址/经纬度）
      - 行政区、地名 -> area（只有行政区名和中心点，没有 pois）
    """

    status = payload.get("status")

    if isinstance(status, dict):
        # v2 用 infocode；有些返回/变体用 code
        infocode = status.get("infocode")
        if infocode is None:
            infocode = status.get("code")
        cndesc = (
            status.get("cndesc") or status.get("msg") or ""
        ).strip()
    else:
        infocode = payload.get("ret_code")
        cndesc = (
            payload.get("remark") or payload.get("msg") or ""
        ).strip()

    if infocode is None:
        infocode = payload.get("code")

    results = []

    for poi in (payload.get("pois") or [])[:10]:

        if not isinstance(poi, dict):
            continue

        lon, lat = parse_lonlat(poi.get("lonlat"))

        if lon is None or lat is None:
            continue

        results.append(
            {
                "name": (poi.get("name") or "").strip(),
                "address": (poi.get("address") or "").strip(),
                "lon": lon,
                "lat": lat,
                "kind": "poi",
            }
        )

    area = payload.get("area")

    if not results and isinstance(area, dict):

        lon, lat = parse_lonlat(area.get("lonlat"))

        if lon is not None and lat is not None:

            results.append(
                {
                    "name": (area.get("name") or keyword).strip(),
                    "address": "行政区/地名中心点",
                    "lon": lon,
                    "lat": lat,
                    "kind": "area",
                }
            )

    if not results and infocode not in (0, "0", 1000, "1000", None):

        raise ValueError(
            f"天地图地名搜索失败：{cndesc or infocode}"
        )

    return results


def geocode_place(keyword):

    keyword = (keyword or "").strip()

    if not keyword:
        raise ValueError("请输入要搜索的地名。")

    if len(keyword) > 60:
        raise ValueError("地名关键词过长。")

    tianditu_key = get_tianditu_key()

    if not tianditu_key:
        raise ValueError(
            "No Tianditu key configured, so place search is unavailable."
            f" Paste the tk from the Tianditu console into {TIANDITU_KEY_FILE.name}"
            " (that file sits next to project_manager.py; save it and refresh the page — no restart needed)."
        )

    # 一级缓存：内存

    with GEOCODE_MEMORY_LOCK:
        cached = GEOCODE_MEMORY.get(keyword)

    if cached is not None:
        return cached

    # 二级缓存：磁盘（缓存不可写时不影响功能）

    cache_path = (
        GEOCODE_CACHE_DIR
        / (hashlib.md5(keyword.encode("utf-8")).hexdigest() + ".json")
    )

    try:

        if (
            cache_path.exists()
            and (time.time() - cache_path.stat().st_mtime)
            < GEOCODE_CACHE_SECONDS
        ):

            with cache_path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            with GEOCODE_MEMORY_LOCK:
                GEOCODE_MEMORY[keyword] = data

            return data

    except (OSError, ValueError):
        pass

    payload = request_tianditu_search(keyword, tianditu_key)
    results = parse_tianditu_payload(payload, keyword)
    resolved_keyword = keyword

    # 完整地址（如“肇庆市端州区南岸街道”）天地图常常查不到，
    # 退一步只查最具体的那一段再试一次。
    if not results:

        shortened = shorter_keyword(keyword)

        if shortened:

            payload = request_tianditu_search(shortened, tianditu_key)
            results = parse_tianditu_payload(payload, shortened)

            if results:
                resolved_keyword = shortened

    data = {
        "keyword": keyword,
        "resolved_keyword": resolved_keyword,
        "count": len(results),
        "results": results,
    }

    # 只缓存成功结果；缓存不可写时不影响功能

    try:

        GEOCODE_CACHE_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        with cache_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    except OSError:
        pass

    with GEOCODE_MEMORY_LOCK:
        GEOCODE_MEMORY[keyword] = data

    return data


def guess_image_type(data):
    """按文件头判断图片格式——瓦片缓存里可能存的是 PNG，也可能是 JPEG。"""

    if data[:4] == b"\x89PNG":
        return "image/png"

    if data[:2] == b"\xff\xd8":
        return "image/jpeg"

    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"

    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"

    return None


def tile_source_url(source, z, x, y):
    """拼出上游瓦片地址。"""

    if source == "osm":
        return f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"

    layer = TIANDITU_TILE_LAYERS.get(source)

    if not layer:
        raise ValueError(f"未知的底图来源：{source}")

    layer_name, service = layer
    key = get_tianditu_key()

    if not key:
        raise ValueError(
            "尚未配置天地图 key，无法加载天地图底图。"
            f" 请把 tk 填到 {TIANDITU_KEY_FILE.name}，或改用 OpenStreetMap 底图。"
        )

    # 天地图用 t0~t7 分片，按瓦片坐标散开
    host = f"t{(x + y) % TIANDITU_TILE_SUBDOMAINS}.tianditu.gov.cn"

    return (
        f"https://{host}/{service}/wmts"
        f"?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
        f"&LAYER={layer_name}&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles"
        f"&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk={key}"
    )


def prune_tile_cache():
    """瓦片缓存超过上限时，按最旧的先删。"""

    try:
        files = [
            item for item in MAP_TILE_CACHE_DIR.rglob("*.tile")
            if item.is_file()
        ]

    except OSError:
        return

    total = sum(item.stat().st_size for item in files)
    limit = MAP_TILE_CACHE_MAX_MB * 1024 * 1024

    if total <= limit:
        return

    files.sort(key=lambda item: item.stat().st_mtime)

    for item in files:

        if total <= limit:
            break

        try:
            size = item.stat().st_size
            item.unlink()
            total -= size

        except OSError:
            continue


def proxy_map_tile(handler, source, z, x, y):
    """代理地图瓦片（天地图 / OSM）并在本地缓存。

    天地图的 key 是「服务器端」类型，浏览器直接请求会被拒（错误码 301013），
    所以底图必须由服务端代取；顺带也把 key 留在服务端，不暴露到页面里。
    """

    try:
        z = int(z)
        x = int(x)
        y = int(y)
    except Exception:
        raise ValueError("地图瓦片坐标无效。")

    if z < 0 or z > 22:
        raise ValueError("地图缩放级别无效。")

    max_index = (1 << z) - 1

    if x < 0 or x > max_index or y < 0 or y > max_index:
        raise ValueError("地图瓦片坐标超出范围。")

    # 仅缓存用户当前实际查看到的瓦片，不做预下载。
    cache_path = (
        MAP_TILE_CACHE_DIR
        / source
        / str(z)
        / str(x)
        / f"{y}.tile"
    )

    now = time.time()

    if cache_path.exists():
        try:
            if now - cache_path.stat().st_mtime < MAP_TILE_CACHE_SECONDS:
                data = cache_path.read_bytes()
                handler.send_response(200)
                handler.send_header(
                    "Content-Type",
                    guess_image_type(data) or "image/png"
                )
                handler.send_header("Cache-Control", "public, max-age=604800")
                handler.send_header("Content-Length", str(len(data)))
                handler.end_headers()
                handler._write_body(data) if hasattr(handler, "_write_body") else handler.wfile.write(data)
                return
        except OSError:
            pass

    url = tile_source_url(source, z, x, y)

    request = urllib.request.Request(
        url,
        headers={
            # 天地图的服务器端 key 会拒绝浏览器 UA，这里必须用非浏览器 UA
            "User-Agent":
                "LianheZhihui-UAV-Inspection-Map/1.0",
        }
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=20
        ) as response:
            data = response.read()

    except urllib.error.HTTPError as e:

        detail = ""

        try:
            parsed = json.loads(
                e.read().decode("utf-8", errors="replace")
            )
            detail = parsed.get("resolve") or parsed.get("msg") or ""

        except Exception:
            detail = ""

        raise RuntimeError(
            f"底图服务返回 HTTP {e.code}。{detail}".strip()
        )

    except Exception as e:
        raise RuntimeError(f"底图瓦片获取失败：{e}")

    content_type = guess_image_type(data)

    # 上游没返回图片（多半是错误说明），不要缓存，把原因带出去
    if not content_type:
        raise RuntimeError(
            "底图服务没有返回图片："
            + data[:160].decode("utf-8", errors="replace")
        )

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(data)
        prune_tile_cache()

    except OSError:
        pass

    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", "public, max-age=604800")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler._write_body(data) if hasattr(handler, "_write_body") else handler.wfile.write(data)


# ============================================================
# 标记点报告（Word）：逆地理编码 / 视频抽帧 / 地图截图 / docx
#
# python-docx 与 Pillow 都是【延迟导入】：缺库时后端照常启动，
# 只有报告相关接口报错，并在 /api/config 里如实告诉前端。
# ============================================================


def report_capabilities():
    """报告要用的三方库 / 程序在不在，如实报给前端。"""

    def importable(module_name):

        try:
            __import__(module_name)
            return True

        except Exception:
            return False

    return {
        "docx": importable("docx"),
        "pillow": importable("PIL"),
        "ffmpeg": bool(find_ffmpeg()),
    }


def new_report_name(prefix, suffix):
    """report_cache/ 下的新文件名：纯 ASCII，省得 URL 编码出问题。"""

    stamp = time.strftime("%Y%m%d-%H%M%S")

    digest = hashlib.sha1(os.urandom(16)).hexdigest()[:6]

    return f"{prefix}_{stamp}_{digest}{suffix}"


def report_file(name):
    """把 /report/<名字> 映射成磁盘路径：只允许单层文件名。"""

    if not name or "/" in name or "\\" in name or ".." in name:
        raise ValueError("Invalid file name.")

    return REPORT_DIR / name


def resolve_report_image(name):
    """报告里的图片名 -> 磁盘路径；不存在就返回 None（不往 docx 里塞坏图）。"""

    if not name:
        return None

    try:
        path = report_file(str(name))

    except ValueError:
        return None

    return path if path.is_file() else None


def safe_file_stem(text, fallback="Untitled"):
    """把项目名之类的东西收拾成能进文件名的样子。"""

    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", str(text or "")).strip(" ._")

    return cleaned or fallback


def format_seconds_text(seconds):
    """秒 -> 00:00:00（报告里显示视频时间用）。"""

    try:
        total = max(0, int(float(seconds)))

    except (TypeError, ValueError):
        return "-"

    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def reverse_geocode_place(lat, lng):
    """经纬度 -> 「广东省肇庆市高要区南岸街道」（天地图逆地理编码）。

    取不到就抛错，由调用方写「未解析」—— 绝不编造位置。
    """

    tianditu_key = get_tianditu_key()

    if not tianditu_key:
        raise ValueError("No Tianditu key configured, so the location cannot be resolved.")

    try:
        lat_value = float(lat)
        lng_value = float(lng)

    except (TypeError, ValueError):
        raise ValueError("Invalid latitude/longitude.")

    if not (-90.0 <= lat_value <= 90.0 and -180.0 <= lng_value <= 180.0):
        raise ValueError("Latitude/longitude out of range.")

    cache_key = f"{lat_value:.6f},{lng_value:.6f}"

    with REVERSE_GEOCODE_LOCK:
        cached = REVERSE_GEOCODE_MEMORY.get(cache_key)

    if cached is not None:
        return cached

    post_str = json.dumps(
        {"lon": lng_value, "lat": lat_value, "ver": 1},
        ensure_ascii=False
    )

    url = (
        TIANDITU_GEOCODER_URL
        + "?"
        + urlencode(
            {
                "postStr": post_str,
                "type": "geocode",
                "tk": tianditu_key,
            }
        )
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent":
                "LianheZhihui-UAV-Inspection-Map/1.0",
        }
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(
                response.read().decode("utf-8", errors="replace")
            )

    except urllib.error.HTTPError as e:
        raise ValueError(f"天地图逆地理编码失败：HTTP {e.code}")

    except urllib.error.URLError as e:
        raise ValueError(f"天地图逆地理编码失败：{e.reason}")

    except json.JSONDecodeError:
        raise ValueError("Tianditu reverse geocoding did not return JSON.")

    if str(payload.get("status")) != "0":
        raise ValueError(
            "Tianditu reverse geocoding failed: "
            + str(payload.get("msg") or payload.get("status") or "unknown reason")
        )

    result = payload.get("result") or {}
    component = result.get("addressComponent") or {}

    parts = []

    for field in ("province", "city", "county", "town", "village"):
        value = str(component.get(field) or "").strip()
        if value and value not in parts:
            parts.append(value)

    answer = {
        "place": "".join(parts) or str(result.get("formatted_address") or "").strip(),
        "detail": str(result.get("formatted_address") or "").strip(),
    }

    with REVERSE_GEOCODE_LOCK:
        REVERSE_GEOCODE_MEMORY[cache_key] = answer

    return answer


def cached_map_tile_bytes(source, z, x, y):
    """取一块底图瓦片：命中磁盘缓存就直接用，否则下载并写回缓存。

    和 proxy_map_tile 共用同一份缓存目录 —— 报告里的地图截图能直接吃到
    屏幕上已经看过的瓦片，不会把整片区域重新下一遍。
    """

    cache_path = (
        MAP_TILE_CACHE_DIR
        / source
        / str(z)
        / str(x)
        / f"{y}.tile"
    )

    if cache_path.exists():

        try:
            if time.time() - cache_path.stat().st_mtime < MAP_TILE_CACHE_SECONDS:
                data = cache_path.read_bytes()
                if data:
                    return data

        except OSError:
            pass

    request = urllib.request.Request(
        tile_source_url(source, z, x, y),
        headers={
            "User-Agent":
                "LianheZhihui-UAV-Inspection-Map/1.0",
        }
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read()

    except urllib.error.HTTPError as e:
        raise ValueError(f"底图瓦片取不到（{source} {z}/{x}/{y}）：HTTP {e.code}")

    except urllib.error.URLError as e:
        raise ValueError(f"底图瓦片取不到（{source} {z}/{x}/{y}）：{e.reason}")

    if not data:
        raise ValueError(f"底图瓦片是空的（{source} {z}/{x}/{y}）。")

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(data)

    except OSError:
        pass

    return data


def mercator_world_pixel(lat, lng, zoom):
    """经纬度 -> 整幅世界地图在 zoom 级下的像素坐标（Web 墨卡托 + XYZ 瓦片）。"""

    tiles_across = 1 << zoom

    lat_rad = math.radians(max(-85.05112878, min(85.05112878, lat)))

    x = (lng + 180.0) / 360.0 * tiles_across * MAP_TILE_PIXELS

    y = (
        1.0
        - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi
    ) / 2.0 * tiles_across * MAP_TILE_PIXELS

    return x, y


def draw_dashed_line(draw, start, end, color, width=2, dash=6, gap=6):
    """画一条虚线（PIL 没有虚线支持，自己按段画）。"""

    x1, y1 = start
    x2, y2 = end

    total = math.hypot(x2 - x1, y2 - y1)

    if total <= 0:
        return

    ux, uy = (x2 - x1) / total, (y2 - y1) / total
    position = 0.0

    while position < total:

        stop = min(position + dash, total)

        draw.line(
            (
                x1 + ux * position,
                y1 + uy * position,
                x1 + ux * stop,
                y1 + uy * stop,
            ),
            fill=color,
            width=width
        )

        position = stop + gap


# 目标点标志：白圈打底 + 红十字 —— **地图截图与原片截图共用这一套画法**，
# 页面上、地图截图里、视频截图里看到的都是同一种「目标点」符号。
# 半径沿用像素值，但视频截图有 4K 与 2480px 两档，固定像素在两档下视觉大小会差一倍，
# 所以那边按图像宽度取比例（见 TARGET_MARK_WIDTH_RATIO）。
TARGET_MARK_WIDTH_RATIO = 0.010     # 半径 ≈ 图宽的 1%（铺满 15.9cm 时直径约 3.2mm）


def draw_target_marker(draw, center_x, center_y, radius):
    """在 (center_x, center_y) 画目标点十字（白圈打底，深浅底图上都看得见）。"""

    center_x = int(round(center_x))
    center_y = int(round(center_y))
    radius = max(6, int(round(radius)))

    # 十字臂比圆多伸出去一点（和页面上那个准星一致）
    arm = radius + max(4, int(round(radius * 0.62)))

    for color, line_width in (
        ((255, 255, 255), max(2, int(round(radius * 0.31)))),
        ((220, 38, 38), max(1, int(round(radius * 0.19)))),
    ):
        draw.ellipse(
            (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
            outline=color,
            width=line_width
        )
        draw.line(
            (center_x - arm, center_y, center_x + arm, center_y),
            fill=color,
            width=line_width
        )
        draw.line(
            (center_x, center_y - arm, center_x, center_y + arm),
            fill=color,
            width=line_width
        )


def parse_image_spot(payload):
    """画面上的落点（归一化 0..1，左上为原点）：`spot_fx` / `spot_fy`。

    给了就返回 `(fx, fy)`；没给、不是数字、或越界都返回 `None`
    —— **不编造位置**：老标记点没存过这两个字段，报告里就不叠目标点标志。
    """

    if payload.get("spot_fx") is None or payload.get("spot_fy") is None:
        return None

    try:
        fx = float(payload["spot_fx"])
        fy = float(payload["spot_fy"])

    except (TypeError, ValueError):
        return None

    if not (0.0 <= fx <= 1.0 and 0.0 <= fy <= 1.0):
        return None

    return (fx, fy)


def draw_drone_arrow(draw, center, bearing, size=DRONE_ARROW_SIZE):
    """在 center 画一个朝 bearing（自正北顺时针）的飞机箭头。

    形状与颜色跟页面上的飞机图标一致；屏幕坐标 x 向右、y 向下。
    """

    try:
        rad = math.radians(float(bearing or 0))

    except (TypeError, ValueError):
        rad = 0.0

    cos_a, sin_a = math.cos(rad), math.sin(rad)

    def place(dx, dy):
        return (
            center[0] + dx * cos_a - dy * sin_a,
            center[1] + dx * sin_a + dy * cos_a,
        )

    # 局部坐标（机头朝上），比例照抄网页上的 SVG：机尖 (20,3)、翼尖 (34,34)/(6,34)、
    # 尾中缺口 (20,26)，中心 (20,20) —— 换算成相对 size 的比例就是 0.82 / 0.35。
    # （之前用 0.62/0.5，画出来比网页版窄一截，像被压扁了）
    points = [
        place(0, -size),
        place(size * 0.82, size * 0.82),
        place(0, size * 0.35),
        place(-size * 0.82, size * 0.82),
    ]

    draw.polygon(
        points,
        fill=DRONE_ARROW_FILL,
        outline=(255, 255, 255),
        width=2
    )


def compose_map_snapshot(lat, lng, zoom, kind, width, height, drone=None, target=None):
    """按指定底图拼一张地图截图，并标出目标点。

    不用前端 canvas 截图：瓦片跨域会污染画布，拿不到图。

    - `lat` / `lng`：**取景中心**（图片正中间对应的经纬度）
    - `target`：**目标点**（画红十字与虚线终点的地方），不给就当取景中心。
      有飞机时取景中心取「目标点与飞机的中点」，这时两者不是一个点。
    - `drone`：给了（lat/lng/bearing）就画飞机图标和「飞机 -> 目标点」的注视虚线，
      和地图页面上看到的是同一种表达。
    """

    from PIL import Image, ImageDraw

    layers = MAP_SNAPSHOT_LAYERS.get(kind) or MAP_SNAPSHOT_LAYERS["street"]

    tiles_across = 1 << zoom

    # 取景中心在「整幅世界地图」上的像素坐标
    world_x, world_y = mercator_world_pixel(lat, lng, zoom)

    left = world_x - width / 2.0
    top = world_y - height / 2.0

    first_x = int(math.floor(left / MAP_TILE_PIXELS))
    first_y = int(math.floor(top / MAP_TILE_PIXELS))
    last_x = int(math.floor((left + width - 1) / MAP_TILE_PIXELS))
    last_y = int(math.floor((top + height - 1) / MAP_TILE_PIXELS))

    if (last_x - first_x + 1) * (last_y - first_y + 1) > MAP_SNAPSHOT_MAX_TILES:
        raise ValueError("地图截图范围太大：请减小尺寸或降低缩放级别。")

    canvas = Image.new(
        "RGBA",
        (
            (last_x - first_x + 1) * MAP_TILE_PIXELS,
            (last_y - first_y + 1) * MAP_TILE_PIXELS,
        ),
        (255, 255, 255, 255)
    )

    for source, is_overlay in layers:

        for tile_x in range(first_x, last_x + 1):
            for tile_y in range(first_y, last_y + 1):

                if not (0 <= tile_x < tiles_across and 0 <= tile_y < tiles_across):
                    continue

                data = cached_map_tile_bytes(source, zoom, tile_x, tile_y)

                tile = Image.open(io.BytesIO(data)).convert("RGBA")

                if tile.size != (MAP_TILE_PIXELS, MAP_TILE_PIXELS):
                    tile = tile.resize((MAP_TILE_PIXELS, MAP_TILE_PIXELS))

                position = (
                    (tile_x - first_x) * MAP_TILE_PIXELS,
                    (tile_y - first_y) * MAP_TILE_PIXELS,
                )

                if is_overlay:
                    canvas.alpha_composite(tile, position)
                else:
                    canvas.paste(tile, position)

    offset_x = int(round(left - first_x * MAP_TILE_PIXELS))
    offset_y = int(round(top - first_y * MAP_TILE_PIXELS))

    image = canvas.crop(
        (offset_x, offset_y, offset_x + width, offset_y + height)
    ).convert("RGB")

    # 标出目标点：白圈打底 + 红十字，深浅底图上都看得见。
    # 位置按坐标算而不是写死图片中心 —— 有飞机时取景中心是「目标点与飞机的中点」，
    # 目标点会偏一点，写死中心就会把红十字画错地方。
    draw = ImageDraw.Draw(image)

    if target and target.get("lat") is not None and target.get("lng") is not None:
        target_x, target_y = mercator_world_pixel(
            float(target["lat"]),
            float(target["lng"]),
            zoom
        )

    else:
        target_x, target_y = world_x, world_y

    center_x = int(round(target_x - left))
    center_y = int(round(target_y - top))

    draw_target_marker(draw, center_x, center_y, 16)

    # 飞机 + 「飞机 -> 目标点」的注视虚线（和地图页面上是同一种表达）
    if drone and drone.get("lat") is not None and drone.get("lng") is not None:

        drone_world_x, drone_world_y = mercator_world_pixel(
            float(drone["lat"]),
            float(drone["lng"]),
            zoom
        )

        drone_center = (drone_world_x - left, drone_world_y - top)

        try:
            bearing_rad = math.radians(float(drone.get("bearing") or 0))

        except (TypeError, ValueError):
            bearing_rad = 0.0

        # 虚线从【机头】出发（和页面上那条线一样，起点按像素偏移算）
        nose = (
            drone_center[0] + math.sin(bearing_rad) * DRONE_NOSE_PX,
            drone_center[1] - math.cos(bearing_rad) * DRONE_NOSE_PX,
        )

        draw_dashed_line(draw, nose, (center_x, center_y), LOOK_LINE_COLOR, width=2)

        draw_drone_arrow(draw, drone_center, drone.get("bearing"))

    return image


def make_video_snapshot(payload):
    """视频抽帧：从【原片】抽，所以是原始分辨率。"""

    project_name = str(payload.get("project_name") or "")
    relative_path = str(payload.get("path") or "")

    if not project_name:
        raise ValueError("Missing project name.")

    if not relative_path:
        raise ValueError("Missing video relative path.")

    try:
        time_seconds = max(0.0, float(payload.get("time") or 0))

    except (TypeError, ValueError):
        raise ValueError("Invalid time.")

    mode = str(payload.get("mode") or "full")

    if mode not in ("full", "a4"):
        mode = "full"

    video_path = resolve_project_video(
        project_name,
        payload.get("folder_index"),
        relative_path
    )

    ffmpeg = find_ffmpeg()

    if not ffmpeg:
        raise ValueError("ffmpeg not found, so no video frame can be extracted. Install ffmpeg and restart the service.")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # 中间出 PNG，再交给 Pillow 转 JPEG。原因是 ffmpeg 写的 JPEG 头是
    # SOI + COM("Lavc…")，python-docx 的嗅探只认 JFIF/Exif，会直接抛
    # UnrecognizedImageError（而且它的消息是空的，很难查）。Pillow 存的
    # JPEG 带 JFIF 头，docx 认。
    temp_path = REPORT_DIR / new_report_name("frame", ".png")
    name = new_report_name("shot", ".jpg")
    output_path = REPORT_DIR / name

    command = [
        ffmpeg,
        "-ss", f"{time_seconds:.3f}",
        "-i", str(video_path),
        "-frames:v", "1",
        "-y", str(temp_path),
    ]

    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
        )

    except subprocess.TimeoutExpired:
        raise ValueError("Timed out extracting the video frame.")

    except OSError as e:
        raise ValueError(f"无法启动 ffmpeg：{e}")

    if (
        completed.returncode != 0
        or not temp_path.exists()
        or temp_path.stat().st_size == 0
    ):
        try:
            temp_path.unlink()

        except OSError:
            pass

        lines = (completed.stderr or b"").decode(
            "utf-8", "replace"
        ).strip().splitlines()

        raise ValueError(
            "Frame extraction failed: "
            + (lines[-1] if lines else f"ffmpeg 退出码 {completed.returncode}")
        )

    try:
        from PIL import Image

        with Image.open(temp_path) as frame:

            image = frame.convert("RGB")

            # A4 档要的是「固定铺满正文宽」的那一版：不论原片是 4K 还是 1080p，
            # 都缩放到 REPORT_IMAGE_WIDTH_A4。原来只写了「大于才缩」，
            # 于是 1080p 素材抽出来的帧（1920 宽）永远到不了 2480 ——
            # 实测 1920x1080，报告里那张图比 A4 正文窄一截。
            if mode == "a4" and image.width != REPORT_IMAGE_WIDTH_A4:
                ratio = REPORT_IMAGE_WIDTH_A4 / image.width
                image = image.resize(
                    (
                        REPORT_IMAGE_WIDTH_A4,
                        max(2, round(image.height * ratio))
                    )
                )

            width, height = image.size

            # 目标点标志：当初在画面上点的那一处（归一化坐标）—— 按输出分辨率放大
            spot = parse_image_spot(payload)

            if spot:
                from PIL import ImageDraw

                radius = max(12, round(width * TARGET_MARK_WIDTH_RATIO))

                draw_target_marker(
                    ImageDraw.Draw(image),
                    spot[0] * width,
                    spot[1] * height,
                    radius
                )

            image.save(
                output_path,
                "JPEG",
                quality=92,
                optimize=True,
                dpi=report_image_dpi(width, height, REPORT_VIDEO_IMAGE_MAX_HEIGHT_CM)
            )

    except Exception as e:
        raise ValueError(
            "Converting the extracted frame failed (Pillow is required): "
            + (str(e) or type(e).__name__)
        )

    finally:
        try:
            temp_path.unlink()

        except OSError:
            pass

    return {
        "file": name,
        "url": "/report/" + name,
        "time": round(time_seconds, 3),
        "mode": mode,
        "width": width,
        "height": height,
        "spot": bool(parse_image_spot(payload)),
    }


def make_map_snapshot(payload):
    """拼一张地图截图；底图类型由前端传（跟随用户当前选的那一种）。"""

    try:
        lat = float(payload.get("lat"))
        lng = float(payload.get("lng"))

    except (TypeError, ValueError):
        raise ValueError("Invalid latitude/longitude.")

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        raise ValueError("Latitude/longitude out of range.")

    try:
        zoom = int(payload.get("zoom") or 16)

    except (TypeError, ValueError):
        zoom = 16

    if not (1 <= zoom <= 19):
        raise ValueError("Zoom level must be between 1 and 19.")

    kind = str(payload.get("basemap") or "street")

    if kind not in MAP_SNAPSHOT_LAYERS:
        kind = "street"

    try:
        width = int(payload.get("width") or 1280)
        height = int(payload.get("height") or 960)

    except (TypeError, ValueError):
        width, height = 1280, 960

    width = max(320, min(width, 2560))
    height = max(240, min(height, 1920))

    # 目标点（红十字/虚线终点）：不给就当取景中心
    target = None

    if payload.get("target_lat") is not None and payload.get("target_lng") is not None:

        try:
            target = {
                "lat": float(payload["target_lat"]),
                "lng": float(payload["target_lng"]),
            }

        except (TypeError, ValueError):
            target = None

    # 飞机的位置与朝向（可选）：给了就在图上画飞机和注视虚线
    drone = None

    if payload.get("drone_lat") is not None and payload.get("drone_lng") is not None:

        try:
            drone = {
                "lat": float(payload["drone_lat"]),
                "lng": float(payload["drone_lng"]),
                "bearing": float(payload.get("drone_bearing") or 0),
            }

        except (TypeError, ValueError):
            drone = None

    image = compose_map_snapshot(lat, lng, zoom, kind, width, height, drone, target)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    name = new_report_name("map", ".jpg")

    image.save(
        REPORT_DIR / name,
        "JPEG",
        quality=88,
        dpi=report_image_dpi(image.width, image.height, REPORT_MAP_IMAGE_MAX_HEIGHT_CM)
    )

    return {
        "file": name,
        "url": "/report/" + name,
        "basemap": kind,
        "zoom": zoom,
        "width": image.width,
        "height": image.height,
        "drone": bool(drone),
    }


# ------------------------------------------------------------
# docx：书签 + 超链接目录（不是要按 F9 刷新的域）
# ------------------------------------------------------------


def add_docx_bookmark(paragraph, name, bookmark_id):
    """给段落挂一个书签（目录的超链接指到它）。"""

    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(bookmark_id))
    start.set(qn("w:name"), name)

    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(bookmark_id))

    paragraph._p.insert(0, start)
    paragraph._p.append(end)


def add_docx_internal_link(paragraph, anchor, text):
    """加一个「点了直接跳转」的超链接（w:hyperlink + w:anchor）。"""

    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    link = OxmlElement("w:hyperlink")
    link.set(qn("w:anchor"), anchor)

    run = OxmlElement("w:r")

    properties = OxmlElement("w:rPr")

    # 目录项也要显式给字体（这是手写 XML 的 run，不显式给就吃主题字体）
    fonts = OxmlElement("w:rFonts")
    fonts.set(qn("w:ascii"), REPORT_FONT_LATIN)
    fonts.set(qn("w:hAnsi"), REPORT_FONT_LATIN)
    fonts.set(qn("w:eastAsia"), REPORT_FONT_CJK)
    properties.append(fonts)

    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    properties.append(color)

    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    properties.append(underline)

    run.append(properties)

    text_element = OxmlElement("w:t")
    text_element.text = text
    run.append(text_element)

    link.append(run)
    paragraph._p.append(link)


def report_image_dpi(pixel_width, pixel_height, max_height_cm):
    """给报告插图写一个「诚实的 DPI」：像素宽 ÷ 目标显示宽。

    插图的显示尺寸是按高度封顶算的（见 report_picture_width_cm），docx 里也写死了
    wp:extent —— Word 按 wp:extent 排，本来就不会错。

    写上 DPI 是为了那些「不看 wp:extent、按图片固有尺寸排」的阅读器也算出同样大小，
    顺带让这些截图在打印时有正确的分辨率含义。
    （实测：捆绑 LibreOffice 两者都不看，渲染结果不受影响；别拿它的光栅当尺寸依据，
    它的整页光栅比实际页面放大约 10% 且底部会裁掉一截。）
    """

    if not pixel_width or not pixel_height:
        return (300, 300)

    width_cm = min(
        REPORT_IMAGE_MAX_WIDTH_CM,
        max_height_cm * (pixel_width / pixel_height)
    )

    dpi = pixel_width / (width_cm / 2.54)

    return (round(dpi), round(dpi))


def report_image_pixel_size(path):
    """读一张图的像素尺寸；读不出来就返回 None。"""

    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size

    except Exception:
        return None


def report_picture_width_cm(path, max_height_cm=REPORT_VIDEO_IMAGE_MAX_HEIGHT_CM):
    """算这张图在报告里该多宽：**先铺满正文宽**，只有太高时才按高度上限回缩。

    一个点那一节要塞下：字段表 + 图 1（视频截图）+ 图 2（地图截图）+ 两行图注，
    必须都在同一页 A4 里 —— 所以照片与地图都横向铺满（15.9cm），
    高度超限的（热成像 5:4 那类）才回缩，免得把章节顶到下一页。
    """

    size = report_image_pixel_size(path)

    if not size or not size[0] or not size[1]:
        return REPORT_IMAGE_MAX_WIDTH_CM

    width = max_height_cm * (size[0] / size[1])

    return round(min(width, REPORT_IMAGE_MAX_WIDTH_CM), 2)


def add_report_picture(document, path, max_height_cm=REPORT_VIDEO_IMAGE_MAX_HEIGHT_CM):
    """按上面算出来的宽度插图（返回段落，方便控制间距）。

    keep_with_next：图要和紧跟的图注留在同一页 —— 不然会出现
    「图在这一页底、说明在下一页」这种很难看的排法。
    段落居中：铺满宽度的图看不出差别，回缩过的窄图（热成像）居中才好看。
    """

    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    paragraph = document.add_paragraph()
    # 左对齐（不是居中）：图与表格的左边缘必须是同一条线
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.space_before = Pt(6)
    paragraph.paragraph_format.keep_with_next = True

    paragraph.add_run().add_picture(
        str(path),
        width=Cm(report_picture_width_cm(path, max_height_cm))
    )

    return paragraph


def add_report_caption(document, text):
    """图注：小字、居中、跟着图走。"""

    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    caption = document.add_paragraph(text)
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption.paragraph_format.space_after = Pt(2)
    set_report_font(caption.runs[0], 9)

    return caption


# 报告里的字体：中文走 w:eastAsia，西文与数字走 w:ascii/w:hAnsi。
# 只设前者的话，Word 会拿主题里的东亚字体（python-docx 默认模板是 MS Gothic）
# 去配西文，标题就会一半微软雅黑、一半 MS Gothic。
REPORT_FONT_LATIN = "Arial"
REPORT_FONT_CJK = "微软雅黑"


def set_report_font(target, size_pt=None, bold=None):
    """统一样式或 run 的字体：西文/数字 Arial，中文 微软雅黑。

    关键：**必须先把主题字体引用删掉**。样式里常常写着
    `w:asciiTheme="majorHAnsi"` / `w:eastAsiaTheme="majorEastAsia"`，
    它们的优先级高于 `w:ascii` / `w:eastAsia` —— 只写字体名不改主题引用的话，
    标题里的中文仍是主题的 MS Gothic、数字仍是主题的 Calibri（踩过）。
    """

    from docx.oxml.ns import qn
    from docx.shared import Pt

    target.font.name = REPORT_FONT_LATIN

    if size_pt is not None:
        target.font.size = Pt(size_pt)

    if bold is not None:
        target.font.bold = bold

    element = getattr(target, "_element", None)

    if element is None:
        element = target.element          # 段落样式走这条

    rfonts = element.get_or_add_rPr().get_or_add_rFonts()

    for theme_attr in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
        rfonts.attrib.pop(qn(f"w:{theme_attr}"), None)

    rfonts.set(qn("w:eastAsia"), REPORT_FONT_CJK)


def format_latitude(lat):
    """纬度数值：带符号的十进制度数（南纬为负、北纬为正）。

    半球写在表头里（`纬度（°N）`），数字尾巴上不带 N/S —— 用户要拿去复制粘贴，
    多两个字母很碍事；半球用正负号表示，比写 S/W 更好复制。
    """

    return f"{float(lat):.6f}"


def format_longitude(lng):
    """经度数值：带符号的十进制度数（西经为负、东经为正）。"""

    return f"{float(lng):.6f}"


def docx_point_field_table(document, point):
    """每个点那一节里的「字段 / 值」小表（中部左对齐）。"""

    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm

    rows = [
        (i18n.t("report.col_name"), point.get("name") or i18n.t("report.marker_fallback")),
        # 半球写在表头里；数字用正负号区分南北/东西，方便直接复制
        (i18n.t("report.field_lat"), point.get("lat_text") or ""),
        (i18n.t("report.field_lng"), point.get("lng_text") or ""),
        (i18n.t("report.col_location"), point.get("place") or i18n.t("report.unresolved")),
        (i18n.t("report.col_video"), point.get("video") or "-"),
        (i18n.t("report.col_time"), point.get("time_text") or "-"),
    ]

    table = document.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    table.autofit = False

    widths = (Cm(2.6), Cm(13.3))       # 合计 15.9cm，与插图同宽

    for label, value in rows:
        cells = table.add_row().cells
        cells[0].text = label
        cells[1].text = str(value)

        for cell, width in zip(cells, widths):
            cell.width = width
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

            for paragraph in cell.paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT

    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    set_report_font(run, 10)

    # 列宽要同时写进「表格网格」和单元格：只写单元格（tcW）的话，
    # gridCol 还是 python-docx 建表时的默认等分（8.0+8.0=16.0cm），
    # 不同阅读器取哪个值不一致 —— 表格边框就会比插图多出 1~2mm（用户实测过）。
    for column, width in zip(table.columns, widths):
        column.width = width

    set_docx_table_width(table, widths)

    return table


def breakable_text(text, every=12):
    """每 N 个字符插一个零宽空格，给 Word 制造换行机会。

    视频文件名（DJI_20260924101516_0001_V.MP4）里的下划线 Word 不当断点，
    放在表格里会把整张表撑出页面 —— 加了零宽空格就能断，而且看不见。
    """

    raw = str(text or "")

    if len(raw) <= every:
        return raw

    return "\u200b".join(raw[i:i + every] for i in range(0, len(raw), every))


def set_docx_cell(cell, text, size_pt=8.5, bold=False):
    """写单元格：字号压下来（汇总表 7 列，默认字号会撑爆）+ 中部左对齐。"""

    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    cell.text = str(text)

    # 统一「中部左对齐」：垂直居中、水平靠左
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

    for paragraph in cell.paragraphs:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT

        for run in paragraph.runs:
            set_report_font(run, size_pt, bold)


def set_docx_table_width(table, column_widths):
    """把表格总宽、缩进、单元格边距都写死，保证「表格边框」与「插图」同一条线。

    python-docx 建的表格 `tblW` 是 `auto/0`：只设网格列宽时，
    有的渲染器（LibreOffice）会按内容重算列宽并把表撑出正文区。
    显式写死总宽（= 各列宽之和）最省心，Word / LibreOffice 都照它排。

    另一半是**位置**，这里有个反直觉的坑（用户实测发现的）：

    Word 定位表格是按**单元格里文字的起始位置**算的，不是按边框。所以
    `tblInd = 0` 时文字落在正文左边距上，**边框却会被推到边距左边一个「左单元格边距」的距离**
    —— Word 默认左右单元格边距 0.08 英寸（≈2.03mm），用户量到的「表格边框比照片多出约 2mm」
    就是这个数（他把它调成 0 之后几乎严格对齐，也验证了这一点）。

    所以这里把 `tblCellMar` 左右都显式写成 0：文字起点、表格边框、左对齐的插图
    三者就都落在正文左边距上；而且各家阅读器对 `tblInd` 的解释不一致时也不会跑偏
    （只写 tblInd 补偿的话，Word 与 LibreOffice 会差出一个边距）。
    """

    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    total_emu = sum(int(width) for width in column_widths)
    total_twips = max(1, int(round(total_emu / 635)))   # 1 twip = 635 EMU

    tblPr = table._tbl.tblPr

    # 总宽：tblW 要排在 tblInd/tblLayout/tblCellMar 之前（schema 顺序）
    tblW = tblPr.find(qn("w:tblW"))

    if tblW is None:
        tblW = OxmlElement("w:tblW")
        tblPr.append(tblW)

    tblW.set(qn("w:type"), "dxa")
    tblW.set(qn("w:w"), str(total_twips))

    # 缩进 0：不给表格样式/阅读器留默认负缩进的余地
    for existing in tblPr.findall(qn("w:tblInd")):
        tblPr.remove(existing)

    indent = OxmlElement("w:tblInd")
    indent.set(qn("w:type"), "dxa")
    indent.set(qn("w:w"), "0")
    tblW.addnext(indent)          # 紧跟 tblW，顺序合 schema

    # 单元格边距全 0（见上面的说明：这是边框能不能和插图对齐的关键）
    for existing in tblPr.findall(qn("w:tblCellMar")):
        tblPr.remove(existing)

    cell_margins = OxmlElement("w:tblCellMar")

    for side in ("top", "left", "bottom", "right"):
        node = OxmlElement(f"w:{side}")
        node.set(qn("w:type"), "dxa")
        node.set(qn("w:w"), "0")
        cell_margins.append(node)

    # 顺序要合 schema：tblCellMar 在 tblLayout 之后、tblLook 之前
    tblLook = tblPr.find(qn("w:tblLook"))

    if tblLook is not None:
        tblLook.addprevious(cell_margins)
    else:
        tblPr.append(cell_margins)

    return table


def normalize_report_points(points):
    """把前端传来的点收拾干净：格式化一律在服务端做，不信前端。"""

    normalized = []

    for index, raw in enumerate(points, start=1):

        if not isinstance(raw, dict):
            continue

        try:
            lat = float(raw.get("lat"))
            lng = float(raw.get("lng"))

        except (TypeError, ValueError):
            continue

        normalized.append({
            "name": str(raw.get("name") or f"标记点 {index}"),
            "lat": lat,
            "lng": lng,
            # 经纬度带上半球：N/S、E/W（南纬西经不写负号，直接给 S/W）
            "lat_text": format_latitude(lat),
            "lng_text": format_longitude(lng),
            "place": str(raw.get("place") or "unresolved"),
            "video": str(raw.get("video") or ""),
            "time": raw.get("time") or 0,
            "time_text": format_seconds_text(raw.get("time")),
            "video_image": str(raw.get("video_image") or ""),
            "map_image": str(raw.get("map_image") or ""),
            "basemap_name": str(raw.get("basemap_name") or ""),
            "zoom": raw.get("zoom") or 16,
        })

    return normalized


def build_docx_report(payload):
    """生成标记点报告 docx，返回文件信息。

    结构：标题 -> 目录（可点）-> 汇总表 -> 每点一节（字段 + 两张图）。
    """

    from docx import Document
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt

    # 报告语言：这个请求可能不带语言上下文（比如从后台任务发起），
    # 所以 payload 里可以显式指定；不指定就用请求/服务端设置定下的那个。
    if payload.get("lang"):
        i18n.set_lang(payload.get("lang"))

    project_name = str(payload.get("project_name") or "")

    points = normalize_report_points(payload.get("points") or [])

    if not points:
        raise ValueError(i18n.t("report.no_markers"))

    image_mode = str(payload.get("image_mode") or "full")

    mode_text = i18n.t(
        "report.image_compressed" if image_mode == "a4" else "report.image_original")

    document = Document()

    # 页面：A4 + 2.5cm 页边距（python-docx 默认模板是 Letter，中文报告要 A4）
    section = document.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)

    # 正文：西文 Arial + 中文微软雅黑。（只设一种的话，Word 会拿主题里的
    # 东亚字体 —— python-docx 默认模板是 MS Gothic —— 去凑另一种，就会出现两种字体）
    set_report_font(document.styles["Normal"], 10.5)

    # 标题：默认 Title 是 28pt，长项目名会顶出页面，压到 19pt
    set_report_font(document.styles["Title"], 19)

    # 章节小标题（目录 / 汇总表 / 一、二、…）也要设 —— 它们默认继承主题字体，
    # 正是「标题里中文一种字体、数字另一种」的根源
    for style_name in ("Heading 1", "Heading 2", "Heading 3", "List Number"):
        try:
            set_report_font(document.styles[style_name])

        except KeyError:
            pass

    document.add_heading(
        i18n.t("report.title", project=project_name or i18n.t("report.untitled")),
        level=0
    )

    meta = document.add_paragraph(
        i18n.t("report.generated",
               time=time.strftime('%Y-%m-%d %H:%M'),
               count=len(points), mode=mode_text)
    )
    meta.runs[0].font.size = Pt(9)
    set_report_font(meta.runs[0], 9)

    document.add_heading(i18n.t("report.contents"), level=1)
    hint = document.add_paragraph(i18n.t("report.contents_hint"))
    set_report_font(hint.runs[0], 9)

    for index, point in enumerate(points, start=1):
        paragraph = document.add_paragraph(style="List Number")
        add_docx_internal_link(paragraph, f"mark{index}", point["name"])

    document.add_heading(i18n.t("report.summary"), level=1)

    columns = [
        i18n.t("report.col_index"), i18n.t("report.col_name"),
        i18n.t("report.col_lat"), i18n.t("report.col_lng"),
        i18n.t("report.col_location"), i18n.t("report.col_video"),
        i18n.t("report.col_time"),
    ]

    # 列宽写死 + 关掉自动伸缩：长文件名（下划线处 Word 不断行）容易把表撑出正文区。
    # 合计 15.9cm —— 与插图同一个宽度，左边缘、右边缘才对得齐。
    # 英文表头比中文长（"Video time" 要 1.56cm），所以第 6 列从 1.4 加宽到 2.4，
    # 余下的宽度从 #/Name/Lat/Lng/Location/Video file 各匀一点，总和不变。
    column_widths = (
        Cm(0.9), Cm(2.4), Cm(1.9), Cm(2.0), Cm(3.3), Cm(3.0), Cm(2.4)
    )

    summary = document.add_table(rows=1, cols=len(columns))
    summary.style = "Table Grid"
    summary.autofit = False

    for cell, title in zip(summary.rows[0].cells, columns):
        set_docx_cell(cell, title, size_pt=8.5, bold=True)

    for index, point in enumerate(points, start=1):
        cells = summary.add_row().cells

        values = [
            str(index),
            point["name"],
            point["lat_text"],
            point["lng_text"],
            point["place"],
            breakable_text(point["video"] or "-"),
            point["time_text"],
        ]

        for cell, value in zip(cells, values):
            set_docx_cell(cell, value, size_pt=8.5)

    for row in summary.rows:
        for cell, width in zip(row.cells, column_widths):
            cell.width = width

    for column, width in zip(summary.columns, column_widths):
        column.width = width

    set_docx_table_width(summary, column_widths)

    for index, point in enumerate(points, start=1):

        document.add_page_break()

        heading = document.add_heading(
            # 章节标题：阿拉伯序号 + 英文句点 + 一个空格 + 点名（如 22. 东莞2-5）
            f"{index}. {point['name']}",
            level=1
        )
        add_docx_bookmark(heading, f"mark{index}", 1000 + index)

        docx_point_field_table(document, point)

        video_image = resolve_report_image(point["video_image"])
        map_image = resolve_report_image(point["map_image"])

        if video_image:
            add_report_picture(document, video_image)
            add_report_caption(
                document,
                i18n.t("report.fig_video",
                       video=point['video'] or '-', time=point['time_text'])
            ).paragraph_format.keep_with_next = True      # 图 2 跟着它一起走

        if map_image:
            add_report_picture(document, map_image, REPORT_MAP_IMAGE_MAX_HEIGHT_CM)
            add_report_caption(
                document,
                i18n.t("report.fig_map",
                       basemap=point['basemap_name'] or i18n.t("report.basemap_current"),
                       zoom=point['zoom'])
            )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    name = new_report_name("report", ".docx")

    document.save(str(REPORT_DIR / name))

    return {
        "file": name,
        "url": "/report/" + name,
        "download_name":
            i18n.t("report.filename",
                   project=safe_file_stem(project_name),
                   date=time.strftime('%Y-%m-%d')),
        "points": len(points),
        "image_mode": image_mode,
    }


# ============================================================
# HTTP Handler
# ============================================================

class ProjectManagerHandler(
    BaseHTTPRequestHandler
):

    # ========================================================
    # 语言
    # ========================================================

    def _apply_request_lang(self, parsed):
        """每个请求先把**本线程**的语言定下来，后面的 t() 就用它。

        优先级（从高到低）：
          1. 查询串 `?lang=en|zh`      —— 显式指定，测试和深链用
          2. `Accept-Language` 请求头   —— 浏览器自己带的
          3. 服务端保存的设置            —— 前端切换语言时写进去的
          4. 默认（英文）

        为什么要有第 3 层：有些调用**没有请求上下文**（Windows 文件选择对话框
        在独立线程里弹），它们只能读服务端设置。所以前端切换时要通知后端一次。

        为什么用 thread-local：`ThreadingHTTPServer` 每请求一个线程，
        这样并发请求之间不会互相踩语言。
        """
        lang = None
        try:
            q = parse_qs(parsed.query).get("lang") or []
            if q and q[0]:
                lang = q[0]
        except Exception:
            lang = None
        if lang is None:
            try:
                accept = self.headers.get("Accept-Language") or ""
                if accept:
                    # 只认第一个语言标签的主部（"zh-CN,zh;q=0.9" -> "zh"）
                    first = accept.split(",")[0].split(";")[0].strip()
                    if first:
                        cand = i18n.norm_lang(first)
                        # norm_lang 认不出来会给默认值；只有真的认出来了才采纳
                        if first.lower().replace("_", "-").startswith(("zh", "en")) \
                                or cand != i18n.DEFAULT_LANG:
                            lang = cand
            except Exception:
                lang = None
        if lang is None:
            lang = settings_store.get("lang")
        i18n.set_lang(lang)
        return i18n.get_lang()

    # ========================================================
    # HEAD
    # ========================================================

    def do_HEAD(self):
        """把 HEAD 当作 GET 处理，但只发响应头、不发正文。

        为什么必须实现：浏览器（以及某些播放器）在决定要不要请求一个视频/图片时，
        会先发一个 HEAD 探一下。不实现会返回 `501 Unsupported method ('HEAD')` ——
        功能不受影响，但控制台一片红字，而且探测失败后有些客户端会改用更笨的
        方式（整段下载）。

        实现方式：**不动 wfile**，只置一个"这次是 HEAD"的标志，
        由各正文出口自己跳过。
        试过"把 wfile 换成丢弃写入的壳"，结果是整个响应 0 字节 ——
        HTTP/1.0 单请求模式下 wfile 与连接生命周期绑得很紧，
        替换它会连带把 flush/close 语义弄坏。改成不碰连接的做法。
        """
        self._head_only = True
        try:
            self.do_GET()
        finally:
            self._head_only = False

    def _write_body(self, data):
        """正文出口统一走这里：HEAD 请求直接丢弃。

        新增的正文出口请一律用它，不要直接 self.wfile.write(...) ——
        漏掉一处就会往 HEAD 响应里塞数据，让客户端解析错乱（比 501 更难查）。
        """
        if getattr(self, "_head_only", False):
            return 0
        self.wfile.write(data)
        return len(data)

    # ========================================================
    # GET
    # ========================================================

    def do_GET(self):

        parsed = urlparse(
            self.path
        )

        path = parsed.path

        # 语言：每个请求先定下来（见 `_apply_request_lang`）。
        # 优先级：?lang= > Accept-Language > 服务端保存的设置 > 默认英文。
        self._apply_request_lang(parsed)

        if path == "/api/i18n":
            # 前端启动时拉一次：拿到整张文案表 + 当前语言 + 可选语言。
            # 这样前端**不需要**再维护一份重复的翻译表。
            want = (parse_qs(parsed.query).get("lang") or [""])[0]
            lang = i18n.norm_lang(want) if want else i18n.get_lang()
            json_response(self, {
                "lang": lang,
                "langs": list(i18n.LANGS),
                "messages": i18n.all_messages(lang),
            })
            return

        if path == "/":
            self.send_html(
                PROJECT_MANAGER_HTML
            )
            return

        if path == "/project_manager.html":
            self.send_html(
                PROJECT_MANAGER_HTML
            )
            return

        if path == "/project_import.html":
            self.send_html(
                PROJECT_IMPORT_HTML
            )
            return

        if path == "/project_media.html":
            self.send_html(
                PROJECT_MEDIA_HTML
            )
            return

        if (
            path
            ==
            "/project_video_inspector.html"
        ):
            self.send_html(
                PROJECT_VIDEO_INSPECTOR_HTML
            )
            return

        if path == "/project_geojson_preview.html":
            self.send_html(
                PROJECT_GEOJSON_PREVIEW_HTML
            )
            return

        if path == "/project_geo3d_preview.html":
            self.send_html(
                PROJECT_GEO3D_PREVIEW_HTML
            )
            return

        if path == "/pano360.html":
            self.send_html(
                PANO360_VIEWER_HTML
            )
            return

        if path == "/pano360_player.html":
            # 转码后的等距柱状视频播放器（播放 + 拖拽转向）。
            # 与 pano360.html 的分工：
            #   · pano360.html        逐帧向服务端要透视小图（无需转码，但只能一格一格看）
            #   · pano360_player.html 播转码产物（要转一次，之后随点随放、可连续拖拽）
            self.send_html(
                PANO360_PLAYER_HTML
            )
            return


        # ----------------------------------------------------
        # 地图瓦片代理
        # ----------------------------------------------------

        if path.startswith("/maptile/"):

            parts = path.strip("/").split("/")

            # 兼容两种写法：/maptile/z/x/y.png 与 /maptile/来源/z/x/y.png
            if len(parts) == 4 and parts[0] == "maptile":
                source = "osm"
                z, x, y = parts[1], parts[2], parts[3]

            elif len(parts) == 5 and parts[0] == "maptile":
                source = parts[1]
                z, x, y = parts[2], parts[3], parts[4]

            else:
                source = None
                z = x = y = None

            if source and y and "." in y:

                try:
                    proxy_map_tile(
                        self,
                        source,
                        z,
                        x,
                        y.rsplit(".", 1)[0]
                    )

                except Exception as e:

                    # send_error 的状态行只能是 latin-1，中文说明会抛
                    # UnicodeEncodeError 导致连响应都发不出去，这里分开处理
                    print(f"[底图代理] {source} {z}/{x}/{y} 失败：{e}")

                    self.send_error(502, "Tile upstream error")

                return

        # ----------------------------------------------------
        # 本地第三方资源（Leaflet 等），让页面不依赖外网 CDN
        # ----------------------------------------------------

        # 照片缩略图 / 原图：/photo?path=<绝对路径>
        # 安全：只允许读「某个项目文件夹内」的图片（否则就成了任意文件读取）。
        # 注意：parse_qs 在文件顶部已经 import 过了，这里**不要**再写一次
        # 「from urllib.parse import parse_qs」—— 函数里出现这个 import，Python 会把
        # parse_qs 当成整个 do_GET 的局部名；本函数里位置更靠前的那些分支
        # （/api/project/telemetry、/api/project/geojson…）用到它时就会报
        # UnboundLocalError: cannot access local variable 'parse_qs'（踩过一次）。
        # ---------------- 正射影像（GeoTIFF）----------------
        #
        # 三条接口 + 一条瓦片服务，实现思路是 ArcGIS / gdal2tiles 那套：
        # 一次性把各层级切成 256×256 PNG 放磁盘（/api/ortho/build），
        # 之后缩放平移就是读文件（/api/ortho/tile 命中磁盘 0.0~0.2 ms）。
        #
        # 还没建完也能看：tile 接口在磁盘没有时现算并顺手落盘。
        if path in ("/api/ortho/list", "/api/ortho/build", "/api/ortho/job",
                    "/api/ortho/tile"):

            import ortho
            import ortho_api

            def _ortho_project():
                q = parse_qs(parsed.query)
                name = (q.get("name") or [""])[0]
                if not name:
                    raise ValueError("缺少项目名。")
                project = load_project(name)
                folders = [item.get("path") for item in (project.get("folders") or [])
                           if item.get("path")]
                return name, project, folders

            try:
                if path == "/api/ortho/list":
                    name, project, folders = _ortho_project()
                    items = ortho_api.discover(PROJECT_DIR / name, folders, name)
                    json_response(self, {"success": True, "orthos": items,
                                         "count": len(items)})
                    return

                if path == "/api/ortho/build":
                    name, project, folders = _ortho_project()
                    q = parse_qs(parsed.query)
                    raw = (q.get("path") or [""])[0]
                    force = (q.get("force") or ["0"])[0] in ("1", "true", "yes")
                    if not raw:
                        raise ValueError("缺少 path。")
                    real = ortho_api.find_by_path(PROJECT_DIR / name, folders, raw)
                    if not real:
                        raise ValueError("这个文件不在项目的任何数据文件夹里，或者不是 .tif。")
                    job = ortho_api.start_build(PROJECT_DIR / name, real, force=force)
                    json_response(self, {"success": True, "job": job})
                    return

                if path == "/api/ortho/job":
                    name, project, folders = _ortho_project()
                    q = parse_qs(parsed.query)
                    raw = (q.get("path") or [""])[0]
                    if raw:
                        real = ortho_api.find_by_path(PROJECT_DIR / name, folders, raw)
                        if not real:
                            raise ValueError("这个文件不在项目的任何数据文件夹里。")
                        job = ortho_api.job_snapshot(
                            ortho_api._key(PROJECT_DIR / name, real))
                        json_response(self, {"success": True, "job": job})
                    else:
                        with ortho_api._JOB_LOCK:
                            jobs = [dict(j) for j in ortho_api._JOBS.values()]
                        json_response(self, {"success": True, "jobs": jobs})
                    return

                # ---- 瓦片 ----
                name, project, folders = _ortho_project()
                q = parse_qs(parsed.query)
                raw = (q.get("path") or [""])[0]
                if not raw:
                    raise ValueError("缺少 path。")
                real = ortho_api.find_by_path(PROJECT_DIR / name, folders, raw)
                if not real:
                    raise ValueError("这个文件不在项目的任何数据文件夹里，或者不是 .tif。")
                try:
                    z = int((q.get("z") or [""])[0])
                    x = int((q.get("x") or [""])[0])
                    y = int((q.get("y") or [""])[0])
                except (TypeError, ValueError):
                    raise ValueError("z/x/y 必须是整数。")

                data, source = ortho_api.tile_bytes(PROJECT_DIR / name, real, z, x, y)

                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                # 已经落盘的可以长缓存；现算的短缓存，避免建完金字塔后还看旧的
                self.send_header("Cache-Control",
                                 "private, max-age=%s" % ("86400" if source == "cache" else "60"))
                self.send_header("X-Ortho-Source", source)
                self.end_headers()
                self._write_body(data)

            except Exception as e:
                message = str(e).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(message)))
                self.end_headers()
                self._write_body(message)

            return

        # ---------------- 全景照片的"透视封面" ----------------
        #
        # 为什么需要：全景照片是 2:1 等距柱状图，直接缩成小图看就是**一条压扁的
        # 弧带**，完全看不出画面里有什么。而按某个方向投成透视小图，
        # 就和人点开 360 查看器看到的一样。
        #
        # 数学直接复用 pano360.perspectives_from_equirect。
        #
        # **两边的 `fov` 语义不一样，必须换算**（这个坑是靠"图对图"比出来的，
        # 不是看代码能看出来的）：
        #   播放器 draw():  ny = ±tan(fov/2)                  -> fov 是**垂直**视场角
        #   perspectives_from_equirect: dx = ±out_w/2, dz=f   -> fov 是**水平**视场角
        # 直接把 75 传进去，封面会比查看器"更近"：实测两张图的归一化互相关只有 0.372。
        # 按输出宽高比把垂直 fov 换成水平 fov 之后 -> 0.625；
        # 再让画幅比与查看器一致（w=760&h=520）-> **0.9996**，即同一个画面。
        if path == "/photo/pano":

            try:
                # 在参数解析之前就 import：下面 _num("pitch", pano360.DEFAULT_COVER_PITCH)
                # 要用这个常量，放晚了会 NameError。
                import pano360

                q = parse_qs(parsed.query)
                raw = (q.get("path") or [""])[0]
                if not raw:
                    raise ValueError("缺少 path。")

                def _num(key, default, lo, hi):
                    try:
                        v = float((q.get(key) or [default])[0])
                    except (TypeError, ValueError):
                        v = float(default)
                    return max(lo, min(hi, v))

                want = int(_num("w", 720, 160, 1600))
                # 高度可选：不给就按 16:9。照片卡片不是 16:9，调用方可以传 h
                # 直接要一个贴合卡片比例的封面，省掉被裁掉的上下部分。
                # 注意 `h` 只影响**画幅**，不改变视场语义：`fov` 始终是垂直视场角
                # （与播放器里的含义一致），所以改 h 不会让封面"变焦"。
                want_h = (q.get("h") or [""])[0]
                if want_h:
                    want_h = int(_num("h", 0, 120, 1600))
                    if want_h < 60:
                        want_h = None
                else:
                    want_h = None
                yaw = _num("yaw", 0.0, -180.0, 180.0)
                # 默认俯仰角来自 pano360 的常量，必须与前端 openPanoPhoto() 一致
                pitch = _num("pitch", pano360.DEFAULT_COVER_PITCH, -89.0, 89.0)
                fov = _num("fov", 75.0, 20.0, 120.0)

                candidate = Path(raw).resolve()
                if candidate.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                    raise ValueError("只支持 jpg/png。")

                allowed = False
                for project_file in PROJECT_DIR.glob("*/project.json"):
                    try:
                        data = json.loads(project_file.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        continue
                    for item in data.get("folders") or []:
                        folder = item.get("path")
                        if not folder:
                            continue
                        try:
                            candidate.relative_to(Path(folder).resolve())
                            allowed = True
                            break
                        except ValueError:
                            pass
                    if allowed:
                        break
                if not allowed:
                    raise ValueError("这个路径不在任何项目文件夹里。")

                import hashlib
                from PIL import Image

                stat = candidate.stat()
                key = hashlib.sha1((
                    "%s|%d|%d|%d|%s|%.2f|%.2f|%.2f" % (
                        candidate, stat.st_size, int(stat.st_mtime),
                        want, want_h or 0, yaw, pitch, fov)
                ).encode("utf-8")).hexdigest()[:20]
                cache_dir = TEST_DIR / "_cache" / "pano"
                cache_dir.mkdir(parents=True, exist_ok=True)
                cached = cache_dir / ("%s.jpg" % key)

                if not cached.is_file():
                    import numpy as np

                    Image.MAX_IMAGE_PIXELS = None
                    with Image.open(candidate) as im:
                        # 等距柱状源只需要 2048 宽就够投一张 720 的小图：
                        # draft() 让 libjpeg 直接低分辨率解码，14400 宽也不用全解。
                        try:
                            im.draft("RGB", (2048, 1024))
                        except Exception:
                            pass
                        im = im.convert("RGB")
                        if im.width > 2048:
                            ratio = 2048 / float(im.width)
                            im = im.resize((2048, max(1, int(round(im.height * ratio)))),
                                           Image.LANCZOS)
                        equi = np.asarray(im)

                    out_h = want_h if want_h else max(1, int(round(want * 9 / 16.0)))
                    # **fov 的语义两边不一样，必须换算**（踩过，靠图对图比出来的）：
                    #   播放器 draw():  ny = ±tan(fov/2)            -> fov 是**垂直**视场角
                    #   perspectives_from_equirect: dx = ±out_w/2, dz=f -> fov 是**水平**视场角
                    # 直接把同一个 75 传进去，服务端封面会比查看器"更近"
                    # （水平 75° vs 实际 96°），两张图相关系数只有 0.372。
                    # 这里按输出宽高比把"垂直 fov"换成"水平 fov"，两者才看同一个画面。
                    import math as _math
                    fov_h = 2.0 * _math.degrees(_math.atan(
                        _math.tan(_math.radians(fov) / 2.0) * (want / float(out_h))))
                    fov_h = max(1.0, min(170.0, fov_h))

                    persp = pano360.perspectives_from_equirect(
                        equi, yaw, pitch, fov_deg=fov_h, out_w=want, out_h=out_h)
                    tmp = cached.with_suffix(".jpg.tmp")
                    Image.fromarray(persp, "RGB").save(
                        tmp, format="JPEG", quality=85, optimize=True)
                    tmp.replace(cached)

                payload = cached.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "private, max-age=86400")
                self.end_headers()
                self._write_body(payload)

            except Exception as e:
                message = str(e).encode("utf-8")
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(message)))
                self.end_headers()
                self._write_body(message)

            return

        # ---------------- 照片缩略图 ----------------
        #
        # 为什么必须有：`/photo` 返回的是**原图字节**。普通照片 3~4 MB 还能忍，
        # 但全景照片是 14400×7200、单张 **34 MB**（实测那批 150 张共 4.85 GB）——
        # 照片卡片里放一张"缩略图"就要下 34 MB，等于把整批数据拉一遍。
        #
        # 这里按宽度降采样并**落盘缓存**，第一次 0.1~0.4 s，之后就是读文件。
        # JPEG 解码用 PIL 的 draft()：它能让 libjpeg 直接按 1/2、1/4、1/8 解码，
        # 对 14400×7200 这种大图比"解码整幅再缩"快一个数量级。
        #
        # 缓存目录**不能放 Project/ 下** —— 项目列表是扫 Project/*/project.json，
        # 放进去会多出一个把缓存目录当项目的空条目（我一开始就放错了）。
        # 放 TEST_DIR/_cache/thumbs，`.gitignore` 已有 `_*` 与 `**/.thumbs/` 覆盖。
        if path == "/photo/thumb":

            try:
                q = parse_qs(parsed.query)
                raw = (q.get("path") or [""])[0]
                if not raw:
                    raise ValueError("缺少 path。")
                try:
                    want = int((q.get("w") or ["640"])[0])
                except (TypeError, ValueError):
                    want = 640
                want = max(64, min(1600, want))

                candidate = Path(raw).resolve()
                if candidate.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                    raise ValueError("只支持 jpg/png。")

                # 与 /photo 同一套"必须落在某个项目文件夹内"的校验，
                # 否则这里就成了任意文件读取的口子。
                allowed = False
                for project_file in PROJECT_DIR.glob("*/project.json"):
                    try:
                        data = json.loads(project_file.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        continue
                    for item in data.get("folders") or []:
                        folder = item.get("path")
                        if not folder:
                            continue
                        try:
                            candidate.relative_to(Path(folder).resolve())
                            allowed = True
                            break
                        except ValueError:
                            pass
                    if allowed:
                        break
                if not allowed:
                    raise ValueError("这个路径不在任何项目文件夹里。")

                import hashlib
                from PIL import Image

                stat = candidate.stat()
                key = hashlib.sha1(
                    ("%s|%d|%d|%d" % (candidate, stat.st_size, int(stat.st_mtime), want)).encode("utf-8")
                ).hexdigest()[:20]
                cache_dir = TEST_DIR / "_cache" / "thumbs"
                cache_dir.mkdir(parents=True, exist_ok=True)
                cached = cache_dir / ("%s_%d.jpg" % (key, want))

                if not cached.is_file():
                    Image.MAX_IMAGE_PIXELS = None
                    with Image.open(candidate) as im:
                        # draft() 让 libjpeg 直接低分辨率解码（大图的关键优化）
                        try:
                            im.draft("RGB", (want, max(1, want // 2)))
                        except Exception:
                            pass
                        im = im.convert("RGB")
                        # 只缩不放：本来就比 want 窄的图保持原尺寸
                        if im.width > want:
                            ratio = want / float(im.width)
                            im = im.resize((want, max(1, int(round(im.height * ratio)))),
                                           Image.LANCZOS)
                        tmp = cached.with_suffix(".jpg.tmp")
                        im.save(tmp, format="JPEG", quality=82, optimize=True)
                        tmp.replace(cached)

                payload = cached.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "private, max-age=86400")
                self.end_headers()
                self._write_body(payload)

            except Exception as e:
                message = str(e).encode("utf-8")
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(message)))
                self.end_headers()
                self._write_body(message)

            return

        if path == "/photo":

            try:
                raw = (parse_qs(parsed.query).get("path") or [""])[0]

                if not raw:
                    raise ValueError("缺少 path。")

                candidate = Path(raw).resolve()

                if candidate.suffix.lower() not in (".jpg", ".jpeg", ".png", ".dng"):
                    raise ValueError("只支持图片。")

                allowed = False

                for project_file in PROJECT_DIR.glob("*/project.json"):
                    try:
                        data = json.loads(project_file.read_text(encoding="utf-8"))

                    except (OSError, ValueError):
                        continue

                    for item in data.get("folders") or []:
                        folder = item.get("path")

                        if not folder:
                            continue

                        try:
                            candidate.relative_to(Path(folder).resolve())
                            allowed = True
                            break

                        except ValueError:
                            pass

                    if allowed:
                        break

                if not allowed:
                    raise ValueError("这个路径不在任何项目文件夹里。")

                payload = candidate.read_bytes()
                content_type = {
                    ".png": "image/png",
                    ".dng": "image/x-adobe-dng",
                }.get(candidate.suffix.lower(), "image/jpeg")

                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "private, max-age=3600")
                self.end_headers()
                self._write_body(payload)

            except Exception as e:
                # 状态行与 header 只能是 ASCII（放中文会让客户端收到畸形响应、直接断开），
                # 中文说明一律放 body。
                message = str(e).encode("utf-8")

                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(message)))
                self.end_headers()
                self._write_body(message)

            return

        # 照片定位：把项目里各架次文件夹的 JPG 读出来、算中心点、按目标点合并成组。
        # 前端靠它画「照片图层」和地图下方那条展示区。
        # 同样不要在函数里重复 import parse_qs（原因见上面 /photo 那段注释）。
        if path == "/api/project/photos":

            try:
                name = (parse_qs(parsed.query).get("name") or [""])[0]

                if not name:
                    raise ValueError("缺少项目名。")

                project = load_project(name)
                folders = [item.get("path") for item in (project.get("folders") or []) if item.get("path")]

                import photo_meta

                json_response(self, photo_meta.build_photo_payload(folders))

            except Exception as e:
                json_response(self, {"error": str(e)}, 400)

            return

        if path.startswith("/vendor/"):

            name = path[len("/vendor/"):]

            # 允许单层文件名，或一层子目录（Leaflet 的 CSS 会引用 images/xxx.png）。
            # 其余一律挡掉，防路径穿越。
            if (
                not name
                or ".." in name
                or "\\" in name
                or not re.fullmatch(r"[A-Za-z0-9_.\-]+(/[A-Za-z0-9_.\-]+)?", name)
            ):
                self.send_error(404, "Not found")
                return

            target = None

            # 数据目录里的 vendor 优先（用户可自行替换），其次包内自带的那份
            for root in (VENDOR_DIR, VENDOR_DIR_BUNDLED):

                candidate = root / name

                if candidate.is_file():
                    target = candidate
                    break

            if target is None:
                # 前端检测到本地缺失会自动退回 CDN，所以这里安静地 404
                self.send_error(404, "Not found")
                return

            try:
                data = target.read_bytes()

            except OSError:
                self.send_error(500, "Read failed")
                return

            self.send_response(200)
            self.send_header(
                "Content-Type",
                VENDOR_CONTENT_TYPES.get(
                    target.suffix.lower(),
                    "application/octet-stream"
                )
            )
            self.send_header("Cache-Control", "public, max-age=604800")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self._write_body(data)
            return

        # ----------------------------------------------------
        # 标记点报告的截图与 docx（report_cache/ 下，只允许单层文件名）
        # ----------------------------------------------------

        if path.startswith("/report/"):

            try:
                target = report_file(path[len("/report/"):])

            except ValueError:
                self.send_error(404, "Not found")
                return

            if not target.is_file():
                self.send_error(404, "Not found")
                return

            try:
                data = target.read_bytes()

            except OSError:
                self.send_error(500, "Read failed")
                return

            content_type = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".docx":
                    "application/vnd.openxmlformats-officedocument"
                    ".wordprocessingml.document",
            }.get(target.suffix.lower(), "application/octet-stream")

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self._write_body(data)
            return

        # ----------------------------------------------------
        # 前端启动配置（有没有天地图 key、报告依赖齐不齐）
        # ----------------------------------------------------

        if path == "/api/config":

            json_response(
                self,
                {
                    "tianditu": bool(get_tianditu_key()),
                    "report": report_capabilities(),
                }
            )

            return

        # ----------------------------------------------------
        # 视场覆盖：清单 / 点查询 / 热力图 / 矢量导出
        # ----------------------------------------------------
        # 这几个接口都把重活塞进 coverage_api，project_manager 只做参数校验与转发。

        # ----------------------------------------------------
        # 360 全景：清单 / 元信息 / 渲染等距柱状（预览器用）
        # ----------------------------------------------------
        # Avata 360 的 .OSV 是两路半球鱼眼、十几 GB，浏览器没法直接放。
        # 这里按需转成等距柱状全景图，前端拖拽看任意方向。见 pano360_service.py。

        if path == "/api/pano360/list":
            try:
                params = parse_qs(parsed.query)
                name = (params.get("name") or [""])[0]
                if not name:
                    raise ValueError("Missing project name.")
                import pano360_service

                project = load_project(name)
                folders = [item.get("path") for item in (project.get("folders") or [])
                           if item.get("path")]
                items = pano360_service.find_360_videos(folders)
                for it in items:
                    srt = Path(it["srt"]) if it["srt"] else None
                    it["info"] = pano360_service.video_info(Path(folders[it["folder_index"]]).expanduser()
                                                            / it["relative_path"], srt)
                json_response(self, {"project": name, "count": len(items), "items": items})
            except Exception as e:
                json_response(self, {"error": str(e)}, 400)
            return

        if path == "/api/pano360/frame":
            # 渲染一张等距柱状全景（JPEG）。参数：name / rel / t / ew
            try:
                params = parse_qs(parsed.query)
                name = (params.get("name") or [""])[0]
                rel = (params.get("rel") or [""])[0]
                t = float((params.get("t") or ["0"])[0])
                ew = int((params.get("ew") or ["2048"])[0])
                if not name or not rel:
                    raise ValueError("Missing name/rel.")
                if not (512 <= ew <= 4096):
                    raise ValueError("ew out of range (512..4096).")
                import pano360_service

                project = load_project(name)
                folders = [Path(item.get("path")).expanduser()
                           for item in (project.get("folders") or []) if item.get("path")]
                target = None
                for f in folders:
                    cand = (f / rel).resolve()
                    if cand.is_file() and f.resolve() in cand.parents:
                        target = cand
                        break
                if target is None or target.suffix.lower() != ".osv":
                    raise ValueError("That .OSV is not inside this project's folders.")

                data, hit = pano360_service.render_cached(
                    target, pano360_service.cache_dir(target.parent), t, ew=ew)
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("X-Pano-Cache", "hit" if hit else "miss")
                self.end_headers()
                self._write_body(data)
            except Exception as e:
                json_response(self, {"error": str(e)}, 400)
            return

        if path == "/api/pano360/frames":
            # 360 专用检索：哪些时刻拍到了这一点（圆环判据，不需要云台姿态）
            try:
                params = parse_qs(parsed.query)
                name = (params.get("name") or [""])[0]
                lat = (params.get("lat") or [""])[0]
                lng = (params.get("lng") or [""])[0]
                limit = int((params.get("limit") or ["60"])[0])
                mode = (params.get("mode") or ["passes"])[0].strip().lower()
                if not name or lat == "" or lng == "":
                    raise ValueError("Missing name/lat/lng.")
                import pano360_service
                import pano360_coverage

                if mode not in pano360_coverage.FIND_MODES:
                    mode = "passes"
                json_response(self, pano360_service.find_360_frames(
                    name, float(lat), float(lng), limit=limit, mode=mode))
            except Exception as e:
                json_response(self, {"error": str(e)}, 400)
            return

        if path == "/api/pano360/look":
            # 从 360 全景裁一张**透视小图**（检索卡片缩略图 / 预览器取景用）
            try:
                params = parse_qs(parsed.query)
                name = (params.get("name") or [""])[0]
                rel = (params.get("rel") or [""])[0]
                t = float((params.get("t") or ["0"])[0])
                yaw = float((params.get("yaw") or ["0"])[0])
                pitch = float((params.get("pitch") or ["0"])[0])
                fov = float((params.get("fov") or ["75"])[0])
                w = int((params.get("w") or ["480"])[0])
                if not name or not rel:
                    raise ValueError("Missing name/rel.")
                if not (160 <= w <= 1600):
                    raise ValueError("w out of range (160..1600).")
                if not (20.0 <= fov <= 150.0):
                    raise ValueError("fov out of range (20..150).")
                import pano360_service

                project = load_project(name)
                folders = [Path(item.get("path")).expanduser()
                           for item in (project.get("folders") or []) if item.get("path")]
                target = None
                for f in folders:
                    cand = (f / rel).resolve()
                    if cand.is_file() and f.resolve() in cand.parents:
                        target = cand
                        break
                if target is None or target.suffix.lower() != ".osv":
                    raise ValueError("That .OSV is not inside this project's folders.")

                data, hit = pano360_service.render_perspective(
                    target, pano360_service.cache_dir(target.parent), t,
                    yaw, pitch, fov_deg=fov, out_w=w)
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("X-Pano-Cache", "hit" if hit else "miss")
                self.end_headers()
                self._write_body(data)
            except Exception as e:
                json_response(self, {"error": str(e)}, 400)
            return

        if path == "/pano":
            # 流式送出**转码后的等距柱状 mp4**（支持 Range，浏览器 <video> 才能拖进度）。
            # 用法：/pano?name=<项目>&rel=<素材相对路径>&tier=full
            try:
                params = parse_qs(parsed.query)
                name = (params.get("name") or [""])[0]
                rel = (params.get("rel") or [""])[0]
                tier = (params.get("tier") or ["full"])[0]
                if not name or not rel:
                    raise ValueError("Missing name/rel.")
                import pano360_transcode
                if tier not in pano360_transcode.QUALITY_TIERS:
                    raise ValueError("Unknown tier: %s" % tier)
                target = _resolve_project_media(name, rel, ".osv")
                out = target.parent / "pano_cache" / ("%s_%s.mp4" % (target.stem, tier))
                if not pano360_transcode.is_valid_output(out):
                    raise ValueError("Not transcoded yet — call /api/pano360/transcode first.")
                send_file_range(self, out, content_type="video/mp4",
                                cache_control="public, max-age=86400")
            except Exception as e:
                json_response(self, {"error": str(e)}, 400)
            return

        if path == "/api/pano360/transcode":
            #
            # 为什么要转：`.OSV` 是两路 4K HEVC Main10 鱼眼，浏览器解不了，
            # 而且就算能解也拿到的是两张圆图 —— 重投影必须有人做。
            # 转一次之后前端就是普通 <video> 播放 + canvas 拖拽转向。
            #
            # **异步**：转码是分钟级（79 秒素材约 7 分钟），同步会让前端干等、
            # 还可能被浏览器/代理超时掐掉。所以立刻返回 job_id，
            # 进度用 `/api/pano360/job?id=` 轮询。
            # 已转过就直接返回 cached（除非 force=1）。
            try:
                params = parse_qs(parsed.query)
                name = (params.get("name") or [""])[0]
                rel = (params.get("rel") or [""])[0]
                tier = (params.get("tier") or ["full"])[0]
                force = (params.get("force") or ["0"])[0] in ("1", "true", "yes")
                if not name or not rel:
                    raise ValueError("Missing name/rel.")
                # 在**用到处**导入：pano360_transcode 会 import project_manager，
                # 顶层导入会绕成环。这与本文件里 pano360_service 的写法一致。
                import pano360_transcode
                if tier not in pano360_transcode.QUALITY_TIERS:
                    raise ValueError("Unknown tier: %s" % tier)

                target = _resolve_project_media(name, rel, ".osv")
                out_dir = target.parent / "pano_cache"
                out = out_dir / ("%s_%s.mp4" % (target.stem, tier))
                rel_out = str(out.relative_to(target.parent)).replace("\\", "/")

                if pano360_transcode.is_valid_output(out) and not force:
                    json_response(self, {
                        "success": True, "cached": True, "job": None,
                        "path": rel_out, "size": out.stat().st_size, "tier": tier,
                    })
                    return

                jid = pano360_transcode.submit(target, out, tier=tier, force=force)
                json_response(self, {
                    "success": True, "cached": False, "job": jid,
                    "path": rel_out, "tier": tier,
                })
            except Exception as e:
                json_response(self, {"error": str(e)}, 400)
            return

        if path == "/api/pano360/job":
            # 查转码任务进度。省略 id 时返回全部任务（前端用来显示"后台在转几个"）。
            try:
                params = parse_qs(parsed.query)
                jid = (params.get("id") or [""])[0]
                import pano360_transcode
                if jid:
                    j = pano360_transcode.job(jid)
                    if not j:
                        raise ValueError("Unknown job: %s" % jid)
                    json_response(self, {"success": True, "job": j})
                else:
                    json_response(self, {
                        "success": True,
                        "jobs": pano360_transcode.all_jobs(),
                        "active": len(pano360_transcode.active_jobs()),
                    })
            except Exception as e:
                json_response(self, {"error": str(e)}, 400)
            return

        if path == "/api/pano360/precache":
            # **批量预转**：把一个项目里所有 `.OSV` 排进队列。
            # 用户说过「不怕预加载和导入的过程中生成文件」——
            # 导入后跑一次，之后点开任何 360 素材都是秒开。
            try:
                params = parse_qs(parsed.query)
                name = (params.get("name") or [""])[0]
                tier = (params.get("tier") or ["full"])[0]
                force = (params.get("force") or ["0"])[0] in ("1", "true", "yes")
                if not name:
                    raise ValueError("Missing name.")
                import pano360_transcode
                if tier not in pano360_transcode.QUALITY_TIERS:
                    raise ValueError("Unknown tier: %s" % tier)

                queued, already = queue_pano_precache(name, tier=tier, force=force)
                json_response(self, {
                    "success": True, "queued": len(queued), "already_done": already,
                    "jobs": queued, "tier": tier,
                })
            except Exception as e:
                json_response(self, {"error": str(e)}, 400)
            return

        if path == "/api/project/sync-check":
            # 视频时长 vs 航迹/SRT 时长：发现不同步就报出来，让用户重生成
            try:
                params = parse_qs(parsed.query)
                name = (params.get("name") or [""])[0]
                if not name:
                    raise ValueError("Missing name.")
                tol = float((params.get("tolerance") or [""])[0] or
                            SYNC_TOLERANCE_SECONDS)
                json_response(self, check_project_sync(name, tolerance=tol))
            except Exception as e:
                json_response(self, {"error": str(e)}, 400)
            return

        if path == "/api/project/sync-fix":
            # 就地重生成 SRT + 航迹，并清掉按旧时间轴生成的缓存
            try:
                params = parse_qs(parsed.query)
                name = (params.get("name") or [""])[0]
                fi = int((params.get("folder_index") or ["-1"])[0])
                rel = (params.get("relative_path") or [""])[0]
                if not name or fi < 0 or not rel:
                    raise ValueError("Missing name/folder_index/relative_path.")
                json_response(self, resync_existing_files(name, fi, rel))
            except Exception as e:
                json_response(self, {"error": str(e)}, 400)
            return

        if path == "/api/project/coverage/list":

            try:
                params = parse_qs(parsed.query)
                name = (params.get("name") or [""])[0]

                if not name:
                    raise ValueError("Missing project name.")

                import coverage_api

                project = load_project(name)
                folders = [
                    item.get("path")
                    for item in (project.get("folders") or [])
                    if item.get("path")
                ]

                json_response(self, coverage_api.list_coverage(name, folders))

            except Exception as e:
                json_response(self, {"error": str(e)}, 400)

            return

        if path == "/api/project/coverage/query":

            try:
                params = parse_qs(parsed.query)
                name = (params.get("name") or [""])[0]
                lat = (params.get("lat") or [""])[0]
                lng = (params.get("lng") or [""])[0]
                npz = (params.get("npz") or [""])[0]

                if not name:
                    raise ValueError("Missing project name.")

                if lat == "" or lng == "":
                    raise ValueError("Missing lat/lng.")

                import coverage_api

                target = self.resolve_coverage_npz(name, npz)

                json_response(self, coverage_api.query_point(
                    name, target, float(lat), float(lng)))

            except Exception as e:
                json_response(self, {"error": str(e)}, 400)

            return

        # 「这个位置被哪些画面拍到过」—— 跨架次检索
        if path == "/api/project/coverage/frames":

            try:
                params = parse_qs(parsed.query)
                name = (params.get("name") or [""])[0]
                lat = (params.get("lat") or [""])[0]
                lng = (params.get("lng") or [""])[0]
                limit = (params.get("limit") or ["60"])[0]
                max_gsd = (params.get("max_gsd") or [""])[0]
                only = (params.get("srt") or [""])[0]
                import coverage_api

                # 检索档位：best=只要最清晰的 1 张；passes=每个独立趟次 1 张（默认）；
                # angles=每种视角 1 张（方位/俯角接近的合并）—— 后者是为**遮挡**准备的：
                # 最清晰的那张可能正好被树挡住，换个方向才看得见。
                mode = (params.get("mode") or ["passes"])[0].strip().lower()
                if mode not in coverage_api.FIND_MODES:
                    mode = "passes"

                # 边距内缩：目标必须落在画面内缩这个比例的范围内（可调选项）。
                # 缺省用后端的常量；传了就用传的（find_frames 内部会夹到合法范围）。
                # 注意：**不能**用 `if inset:` 判空 —— "0" 是合法值（= 不限制）。
                inset_raw = (params.get("inset") or [""])[0].strip()
                frame_inset = None
                if inset_raw != "":
                    try:
                        frame_inset = float(inset_raw)
                    except ValueError:
                        raise ValueError("inset must be a number (fraction, e.g. 0.25).")

                if not name:
                    raise ValueError("Missing project name.")

                if lat == "" or lng == "":
                    raise ValueError("Missing lat/lng.")

                import coverage_api

                srt_path = None
                if only:
                    # 限定单个架次时也要过一遍归属校验，别让这个参数变成任意文件读
                    project = load_project(name)
                    folders = [
                        Path(item.get("path")).resolve()
                        for item in (project.get("folders") or [])
                        if item.get("path")
                    ]
                    cand = Path(only).resolve()
                    if not any(f == cand.parent or f in cand.parents for f in folders):
                        raise ValueError("That SRT is not inside this project's folders.")
                    srt_path = cand

                json_response(self, coverage_api.find_frames(
                    name, float(lat), float(lng),
                    limit=int(limit),
                    max_gsd=float(max_gsd) if max_gsd else None,
                    srt_path=srt_path,
                    mode=mode,
                    frame_inset=frame_inset,
                ))

            except Exception as e:
                json_response(self, {"error": str(e)}, 400)

            return

        # 检索结果的缩略图（抽帧带磁盘缓存）
        if path == "/api/project/coverage/thumb":

            try:
                params = parse_qs(parsed.query)
                name = (params.get("name") or [""])[0]
                folder_index = (params.get("folder_index") or [""])[0]
                rel = (params.get("path") or [""])[0]
                t = (params.get("t") or [""])[0]
                width = (params.get("w") or ["480"])[0]

                if not name:
                    raise ValueError("Missing project name.")

                if not rel or t == "":
                    raise ValueError("Missing path/time.")

                import coverage_api

                video = resolve_project_video(name, folder_index, rel)
                thumb = coverage_api.make_thumbnail(
                    video, float(t), width=int(width))
                data = thumb.read_bytes()

                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                # 缩略图内容只取决于 (视频, 时间)，可以放心缓存
                self.send_header("Cache-Control", "private, max-age=86400")
                self.end_headers()
                self._write_body(data)

            except Exception as e:
                json_response(self, {"error": str(e)}, 400)

            return

        # 取回导出的 GeoJSON 文件（用户可能想直接从浏览器下载或另存）
        if path == "/api/project/coverage/file":
            try:
                params = parse_qs(parsed.query)
                name = (params.get("name") or [""])[0]
                fn = (params.get("file") or [""])[0]

                if not name:
                    raise ValueError("Missing project name.")

                if not fn:
                    raise ValueError("Missing file name.")

                import coverage_api

                cdir = coverage_api.coverage_dir(name).resolve()
                target = (cdir / Path(fn).name).resolve()

                if cdir not in target.parents:
                    raise ValueError("File must live under the project coverage folder.")

                if target.suffix.lower() not in (".geojson", ".json", ".png"):
                    raise ValueError("Only .geojson / .json / .png can be served.")

                if not target.is_file():
                    raise FileNotFoundError("File not found.")

                ctype = {
                    ".geojson": "application/geo+json; charset=utf-8",
                    ".json": "application/json; charset=utf-8",
                    ".png": "image/png",
                }[target.suffix.lower()]

                data = target.read_bytes()

                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header(
                    "Content-Disposition",
                    f'inline; filename="{target.name}"'
                )
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self._write_body(data)

            except Exception as e:
                json_response(self, {"error": str(e)}, 400)

            return

        if path == "/api/project/coverage/heatmap":
            try:
                params = parse_qs(parsed.query)
                name = (params.get("name") or [""])[0]
                npz = (params.get("npz") or [""])[0]
                metric = (params.get("metric") or ["count"])[0]
                gsd_max = (params.get("gsd_max") or [""])[0]
                overlay = (params.get("overlay") or [""])[0] in ("1", "true", "yes")
                threshold = (params.get("threshold") or [""])[0]

                if not name:
                    raise ValueError("Missing project name.")

                import coverage_api

                target = self.resolve_coverage_npz(name, npz)
                kw = {"metric": metric}
                if gsd_max:
                    kw["gsd_max"] = float(gsd_max)

                if overlay:
                    th = int(threshold) if threshold else int(
                        (params.get("overlay_threshold") or ["1"])[0])
                    geo = coverage_api.export_geojson(
                        name, target, metric=metric, threshold=th)
                    data = coverage_api.render_overlay_png(target, geo, **kw)
                else:
                    data = coverage_api.render_heatmap_png(target, **kw)

                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                # 本机工具，允许缓存但每次校验；重建后 npz 的 mtime 会变，
                # 所以再加一层 no-store 免得看到旧图。
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self._write_body(data)

            except Exception as e:
                json_response(self, {"error": str(e)}, 400)

            return

        # ----------------------------------------------------
        # 视频文件流（支持 HTTP Range）
        # ----------------------------------------------------

        if path == "/api/project/video":

            try:

                params = parse_qs(parsed.query)

                project_name = params.get("name", [""])[0]
                folder_index = params.get("folder_index", [""])[0]
                relative_path = params.get("path", [""])[0]

                if not project_name:
                    raise ValueError("Missing project name.")

                if not relative_path:
                    raise ValueError("Missing video relative path.")

                stream_project_video(
                    self,
                    project_name,
                    folder_index,
                    relative_path
                )

            except Exception as e:

                json_response(
                    self,
                    {"error": str(e)},
                    400
                )

            return

        # ----------------------------------------------------
        # 地名搜索（天地图代理）
        # ----------------------------------------------------

        if path == "/api/geocode":

            try:

                params = parse_qs(parsed.query)

                keyword = params.get("q", [""])[0]

                json_response(
                    self,
                    geocode_place(keyword)
                )

            except Exception as e:

                json_response(
                    self,
                    {"error": str(e)},
                    400
                )

            return

        # ----------------------------------------------------
        # 逆地理编码：经纬度 -> 镇村级位置（报告里的「所在位置」）
        # ----------------------------------------------------

        if path == "/api/reverse-geocode":

            try:

                params = parse_qs(parsed.query)

                json_response(
                    self,
                    reverse_geocode_place(
                        params.get("lat", [""])[0],
                        params.get("lng", [""])[0]
                    )
                )

            except Exception as e:

                json_response(
                    self,
                    {"error": str(e)},
                    400
                )

            return

        # ----------------------------------------------------
        # 导出「前后 10 秒」：以当前播放位置为中心，前 5 秒 + 后 5 秒，1080p
        # ----------------------------------------------------

        if path == "/api/project/clip":

            try:

                params = parse_qs(parsed.query)

                project_name = params.get("name", [""])[0]
                folder_index = params.get("folder_index", [""])[0]
                relative_path = params.get("path", [""])[0]

                if not project_name:
                    raise ValueError("Missing project name.")

                if not relative_path:
                    raise ValueError("Missing video relative path.")

                try:
                    center = float(params.get("center", ["0"])[0] or 0)
                except ValueError:
                    center = 0.0

                center = max(0.0, center)

                video_path = resolve_project_video(
                    project_name,
                    folder_index,
                    relative_path
                )

                clip_path, start, seconds = build_clip(video_path, center)

                # 文件名：视频名 + 起止时刻，转发给别人时一眼能看出是哪一段
                # （文件名里不能有冒号，Windows 不允许，所以用点分隔）
                stem = Path(relative_path).stem
                span = (
                    f"{format_seconds_text(start).replace(':', '.')}"
                    f"-{format_seconds_text(start + seconds).replace(':', '.')}"
                )
                download_name = f"{stem}_{span}.mp4"

                send_clip_download(self, clip_path, download_name)

            except Exception as e:

                json_response(
                    self,
                    {"error": str(e)},
                    400
                )

            return

        # ----------------------------------------------------
        # 网页播放代理：按需把点击位置附近的一段转成 H.264
        # ----------------------------------------------------

        if path == "/api/project/proxy":

            try:

                params = parse_qs(parsed.query)

                project_name = params.get("name", [""])[0]
                folder_index = params.get("folder_index", [""])[0]
                relative_path = params.get("path", [""])[0]

                if not project_name:
                    raise ValueError("Missing project name.")

                if not relative_path:
                    raise ValueError("Missing video relative path.")

                try:
                    start_seconds = float(
                        params.get("start", ["0"])[0] or 0
                    )
                except ValueError:
                    start_seconds = 0.0

                try:
                    seconds = float(
                        params.get("duration", [str(PROXY_SECONDS)])[0]
                        or PROXY_SECONDS
                    )
                except ValueError:
                    seconds = float(PROXY_SECONDS)

                seconds = max(5.0, min(seconds, 600.0))
                start_seconds = max(0.0, start_seconds)

                video_path = resolve_project_video(
                    project_name,
                    folder_index,
                    relative_path
                )

                info = probe_video_stream(video_path)
                duration = (info or {}).get("duration") or 0.0

                # 别请求到文件末尾之后，那样会转出空片段
                if duration and start_seconds > duration - 1:
                    start_seconds = max(0.0, duration - seconds)

                proxy_path, _bucket = build_proxy_segment(
                    video_path,
                    start_seconds,
                    seconds
                )

                send_file_range(
                    self,
                    proxy_path,
                    "video/mp4",
                    cache_control="public, max-age=86400"
                )

            except Exception as e:

                json_response(
                    self,
                    {"error": str(e)},
                    400
                )

            return

        # ----------------------------------------------------
        # 视频实时信息（云台朝向/俯仰、焦距、变焦、高度）
        # ----------------------------------------------------

        if path == "/api/project/telemetry":

            try:

                params = parse_qs(parsed.query)

                project_name = params.get("name", [""])[0]
                folder_index = params.get("folder_index", [""])[0]
                relative_path = params.get("path", [""])[0]

                if not project_name:
                    raise ValueError("Missing project name.")

                if not relative_path:
                    raise ValueError("Missing video relative path.")

                video_path = resolve_project_video(
                    project_name,
                    folder_index,
                    relative_path
                )

                srt_path = video_path.with_suffix(".srt")

                if not srt_path.exists():
                    upper = video_path.with_suffix(".SRT")
                    srt_path = upper if upper.exists() else srt_path

                if not srt_path.exists():
                    raise FileNotFoundError(
                        "找不到该视频对应的 SRT 字幕文件，"
                        "无法读取云台与焦距数据。"
                    )

                data = load_srt_telemetry(srt_path)
                data["video"] = video_path.name
                data["srt"] = srt_path.name

                # 顺带告诉前端有没有配对的红外录像（可见光视频才有）
                thermal = sibling_thermal_video(video_path)

                if thermal is not None:
                    data["thermal"] = {
                        "video": thermal.name,
                        "path": sibling_relative_path(
                            relative_path,
                            thermal.suffix
                        ),
                    }

                json_response(self, data)

            except Exception as e:

                json_response(
                    self,
                    {"error": str(e)},
                    400
                )

            return

        if path == "/api/project/list":

            try:

                projects = (
                    get_project_directories()
                )

                json_response(
                    self,
                    {
                        "projects":
                            projects
                    }
                )

            except Exception as e:

                json_response(
                    self,
                    {
                        "error":
                            str(e)
                    },
                    500
                )

            return

        if path == "/api/project/get":

            try:

                params = parse_qs(
                    parsed.query
                )

                project_name = (
                    params.get(
                        "name",
                        [""]
                    )[0]
                )

                if not project_name:
                    raise ValueError(
                        "Missing project name."
                    )

                project = load_project(
                    project_name
                )

                json_response(
                    self,
                    {
                        "project":
                            project
                    }
                )

            except Exception as e:

                json_response(
                    self,
                    {
                        "error":
                            str(e)
                    },
                    400
                )

            return

        if (
            path
            ==
            "/api/project/select-folder"
        ):

            try:

                # 多选：Windows 原生对话框支持一次挑多个文件夹。
                # 返回 paths（全部）并保留 path（第一个）兼容老前端。
                selected_paths = select_folders_windows()

                if not selected_paths:

                    json_response(
                        self,
                        {
                            "cancelled":
                                True
                        }
                    )

                    return

                json_response(
                    self,
                    {
                        "success":
                            True,
                        "paths":
                            selected_paths,
                        "path":
                            selected_paths[0]
                    }
                )

            except Exception as e:

                json_response(
                    self,
                    {
                        "error":
                            f"选择文件夹失败：{e}"
                    },
                    500
                )

            return

        if (
            path
            ==
            "/api/project/select-files"
        ):

            # 只导入挑出来的几个文件：直接返回一个和 scan-folder 同构的
            # folder 对象，前端拿它去调 add-folder 即可。
            try:

                selected_files = (
                    select_files_windows()
                )

                if not selected_files:

                    json_response(
                        self,
                        {
                            "cancelled":
                                True
                        }
                    )

                    return

                json_response(
                    self,
                    {
                        "success":
                            True,
                        "folder":
                            folder_from_files(
                                selected_files
                            )
                    }
                )

            except Exception as e:

                json_response(
                    self,
                    {
                        "error":
                            f"选择文件失败：{e}"
                    },
                    500
                )

            return

        if (
            path
            ==
            "/api/project/scan-folder"
        ):

            try:

                params = parse_qs(
                    parsed.query
                )

                folder_path = (
                    params.get(
                        "path",
                        [""]
                    )[0]
                )

                if not folder_path:
                    raise ValueError(
                        "没有指定文件夹。"
                    )

                result = scan_folder(
                    folder_path
                )

                json_response(
                    self,
                    {
                        "success":
                            True,
                        "folder":
                            result
                    }
                )

            except Exception as e:

                json_response(
                    self,
                    {
                        "error":
                            str(e)
                    },
                    400
                )

            return

        if (
            path
            ==
            "/api/project/media"
        ):

            try:

                params = parse_qs(
                    parsed.query
                )

                project_name = (
                    params.get(
                        "name",
                        [""]
                    )[0]
                )

                if not project_name:
                    raise ValueError(
                        "Missing project name."
                    )

                result = (
                    analyze_project_media(
                        project_name
                    )
                )

                json_response(
                    self,
                    result
                )

            except Exception as e:

                json_response(
                    self,
                    {
                        "error":
                            str(e)
                    },
                    400
                )

            return

        if (
            path
            ==
            "/api/project/video-inspect"
        ):

            try:

                params = parse_qs(
                    parsed.query
                )

                project_name = (
                    params.get(
                        "name",
                        [""]
                    )[0]
                )

                if not project_name:
                    raise ValueError(
                        "Missing project name."
                    )

                result = (
                    inspect_project_videos(
                        project_name
                    )
                )

                json_response(
                    self,
                    result
                )

            except Exception as e:

                json_response(
                    self,
                    {
                        "error":
                            str(e)
                    },
                    400
                )

            return

        if path == "/api/project/geojson-list":

            try:

                params = parse_qs(parsed.query)

                project_name = params.get(
                    "name",
                    [""]
                )[0]

                if not project_name:
                    raise ValueError("Missing project name.")

                result = list_project_geojson(
                    project_name
                )

                json_response(
                    self,
                    result
                )

            except Exception as e:

                json_response(
                    self,
                    {
                        "error": str(e)
                    },
                    400
                )

            return

        if path == "/api/project/geo3d":

            try:

                params = parse_qs(
                    parsed.query
                )

                project_name = params.get(
                    "name",
                    [""]
                )[0]

                folder_index = params.get(
                    "folder_index",
                    [""]
                )[0]

                relative_path = params.get(
                    "path",
                    [""]
                )[0]

                if not project_name:
                    raise ValueError("Missing project name.")

                if not relative_path:
                    raise ValueError("缺少 3D GeoJSON 文件路径。")

                # 3D 页面传入普通 GeoJSON 路径。
                # 后端根据同名 MP4 + SRT 自动生成独立的 .3d.geojson，
                # 不修改原来的 2D GeoJSON。
                source_video_path = str(
                    Path(relative_path).with_suffix(".mp4")
                )

                folder_info = load_project(
                    project_name
                ).get("folders", [])[int(folder_index)]

                result = generate_geo3d_for_video(
                    project_name,
                    folder_info.get("path"),
                    source_video_path
                )

                geo3d_data = load_project_geojson(
                    project_name,
                    folder_index,
                    result["geo3d_relative_path"]
                )

                json_response(
                    self,
                    {
                        "success": True,
                        "geojson": geo3d_data,
                        "result": result
                    }
                )

            except Exception as e:

                json_response(
                    self,
                    {
                        "error": str(e)
                    },
                    400
                )

            return

        if path == "/api/project/geojson":

            try:

                params = parse_qs(parsed.query)

                project_name = params.get(
                    "name",
                    [""]
                )[0]

                folder_index = params.get(
                    "folder_index",
                    [""]
                )[0]

                relative_path = params.get(
                    "path",
                    [""]
                )[0]

                if not project_name:
                    raise ValueError("Missing project name.")

                if not relative_path:
                    raise ValueError("缺少 GeoJSON 文件路径。")

                data = load_project_geojson(
                    project_name,
                    folder_index,
                    relative_path
                )

                json_response(
                    self,
                    {
                        "success": True,
                        "geojson": data
                    }
                )

            except Exception as e:

                json_response(
                    self,
                    {
                        "error": str(e)
                    },
                    400
                )

            return

        self.send_error(
            404,
            "Not Found"
        )

    # ========================================================
    # POST
    # ========================================================

    def do_POST(self):

        path = urlparse(
            self.path
        ).path

        # 切换语言：前端切一次就通知后端，之后**没有请求上下文**的调用
        # （Windows 文件选择对话框）也会跟着用这个语言。
        if path == "/api/lang":
            try:
                data = self.read_json()
                lang = i18n.norm_lang(data.get("lang"))
                settings_store.set_value("lang", lang)
                i18n.set_lang(lang)
                json_response(self, {
                    "ok": True, "lang": lang,
                    "messages": i18n.all_messages(lang),
                })
            except Exception as e:
                json_response(self, {"error": str(e)}, 400)
            return

        # 网页上补填 / 更换天地图 key：客户先开始用、key 后批下来的场景。
        # 只认本机（服务本来就只绑 127.0.0.1）。
        if path == "/api/tianditu/key":

            try:
                data = self.read_json()
                result = save_tianditu_key(data.get("key"), bool(data.get("clear")))

            except Exception as e:
                json_response(self, {"error": str(e)}, 400)
                return

            json_response(self, result)

            return

        # 优雅退出：托盘「退出」菜单、以及托盘不可用时的手动出口都用它。
        # 只认本机（服务本来就只绑 127.0.0.1），并且用 POST 触发，避免被网页
        # 上一个 <img> 之类的 GET 顺手点到。
        if path == "/api/shutdown":

            json_response(self, {"ok": True, "message": "正在退出……"})

            # 不能在处理请求的线程里直接 shutdown（会把自己等死），丢给后台线程
            def _later():
                time.sleep(0.3)
                SHUTDOWN_REQUEST.set()

            threading.Thread(target=_later, daemon=True).start()
            return

        if (
            path
            ==
            "/api/project/create"
        ):

            self.create_project()
            return

        if (
            path
            ==
            "/api/project/add-folder"
        ):

            self.add_folder()
            return

        if (
            path
            ==
            "/api/project/extract-srt"
        ):

            self.extract_srt()
            return

        if (
            path
            ==
            "/api/project/coverage/build"
        ):

            self.build_coverage()
            return

        if (
            path
            ==
            "/api/project/coverage/export"
        ):

            self.export_coverage_geojson()
            return

        if (
            path
            ==
            "/api/project/generate-geojson"
        ):

            self.generate_geojson()
            return

        if (
            path
            ==
            "/api/project/generate-geo3d"
        ):

            self.generate_geo3d()
            return

        if (
            path
            ==
            "/api/project/markers"
        ):

            # 保存标记点：整表覆盖（前端把当前列表整个提交上来）
            self.save_markers()
            return

        if (
            path
            ==
            "/api/snapshot"
        ):

            # 报告用：从原片抽一帧
            self.make_snapshot()
            return

        if (
            path
            ==
            "/api/mapsnapshot"
        ):

            # 报告用：拼一张当前底图的地图截图
            self.make_map_snapshot()
            return

        if (
            path
            ==
            "/api/report/docx"
        ):

            # 报告用：生成 docx
            self.make_report_docx()
            return

        if (
            path
            ==
            "/api/project/delete-geojson"
        ):

            self.delete_geojson()
            return

        if (
            path
            ==
            "/api/project/delete"
        ):

            self.delete_project()
            return

        self.send_error(
            404,
            "Not Found"
        )

    # ========================================================
    # 删除项目
    # ========================================================

    def delete_project(self):
        """把一个项目从项目列表里移除。

        注意语义：删的只是「项目定义」（Project\\<名字>\\project.json），
        也就是项目列表里的那一项。Data 里的原始视频 / SRT / GeoJSON
        一个都不会动 —— 数据文件夹归哪个项目，由用户自己决定，
        删掉项目之后可以再导入到任意项目。
        """

        data = self.read_json()

        project_name = data.get(
            "name"
        )

        error = validate_project_name(
            project_name
        )

        if error:
            json_response(
                self,
                {"error": error},
                400
            )
            return

        root = PROJECT_DIR.resolve()

        target = (
            root / project_name
        ).resolve()

        # 只允许删 Project 的直接子目录：挡住 ../ 之类的路径穿越
        if target.parent != root:
            json_response(
                self,
                {"error": "项目路径不合法。"},
                400
            )
            return

        # 再显式挡一次 Data：删项目绝不涉及数据文件，
        # 万一以后有人改动了 PROJECT_DIR 的定义，这里也能拦住。
        data_root = (TEST_DIR / "Data").resolve()

        if target == data_root or data_root in target.parents:
            json_response(
                self,
                {"error": "拒绝删除 Data 目录下的内容：删除项目不会动数据文件。"},
                400
            )
            return

        if not target.exists():
            json_response(
                self,
                {"error": "项目不存在。"},
                404
            )
            return

        if not target.is_dir():
            json_response(
                self,
                {"error": "项目路径不是文件夹。"},
                400
            )
            return

        shutil.rmtree(target)

        json_response(
            self,
            {"deleted": project_name}
        )

    # ========================================================
    # 创建项目
    # ========================================================

    def create_project(self):

        try:

            data = self.read_json()

            project_name = data.get(
                "name"
            )

            error = validate_project_name(
                project_name
            )

            if error:

                json_response(
                    self,
                    {
                        "error":
                            error
                    },
                    400
                )

                return

            PROJECT_DIR.mkdir(
                parents=True,
                exist_ok=True
            )

            target_name = (
                project_name.casefold()
            )

            for existing in PROJECT_DIR.iterdir():

                if not existing.is_dir():
                    continue

                if (
                    existing.name.casefold()
                    ==
                    target_name
                ):

                    json_response(
                        self,
                        {
                            "error":
                                "项目名称已经存在。"
                        },
                        409
                    )

                    return

            project_path = (
                PROJECT_DIR
                /
                project_name
            )

            project_path.mkdir()

            project_config = {
                "name":
                    project_name,

                "version":
                    1,

                "folders":
                    [],

                "videos":
                    [],

                "photos":
                    [],

                "tracks":
                    []
            }

            config_path = (
                project_path
                /
                "project.json"
            )

            config_path.write_text(
                json.dumps(
                    project_config,
                    ensure_ascii=False,
                    indent=4
                ),
                encoding="utf-8"
            )

            json_response(
                self,
                {
                    "success":
                        True,

                    "name":
                        project_name
                }
            )

        except Exception as e:

            json_response(
                self,
                {
                    "error":
                        f"服务器错误：{e}"
                },
                500
            )

    # ========================================================
    # 加入项目
    # ========================================================

    def add_folder(self):

        try:

            data = self.read_json()

            project_name = data.get(
                "project_name"
            )

            folder_data = data.get(
                "folder"
            )

            if not project_name:
                raise ValueError(
                    "Missing project name."
                )

            if not folder_data:
                raise ValueError(
                    "缺少文件夹数据。"
                )

            project = load_project(
                project_name
            )

            folders = project.setdefault(
                "folders",
                []
            )

            folder_path = folder_data.get(
                "path"
            )

            if not folder_path:
                raise ValueError(
                    "文件夹路径不能为空。"
                )

            normalized_path = str(
                Path(
                    folder_path
                )
                .expanduser()
                .resolve()
            ).casefold()

            for existing in folders:

                existing_path = (
                    existing.get(
                        "path",
                        ""
                    )
                )

                try:

                    existing_normalized = str(
                        Path(
                            existing_path
                        )
                        .expanduser()
                        .resolve()
                    ).casefold()

                except Exception:

                    existing_normalized = (
                        existing_path.casefold()
                    )

                if (
                    existing_normalized
                    ==
                    normalized_path
                ):

                    # 同一个文件夹再次导入：以前这里返回 409 挡住，
                    # 但"重新导入一遍"是很自然的动作（比如 SRT/GeoJSON
                    # 被误删后想重新生成），挡住反而不合直觉。
                    # 现在改成就地更新这条记录：文件清单以这次扫描为准，
                    # 并把 updated 标记返回给前端，好提示"已更新"而不是"已添加"。
                    existing.update(
                        folder_data
                    )

                    save_project(
                        project_name,
                        project
                    )

                    json_response(
                        self,
                        {
                            "success":
                                True,

                            "updated":
                                True,

                            "project":
                                project
                        }
                    )

                    return

            folders.append(
                folder_data
            )

            save_project(
                project_name,
                project
            )

            # 导入后**顺手把 360 素材排进转码队列**。
            #
            # 为什么放在导入时：转码是分钟级（79 秒素材约 7 分钟）。
            # 如果等用户点开才转，第一次点要干等好几分钟；
            # 用户说过「不怕预加载和导入的过程中生成文件」，
            # 所以就在导入时后台转，之后点开即秒开。
            #
            # 只扫**刚加进来的这个文件夹**（`scan_root`），不必重扫整个项目。
            # 失败不能影响导入本身 —— 导入成功是主结果，预转只是附带。
            precache = {"queued": 0, "already_done": 0, "error": None}
            try:
                queued, already = queue_pano_precache(
                    project_name, scan_root=folder_path)
                precache = {"queued": len(queued), "already_done": already,
                            "error": None}
            except Exception as e:
                precache["error"] = "%s: %s" % (type(e).__name__, e)

            json_response(
                self,
                {
                    "success":
                        True,

                    "project":
                        project,

                    # 让前端能提示"后台正在转 N 个 360 素材"
                    "pano_precache":
                        precache,
                }
            )

        except Exception as e:

            json_response(
                self,
                {
                    "error":
                        str(e)
                },
                400
            )

    # ========================================================
    # 提取 SRT
    # ========================================================

    def extract_srt(self):

        try:

            data = self.read_json()

            result = extract_srt_for_video(
                data.get("project_name"),
                data.get("folder_path"),
                data.get("relative_path")
            )

            json_response(
                self,
                {
                    "success": True,
                    "result": result
                }
            )

        except Exception as e:

            json_response(
                self,
                {
                    "error": str(e)
                },
                400
            )

    # ========================================================
    # 视场覆盖
    # ========================================================

    def resolve_coverage_npz(self, project_name, npz_param):
        """把前端给的 npz 参数解析成**项目覆盖目录里**的真实文件。

        安全检查：只允许项目 coverage/ 下的文件，并且必须是 .npz ——
        不然这个参数就成了任意文件读取的口子。
        """

        import coverage_api

        cdir = coverage_api.coverage_dir(project_name).resolve()

        if npz_param:

            candidate = Path(npz_param)

            if not candidate.is_absolute():
                candidate = cdir / candidate

            candidate = candidate.resolve()

            if candidate.suffix.lower() != ".npz":
                raise ValueError("Only .npz coverage grids are allowed.")

            if cdir not in candidate.parents:
                raise ValueError("Coverage grid must live under the project coverage folder.")

            if not candidate.is_file():
                raise FileNotFoundError("Coverage grid not found.")

            return candidate

        # 没给就挑最新的一个（前端「刚建完」的场景最常用）
        if not cdir.is_dir():
            raise FileNotFoundError("This project has no coverage grids yet.")

        grids = sorted(
            cdir.glob("*.npz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        if not grids:
            raise FileNotFoundError("This project has no coverage grids yet.")

        return grids[0]

    def build_coverage(self):

        try:

            data = self.read_json()

            project_name = data.get("project_name")
            srt_path = data.get("srt")
            cell = data.get("cell") or 1.0
            force = bool(data.get("force"))

            if not project_name:
                raise ValueError("Missing project name.")

            if not srt_path:
                raise ValueError("Missing SRT path.")

            # 只允许建在项目自己登记的文件夹里
            project = load_project(project_name)
            folders = [
                Path(item.get("path")).resolve()
                for item in (project.get("folders") or [])
                if item.get("path")
            ]

            target = Path(srt_path).resolve()

            if target.suffix.lower() != ".srt":
                raise ValueError("Only .srt files can be used to build coverage.")

            if not any(f == target.parent or f in target.parents for f in folders):
                raise ValueError("That SRT is not inside this project's folders.")

            import coverage_api

            result = coverage_api.build_coverage(
                project_name, target, cell=cell, force=force)

            json_response(self, {"success": True, "result": result})

        except Exception as e:

            json_response(self, {"error": str(e)}, 400)

    def export_coverage_geojson(self):

        try:

            data = self.read_json()

            project_name = data.get("project_name")
            metric = data.get("metric") or "count"
            threshold = data.get("threshold")
            gsd_max = data.get("gsd_max")
            tol_m = float(data.get("tol_m") or 0.0)
            min_area = int(data.get("min_area_cells") or 4)
            # 是否把多边形也交给前端（贴图用）；文件一律落盘，方便直接拿走
            inline = bool(data.get("inline", True))

            if not project_name:
                raise ValueError("Missing project name.")

            import coverage_api

            target = self.resolve_coverage_npz(project_name, data.get("npz"))

            out = coverage_api.write_geojson(
                project_name,
                target,
                metric=metric,
                threshold=int(threshold) if threshold not in (None, "") else None,
                gsd_max=float(gsd_max) if gsd_max not in (None, "") else None,
                tol_m=tol_m,
                min_area_cells=min_area
            )

            payload = {
                "success": True,
                "file": str(out),
                "file_name": out.name,
                "size_kb": round(out.stat().st_size / 1024),
            }

            if inline:
                with open(out, "r", encoding="utf-8") as f:
                    payload["geojson"] = json.load(f)

            json_response(self, payload)

        except Exception as e:

            json_response(self, {"error": str(e)}, 400)

    # ========================================================
    # 生成 GeoJSON
    # ========================================================

    def generate_geojson(self):

        try:

            data = self.read_json()

            # 用**合并入口**：一次拍摄的多路（V/S/T）合成一份航迹。
            # 单路素材会自己退回原来的单路生成（见 generate_merged_track）。
            result = generate_merged_track(
                data.get("project_name"),
                data.get("folder_path"),
                data.get("relative_path")
            )

            json_response(
                self,
                {
                    "success": True,
                    "result": result
                }
            )

        except Exception as e:

            json_response(
                self,
                {
                    "error": str(e)
                },
                400
            )

    # ========================================================
    # 生成 3D GeoJSON
    # ========================================================

    def generate_geo3d(self):

        try:

            data = self.read_json()

            result = generate_geo3d_for_video(
                data.get("project_name"),
                data.get("folder_path"),
                data.get("relative_path")
            )

            json_response(
                self,
                {
                    "success": True,
                    "result": result
                }
            )

        except Exception as e:

            json_response(
                self,
                {
                    "error": str(e)
                },
                400
            )

    # ========================================================
    # 删除单个 GeoJSON 文件
    # ========================================================

    # ========================================================
    # 标记点（画面右键取点得到的点，随项目保存）
    # ========================================================

    def save_markers(self):
        """整表覆盖保存某个项目的标记点。

        存在 Project/<项目名>/project.json 的 markers 数组里 —— 跟着项目走，
        关掉页面再打开仍在。读取不需要单独接口：/api/project/get 会带回整个项目，
        里面就含 markers。

        每个标记点的字段（前端负责填全）：
            id / name / lat / lng / video / time / created
            fx / fy（可选）：右键取点时鼠标点在画面上的归一化位置（0..1，左上为原点），
                            报告的视频截图靠它叠目标点标志。老标记点没有这两个字段。
        其中 video + time 是"点列表能跳回那一帧"的关键。
        """

        try:

            data = self.read_json()

            project_name = data.get("project_name")

            markers = data.get("markers")

            if not project_name:
                raise ValueError("Missing project name.")

            if markers is None or not isinstance(markers, list):
                raise ValueError("markers 必须是数组。")

            project = load_project(project_name)

            cleaned = []

            for item in markers:

                if not isinstance(item, dict):
                    continue

                lat = item.get("lat")
                lng = item.get("lng")

                if lat is None or lng is None:
                    continue

                entry = {
                    "id": str(item.get("id") or ""),
                    "name": str(item.get("name") or "标记"),
                    "lat": float(lat),
                    "lng": float(lng),
                    "video": str(item.get("video") or ""),
                    "time": float(item.get("time") or 0),
                    "created": str(item.get("created") or ""),
                    # 类别：用户可以自由输入，作用相当于"文件夹"（用户 2026-10-16：
                    # 「第一次输入是建立类别，就是对应文件夹，第二次就可以选择新建
                    # 新的类别或者直接复用上次的类别」）。
                    # 所以**不做枚举校验** —— 新值出现即视为新建类别。
                    "category": str(item.get("category") or "").strip(),
                }

                # 备注：一样是自由文本，先留着（分类体系还没定，但"这个点是什么"
                # 迟早要记；加一个字段几乎零成本，见 docs 里的讨论）。
                note = str(item.get("note") or "").strip()

                if note:
                    entry["note"] = note

                # 画面落点：有且合法才带上。
                # 这里曾经按固定字段重建、把它悄悄丢了 —— 表现是「页面刷新后报告里的
                # 目标点标志全没了」，打包验收时才发现（见 packaging/accept_packaged_app.py）。
                try:
                    fx = float(item.get("fx"))
                    fy = float(item.get("fy"))

                except (TypeError, ValueError):
                    fx = fy = None

                if fx is not None and fy is not None and 0.0 <= fx <= 1.0 and 0.0 <= fy <= 1.0:
                    entry["fx"] = fx
                    entry["fy"] = fy

                cleaned.append(entry)

            project["markers"] = cleaned

            save_project(project_name, project)

            json_response(
                self,
                {
                    "success": True,
                    "count": len(cleaned),
                    "markers": cleaned
                }
            )

        except Exception as e:

            json_response(
                self,
                {
                    "error": str(e)
                },
                400
            )

    def make_snapshot(self):
        """报告用：从原片抽一帧（原始分辨率）。"""

        try:

            json_response(
                self,
                make_video_snapshot(self.read_json())
            )

        except Exception as e:

            json_response(
                self,
                {"error": str(e)},
                400
            )

    def make_map_snapshot(self):
        """报告用：拼一张地图截图（底图跟随前端传来的类型）。"""

        try:

            json_response(
                self,
                make_map_snapshot(self.read_json())
            )

        except Exception as e:

            json_response(
                self,
                {"error": str(e)},
                400
            )

    def make_report_docx(self):
        """报告用：生成标记点报告 docx。"""

        try:

            json_response(
                self,
                build_docx_report(self.read_json())
            )

        except Exception as e:

            json_response(
                self,
                {"error": str(e)},
                400
            )

    def delete_geojson(self):
        """把一个 GeoJSON 文件从项目里删掉（磁盘上的文件真的删除）。

        源视频和 SRT 不动 —— 所以之后还能用「生成 GeoJSON」重新生成。
        """

        try:

            data = self.read_json()

            result = delete_geojson_for_video(
                data.get("project_name"),
                data.get("folder_path"),
                data.get("relative_path")
            )

            json_response(
                self,
                {
                    "success": True,
                    "result": result
                }
            )

        except Exception as e:

            json_response(
                self,
                {
                    "error": str(e)
                },
                400
            )


    # ========================================================
    # 读取 JSON
    # ========================================================

    def read_json(self):

        content_length = int(
            self.headers.get(
                "Content-Length",
                "0"
            )
        )

        raw_data = self.rfile.read(
            content_length
        )

        return json.loads(
            raw_data.decode("utf-8")
        )

    # ========================================================
    # 发送 HTML
    # ========================================================

    def send_html(
        self,
        html_file
    ):

        if not html_file.exists():

            self.send_error(
                404,
                f"{html_file.name} 不存在"
            )

            return

        content = html_file.read_bytes()

        self.send_response(200)

        self.send_header(
            "Content-Type",
            "text/html; charset=utf-8"
        )

        self.send_header(
            "Content-Length",
            str(len(content))
        )

        self.end_headers()

        self._write_body(
            content
        )

    # ========================================================
    # 日志
    # ========================================================

    def log_message(
        self,
        format,
        *args
    ):

        print(
            "%s - - [%s] %s"
            %
            (
                self.client_address[0],
                self.log_date_time_string(),
                format % args
            )
        )


def existing_server_hint(host, port, timeout=2):
    """启动前探一下：这个端口上是不是已经有服务在应答。

    有的话多半是上一次没关干净的旧进程。两个进程同时绑同一端口会「随机抢答」，
    典型表现是「页面是新的、接口却 404」—— 因为页面是每次请求现读的，
    而 Python 代码只在进程启动时载入一次。

    返回一句给人看的提示；端口上没东西时返回 None。
    """

    try:
        with urllib.request.urlopen(
            f"http://{host}:{port}/api/config",
            timeout=timeout
        ) as response:
            response.read(64)

    except Exception:
        return None

    return (
        f"⚠   {host}:{port} 上已经有服务在应答 —— 很可能是上一次没关掉的旧进程。\n"
        f"    两个进程绑同一端口会随机抢答，表现是「改了代码却 404 / 时通时不通」，\n"
        f"    甚至出现「页面是新的、接口是旧的」（页面每次现读，Python 只在启动时载入）。\n"
        f"    建议先关掉旧的再启动：\n"
        f"        netstat -ano | findstr :{port}\n"
        f"        taskkill /PID <上面那个 PID> /F\n"
        f"    （本进程仍会照常启动，但这件事没解决前可能出现各种莫名其妙的现象。）"
    )


# ============================================================
# 打包成 exe 之后的运行时外壳：端口自适应 / 单实例 / 自动开界面 / 托盘图标
# ============================================================

APP_TITLE = "无人机巡查数据地图"
APP_PAGE = "project_geojson_preview.html"

# 退出信号：托盘的「退出」菜单、/api/shutdown 都设它
SHUTDOWN_REQUEST = threading.Event()


def probe_running_server(host, port, timeout=2):
    """这个端口上是不是已经有一个「我们自己的」服务在跑？—— 单实例判断用。"""

    try:
        with urllib.request.urlopen(
            f"http://{host}:{port}/api/config",
            timeout=timeout
        ) as response:
            body = response.read(4096).decode("utf-8", "replace")

    except Exception:
        return False

    # 认指纹：这个接口会返回天地图与报告能力
    return "tianditu" in body and "report" in body


def pick_free_port(host, preferred, tries=12):
    """从 preferred 起找一个能**独占**绑定的端口，返回 (端口, 偏移)。

    **不要**设 SO_REUSEADDR：Windows 上它允许两个进程绑同一端口，
    「页面是新的、接口是旧的」那种随机抢答就会回来。
    """

    import socket

    for offset in range(tries):

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:

            try:
                probe.bind((host, preferred + offset))
                return preferred + offset, offset

            except OSError:
                continue

    return None, tries


def open_app_window(url):
    """用 Edge/Chrome 的「应用窗口」模式打开：没有地址栏，看着像桌面程序。

    找不到就退回系统默认浏览器；都失败也不影响服务本身。返回用了哪个（给日志用）。
    """

    import webbrowser

    program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    local_appdata = os.environ.get("LOCALAPPDATA", "")

    candidates = [
        Path(program_files_x86) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(program_files) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(program_files) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(program_files_x86) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]

    if local_appdata:
        candidates.append(
            Path(local_appdata) / "Google" / "Chrome" / "Application" / "chrome.exe"
        )

    for browser in candidates:

        if not browser.is_file():
            continue

        try:
            subprocess.Popen([str(browser), f"--app={url}"])
            return f"{browser.name} 应用窗口"

        except OSError:
            continue

    try:
        webbrowser.open(url)
        return "系统默认浏览器"

    except Exception:
        return None


def tray_icon_image():
    """托盘图标：优先用随包的 UAVMap.ico，找不到就现画一个（保证托盘起得来）。"""

    try:
        from PIL import Image

        for candidate in (
            CODE_DIR / "UAVMap.ico",
            DATA_DIR / "UAVMap.ico",
            TEST_DIR / "packaging" / "UAVMap.ico",
        ):

            if candidate.is_file():

                with Image.open(candidate) as opened:
                    return opened.convert("RGBA").copy()

        from PIL import ImageDraw

        image = Image.new("RGBA", (64, 64), (37, 99, 235, 255))
        ImageDraw.Draw(image).ellipse((16, 16, 48, 48), outline=(255, 255, 255, 255), width=6)

        return image

    except Exception:
        return None


def start_tray(open_callback, restart_callback, quit_callback):
    """起托盘图标（打包后才启用）。返回 icon 对象，起不来就返回 None。"""

    try:
        import pystray
    except Exception:
        return None

    image = tray_icon_image()

    if image is None:
        return None

    def _open(icon, item):
        open_callback()

    def _folder(icon, item):

        try:
            os.startfile(str(DATA_DIR))     # Windows 专用：打开资源管理器

        except Exception:
            pass

    def _restart(icon, item):
        restart_callback()

    def _quit(icon, item):
        quit_callback()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("打开界面", _open, default=True),
        pystray.MenuItem("打开数据目录", _folder),
        pystray.MenuItem("重启服务", _restart),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", _quit),
    )

    return pystray.Icon("UAVMap", image, APP_TITLE, menu)


# ============================================================
# 启动服务器
# ============================================================

def setup_frozen_logging():
    """打包后没有控制台：把输出重定向到数据目录的「运行日志.txt」，出问题好查。"""

    if not FROZEN:
        return None

    try:
        stream = (DATA_DIR / "运行日志.txt").open("a", encoding="utf-8", buffering=1)

    except OSError:
        return None

    sys.stdout = stream
    sys.stderr = stream

    print()
    print("=" * 60)
    print("启动时间：", time.strftime("%Y-%m-%d %H:%M:%S"))

    return stream


def main():

    PROJECT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    host = "127.0.0.1"

    # 端口默认 8000；想固定用别的端口就设环境变量 UAV_MAP_PORT
    # （页面里所有请求都是相对路径，换端口不用改前端）
    try:
        base_port = int(os.environ.get("UAV_MAP_PORT") or 8000)

    except ValueError:
        base_port = 8000

    # 已经有一个自己在跑 → 不重复起服务，直接把界面打开（连点两次快捷方式的情况）
    if probe_running_server(host, base_port) and not os.environ.get("UAV_MAP_FORCE_NEW"):
        print(f"{APP_TITLE}：{host}:{base_port} 上已经在运行，直接打开界面。")

        if not os.environ.get("UAV_MAP_NO_BROWSER"):
            open_app_window(f"http://{host}:{base_port}/{APP_PAGE}")

        return

    port, offset = pick_free_port(host, base_port)

    if port is None:
        print(f"端口 {base_port}~{base_port + 11} 都被占用了，服务起不来。")
        return

    if offset:
        print(f"端口 {base_port} 被占用，改用 {port}。")

    # 绑之前再看一眼有没有旧服务（绑上之后就问不出来了）
    port_hint = existing_server_hint(host, port)

    server = ThreadingHTTPServer((host, port), ProjectManagerHandler)

    url = f"http://{host}:{port}/{APP_PAGE}"
    state = {"server": server, "port": port}

    print()
    print("=" * 60)
    print(APP_TITLE)
    print("=" * 60)
    print()

    for page_label, page_name in (
        ("项目管理", "project_manager.html"),
        ("项目数据导入", "project_import.html"),
        ("项目媒体识别", "project_media.html"),
        ("视频结构检测", "project_video_inspector.html"),
        ("GeoJSON 轨迹预览", "project_geojson_preview.html"),
        ("3D 轨迹预览", "project_geo3d_preview.html"),
    ):
        print(f"{page_label}： http://{host}:{port}/{page_name}")

    print()
    print(f"数据目录： {DATA_DIR}")
    print(f"DPI 感知： {enable_dpi_awareness() or '（未能声明，界面可能发虚）'}")

    if migrate_legacy_key_file():
        print(f"天地图 key：已从老位置（{CODE_DIR.name}\\tianditu_key.txt）搬到数据目录")

    print(f"天地图 key： {TIANDITU_KEY_FILE if get_tianditu_key() else '未配置（底图退回 OSM，地名搜索不可用）'}")
    print(f"ffmpeg ： {find_ffmpeg() or '（没找到：抽帧与 4K 转码会失败）'}")
    print()

    if port_hint:
        print(port_hint)
        print()

    def open_url():
        where = open_app_window(url)
        print(f"已用{where or '（没找到浏览器）'}打开界面。")

    def restart():
        old = state["server"]
        print("重启服务……")

        try:
            old.shutdown()
            old.server_close()

        except Exception:
            pass

        fresh = ThreadingHTTPServer((host, state["port"]), ProjectManagerHandler)
        state["server"] = fresh
        threading.Thread(target=fresh.serve_forever, daemon=True).start()
        print("服务已重启。")

    def _quit_callback():
        SHUTDOWN_REQUEST.set()

    # 托盘要跑在**主线程**（Windows 的要求），所以服务放到后台线程里。
    # - 源码直跑默认不起托盘（会打扰开发），UAV_MAP_TRAY=1 打开；
    # - UAV_MAP_NO_TRAY=1 强制不起（受限桌面里创建托盘窗口会被系统拒掉，
    #   那种环境下要么这里退让，要么整个进程被连带干掉）。
    want_tray = (FROZEN or os.environ.get("UAV_MAP_TRAY")) and not os.environ.get("UAV_MAP_NO_TRAY")
    icon = None

    if want_tray:
        icon = start_tray(open_url, restart, _quit_callback)

    if icon is not None:

        def _watch_quit():
            SHUTDOWN_REQUEST.wait()

            try:
                state["server"].shutdown()

            except Exception:
                pass

            try:
                icon.stop()

            except Exception:
                pass

        threading.Thread(target=state["server"].serve_forever, daemon=True).start()
        threading.Thread(target=_watch_quit, daemon=True).start()

        if not os.environ.get("UAV_MAP_NO_BROWSER"):
            open_url()

        print("已最小化到右下角托盘：右键图标可打开界面 / 打开数据目录 / 重启服务 / 退出。")
        print()

        try:
            icon.run()

        except Exception as e:
            # 托盘起不来（受限桌面、权限不足……）**不能连带把程序弄死**：
            # 退回前台服务，日志里写明怎么退出。
            print(f"⚠ 托盘图标不可用（{e}）；已改为前台运行。")
            print("   退出方式：托盘可用时点托盘菜单「退出」，否则关掉本进程或调 /api/shutdown。")
            print()

            try:
                threading.Thread(
                    target=state["server"].serve_forever,
                    daemon=True
                ).start()

                SHUTDOWN_REQUEST.wait()

            except KeyboardInterrupt:
                pass

            finally:
                state["server"].server_close()

            return

        print("已退出。")
        return

    if FROZEN and not os.environ.get("UAV_MAP_NO_BROWSER"):
        open_url()

    print("按 Ctrl+C 停止服务器")
    print()

    threading.Thread(target=state["server"].serve_forever, daemon=True).start()

    try:

        # 等到「退出」信号（托盘菜单 / /api/shutdown / Ctrl+C）
        while not SHUTDOWN_REQUEST.wait(0.4):
            pass

    except KeyboardInterrupt:

        print()
        print("服务器已停止。")

    finally:

        try:
            state["server"].shutdown()

        except Exception:
            pass

        state["server"].server_close()


if __name__ == "__main__":
    setup_frozen_logging()
    main()
