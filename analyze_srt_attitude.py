import re, sys, io, statistics as st
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DIR = Path(r"<仓库根>\Data\DJI_202609240950_001")

FIELDS = {
    "focal_len":  re.compile(r"\[focal_len:\s*([-\d.]+)\]"),
    "dzoom":      re.compile(r"\[dzoom_ratio:\s*([-\d.]+)\]"),
    "latitude":   re.compile(r"\[latitude:\s*([-\d.]+)\]"),
    "longitude":  re.compile(r"\[longitude:\s*([-\d.]+)\]"),
    "rel_alt":    re.compile(r"\[rel_alt:\s*([-\d.]+)"),
    "abs_alt":    re.compile(r"abs_alt:\s*([-\d.]+)\]"),
    "gb_yaw":     re.compile(r"gb_yaw:\s*([-\d.]+)"),
    "gb_pitch":   re.compile(r"gb_pitch:\s*([-\d.]+)"),
    "gb_roll":    re.compile(r"gb_roll:\s*([-\d.]+)"),
    "iso":        re.compile(r"\[iso:\s*([-\d.]+)\]"),
}

for name in ("DJI_20260924095258_0001_V.srt",
             "DJI_20260924095258_0001_T.srt",
             "DJI_20260924095258_0001_S.srt"):
    path = DIR / name
    if not path.exists():
        print(f"{name}: 不存在")
        continue

    print("=" * 78)
    print(f"{name}   {path.stat().st_size/1048576:.2f} MB")
    print("=" * 78)

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    # 先看一条完整记录，确认到底有哪些字段
    for i, ln in enumerate(lines):
        if "latitude" in ln:
            print("一条完整记录:")
            print("   ", ln.strip()[:400])
            break

    data = {k: [] for k in FIELDS}
    total = 0
    for ln in lines:
        if "latitude" not in ln:
            continue
        total += 1
        for k, rx in FIELDS.items():
            m = rx.search(ln)
            if m:
                try:
                    data[k].append(float(m.group(1)))
                except ValueError:
                    pass

    print(f"\n含定位的记录数: {total}")
    print(f"\n{'字段':<12}{'有值数':>8}{'最小':>12}{'最大':>12}{'均值':>12}{'标准差':>10}")
    for k in FIELDS:
        v = data[k]
        if not v:
            print(f"{k:<12}{'0':>8}{'—':>12}{'—':>12}{'—':>12}{'—':>10}")
            continue
        print(f"{k:<12}{len(v):>8}{min(v):>12.3f}{max(v):>12.3f}"
              f"{st.mean(v):>12.3f}{(st.pstdev(v) if len(v)>1 else 0):>10.3f}")

    pitch = data["gb_pitch"]
    if pitch:
        print("\ngb_pitch 分布（决定视角框的精度）：")
        buckets = [(-90,-80),(-80,-60),(-60,-40),(-40,-20),(-20,-5),(-5,5),(5,90)]
        for lo, hi in buckets:
            n = sum(1 for p in pitch if lo <= p < hi)
            if n:
                bar = "#" * max(1, int(40*n/len(pitch)))
                print(f"   [{lo:>4},{hi:>4}) {n:>7}  {100*n/len(pitch):>5.1f}%  {bar}")

    roll = data["gb_roll"]
    if roll:
        big = sum(1 for r in roll if abs(r) > 2)
        print(f"\ngb_roll |roll|>2° 的比例: {100*big/len(roll):.2f}%   （云台增稳效果）")

    yaw = data["gb_yaw"]
    if yaw:
        print(f"gb_yaw 范围: {min(yaw):.1f} ~ {max(yaw):.1f}   （航向变化 {max(yaw)-min(yaw):.0f}°）")

    h = data["rel_alt"]
    if h:
        print(f"\n相对高度 rel_alt: {min(h):.1f} ~ {max(h):.1f} m，均值 {st.mean(h):.1f} m")
        # 顺便算一下典型视场覆盖尺寸
        import math
        FOV35 = 36.0  # 35mm 全幅宽
        for label, alt in (("最低", min(h)), ("均值", st.mean(h)), ("最高", max(h))):
            if alt <= 0:
                continue
            f = st.mean(data["focal_len"]) if data["focal_len"] else 24.0
            hfov = 2*math.degrees(math.atan(FOV35/(2*f)))
            vfov = 2*math.degrees(math.atan(math.tan(math.radians(hfov/2))*9/16))
            w = 2*alt*math.tan(math.radians(hfov/2))
            hh = 2*alt*math.tan(math.radians(vfov/2))
            print(f"    高度{label} {alt:>6.1f} m -> 若正下视，地面覆盖约 {w:>6.1f} x {hh:>5.1f} m"
                  f"  (HFOV {hfov:.1f}°, VFOV {vfov:.1f}°)")
    print()
