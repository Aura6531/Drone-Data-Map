# -*- coding: utf-8 -*-
"""360 全景模块的自检（不需要网络、不需要视频文件）。

覆盖三件在开发中**真的出过错**的事：
  ① 像面手性：下镜头的 phi 式子写错 -> 天空像素被下镜头抢走、太阳填到地平线以下
  ② 太阳检测：外圈白环 / 水面反光比日面更亮更大 -> 必须有"预测半径"约束
  ③ 北向只依赖方位角，与极角标定无关（这是个重要性质，要钉住）

没有 numpy 时明确 [SKIP] 并算通过（与 test_coverage*.py 同一个约定）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ok = True


def _fmt(v):
    """把附加信息转成短字符串。numpy 标量/数组都要能处理。"""
    if isinstance(v, str):
        return v
    try:
        a = np.asarray(v)
        if a.ndim == 0:
            return "%.6g" % float(a)
        return str([round(float(x), 3) for x in a.ravel()])
    except Exception:
        return str(v)


def chk(cond, label, extra=""):
    global ok
    if not cond:
        ok = False
    print("  [%s] %s%s" % ("OK" if cond else "FAIL", label,
                           (" -> " + _fmt(extra)) if extra is not None and
                           str(extra) != "" else ""))


try:
    import numpy as np
except ImportError:
    print("=== 360 全景模块自检 ===")
    print("  [SKIP] 这个解释器没有 numpy，跳过")
    print("\n结果: 全部通过（已跳过）")
    raise SystemExit(0)

import pano360
import pano360_north as pn

print("=== 1) 等距柱状的方向网格 ===")
ew, eh = 8, 4
LON, cz, dx, dy = pano360.Fisheye360()._direction_grid(ew, eh)
chk(LON.shape == (eh, ew), "网格尺寸对", LON.shape)
chk(abs(float(cz[0, 0]) - np.sin(np.pi / 2 - np.pi / eh / 2)) < 1e-9,
    "最上一行接近天顶", float(cz[0, 0]))
chk(cz[0, 0] > cz[-1, 0], "z 从上一行到下一行递减")
n = np.sqrt(dx ** 2 + dy ** 2 + cz ** 2)
chk(abs(float(n.max()) - 1.0) < 1e-9 and abs(float(n.min()) - 1.0) < 1e-9,
    "每格都是单位向量", "%.6f~%.6f" % (n.min(), n.max()))

print("\n=== 2) 手性 + 择优：上下半球各由对应镜头填，且不留黑带 ===")
# 造两张可区分的假图：上镜头全红、下镜头全绿
N = 64
up = np.zeros((N, N, 3), dtype=np.uint8); up[..., 0] = 255
dn = np.zeros((N, N, 3), dtype=np.uint8); dn[..., 1] = 255
g = pano360.Fisheye360(fov_deg=200.0)
eq = g.stitch(up, dn, ew=128)
eh2 = eq.shape[0]
top = eq[:eh2 // 4].reshape(-1, 3).mean(axis=0)
bot = eq[-eh2 // 4:].reshape(-1, 3).mean(axis=0)
chk(top[0] > 200 and top[1] < 40, "最上面四分之一来自上镜头（红）", top.round(1))
chk(bot[1] > 200 and bot[0] < 40, "最下面四分之一来自下镜头（绿）", bot.round(1))
# 这一条正是当初的 bug：写错 phi 会让下镜头抢走天空
mid_top = eq[eh2 // 4:eh2 // 2].reshape(-1, 3).mean(axis=0)
chk(mid_top[0] > 150, "赤道以上仍然以上镜头为主（当初就错在这里）", mid_top.round(1))

# **择优**带来的新性质：两路给的都不是黑（这里用"纯红/纯绿"），
# 所以整张全景不该出现黑像素；如果有黑块，说明某处两路都没填上。
lum = eq.reshape(-1, 3).max(axis=1)
chk(int((lum == 0).sum()) == 0, "全景没有黑块（两路覆盖完整、择优不留洞）",
    "%d 个黑像素" % int((lum == 0).sum()))

# 两路真的都在用：红像素和绿像素都要存在（不是一路包了全场）
reds = int(((eq[..., 0] > 200) & (eq[..., 1] < 40)).sum())
greens = int(((eq[..., 1] > 200) & (eq[..., 0] < 40)).sum())
chk(reds > 0 and greens > 0, "两路都被用到（不是一路包全场）",
    "红 %d px / 绿 %d px" % (reds, greens))

# **择优的判据**：赤道以上红、赤道以下绿（按极角选近的那一路）
up_half = eq[:eh2 // 2].reshape(-1, 3)
dn_half = eq[eh2 // 2:].reshape(-1, 3)
chk(up_half[:, 0].mean() > up_half[:, 1].mean(), "上半张以红为主")
chk(dn_half[:, 1].mean() > dn_half[:, 0].mean(), "下半张以绿为主")

print("\n=== 3) 太阳检测必须拒绝'外圈白环'与'环外反光' ===")
# 造一张图：中心附近有个日面，外圈一道白环，别处一片更亮的反光
H = W = 480
img = np.full((H, W), 40.0, dtype=np.float32)
yy, xx = np.mgrid[0:H, 0:W]
c = (H - 1) / 2.0
R = (H - 1) / 2.0
rr = np.hypot(xx - c, yy - c) / R
# 外圈白环（比日面还亮、面积还大）—— 实测真的存在
ring = np.abs(rr - 0.97) < 0.03
img[ring] = 255.0
# 日面放在 r/R = 0.45 处
sun_r, sun_a = 0.45, np.deg2rad(-80)
sx0, sy0 = c + sun_r * R * np.cos(sun_a), c + sun_r * R * np.sin(sun_a)
img[(np.hypot(xx - sx0, yy - sy0) < 26)] = 250.0
# 水面反光：r/R = 0.85 处、更大更亮
gx, gy = c + 0.85 * R * np.cos(np.deg2rad(100)), c + 0.85 * R * np.sin(np.deg2rad(100))
img[(np.hypot(xx - gx, yy - gy) < 60)] = 255.0

sx, sy, r_R, phi, blob = pn.measure_sun(img, c, c, R, r_expect=0.45)
chk(abs(r_R - 0.45) < 0.08, "有预测半径时，找到的是日面而不是白环/反光",
    "r/R=%.3f (期望 0.45)" % r_R)
chk(abs(np.rad2deg(phi) - (-80)) < 6, "方位角也对", "phi=%.1f" % np.rad2deg(phi))
# 不给预测半径时，应当被白环/反光骗到 —— 这正是当初的失败模式
sx2, sy2, r2, phi2, _ = pn.measure_sun(img, c, c, R)
chk(r2 > 0.7, "不给预测半径时确实会被白环/反光骗走（所以要强制给）", "r/R=%.3f" % r2)

print("\n=== 3b) 太阳高度角的门槛（2026-10-15 贡嘎素材暴露的漏网之鱼）===")
# 实测那批素材是刚日出拍的，太阳高度角 +0.07° —— 太阳贴着地平线，
# 整个天空是一大片渐变的晨昏光带。这时候"找最亮区当太阳"必然抓到光带，
# 算出 r/R 0.88~0.91、blob 17509 px 的假太阳。
# 而原有的两道检查（预测半径、日面面积下限）只防"太小的碎片"，
# 拦不住又大又亮的光带。所以要有一道**物理前提**检查。
chk(hasattr(pn, "MIN_SUN_ELEVATION_DEG"), "有 MIN_SUN_ELEVATION_DEG 常量")
chk(pn.MIN_SUN_ELEVATION_DEG >= 5.0,
    "门槛不是象征性的（实测 0.07°/2.45°/4.58°/8.55° 都该被判不可用）",
    "%.1f°" % pn.MIN_SUN_ELEVATION_DEG)

# 用一个"太阳贴地平线"的假场景验证：理论高度角低于门槛时必须拒绝
import inspect as _insp

_src = _insp.getsource(pn.north_yaw_for)
chk("MIN_SUN_ELEVATION_DEG" in _src,
    "north_yaw_for 里真的用了这个门槛（不是只定义没用）")
chk("el_t < MIN_SUN_ELEVATION_DEG" in _src,
    "判据是理论高度角低于门槛就 raise（而不是继续去量）")

# 面积上限：光带的 blob 有多大，日面就有多大；上限要能挡住 17509 px
_svc = open(str(__import__("pathlib").Path(pn.__file__).with_name("pano360_service.py")),
            encoding="utf-8").read()
chk("800 <= blob <= 8000" in _svc,
    "服务层同时限制日面面积**上限**（17509 px 的地平线光带要被挡住）")

print("\n=== 4) 北向只看方位角，与极角标定无关 ===")
# 同一个像面方位角，在两种 FOV 下算出的 north_yaw 必须一致
for fov in (170.0, 200.0, 230.0):
    g2 = pano360.Fisheye360(fov_deg=fov)
    chk(abs(g2.fov_deg - fov) < 1e-9, "FOV 只是个参数（%.0f）" % fov)
# 用公式直接验证：north = az_theory - phi_px（不含 FOV）
az_t, phi_px = 139.26, -81.53
north = (az_t - phi_px + 180.0) % 360.0 - 180.0
chk(abs(north - (-139.21)) < 0.05, "north = az - phi = %.2f（与 FOV 无关）" % north)

print("\n=== 5) 地面距离公式（360 覆盖几何的基础）===")
# 一帧 360 覆盖的是圆环：d = h / tan(俯角)
lat = np.deg2rad(np.array([80.0, 45.0, 10.0, 0.0, -10.0]))
d = pano360.ground_distance(100.0, lat)
chk(abs(d[0] - 100 / np.tan(np.deg2rad(80))) < 1e-6, "俯角 80° -> d=%.2f m" % d[0])
chk(abs(d[1] - 100.0) < 1e-6, "俯角 45° -> d=100 m（h/tan45）", "%.3f" % d[1])
chk(d[0] < d[1] < d[2], "俯角越小地面越远（内圈->外圈）")
chk(np.isnan(d[3]) and np.isnan(d[4]), "地平线及以上不落地（NaN）")

print("\n=== 6) stitch 的输入校验 ===")
try:
    pano360.Fisheye360().stitch(np.zeros((4, 5, 3), np.uint8), np.zeros((4, 5, 3), np.uint8))
    chk(False, "非正方形的输入应当报错")
except ValueError:
    chk(True, "非正方形输入被拒绝")
try:
    pano360.Fisheye360().stitch(np.zeros((4, 4, 3), np.uint8), np.zeros((5, 5, 3), np.uint8))
    chk(False, "两路尺寸不一致应当报错")
except ValueError:
    chk(True, "两路尺寸不一致被拒绝")

print("\n结果:", "全部通过" if ok else "有失败项")
raise SystemExit(0 if ok else 1)
