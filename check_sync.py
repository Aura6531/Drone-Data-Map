import re, sys, io, bisect
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

SERVED = Path(__file__).resolve().parent / "Data" / "DJI_202609240950_001"
CUE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->")
LAT = re.compile(r"\[latitude:\s*([-\d.]+)\]")
LON = re.compile(r"\[longitude:\s*([-\d.]+)\]")
ALT = re.compile(r"\[rel_alt:\s*([-\d.]+)\s+abs_alt:\s*([-\d.]+)\]")
ATT = re.compile(r"\[gb_yaw:\s*([-\d.]+)\s+gb_pitch:\s*([-\d.]+)\s+gb_roll:\s*([-\d.]+)\]")


def parse(tag):
    times, rows = [], []
    path = SERVED / f"DJI_20260924095258_0001_{tag}.srt"
    with path.open(encoding="utf-8", errors="replace") as h:
        cur = None
        for line in h:
            m = CUE.search(line)
            if m:
                hh, mm, ss, ms = (int(x) for x in m.groups())
                cur = hh * 3600 + mm * 60 + ss + ms / 1000.0
                continue
            if "latitude" not in line or cur is None:
                continue
            la = LAT.search(line).group(1)
            lo = LON.search(line).group(1)
            al, ab = ALT.search(line).groups()
            ya, pi, ro = ATT.search(line).groups()
            times.append(cur)
            rows.append((float(la), float(lo), float(al), float(ya), float(pi), float(ro)))
            cur = None
    return times, rows


R = 6371000.0
def meters(a, b):
    import math
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


data = {}
for tag in ("V", "S", "T"):
    t, r = parse(tag)
    data[tag] = (t, r)
    print(f"{tag}: {len(t)} 条  时间轴 {t[0]:.3f} s ~ {t[-1]:.3f} s  跨度 {t[-1]-t[0]:.3f} s  中位间隔 {sorted([round(b-a,4) for a,b in zip(t,t[1:])])[len(t)//2]:.4f} s")

print()
print("=== 同一时间戳上，V 与 T 的位置/姿态是否一致？===")
tv, rv = data["V"]
tt, rt = data["T"]

def at(times, rows, t):
    i = bisect.bisect_left(times, t)
    i = min(max(i, 0), len(times) - 1)
    return rows[i]

print(f"{'时刻':>8}  {'V 位置':>22}  {'T 位置':>22}  {'水平差':>8}  {'高度差':>7}  {'航向差':>7}")
worst = 0.0
for t in (0, 1, 30, 60, 120, 300, 400, 600, 900, 1200, 1210):
    if t > tv[-1] or t > tt[-1]:
        continue
    a = at(tv, rv, t)
    b = at(tt, rt, t)
    d = meters(a, b)
    worst = max(worst, d)
    print(f"{t:>8}  {a[0]:.6f},{a[1]:.6f}  {b[0]:.6f},{b[1]:.6f}  {d:>7.2f}m  {abs(a[2]-b[2]):>6.2f}m  {abs(a[3]-b[3]):>6.1f}°")

print(f"\n同一时间戳上 V 与 T 的最大水平偏差：{worst:.2f} m")

# 用「位置最近」反推两条时间轴的偏移，看 0 偏移是不是最优
print("\n=== 反推时间轴偏移：把 T 平移多少秒，位置最吻合？===")
best = None
for shift in [x * 0.5 for x in range(-24, 25)]:
    total, n = 0.0, 0
    for idx in range(0, len(tv), 400):
        t = tv[idx]
        t2 = t + shift
        if t2 < tt[0] or t2 > tt[-1]:
            continue
        total += meters(rv[idx], at(tt, rt, t2))
        n += 1
    if n < 20:
        continue
    avg = total / n
    if best is None or avg < best[1]:
        best = (shift, avg)
    if abs(shift) <= 3:
        print(f"   T 平移 {shift:+.1f} s  ->  平均偏差 {avg:7.2f} m")

print(f"\n最优偏移：{best[0]:+.1f} s（平均偏差 {best[1]:.2f} m）")
