# -*- coding: utf-8 -*-
"""验证 360 圆环 footprint 的几何：手算对照 + 边界情形。"""
import math
import sys

sys.path.insert(0, r"<仓库根>\Code")
import pano360_coverage as pc

ok = True


def chk(cond, label, extra=""):
    global ok
    if not cond:
        ok = False
    print("  [%s] %s%s" % ("OK" if cond else "FAIL", label,
                           (" -> " + str(extra)) if extra else ""))


print("=== 1) 径向标度 ===")
chk(abs(pc.DEG_PER_UNIT_R - 104.0) < 0.5, "每单位半径 104°（两段实测一致到 0.02%）",
    "%.2f" % pc.DEG_PER_UNIT_R)
chk(abs(pc.theta_of_r(1.0) - 104.0) < 1e-9, "半径 1.0 -> 极角 104°")
chk(abs(pc.r_of_theta(90.0) - 90.0 / 104.0) < 1e-9,
    "正下方（极角 90°）落在半径 %.3f 处" % pc.r_of_theta(90.0))
chk(abs(pc.r_of_theta(52.0) - 0.5) < 1e-9, "极角 52° -> 半径 0.5", pc.r_of_theta(52.0))

print("\n=== 2) 地面距离：d = h / tan(仰角) ===")
chk(pc.ring_visibility(100.0, 45.0) is not None and
    abs(pc.ring_visibility(100.0, 45.0) - 100.0) < 1e-9, "仰角 45°、h=100 -> d=100 m")
chk(abs(pc.ring_visibility(100.0, 80.0) - 100 / math.tan(math.radians(80))) < 1e-9,
    "仰角 80° -> d=%.2f m（近）" % pc.ring_visibility(100.0, 80.0))
chk(pc.ring_visibility(100.0, 0.0) is None, "仰角 0（地平线）不落地 -> None")
chk(pc.ring_visibility(100.0, -10.0) is None, "仰角为负不落地 -> None")
chk(pc.ring_visibility(100.0, 89.9) < 1.0, "仰角 89.9° -> 几乎正下方，d<1 m",
    "%.3f" % pc.ring_visibility(100.0, 89.9))

print("\n=== 3) 圆环内外半径（命名容易搞反，这里钉住）===")
# 相机水平：画面上边缘仰角 +52°（对应极角 38° 那一圈？不 —— 这里直接给仰角）
ri, ro = pc.ring_radii(100.0, lat_top_deg=50.0, lat_bottom_deg=20.0)
chk(abs(ri - 100 / math.tan(math.radians(50))) < 1e-9,
    "内半径 = 用**大**仰角算（看最近）", "%.2f m" % ri)
chk(abs(ro - 100 / math.tan(math.radians(20))) < 1e-9,
    "外半径 = 用**小**仰角算（看最远）", "%.2f m" % ro)
chk(ri < ro, "内 < 外", "%.1f < %.1f" % (ri, ro))
# 传反了也要给出同样的结果（函数内部取 min/max）
ri2, ro2 = pc.ring_radii(100.0, 20.0, 50.0)
chk(abs(ri2 - ri) < 1e-9 and abs(ro2 - ro) < 1e-9, "两个参数传反了结果不变（内部取 min/max）")

print("\n=== 4) 外半径会在仰角趋近 0 时发散（所以要能截断）===")
ri3, ro3 = pc.ring_radii(100.0, 50.0, 0.0)
chk(math.isinf(ro3), "仰角 0 -> 外半径 = inf（看得无穷远）", ro3)
ri4, ro4 = pc.ring_for_frame(100.0, 50.0, 0.0, near_m=800.0)
chk(abs(ro4 - 800.0) < 1e-9, "给了 near_m 就截断到 800 m", "%.0f" % ro4)

print("\n=== 5) 一帧 360 的实际覆盖量级（用真实高度）===")
# 素材 0002 段：高度 ~25.5 m、相机水平（360）
h = 25.5
for el in (60, 45, 30, 15, 5):
    d = pc.ring_visibility(h, float(el))
    print("    h=%.1f m  仰角 %2d°  ->  地面距离 %8.1f m" % (h, el, d))
ri5, ro5 = pc.ring_radii(h, 89.0, 5.0)
print("    => 一帧覆盖的圆环: 内 %.2f m ~ 外 %.1f m" % (ri5, ro5))
chk(ro5 > ri5, "外 > 内")

print("\n=== 6) 与针孔那套的对照（说明为什么不能复用）===")
import coverage as cov
has_pinhole = hasattr(cov, "frame_footprint")
chk(has_pinhole, "针孔的 frame_footprint 仍在（360 那套不动它）")
print("    针孔：四角多边形（矩形视场）；360：圆环（仰角只由行决定）")
print("    两者几何不同，所以 360 单起一族函数 —— 这是刻意的。")

print("\n结果:", "全部通过" if ok else "有失败项")
raise SystemExit(0 if ok else 1)
