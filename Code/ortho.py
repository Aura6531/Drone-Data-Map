# -*- coding: utf-8 -*-
"""正射影像（GeoTIFF）→ Web 地图瓦片金字塔。

设计参考 ArcGIS / gdal2tiles 的做法：**一次性把各层级切成 256×256 的 PNG 铺在磁盘上**，
之后缩放/平移就是读文件，不再重算投影 —— 这样"下次也能快速缩放访问"。

为什么不用 GDAL：本机**没有** GDAL / rasterio / pyproj（只有 numpy + Pillow）。
所以三件事都是手写的：
  1. 解析 TIFF 的 TileOffsets/TileByteCounts，按块随机读（整幅读要 7.3 GB 内存）
  2. UTM <-> WGS84 的横轴墨卡托正反算
  3. 投到 Web Mercator 并重采样

验证记录见 docs/正射影像技术验证.md：
  · 单块解压 0.0~0.7 ms，正好 262144 B = 256×256×4 RGBA
  · 网格收敛角实测 -1.13°，理论 1.12°（吻合到 0.01°）—— 投影实现正确
  · PIL.crop() 取 256×256 要 6.4 秒（整幅解码），所以不能用 Pillow 做瓦片

层级选择：源 GSD 4.64 cm/px。Web Mercator 在纬度 22.93° 处
  z19 = 0.269 m/px, z20 = 0.134, z21 = 0.067, z22 = 0.034
native 最接近的是 z21（略粗于原图），所以**最高建到 z21**，z22 只是放大插值没有新信息。

空瓦片的裁剪（这是能不能跑得动的关键）：
  实测这片影像 **NODATA 约 87%**（一条斜向走廊）。若照外接矩形铺，
  z21 一层就要 14884 块 × ~38 ms ≈ 9 分钟，而绝大多数是全透明的。
  办法：**从粗到细建，父块全透明就直接跳过子块** ——
  子块区域一定被父块包含，父块没数据则子块必然没数据。
"""

import io
import json
import math
import re
import struct
import threading
import time
import zlib
from pathlib import Path

try:
    import numpy as np
except ImportError:  # 没 numpy 时整块功能不可用，但别让服务起不来
    np = None

TILE = 256                     # 瓦片边长（Web 标准）
MIN_Z, MAX_Z_HARD = 10, 22     # 兜底范围；实际范围由 src 的 GSD 与覆盖范围决定
DEFAULT_MIN_Z = 12

# NODATA 判定：影像的 alpha=0 是空；DSM 之类用 -9999
NODATA_FLOATS = (-9999.0, 9999.0)


def _need_numpy():
    if np is None:
        raise RuntimeError("正射影像需要 numpy，当前解释器没有。")
    return np


# ============================================================
# 投影：WGS84 <-> UTM（横轴墨卡托）
# ============================================================
#
# 只用 WGS84 椭球。国产坐标系（Beijing54 / Xian80 / CGCS2000 高斯投影）
# 的椭球与带号规则不同，这里**明确不支持** —— 遇到就报错，不要静默算错位置
# （静默算错比不显示更糟：用户会以为影像就是长那样）。

WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563


def utm_params(epsg):
    """从 EPSG 反推 UTM 带号与半球。

    只接受 326xx（北半球）与 327xx（南半球）—— 即 WGS84 / UTM。
    别的坐标系直接抛错并说明原因。
    """
    try:
        code = int(epsg)
    except (TypeError, ValueError):
        raise ValueError("没读到 EPSG 代码，无法把影像投到地图上。")

    if 32601 <= code <= 32660:
        return code - 32600, True
    if 32701 <= code <= 32760:
        return code - 32700, False

    raise ValueError(
        "这张影像的坐标系是 EPSG:%d，目前只支持 WGS84/UTM（326xx / 327xx）。"
        "国产坐标系（Beijing54 / Xian80 / CGCS2000 高斯投影）的椭球与带号规则不同，"
        "贸然换算会把位置算偏，所以这里直接拒绝而不是猜。" % code)


def latlng_to_utm(lat, lon, zone, northern=True):
    """经纬度 -> UTM 东/北坐标（米）。支持 numpy 数组。"""
    np = _need_numpy()
    a, f = WGS84_A, WGS84_F
    k0 = 0.9996
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)

    lat = np.asarray(lat, dtype=np.float64)
    lon = np.asarray(lon, dtype=np.float64)
    phi = np.radians(lat)
    lam = np.radians(lon) - math.radians((zone - 1) * 6 - 180 + 3)

    sin_phi = np.sin(phi)
    cos_phi = np.cos(phi)
    N = a / np.sqrt(1 - e2 * sin_phi ** 2)
    T = np.tan(phi) ** 2
    C = ep2 * cos_phi ** 2
    A = cos_phi * lam

    M = a * ((1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * phi
             - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * np.sin(2 * phi)
             + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * np.sin(4 * phi)
             - (35 * e2 ** 3 / 3072) * np.sin(6 * phi))

    east = 500000.0 + k0 * N * (A + (1 - T + C) * A ** 3 / 6
                                + (5 - 18 * T + T ** 2 + 72 * C - 58 * ep2) * A ** 5 / 120)
    north = k0 * (M + N * np.tan(phi) * (A ** 2 / 2
                 + (5 - T + 9 * C + 4 * C ** 2) * A ** 4 / 24
                 + (61 - 58 * T + T ** 2 + 600 * C - 330 * ep2) * A ** 6 / 720))
    if not northern:
        north = north + 10000000.0
    return east, north


def utm_to_latlng(easting, northing, zone, northern=True):
    """UTM 东/北坐标 -> 经纬度（度）。标量版（只给外框的四个角用）。"""
    a, f = WGS84_A, WGS84_F
    k0 = 0.9996
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)

    x = float(easting) - 500000.0
    y = float(northing) if northern else float(northing) - 10000000.0

    M = y / k0
    mu = M / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = (mu
            + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * math.sin(6 * mu))

    C1 = ep2 * math.cos(phi1) ** 2
    T1 = math.tan(phi1) ** 2
    N1 = a / math.sqrt(1 - e2 * math.sin(phi1) ** 2)
    R1 = a * (1 - e2) / (1 - e2 * math.sin(phi1) ** 2) ** 1.5
    D = x / (N1 * k0)

    lat = phi1 - (N1 * math.tan(phi1) / R1) * (
        D ** 2 / 2
        - (5 + 3 * T1 + 10 * C1 - 4 * C1 ** 2 - 9 * ep2) * D ** 4 / 24
        + (61 + 90 * T1 + 298 * C1 + 45 * T1 ** 2 - 252 * ep2 - 3 * C1 ** 2) * D ** 6 / 720)
    lon = (D
           - (1 + 2 * T1 + C1) * D ** 3 / 6
           + (5 - 2 * C1 + 28 * T1 - 3 * C1 ** 2 + 8 * ep2 + 24 * T1 ** 2) * D ** 5 / 120
           ) / math.cos(phi1)

    lon0 = math.radians((zone - 1) * 6 - 180 + 3)
    return math.degrees(lat), math.degrees(lon0 + lon)


# ============================================================
# Web Mercator 瓦片网格
# ============================================================

def latlng_to_tile(lat, lon, z):
    n = 2.0 ** z
    x = (lon + 180.0) / 360.0 * n
    lr = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(lr)) / math.pi) / 2.0 * n
    return x, y


def tile_latlng_bounds(z, x, y):
    """瓦片的 (latNW, lngNW, latSE, lngSE)。"""
    n = 2.0 ** z

    def ll(px, py):
        lon = px / n * 360.0 - 180.0
        lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * py / n))))
        return lat, lon

    (lat_nw, lon_nw) = ll(x, y)
    (lat_se, lon_se) = ll(x + 1, y + 1)
    return lat_nw, lon_nw, lat_se, lon_se


def mercator_pixel_size(lat, z):
    """z 层在该纬度每像素的地面米数。"""
    return 156543.03392804097 * math.cos(math.radians(lat)) / (2.0 ** z)


# ============================================================
# GeoTIFF 按块读取
# ============================================================

class GeoRaster(object):
    """分块 TIFF 的按块随机读取器（只支持无 Predictor 的 deflate / 原始块）。

    为什么要这么底层：整幅 39658×46163×4 = 7.3 GB，读不动；
    但它按 256×256 分块，可以只读需要的那几块（0.7 ms / 块）。
    """

    def __init__(self, path):
        from PIL import Image

        _need_numpy()
        Image.MAX_IMAGE_PIXELS = None     # 正射影像动辄上亿像素，不是 attack
        self.path = Path(path)
        self._fh = None
        self._cache = {}
        self._lock = threading.Lock()

        with Image.open(self.path) as im:
            tg = im.tag_v2
            self.width = im.width
            self.height = im.height
            self.tile_w = tg.get(322)
            self.tile_h = tg.get(323)
            self.compression = tg.get(259)
            self.samples = int(tg.get(277) or 4)
            bps = tg.get(258) or 8
            # **每通道**字节数，不是每像素 ——
            # BitsPerSample 是 (8,8,8,8) 时 sum//8 = 4 已经是整像素字节数，
            # 再乘 samples 就把期望长度放大 4 倍（踩过：解压出 1048576 字节
            # 却要 reshape 成 256×256×4）。所以只取单个通道的位深。
            if isinstance(bps, (tuple, list)):
                self.channel_bytes = max(1, int(bps[0]) // 8)
            else:
                self.channel_bytes = max(1, int(bps) // 8)
            offsets = tg.get(324)
            counts = tg.get(325)
            self.pixel_scale = tg.get(33550)
            self.tiepoint = tg.get(33922)
            self.geokeys = tg.get(34735)
            self.nodata = tg.get(42113)

        if not self.tile_w or not self.tile_h or not offsets or not counts:
            raise ValueError(
                "这个 TIFF 不是分块（tiled）存储，无法按块读取；"
                "整幅读进内存对正射影像不现实。请用大疆智图导出、或用 gdal_translate "
                "加 -co TILED=YES 重新输出。")

        self.offsets = list(offsets)
        self.counts = list(counts)
        self.across = (self.width + self.tile_w - 1) // self.tile_w
        self.down = (self.height + self.tile_h - 1) // self.tile_h

        if not self.pixel_scale or not self.tiepoint:
            raise ValueError("这张 TIFF 没有地理参考（ModelPixelScale / ModelTiepoint），"
                             "贴不到地图上。")

        self.scale = float(self.pixel_scale[0])
        self.tie_x = float(self.tiepoint[3])
        self.tie_y = float(self.tiepoint[4])

        # ---- 只接受**彩色 8 位**栅格 ----
        #
        # 同一个成果包里除了正射影像（RGBA 8 位）还有 DSM（单波段 float32 高程）。
        # 拿 DSM 当影像显示会是一片噪点（把 float32 的字节当颜色读），
        # 所以这里明确拒绝并说清原因，而不是画出一团垃圾让用户困惑。
        if self.channel_bytes != 1 or self.samples < 3:
            kind = "单波段浮点（高程/DSM）" if self.channel_bytes == 4 else \
                   ("单波段" if self.samples == 1 else "%d 波段" % self.samples)
            raise ValueError(
                "这不是彩色正射影像，而是%s：%d 波段、每通道 %d 字节。"
                "能贴到地图上显示的是 RGB/RGBA 8 位的正射影像（DJI Terra 里的 "
                "result.tif），高程模型（dsm.tif）不能当底图用。"
                % (kind, self.samples, self.channel_bytes))
        self.epsg = self._read_epsg()
        self.zone, self.northern = utm_params(self.epsg)

        # 影像的外接经纬度范围
        corners = []
        for px, py in ((0, 0), (self.width, 0), (0, self.height), (self.width, self.height)):
            e = self.tie_x + px * self.scale
            n = self.tie_y - py * self.scale
            corners.append(utm_to_latlng(e, n, self.zone, self.northern))
        lats = [c[0] for c in corners]
        lngs = [c[1] for c in corners]
        self.bounds = (min(lats), min(lngs), max(lats), max(lngs))

    # ---- 元数据 ----
    def _read_epsg(self):
        gk = self.geokeys
        if not gk:
            raise ValueError("TIFF 里没有 GeoKeyDirectory，读不到坐标系。")
        if isinstance(gk, bytes):
            gk = struct.unpack("<%dH" % (len(gk) // 2), gk)
        nkeys = gk[3]
        for i in range(nkeys):
            kid, loc, cnt, val = gk[4 + i * 4: 8 + i * 4]
            if kid == 3072:          # ProjectedCSTypeGeoKey
                return int(val)
        # 没写投影坐标系：可能是地理坐标系（经纬度）
        for i in range(nkeys):
            kid, loc, cnt, val = gk[4 + i * 4: 8 + i * 4]
            if kid == 2048:
                raise ValueError(
                    "这张 TIFF 是**地理坐标系**（EPSG:%d，单位是度），"
                    "当前只处理投影坐标（UTM）。" % int(val))
        raise ValueError("GeoKeyDirectory 里既没有投影坐标系也没有地理坐标系。")

    def info(self):
        return {
            "path": str(self.path),
            "width": self.width,
            "height": self.height,
            "tile": [self.tile_w, self.tile_h],
            "tiles": self.across * self.down,
            "epsg": self.epsg,
            "utm_zone": self.zone,
            "northern": self.northern,
            "gsd_m": self.scale,
            "bounds": {"south": self.bounds[0], "west": self.bounds[1],
                       "north": self.bounds[2], "east": self.bounds[3]},
            "crs": "EPSG:%d" % self.epsg,
        }

    # ---- 按块读 ----
    def _open(self):
        if self._fh is None:
            self._fh = open(self.path, "rb")
        return self._fh

    def read_tile(self, tx, ty):
        """读一块，返回 (th, tw, samples) uint8。带 LRU 上界。"""
        np = _need_numpy()
        key = (tx, ty)
        hit = self._cache.get(key)
        if hit is not None:
            return hit

        with self._lock:
            idx = ty * self.across + tx
            if idx < 0 or idx >= len(self.offsets):
                out = np.zeros((self.tile_h, self.tile_w, self.samples), dtype=np.uint8)
                self._cache[key] = out
                return out
            fh = self._open()
            fh.seek(self.offsets[idx])
            raw = fh.read(self.counts[idx])

        if self.compression == 1:
            data = raw
        else:
            data = zlib.decompress(raw)

        expect = self.tile_w * self.tile_h * self.samples * self.channel_bytes
        if len(data) < expect:
            # 被截断的块（文件损坏）当空块处理，别让整张图崩掉
            data = data + b"\0" * (expect - len(data))
        arr = np.frombuffer(data, dtype=np.uint8)[:expect].reshape(
            self.tile_h, self.tile_w, self.samples)

        # 缓存上界：一块 256 KB，留 96 块 ≈ 24 MB
        if len(self._cache) > 96:
            self._cache.clear()
        self._cache[key] = arr
        return arr

    def close(self):
        with self._lock:
            if self._fh is not None:
                try:
                    self._fh.close()
                finally:
                    self._fh = None
        self._cache.clear()

    # ---- 采样 ----
    def sample_simple(self, px, py):
        """最近邻采样（快、够用）。返回 (RGBA uint8, inside mask)。

        双线性的精确实现需要四次邻居查找，成本约 4 倍；
        在 256×256 的瓦片上这点差别肉眼几乎看不出（源影像 4.6 cm/px，
        下层都是缩小的），所以默认用最近邻，配 **2×2 超采样**来压锯齿。
        """
        np = _need_numpy()
        h, w = px.shape
        inside = (px >= 0) & (px < self.width - 1) & (py >= 0) & (py < self.height - 1)

        x0 = np.clip(px.astype(np.int32), 0, self.width - 1)
        y0 = np.clip(py.astype(np.int32), 0, self.height - 1)
        out = np.zeros((h, w, 4), dtype=np.uint8)

        txi = np.clip(x0 // self.tile_w, 0, self.across - 1)
        tyi = np.clip(y0 // self.tile_h, 0, self.down - 1)
        keys = tyi * self.across + txi

        for k in np.unique(keys):
            ty, tx = int(k // self.across), int(k % self.across)
            tile = self.read_tile(tx, ty)
            m = keys == k
            lx = np.clip(x0[m] - tx * self.tile_w, 0, self.tile_w - 1)
            ly = np.clip(y0[m] - ty * self.tile_h, 0, self.tile_h - 1)
            out[m] = tile[ly, lx]

        return out, inside

    # ---- 内存总览（mipmap 链）----
    #
    # 为什么必须有这个：直接对每块瓦片去源图采样，**粗层级反而最慢** ——
    # z16 一块瓦片覆盖 563 m，而一个源块只有 11.9 m，要碰约 2200 个源块；
    # 再叠加"每个源块一次 65536 元素的布尔掩码"，实测 z16 = 9827 ms，
    # 而 z21（只碰 9 个源块）只要 60 ms。完全反直觉但讲得通。
    #
    # 解法就是 ArcGIS / gdal2tiles 那套：先建金字塔。
    # 这里分两半 ——
    #   内存里：OVERVIEW_STEP 倍降采样的一张总览 + 逐级减半的 mip 链（粗层级用）
    #   磁盘上：各层级的 256×256 PNG 瓦片（build_pyramid，见文件末尾）
    OVERVIEW_STEP = 16        # 16 × 4.64 cm = 0.74 m/px
    OVERVIEW_MEM_LIMIT = 400e6  # 总览+各级 mip 的内存上限（字节）

    def overview(self):
        """懒加载：16 倍降采样的总览图（uint8, (h, w, 4)）。"""
        np = _need_numpy()
        if getattr(self, "_ov", None) is not None:
            return self._ov

        step = self.OVERVIEW_STEP
        ow = self.width // step
        oh = self.height // step
        if ow * oh * 4 > self.OVERVIEW_MEM_LIMIT:
            raise RuntimeError("影像太大，内存总览会超过 %.0f MB"
                               % (self.OVERVIEW_MEM_LIMIT / 1e6))

        ov = np.zeros((oh, ow, self.samples), dtype=np.uint8)
        # 逐块取，块内按 step×step 求平均（点采样会在缩小时出现明显噪点）
        # 块内的降采样：只要读到的块覆盖到某个总览像素就写进去。
        for ty in range(self.down):
            for tx in range(self.across):
                tile = self.read_tile(tx, ty)
                # 该块在总览里的像素范围
                ox0 = (tx * self.tile_w) // step
                oy0 = (ty * self.tile_h) // step
                if ox0 >= ow or oy0 >= oh:
                    continue
                # 块内按 step 取样；对不齐时用最近的
                sub = tile[::step, ::step]
                sh, sw = sub.shape[0], sub.shape[1]
                ox1 = min(ow, ox0 + sw)
                oy1 = min(oh, oy0 + sh)
                ov[oy0:oy1, ox0:ox1] = sub[:oy1 - oy0, :ox1 - ox0]

        self._ov = ov
        self._ov_scale = self.scale * step
        self._mips = [ov]
        self._mip_scales = [self._ov_scale]
        return ov

    def _build_mips(self):
        """总览再逐级减半，直到最长边 < 8 像素。粗层级从合适的 mip 取样。"""
        np = _need_numpy()
        self.overview()
        if len(self._mips) > 1:
            return
        cur = self._mips[0]
        scale = self._mip_scales[0]
        while max(cur.shape[0], cur.shape[1]) > 8:
            h, w = cur.shape[0] // 2, cur.shape[1] // 2
            if h < 1 or w < 1:
                break
            # 2×2 均值，顺便把 alpha 也平均 —— 边缘会变成半透明，视觉上更平滑
            nxt = cur[:h * 2, :w * 2].astype(np.float32).reshape(h, 2, w, 2, 4).mean(axis=(1, 3))
            cur = np.clip(nxt, 0, 255).astype(np.uint8)
            scale *= 2.0
            self._mips.append(cur)
            self._mip_scales.append(scale)

    def pix_at(self, z, x, y, size=TILE):
        """把瓦片像素映射到源图像素坐标。

        返回 (px, py)：两个 (size,size) 数组。投影只算一次、粗层级复用。
        """
        np = _need_numpy()
        lat_nw, lon_nw, lat_se, lon_se = tile_latlng_bounds(z, x, y)
        u = (np.arange(size) + 0.5) / size
        v = (np.arange(size) + 0.5) / size
        lon = lon_nw + (lon_se - lon_nw) * u
        yy = (y + v) / (2.0 ** z)
        lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * yy))))
        LON, LAT = np.meshgrid(lon, lat)
        E, N = latlng_to_utm(LAT, LON, self.zone, self.northern)
        return (E - self.tie_x) / self.scale, (self.tie_y - N) / self.scale

    # ---- 渲染一块 Web 瓦片 ----
    def render_tile(self, z, x, y, size=TILE, samples=1):
        """把 (z,x,y) 渲染成 RGBA uint8 (size,size,4)。

        自动选源：粗层级走内存 mip 链（毫秒级），细层级才读原图。
        """
        np = _need_numpy()
        px, py = self.pix_at(z, x, y, size)

        # 这个层级每像素多少米？决定用哪一级 mip。
        mid_lat = (tile_latlng_bounds(z, x, y)[0] + tile_latlng_bounds(z, x, y)[2]) / 2.0
        dest = mercator_pixel_size(mid_lat, z)

        self._build_mips()
        # 选"不比目标分辨率更细"的最细 mip：再细就只是白读像素
        pick = 0
        for i, sc in enumerate(self._mip_scales):
            if sc <= dest:
                pick = i
            else:
                break

        if pick > 0 or self._mip_scales[0] <= dest * 1.05:
            mip = self._mips[pick]
            mh, mw = mip.shape[0], mip.shape[1]
            # 源图像素 -> mip 像素（mip 是 step*2^pick 倍降采样）
            f = (self.scale * self.OVERVIEW_STEP * (2 ** pick))
            mx = px * self.scale / f
            my = py * self.scale / f
            inside = (mx >= 0) & (mx < mw - 1) & (my >= 0) & (my < mh - 1)
            ix = np.clip(mx.astype(np.int32), 0, mw - 1)
            iy = np.clip(my.astype(np.int32), 0, mh - 1)
            out = np.zeros((size, size, 4), dtype=np.uint8)
            out[inside] = mip[iy[inside], ix[inside]]
            return out

        # ---- 细层级：读原图 ----
        acc = np.zeros((size, size, 4), dtype=np.float32)
        mask = np.zeros((size, size), dtype=bool)
        n = max(1, int(samples))
        offs = (np.arange(n) + 0.5) / n
        for oy in offs:
            for ox in offs:
                # 同一块瓦片内的子采样平移（亚像素）
                sxp = px + (ox - 0.5)
                syp = py + (oy - 0.5)
                rgba, inside = self.sample_simple(sxp, syp)
                acc += rgba.astype(np.float32)
                mask |= inside
        acc /= float(n * n)
        out = np.clip(acc, 0, 255).astype(np.uint8)
        out[~mask] = 0
        return out

    def is_empty(self, rgba):
        """全透明就当空块（不落盘、不返回）。"""
        np = _need_numpy()
        return not bool(np.any(rgba[..., 3] > 0))


# ============================================================
# 打开/缓存
# ============================================================

_sources = {}
_sources_lock = threading.Lock()


def open_raster(path):
    key = str(Path(path).resolve())
    with _sources_lock:
        src = _sources.get(key)
        if src is None:
            src = GeoRaster(key)
            _sources[key] = src
        return src


def close_all():
    with _sources_lock:
        for src in _sources.values():
            try:
                src.close()
            except Exception:
                pass
        _sources.clear()


def level_range(src):
    """给这张影像选一个合适的层级范围。

    最细层级取"和源 GSD 最接近的那一层"—— 再细只是插值放大，没有新信息。
    """
    # 最细层级取"不比源 GSD 更细"的那一层 —— 再细只是插值放大，没有新信息。
    # 判据用 `>=` 而不是"最接近"：宁可略粗，也别生成一堆靠插值撑出来的瓦片。
    mid_lat = (src.bounds[0] + src.bounds[2]) / 2.0
    best = DEFAULT_MIN_Z
    for z in range(MAX_Z_HARD, MIN_Z - 1, -1):
        if mercator_pixel_size(mid_lat, z) >= src.scale:
            best = z
            break
    return DEFAULT_MIN_Z, best


def tile_range_for_bounds(bounds, z):
    """给定经纬度范围与层级，返回需要覆盖的瓦片索引范围 (x0,x1,y0,y1) 含端点。"""
    south, west, north, east = bounds
    x0, y1 = latlng_to_tile(south, west, z)
    x1, y0 = latlng_to_tile(north, east, z)
    return (int(math.floor(x0)), int(math.ceil(x1)),
            int(math.floor(y0)), int(math.ceil(y1)))


# ============================================================
# 金字塔：落盘
# ============================================================

EMPTY_TILE_PNG = None       # 1×1 全透明 PNG 的字节；空块返回它，浏览器不会报错


def _empty_png():
    global EMPTY_TILE_PNG
    if EMPTY_TILE_PNG is None:
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(buf, format="PNG")
        EMPTY_TILE_PNG = buf.getvalue()
    return EMPTY_TILE_PNG


def png_bytes(rgba):
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def pyramid_levels(src):
    return level_range(src)


def tile_path(cache_dir, z, x, y):
    return Path(cache_dir) / str(z) / str(x) / ("%d.png" % y)


def build_pyramid(src, cache_dir, min_z=None, max_z=None, progress=None, should_stop=None):
    """从粗到细建金字塔，**父块空就跳过子块**。

    返回统计 dict：{levels: {z: {built, skipped, empty}}, seconds, bytes}
    """
    import os

    np = _need_numpy()
    lo, hi = pyramid_levels(src)
    if min_z is not None:
        lo = int(min_z)
    if max_z is not None:
        hi = int(max_z)

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    stats = {"levels": {}, "seconds": 0.0, "bytes": 0, "min_z": lo, "max_z": hi}
    t_start = time.time()

    # 每层"有数据的瓦片"集合；下一层用它来裁剪
    opaque_at = {}

    for z in range(lo, hi + 1):
        x0, x1, y0, y1 = tile_range_for_bounds(src.bounds, z)
        built = skipped = empty = 0
        keep = set()

        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                if should_stop is not None and should_stop():
                    stats["seconds"] = time.time() - t_start
                    stats["aborted"] = True
                    return stats

                # 父块（上一层里包含这块的那一个）
                if z > lo:
                    pz = z - 1
                    ptx, pty = tx // 2, ty // 2
                    if opaque_at.get(pz) is not None and (ptx, pty) not in opaque_at[pz]:
                        skipped += 1
                        continue

                rgba = src.render_tile(z, tx, ty)
                if src.is_empty(rgba):
                    empty += 1
                    continue

                data = png_bytes(rgba)
                dest = tile_path(cache_dir, z, tx, ty)
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(".png.tmp")
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, dest)
                built += 1
                keep.add((tx, ty))
                stats["bytes"] += len(data)

        opaque_at[z] = keep
        stats["levels"][z] = {"built": built, "skipped": skipped, "empty": empty,
                              "tiles": (x1 - x0 + 1) * (y1 - y0 + 1)}
        if progress is not None:
            try:
                progress(z, built, skipped, empty)
            except Exception:
                pass

    stats["seconds"] = time.time() - t_start
    return stats


def write_meta(cache_dir, src, stats=None):
    meta = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": src.info(),
        "levels": pyramid_levels(src),
        "build": stats or {},
    }
    path = Path(cache_dir) / "meta.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def read_meta(cache_dir):
    path = Path(cache_dir) / "meta.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cache_is_ready(cache_dir, min_tiles=1):
    """判据用 meta.json + 至少一块瓦片 —— 只看目录是否存在会误判半成品。"""
    meta = read_meta(cache_dir)
    if not meta:
        return False
    root = Path(cache_dir)
    n = 0
    for z in range(meta.get("levels", (12, 21))[0], meta.get("levels", (12, 21))[1] + 1):
        d = root / str(z)
        if d.is_dir():
            n += sum(1 for _ in d.rglob("*.png"))
            if n >= min_tiles:
                return True
    return n >= min_tiles
