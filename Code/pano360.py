# -*- coding: utf-8 -*-
"""Avata 360 双鱼眼 -> 等距柱状（equirectangular）重投影。

## 为什么需要它

Avata 360 的 `.OSV` 是**两条流**：流 0 = 朝上的镜头、流 1 = 朝下的镜头，
都是 3840×3840 的圆形鱼眼。要让这个素材能用（预览、定北向、算覆盖），
第一步必须把两路拼成一张**等距柱状全景**。

## 实测出来的几何（2026-10-14，室外素材）

- 圆正好**外接于正方形画面**：四边中点都在圆上，半径 = 边长/2（实测 960 图上 480px）
- 圆心 ≈ 画面中心（实测质心 478.4, 481.8 vs 图心 480,480 —— 偏差 < 2px）
- 投影是**等距投影**（equidistant）：`r = R · θ / (FOV/2)`
- `FOV ≈ 200°`（不是 180°）

**FOV 是怎么定的**：鱼眼视场下限是 180°（两颗刚好覆盖全球）。
按 180° 重投影后，**地平线会偏离赤道**；按 200° 重投影后地平线**水平地落在
正中间**（纬度 0）—— 这是客观判据，不靠"看着像"。

> 试过的错误方法：拿两路的**径向亮度剖面**做互相关去解角度尺度，
> 得到 S=604px => FOV 286°（物理上不可能）。原因是两个剖面都只是
> "山-天-地"的相似结构，任何对齐都会相关 —— **弱判据**。
> 换"地平线必须落在赤道"这种**有物理硬约束**的判据才靠得住。

## 用法

    g = Fisheye360(fov_deg=200.0)
    equi = g.stitch(frame_up, frame_down)      # 两张 HxWx3 -> Hx(2H)x3

两个 input 必须是**同一时刻**的两路帧、同尺寸、正方形。
"""
from __future__ import annotations

import math

import numpy as np

# 默认水平视场（度）。见上面的标定说明。
DEFAULT_FOV = 200.0

# 等距柱状的宽高比恒为 2:1
EQUI_ASPECT = 2


def _sample_bilinear(img: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """在 img 上按浮点坐标双线性采样。越界处返回 0（黑）。"""
    h, w = img.shape[:2]
    x0 = np.floor(xs).astype(np.int32)
    y0 = np.floor(ys).astype(np.int32)
    fx = (xs - x0)[..., None]
    fy = (ys - y0)[..., None]
    x0c = np.clip(x0, 0, w - 2)
    y0c = np.clip(y0, 0, h - 2)
    p00 = img[y0c, x0c]
    p01 = img[y0c, x0c + 1]
    p10 = img[y0c + 1, x0c]
    p11 = img[y0c + 1, x0c + 1]
    out = (p00 * (1 - fx) * (1 - fy) + p01 * fx * (1 - fy)
           + p10 * (1 - fx) * fy + p11 * fx * fy)
    inside = (xs >= 0) & (xs < w - 1) & (ys >= 0) & (ys < h - 1)
    return out * inside[..., None]


class Fisheye360:
    """一颗朝上 + 一颗朝下的鱼眼，拼成等距柱状全景。

    坐标约定（**很重要**，后面定北向要用）：
      · 等距柱状的**列**是方位角 lon（-180..180），行是纬度 lat（+90..-90）
      · 这里把 lon=0 定义为**"上镜头"像面的 +Y 方向**（即鱼眼图的正下方）
      · lon=+90° 对应上镜头像面的 +X（正右方）
    也就是说 **lon 的零点由相机的机械朝向决定**，与"北"无关 ——
    这正是缺少云台姿态时唯一未知的那一个自由度（绕竖轴的旋转）。
    """

    def __init__(self, fov_deg: float = DEFAULT_FOV, cx: float | None = None,
                 cy: float | None = None, radius: float | None = None):
        self.fov_deg = float(fov_deg)
        self.cx = cx          # 圆心（像素）；None = 用图心
        self.cy = cy
        self.radius = radius  # 圆半径（像素）；None = 用边长/2

    # ---------------- 核心：等距柱状 -> 两张像面上的坐标 ----------------
    def _direction_grid(self, ew: int, eh: int):
        """等距柱状像素 -> **世界系**单位方向 (x=东/右, y=北/前, z=天)。"""
        lon = (np.arange(ew) + 0.5) / ew * 2 * np.pi - np.pi
        lat = np.pi / 2 - (np.arange(eh) + 0.5) / eh * np.pi
        LON, LAT = np.meshgrid(lon, lat)
        cz = np.sin(LAT)
        rho = np.cos(LAT)
        return LON, cz, rho * np.sin(LON), rho * np.cos(LON)

    def stitch(self, up: np.ndarray, down: np.ndarray,
               ew: int | None = None, ring_inner: float = 0.99) -> np.ndarray:
        """两路鱼眼 -> 等距柱状。ew = 输出宽度（高度为其一半）。

        `ring_inner`：遮掉每路 `r/R > 这个值` 的最外圈。**默认 0.99**，
        只切掉紧贴边缘的那道**细白线**（实测图像圆真实边缘在 r/R=0.998）。

        **不要设太大**：实测把遮罩设到 0.93 会人为造出一条横贯全景的**黑带**
        （因为 0.93 对应极角 96.7°，两颗镜头各切 6.7° 就多出 13° 的假缺口）。
        真实情况是两颗镜头在赤道附近**重叠 27.6°**（103.8 + 103.8 − 180），
        根本没有缺口。

        ## 像面朝向（这里踩过一个大坑，写清楚）

        像面坐标 (dx, dy) 在**两个镜头上含义相同**：+X = 画面右、+Y = 画面上。
        两颗镜头背靠背，各自的相机基（X, Y, Z）——Z 是光轴：

            上镜头: X=东   Y=北(前)  Z=天顶(+Z)     -> 世界 = (dx,  dy,  cz)
            下镜头: X=东   Y=南      Z=天底(-Z)     -> 世界 = (dx, -dy, -cz)

        所以

            phi = atan2(dx, dy)      # **两个镜头用同一个式子**
            上: 世界方向 = (sinθ·cosφ,  sinθ·sinφ,  cosθ)
            下: 世界方向 = (sinθ·cosφ, -sinθ·sinφ, -cosθ)

        **错误做法**（我第一版）：把下镜头的 phi 写成 `-atan2(dx,-dy)`，
        把"光轴反向"误当成了"像面镜像"。后果很隐蔽 —— 天空区域的像素被下镜头
        抢走，太阳被填到地平线**以下**（实测高度角 -4.8°，而真值是 +42.8°）。
        正确性判据：太阳的量测高度角必须等于理论值（见 pano360_north.py 的自检）。
        """
        if up.shape != down.shape:
            raise ValueError("两路尺寸必须一致：%s vs %s" % (up.shape, down.shape))
        h, w = up.shape[:2]
        if h != w:
            raise ValueError("鱼眼帧必须是正方形：%s" % (up.shape,))
        if ew is None:
            ew = w
        eh = ew // EQUI_ASPECT

        cx = (w - 1) / 2.0 if self.cx is None else float(self.cx)
        cy = (h - 1) / 2.0 if self.cy is None else float(self.cy)
        R = (w - 1) / 2.0 if self.radius is None else float(self.radius)
        half = np.deg2rad(self.fov_deg / 2.0)

        _LON, cz, dx, dy = self._direction_grid(ew, eh)
        out = np.zeros((eh, ew, up.shape[2]), dtype=up.dtype)
        filled = np.zeros((eh, ew), dtype=bool)

        # 每路外圈那道细白线所在的像素：**不参与赋值**（跳过），而不是涂黑。
        #
        # 为什么不能涂黑（踩过）：涂黑等于让这一路拿**黑像素**去占位，
        # 于是它把另一路**本来有效**的内容盖掉了 —— 实测在全景里留下一条
        # 横贯的**黑带**（纬度 −10° 附近）。跳过就能让另一路补上。
        yy, xx = np.mgrid[0:h, 0:w]
        rr_img = np.hypot(xx - cx, yy - cy) / max(R, 1e-9)
        ring_mask = rr_img > ring_inner

        # **按"极角更小"择优**，而不是"上镜头优先"。
        #
        # 为什么（踩过）：鱼眼外圈那道白环**是不对称的**（实测上镜头 0° 方位
        # 在 r/R 0.99~1.00、270° 方位在 0.95~0.96）。"上镜头优先"会让它用自己的
        # **边缘最差区域**去覆盖本该由下镜头**中心区**负责的地带 ——
        # 于是全景地平线附近出现一道白色弧（真的出现过）。
        # 按极角择优 = 永远选离光轴更近、畸变更小的那一路，白环自然退到
        # 各自视场最边缘、且只在两路都够不到的地方才被采样到。
        th_u = np.arccos(np.clip(cz, -1.0, 1.0))
        th_d = np.arccos(np.clip(-cz, -1.0, 1.0))
        # 上镜头当 th_u <= th_d，即它在光轴 90° 以内
        prefer_up = th_u <= th_d

        for img, sign, prefer in ((up, 1.0, prefer_up), (down, -1.0, ~prefer_up)):
            cos_t = np.clip(sign * cz, -1.0, 1.0)
            theta = np.arccos(cos_t)
            r = R * (theta / half)
            # phi 与 sign 无关（像面 +X/+Y 的含义两路相同）
            phi = np.arctan2(dx, dy)
            sx = cx + r * np.cos(phi)
            sy = cy + r * np.sin(phi)
            val = _sample_bilinear(img, sx, sy)
            # 采样点落在白环上就跳过（让另一路去填），不拿黑像素占位
            rr_s = np.hypot(sx - cx, sy - cy) / max(R, 1e-9)
            on_ring = rr_s > ring_inner
            ok = (r <= R) & (~filled) & (~on_ring) & prefer
            out[ok] = val[ok]
            filled |= ok

        # 兜底：还有没填上的（两路都够不到或都在环上），用"不限 prefer"再补一次，
        # 以免留黑洞。这些像素很少，质量差也无所谓。
        if not filled.all():
            for img, sign in ((up, 1.0), (down, -1.0)):
                cos_t = np.clip(sign * cz, -1.0, 1.0)
                theta = np.arccos(cos_t)
                r = R * (theta / half)
                phi = np.arctan2(dx, dy)
                sx = cx + r * np.cos(phi)
                sy = cy + r * np.sin(phi)
                val = _sample_bilinear(img, sx, sy)
                ok = (r <= R) & (~filled)
                out[ok] = val[ok]
                filled |= ok
        return out

    def coverage_mask(self, ew: int | None, eh: int) -> np.ndarray:
        """每个等距柱状像素有没有被拍到（用于确认没有空洞）。"""
        R = np.ones(1)  # 占位，真正的判据在 stitch 内部
        _LON, cz, _dx, _dy = self._direction_grid(ew, eh)
        half = np.deg2rad(self.fov_deg / 2.0)
        # 只要"离光轴最近的那颗镜头"的夹角 <= half 就算覆盖到
        theta_min = np.minimum(np.arccos(np.clip(cz, -1, 1)),
                               np.arccos(np.clip(-cz, -1, 1)))
        return theta_min <= half


def perspectives_from_equirect(equi: np.ndarray, yaw_deg: float, pitch_deg: float,
                              fov_deg: float = 75.0, out_w: int = 480,
                              out_h: int | None = None) -> np.ndarray:
    """从等距柱状全景裁一张**透视小图**（小孔相机视角）。

    为什么需要：全景图是 2:1 的"展开图"，直接当缩略图看是一团弯的；
    要让人一眼看出"那张画面里是什么样"，必须按某个方向投影成正常透视。

    相机系约定（与 pano360.stitch 一致）：
      · 图上的经度 lon=0 -> 相机系 +Y（"前方"），+90° -> +X（右）
      · yaw 是想看的**相机系经度**，pitch 是仰角（正=向上）
    """
    if out_h is None:
        out_h = max(1, int(out_w * 9 / 16))
    eh, ew = equi.shape[:2]
    f = 0.5 * out_w / math.tan(math.radians(fov_deg) / 2.0)
    py = math.radians(pitch_deg)
    yy = math.radians(yaw_deg)
    cy, sy = math.cos(yy), math.sin(yy)
    cp, sp = math.cos(py), math.sin(py)

    xs = np.arange(out_w) - out_w / 2.0
    ys = np.arange(out_h) - out_h / 2.0
    XS, YS = np.meshgrid(xs, ys)
    # 相机系方向（x 右、y 上、z 前）
    dx, dy, dz = XS, -YS, np.full_like(XS, f)
    # 先俯仰（绕 x），再偏航（绕 y）。
    # **旋转符号必须与 `stitch()` 的逆式一致** —— 否则 pitch 会反
    # （踩过：pitch=-45° 看到的是天空而不是地面）。
    # 与 stitch 里的 `phi = atan2(dx, dy)` 对齐的推导给出下面这一式。
    dy2 = dy * cp + dz * sp
    dz2 = -dy * sp + dz * cp
    dx3 = dx * cy + dz2 * sy
    dz3 = -dx * sy + dz2 * cy
    n = np.sqrt(dx3 * dx3 + dy2 * dy2 + dz3 * dz3)
    ex, ey, ez = dx3 / n, dy2 / n, dz3 / n
    lat = np.arcsin(np.clip(ey, -1.0, 1.0))
    lon = np.arctan2(ex, ez)
    u = (lon / (2 * np.pi) + 0.5) * ew
    v = (0.5 - lat / np.pi) * eh
    # 经度方向是环形的，列要绕回；纬度不绕
    u = np.mod(u, ew)
    v = np.clip(v, 0, eh - 1)
    x0 = np.floor(u).astype(np.int32) % ew
    x1 = (x0 + 1) % ew
    y0 = np.clip(np.floor(v).astype(np.int32), 0, eh - 2)
    y1 = np.clip(y0 + 1, 0, eh - 1)
    fu = (u - np.floor(u))[..., None]
    fv = (v - np.floor(v))[..., None]
    a = equi[y0, x0] * (1 - fu) + equi[y0, x1] * fu
    b = equi[y1, x0] * (1 - fu) + equi[y1, x1] * fu
    return (a * (1 - fv) + b * fv).astype(equi.dtype)


def equirect_direction(ew: int, eh: int):
    """返回等距柱状每个像素的方向（单位向量，右手系：x=东/右, y=北/上, z=天）。

    注意这里的 (x,y,z) 是**相机系**，不是地理系 —— 与"北"的对应关系
    要靠定北向那一步解出来（`docs/360_定北向.md`）。
    """
    lon = (np.arange(ew) + 0.5) / ew * 2 * np.pi - np.pi
    lat = np.pi / 2 - (np.arange(eh) + 0.5) / eh * np.pi
    LON, LAT = np.meshgrid(lon, lat)
    return np.stack([np.cos(LAT) * np.sin(LON),
                     np.cos(LAT) * np.cos(LON),
                     np.sin(LAT)], axis=-1)


# ---------------------------------------------------------------- 正向模型
# 为什么需要"世界方向 -> 像素"这个正向模型：
#   ① 拼接/标定的**验证**：可以造一张"已知标定"的合成鱼眼图，
#      再看重投影/接缝比对能不能把它还原出来。
#      （只写逆向（等距柱状 -> 像素）时没法自检 —— 我在这上面卡了很久：
#       试过"同一张图当两路比对，失配应当为 0"，但那个 sanity 本身是错的，
#       因为 t 与 π−t 的方位角关系不是恒等，同一张图的两路采样点本来就不重合。）
#   ② 覆盖几何要算"某个地面点在画面的哪个像素"。
#
# 两镜头的像面基（关键，别搞错）：
#   上镜头: 光轴 Z=+Z(天顶)，像面 X=东、Y=北  -> 世界 = (dx, dy, cz)
#   下镜头: 光轴 Z=−Z(天底)，像面 X=东、Y=南  -> 世界 = (dx, −dy, −cz)
# 两路用的是**同一个** phi = atan2(dx, dy) 式子。

def world_to_lens(dx_w, dy_w, dz_w, lens: str = "up",
                  fov_deg: float = DEFAULT_FOV,
                  cx: float = 0.0, cy: float = 0.0, radius: float = 1.0):
    """世界方向（相机系单位向量）-> (x, y, inside)。

    参数 cx/cy/radius 用像素单位（radius 是鱼眼圆半径）。
    返回的 inside 表示该方向是否落在这一路的视场内。
    """
    import numpy as _np
    dx_w = _np.asarray(dx_w, dtype=_np.float64)
    dy_w = _np.asarray(dy_w, dtype=_np.float64)
    dz_w = _np.asarray(dz_w, dtype=_np.float64)
    sign = 1.0 if lens == "up" else -1.0
    # 与光轴的夹角
    cos_t = _np.clip(sign * dz_w, -1.0, 1.0)
    theta = _np.arccos(cos_t)
    r = radius * (theta / _np.deg2rad(fov_deg / 2.0))
    # 像面方位：两路同式
    phi = _np.arctan2(dx_w, dy_w)          # 注意：上镜头 dy=世界 y, dz=世界 z
    x = cx + r * _np.cos(phi)
    y = cy + r * _np.sin(phi)
    return x, y, (theta <= _np.deg2rad(fov_deg / 2.0))


def equirect_to_lens(lon_deg, lat_deg, lens: str = "up",
                     fov_deg: float = DEFAULT_FOV, size: int = 3840):
    """等距柱状的 (经度, 纬度) -> 该路的像素坐标。覆盖几何/检索要用。"""
    import numpy as _np
    lon = _np.deg2rad(_np.asarray(lon_deg, dtype=_np.float64))
    lat = _np.deg2rad(_np.asarray(lat_deg, dtype=_np.float64))
    dx = _np.cos(lat) * _np.sin(lon)
    dy = _np.cos(lat) * _np.cos(lon)
    dz = _np.sin(lat)
    c = (size - 1) / 2.0
    return world_to_lens(dx, dy, dz, lens=lens, fov_deg=fov_deg,
                         cx=c, cy=c, radius=c)


def synth_lens_image(lon_deg, lat_deg, lens: str, fov_deg: float = DEFAULT_FOV,
                     size: int = 480, mark_radius: float = 6.0):
    """按**已知标定**造一张合成鱼眼图：给定若干方向，在这些位置画亮点。

    用途：验证重投影与接缝比对。它同时是"正向模型正确"的自检 ——
    造出来的图如果重投影回等距柱状能落在原方向，说明正向/逆向一致。
    """
    import numpy as _np
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(im)
    x, y, inside = equirect_to_lens(lon_deg, lat_deg, lens=lens,
                                    fov_deg=fov_deg, size=size)
    xs = _np.atleast_1d(x)
    ys = _np.atleast_1d(y)
    ins = _np.atleast_1d(inside)
    for xi, yi, ok in zip(xs, ys, ins):
        if not ok:
            continue
        d.ellipse([float(xi) - mark_radius, float(yi) - mark_radius,
                   float(xi) + mark_radius, float(yi) + mark_radius],
                  fill=(255, 255, 255))
    return _np.asarray(im)



def ground_distance(alt_m: float, lat_rad: np.ndarray) -> np.ndarray:
    """等距柱状某一行对应的**地面距离**（米）。

    这是 360 覆盖几何的核心，也是它比针孔简单的原因：
    仰角只由**行**决定、与方位无关，所以

        d = h / tan(仰角)

    -> 一帧 360 覆盖的地面是**一个圆环**，不是梯形。
    """
    lat = np.asarray(lat_rad, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        d = alt_m / np.tan(lat)
    d = np.where(lat <= 0, np.nan, d)      # 地平线以上不落地
    return d
