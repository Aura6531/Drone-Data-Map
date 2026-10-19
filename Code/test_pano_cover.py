# -*- coding: utf-8 -*-
"""全景"透视封面"的投影约定自检。

为什么要有这份：封面要在**服务端**（Python）生成，而用户点开的是
**浏览器里**的 360 查看器（JS）。两边的 yaw/pitch 约定只要差一点，
封面就会和"点开第一眼"看到的画面不一样 —— 而且**看起来都很正常**，
不会报错，只有把两张图并排比对才发现。所以约定必须被测试钉住。

做法：造一张合成的等距柱状图，在**已知位置**放一个亮点，
然后检查 `perspectives_from_equirect` 把那个亮点投到了哪儿。
这不需要任何真实素材，也不依赖浏览器。

约定的来源（两份实现都是这个约定）：
  Code/pano360.py  perspectives_from_equirect()
  Code/pano360_player.html  draw()
    · 等距柱状图：u = (lon/2π + 0.5) * W，v = (0.5 - lat/π) * H
    · yaw  = 0 看的是**图像水平中心**（lon=0）
    · yaw  > 0 往 u 增大的方向看（图像右侧）
    · pitch > 0 **抬头**（看 v 减小的方向，即图像上方）
    · fov 是**水平**视场角
"""
import sys
from pathlib import Path

import numpy as np

CODE = Path(__file__).resolve().parent
sys.path.insert(0, str(CODE))

import pano360

ok = True


def chk(cond, label, extra=""):
    global ok
    if not cond:
        ok = False
    print("  [%s] %s%s" % ("OK" if cond else "FAIL", label,
                           (" -> %s" % extra) if extra else ""))


EW, EH = 720, 360
PATCH = 6


def make_equirect(patch_u_frac, patch_v_frac):
    """全黑底 + 一个亮方块（位置用 0..1 的比例给）。"""
    img = np.zeros((EH, EW, 3), dtype=np.uint8)
    cu = int(round(patch_u_frac * EW)) % EW
    cv = int(round(patch_v_frac * EH))
    cv = max(0, min(EH - 1, cv))
    for dv in range(-PATCH, PATCH + 1):
        for du in range(-PATCH, PATCH + 1):
            y = cv + dv
            if 0 <= y < EH:
                img[y, (cu + du) % EW] = (255, 255, 255)
    return img


def peak_of(persp):
    """透视图的亮度重心（归一化到 0..1，便于断言）。"""
    g = persp.astype(np.float64).mean(axis=2)
    if g.max() <= 1:
        return None
    h, w = g.shape
    ys, xs = np.mgrid[0:h, 0:w]
    total = g.sum()
    return (float((xs * g).sum() / total) / w, float((ys * g).sum() / total) / h)


print("=== 1) yaw=0 / pitch=0 看的是图像水平中心 ===")
equi = make_equirect(0.5, 0.5)
p = pano360.perspectives_from_equirect(equi, 0.0, 0.0, fov_deg=75, out_w=320)
c = peak_of(p)
chk(c is not None, "画面上出现了亮点", str(c))
if c:
    chk(abs(c[0] - 0.5) < 0.06 and abs(c[1] - 0.5) < 0.06,
        "亮点落在透视图中心", "(%.3f, %.3f)" % c)

print()
print("=== 2) yaw 的符号：正 yaw 往图像右侧看 ===")
# lon = +90° 对应 u = (90/360 + 0.5) * W = 0.75 W
equi = make_equirect(0.75, 0.5)
p = pano360.perspectives_from_equirect(equi, 90.0, 0.0, fov_deg=75, out_w=320)
c = peak_of(p)
chk(c is not None and abs(c[0] - 0.5) < 0.08,
    "yaw=+90 时，u=0.75 那一点正好在画面中心", str(c))

equi = make_equirect(0.25, 0.5)
p = pano360.perspectives_from_equirect(equi, -90.0, 0.0, fov_deg=75, out_w=320)
c = peak_of(p)
chk(c is not None and abs(c[0] - 0.5) < 0.08,
    "yaw=-90 时，u=0.25 那一点正好在画面中心", str(c))

print()
print("=== 3) pitch 的符号：正 pitch 抬头（看图像上方）===")
# lat = +45° -> v = (0.5 - 45/180) * H = 0.25 H
equi = make_equirect(0.5, 0.25)
p = pano360.perspectives_from_equirect(equi, 0.0, 45.0, fov_deg=75, out_w=320)
c = peak_of(p)
chk(c is not None and abs(c[1] - 0.5) < 0.09,
    "pitch=+45 时，v=0.25（图像上方）那一点在画面中心", str(c))

# lat = -45° -> v = 0.75 H
equi = make_equirect(0.5, 0.75)
p = pano360.perspectives_from_equirect(equi, 0.0, -45.0, fov_deg=75, out_w=320)
c = peak_of(p)
chk(c is not None and abs(c[1] - 0.5) < 0.09,
    "pitch=-45 时，v=0.75（图像下方）那一点在画面中心 —— 低头看地面", str(c))

print()
print("=== 4) 符号反了会被抓到（反向断言）===")
# 如果实现把 pitch 搞反（和 stitch 那次踩过的一样），下面这条会失败
equi = make_equirect(0.5, 0.25)
p = pano360.perspectives_from_equirect(equi, 0.0, -45.0, fov_deg=75, out_w=320)
c = peak_of(p)
chk(c is None or abs(c[1] - 0.5) > 0.2,
    "pitch=-45 看不到 v=0.25 那一点（说明 pitch 没有被搞反）", str(c))

print()
print("=== 5) fov 是水平视场角（左右看到多少由它定）===")
# 只放**一个**偏心点：偏离中心 0.05*W（= 18°）。
# 注意别复用上面那张已经带中心亮点的图 —— fov 收窄后中心亮点会被放大，
# 反而让"窄画面"的亮像素更多（第一版就这么写错了，测出来 narrow > wide）。
# fov=20 时水平半视场只有 10°，18° 那一点应当在画面外。
equi = np.zeros((EH, EW, 3), dtype=np.uint8)
cu = (EW // 2 + int(round(0.05 * EW))) % EW
for dv in range(-PATCH, PATCH + 1):
    for du in range(-PATCH, PATCH + 1):
        equi[EH // 2 + dv, (cu + du) % EW] = (255, 255, 255)
wide = pano360.perspectives_from_equirect(equi, 0.0, 0.0, fov_deg=75, out_w=320)
narrow = pano360.perspectives_from_equirect(equi, 0.0, 0.0, fov_deg=20, out_w=320)
wide_on = int((wide.astype(np.float64).mean(axis=2) > 8).sum())
narrow_on = int((narrow.astype(np.float64).mean(axis=2) > 8).sum())
chk(wide_on > 0 and narrow_on == 0,
    "偏心 18° 的点：fov=75 看得到，fov=20 看不到（水平视场角）",
    "wide=%d narrow=%d 亮像素" % (wide_on, narrow_on))

print()
print("=== 6) 输出尺寸与 dtype 契约 ===")
p = pano360.perspectives_from_equirect(equi, 0.0, 0.0, fov_deg=75, out_w=720, out_h=405)
chk(p.shape == (405, 720, 3), "给定 out_h 时形状为 (out_h, out_w, 3)", str(p.shape))
chk(p.dtype == np.uint8, "dtype 与输入一致（uint8）", str(p.dtype))
p2 = pano360.perspectives_from_equirect(equi, 0.0, 0.0, fov_deg=75, out_w=480)
chk(p2.shape == (270, 480, 3), "不给 out_h 时按 16:9 推", str(p2.shape))

print()
print("结果:", "全部通过" if ok else "有失败项")
raise SystemExit(0 if ok else 1)
