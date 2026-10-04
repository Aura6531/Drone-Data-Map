import re, sys, io
from pathlib import Path
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8")

SERVED = Path(r"<仓库根>\Data\DJI_202609240950_001")
RX_FOCAL = re.compile(r"\[focal_len:\s*([-\d.]+)\]")
RX_DZOOM = re.compile(r"\[dzoom_ratio:\s*([-\d.]+)\]")

def load(tag):
    f, d = [], []
    with (SERVED / f"DJI_20260924095258_0001_{tag}.srt").open(encoding="utf-8", errors="replace") as h:
        for line in h:
            if "latitude" not in line:
                continue
            m = RX_FOCAL.search(line)
            f.append(float(m.group(1)) if m else None)
            m = RX_DZOOM.search(line)
            d.append(float(m.group(1)) if m else None)
    return f, d

print("=== 焦距直方图：判断是「一颗连续变焦镜头」还是「多颗定焦镜头切换」===")
for tag in ("V", "S", "T"):
    f, d = load(tag)
    print(f"\n--- {tag}（{len(f)} 帧）---")
    buckets = Counter()
    for v in f:
        buckets[int(v // 10) * 10] += 1
    for lo in sorted(buckets):
        pct = 100 * buckets[lo] / len(f)
        bar = "#" * max(1, int(pct / 1.2))
        print(f"   {lo:>4}-{lo+9:<4} mm  {buckets[lo]:>6} 帧  {pct:>5.1f}%  {bar}")

print("\n=== 排除数码变焦后的「光学焦距」分布（焦距 / 数码变焦）===")
for tag in ("V", "S", "T"):
    f, d = load(tag)
    optical = [round(a / b, 1) for a, b in zip(f, d) if a and b]
    c = Counter(optical)
    print(f"\n--- {tag} 光学焦距取值（取出现最多的 12 个）---")
    for v, n in c.most_common(12):
        print(f"   {v:>7.1f} mm  {n:>7} 帧  {100*n/len(optical):>5.1f}%")
    near = [v for v in optical if abs(v - round(v)) < 0.05]
    if near:
        print(f"   整数光学焦距的帧占比: {100*len(near)/len(optical):.1f}%")
