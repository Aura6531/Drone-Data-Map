# -*- coding: utf-8 -*-
"""视场覆盖栅格 —— 回答「某个经纬度有没有被拍到、看多清、观测了几次多大把握」。

## 设计（v2，性能与字段都经过修正）

核心洞察：**"覆盖了几帧"和"最好一次看得多清"可以一次栅格化同时得到。**

  - 同一帧内，GSD（地面分辨率）与到无人机的**斜距**成正比
    （`GSD = 斜距 × 单像素角`，单像素角只由焦距决定）
  - 所以"某格的最优 GSD" ⟺ "覆盖该格的所有帧里，哪一帧的斜距最小"
  - 于是每帧只需做两件事：`count += 1`、`min_slant2 = minimum(min_slant2, 该格斜距²)`
  - 斜距平方在行内是 **二次多项式**，可以整段向量化，**不需要 sqrt、不需要 meshgrid**

其余字段都在最后从 `count / min_slant2 / frame_at_min / last_frame` 推出来。

## 修正过的两处设计缺陷

1. **性能**：v1 每帧做 meshgrid + 凸四边形内点判定 + sqrt，12181 帧要 161 s。
   v2 用「行内二次多项式取最小」代替，实测降到 ~40 s。
2. **`clipped` 不能是布尔标志**：v1 用 `clipped_hit`（只要有一帧用了收口就置 1），
   结果 **85.8% 的格子被标成"依赖收口"** —— 因为一格平均被 230 帧覆盖，标志饱和了，
   失去区分度。v2 改成 **`clipped_count`（计数）**，
   置信度里按**比例**打折：`r_clip = 1 - (1-PENALTY) · clipped_count/count`。

## 扩展点：将来接 DEM/DSM 做非平地验证

现在高度是"相对起飞点"，地面按平面处理。接 DEM 时：

- SRT 里同时有 `rel_alt` 与 `abs_alt`，**逐点相减即得起飞点高程**（实测 std 0.0001 m，很稳）
- 有了 DEM 后，某格的地形高度 `dem(格)` 已知，
  无人机在该格上方的**净空** = `起飞点高程 + rel_alt − dem(格)`
- 把本模块里所有 `height` 从标量换成**逐格数组**，`frame_footprint()` 需要从
  "一次求交"改成"迭代求交"（因为净空随格而变），其余结构不动
- 置信度里 `dh_terrain` 从**标量**换成**逐格数组**即可 —— 函数签名已经预留 `dh` 参数

依赖：numpy（必需，纯 Python 太慢）。存储：`.npz`（放数据目录，不进仓库）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# ============================================================
# 常量
# ============================================================

FULLFRAME_DIAGONAL = 43.2666
FRAME_ASPECT = (16, 9)
M_PER_DEG_LAT = 110540.0
M_PER_DEG_LNG = 111320.0
TELEMETRY_STEP = 3                 # 与 project_manager 一致
PASS_GAP_FRAMES = 10               # 间隔超过这么多采样点(≈1s) 算新的一次经过

WIDE_MAX_FOCAL = 40.0              # <=40mm 广角档
CLIP_PER_ALT = 12.0                # 远边收口：12 × 相对高度
CLIP_MIN = 600.0
BOUND_MARGIN = 120.0

LONG_PX_VISIBLE = 3840             # 可见光长边
LONG_PX_THERMAL = 640              # 热成像长边

# —— 置信度系数（docs/视场覆盖_置信度函数.md 定稿）——
CONF = {
    "d_pitch": 0.15,        # 度（SRT 量化地板 0.1° + 一档余量）
    "d_yaw": 0.15,          # 度
    "dh_terrain": 0.5,      # 米，常数；接 DEM 时改逐格数组
    "d_gnss": 1.5,          # 米，只进 accuracy_note
    "sigma_ref": 3.0,       # 米
    "frames_full": 120,
    "passes_full": 3,
    "gsd_good": 0.10,       # 米/像素
    "clip_penalty": 0.5,
    "w_space": 0.5,
    "gamma": 0.8,
    "min_floor": 0.25,
}


# ============================================================
# 相机几何
# ============================================================

def fov_of(focal: float) -> tuple[float, float]:
    """等效焦距 -> (水平视场, 垂直视场)，度。"""
    diag = math.hypot(*FRAME_ASPECT)
    tan_diag = FULLFRAME_DIAGONAL / (2.0 * focal)
    return (2 * math.degrees(math.atan(tan_diag * FRAME_ASPECT[0] / diag)),
            2 * math.degrees(math.atan(tan_diag * FRAME_ASPECT[1] / diag)))


def rad_per_px(focal: float, long_px: int) -> float:
    """单像素张角（弧度）—— 只与焦距和像素数有关。"""
    return math.radians(fov_of(focal)[0]) / max(long_px, 1)


def long_px_for(name: str) -> int:
    s = str(name or "").upper()
    if "_T." in s or s.endswith("_T.SRT"):
        return LONG_PX_THERMAL
    return LONG_PX_VISIBLE


def ground_point_in_frame(drone, height, yaw, pitch, focal, point):
    """地面点是否**真的在画面内** —— 把点投到图像，看归一化坐标是否在 ±1 之内。

    为什么需要它（这是"四角连线"判不出来的一件事）：
      `frame_footprint()` 只算四个角，中间是**直线插值**。对**非收口**帧这是精确的
      （实测 0% 误差）；但**收口帧**上远边被沿径向缩成一条弧，四边形被扭歪，
      会给出"在足迹内、其实在画面外"的格子。实测收口帧上 26% 的命中是这种情况。

    所以「Frames of this spot」这类**要指出画面**的功能，必须用这个射影判定，
    不能用四角多边形。

    drone   (lat, lng) 无人机位置
    point   (lat, lng) 目标
    返回    (xi, yi, inside)：归一化图像坐标与是否在画面内；
            点在相机背后时返回 (None, None, False)
    """
    lat0, lng0 = drone
    mx = M_PER_DEG_LNG * math.cos(math.radians(lat0))
    d = ((point[1] - lng0) * mx,
         (point[0] - lat0) * M_PER_DEG_LAT,
         -height)
    L = math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
    if L <= 1e-9:
        return None, None, False
    d = (d[0] / L, d[1] / L, d[2] / L)

    yr, pr = math.radians(yaw), math.radians(pitch)
    sy, cy = math.sin(yr), math.cos(yr)
    sp, cp = math.sin(pr), math.cos(pr)
    f = (cp * sy, cp * cy, sp)
    u = (-sp * sy, -sp * cy, cp)
    r = (f[1] * u[2] - f[2] * u[1],
         f[2] * u[0] - f[0] * u[2],
         f[0] * u[1] - f[1] * u[0])

    z = d[0] * f[0] + d[1] * f[1] + d[2] * f[2]
    # 用 epsilon 而不是 > 0：当目标和地面"地平线方向"几乎重合时（例如俯角 −40°、
    # 垂直视场 45°，地平线正好落在画面顶边），z 会算成 0 或极小值，
    # 于是 x/z 得到一个**看似正常**的 0 —— 把地平线误判成"在画面里"。
    if z <= 1e-9:
        return None, None, False                    # 相机背后 / 地平线以上
    x = (d[0] * r[0] + d[1] * r[1] + d[2] * r[2]) / z
    y = (d[0] * u[0] + d[1] * u[1] + d[2] * u[2]) / z
    hfov, vfov = fov_of(focal)
    xi = x / math.tan(math.radians(hfov / 2))
    yi = y / math.tan(math.radians(vfov / 2))
    return xi, yi, (abs(xi) <= 1.0 and abs(yi) <= 1.0)


def bearing_elevation(drone, height, point):
    """从无人机看目标点的**方位角**与**俯角**（度）。

    为什么不用相机 yaw：云台会独立转动，`frame_yaw` 是相机指向、不一定对着目标。
    判断"这一帧是从哪个方向看过去的"，必须用**无人机→目标**的几何关系。

    方位角约定：正北 0°，顺时针为正（正东 90°），与 `frame_footprint` 里
    yaw 的约定一致（实测 yaw=0 时足迹中心在正北、yaw=90 在正东）。
    俯角：负值表示向下看。
    """
    lat0, lng0 = drone
    e = (point[1] - lng0) * M_PER_DEG_LNG * math.cos(math.radians(lat0))
    n = (point[0] - lat0) * M_PER_DEG_LAT
    bearing = math.degrees(math.atan2(e, n)) % 360.0
    horiz = math.hypot(e, n)
    pitch = -math.degrees(math.atan2(height, horiz)) if horiz > 1e-9 else -90.0
    return bearing, pitch


# 视频帧率。SRT 的 cue 时间戳是按视频时间记的，所以"帧号 -> 秒"就是除以它。
VIDEO_FPS = 30.0


def telemetry_sample_of_frame(frame_index):
    """**视频帧号 -> 抽稀后的遥测采样下标**。

    这是整个模块唯一的换算入口，别再在别处手写。

    为什么必须收成一处（踩过的坑，2026-10-13）：
      遥测按 TELEMETRY_STEP 抽稀（30fps 每 3 帧一个点 -> 10Hz），
      所以 frame_focal/frame_alt/... 这些数组的**下标是采样点序号**，不是视频帧号。
      而 times[] 也是采样点序号对齐的。

      曾经在 find_frames 里写成 `times[frame_index]` ——
      把视频帧号当成了采样点序号。因为采样数组长度（12453）比帧号（11793）
      只大一点，**不报错**，只是悄悄取到了 **17.7 秒之后** 的坐标：
      帧 11793 的视频时刻是 1179.3 s，而 times[11793] = 1197.0 s。
      实测偏差 228 m（用画面里 DJI 烧录的 OSD 经纬度核对出来的）。

    正确：sample = frame / (fps / step) = frame * step / fps
    """
    return int(round(frame_index * TELEMETRY_STEP / VIDEO_FPS))


def video_seconds_of_frame(frame_index):
    """**视频帧号 -> 视频内的秒数**。同样只此一处。"""
    return frame_index * TELEMETRY_STEP / VIDEO_FPS


def frame_footprint(height, yaw, pitch, focal, clip):
    """一帧的地面四边形（ENU 偏移，米），顺序 左下/右下/右上/左上。

    返回 (pts, clipped)；pts 为 4x2 的 tuple of tuple，算不出时返回 (None, False)。
    仅对**画面上边缘**（地面远端）收口；近边永不收口
    （v1 曾对四个角都收口，导致近边被推到远处、四边形压扁成窄带）。
    """
    hfov, vfov = fov_of(focal)
    th = math.tan(math.radians(hfov / 2))
    tv = math.tan(math.radians(vfov / 2))

    yr, pr = math.radians(yaw), math.radians(pitch)
    sy, cy = math.sin(yr), math.cos(yr)
    sp, cp = math.sin(pr), math.cos(pr)

    f = (cp * sy, cp * cy, sp)
    u = (-sp * sy, -sp * cy, cp)
    r = (f[1] * u[2] - f[2] * u[1],
         f[2] * u[0] - f[0] * u[2],
         f[0] * u[1] - f[1] * u[0])

    def cast(xi, yi):
        d2 = r[2] * (xi * th) + u[2] * (yi * tv) + f[2]
        if d2 >= -1e-9:
            return None
        d0 = r[0] * (xi * th) + u[0] * (yi * tv) + f[0]
        d1 = r[1] * (xi * th) + u[1] * (yi * tv) + f[1]
        t = -height / d2
        return (t * d0, t * d1)

    pts, clipped = [], False
    for xi, yi in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        p = cast(xi, yi)
        if p is None:
            q = cast(xi, -1)
            if q is None:
                return None, False
            dd = math.hypot(*q)
            p = (q[0] * clip / dd, q[1] * clip / dd) if dd > 1e-6 else q
            clipped = True
        elif yi > 0:
            dd = math.hypot(*p)
            if dd > clip and dd > 1e-6:
                p = (p[0] * clip / dd, p[1] * clip / dd)
                clipped = True
        pts.append(p)
    return pts, clipped


# ============================================================
# 网格容器
# ============================================================

@dataclass
class CoverageGrid:
    # lat0/lng0 是网格的**西南角**（原点），不是中心。
    # 为什么：曾经把原点当中心、半宽取 12×最高高度 —— 那假设了"飞机就在起点附近"，
    # 而实际一趟能飞好几公里，于是网格边缘把航线切掉，热力图只剩一块矩形。
    # 现在按**实际航线范围**建网格（见 build_from_telemetry）。
    lat0: float
    lng0: float
    cell: float
    nx: int
    ny: int
    half: float                         # 兼容旧字段：max(half_x, half_y)/... 见 summary
    half_x: float = 0.0                 # 东西向半宽（米）
    half_y: float = 0.0                 # 南北向半宽（米）
    count: np.ndarray = None            # int32  覆盖帧数
    gsd_best_map: np.ndarray = None     # float32 最优地面分辨率（米/像素），0 = 未覆盖
    frame_at_min: np.ndarray = None     # int32  取得最优 GSD 的帧号
    last_frame: np.ndarray = None       # int32  最近一次覆盖的帧号
    clipped_count: np.ndarray = None    # int32  其中用到收口的帧数
    zoom_count: np.ndarray = None       # int32  其中变焦帧数
    frames_total: int = 0
    frames_used: int = 0
    frames_skipped: int = 0
    frames_wide: int = 0
    frames_zoom: int = 0
    srt_name: str = ""
    takeoff_elev: float = 0.0
    long_px: int = LONG_PX_VISIBLE
    frame_focal: list = field(default_factory=list)   # 每帧焦距
    frame_alt: list = field(default_factory=list)
    frame_yaw: list = field(default_factory=list)
    frame_pitch: list = field(default_factory=list)
    # 逐帧的**单像素角**（弧度）。存下来是为了让 360 素材（frame_focal = 0，
    # 没有焦距这个概念）也能反推斜距、算 GSD —— 否则查询时会除零。
    frame_ang_per_px: list = field(default_factory=list)
    # 逐采样点的**视频内秒数**（即 SRT 的 cue 时间）。
    # 为什么必须存：光有采样下标推不出准确时刻 —— SRT 的采样间隔并非严格 1/10 s，
    # 按帧率折算会累积到十几秒的误差（实测 17.7 s / 228 m）。
    frame_times: list = field(default_factory=list)
    cols: np.ndarray = None             # 列心的东向偏移（米），构建时缓存

    # ---------- 派生量 ----------
    def passes(self):
        """独立经过次数（估计）：覆盖帧号跨度 / 单次经过的最大帧跨度。"""
        return 1 + (self.count - 1) // PASS_GAP_FRAMES

    def gsd_best(self):
        """最优地面分辨率（米/像素）—— 构建时就已算好，这里直接返回。"""
        return self.gsd_best_map

    def clipped_ratio(self):
        m = self.count > 0
        r = np.zeros(self.count.shape, dtype=np.float32)
        r[m] = self.clipped_count[m] / self.count[m]
        return r

    # ---------- 坐标换算 ----------
    # 格 (ix,iy) 的中心：e = -half_x + (ix+0.5)*cell，n = -half_y + (iy+0.5)*cell
    # （即原点 (lat0,lng0) 在网格的西南角）
    def _mx(self):
        return M_PER_DEG_LNG * math.cos(math.radians(self.lat0))

    def hx(self):
        return self.half_x or self.half

    def hy(self):
        return self.half_y or self.half

    def cell_of(self, lat, lng):
        e = (lng - self.lng0) * self._mx()
        n = (lat - self.lat0) * M_PER_DEG_LAT
        return int(e / self.cell), int(n / self.cell)

    def inside(self, ix, iy):
        return 0 <= ix < self.nx and 0 <= iy < self.ny

    def cell_latlng(self, ix, iy):
        """格中心的经纬度（点查询反向用得到）。"""
        e = (ix + 0.5) * self.cell
        n = (iy + 0.5) * self.cell
        return (self.lat0 + n / M_PER_DEG_LAT,
                self.lng0 + e / self._mx())

    # ---------- 查询 ----------
    def query(self, lat, lng, cfg=None):
        ix, iy = self.cell_of(lat, lng)
        if not self.inside(ix, iy):
            return {"covered": False, "reason": "Outside the coverage grid for this flight."}
        n = int(self.count[iy, ix])
        if n == 0:
            return {"covered": False, "reason": "No frame of this flight saw this spot."}
        cfg = cfg or CONF
        fi = int(self.frame_at_min[iy, ix])
        gsd = float(self.gsd_best_map[iy, ix])
        # 反推斜距（供展示）：GSD 已含"单像素角"信息，所以斜距 = GSD / 单像素角。
        # **用建网格时逐帧存下来的 ang_per_px**，不要用 frame_focal 现算 ——
        # 360 素材没有焦距（frame_focal = 0），现算会 ZeroDivisionError；
        # 而存下来的值在两种机型上都对。
        app = None
        if 0 <= fi < len(getattr(self, "frame_ang_per_px", [])):
            app = self.frame_ang_per_px[fi]
        if not app or app <= 0:
            foc_fi = self.frame_focal[fi] if 0 <= fi < len(self.frame_focal) else 24.0
            app = rad_per_px(foc_fi, self.long_px)
        slant = gsd / max(app, 1e-12)
        pit = self.frame_pitch[fi]
        alt = self.frame_alt[fi]
        passes = int(1 + (n - 1) // PASS_GAP_FRAMES)
        clip_ratio = float(self.clipped_count[iy, ix]) / n
        # 收口比例 -> r_clip（线性打折）
        r_clip = 1.0 - (1.0 - cfg["clip_penalty"]) * clip_ratio
        # 360 没有云台姿态 -> sigma_footprint 的俯角项无意义（pitch=0 会返回 inf，
        # 把置信度压成 0）。全景的"边界不确定度"只由地表高差决定，所以这里
        # 用 dh/tan(45°) 量级的保守值代替，而不是让它变成 inf。
        if pit is None or abs(pit) < 1e-6:
            sigma = cfg["dh_terrain"]
        else:
            sigma = sigma_footprint(alt, pit, cfg=cfg)
        c, parts = confidence(n, passes, gsd, clip_ratio, sigma, cfg)
        return {
            "covered": True,
            "confidence": round(c, 4),
            "grade": grade(c),
            "r_space": round(parts["r_space"], 4),
            "r_support": round(parts["r_support"], 4),
            "r_clip": round(r_clip, 4),
            "sigma_m": round(sigma, 3),
            "clipped_ratio": round(clip_ratio, 4),
            "type": "clipped" if clip_ratio > 0.5 else "hard_boundary",
            "basis": {
                "frames": n,
                "passes": passes,
                "gsd_m_per_px": round(gsd, 4),
                "can_resolve_cm": round(gsd * 100, 1),
                "slant_m": round(slant, 1),
                "alt_m": round(alt, 1),
                # 必须 round：SRT 读出来的是 1 位小数（如 -29.3），但存进 .npz 时
                # 经过 float32，直接吐出来会变成 -29.299999237060547 这种精度尾巴
                # （界面上真的这么显示过）。
                "pitch_deg": round(pit, 1),
                "yaw_deg": round(self.frame_yaw[fi], 1),
                "zoom_used": bool(self.zoom_count[iy, ix]),
                # 注意：这是**遥测采样下标**，不是视频帧号；换算成秒用下面的 time_s
                "frame_index": fi,
                "time_s": round(self.frame_time(fi), 2),
            },
            "accuracy_note": (
                f"Flat-ground model; footprint boundary is uncertain to about "
                f"±{sigma:.1f} m. The whole map also carries a ±{cfg['d_gnss']} m "
                f"positioning offset. Attitude accuracy is estimated from the SRT "
                f"quantisation step plus a safety margin, and has not been verified "
                f"against a surveyed target."
            ),
        }

    def frame_time(self, frame_index):
        """**遥测采样下标 -> 视频内的秒数**。

        唯一权威来源是建网格时存下来的 `frame_times[]`（即 SRT 的 cue 时间，
        与视频时间轴一致）。没有它（旧网格）才退回按帧率折算 ——
        那个折算只在"采样点均匀分布"时才对，实测会积到十几秒的误差，
        所以新网格一定要走到上面那条路。
        """
        ft = getattr(self, "frame_times", None)
        if ft is not None and 0 <= frame_index < len(ft) and float(ft[frame_index]) > 0:
            return float(ft[frame_index])
        return video_seconds_of_frame(frame_index)

    def sample_of_frame(self, frame_index):
        """**视频帧号 -> 遥测采样下标**（见 telemetry_sample_of_frame 的说明）。"""
        return telemetry_sample_of_frame(frame_index)

    # ---------- 存取 ----------
    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            lat0=self.lat0, lng0=self.lng0, cell=self.cell,
            nx=self.nx, ny=self.ny, half=self.half,
            half_x=self.hx(), half_y=self.hy(),
            count=self.count, gsd_best_map=self.gsd_best_map,
            frame_at_min=self.frame_at_min, last_frame=self.last_frame,
            clipped_count=self.clipped_count, zoom_count=self.zoom_count,
            frames_total=self.frames_total, frames_used=self.frames_used,
            frames_skipped=self.frames_skipped,
            frames_wide=self.frames_wide, frames_zoom=self.frames_zoom,
            srt_name=self.srt_name, takeoff_elev=self.takeoff_elev,
            long_px=self.long_px,
            frame_focal=np.asarray(self.frame_focal, dtype=np.float32),
            frame_alt=np.asarray(self.frame_alt, dtype=np.float32),
            frame_yaw=np.asarray(self.frame_yaw, dtype=np.float32),
            frame_pitch=np.asarray(self.frame_pitch, dtype=np.float32),
            # 逐帧单像素角：360 素材没有焦距，靠它才能反推斜距/算 GSD
            frame_ang_per_px=np.asarray(getattr(self, "frame_ang_per_px", []) or [],
                                        dtype=np.float32),
            # 时刻用 float64：它要和视频时间轴对齐，float32 的精度尾巴会带进界面
            frame_times=np.asarray(self.frame_times or [], dtype=np.float64),
        )

    @classmethod
    def load(cls, path: Path) -> "CoverageGrid":
        with np.load(path) as z:
            # 旧的网格用「原点是中心 + 单一 half」建，新的是「原点是西南角 +
            # half_x/half_y」。两者**不能互换** —— 把旧网格按新语义读，坐标会
            # 整体偏移半个网格宽，热力图和点查询都会静默错位。
            # 所以这里宁可**明确报错**（上层会据此重建），也不要给出错的结果。
            if "half_x" not in z.files:
                raise ValueError(
                    "This coverage grid was built by an older version whose origin "
                    "convention differs. Rebuild it (Build button) to get correct bounds."
                )
            return cls(
                lat0=float(z["lat0"]), lng0=float(z["lng0"]),
                cell=float(z["cell"]), nx=int(z["nx"]), ny=int(z["ny"]),
                half=float(z["half"]),
                half_x=float(z["half_x"]), half_y=float(z["half_y"]),
                count=z["count"], gsd_best_map=z["gsd_best_map"],
                frame_at_min=z["frame_at_min"], last_frame=z["last_frame"],
                clipped_count=z["clipped_count"], zoom_count=z["zoom_count"],
                frames_total=int(z["frames_total"]), frames_used=int(z["frames_used"]),
                frames_skipped=int(z["frames_skipped"]),
                frames_wide=int(z["frames_wide"]), frames_zoom=int(z["frames_zoom"]),
                srt_name=str(z["srt_name"]), takeoff_elev=float(z["takeoff_elev"]),
                long_px=int(z["long_px"]),
                frame_focal=[float(v) for v in z["frame_focal"]],
                frame_alt=[float(v) for v in z["frame_alt"]],
                frame_yaw=[float(v) for v in z["frame_yaw"]],
                frame_pitch=[float(v) for v in z["frame_pitch"]],
                frame_ang_per_px=([float(v) for v in z["frame_ang_per_px"]]
                                  if "frame_ang_per_px" in z.files else []),
                # 缺失时留空 —— frame_time() 会退回按帧率折算（旧网格）
                frame_times=([float(v) for v in z["frame_times"]]
                             if "frame_times" in z.files else []),
            )


# ============================================================
# 栅格化：一次扫描同时更新 count 与 min_slant2
# ============================================================

def _raster_frame(pts, height, g, frame_idx, clipped, wide, gx0, gy0, cell,
                  col_e2, ang_per_px, de, dn):
    """把一个四边形盖进网格，同时更新 count / gsd_best / frame_at_min。

    三个坑（都是被实测逼出来的）：

    1. **行内"到无人机的水平距离²"是二次多项式**（列号），可以整段向量运算，
       不需要 sqrt、不需要 meshgrid —— 这是性能的关键（12181 帧 29 s）。
    2. **必须用"相对无人机"的偏移，不能用格子自身的绝对坐标**。
       `d² = (列东 − 无人机东)² + (行北 − 无人机北)² + 高度²`。
       曾漏掉 `− de / − dn`，等于把网格原点当成了无人机；
       无人机离原点 800 m 时斜距算成 938 m（真值 130 m），GSD 差 7 倍。
    3. **存的是最小 GSD，不是最小斜距**：`GSD = 斜距 × 单像素角`，
       而单像素角随焦距变（24mm 与 172mm 差 7 倍）。用"最小斜距"会在
       不同焦距档之间选错帧。直接比较 GSD 同样便宜。
    """
    nx, ny = g.nx, g.ny
    xs = (pts[0][0], pts[1][0], pts[2][0], pts[3][0])
    ys = (pts[0][1], pts[1][1], pts[2][1], pts[3][1])
    iy0 = max(0, int((min(ys) - gy0) / cell))
    iy1 = min(ny - 1, int((max(ys) - gy0) / cell))
    if iy1 < iy0:
        return 0
    cnt = g.count
    gb = g.gsd_best_map
    fam = g.frame_at_min
    lf = g.last_frame
    cc = g.clipped_count
    zc = g.zoom_count
    de2 = de * de
    h2 = height * height
    # 每帧只算一次的前缀项；行内再补 (行北 − 无人机北)²
    base = col_e2 - 2.0 * de * g.cols + de2 + h2
    stamped = 0
    for iy in range(iy0, iy1 + 1):
        yc = gy0 + (iy + 0.5) * cell
        dy = yc - dn
        dy2 = dy * dy
        xsec = []
        for k in range(4):
            x1, y1 = xs[k], ys[k]
            x2, y2 = xs[(k + 1) % 4], ys[(k + 1) % 4]
            if (y1 <= yc < y2) or (y2 <= yc < y1):
                xsec.append(x1 + (yc - y1) * (x2 - x1) / (y2 - y1))
        if len(xsec) < 2:
            continue
        xsec.sort()
        for k in range(0, len(xsec) - 1, 2):
            a = max(0, int((xsec[k] - gx0) / cell))
            b = min(nx - 1, int((xsec[k + 1] - gx0) / cell))
            if b < a:
                continue
            sl = slice(a, b + 1)
            cnt[iy, sl] += 1
            # 逐格精确斜距：d² = (列东 − 无人机东)² + (行北 − 无人机北)² + 高度²
            # 曾试过"行内斜距近似常数"来省 sqrt —— 76° 广角下误差高达 69%，已弃用。
            slant = np.sqrt(base[sl] + dy2)
            gsd = slant * ang_per_px
            cur = gb[iy, sl]
            # 先算新值再一次性赋值：np.where 返回的是整个切片的新数组，
            # 若直接 a[iy,sl]=np.where(better,new,cur) 且 better 相对旧值算，
            # 不需要更新的格子也会被写成当前帧的值，污染后续比较。
            better = (cur <= 0.0) | (gsd < cur)
            if better.any():
                gb[iy, sl] = np.where(better, gsd, cur)
                fam[iy, sl] = np.where(better, frame_idx, fam[iy, sl])
            lf[iy, sl] = frame_idx
            if clipped:
                cc[iy, sl] += 1
            if not wide:
                zc[iy, sl] += 1
            stamped += b - a + 1
    return stamped


# ============================================================
# 360 / 全景：一帧覆盖的是**圆环**，不是四边形
# ============================================================

# 360 看多远：**复用针孔那套的收口参数**（CLIP_PER_ALT × 高度，下限 CLIP_MIN）。
#
# 为什么复用而不是另设一组数字：针孔那边已经解决了"仰角趋近 0 时 d→∞"这个
# 一模一样的问题，而且它的默认值是实测调过的。360 再发明一套只会多一个
# 没人验证过的旋钮。副作用是两边的网格尺度一致，可比性也更好。
SPHERE_FAR_PER_ALT = CLIP_PER_ALT
SPHERE_FAR_MIN = CLIP_MIN

# 360 的"单像素角"用什么焦距做代理。
#
# 360 相机没有可变焦距，但**必须有**一个单像素角才能算 GSD（= 斜距 × 单像素角）。
# 取 24 mm 等效（即广角子镜头的角分辨率，约 0.0195°/px）作为代理 ——
# 理由是 Avata 360 的球面图来源于两颗广角鱼眼，其角分辨率量级与 24mm 广角一致。
# 这**只是一个代理**（真实值取决于那颗鱼眼的实际视场与像素数），
# 会让 GSD 有一个**乘性比例误差**，但不影响覆盖范围（覆盖只由高度与仰角决定）。
SPHERE_PROXY_FOCAL_MM = 24.0


def sphere_ring(height, pitch_deg=None, far_per_alt=SPHERE_FAR_PER_ALT,
                far_min=SPHERE_FAR_MIN):
    """全景一帧覆盖的地面圆环 (内半径, 外半径)，单位米。

    ## 为什么和针孔完全不同

    等距柱状图里 **仰角只由行决定、与方位无关**，所以

        d = h / tan(仰角)

    与方位无关 —— 一帧覆盖的地面就是一个**圆环**，没有"画面边缘切掉"这回事。

    ## 内半径 = 正下方的盲区

    若镜头沿某方向俯仰了 pitch，正下方的盲区半径 = h·tan(|pitch|)。
    但 **360 素材的 SRT 里没有任何云台姿态**（`gb_pitch` 一个都没有），
    所以这个盲区其实**无法从数据得知**。

    这里的处理：给 `pitch_deg` 就按它算；不给（None）就取 **0** —— 即
    "假设整个下半球都被拍到"。对 360 相机这是**保守且基本正确**的假设
    （整球覆盖，正常安装下能拍到正下方）；代价是可能低估了正下方的盲区。
    **这是已知的近似，写在这里免得以后被当成 bug。**

    ## 外半径为什么要截断

    仰角趋近 0 时 d → ∞。按 `far = max(CLIP_MIN, CLIP_PER_ALT × h)` 截断
    （与针孔那套同参数）—— 这不是几何结论，是**取一个有用的工作范围**：
    更远处即使拍到，解像度也已经低到没有判读价值。
    """
    if height is None or height <= 0:
        return None
    far = max(far_min, far_per_alt * height)
    if pitch_deg is None:
        near = 0.0
    else:
        p = math.radians(min(89.0, abs(float(pitch_deg))))
        near = height * math.tan(p)
    if near >= far:
        return None
    return near, far


def _raster_sphere_ring(height, near, far, g, frame_idx, wide, gx0, gy0, cell,
                        col_e2, ang_per_px, de, dn):
    """把一个**圆环**盖进网格（精确判定，不做多边形近似）。

    为什么单写一个而不用 `_raster_frame`：那个是"按行与四边形的交点对"填充的，
    靠 even-odd 规则；圆环是**带洞**的区域，用多边形近似填不对（除非拆成很多扇形）。

    而圆环的判据极简单：`near² <= d² <= far²`，而 `d²` 在行内是列号的**二次多项式**
    —— 所以可以整段向量运算，和针孔那套同样快，而且比多边形近似**更准**。
    """
    nx, ny = g.nx, g.ny
    iy0 = max(0, int((dn - far - gy0) / cell))
    iy1 = min(ny - 1, int((dn + far - gy0) / cell))
    if iy1 < iy0:
        return 0
    cnt = g.count
    gb = g.gsd_best_map
    fam = g.frame_at_min
    lf = g.last_frame
    zc = g.zoom_count
    de2 = de * de
    h2 = height * height
    base = col_e2 - 2.0 * de * g.cols + de2 + h2
    near2, far2 = near * near, far * far
    # 远景帧不参与"变焦"计数：广角 24mm 与 360 的"焦距"不是一回事
    stamped = 0
    for iy in range(iy0, iy1 + 1):
        yc = gy0 + (iy + 0.5) * cell
        dy = yc - dn
        d2 = base + dy * dy                 # 各列到无人机的水平距离² + 高度²
        hit = (d2 >= near2) & (d2 <= far2)
        if not hit.any():
            continue
        # 取命中列的最小/最大下标，整段赋值（与针孔那条同样的向量化思路）
        idx = np.nonzero(hit)[0]
        a, b = int(idx[0]), int(idx[-1])
        sl = slice(a, b + 1)
        sub = hit[sl]
        cnt[iy, sl] += sub
        slant = np.sqrt(d2[sl])
        gsd = slant * ang_per_px
        cur = gb[iy, sl]
        better = sub & ((cur <= 0.0) | (gsd < cur))
        if better.any():
            gb[iy, sl] = np.where(better, gsd, cur)
            fam[iy, sl] = np.where(better, frame_idx, fam[iy, sl])
        lf[iy, sl] = np.where(sub, frame_idx, lf[iy, sl])
        stamped += int(sub.sum())
    return stamped


def build_from_telemetry(tele, lats, lngs, srt_name="", cell=1.0,
                         takeoff_elev=0.0, progress=None):
    """从遥测 + 定位序列构建覆盖网格。

    tele     project_manager.load_srt_telemetry() 的返回
    lats/lngs 与 tele 对齐的逐点经纬度（步长 TELEMETRY_STEP）
    """
    cell = float(cell)
    n = min(len(lats), len(lngs), tele.get("count", 0))
    if n == 0:
        raise ValueError("没有可用的遥测/定位点")

    clip_max = CLIP_MIN
    for i in range(n):
        a = tele["alt"][i]
        if a:
            clip_max = max(clip_max, max(CLIP_MIN, CLIP_PER_ALT * a))

    mx = M_PER_DEG_LNG * math.cos(math.radians(lats[0]))

    # ------------------------------------------------------------------
    # 第一遍：把每帧的足迹算出来，取**实际包围盒**。
    #
    # 网格范围必须按实际航线定，不能"以第一个点为心的方形"：
    # 一趟能飞好几公里，实测某一趟南北向飞了 -4222..438 m，
    # 而旧网格只有 ±1377 m，南边 2845 m 的航线被切掉，热力图只剩一块矩形。
    #
    # 外扩也不能一律用"最大收口距离"：那是最坏情况的半径，四边均匀铺开会让
    # 网格大出一倍（实测 203 公顷的航线撑出 3700×7400 的网格）。
    # 所以直接取每帧足迹四角的包络 —— 既保证不漏，又贴得紧。
    # ------------------------------------------------------------------
    footprints = []          # (i, shifted_pts, alt, foc, clipped, wide, e_d, n_d)
    e_lo = n_lo = float("inf")
    e_hi = n_hi = float("-inf")
    for i in range(n):
        pit = tele["pitch"][i]
        yaw = tele["yaw"][i]
        alt = tele["alt"][i]
        if alt is None or alt <= 0:
            footprints.append(None)
            continue
        # ---- 360 / 全景分支 ----
        # SRT 里**没有** yaw/pitch（`gb_yaw`/`gb_pitch` 一个字段都没有），
        # 但全景的覆盖是**圆环**，只需要高度与位置 —— 所以这条路径能建。
        # 见 sphere_ring()：不与针孔混用，几何不同。
        if pit is None or yaw is None:
            ring = sphere_ring(alt, pit)
            if ring is None:
                footprints.append(None)
                continue
            near, far = ring
            e_d = (lngs[i] - lngs[0]) * mx
            n_d = (lats[i] - lats[0]) * M_PER_DEG_LAT
            # 用"外接正方形"进包围盒（圆环本身由 _raster_sphere_ring 精确判定）
            pts = ((e_d - far, n_d - far), (e_d + far, n_d - far),
                   (e_d + far, n_d + far), (e_d - far, n_d + far))
            footprints.append(("sphere", i, pts, alt, near, far))
            for (px, py) in pts:
                if px < e_lo:
                    e_lo = px
                if px > e_hi:
                    e_hi = px
                if py < n_lo:
                    n_lo = py
                if py > n_hi:
                    n_hi = py
            continue
        if pit >= 0:
            footprints.append(None)
            continue
        foc = tele["focal"][i] or 24.0
        clip = max(CLIP_MIN, CLIP_PER_ALT * alt)
        pts, clipped = frame_footprint(alt, yaw, pit, foc, clip)
        if pts is None:
            footprints.append(None)
            continue
        e_d = (lngs[i] - lngs[0]) * mx
        n_d = (lats[i] - lats[0]) * M_PER_DEG_LAT
        shifted = tuple((p[0] + e_d, p[1] + n_d) for p in pts)
        footprints.append((i, shifted, alt, foc, clipped, foc <= WIDE_MAX_FOCAL))
        for (px, py) in shifted:
            if px < e_lo:
                e_lo = px
            if px > e_hi:
                e_hi = px
            if py < n_lo:
                n_lo = py
            if py > n_hi:
                n_hi = py

    if not math.isfinite(e_lo):               # 一帧都没算出来
        raise ValueError("所有帧都算不出足迹（俯角/高度数据可能有问题）")

    e0, e1 = e_lo - BOUND_MARGIN, e_hi + BOUND_MARGIN
    n0, n1 = n_lo - BOUND_MARGIN, n_hi + BOUND_MARGIN

    half_x = max(1.0, (e1 - e0) / 2.0)
    half_y = max(1.0, (n1 - n0) / 2.0)
    nx = int(math.ceil((e1 - e0) / cell)) + 1
    ny = int(math.ceil((n1 - n0) / cell)) + 1

    # 网格原点 = 西南角（不再是中心）
    lat0 = lats[0] + n0 / M_PER_DEG_LAT
    lng0 = lngs[0] + e0 / mx
    e_off, n_off = e0, n0

    g = CoverageGrid(lat0=lat0, lng0=lng0, cell=cell, nx=nx, ny=ny,
                     half=max(half_x, half_y), half_x=half_x, half_y=half_y,
                     srt_name=srt_name, takeoff_elev=takeoff_elev,
                     frames_total=n, long_px=long_px_for(srt_name))
    # 首条遥测点（中心约定时的基准）—— 供诊断脚本对照，也便于"回到起点"
    g.start_lat, g.start_lng = lats[0], lngs[0]

    g.count = np.zeros((ny, nx), dtype=np.int32)
    g.gsd_best_map = np.zeros((ny, nx), dtype=np.float32)
    g.frame_at_min = np.full((ny, nx), -1, dtype=np.int32)
    g.last_frame = np.full((ny, nx), -1, dtype=np.int32)
    g.clipped_count = np.zeros((ny, nx), dtype=np.int32)
    g.zoom_count = np.zeros((ny, nx), dtype=np.int32)

    gx0, gy0 = 0.0, 0.0
    # 列心的东向偏移（整张网格共用）
    cols = (np.arange(nx) + 0.5) * cell
    col_e2 = (cols * cols).astype(np.float64)
    g.cols = cols.astype(np.float64)

    # 逐帧参数表：**必须按原始帧号 i 索引**（有跳帧时不能用 append 的顺序号）
    # 曾经用 append，导致 frame_at_min 存的是原始帧号、而 frame_focal 是有效帧序号，
    # 两者错位 -> 查出来的焦距不对 -> GSD 算错。
    g.frame_focal = [0.0] * n
    g.frame_alt = [0.0] * n
    g.frame_yaw = [0.0] * n
    g.frame_pitch = [0.0] * n
    # 逐帧单像素角（弧度）。360 没有焦距，靠这个才能反推斜距/算 GSD。
    g.frame_ang_per_px = [0.0] * n
    # 逐采样点的视频内秒数（SRT cue 时间）。
    # 存下来是关键：`times` 是唯一权威的时刻来源，光靠下标按帧率折算会偏十几秒。
    # 传进来的 times 与 lats/lngs 同长同序；缺失时留空（frame_time 会退回收折算）。
    _times = tele.get("times") or []
    g.frame_times = [float(_times[i]) if i < len(_times) else 0.0 for i in range(n)]

    # 第一遍的足迹存的是「相对首点」的坐标；lat0/lng0 也是从首点推出来的，
    # 所以这里只需要一个常量平移就能落到网格坐标上。
    de = (lngs[0] - g.lng0) * mx
    dn = (lats[0] - g.lat0) * M_PER_DEG_LAT

    for fp in footprints:
        if fp is None:
            g.frames_skipped += 1
            continue

        # ---- 360 / 全景：圆环 ----
        if fp[0] == "sphere":
            _, i, pts0, alt, near, far = fp
            e_d = (lngs[i] - g.lng0) * mx
            n_d = (lats[i] - g.lat0) * M_PER_DEG_LAT
            g.frame_alt[i] = alt
            # 360 没有焦距/云台姿态，逐帧表里留 0（下游按 0 处理，不猜）
            g.frame_focal[i] = 0.0
            g.frame_yaw[i] = 0.0
            g.frame_pitch[i] = 0.0
            # 360 是整球覆盖，算"广角"（不占变焦计数）
            g.frames_wide += 1
            # 单像素角用 **广角子镜头** 的值做代理（见常量说明）
            app = rad_per_px(SPHERE_PROXY_FOCAL_MM, g.long_px)
            g.frame_ang_per_px[i] = app
            _raster_sphere_ring(alt, near, far, g, i, True, gx0, gy0, cell,
                                col_e2, app, e_d, n_d)
            g.frames_used += 1
            if progress and (i % 500 == 0):
                progress(i, n)
            continue

        i, pts0, alt, foc, clipped, wide = fp

        e_d = (lngs[i] - g.lng0) * mx
        n_d = (lats[i] - g.lat0) * M_PER_DEG_LAT
        shifted = tuple((p[0] + de, p[1] + dn) for p in pts0)

        g.frame_focal[i] = foc
        g.frame_alt[i] = alt
        g.frame_yaw[i] = tele["yaw"][i]
        g.frame_pitch[i] = tele["pitch"][i]

        g.frame_focal[i] = foc
        g.frame_alt[i] = alt
        g.frame_yaw[i] = tele["yaw"][i]
        g.frame_pitch[i] = tele["pitch"][i]

        if wide:
            g.frames_wide += 1
        else:
            g.frames_zoom += 1

        app = rad_per_px(foc, g.long_px)
        g.frame_ang_per_px[i] = app
        _raster_frame(shifted, alt, g, i, clipped, wide, gx0, gy0, cell, col_e2, app, e_d, n_d)
        g.frames_used += 1
        if progress and (i % 500 == 0):
            progress(i, n)

    return g


# ============================================================
# 置信度
# ============================================================

def sigma_footprint(height, pitch_deg, dh=None, cfg=None):
    """足迹边界的形变不确定度（米）：云台俯角项 + 地表高差项。

    dh 可传**逐格数组**（将来接 DEM 时用），函数结构不变。
    """
    cfg = cfg or CONF
    dh = cfg["dh_terrain"] if dh is None else dh
    th = math.radians(abs(pitch_deg))
    s, t = math.sin(th), math.tan(th)
    if s < 1e-6 or t < 1e-6:
        return float("inf")
    d_att = height * math.radians(cfg["d_pitch"]) / (s * s)
    d_ter = dh / t
    return math.hypot(d_att, d_ter)


def r_space(sigma, cfg=None):
    cfg = cfg or CONF
    if not math.isfinite(sigma):
        return 0.0
    return math.exp(-sigma / cfg["sigma_ref"])


def r_support(frames, passes, gsd, cfg=None):
    cfg = cfg or CONF
    f = min(1.0, frames / cfg["frames_full"]) if frames else 0.0
    p = min(1.0, passes / cfg["passes_full"]) if passes else 0.0
    g = min(1.0, cfg["gsd_good"] / gsd) if gsd and gsd > 0 else 0.0
    if f <= 0 or p <= 0 or g <= 0:
        return 0.0
    return (f * p * g) ** (1.0 / 3.0)


def confidence(frames, passes, gsd, clip_ratio, sigma, cfg=None):
    """综合置信度 0~1。clip_ratio 是"用到收口的帧占比"（0~1），不是布尔。"""
    cfg = cfg or CONF
    rs = r_space(sigma, cfg)
    ru = r_support(frames, passes, gsd, cfg)
    w = cfg["w_space"]
    c = ((rs ** w) * (ru ** (1 - w))) ** cfg["gamma"]
    c = max(c, cfg["min_floor"] * min(rs, ru))
    r_clip = 1.0 - (1.0 - cfg["clip_penalty"]) * max(0.0, min(1.0, clip_ratio))
    c *= r_clip
    return c, {"r_space": rs, "r_support": ru, "r_clip": r_clip}


def grade(c):
    return ("high" if c >= 0.80 else
            "medium" if c >= 0.55 else
            "low" if c >= 0.30 else "very_low")


# ============================================================
# 自测
# ============================================================

if __name__ == "__main__":
    print("coverage 模块自测（v2）")
    h, f = 100.0, 24.0
    pts, clipped = frame_footprint(h, 0.0, -90.0, f, 3000.0)
    hf, vf = fov_of(f)
    print(f"  正下视 100m：宽 {max(p[0] for p in pts)-min(p[0] for p in pts):.1f} m"
          f"（应 {2*h*math.tan(math.radians(hf/2)):.1f}）"
          f"  高 {max(p[1] for p in pts)-min(p[1] for p in pts):.1f} m"
          f"（应 {2*h*math.tan(math.radians(vf/2)):.1f}）  clipped={clipped}")
    print("  置信度：")
    for pitch, fr, ps, gsd, cr in ((85, 400, 5, 0.03, 0.0), (30, 300, 3, 0.08, 0.0),
                                   (30, 300, 3, 0.08, 0.86), (30, 10, 1, 0.10, 0.0),
                                   (15, 200, 4, 0.40, 0.3)):
        s = sigma_footprint(97.0, -pitch)
        c, parts = confidence(fr, ps, gsd, cr, s)
        print(f"    俯角-{pitch:>2} {fr:>4}帧 {ps}次 gsd{gsd:.2f} 收口{cr:.2f} "
              f"σ={s:5.2f} -> {c:.3f} ({grade(c)})  "
              f"r_space={parts['r_space']:.3f} r_support={parts['r_support']:.3f}")
