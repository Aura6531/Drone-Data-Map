# -*- coding: utf-8 -*-
"""验证 flight_profile：悬停延时 vs 真实航线。

用**真实素材**标定（这是关键 —— 上一轮我就是因为采样错了，把真航线看成悬停）。
"""
import sys
from pathlib import Path

sys.path.insert(0, r"<仓库根>\Code")
import coverage as cov
import pano360_coverage as pc
import project_manager as pm

ROOT = Path(r"<仓库根>\Data\360视频")

CASES = [
    ("贡嘎 0004（真悬停延时）", ROOT / "贡嘎" / "DJI_001" / "DJI_20261015071803_0004_D", "hover"),
    ("贡嘎 0001（真航线）",     ROOT / "贡嘎" / "DJI_001" / "DJI_20261015075758_0001_D", "transit"),
    ("贡嘎 0003（2.2s 极短）",  ROOT / "贡嘎" / "DJI_001" / "DJI_20261015071758_0003_D", None),
    ("DJI_001 0002（62s 悬停）", ROOT / "DJI_001" / "DJI_20261014110343_0002_D", None),
    ("DJI_001 0002b（528s）",   ROOT / "DJI_001" / "DJI_20261015142247_0002_D", None),
]

ok = True


def chk(cond, label, extra=""):
    global ok
    if not cond:
        ok = False
    print("  [%s] %s%s" % ("OK" if cond else "FAIL", label,
                           (" -> " + str(extra)) if extra else ""))


print("=== 逐条算飞行剖面 ===")
print("  %-24s %-9s %10s %10s %8s %10s" % (
    "素材", "判定", "水平漂移", "高度跨度", "比值", "时长"))
print("  " + "-" * 82)
for tag, stem, want in CASES:
    srt = stem.with_suffix(".SRT")
    if not srt.is_file():
        print("  %-24s （缺 SRT）" % tag)
        continue
    recs = pm.parse_dji_srt(srt)
    tele = pm.load_srt_telemetry(srt)
    step = cov.TELEMETRY_STEP
    samples = []
    for i in range(tele["count"]):
        j = i * step
        if j >= len(recs):
            break
        samples.append((tele["times"][i] if i < len(tele["times"]) else 0.0,
                        recs[j]["latitude"], recs[j]["longitude"],
                        tele["alt"][i] if i < len(tele["alt"]) else 0.0))
    p = pc.flight_profile(samples)
    print("  %-24s %-9s %10s %10s %8s %10s" % (
        tag, p.get("kind"), p.get("drift_m"), p.get("alt_span_m"),
        p.get("ratio"), p.get("seconds")))
    if want:
        chk(p.get("kind") == want, "%s 判定为 %s" % (tag, want), p.get("kind"))
    if tag.startswith("贡嘎 0004"):
        chk(p.get("drift_m") is not None and p["drift_m"] <= 5.0,
            "真悬停的水平漂移确实接近 0", p.get("drift_m"))
    if tag.startswith("贡嘎 0001"):
        chk(p.get("drift_m") is not None and p["drift_m"] > 1000.0,
            "真航线的水平漂移超过 1000 m（这正是我上一轮看错的数）",
            p.get("drift_m"))

print()
print("=== 边界行为 ===")
chk(pc.flight_profile([])["kind"] == "unknown", "空输入 -> unknown")
chk(pc.flight_profile([(0, 30.0, 101.0, 50.0)])["kind"] == "unknown",
    "只有一个点 -> unknown")
# 高度几乎不变 + 位移很小 -> hover
chk(pc.flight_profile([(0, 30.0, 101.0, 50.0), (10, 30.0, 101.0, 50.2)])["kind"] == "hover",
    "高度不变 + 不动 -> hover")
# 高度几乎不变 + 位移很大 -> transit
chk(pc.flight_profile([(0, 30.0, 101.0, 50.0), (10, 30.01, 101.0, 50.2)])["kind"] == "transit",
    "高度不变 + 飞了 1km -> transit")
# 高度变了很多 + 位移不大 -> hover（比如垂直升降取景）
chk(pc.flight_profile([(0, 30.0, 101.0, 20.0), (10, 30.0, 101.0, 120.0)])["kind"] == "hover",
    "原地升降 100m -> hover（水平没动）")

print()
print("结果:", "全部通过" if ok else "有失败项")
raise SystemExit(0 if ok else 1)
