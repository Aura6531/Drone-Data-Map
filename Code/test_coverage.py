# -*- coding: utf-8 -*-
"""覆盖栅格的回归测试（合成数据，不依赖真实素材、不依赖 numpy 之外的库）

锁住三个曾经踩过的坑：
  ① 斜距必须相对【无人机】算，不能把网格原点当成无人机
     —— 曾把 130 m 的斜距算成 938 m，GSD 差 7 倍
  ② 存的是最小 **GSD**，不是最小斜距（焦距不同档时两者不等价）
  ③ 收口只作用于远边，近边不能被截
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import numpy as _np  # noqa: F401
except ImportError:
    # 覆盖栅格依赖 numpy。没装时**明确跳过**而不是报失败 ——
    # 这样系统 Python（可能没有 numpy）跑 run_tests.js 也不会误判。
    print("=== 视场覆盖栅格回归测试 ===")
    print("  [SKIP] 这个解释器没有 numpy，跳过")
    print("         （coverage.py 需要 numpy；可用 PYTHON=<带 numpy 的解释器> 指定）")
    print("\n结果: 全部通过（已跳过）")
    raise SystemExit(0)

import coverage as cov  # noqa: E402

ok = True


def _pixel_to_ground(drone, height, yaw, pitch, focal, xi, yi):
    """归一化图像坐标 (xi,yi) -> 地面经纬度（针孔模型正投影）。

    只用于测试：给 ground_point_in_frame 造输入，好做互逆核对。
    这里**独立实现**，不复用被测函数 —— 复用就失去互逆验证的意义了。
    """
    lat0, lng0 = drone
    hfov, vfov = cov.fov_of(focal)
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
    d = (r[0] * xi * th + u[0] * yi * tv + f[0],
         r[1] * xi * th + u[1] * yi * tv + f[1],
         r[2] * xi * th + u[2] * yi * tv + f[2])
    if d[2] >= -1e-9:
        return None                       # 打到水平线以上
    t = -height / d[2]
    e, n = t * d[0], t * d[1]
    mx = cov.M_PER_DEG_LNG * math.cos(math.radians(lat0))
    return (lat0 + n / cov.M_PER_DEG_LAT, lng0 + e / mx)


def chk(cond, label, extra=""):
    global ok
    ok = ok and bool(cond)
    print(f"  {'[OK]' if cond else '[FAIL]'} {label}" + (f" -> {extra}" if extra else ""))


print("=== 1) 几何：正下视 100 m、24mm 的地面覆盖应等于视场角算出的宽高 ===")
h, f = 100.0, 24.0
pts, clipped = cov.frame_footprint(h, 0.0, -90.0, f, 1e6)
hf, vf = cov.fov_of(f)
w_exp = 2 * h * math.tan(math.radians(hf / 2))
h_exp = 2 * h * math.tan(math.radians(vf / 2))
w = max(p[0] for p in pts) - min(p[0] for p in pts)
hh = max(p[1] for p in pts) - min(p[1] for p in pts)
chk(abs(w - w_exp) < 0.05, "宽度与视场角一致", f"{w:.2f} vs {w_exp:.2f}")
chk(abs(hh - h_exp) < 0.05, "高度与视场角一致", f"{hh:.2f} vs {h_exp:.2f}")
chk(clipped is False, "正下视不该触发收口")

print("\n=== 2) 收口只作用于远边（近边永不被截） ===")
# 浅俯角：上边缘会打到水平线以上，必须收口
pts2, cl2 = cov.frame_footprint(100.0, 0.0, -10.0, 24.0, 600.0)
ds = [math.hypot(p[0], p[1]) for p in pts2]
chk(cl2 is True, "浅俯角触发了收口")
chk(max(ds) <= 600.0 + 1e-6, "远边被收到上限之内", f"max {max(ds):.1f}")
chk(min(ds) < 600.0, "近边没有被一起截到上限", f"min {min(ds):.1f}")

print("\n=== 3) 斜距必须相对无人机（回归：曾把原点当无人机） ===")
# 造一段"无人机停在离网格原点很远的地方、正下视"的合成遥测
LAT0, LNG0 = 22.96, 113.77
ALT = 100.0
# 无人机位置：向东 800 m（约 0.0078 度经度）
off_lng = 800.0 / (cov.M_PER_DEG_LNG * math.cos(math.radians(LAT0)))
drone_lat, drone_lng = LAT0, LNG0 + off_lng
tele = {
    "count": 3,
    "times": [0.0, 0.1, 0.2],
    "yaw": [0.0, 0.0, 0.0],
    "pitch": [-90.0, -90.0, -90.0],
    "focal": [24.0, 24.0, 24.0],
    "dzoom": [1.0, 1.0, 1.0],
    "alt": [ALT, ALT, ALT],
}
lats = [drone_lat] * 3
lngs = [drone_lng] * 3
g = cov.build_from_telemetry(tele, lats, lngs, srt_name="TEST_V.SRT", cell=1.0)

# 正下视时，无人机正下方那一格的 GSD 应 ≈ 高度 × 单像素角
app = cov.rad_per_px(24.0, g.long_px)
gsd_expect = ALT * app
ix, iy = g.cell_of(drone_lat, drone_lng)
got = float(g.gsd_best_map[iy, ix])
chk(abs(got - gsd_expect) / gsd_expect < 0.02,
    "无人机正下方的 GSD ≈ 高度×单像素角", f"{got:.5f} vs {gsd_expect:.5f}")

# 同一行里偏出中心 40 m 的格子：仍在足迹内（正下视 100 m 宽 157 m），
# 但斜距 = hypot(40, 100)。用来验证"斜距真的随位置变化"，
# 而不是被错误地按原点算成同一个值。
off_lng2 = 40.0 / (cov.M_PER_DEG_LNG * math.cos(math.radians(LAT0)))
ix2, iy2 = g.cell_of(drone_lat, drone_lng + off_lng2)
got2 = float(g.gsd_best_map[iy2, ix2])
slant2 = math.hypot(40.0, ALT) * app
chk(got2 > 0, "偏出 40 m 的格子有覆盖")
chk(abs(got2 - slant2) / slant2 < 0.03,
    "偏出 40 m 的 GSD ≈ 斜距×单像素角", f"{got2:.5f} vs {slant2:.5f}")
chk(got2 > got * 1.03, "偏出中心的 GSD 比正下方差（斜距确实随位置变化）",
    f"{got2:.5f} vs {got:.5f}")

def _test_projection_roundtrip():
    """ground_point_in_frame 与正投影必须互逆。"""
    # 为什么单测这个：检索「这个位置被哪些画面拍到过」要靠它判断
    # "目标是否真的在画面里"。四角多边形在**收口帧**上会给出错的答案
    # （实测 26% 的命中目标其实在画面外），所以必须用精确射影。
    #
    # 验法：对同一个相机姿态，把归一化像素 (xi,yi) 正投影成地面点，
    # 再用 ground_point_in_frame 投回图像 —— 应当回到同一个 (xi,yi)。
    h, foc = 97.0, 24.0
    drone = (23.05, 114.10)

    for pitch in (-90.0, -60.0, -30.0):
        for yaw in (0.0, 137.0):
            worst = 0.0
            for xi in (-0.9, -0.5, 0.0, 0.5, 0.9):
                for yi in (-0.9, -0.5, 0.0, 0.5, 0.9):
                    # ① 归一化像素 -> 地面点（同一个针孔模型的正投影）
                    pt = _pixel_to_ground(drone, h, yaw, pitch, foc, xi, yi)
                    if pt is None:
                        continue
                    # ② 地面点 -> 归一化像素
                    bx, by, _inside = cov.ground_point_in_frame(
                        drone, h, yaw, pitch, foc, pt)
                    if bx is None:
                        worst = 99.0
                        continue
                    worst = max(worst, abs(bx - xi), abs(by - yi))
            chk(worst < 1e-6,
                f"俯角 {pitch}° 偏航 {yaw}° 往返一致",
                f"最大误差 {worst:.2e}")

    # 画面外的点必须判为不在画面里（这是修复 A 的核心）
    outside = _pixel_to_ground(drone, h, 0.0, -40.0, foc, 1.8, 0.0)
    if outside is not None:
        bx, _by, inside = cov.ground_point_in_frame(drone, h, 0.0, -40.0, foc, outside)
        chk(inside is False, "归一化坐标 1.8 的点判为「不在画面内」",
            f"xi={bx:.2f} inside={inside}")

    # 相机背后的点：取一个**与无人机等高**的目标（height=0 -> d[2]=0）。
    #
    # 注意两个容易搞错的构造：
    #   ① "无人机正上方"不行 —— 那正好落在视轴上，不是背后
    #   ② "远处的地面点"也不行 —— 相机俯视 40°、视场半高 24°，
    #      地面点只要在画面俯仰范围内 z 就是正的
    #      （我第一版就错在这儿，以为远处地面点在地平线以上）
    # 同高度的点，视线与相机前向的点积 = −sin(俯角) < 0，才是真的"背后"。
    # 与无人机等高的点 z=0 -> 视作"看不到"（inside=False）。
    # 归一化坐标本身是 (0, 0) —— 因为方向就是相机前向在水平面的投影，
    # 落在画面正中心，但那个位置上是天空，不是地面点。
    bx, by, inside = cov.ground_point_in_frame(
        drone, 0.0, 0.0, -40.0, foc,
        (drone[0] + 100.0 / cov.M_PER_DEG_LAT, drone[1]))
    chk((bx is None or abs(bx) < 1e-9) and inside is False,
        "与无人机等高的点（相机背后）判为看不到",
        f"xi={bx} yi={by} inside={inside}")


print("\n=== 4) ground_point_in_frame 与正投影必须互逆 ===")
_test_projection_roundtrip()

print("\n=== 5) 置信度函数：分项与总分的单调性 ===")
s30 = cov.sigma_footprint(97.0, -30.0)
c_hi, _ = cov.confidence(300, 3, 0.08, 0.0, s30)
c_lo, _ = cov.confidence(10, 1, 0.10, 0.0, s30)
chk(c_hi > c_lo, "观测充分 > 只扫一眼", f"{c_hi:.3f} vs {c_lo:.3f}")
c_clip, parts = cov.confidence(300, 3, 0.08, 0.9, s30)
chk(c_clip < c_hi, "收口比例高会降级", f"{c_clip:.3f} vs {c_hi:.3f}")
chk(0.0 < c_hi <= 1.0, "取值在 0~1", f"{c_hi:.3f}")
chk(cov.grade(c_hi) in ("high", "medium", "low", "very_low"), "分级有效", cov.grade(c_hi))
s_shallow = cov.sigma_footprint(97.0, -10.0)
chk(s_shallow > s30, "浅俯角不确定度更大（远处怕姿态）", f"{s_shallow:.2f} vs {s30:.2f}")

print("\n=== 6) 存取往返一致 ===")
tmp = Path(__file__).resolve().parent.parent / "_coverage_roundtrip.npz"
try:
    g.save(tmp)
    g2 = cov.CoverageGrid.load(tmp)
    chk(int(g2.count.sum()) == int(g.count.sum()), "count 一致",
        f"{int(g2.count.sum())} vs {int(g.count.sum())}")
    chk(abs(float(g2.gsd_best_map.max()) - float(g.gsd_best_map.max())) < 1e-6,
        "gsd_best_map 一致")
    chk(g2.lat0 == g.lat0 and g2.cell == g.cell, "范围/格宽一致")
    # 逐采样点的时刻必须一起存下来 —— 它是"采样下标 -> 视频秒"的唯一权威来源
    chk(len(g2.frame_times) == len(g.frame_times),
        "frame_times 一起存下来了", f"{len(g2.frame_times)} vs {len(g.frame_times)}")
finally:
    if tmp.exists():
        tmp.unlink()

def _test_frame_time():
    """「采样下标 -> 视频秒」必须走 frame_times，不能按帧率折算。"""
    # 这是 2026-10-13 那个"地图位置差 228 m"的根因：
    # find_frames 把**遥测采样下标**当成了**视频帧号**，用 fi*step/fps 算秒数。
    # 实测偏 17.7 s。这里钉住"必须走 frame_times"。
    #
    # 造一个"采样间隔不均匀"的网格：这就是真实 SRT 的样子
    # （37358 行跨 1263.3 s，平均 0.0338 s/行，不是正好 0.0333）。
    tele2 = {
        "step": cov.TELEMETRY_STEP, "count": 5,
        "times": [0.0, 0.05, 0.20, 0.60, 1.40],
        "yaw": [-90.0] * 5, "pitch": [-90.0] * 5,
        "focal": [24.0] * 5, "dzoom": [1.0] * 5,
        "alt": [100.0] * 5,
    }
    lats2 = [LAT0 + i * 1e-5 for i in range(5)]
    lngs2 = [LNG0 + i * 1e-5 for i in range(5)]
    g3 = cov.build_from_telemetry(tele2, lats2, lngs2, srt_name="T.SRT", cell=1.0)

    chk(len(g3.frame_times) == 5, "建网格时把 times 抄进了 frame_times",
        str(g3.frame_times))
    chk(g3.frame_time(4) == 1.40,
        "frame_time 用 frame_times 的值（第 5 个采样点 = 1.40 s）",
        str(g3.frame_time(4)))
    naive = cov.video_seconds_of_frame(4)
    chk(abs(naive - 1.40) > 0.5,
        "按帧率折算会算成另一回事（正是那个 bug）",
        f"折算 {naive:.3f} s vs 实际 1.40 s，差 {abs(naive - 1.40):.2f} s")

    # 换算入口本身也要对：视频帧号 -> 采样下标
    chk(cov.telemetry_sample_of_frame(300) == 30,
        "视频帧号 300（10 s）-> 采样下标 30（10Hz）",
        str(cov.telemetry_sample_of_frame(300)))
    chk(cov.telemetry_sample_of_frame(11793) == 1179,
        "视频帧号 11793（19:39.3）-> 采样下标 1179，不是 11793",
        str(cov.telemetry_sample_of_frame(11793)))


print("\n=== 7) 「采样下标 -> 视频秒」必须用 frame_times，不能按帧率折算 ===")
_test_frame_time()


def _test_sphere_path():
    """360 / 全景：没有 yaw/pitch 时也要能建网格（圆环 footprint）。

    用户 2026-10-14 要求把 360 接进覆盖链路。360 的 SRT 里**没有**
    `gb_yaw`/`gb_pitch`，所以原来 `pit is None or yaw is None` 会把每一帧都跳过
    （frames_used=0）。全景的覆盖是**圆环**、只需要高度与位置，所以另起一条路径。
    """
    tele2 = {
        "count": 6, "times": [i * 0.1 for i in range(6)],
        # 360：这两个字段全是 None（SRT 里根本没有）
        "yaw": [None] * 6, "pitch": [None] * 6,
        "focal": [None] * 6, "dzoom": [None] * 6,
        "alt": [25.5] * 6,
    }
    la = [LAT0 + i * 1e-5 for i in range(6)]
    ln = [LNG0 + i * 1e-5 for i in range(6)]
    g4 = cov.build_from_telemetry(tele2, la, ln, srt_name="T360_V.SRT", cell=1.0)

    chk(g4.frames_used == 6, "360 的帧不再被跳过", f"used={g4.frames_used} skipped={g4.frames_skipped}")
    chk(g4.frames_skipped == 0, "一帧都没被跳过", str(g4.frames_skipped))
    covered = int((g4.count > 0).sum())
    chk(covered > 0, "确实盖出了覆盖", f"{covered} 格")

    # 圆环的外半径 = max(CLIP_MIN, CLIP_PER_ALT × h)；25.5 m -> 600 m（下限）
    ri, ro = cov.sphere_ring(25.5)
    chk(ri == 0.0, "没给俯角时内半径取 0（假设整球覆盖，保守）", str(ri))
    chk(abs(ro - max(cov.CLIP_MIN, cov.CLIP_PER_ALT * 25.5)) < 1e-9,
        "外半径复用针孔那套收口参数（可比、不用新旋钮）", f"{ro:.0f} m")

    # 覆盖应当是**圆盘**（半径 ro），面积 ~ pi*ro^2
    area = covered * g4.cell * g4.cell
    expect = math.pi * ro * ro
    chk(abs(area - expect) / expect < 0.05,
        "覆盖面积接近圆盘 pi·r²（圆环几何对了）",
        f"{area/10000:.1f} vs {expect/10000:.1f} 公顷")

    # 逐帧单像素角必须存下来 —— 360 没有焦距，查询时靠它反推斜距，否则除零
    chk(len(g4.frame_ang_per_px) == 6 and g4.frame_ang_per_px[0] > 0,
        "存了逐帧单像素角（360 没有焦距，靠它算斜距）",
        f"{g4.frame_ang_per_px[0]:.6f} rad" if g4.frame_ang_per_px else "空")
    chk(all(v == 0.0 for v in g4.frame_focal),
        "360 的 frame_focal 保持 0（不编一个假焦距出来）")

    # 点查询不能崩（原来这里 ZeroDivisionError）
    q = g4.query(la[2], ln[2])
    chk(q.get("covered") is True, "点查询可用（360 网格不再除零）",
        str(q.get("reason") or q.get("confidence")))
    if q.get("covered"):
        b = q["basis"]
        chk(b.get("slant_m") and b["slant_m"] > 0, "斜距为正", str(b.get("slant_m")))
        chk(abs(b["slant_m"] * g4.frame_ang_per_px[0] * 100 - b["can_resolve_cm"]) < 0.2,
            "斜距 × 单像素角 = GSD（自洽）",
            f"{b['slant_m']:.1f} m × {g4.frame_ang_per_px[0]:.6f} = "
            f"{b['slant_m']*g4.frame_ang_per_px[0]*100:.1f} cm/px vs {b['can_resolve_cm']}")
        # 360 没有云台俯角 -> sigma 不能用"俯角项"（那会给 inf 把置信度压成 0）
        chk(math.isfinite(q["sigma_m"]) and q["sigma_m"] > 0,
            "边界不确定度是有限值（俯角缺失时不能变成 inf）", str(q["sigma_m"]))
        chk(q["confidence"] > 0, "置信度 > 0", str(q["confidence"]))

    # 针孔那条不能被带坏。判据用**纯几何**而不是栅格统计 ——
    # 栅格的边缘效应（外接框角格的中心可能恰好落在多边形外一点点）会让
    # "四角是否被覆盖"不稳定（实测 2/4），那是采样问题、不是几何问题。
    #
    # 几何上的本质区别：
    #   针孔正下视：足迹四角**距离相同**（正方形，边长 = 2h·tan(fov/2)）
    #   360 圆环  ：足迹是**圆**，内外半径差一个量级（0.45 m vs 291 m）
    ipx, _cl = cov.frame_footprint(25.5, 0.0, -90.0, 24.0, 600.0)
    ds = [math.hypot(p[0], p[1]) for p in ipx]
    chk(max(ds) - min(ds) < 0.5,
        "针孔正下视的足迹四角**等距**（正方形）",
        f"距离 {min(ds):.2f}~{max(ds):.2f} m")
    half_span = max(p[0] for p in ipx) - min(p[0] for p in ipx)
    h = 25.5
    hf = cov.fov_of(24.0)[0]
    chk(abs(half_span - 2 * h * math.tan(math.radians(hf / 2))) < 0.5,
        "针孔边长 = 2·h·tan(fov/2)（矩形那套没被动过）",
        f"{half_span:.1f} vs {2*h*math.tan(math.radians(hf/2)):.1f} m")

    ri6, ro6 = cov.sphere_ring(h)
    chk(ro6 / max(ri6, 1e-9) > 10,
        "360 的覆盖是**圆环/圆盘**而不是方形（内外半径差一个量级）",
        f"内 {ri6:.2f} m vs 外 {ro6:.0f} m")


print("\n=== 8) 360 / 全景：没有 yaw/pitch 也要能建网格（圆环） ===")
_test_sphere_path()

print("\n结果:", "全部通过" if ok else "有失败项")
raise SystemExit(0 if ok else 1)
