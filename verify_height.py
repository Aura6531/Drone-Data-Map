"""验证：用 SRT 遥测的 alt 替代 3D GeoJSON 的 point_heights 是否等价。"""
import json, sys, io
from pathlib import Path
sys.path.insert(0, r"<仓库根>\Code")
sys.stdout.reconfigure(encoding="utf-8")
import project_manager as pm

ROOT = Path(r"<仓库根>\Data\DJI_202609240950_001")
TAG = "V"

plain = json.loads((ROOT / f"DJI_20260924095258_0001_{TAG}.geojson").read_text(encoding="utf-8"))
three = json.loads((ROOT / f"DJI_20260924095258_0001_{TAG}.3d.geojson").read_text(encoding="utf-8"))

pt = plain["features"][0]["properties"]
tt = three["features"][0]["properties"]

print("=== 1) 两份 GeoJSON 的 point_times 是否一致 ===")
same_times = pt["point_times"] == tt["point_times"]
print(f"   point_times 完全相同: {same_times}   长度 {len(pt['point_times'])} / {len(tt['point_times'])}")
p2 = plain["features"][0]["geometry"]["coordinates"]
p3 = three["features"][0]["geometry"]["coordinates"]
print(f"   coordinates 长度: 2D={len(p2)}  3D={len(p3)}")
print(f"   point_heights 长度: {len(tt['point_heights'])}")

print("\n=== 2) 3D 的 point_heights 与它自己坐标第三维是否一致 ===")
same_z = all(abs(p3[i][2] - tt["point_heights"][i]) < 1e-9 for i in range(len(p3)))
print(f"   完全一致: {same_z}")

print("\n=== 3) 核心：SRT 里的 rel_alt 与 point_heights 是否一致 ===")
tel = pm.load_srt_telemetry(ROOT / f"DJI_20260924095258_0001_{TAG}.srt")
times, alts = tel["times"], tel["alt"]
print(f"   SRT 遥测: {len(times)} 个采样点，alt 范围 {min(alts):.3f} ~ {max(alts):.3f} m")

# 后端用的是同样的做法：按时间取最近的点
import bisect
def alt_at(t):
    i = bisect.bisect_left(times, t)
    i = min(max(i, 0), len(times) - 1)
    return alts[i]

n = len(pt["point_times"])
worst = 0.0
worst_i = -1
for i in range(n):
    a = alt_at(pt["point_times"][i])
    b = tt["point_heights"][i]
    d = abs(a - b)
    if d > worst:
        worst, worst_i = d, i

print(f"   逐点比对 {n} 个点，最近点法最大差值 = {worst:.6f} m（第 {worst_i} 点）")

# 加线性插值：遥测每 3 帧一个点，GeoJSON 是逐帧的，取最近点会差近 1 米
def interp_at(t):
    if t <= times[0]:
        return alts[0]
    if t >= times[-1]:
        return alts[-1]
    i = bisect.bisect_left(times, t)
    lo, hi = i - 1, i
    span = times[hi] - times[lo]
    r = (t - times[lo]) / span if span > 0 else 0
    return alts[lo] + (alts[hi] - alts[lo]) * r

worst2 = 0.0
worst2_i = -1
for i in range(n):
    d = abs(interp_at(pt["point_times"][i]) - tt["point_heights"][i])
    if d > worst2:
        worst2, worst2_i = d, i

print(f"   逐点比对 {n} 个点，线性插值法最大差值 = {worst2:.6f} m（第 {worst2_i} 点）")
print(f"   抽样（显示精度是 0.1 m）：")
for i in (0, 1, n // 4, n // 2, n - 1):
    t = pt["point_times"][i]
    print(f"     #{i:<6} t={t:>9.3f}s   最近点={alt_at(t):>7.3f}   插值={interp_at(t):>7.3f}   "
          f"point_heights={tt['point_heights'][i]:>7.3f}")

ok = worst2 < 0.05
print(f"\n结论：线性插值后最大差 {worst2:.4f} m —— "
      f"{'远小于 0.1 m 显示精度，可视为等价' if ok else '仍有可见偏差'}")

print("\n=== 4) 差异为什么这么大？看第 7 点附近的原始数值 ===")
print(f"   GeoJSON point_times 前 12 个: {[round(t,4) for t in pt['point_times'][:12]]}")
print(f"   遥测 times 前 8 个:          {[round(t,4) for t in times[:8]]}")
print(f"   GeoJSON point_heights 前 12: {[round(h,4) for h in tt['point_heights'][:12]]}")
print(f"   遥测 alt 前 8 个:            {[round(a,4) for a in alts[:8]]}")
print()
print(f"   {'i':>4} {'point_times':>12} {'point_heights':>14} {'遥测最近t':>12} {'遥测alt':>10} {'插值':>10} {'差':>8}")
for i in range(12):
    t = pt["point_times"][i]
    j = min(bisect.bisect_left(times, t), len(times) - 1)
    print(f"   {i:>4} {t:>12.4f} {tt['point_heights'][i]:>14.4f} {times[j]:>12.4f} {alts[j]:>10.4f} "
          f"{interp_at(t):>10.4f} {interp_at(t)-tt['point_heights'][i]:>8.4f}")

# 高度值本身是不是每 3 帧才变一次？
uniq = len(set(tt["point_heights"]))
print(f"\n   point_heights 的不同取值数: {uniq} / {len(tt['point_heights'])} 个点")
print(f"   alt 的不同取值数:          {len(set(alts))} / {len(alts)} 个采样点")
print(f"   -> 高度是台阶状的（GPS 高度按帧跳变），跨台阶插值必然差一个台阶")

errs = sorted(abs(interp_at(pt["point_times"][i]) - tt["point_heights"][i]) for i in range(n))
med = errs[n // 2]
p90 = errs[int(n * 0.90)]
p99 = errs[int(n * 0.99)]
within = sum(1 for e in errs if e <= 0.1001)
print(f"\n   误差分布（插值法 vs point_heights，共 {n} 点）：")
print(f"     中位数 {med:.4f} m   90分位 {p90:.4f} m   99分位 {p99:.4f} m   最大 {errs[-1]:.4f} m")
print(f"     与 3D 文件显示到 0.1 m 后完全一致的点：{within}/{n} = {100*within/n:.2f}%")

sys.exit(0 if ok else 1)
