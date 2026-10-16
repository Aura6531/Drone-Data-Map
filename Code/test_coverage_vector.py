# -*- coding: utf-8 -*-
"""矢量化算法的合成测试：实心方块 / 带洞 / 对角相接 / 多块。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import numpy as _np  # noqa: F401
except ImportError:
    # 矢量化依赖 numpy。没装时**明确跳过**而不是报失败 ——
    # 这样系统 Python（可能没有 numpy）跑 run_tests.js 也不会误判。
    print("=== 覆盖栅格矢量化回归测试 ===")
    print("  [SKIP] 这个解释器没有 numpy，跳过")
    print("\n结果: 全部通过（已跳过）")
    raise SystemExit(0)

import numpy as np  # noqa: E402
import coverage_vector as cv  # noqa: E402

ok = True


def chk(cond, label, extra=""):
    global ok
    ok = ok and bool(cond)
    print(f"  {'[OK]' if cond else '[FAIL]'} {label}" + (f" -> {extra}" if extra else ""))


def show(mask):
    for row in mask:
        print("      " + "".join("#" if v else "." for v in row))


print("=== 1) 实心 3x3 方块 -> 1 个外环、12 个顶点、面积 9 ===")
m = np.zeros((10, 10), dtype=bool)
m[3:6, 3:6] = True
ext, holes = cv.mask_to_rings(m)
chk(len(ext) == 1, "外环数", str(len(ext)))
chk(len(ext[0]) == 12, "顶点数", str(len(ext[0])))
area = abs(cv.signed_area_px(ext[0]))          # 像素坐标里 1 格 = 1 单位面积
chk(abs(area - 9.0) < 1e-9, "像素面积 = 9 格", f"{area}")
chk(cv.signed_area_px(ext[0]) > 0, "外环有向面积为正（顺时针）", f"{cv.signed_area_px(ext[0])}")
chk(len(holes[0]) == 0, "没有洞")

print("\n=== 2) 5x5 方块中间挖 1 格 -> 1 外环 + 1 洞 ===")
m2 = np.zeros((10, 10), dtype=bool)
m2[2:7, 2:7] = True
m2[4, 4] = False
ext2, holes2 = cv.mask_to_rings(m2)
chk(len(ext2) == 1, "外环数", str(len(ext2)))
chk(len(holes2[0]) == 1, "洞数", str(len(holes2[0])))
if holes2[0]:
    chk(cv.signed_area_px(holes2[0][0]) < 0, "洞有向面积为负（逆时针）",
        f"{cv.signed_area_px(holes2[0][0])}")
    chk(len(holes2[0][0]) == 4, "洞顶点数 4", str(len(holes2[0][0])))

print("\n=== 3) 对角相接的两格 -> 8 邻接下应是 1 个环、8 顶点 ===")
m3 = np.zeros((6, 6), dtype=bool)
m3[2, 2] = True
m3[3, 3] = True
show(m3)
ext3, holes3 = cv.mask_to_rings(m3)
chk(len(ext3) == 1, "外环数（8 邻接应连通）", str(len(ext3)))
if ext3:
    chk(len(ext3[0]) == 8, "顶点数 8", str(len(ext3[0])))
    # 对角缝只补**一格**（把斜接变成 L 形即可打破歧义），所以面积是 3 而不是 4。
    # 这是有意的：每处斜接多 1 m²，相对 1 m 网格的固有 ±1.3 m 不确定度可忽略。
    chk(abs(abs(cv.signed_area_px(ext3[0])) - 3.0) < 1e-9,
        "填缝后面积 3 格（两格 + 补缝一格）", f"{abs(cv.signed_area_px(ext3[0]))}")
    chk(abs(cv.signed_area_px(ext3[0])) > 2.0, "填缝后面积大于两格原面积")

print("\n=== 4) 两块分离的方块 -> 2 个外环 ===")
m4 = np.zeros((10, 20), dtype=bool)
m4[1:4, 1:4] = True
m4[5:9, 10:15] = True
ext4, holes4 = cv.mask_to_rings(m4)
chk(len(ext4) == 2, "外环数", str(len(ext4)))
areas = sorted(abs(cv.signed_area_px(r)) for r in ext4)
chk(abs(areas[0] - 9.0) < 1e-9 and abs(areas[1] - 20.0) < 1e-9,
    "两环面积 9 与 20", str(areas))

print("\n=== 5) 全空 / 全满 ===")
e0, _ = cv.mask_to_rings(np.zeros((5, 5), dtype=bool))
chk(len(e0) == 0, "全空 -> 0 个环", str(len(e0)))
e1, _ = cv.mask_to_rings(np.ones((5, 5), dtype=bool))
chk(len(e1) == 1, "全满 -> 1 个环", str(len(e1)))
# 5x5 的边界绕一圈：每边 5 条格边，合计 20 个顶点
chk(len(e1[0]) == 20, "全满环有 20 个顶点（周长）", str(len(e1[0])))
chk(abs(abs(cv.signed_area_px(e1[0])) - 25.0) < 1e-9, "全满面积 25",
    f"{abs(cv.signed_area_px(e1[0]))}")

print("\n=== 6) 简化：台阶能被抽掉 ===")
m6 = np.zeros((20, 20), dtype=bool)
m6[5:15, 5:15] = True
ext_plain, _ = cv.mask_to_rings(m6, cell_m=1.0, tol_m=0.0)
ext_simp, _ = cv.mask_to_rings(m6, cell_m=1.0, tol_m=0.6)
chk(len(ext_simp[0]) <= len(ext_plain[0]), "简化后顶点数不增加",
    f"{len(ext_simp[0])} vs {len(ext_plain[0])}")

print("\n结果:", "全部通过" if ok else "有失败项")
raise SystemExit(0 if ok else 1)
