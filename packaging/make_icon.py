"""生成程序图标：无人机箭头 + 目标点 + 一条连线（和程序里的视觉语言一致）。

画法说明（为什么这么画）：
- 先按 1024×1024 画大图，再用 LANCZOS 缩到各个尺寸 —— 小尺寸下边缘才不会锯齿。
- 底：圆角方块 + 自上而下的蓝色渐变（用程序主色 #2563EB → #1E3A8A），
  这样在深色/浅色桌面、任务栏上都看得清（透明底的小图标在 16px 下容易糊）。
- 无人机：**直接用程序里那个机头箭头**（机尖 / 两侧翼尖 / 尾部凹口，比例 0.82、0.35），
  朝向指向目标点 —— 和地图上的飞机箭头、报告里的图标是同一个形状。
- 目标点：白圈打底 + 红十字（和地图截图、视频截图上的目标点标志同一套画法）。
- 连线：从机头到目标点之间的白色虚线（就是「注视虚线」那条）。

用法：python make_icon.py   ->  生成 UAVMap.ico 与两张预览图
"""

from PIL import Image, ImageDraw
import math
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent

SIZE = 1024
BG_TOP = (37, 99, 235)        # #2563eb 程序主蓝
BG_BOTTOM = (30, 58, 138)     # #1e3a8a
WHITE = (255, 255, 255)
RED = (220, 38, 38)           # 与地图/视频截图上的红十字同色

MARGIN_RATIO = 0.13           # 圆角方块离画布边的留白
RADIUS_RATIO = 0.22           # 圆角半径


def rounded_mask(size, margin, radius):
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (margin, margin, size - margin - 1, size - margin - 1),
        radius=radius,
        fill=255
    )
    return mask


def gradient(size, top, bottom):
    image = Image.new("RGB", (size, size), top)
    draw = ImageDraw.Draw(image)

    for y in range(size):
        t = y / (size - 1)
        draw.line(
            (0, y, size, y),
            fill=tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        )

    return image


def rotate(points, degrees):
    rad = math.radians(degrees)
    cos_a, sin_a = math.cos(rad), math.sin(rad)

    return [
        (x * cos_a - y * sin_a, x * sin_a + y * cos_a)
        for x, y in points
    ]


def draw_dashed_line(draw, start, end, color, width, dash=46, gap=34):
    x0, y0 = start
    x1, y1 = end
    total = math.hypot(x1 - x0, y1 - y0)

    if total <= 0:
        return

    ux, uy = (x1 - x0) / total, (y1 - y0) / total
    position = 0.0

    while position < total:
        stop = min(position + dash, total)
        draw.line(
            (x0 + ux * position, y0 + uy * position, x0 + ux * stop, y0 + uy * stop),
            fill=color,
            width=width
        )
        position = stop + gap


def build():
    image = gradient(SIZE, BG_TOP, BG_BOTTOM).convert("RGBA")

    margin = int(SIZE * MARGIN_RATIO)
    radius = int(SIZE * RADIUS_RATIO)
    mask = rounded_mask(SIZE, margin, radius)

    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas.paste(image, (0, 0), mask)

    # 图形单独画在一层，最后和圆角遮罩一起合成 ——
    # 否则超出圆角的部分会留在透明区里（第一版左上角的飞机就露到方块外面了）
    glyph = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glyph)

    # 目标点在右下、飞机在左上，连线从左上的机头指向目标
    # （比例调过两版：飞机别顶到圆角边上，小尺寸下才不糊）
    target = (int(SIZE * 0.664), int(SIZE * 0.686))
    target_radius = int(SIZE * 0.111)

    drone_center = (int(SIZE * 0.372), int(SIZE * 0.316))
    drone_size = int(SIZE * 0.104)
    bearing = 42.0        # 机头朝右下（指向目标）

    # 连线：起点＝机头（和程序里一样，从机头开始画）
    rad = math.radians(bearing)
    nose = (
        drone_center[0] + math.sin(rad) * drone_size * 1.15,
        drone_center[1] - math.cos(rad) * drone_size * 1.15,
    )

    draw_dashed_line(draw, nose, target, (255, 255, 255, 235), width=int(SIZE * 0.026))

    # 无人机：程序里的那个箭头形状
    points = [
        (0, -drone_size),
        (drone_size * 0.82, drone_size * 0.82),
        (0, drone_size * 0.35),
        (-drone_size * 0.82, drone_size * 0.82),
    ]
    arrow = [
        (drone_center[0] + x, drone_center[1] + y)
        for x, y in rotate(points, bearing)
    ]

    draw.polygon(arrow, fill=WHITE, outline=WHITE)
    draw.line(arrow + [arrow[0]], fill=(255, 255, 255, 255), width=int(SIZE * 0.012), joint="curve")

    # 目标点：白圈打底 + 红十字
    ring = int(SIZE * 0.014)
    arm = target_radius + int(SIZE * 0.038)

    for color, width in ((WHITE, ring * 3), (RED, ring * 2)):
        draw.ellipse(
            (
                target[0] - target_radius, target[1] - target_radius,
                target[0] + target_radius, target[1] + target_radius,
            ),
            outline=color,
            width=width
        )
        draw.line((target[0] - arm, target[1], target[0] + arm, target[1]), fill=color, width=width)
        draw.line((target[0], target[1] - arm, target[0], target[1] + arm), fill=color, width=width)

    canvas.alpha_composite(glyph)
    canvas.putalpha(mask)      # 再裁一次：保证没有任何东西露在圆角方块之外

    return canvas


def main():
    icon = build()

    sizes = [16, 24, 32, 48, 64, 128, 256]
    icon.save(OUT_DIR / "UAVMap.ico", format="ICO", sizes=[(s, s) for s in sizes])
    icon.resize((256, 256), Image.LANCZOS).save(OUT_DIR / "icon_256.png")

    # 小尺寸可读性检查：把几个尺寸并排放在一起
    strip = Image.new("RGBA", (16 + 32 + 48 + 64 + 256 + 5 * 16, 256 + 32), (255, 255, 255, 255))
    x = 16

    for size in (16, 32, 48, 64, 256):
        small = icon.resize((size, size), Image.LANCZOS)
        strip.paste(small, (x, 16 + (256 - size) // 2), small)
        x += size + 16

    strip.save(OUT_DIR / "icon_sizes.png")

    print("已生成：")
    for name in ("UAVMap.ico", "icon_256.png", "icon_sizes.png"):
        path = OUT_DIR / name
        print(f"  {name}  {path.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
