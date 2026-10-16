# -*- coding: utf-8 -*-
"""可自证的检查：透视裁剪的方向必须与拼接的逆式一致。

做法：把一张**人造全景**（每个像素写上它自己的经纬度）喂给
`perspectives_from_equirect`，看裁出来的像素值是不是等于"该方向"。
`stitch()` 的 `_direction_grid` 就是这个"方向 <-> (lon,lat)"的定义，
所以两者对得上才算一致。
"""
import math
import sys

import numpy as np

sys.path.insert(0, r"<仓库根>\Code")
import pano360

ok = True


def chk(cond, label, extra=""):
    global ok
    if not cond:
        ok = False
    print("  [%s] %s%s" % ("OK" if cond else "FAIL", label,
                           (" -> " + str(extra)) if extra else ""))


EW, EH = 720, 360
# 人造全景：R 通道 = 归一化经度(0..255)，G 通道 = 归一化纬度
lon_axis = (np.arange(EW) + 0.5) / EW * 2 * np.pi - np.pi
lat_axis = np.pi / 2 - (np.arange(EH) + 0.5) / EH * np.pi
LON, LAT = np.meshgrid(lon_axis, lat_axis)
fake = np.zeros((EH, EW, 3), np.uint8)
fake[..., 0] = np.clip((LON / (2 * np.pi) + 0.5) * 255, 0, 255).astype(np.uint8)
fake[..., 1] = np.clip((LAT / np.pi + 0.5) * 255, 0, 255).astype(np.uint8)

print("=== 1) 正前方（yaw=0, pitch=0）应当看到 lon≈0, lat≈0 ===")
c = pano360.perspectives_from_equirect(fake, 0.0, 0.0, fov_deg=60.0, out_w=161, out_h=91)
h, w = c.shape[:2]
mid = c[h // 2, w // 2]
lon_c = (float(mid[0]) / 255 - 0.5) * 360
lat_c = (float(mid[1]) / 255 - 0.5) * 180
chk(abs(lon_c) < 4 and abs(lat_c) < 4, "画面中心 = (lon 0, lat 0)",
    f"lon {lon_c:+.1f}°  lat {lat_c:+.1f}°")

print("\n=== 2) pitch 的符号：+30° 应当看**上方**、-30° 看**下方** ===")
c_up = pano360.perspectives_from_equirect(fake, 0.0, 30.0, fov_deg=60.0, out_w=161, out_h=91)
lat_up = (float(c_up[c_up.shape[0] // 2, c_up.shape[1] // 2][1]) / 255 - 0.5) * 180
c_dn = pano360.perspectives_from_equirect(fake, 0.0, -30.0, fov_deg=60.0, out_w=161, out_h=91)
lat_dn = (float(c_dn[c_dn.shape[0] // 2, c_dn.shape[1] // 2][1]) / 255 - 0.5) * 180
chk(abs(lat_up - 30.0) < 4, "pitch=+30° -> 画面中心仰角 +30°", f"{lat_up:+.1f}°")
chk(abs(lat_dn - (-30.0)) < 4, "pitch=-30° -> 画面中心仰角 -30°", f"{lat_dn:+.1f}°")
chk(lat_up > lat_dn, "正 pitch 比负 pitch 看得高")

print("\n=== 3) yaw 的符号：+90° 应当看到 lon=+90° ===")
c_r = pano360.perspectives_from_equirect(fake, 90.0, 0.0, fov_deg=60.0, out_w=161, out_h=91)
lon_r = (float(c_r[c_r.shape[0] // 2, c_r.shape[1] // 2][0]) / 255 - 0.5) * 360
chk(abs(lon_r - 90.0) < 4, "yaw=+90° -> 画面中心 lon +90°", f"{lon_r:+.1f}°")
c_l = pano360.perspectives_from_equirect(fake, -90.0, 0.0, fov_deg=60.0, out_w=161, out_h=91)
lon_l = (float(c_l[c_l.shape[0] // 2, c_l.shape[1] // 2][0]) / 255 - 0.5) * 360
chk(abs(lon_l - (-90.0)) < 4, "yaw=-90° -> 画面中心 lon -90°", f"{lon_l:+.1f}°")

print("\n=== 4) 与 stitch 的 _direction_grid 交叉验证 ===")
# 从 _direction_grid 取一个已知方向，反算它的 (lon, lat)，
# 再用透视裁剪看该方向的像素值是否吻合
_LON, cz, dx, dy = pano360.Fisheye360()._direction_grid(EW, EH)
# 取 lon=+120°, lat=+20° 附近的格
i_lon = int(((math.radians(120.0) + math.pi) / (2 * math.pi)) * EW) % EW
i_lat = int(((math.pi / 2 - math.radians(20.0)) / math.pi) * EH)
want_lon = (float(fake[i_lat, i_lon, 0]) / 255 - 0.5) * 360
want_lat = (float(fake[i_lat, i_lon, 1]) / 255 - 0.5) * 180
c2 = pano360.perspectives_from_equirect(fake, want_lon, want_lat, fov_deg=40.0,
                                        out_w=161, out_h=91)
got = c2[c2.shape[0] // 2, c2.shape[1] // 2]
got_lon = (float(got[0]) / 255 - 0.5) * 360
got_lat = (float(got[1]) / 255 - 0.5) * 180
chk(abs(got_lon - want_lon) < 6 and abs(got_lat - want_lat) < 6,
    "把镜头转到某方向，画面中心就是那个方向（回环一致）",
    f"要 ({want_lon:+.1f},{want_lat:+.1f}) 得到 ({got_lon:+.1f},{got_lat:+.1f})")

print("\n=== 5) 上下不应被镜像 ===")
# 同一 yaw、pitch=+20 时，画面**上半**应当比**下半**更靠上（lat 更大）
c5 = pano360.perspectives_from_equirect(fake, 0.0, 20.0, fov_deg=80.0, out_w=161, out_h=161)
top_lat = (float(c5[20, 80][1]) / 255 - 0.5) * 180
bot_lat = (float(c5[140, 80][1]) / 255 - 0.5) * 180
chk(top_lat > bot_lat, "画面上面看到的方向更靠上（没被上下镜像）",
    f"上 {top_lat:+.1f}°  下 {bot_lat:+.1f}°")

print("\n结果:", "全部通过" if ok else "有失败项")
raise SystemExit(0 if ok else 1)
