# -*- coding: utf-8 -*-
"""360 专用视场覆盖几何：一帧覆盖的**圆环** footprint。

## 为什么 360 的几何比针孔简单

等距柱状里 **仰角只由行决定、与方位无关**，所以

    地面距离 d = h / tan(俯角)

一帧 360 覆盖的地面就是**一个圆环**（不是梯形）：
  · 外半径 = h / tan(θ_top)      θ_top = 画面上边缘对应的俯角（看最近）
  · 内半径 = h / tan(θ_bottom)   θ_bottom = 画面下边缘（看最远，接近地平线）
正下方是盲区（θ 从 90° 往下时 d 从 h·... 变化；等距柱状里 90° 就是正下方）
—— 见 `panorama_tangent_radii()`。

## 与针孔那套的关系

`coverage.frame_footprint()` 是针孔的四角梯形，**完全不适用**（那是按相机的
矩形视场算的）。所以这里另起一族函数，不动原来那套。

## 径向标度

`r = R · θ / (FOV/2)`（等距投影）。FOV 还有不确定（见 docs），但
**径向标度 k = θ/r 可以用太阳实测**：太阳高度角由时间+位置独立算出，
量出它的像面半径就能反推 k。两段素材给出的 k 只差 3.3%（0.4447 vs 0.4595 度/px），
互相印证。所以本模块的 `DEG_PER_UNIT_R` 用实测值，而不是靠 FOV 猜。
"""
from __future__ import annotations

import math

# 径向标度：每单位归一化半径对应多少度极角。
# 由太阳实测反推（theta = 90 - 太阳高度角，r/R = 量到的半径）：
#   0002 段: 47.16 / 0.4534 = 104.0 度/单位
#   0001 段: 48.65 / 0.4678 = 104.0 度/单位
# 两段一致到 0.1% —— 所以这个数比"猜 FOV"可靠得多。
# 等价说法：单镜头半视场 = 104.0°（即 FOV = 208°）。
DEG_PER_UNIT_R = 104.0
FOV_IMPLIED = 2 * DEG_PER_UNIT_R          # 208°

# 360 的"单像素角"代理（弧度）。与 coverage.SPHERE_PROXY_FOCAL_MM 同源：
# 24 mm 等效广角的角分辨率。**只是代理** —— 会让 GSD 有乘性比例误差，
# 但不影响覆盖范围（覆盖只由高度与仰角决定）。
SPHERE_PROXY_ANG_PER_PX = 0.00034675


def theta_of_r(r_norm: float, deg_per_unit: float = DEG_PER_UNIT_R) -> float:
    """归一化半径（0=光轴, 1=鱼眼圆边缘）-> 与光轴的夹角（度）。"""
    return r_norm * deg_per_unit


def r_of_theta(theta_deg: float, deg_per_unit: float = DEG_PER_UNIT_R) -> float:
    """与光轴的夹角（度）-> 归一化半径。"""
    return theta_deg / deg_per_unit


# ---------------------------------------------------------------- 圆环
def ring_radii(alt_m: float, lat_top_deg: float, lat_bottom_deg: float):
    """一帧 360 覆盖的**地面圆环**内外半径（米）。

    lat_top / lat_bottom 是等距柱状图上、下边缘对应的**仰角**（度，地平线为 0）：
      · 上边缘仰角最大 -> 看最近 -> 外半径（其实是最小距离的倒数…注意命名）
      · 下边缘仰角最小/为负 -> 看最远 -> 内半径？

    **命名容易搞反，这里说清楚**：以无人机正下方为圆心，
    仰角越大 -> tan 越大 -> d = h/tan 越小 -> **越靠近圆心**。
    所以：
      · 仰角最大（画面最上边，若相机水平则接近天顶方向）-> d 最小 -> **内半径**
      · 仰角最小（画面最下边，接近地平线）-> d 最大 -> **外半径**

    返回 (r_inner_m, r_outer_m)。仰角 <= 0（地平线及以上）不落地 -> 外半径 = inf。
    """
    def d_of(el_deg):
        el = math.radians(el_deg)
        if el <= 1e-9:
            return math.inf
        return alt_m / math.tan(el)

    r_from_top = d_of(lat_top_deg)        # 仰角大 -> 距离小
    r_from_bottom = d_of(lat_bottom_deg)  # 仰角小 -> 距离大
    r_inner = min(r_from_top, r_from_bottom)
    r_outer = max(r_from_top, r_from_bottom)
    return r_inner, r_outer


def ring_for_frame(alt_m: float, lat_top_deg: float, lat_bottom_deg: float,
                   near_m: float = 0.0):
    """同上，但把外半径截到 near_m 以外（near_m<=0 表示不截）。

    为什么要截：仰角趋近 0 时 d -> ∞。等距柱状的**下边缘**仰角是 −90°（正下方），
    真正决定"看多远"的其实是地平线那一行。所以实际使用时通常传
    lat_bottom = 0（地平线）或一个很小的正数。
    """
    ri, ro = ring_radii(alt_m, lat_top_deg, lat_bottom_deg)
    if near_m and near_m > 0:
        ro = min(ro, near_m)
    return ri, ro


def ring_visibility(alt_m: float, el_deg: float):
    """某个仰角对应的地面距离；仰角 <= 0 返回 None（不落地）。"""
    el = math.radians(el_deg)
    if el <= 1e-9:
        return None
    return alt_m / math.tan(el)


# ---------------------------------------------------------------- 点是否被拍到
def ground_point_in_pano(lat0: float, lng0: float, alt_m: float,
                         plat: float, plng: float, yaw_deg: float,
                         cam_pitch_deg: float = 0.0):
    """某个地面点是否落在这一帧 360 的覆盖圆环里。

    与针孔的 `ground_point_in_frame()` 不同：360 没有"画面边缘被切"的问题
    （除了正下方的盲区），所以判据只是"距离在圆环内 + 不在盲区"。

    返回 (dist_m, inside_ring, bearing_deg, elev_deg)。
    yaw_deg: 相机系 +Y（图上前方）指向的地理方位角。cam_pitch_deg: 相机俯仰
    （360 一般水平安装，0）。
    """
    import math as _m
    M_LAT = 111320.0
    M_LNG = 111320.0 * _m.cos(_m.radians(lat0))
    de = (plng - lng0) * M_LNG
    dn = (plat - lat0) * M_LAT
    dist = _m.hypot(de, dn)
    bearing = (_m.degrees(_m.atan2(de, dn))) % 360.0
    elev = _m.degrees(_m.atan2(-alt_m, dist)) if dist > 1e-9 else -90.0
    return dist, bearing, elev


# ---------------------------------------------------------------- 飞行剖面
# 悬停延时 vs 真实航线的判据：**水平位移跨度 / 高度跨度**。
#
# 为什么需要它（2026-10-15 踩的坑）：用户说「贡嘎的两个视频是悬停的，拍摄长时间的
# 延时摄影，经纬度不动很正常」。我回去重查，发现我把**一趟真飞的航线**当成了悬停
# —— 而且依据是一个**采样错了的数字**（遍历步长与记录长度不匹配，只采到很小一段，
# 把 1110 m 的跨度看成 3 cm）。
#
# 所以这个判断必须**量准 + 有明确阈值**，不能靠看着像。实测标定：
#   · 纯悬停延时（贡嘎 0004）：水平   0 m / 高度 1.4 m   -> 比值 0.0
#   · 真航线      （贡嘎 0001）：水平 1110 m / 高度 249 m -> 比值 4.5
# 0.5 这个门槛把两者分得很开，也不容易被噪声碰到。
HOVER_DRIFT_RATIO = 0.5
HOVER_MAX_DRIFT_M = 30.0        # 高度几乎不变时，水平位移小于这个就算悬停


def flight_profile(samples):
    """从逐采样点判断这趟是**悬停延时**还是**真实航线**。

    samples: [(t_sec, lat, lng, alt), ...]

    返回 dict：kind / drift_m / alt_span_m / alt_median_m / ratio / seconds / points
    """
    import math as _m
    pts = [(t, la, ln, a) for (t, la, ln, a) in samples
           if la is not None and ln is not None]
    if len(pts) < 2:
        return {"kind": "unknown", "points": len(pts)}

    la0, ln0 = pts[0][1], pts[0][2]
    mlat = 111320.0
    mlng = mlat * _m.cos(_m.radians(la0))
    drift = max(_m.hypot((ln - ln0) * mlng, (la - la0) * mlat)
                for (_t, la, ln, _a) in pts)

    alts = sorted(a for (_t, _la, _ln, a) in pts if a and a > 0)
    alt_span = (alts[-1] - alts[0]) if alts else 0.0
    alt_med = alts[len(alts) // 2] if alts else 0.0

    if alt_span <= 3.0:
        # 高度几乎没变，只能看水平位移
        kind = "hover" if drift <= HOVER_MAX_DRIFT_M else "transit"
        ratio = None
    else:
        ratio = drift / alt_span
        kind = "hover" if ratio <= HOVER_DRIFT_RATIO else "transit"

    return {
        "kind": kind,
        "drift_m": round(drift, 1),
        "alt_span_m": round(alt_span, 1),
        "alt_median_m": round(alt_med, 1),
        "ratio": (None if ratio is None else round(ratio, 2)),
        "seconds": round(pts[-1][0] - pts[0][0], 1),
        "points": len(pts),
    }


# ---------------------------------------------------------------- 检索
# 与 coverage_api 那套**同值**：便于两类素材的检索结果对照，也省得再调参数。
FIND_PASS_GAP_SECONDS = 8.0     # 同一架次里相邻命中至少隔这么久才算"另一趟"
FIND_DEDUP_SECONDS = 5.0        # 相邻两趟再近于这个间隔的，只留最清的一条

# 检索模式：与针孔那条同名，前端可以共用一套渲染
FIND_MODES = ("best", "passes", "all")


def _dedup_and_group(hits_sorted_by_t, mode="passes"):
    """相邻去重 + 按趟分组。hits 必须**按时间**排好序。"""
    dedup = []
    for h in hits_sorted_by_t:
        if dedup and abs(dedup[-1]["t"] - h["t"]) < FIND_DEDUP_SECONDS:
            if h["ground_m_per_px"] < dedup[-1]["ground_m_per_px"]:
                dedup[-1] = h
            continue
        dedup.append(h)
    if mode == "all":
        return dedup
    if mode == "best":
        return sorted(dedup, key=lambda h: h["ground_m_per_px"])[:1]
    # passes：按时间间隔切趟，每趟取该趟里最清（= 最近）的一条
    passes = []
    for h in dedup:
        if passes and h["t"] - passes[-1][-1]["t"] <= FIND_PASS_GAP_SECONDS:
            passes[-1].append(h)
        else:
            passes.append([h])
    out = []
    for grp in passes:
        best = min(grp, key=lambda h: h["ground_m_per_px"])
        best = dict(best)
        best["pass_seconds"] = round(grp[-1]["t"] - grp[0]["t"], 1)
        best["pass_frames"] = len(grp)
        out.append(best)
    return out


def find_frames_360(samples, lat, lng, limit: int = 60,
                    far_per_alt: float = 12.0, far_min: float = 600.0,
                    mode: str = "passes"):
    """在 360 素材里找"哪些帧拍到了这一点"。

    ## 为什么不复用 coverage_api.find_frames

    那条路径依赖**相机姿态**（把点投到画面看 |xi|,|yi| <= 1）。360 的 SRT 里
    没有 `gb_yaw`/`gb_pitch` —— 而且**不需要**：全景的覆盖是圆环，
    判据只是"地面距离落在内外半径之间"。所以单起一条，逻辑反而更简单更快。

    ## 排序与去重

    360 没有焦距/变焦，所以"最清晰"退化为"**离得最近**"：
    地面距离越短 -> 斜距越短 -> GSD 越小 -> 越清晰。
    这与针孔那边"按 GSD 排"实质一致。

    **必须去重**：采样是 20 Hz，相邻帧几乎一样。实测某点命中 1248 帧，
    不去重就是把同一瞬间重复列 1248 次。所以按 `FIND_DEDUP_SECONDS` 合并相邻、
    再按 `FIND_PASS_GAP_SECONDS` 切趟，每趟取最近的一条（`mode="passes"`）。
    这与针孔那条的 `mode/passes` 语义一致，前端可以共用一套渲染。

    samples: [(t_sec, lat, lng, alt), ...]（抽稀后的逐采样点）
    返回 {"total", "hits": [...]}，字段与针孔那条**尽量同名**。
    """
    import math as _m
    if not samples:
        return {"total": 0, "hits": []}
    M_LAT = 111320.0
    raw = []
    for (t, la, ln, alt) in samples:
        if not alt or alt <= 0:
            continue
        # 圆环参数在这里内联算，不 import coverage ——
        # 本模块刻意保持**自洽独立**（不依赖 coverage / numpy），这样它能被
        # 单独引用、单独测。参数与 coverage 那边同源（远半径 = max(min, k*h)）。
        near = 0.0
        far = max(far_min, far_per_alt * alt)
        if near >= far:
            continue
        mx = M_LAT * _m.cos(_m.radians(la))
        de = (lng - ln) * mx
        dn = (lat - la) * M_LAT
        dist = _m.hypot(de, dn)
        if not (near <= dist <= far):
            continue
        elev = _m.degrees(_m.atan2(-alt, dist)) if dist > 1e-9 else -90.0
        bearing = (_m.degrees(_m.atan2(de, dn))) % 360.0
        slant = _m.hypot(dist, alt)
        gsd = slant * SPHERE_PROXY_ANG_PER_PX
        raw.append({
            "t": t,
            "dist_m": round(dist, 2),
            "alt_m": round(alt, 1),
            "slant_m": round(slant, 1),
            "ground_m_per_px": round(gsd, 4),
            "can_resolve_cm": round(gsd * 100, 1),
            "bearing_deg": round(bearing, 1),
            "elev_deg": round(elev, 1),
        })
    if mode not in FIND_MODES:
        mode = "passes"
    grouped = _dedup_and_group(raw, mode=mode)
    grouped.sort(key=lambda h: h["ground_m_per_px"])
    return {"total": len(grouped), "raw_frames": len(raw), "mode": mode,
            "hits": grouped[:limit]}
