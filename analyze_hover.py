import json, sys, io
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

SAMPLE = Path(__file__).resolve().parent / "Data" / "DJI_202609240950_001"
g = json.loads((SAMPLE / "DJI_20260924095258_0001_V.geojson").read_text(encoding="utf-8"))
f = g["features"][0]
coords = f["geometry"]["coordinates"]
times = f["properties"]["point_times"]
n = len(coords)
print(f"总点数 {n}")

# 统计"连续完全相同坐标"的游程
runs = []
cur = 1
for i in range(1, n):
    if coords[i][0] == coords[i-1][0] and coords[i][1] == coords[i-1][1]:
        cur += 1
    else:
        runs.append(cur)
        cur = 1
runs.append(cur)

from collections import Counter
c = Counter(runs)
print("\n连续相同坐标的游程长度分布（前 12 种）:")
for length, cnt in sorted(c.items())[:12]:
    print(f"   长度 {length:>5} 帧   出现 {cnt:>6} 次   合计 {length*cnt:>7} 帧  ({100*length*cnt/n:>5.1f}%)")

# 有多少帧处在长度 >=17 的游程里（17 帧 ≈ 0.57 秒，正好覆盖 ±8 的窗口）
in_long = sum(l*cnt for l, cnt in c.items() if l >= 17)
in_any = sum(l*cnt for l, cnt in c.items() if l >= 2)
print(f"\n处在长度>=2   游程里的帧: {in_any:>7}  ({100*in_any/n:>5.1f}%)   即 GPS 重复")
print(f"处在长度>=17  游程里的帧: {in_long:>7}  ({100*in_long/n:>5.1f}%)   即 ±8 窗口内无位移")
print(f"最长游程: {max(runs)} 帧 = {max(runs)/30:.2f} 秒")

# 看几段长游程的位置
long_idx = [i for i in range(n) if runs[i] >= 60] if False else None
idx = 0
print("\n最长的几段静止（位置、时间区间）:")
pairs = []
cur = 1
for i in range(1, n):
    if coords[i][0] == coords[i-1][0] and coords[i][1] == coords[i-1][1]:
        cur += 1
    else:
        pairs.append((cur, i-cur))
        cur = 1
pairs.append((cur, n-cur))
for length, start in sorted(pairs, reverse=True)[:6]:
    print(f"   第 {start:>6}~{start+length-1:>6} 点  {times[start]:>8.1f}~{times[start+length-1]:>8.1f} 秒"
          f"  持续 {length/30:>5.2f} 秒   坐标 {coords[start][0]:.6f},{coords[start][1]:.6f}")
