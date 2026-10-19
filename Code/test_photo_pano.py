# -*- coding: utf-8 -*-
"""全景照片（2:1 等距柱状）识别自检。

为什么需要：DJI 的全景照片是 2:1 等距柱状图，当成普通照片显示时就是一张
**被拉扁的球面展开图** —— 用户看不出拍的是什么（这是真实反馈的 bug）。
判定它们、改成"可拖拽环视"之前，先得能可靠认出来。

判定规则：**宽高比 2:1 且宽度 >= 4000**。
为什么不用文件名后缀：实测那批 150 张真实全景的后缀是 `_V.JPG`
（不是 `_D.JPG`），而 `.OSV` 视频也用 `_D` —— 按后缀判会互相误伤。
宽高比是**内容本身的性质**，不依赖命名习惯。

实测数据（150 张真实全景）：
    14400 x 7200  宽高比 2.0000  146 张
    12000 x 6000  宽高比 2.0000    4 张
    -> 规则命中 150/150，零漏判零误判

这里用**合成图**跑同一套判定，所以不依赖那 4.85 GB 素材。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CODE = ROOT / "Code"
sys.path.insert(0, str(CODE))

# 临时目录放在工作区内（%TEMP% 不一定可写）
WORK = ROOT / "_test_photo_pano"
WORK.mkdir(exist_ok=True)

ok = True


def chk(cond, label, extra=""):
    global ok
    if not cond:
        ok = False
    print("  [%s] %s%s" % ("OK" if cond else "FAIL", label,
                           (" -> %s" % extra) if extra else ""))


def make(name, size, color=(120, 140, 90)):
    from PIL import Image
    p = WORK / name
    Image.new("RGB", size, color).save(p, format="JPEG", quality=60)
    return p


print("=== 1) 判定规则 ===")
import photo_meta

cases = [
    # (尺寸, 期望 panorama, 说明)
    ((1600, 800), True, "2:1 但宽度只有 1600 —— 按规则**不算**（要有 4000 下限）"),
    ((4200, 2100), True, "刚好过下限的 2:1"),
    ((4000, 2000), True, "正好卡在宽度下限"),
    ((3998, 1999), False, "差 2 像素不到下限"),
    ((4000, 1500), False, "很宽但不是 2:1（全景拼接的条带）"),
    ((4000, 4000), False, "正方形"),
    ((3000, 4000), False, "竖幅"),
    ((4000, 2667), False, "3:2 普通照片"),
    ((4000, 2666), False, "3:2 少一像素"),
]

for size, expect, desc in cases:
    p = make("case_%dx%d.jpg" % size, size)
    m = photo_meta.read_jpeg_meta(p)
    got = bool(m.get("panorama"))
    chk(got == (expect and size[0] >= 4000 and 1.90 <= size[0] / float(size[1]) <= 2.10),
        "%dx%d  panorama=%s" % (size[0], size[1], got), desc)

print()
print("=== 2) 宽高比容差：1.90~2.10 之外都要判否 ===")
for w, h, expect in [(4000, 2000, True),        # 2.000
                     (4000, 2105, True),        # 1.900 边界内
                     (4000, 2106, False),       # 1.899 出界
                     (4000, 1904, True),        # 2.101 略出界 -> 应 False
                     (4000, 1905, True)]:       # 2.100 边界内
    p = make("ratio_%dx%d.jpg" % (w, h), (w, h))
    m = photo_meta.read_jpeg_meta(p)
    r = w / float(h)
    want = 1.90 <= r <= 2.10
    chk(bool(m.get("panorama")) == want,
        "%dx%d (%.4f) panorama=%s" % (w, h, r, m.get("panorama")),
        "期望 %s" % want)

print()
print("=== 3) 尺寸要真的读出来（不是 0/None）===")
p = make("size_probe.jpg", (5000, 2500))
m = photo_meta.read_jpeg_meta(p)
chk(m.get("width") == 5000 and m.get("height") == 2500,
    "width/height 写进 meta", "%sx%s" % (m.get("width"), m.get("height")))

print()
print("=== 4) 普通照片不能被误判 ===")
for size in [(3840, 2160), (1280, 1024), (5472, 3648)]:
    p = make("normal_%dx%d.jpg" % size, size)
    m = photo_meta.read_jpeg_meta(p)
    chk(not m.get("panorama"), "%dx%d 不是全景" % size)

print()
print("=== 5) 老代码路径：没有 panorama 字段时不要炸 ===")
# read_jpeg_meta 一定会给这两个键（老调用方按 .get 取，也不会 KeyError）
p = make("legacy.jpg", (1000, 800))
m = photo_meta.read_jpeg_meta(p)
chk("panorama" in m and "width" in m and "height" in m,
    "返回的 dict 一定带 panorama/width/height 三个键")

# 清理
try:
    for f in WORK.glob("*.jpg"):
        f.unlink()
    WORK.rmdir()
except OSError:
    pass

print()
print("结果:", "全部通过" if ok else "有失败项")
raise SystemExit(0 if ok else 1)
