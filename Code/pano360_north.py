# -*- coding: utf-8 -*-
"""用太阳位置独立标定 360 全景的北向。

原理：
  · 时间（SRT 时间戳）与位置（SRT 经纬度）已知
    -> 可**独立算出**太阳的理论方位角 az 与高度角 el（不用任何图像信息）
  · 同一时刻，全景图里太阳的位置可量出来：
        列 -> 相机系经度 lon_cam      行 -> 高度角 lat_cam
  · north_yaw = az - lon_cam

**自检**：量到的太阳高度角必须与理论值吻合。吻合说明投影与 FOV 都对；
不吻合说明标定有问题 —— 这是很强的交叉校验，不靠"看着像"。
"""
from __future__ import annotations

import argparse
import io
import math
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pano360
import pano360_export
import project_manager as pm

# 用于"预测太阳半径"的视场。它只需要**大致**对：
#   r_expect = (90-el)/(FOV/2)
# FOV 差 10% 时 r_expect 也只差 10%，而搜索环带有 0.18 的宽容度，足够容下。
# **北向本身不依赖这个值**（只用到方位角 phi）。
FOV_FOR_NORTH = pano360.DEFAULT_FOV

# 定北向要求太阳至少升到这个高度（度）。
#
# 实测依据：10-14 与 10-15 下午那几趟（高度角 +41~+47°）日面干净利落，
# 两次独立测量一致到 0.02%；而贡嘎那批清晨素材（+0.07° / +2.45°）
# 太阳贴着地平线，"找最亮区"抓到的全是晨昏光带，算出的方向完全错。
#
# 12° 是个有余量的选择：低于它，日面与地平线光带的距离已经进入
# 容易混淆的区间；高于它，日面稳稳落在天空里。
MIN_SUN_ELEVATION_DEG = 12.0


def solar_position(lat_deg: float, lon_deg: float, when_utc: datetime):
    """太阳方位角/高度角（度）。az: 0=北、顺时针。NOAA 简化算法，精度约 0.02°。"""
    jd = ((when_utc - datetime(2000, 1, 1, 12, tzinfo=timezone.utc)).total_seconds()
          / 86400.0 + 2451545.0)
    n = jd - 2451545.0
    L = (280.460 + 0.9856474 * n) % 360.0
    g = math.radians((357.528 + 0.9856003 * n) % 360.0)
    lam = math.radians(L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    eps = math.radians(23.439 - 0.0000004 * n)
    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))
    dec = math.asin(math.sin(eps) * math.sin(lam))
    gmst = (18.697374558 + 24.06570982441908 * n) % 24.0
    lst = math.radians((gmst * 15.0 + lon_deg) % 360.0)
    ha = lst - ra
    lat = math.radians(lat_deg)
    el = math.asin(max(-1.0, min(1.0, math.sin(lat) * math.sin(dec)
                                 + math.cos(lat) * math.cos(dec) * math.cos(ha))))
    cos_az = (math.sin(dec) - math.sin(el) * math.sin(lat)) / (math.cos(el) * math.cos(lat) + 1e-12)
    az = math.degrees(math.acos(max(-1.0, min(1.0, cos_az))))
    if math.sin(ha) > 0:
        az = 360.0 - az
    return az, math.degrees(el)


def place_at(srt: Path, t_sec: float):
    """取某时刻的经纬度、高度、SRT 本地时间戳。

    复用项目已有的 `parse_dji_srt`（它已经处理好了 SRT 的分块格式），
    不再自己写正则 —— 自己写的那版就因为"时间戳在上一行"而解析失败。
    """
    recs = pm.parse_dji_srt(srt)
    tele = pm.load_srt_telemetry(srt)
    times = tele.get("times") or []
    if not recs:
        raise RuntimeError("SRT 为空")
    # 找离 t_sec 最近的一条**有定位**的采样
    nz = [(i, r) for i, r in enumerate(recs) if r.get("latitude") and r.get("longitude")]
    if not nz:
        raise RuntimeError("SRT 里没有有效定位")
    def key(item):
        i = item[0]
        t = times[i // pm.TELEMETRY_STEP] if i // pm.TELEMETRY_STEP < len(times) else 0.0
        return abs(t - t_sec)
    i, r = min(nz, key=key)
    j = i // pm.TELEMETRY_STEP
    t = times[j] if j < len(times) else 0.0
    return r, t


def find_sun(equi: np.ndarray):
    """在等距柱状图上找太阳的中心。返回 (lon, lat, x, y, 亮点数)。

    两个**必须做对**的地方（都踩过）：
      ① 取 `g[ys, xs]` 里的最亮点后，`ys`/`xs` 是**筛选后**的数组，
         用它们的**下标**去索引是对的；但绝不能拿原图的 `np.argmax` 下标
         去当 (x, y) —— 那在 2:1 的图上会把坐标算错。
      ② 只取最亮的 **1%** 做质心。取太宽会把"接缝处那圈白色羽化带"
         （它其实比太阳还亮、面积还大）当成太阳 —— 实测第一次就抓错了它，
         算出高度角 +10.7°（真值 +42.8°）。
    """
    g = equi.astype(np.float32).mean(axis=2)
    eh, ew = g.shape
    thr = float(np.percentile(g, 99.9))
    ys, xs = np.nonzero(g >= thr)
    if len(xs) < 4:
        return None
    vals = g[ys, xs]
    # 最亮的一小撮：按亮度降序取前 min(1%, 200) 个
    k = max(4, min(200, len(vals) // 100 or 4))
    order = np.argsort(-vals)[:k]
    cx, cy = float(xs[order].mean()), float(ys[order].mean())
    lon = (cx + 0.5) / ew * 360.0 - 180.0
    lat = 90.0 - (cy + 0.5) / eh * 180.0
    return lon, lat, cx, cy, int(len(xs))


def measure_sun(g, cx, cy, R, ring_inner: float = 0.93,
                r_expect: float | None = None, r_tol: float = 0.08):
    """遮外圈白环 -> （可选）只在预测半径附近找日面 -> 找**最大连通亮斑** -> 质心。

    返回 (x, y, r_R, phi_px, blob_px)。

    三个**必须做对**的地方（前两个都踩过，且都会给出"看起来合理"的错值）：

    ① **先遮外圈**。鱼眼外圈有一道白色圆环（镜头/软件加边），比日面更亮更大 ——
       实测抓出过 r/R=0.971 的假太阳（真值 0.557）。

    ② **只在预测半径附近找**。无特征场景里最亮的可能是**水面反光** ——
       实测把 r/R=0.850 的河面反光当成太阳，算出的 north 差了 170°。
       太阳高度角 el 是独立算出的，所以 r/R = (90−el)/(FOV/2) 可预测；
       只在 `r_expect ± r_tol` 环带里找。
       （用的是"高度角"，与待求的 yaw 无关 —— 不循环依赖。）
       **容差不能放太宽**：实测 r_tol=0.18 时，一个半径 60px 的反光斑
       其**边缘**会落进环带，于是反光和日面被连通成一块，质心漂到 0.62。
       默认 0.08（服务里用 0.06）够用 —— 因为 r_expect 本身相当准。

    ③ **取最大连通亮斑，而不是"最亮单点"**。单点最亮可能是一两个噪点或镜面反光，
       取它的邻域质心会把中心拉偏。日面是一个**有面积的盘**，所以
       "过曝区域的连通块"才是对的特征。
    """
    yy, xx = np.mgrid[0:g.shape[0], 0:g.shape[1]]
    rr = np.hypot(xx - cx, yy - cy) / R
    masked = g.copy()
    masked[rr > ring_inner] = 0.0
    if r_expect is not None:
        band = np.abs(rr - r_expect) <= max(0.05, r_tol)
        masked[~band] = 0.0
    if not masked.any():
        masked = g.copy()
        masked[rr > ring_inner] = 0.0

    # 过曝阈值：日面是那块接近饱和的区域。用相对峰值取，适配不同曝光。
    peak = float(masked.max())
    thr = peak - 18.0
    m = masked >= thr
    if m.sum() < 4:
        iy, ix = np.unravel_index(int(np.argmax(masked)), masked.shape)
        return (float(ix), float(iy), math.hypot(ix - cx, iy - cy) / R,
                math.atan2(iy - cy, ix - cx), int(m.sum()))

    # 连通块标记（只关心"最大的那一块"）。用简单的两遍扫描太慢，
    # 这里用迭代膨胀更快也更短：从种子开始反复把相邻亮点并进来。
    iy, ix = np.unravel_index(int(np.argmax(masked)), masked.shape)
    blob = np.zeros_like(m, dtype=bool)
    blob[iy, ix] = True
    for _ in range(400):                      # 日面在这个尺度下几百像素，够了
        grown = blob.copy()
        grown[1:, :] |= blob[:-1, :]
        grown[:-1, :] |= blob[1:, :]
        grown[:, 1:] |= blob[:, :-1]
        grown[:, :-1] |= blob[:, 1:]
        grown &= m
        if grown.sum() == blob.sum():
            break
        blob = grown
    ys, xs = np.nonzero(blob)
    w = (masked[ys, xs] - (peak - 40.0)).clip(0, None)
    if w.sum() <= 0:
        sx, sy = float(xs.mean()), float(ys.mean())
    else:
        sx = float((w * xs).sum() / w.sum())
        sy = float((w * ys).sum() / w.sum())
    return sx, sy, math.hypot(sx - cx, sy - cy) / R, math.atan2(sy - cy, sx - cx), int(blob.sum())


def _lens_frame(video: Path, idx: int, t: float, n: int = 1440) -> np.ndarray:
    """抽某时刻某一路鱼眼帧（供 pano360_service 复用）。"""
    import project_manager as pm
    ff = pm.find_ffmpeg()
    p = subprocess.run(
        [ff, "-y", "-loglevel", "error", "-ss", "%.3f" % t, "-i", str(video),
         "-map", "0:v:%d" % idx, "-frames:v", "1",
         "-vf", "scale=%d:%d" % (n, n), "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True, timeout=1800)
    if p.returncode != 0 or not p.stdout:
        raise RuntimeError("抽帧失败（流 %d）: %s" % (idx, (p.stderr or b"")[:200]))
    import io
    from PIL import Image as _I
    return np.asarray(_I.open(io.BytesIO(p.stdout)).convert("RGB"))


def timestamp_at(srt: Path, t_sec: float):
    """取 SRT 里离 t_sec 最近那条记录的时间戳（本地时间，UTC+8）。"""
    raw = srt.read_text(encoding="utf-8", errors="replace")
    dts = re.findall(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+)", raw)
    cues = re.findall(r"(\d\d):(\d\d):(\d\d),(\d\d\d) --> ", raw)
    if not dts or not cues:
        raise RuntimeError("SRT 里没有时间戳")
    bi, bd = 0, 1e18
    for i, (hh, mm, ss, ms) in enumerate(cues):
        tt = int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0
        if abs(tt - t_sec) < bd:
            bi, bd = i, abs(tt - t_sec)
    return datetime.strptime(dts[min(bi, len(dts) - 1)], "%Y-%m-%d %H:%M:%S.%f")


def north_yaw_for(video: Path, srt: Path, t_sec: float, tz_hours: float = 8.0,
                  size: int = 1440):
    """算这段素材的 north_yaw（度）。返回 (north_yaw, 诊断 dict)。

    北向只用太阳的**方位角**：
        north_yaw = az_theory - phi_measured
    其中 phi 是太阳在鱼眼图上的像面方位角 —— **与极角标定/FOV 无关**，
    所以即使 FOV 还没定准，这个结果也是可信的（这一点很重要）。
    """
    r, _ = place_at(srt, t_sec)
    dt_local = timestamp_at(srt, t_sec)
    dt_utc = dt_local.replace(tzinfo=timezone(timedelta(hours=tz_hours))).astimezone(timezone.utc)
    az_t, el_t = solar_position(r["latitude"], r["longitude"], dt_utc)

    # **太阳太低就不要量。**
    #
    # 踩过（2026-10-15 贡嘎那批素材）：那几趟是**刚刚日出**拍的，
    # 太阳高度角只有 +0.07° / +2.45° —— 太阳贴着地平线，整个天空是一大片
    # 渐变的晨昏光带。这时候"找最亮区当太阳"**必然**抓到那条光带，
    # 于是算出完全错误的 north（实测 r/R 0.88~0.91、blob 高达 17509 px，
    # 而正常日面是 2000~3600 px）。看标注图一眼就能看出红圈套在橙色的
    # 地平线亮带上，日面根本不在画面里。
    #
    # 两道原有的可信检查（预测半径、日面面积）都拦不住它：
    # 它们只防"太小的碎片"，而光环带又大又亮。
    #
    # 所以底部加一道**物理前提**检查：太阳得升到足够高，
    # 才能和地平线光带分开。宁可返回"不可用"，也不给一个错的方向 ——
    # **错的方向比没有方向更危险**。
    if el_t < MIN_SUN_ELEVATION_DEG:
        raise ValueError(
            "太阳高度角只有 %+.2f°（低于 %.0f°），太阳贴着地平线，"
            "无法可靠地把日面和地平线光带分开 —— 北向留空，不猜。"
            % (el_t, MIN_SUN_ELEVATION_DEG))

    up = _lens_frame(video, 0, t_sec, n=size)
    g = up.astype(np.float32).mean(axis=2)
    c = (size - 1) / 2.0
    # 太阳的**预期半径**：由独立算出的高度角得到（与待求的 yaw 无关，不循环依赖）
    fov = FOV_FOR_NORTH
    r_expect = (90.0 - el_t) / (fov / 2.0)
    sx, sy, r_R, phi, blob_px = measure_sun(g, c, c, c, r_expect=r_expect)

    north = (az_t - math.degrees(phi) + 180.0) % 360.0 - 180.0
    diag = {
        "t": t_sec, "utc": dt_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "lat": r["latitude"], "lng": r["longitude"],
        "sun_az_theory": round(az_t, 2), "sun_el_theory": round(el_t, 2),
        "sun_px": [round(sx, 1), round(sy, 1)],
        "sun_blob_px": blob_px,
        "sun_r_over_R": round(r_R, 4), "sun_phi": round(math.degrees(phi), 2),
        # 预期半径与实测半径之差：这个差大就说明"找到的不是日面"（比如水面反光）
        "r_expect": round(r_expect, 4),
        "r_delta": round(r_R - r_expect, 4),
        # 用太阳高度角反推的 FOV（**只是参考**：它假设等距投影、且相机水平）
        "fov_implied": round(2 * (90.0 - el_t) / r_R, 1) if r_R > 1e-6 else None,
    }
    return north, diag


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--srt", required=True)
    ap.add_argument("--t", type=float, default=20.0)
    ap.add_argument("--size", type=int, default=1440)
    ap.add_argument("--ew", type=int, default=2048)
    ap.add_argument("--fov", type=float, default=pano360.DEFAULT_FOV)
    ap.add_argument("--tz", type=float, default=8.0, help="SRT 时间戳相对 UTC 的偏移（小时）")
    ap.add_argument("--save", default=None)
    a = ap.parse_args()

    srt = Path(a.srt)
    r, t_srt = place_at(srt, a.t)
    # SRT 的时间戳里带日期时间，用它比用 cue 时间更直接
    dt_txt = None
    recs = pm.parse_dji_srt(srt)
    m = None
    import re
    raw = srt.read_text(encoding="utf-8", errors="replace")
    dts = re.findall(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+)", raw)
    # 用采样序号按比例取一个（采样与 SRT 行是 1:3 的关系）
    idx = min(len(dts) - 1, max(0, int(round(a.t / max(t_srt, 1e-9)
                                             * min(len(dts) - 1, 10 ** 9))))) if dts else 0
    # 更稳的做法：按 cue 时间找
    if dts:
        # cue 时间与 dts 一一对应（都在同一批行里按顺序出现）
        cues = re.findall(r"(\d\d):(\d\d):(\d\d),(\d\d\d) --> ", raw)
        if cues:
            best_i, best_d = 0, 1e18
            for i, (hh, mm, ss, ms) in enumerate(cues):
                tt = int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0
                if abs(tt - a.t) < best_d:
                    best_i, best_d = i, abs(tt - a.t)
            if best_i < len(dts):
                dt_txt = dts[best_i]
    if dt_txt is None:
        raise RuntimeError("找不到时间戳")
    dt_local = datetime.strptime(dt_txt, "%Y-%m-%d %H:%M:%S.%f")
    dt_utc = dt_local.replace(tzinfo=timezone(timedelta(hours=a.tz))).astimezone(timezone.utc)

    print("=== 输入 ===")
    print("  SRT 本地时间戳 : %s   （按 UTC%+g 解释）" % (dt_local, a.tz))
    print("  换算 UTC       : %s" % dt_utc.strftime("%Y-%m-%d %H:%M:%S"))
    print("  位置           : %.6f, %.6f   rel_alt %.1f m" % (r["latitude"], r["longitude"],
                                                              r.get("rel_alt") or 0))
    print("  取帧时刻       : t=%.1f s（SRT 内最近采样 %.2f s）" % (a.t, t_srt))

    az, el = solar_position(r["latitude"], r["longitude"], dt_utc)
    print()
    print("=== 理论太阳位置（只由时间 + 位置算出，完全不用图像）===")
    print("  方位角 az = %6.2f°   （0=北，顺时针）" % az)
    print("  高度角 el = %6.2f°" % el)

    equi = pano360_export.equirect_at(srt, a.t, size=a.size, ew=a.ew, fov_deg=a.fov)
    if a.save:
        Image.fromarray(equi).save(a.save)

    sun = find_sun(equi)
    print()
    print("=== 图像里量到的太阳 ===")
    if not sun:
        print("  ✗ 没找到亮斑")
        return 1
    lon_c, lat_c, cx, cy, npix = sun
    print("  像素 (%.1f, %.1f)   亮斑 %d px" % (cx, cy, npix))
    print("  相机系经度 lon_cam = %+7.2f°" % lon_c)
    print("  量到高度角         = %+7.2f°" % lat_c)
    if a.save:
        print("  （图已存 %s，可肉眼核对太阳位置）" % a.save)

    print()
    print("=== 交叉校验（这条最重要）===")
    d_el = lat_c - el
    print("  高度角: 量到 %.2f°  理论 %.2f°   差 %+.2f°" % (lat_c, el, d_el))
    ok = abs(d_el) < 1.5
    print("  %s" % ("✓ 吻合 —— 投影标定与时间解释都成立" if ok else
                    "✗ 不吻合 —— 投影/FOV 标定 或 时区 有问题，北向不可信"))
    if not ok:
        print("    排查方向：① --tz 对不对 ② --fov 对不对 ③ 两路是否装反")

    north_yaw = (az - lon_c + 180.0) % 360.0 - 180.0
    print()
    print("=== 北向 ===")
    print("  north_yaw = az - lon_cam = %.2f - (%.2f) = %+.2f°" % (az, lon_c, north_yaw))
    print("  用法：地理方位角 = north_yaw + 等距柱状图的列经度")
    print("        等价地：图上经度 %+.2f° 那一列朝正北" % (-north_yaw))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
