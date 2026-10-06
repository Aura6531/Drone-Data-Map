import json
import hashlib
import io
import math
import os
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
from urllib.parse import urlparse, parse_qs, urlencode


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
# 基础目录
# ============================================================

CODE_DIR = Path(__file__).resolve().parent
TEST_DIR = CODE_DIR.parent

PROJECT_DIR = TEST_DIR / "Project"

PROJECT_MANAGER_HTML = CODE_DIR / "project_manager.html"
PROJECT_IMPORT_HTML = CODE_DIR / "project_import.html"
PROJECT_MEDIA_HTML = CODE_DIR / "project_media.html"
PROJECT_VIDEO_INSPECTOR_HTML = CODE_DIR / "project_video_inspector.html"
PROJECT_GEOJSON_PREVIEW_HTML = CODE_DIR / "project_geojson_preview.html"
PROJECT_GEO3D_PREVIEW_HTML = CODE_DIR / "project_geo3d_preview.html"
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
# key 可在系统环境变量 TIANDITU_KEY 中配置，也可直接填在下面。
# 申请地址：https://console.tianditu.gov.cn/
# ------------------------------------------------------------

TIANDITU_KEY = (os.environ.get("TIANDITU_KEY") or "").strip()
TIANDITU_KEY_FILE = CODE_DIR / "tianditu_key.txt"
TIANDITU_SEARCH_URL = "https://api.tianditu.gov.cn/v2/search"
# 地名搜索的范围框（minLon,minLat,maxLon,maxLat）。用全国范围，
# 这样搜索不受当前地图视野限制。
TIANDITU_MAP_BOUND = "73,3,135,54"
GEOCODE_CACHE_DIR = CODE_DIR / "geocode_cache"
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
PROXY_CACHE_MAX_MB = 4096    # 片段缓存上限，超出后按最旧的删除
PROXY_LOCK = threading.Lock()

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
    """找 ffmpeg：PATH 优先，其次 ffprobe 同目录，最后常见安装路径。"""

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

    if video_path.suffix.lower() not in (".mp4", ".mov"):
        raise ValueError("指定文件不是 MP4/MOV 视频。")

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
                height
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

    if video_path.suffix.lower() not in (".mp4", ".mov"):
        raise ValueError("指定文件不是 MP4/MOV 视频。")

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
            handler.wfile.write(chunk)
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
        "alt": [],
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

            raise ValueError(f"转码失败：{detail or '未知错误'}")

        temp_path.replace(output_path)

    prune_proxy_cache()

    return output_path, bucket


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
            "尚未配置天地图 key，无法使用地名搜索。"
            f" 请把天地图控制台的 tk 粘贴到 {TIANDITU_KEY_FILE.name} 里"
            "（该文件就在 project_manager.py 旁边，存盘后刷新网页即可，不用重启服务）。"
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
                handler.wfile.write(data)
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
    handler.wfile.write(data)


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
        raise ValueError("文件名不合法。")

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


def safe_file_stem(text, fallback="未命名"):
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
        raise ValueError("尚未配置天地图 key，无法解析所在位置。")

    try:
        lat_value = float(lat)
        lng_value = float(lng)

    except (TypeError, ValueError):
        raise ValueError("经纬度无效。")

    if not (-90.0 <= lat_value <= 90.0 and -180.0 <= lng_value <= 180.0):
        raise ValueError("经纬度超出范围。")

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
        raise ValueError("天地图逆地理编码返回的不是 JSON。")

    if str(payload.get("status")) != "0":
        raise ValueError(
            "天地图逆地理编码失败："
            + str(payload.get("msg") or payload.get("status") or "未知原因")
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
    radius = 16

    draw.ellipse(
        (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
        outline=(255, 255, 255),
        width=5
    )
    draw.ellipse(
        (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
        outline=(220, 38, 38),
        width=3
    )

    for color, line_width in (((255, 255, 255), 5), ((220, 38, 38), 3)):
        draw.line(
            (center_x - radius - 10, center_y, center_x + radius + 10, center_y),
            fill=color,
            width=line_width
        )
        draw.line(
            (center_x, center_y - radius - 10, center_x, center_y + radius + 10),
            fill=color,
            width=line_width
        )

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
        raise ValueError("缺少项目名称。")

    if not relative_path:
        raise ValueError("缺少视频相对路径。")

    try:
        time_seconds = max(0.0, float(payload.get("time") or 0))

    except (TypeError, ValueError):
        raise ValueError("时间无效。")

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
        raise ValueError("未找到 ffmpeg，无法抽帧。请安装 ffmpeg 后重启服务。")

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
        raise ValueError("抽帧超时。")

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
            "抽帧失败："
            + (lines[-1] if lines else f"ffmpeg 退出码 {completed.returncode}")
        )

    try:
        from PIL import Image

        with Image.open(temp_path) as frame:

            image = frame.convert("RGB")

            if mode == "a4" and image.width > REPORT_IMAGE_WIDTH_A4:
                ratio = REPORT_IMAGE_WIDTH_A4 / image.width
                image = image.resize(
                    (
                        REPORT_IMAGE_WIDTH_A4,
                        max(2, round(image.height * ratio))
                    )
                )

            width, height = image.size

            image.save(
                output_path,
                "JPEG",
                quality=92,
                optimize=True,
                dpi=report_image_dpi(width, height, REPORT_VIDEO_IMAGE_MAX_HEIGHT_CM)
            )

    except Exception as e:
        raise ValueError(
            "抽帧后的图片转换失败（需要 Pillow）："
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
    }


def make_map_snapshot(payload):
    """拼一张地图截图；底图类型由前端传（跟随用户当前选的那一种）。"""

    try:
        lat = float(payload.get("lat"))
        lng = float(payload.get("lng"))

    except (TypeError, ValueError):
        raise ValueError("经纬度无效。")

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        raise ValueError("经纬度超出范围。")

    try:
        zoom = int(payload.get("zoom") or 16)

    except (TypeError, ValueError):
        zoom = 16

    if not (1 <= zoom <= 19):
        raise ValueError("缩放级别要在 1~19 之间。")

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
        ("名称", point.get("name") or "标记点"),
        # 半球写在表头里；数字用正负号区分南北/东西，方便直接复制
        ("纬度（°N）", point.get("lat_text") or ""),
        ("经度（°E）", point.get("lng_text") or ""),
        ("所在位置", point.get("place") or "未解析"),
        ("视频文件", point.get("video") or "-"),
        ("视频时间", point.get("time_text") or "-"),
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
            "place": str(raw.get("place") or "未解析"),
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

    project_name = str(payload.get("project_name") or "")

    points = normalize_report_points(payload.get("points") or [])

    if not points:
        raise ValueError("没有有效的标记点可写进报告。")

    image_mode = str(payload.get("image_mode") or "full")

    mode_text = (
        "压缩至 320ppi（约 2480px 宽）" if image_mode == "a4" else "原分辨率"
    )

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
        f"标记点报告 —— 项目「{project_name or '未命名'}」",
        level=0
    )

    meta = document.add_paragraph(
        f"生成时间：{time.strftime('%Y-%m-%d %H:%M')}　　"
        f"标记点：{len(points)} 个　　视频截图：{mode_text}"
    )
    meta.runs[0].font.size = Pt(9)
    set_report_font(meta.runs[0], 9)

    document.add_heading("目录", level=1)
    hint = document.add_paragraph("点击下面任意一项，可直接跳到对应章节。")
    set_report_font(hint.runs[0], 9)

    for index, point in enumerate(points, start=1):
        paragraph = document.add_paragraph(style="List Number")
        add_docx_internal_link(paragraph, f"mark{index}", point["name"])

    document.add_heading("汇总表", level=1)

    columns = ["序号", "名称", "纬度（°N）", "经度（°E）", "所在位置", "视频文件", "视频时间"]

    # 列宽写死 + 关掉自动伸缩：长文件名（下划线处 Word 不断行）容易把表撑出正文区。
    # 合计 15.9cm —— 与插图同一个宽度，左边缘、右边缘才对得齐。
    column_widths = (
        Cm(1.1), Cm(2.6), Cm(2.0), Cm(2.3), Cm(3.4), Cm(3.1), Cm(1.4)
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
                f"图 1　目标点视频截图（{point['video'] or '-'}　"
                f"{point['time_text']}）"
            ).paragraph_format.keep_with_next = True      # 图 2 跟着它一起走

        if map_image:
            add_report_picture(document, map_image, REPORT_MAP_IMAGE_MAX_HEIGHT_CM)
            add_report_caption(
                document,
                f"图 2　目标点地图截图（底图："
                f"{point['basemap_name'] or '当前底图'}　"
                f"缩放 {point['zoom']} 级）"
            )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    name = new_report_name("report", ".docx")

    document.save(str(REPORT_DIR / name))

    return {
        "file": name,
        "url": "/report/" + name,
        "download_name":
            f"标记点报告_{safe_file_stem(project_name)}_"
            f"{time.strftime('%Y-%m-%d')}.docx",
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
    # GET
    # ========================================================

    def do_GET(self):

        parsed = urlparse(
            self.path
        )

        path = parsed.path

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

        if path.startswith("/vendor/"):

            name = path[len("/vendor/"):]

            # 只允许目录下的单层文件名，挡掉路径穿越
            if (
                not name
                or "/" in name
                or "\\" in name
                or ".." in name
            ):
                self.send_error(404, "Not found")
                return

            target = VENDOR_DIR / name

            if not target.is_file():
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
            self.wfile.write(data)
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
            self.wfile.write(data)
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
        # 视频文件流（支持 HTTP Range）
        # ----------------------------------------------------

        if path == "/api/project/video":

            try:

                params = parse_qs(parsed.query)

                project_name = params.get("name", [""])[0]
                folder_index = params.get("folder_index", [""])[0]
                relative_path = params.get("path", [""])[0]

                if not project_name:
                    raise ValueError("缺少项目名称。")

                if not relative_path:
                    raise ValueError("缺少视频相对路径。")

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
        # 网页播放代理：按需把点击位置附近的一段转成 H.264
        # ----------------------------------------------------

        if path == "/api/project/proxy":

            try:

                params = parse_qs(parsed.query)

                project_name = params.get("name", [""])[0]
                folder_index = params.get("folder_index", [""])[0]
                relative_path = params.get("path", [""])[0]

                if not project_name:
                    raise ValueError("缺少项目名称。")

                if not relative_path:
                    raise ValueError("缺少视频相对路径。")

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
                    raise ValueError("缺少项目名称。")

                if not relative_path:
                    raise ValueError("缺少视频相对路径。")

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
                        "缺少项目名称。"
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

                selected_path = (
                    select_folder_windows()
                )

                if not selected_path:

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
                        "path":
                            selected_path
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
                        "缺少项目名称。"
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
                        "缺少项目名称。"
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
                    raise ValueError("缺少项目名称。")

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
                    raise ValueError("缺少项目名称。")

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
                    raise ValueError("缺少项目名称。")

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
                    "缺少项目名称。"
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

            json_response(
                self,
                {
                    "success":
                        True,

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
    # 生成 GeoJSON
    # ========================================================

    def generate_geojson(self):

        try:

            data = self.read_json()

            result = generate_geojson_for_video(
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
        其中 video + time 是"点列表能跳回那一帧"的关键。
        """

        try:

            data = self.read_json()

            project_name = data.get("project_name")

            markers = data.get("markers")

            if not project_name:
                raise ValueError("缺少项目名称。")

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

                cleaned.append({
                    "id": str(item.get("id") or ""),
                    "name": str(item.get("name") or "标记"),
                    "lat": float(lat),
                    "lng": float(lng),
                    "video": str(item.get("video") or ""),
                    "time": float(item.get("time") or 0),
                    "created": str(item.get("created") or "")
                })

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

        self.wfile.write(
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
# 启动服务器
# ============================================================

if __name__ == "__main__":

    PROJECT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    HOST = "127.0.0.1"

    # 端口默认 8000；想跑在别的端口（例如已经有旧服务占着 8000、想先另起一个）
    # 就设环境变量 UAV_MAP_PORT。页面里所有请求都是相对路径，换端口不用改前端。
    try:
        PORT = int(os.environ.get("UAV_MAP_PORT") or 8000)

    except ValueError:
        PORT = 8000

    # 绑端口之前先看有没有旧服务占着（绑上之后再问就问不出来了，两个都能绑成功）
    port_hint = existing_server_hint(HOST, PORT)

    server = ThreadingHTTPServer(
        (
            HOST,
            PORT
        ),
        ProjectManagerHandler
    )

    print()
    print("=" * 60)
    print("无人机巡查项目管理")
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
        print(f"{page_label}： http://{HOST}:{PORT}/{page_name}")

    print()
    print("按 Ctrl+C 停止服务器")
    print()

    if port_hint:
        print(port_hint)
        print()

    try:

        server.serve_forever()

    except KeyboardInterrupt:

        print()
        print("服务器已停止。")

    finally:

        server.server_close()
